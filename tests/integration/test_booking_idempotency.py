"""
Fix 1.1 — Booking Idempotency integration tests.

These tests exercise BookingService.create_booking() directly, not via
the HTTP /transport/book route. The route is wrapped by pre-existing
decorators (@require_kyc_tier(2), @require_profile_completion) that are
not part of Fix 1.1. Calling the service isolates the idempotency
guarantee from those unrelated gates.

Guarantee under test:
  Same (idempotency_key, user_id) → exactly one Booking row.
  Second and subsequent submissions return the first booking's
  booking_reference without side effects.
"""
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

import pytest


def _unique_key(prefix):
    """Per-run unique idempotency key.

    The partial unique index ix_booking_idem is GLOBAL on
    idempotency_key (per Fix 1.1 contract Section 5). A fixed key
    whose Booking row survives a run would collide with a fresh
    test_user on the next run. Unique keys keep the suite
    repeatable regardless of leftover rows.
    """
    return f"{prefix}-{uuid.uuid4().hex}"


def _get_user_id(app, test_user):
    """Safely extract the internal user id from a detached User object.

    The test_user fixture commits and returns a detached instance.
    Attribute access on a detached instance triggers a refresh that
    fails with no session bound. merge() re-binds a transient copy to
    a fresh session so column values can be read reliably.
    """
    from app.extensions import db
    with app.app_context():
        merged = db.session.merge(test_user)
        uid = merged.id
        db.session.rollback()
        return uid


def _base_payload():
    return {
        "pickup_location": "Test Pickup",
        "dropoff_location": "Test Dropoff",
        "service_type": "on_demand",
        "pickup_time": "2026-12-31T10:00:00",
        "passenger_count": 1,
        "currency": "USD",
        "vehicle_class": "comfort",
        "payment_method": "cash",
    }


def _call_service(app, user_id, idem_key, payload=None):
    """Call BookingService.create_booking directly.

    Bypasses HTTP decorators (KYC tier 2, profile completion) which are
    pre-existing and out of scope for Fix 1.1.
    """
    from app.transport.services.booking_service import BookingService
    with app.app_context():
        data = _base_payload()
        if payload:
            data.update(payload)
        data["idempotency_key"] = idem_key
        service = BookingService()
        return service.create_booking(
            user_id, data, request_id=f"test-{idem_key}"
        )


def _count_bookings(app, idem_key, user_id):
    from app.transport.models import Booking
    with app.app_context():
        return Booking.query.filter_by(
            idempotency_key=idem_key,
            user_id=user_id,
            is_deleted=False,
        ).count()


def _get_booking_reference(app, idem_key, user_id):
    from app.transport.models import Booking
    with app.app_context():
        booking = Booking.query.filter_by(
            idempotency_key=idem_key,
            user_id=user_id,
            is_deleted=False,
        ).first()
        return booking.booking_reference if booking else None


def _cleanup_key(app, idem_key):
    """Delete every Booking row that carries a given idempotency_key.

    Threaded tests skip _isolate_db (conftest auto-cleanup), so they
    must self-clean every row they create -- established convention
    (see tests/test_transport_concurrent_claim.py _delete). Without
    this, the committed row survives the run and breaks the next run
    via the global unique index ix_booking_idem.
    """
    from app.extensions import db
    from app.transport.models import Booking
    with app.app_context():
        Booking.query.filter_by(idempotency_key=idem_key).delete(
            synchronize_session=False
        )
        db.session.commit()


class TestBookingIdempotency:

    def test_first_post_creates_booking(self, app, test_user):
        """First submission with a new key creates exactly one booking."""
        user_id = _get_user_id(app, test_user)
        idem_key = _unique_key("idem-test-first")

        result = _call_service(app, user_id, idem_key)

        assert result.get("success") is True, f"Service failed: {result}"
        # First call must NOT be flagged as a replay
        assert result["data"].get("idempotent_replay") in (None, False)
        assert _count_bookings(app, idem_key, user_id) == 1

    def test_second_post_returns_existing_booking(self, app, test_user):
        """Second submission with the same key returns the same reference."""
        user_id = _get_user_id(app, test_user)
        idem_key = _unique_key("idem-test-second")

        first = _call_service(app, user_id, idem_key)
        assert first.get("success") is True
        ref_first = first["data"]["booking_reference"]

        second = _call_service(app, user_id, idem_key)
        assert second.get("success") is True
        assert second["data"]["booking_reference"] == ref_first
        assert second["data"].get("idempotent_replay") is True

        # Still exactly one row
        assert _count_bookings(app, idem_key, user_id) == 1

    def test_different_keys_create_different_bookings(self, app, test_user):
        """Different keys create separate bookings."""
        user_id = _get_user_id(app, test_user)
        key1 = _unique_key("idem-test-diff")
        key2 = _unique_key("idem-test-diff")

        r1 = _call_service(app, user_id, key1)
        r2 = _call_service(app, user_id, key2)

        assert r1.get("success") is True
        assert r2.get("success") is True

        ref1 = r1["data"]["booking_reference"]
        ref2 = r2["data"]["booking_reference"]
        assert ref1 != ref2

        assert _count_bookings(app, key1, user_id) == 1
        assert _count_bookings(app, key2, user_id) == 1

    @pytest.mark.threaded
    def test_concurrent_same_key_creates_exactly_one(self, app, test_user):
        """Five concurrent submissions with the same key → one row.

        The loser of the DB unique-index race must be converted into a
        replay, not a ServiceUnavailableError.
        """
        user_id = _get_user_id(app, test_user)
        idem_key = _unique_key("idem-test-concurrent")

        def submit():
            return _call_service(app, user_id, idem_key)

        results = []
        try:
            with ThreadPoolExecutor(max_workers=5) as executor:
                futures = [executor.submit(submit) for _ in range(5)]
                for f in as_completed(futures):
                    results.append(f.result())
            # Capture asserts BEFORE cleanup: _cleanup_key deletes the rows
            # and counting after cleanup would report 0.
            row_count = _count_bookings(app, idem_key, user_id)
            replay_count = sum(
                1 for r in results
                if r.get("data", {}).get("idempotent_replay")
            )
        finally:
            # Threaded tests skip _isolate_db auto-cleanup; remove the
            # committed keyed row so it cannot poison the next run via
            # the global unique index ix_booking_idem.
            _cleanup_key(app, idem_key)

        # Every thread must report success
        for r in results:
            assert r.get("success") is True, f"Thread failed: {r}"

        # Exactly one row existed at commit time
        assert row_count == 1

        # At least one result must be flagged as a replay
        assert replay_count >= 1, (
            f"Expected at least one replay among {len(results)} results; "
            f"got {replay_count}"
        )