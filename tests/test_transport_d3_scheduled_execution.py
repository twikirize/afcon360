# tests/test_transport_d3_scheduled_execution.py
"""TH-3-D3 SCHEDULED TRANSPORT EXECUTION ENGINE — FINAL EVIDENCE GATE.

Proves the D3 contracts:

  E1  Due route (next_departure passed, unclaimed) is claimed via the guarded
      `last_departure = next_departure` UPDATE, and its attached
      CONFIRMED+unassigned bookings advance into the canonical dispatch chain
      (MatchingService.discover_and_offer -> transient offer).
  E2  Idempotency: a claimed departure is never executed twice (re-run no-ops;
      a second beat cannot re-claim the same next_departure).
  E3  Concurrency: two parallel task runs exactly one claim for the same
      departure (guarded UPDATE, rowcount==1) — no double dispatch.
  E4  Negatives: not-due, cancelled, inactive, soft-deleted routes are skipped.
  E5  Status boundary: only CONFIRMED+unassigned attached bookings are
      dispatched; DRAFT / PENDING_PAYMENT attached bookings are left alone
      (payment-state separation preserved, M5 not silently resolved).
  E6  dry_run reports due routes without claiming or dispatching.
  E7  No new Booking is created (per-user scheduled Booking progression, not
      instance creation) — Booking.user_id stays NOT NULL and route execution
      only dispatches existing attached bookings.

These tests reuse the helpers and patterns from tests/test_transport_concurrent_claim.py.
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func

from app.extensions import db
from app.transport.models import (
    Booking,
    BookingStatus,
    ComplianceStatus,
    DriverProfile,
    DriverVehicleHistory,
    ScheduledRoute,
    Vehicle,
    VehicleClass,
)
from app.transport.services.offer_service import OfferService
from tests.test_transport_concurrent_claim import (
    _FakeRedis,
    _bk_field,
    _create_booking,
    _create_driver,
    _create_user,
    _create_vehicle,
    _delete,
    _make_matchable_driver,
)


# =====================================================================
# Helpers — route + attached booking
# =====================================================================

def _create_route(app, label, *, next_departure, is_active=True, is_cancelled=False):
    """Create a ScheduledRoute row. Returns the internal route id."""
    uid = uuid.uuid4().hex[:8]
    with app.app_context():
        route = ScheduledRoute(
            provider_type="system",
            provider_id=1,
            name=f"{label}_{uid}",
            route_type="shuttle",
            route_code=f"RT-{label}-{uid.upper()}",
            schedule_pattern={"frequency": "manual"},
            timezone="UTC",
            stops=[
                {"name": "Start", "latitude": 0.3476, "longitude": 32.5825},
                {"name": "End", "latitude": 0.3130, "longitude": 32.5812},
            ],
            vehicle_capacity=4,
            next_departure=next_departure,
            last_departure=None,
            is_active=is_active,
            is_cancelled=is_cancelled,
        )
        db.session.add(route)
        db.session.commit()
        return route.id


def _attach_booking(app, booking_id, route_id):
    """Attach a booking to a scheduled route (assigned_route_id FK)."""
    with app.app_context():
        bk = db.session.get(Booking, booking_id)
        bk.assigned_route_id = route_id
        db.session.commit()


def _route_field(app, route_id, field):
    with app.app_context():
        return getattr(db.session.get(ScheduledRoute, route_id), field)


# =====================================================================
# E1: due route dispatches attached CONFIRMED+unassigned bookings
# =====================================================================

def test_due_route_dispatches_confirmed_bookings(app, monkeypatch):
    fake = _FakeRedis()
    monkeypatch.setattr("app.transport.services.offer_service.redis_client", fake)

    pax_id = _create_user(app, "paxD3")
    _, drv, veh, hist = _make_matchable_driver(app, "d3")
    bk_id, bk_ref = _create_booking(app, pax_id, "d3")

    route_id = _create_route(
        app, "r1", next_departure=datetime.now(timezone.utc) - timedelta(minutes=5)
    )
    _attach_booking(app, bk_id, route_id)

    from app.tasks.transport_recovery import scheduled_route_execution
    result = scheduled_route_execution()

    assert route_id in result["claimed"], result
    assert bk_id in result["bookings_dispatched"], result
    assert result["offers_created"] >= 1, result
    assert OfferService.get_offer(bk_ref) is not None
    # Claim marker written: departure is now claimed (idempotent for next run)
    assert _route_field(app, route_id, "last_departure") is not None

    _delete(app, (DriverVehicleHistory, hist), (Booking, bk_id),
            (ScheduledRoute, route_id), (DriverProfile, drv), (Vehicle, veh))


# =====================================================================
# E2: idempotency — a claimed departure never re-executes
# =====================================================================

def test_claimed_departure_is_not_reexecuted(app, monkeypatch):
    fake = _FakeRedis()
    monkeypatch.setattr("app.transport.services.offer_service.redis_client", fake)

    pax_id = _create_user(app, "paxIdem")
    bk_id, bk_ref = _create_booking(app, pax_id, "idem")

    route_id = _create_route(
        app, "r2", next_departure=datetime.now(timezone.utc) - timedelta(minutes=1)
    )
    _attach_booking(app, bk_id, route_id)

    from app.tasks.transport_recovery import scheduled_route_execution
    first = scheduled_route_execution()
    second = scheduled_route_execution()

    assert route_id in first["claimed"]
    assert route_id not in second["claimed"], second
    assert bk_id in first["bookings_dispatched"]
    assert bk_id not in second.get("bookings_dispatched", []), second
    assert second["considered"] == 0 or route_id not in second["claimed"]

    _delete(app, (Booking, bk_id), (ScheduledRoute, route_id))


# =====================================================================
# E3: concurrency — two parallel runs, exactly one claim
# =====================================================================

@pytest.mark.threaded
def test_concurrent_runs_claim_exactly_once(app, monkeypatch):
    from threading import Barrier, Thread

    fake = _FakeRedis()
    monkeypatch.setattr(
        "app.transport.services.offer_service.redis_client",
        fake,
    )

    pax_id = _create_user(app, "paxConc")
    bk_id, bk_ref = _create_booking(app, pax_id, "conc")

    route_id = _create_route(
        app, "r3", next_departure=datetime.now(timezone.utc) - timedelta(minutes=2)
    )
    _attach_booking(app, bk_id, route_id)

    from app.tasks.transport_recovery import scheduled_route_execution

    barrier = Barrier(2)
    results = [None, None]
    errors = [None, None]

    def run(idx):
        with app.app_context():
            barrier.wait(timeout=5)
            try:
                results[idx] = scheduled_route_execution()
            except Exception as e:  # noqa: BLE001
                errors[idx] = e

    t0 = Thread(target=run, args=(0,))
    t1 = Thread(target=run, args=(1,))
    t0.start(); t1.start()
    t0.join(timeout=10); t1.join(timeout=10)

    assert errors[0] is None and errors[1] is None, errors

    claims = [
        r["claimed"] for r in results if r and route_id in r["claimed"]
    ]
    assert len(claims) == 1, f"Expected exactly 1 claim, got {claims}"
    # Exactly one worker dispatched the booking too.
    dispatches = [
        r for r in results if r and bk_id in r.get("bookings_dispatched", [])
    ]
    assert len(dispatches) == 1, f"Expected exactly 1 dispatch, got {dispatches}"

    _delete(app, (Booking, bk_id), (ScheduledRoute, route_id))


# =====================================================================
# E4: negatives — not due / cancelled / inactive / soft-deleted
# =====================================================================

def test_not_due_route_is_skipped(app):
    future = datetime.now(timezone.utc) + timedelta(hours=3)
    route_id = _create_route(app, "rFut", next_departure=future)

    from app.tasks.transport_recovery import scheduled_route_execution
    result = scheduled_route_execution()

    assert route_id not in result["claimed"], result
    assert result["considered"] == 0 or route_id not in result["claimed"]

    _delete(app, (ScheduledRoute, route_id))


def test_cancelled_route_is_skipped(app):
    route_id = _create_route(
        app, "rCan",
        next_departure=datetime.now(timezone.utc) - timedelta(minutes=5),
        is_cancelled=True,
    )

    from app.tasks.transport_recovery import scheduled_route_execution
    result = scheduled_route_execution()

    assert route_id not in result["claimed"], result

    _delete(app, (ScheduledRoute, route_id))


def test_inactive_route_is_skipped(app):
    route_id = _create_route(
        app, "rIna",
        next_departure=datetime.now(timezone.utc) - timedelta(minutes=5),
        is_active=False,
    )

    from app.tasks.transport_recovery import scheduled_route_execution
    result = scheduled_route_execution()

    assert route_id not in result["claimed"], result

    _delete(app, (ScheduledRoute, route_id))


def test_soft_deleted_route_is_skipped(app):
    route_id = _create_route(
        app, "rDel", next_departure=datetime.now(timezone.utc) - timedelta(minutes=5)
    )
    with app.app_context():
        route = db.session.get(ScheduledRoute, route_id)
        route.is_deleted = True
        db.session.commit()

    from app.tasks.transport_recovery import scheduled_route_execution
    result = scheduled_route_execution()

    assert route_id not in result["claimed"], result

    _delete(app, (ScheduledRoute, route_id))


# =====================================================================
# E5: status boundary — only CONFIRMED+unassigned attached bookings dispatch
# =====================================================================

def test_draft_and_pending_payment_attached_bookings_are_not_dispatched(app, monkeypatch):
    fake = _FakeRedis()
    monkeypatch.setattr("app.transport.services.offer_service.redis_client", fake)

    pax_id = _create_user(app, "paxBound")
    draft_id, draft_ref = _create_booking(
        app, pax_id, "draft", status=BookingStatus.DRAFT
    )
    pending_id, pending_ref = _create_booking(
        app, pax_id, "pend", status=BookingStatus.PENDING_PAYMENT
    )

    route_id = _create_route(
        app, "r5", next_departure=datetime.now(timezone.utc) - timedelta(minutes=5)
    )
    _attach_booking(app, draft_id, route_id)
    _attach_booking(app, pending_id, route_id)

    from app.tasks.transport_recovery import scheduled_route_execution
    result = scheduled_route_execution()

    # Route still claims/turns over its departure…
    assert route_id in result["claimed"], result
    # …but only executable (CONFIRMED) bookings are advanced.
    assert draft_id not in result["bookings_dispatched"], result
    assert pending_id not in result["bookings_dispatched"], result
    assert OfferService.get_offer(draft_ref) is None
    assert OfferService.get_offer(pending_ref) is None
    # Statuses untouched (payment-state separation preserved).
    assert _bk_field(app, draft_id, "status") == BookingStatus.DRAFT.value
    assert _bk_field(app, pending_id, "status") == BookingStatus.PENDING_PAYMENT.value

    _delete(app, (Booking, draft_id), (Booking, pending_id), (ScheduledRoute, route_id))


# =====================================================================
# E6: dry_run — reports but never claims/dispatches
# =====================================================================

def test_dry_run_does_not_claim_or_dispatch(app, monkeypatch):
    fake = _FakeRedis()
    monkeypatch.setattr("app.transport.services.offer_service.redis_client", fake)

    pax_id = _create_user(app, "paxDry")
    bk_id, bk_ref = _create_booking(app, pax_id, "dry")

    route_id = _create_route(
        app, "r6", next_departure=datetime.now(timezone.utc) - timedelta(minutes=5)
    )
    _attach_booking(app, bk_id, route_id)

    from app.tasks.transport_recovery import scheduled_route_execution
    result = scheduled_route_execution(dry_run=True)

    assert result["dry_run"] is True
    assert result["considered"] >= 1
    assert route_id in result["candidates"], result
    assert route_id not in result["claimed"], result
    assert bk_id not in result.get("bookings_dispatched", []), result
    # Not claimed, so it remains eligible for the next live run.
    assert _route_field(app, route_id, "last_departure") is None
    assert _bk_field(app, bk_id, "status") == BookingStatus.CONFIRMED.value

    _delete(app, (Booking, bk_id), (ScheduledRoute, route_id))


# =====================================================================
# E7: no new Booking is created — count is invariant under execution
# =====================================================================

def test_execution_does_not_create_new_bookings(app, monkeypatch):
    fake = _FakeRedis()
    monkeypatch.setattr("app.transport.services.offer_service.redis_client", fake)

    pax_id = _create_user(app, "paxInv")
    bk_id, bk_ref = _create_booking(app, pax_id, "inv")

    route_id = _create_route(
        app, "r7", next_departure=datetime.now(timezone.utc) - timedelta(minutes=5)
    )
    _attach_booking(app, bk_id, route_id)

    with app.app_context():
        before = db.session.query(func.count(Booking.id)).scalar()

    from app.tasks.transport_recovery import scheduled_route_execution
    result = scheduled_route_execution()

    with app.app_context():
        after = db.session.query(func.count(Booking.id)).scalar()

    assert route_id in result["claimed"], result
    assert before == after, "scheduled-route execution must not create new Bookings"

    _delete(app, (Booking, bk_id), (ScheduledRoute, route_id))