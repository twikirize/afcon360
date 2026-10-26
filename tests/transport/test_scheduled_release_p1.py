"""PICKUP-TIME-AUTHORITY-P1 — Deploy 2 behavior contract.

Covers the Deploy-2 (mode-aware dispatch + Phase B schema) half of the node:

- Booking carries pickup_mode + request_received_at; pickup_time is nullable;
  ck_pickup_mode_valid / ck_pickup_time_mode_aware exist in model metadata
  (source of truth for the constraint sync tool)
- create_booking persists the mode + request receipt time on the row
- central gate: a SCHEDULED ride dispatches only inside the 30-minute lead
  window (discover_and_offer) and its stale matching window is never closed
  as NO_MATCH before that window (check_matching_outcome)
- metadata-only legacy scheduled rows are still gated
- instant and mode-less (legacy) rows are never gated
- transport.scheduled_booking_dispatch: confirms due cash scheduled rides,
  leaves non-cash pending, excludes assigned/not-yet-due rows
- driver trip actions stamp pickup_actual_time (start) and
  dropoff_actual_time (complete)
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.identity.models.user import User
from app.transport.models import (
    Booking,
    BookingStatus,
    ComplianceStatus,
    DriverProfile,
    DriverVehicleHistory,
    ServiceType,
    Vehicle,
    VehicleClass,
)
from app.transport.services.booking_service import get_booking_service
from app.transport.services.matching_service import MatchingService

LEAD_MINUTES = MatchingService.SCHEDULED_DISPATCH_LEAD_MINUTES


def _now():
    return datetime.now(timezone.utc)


def _create_user(app):
    with app.app_context():
        uid = uuid.uuid4().hex[:10]
        user = User(
            username=f"p1d2_{uid}",
            email=f"p1d2_{uid}@afcon360.local",
            is_active=True,
            is_verified=True,
        )
        user.set_password("TestPass123!")
        db.session.add(user)
        db.session.commit()
        return user.id


def _create_booking(
    app,
    user_id,
    *,
    mode,
    pickup_time,
    status=BookingStatus.CONFIRMED,
    payment_method="cash",
    metadata_mode=None,
    with_column_mode=True,
    assigned_driver_id=None,
    assigned_vehicle_id=None,
):
    ref = f"P1D2-{uuid.uuid4().hex[:10].upper()}"
    with app.app_context():
        booking = Booking(
            booking_reference=ref,
            user_id=user_id,
            provider_type="individual_driver",
            service_type=ServiceType.ON_DEMAND,
            pickup_location={"latitude": 0.3476, "longitude": 32.5825},
            dropoff_location={"latitude": 0.3130, "longitude": 32.5812},
            pickup_time=pickup_time,
            pickup_mode=mode if with_column_mode else None,
            request_received_at=_now(),
            base_price=100.00,
            subtotal=100.00,
            total_amount=100.00,
            final_price=100.00,
            passenger_count=1,
            status=status,
            payment_method=payment_method,
            assigned_driver_id=assigned_driver_id,
            assigned_vehicle_id=assigned_vehicle_id,
            booking_metadata={
                "booking_mode": metadata_mode or mode or "",
            },
        )
        db.session.add(booking)
        db.session.commit()
        return booking.id, ref


def _create_driver_with_vehicle(app):
    with app.app_context():
        uid = uuid.uuid4().hex[:10]
        user = User(
            username=f"p1d2drv_{uid}",
            email=f"p1d2drv_{uid}@afcon360.local",
            is_active=True,
            is_verified=True,
        )
        user.set_password("TestPass123!")
        db.session.add(user)
        db.session.commit()
        driver = DriverProfile(
            user_id=user.id,
            driver_code=f"P1D2-{uid.upper()}",
            verification_tier="platform_verified",
            compliance_status=ComplianceStatus.APPROVED,
            is_active=True,
            is_online=True,
            is_available=True,
            max_passenger_capacity=4,
            vehicle_classes=["comfort"],
        )
        db.session.add(driver)
        db.session.commit()
        vehicle = Vehicle(
            owner_type="driver",
            owner_id=driver.id,
            license_plate=f"UG-P1D2-{uid[:5].upper()}",
            make="Toyota",
            model="Corolla",
            year=2022,
            vehicle_type="sedan",
            vehicle_class=VehicleClass.COMFORT,
            passenger_capacity=4,
            status="active",
            is_available=True,
        )
        db.session.add(vehicle)
        db.session.commit()
        db.session.add(DriverVehicleHistory(
            driver_id=driver.id,
            vehicle_id=vehicle.id,
            assignment_reason="test_scheduled_release",
            started_at=_now(),
        ))
        db.session.commit()
        return driver.id, vehicle.id


# ---------------------------------------------------------------------------
# Phase B schema contract (model metadata = sync-tool source of truth)
# ---------------------------------------------------------------------------

class TestPhaseBSchema:

    def test_phase_b_columns_present(self):
        columns = Booking.__table__.c
        assert columns.pickup_mode.nullable is True
        assert columns.request_received_at.nullable is True
        assert columns.pickup_time.nullable is True

    def test_phase_b_checks_present(self):
        names = {c.name for c in Booking.__table__.constraints}
        assert "ck_pickup_mode_valid" in names
        assert "ck_pickup_time_mode_aware" in names

    def test_phase_b_check_expressions(self):
        sql = {
            c.name: " ".join(str(c.sqltext).split())
            for c in Booking.__table__.constraints
            if getattr(c, "name", None) in {
                "ck_pickup_mode_valid",
                "ck_pickup_time_mode_aware",
            }
        }
        assert sql["ck_pickup_mode_valid"] == (
            "pickup_mode IS NULL OR pickup_mode IN ('instant', 'scheduled')"
        )
        assert sql["ck_pickup_time_mode_aware"] == (
            "pickup_mode IS NULL OR pickup_mode = 'instant' "
            "OR pickup_time IS NOT NULL"
        )

    def test_live_check_constraint_definition(self, app):
        with app.app_context():
            definition = db.session.execute(
                text(
                    "select pg_get_constraintdef(oid) from pg_constraint "
                    "where conrelid = 'transport_bookings'::regclass "
                    "and conname = 'ck_pickup_time_mode_aware'"
                )
            ).scalar()
        normalized = " ".join((definition or "").split()).lower()
        assert normalized, "ck_pickup_time_mode_aware missing from live catalog"
        assert "pickup_mode is null" in normalized
        assert "'instant'" in normalized
        assert "pickup_time is not null" in normalized
        assert not normalized.startswith("check (((pickup_time is not null)")

    def test_create_booking_persists_mode_and_receipt_time(self, app):
        user_id = _create_user(app)
        result = get_booking_service().create_booking(
            user_id,
            {
                "service_type": "on_demand",
                "provider_type": "individual_driver",
                "booking_mode": "scheduled",
                "pickup_latitude": 0.3136,
                "pickup_longitude": 32.5811,
                "dropoff_latitude": 0.3476,
                "dropoff_longitude": 32.5825,
                "pickup_location": "Kampala",
                "dropoff_location": "Entebbe",
                "pickup_time": (_now() + timedelta(minutes=45)).isoformat(),
                "passenger_count": 1,
                "currency": "USD",
                "payment_method": "cash",
                "vehicle_class": "comfort",
            },
        )
        assert result["success"] is True
        with app.app_context():
            booking = db.session.get(Booking, result["data"]["booking_id"])
            assert booking.pickup_mode == "scheduled"
            assert booking.request_received_at is not None


class TestPickupConstraintBehavior:

    def test_instant_booking_without_pickup_time_is_allowed(self, app):
        user_id = _create_user(app)
        booking_id, _ = _create_booking(
            app, user_id, mode="instant", pickup_time=None)
        with app.app_context():
            booking = db.session.get(Booking, booking_id)
            assert booking is not None
            assert booking.pickup_mode == "instant"
            assert booking.pickup_time is None

    def test_scheduled_booking_without_pickup_time_is_rejected(self, app):
        user_id = _create_user(app)
        with pytest.raises(IntegrityError) as exc:
            _create_booking(
                app, user_id, mode="scheduled", pickup_time=None)
        assert "ck_pickup_time_mode_aware" in str(exc.value)
        with app.app_context():
            db.session.rollback()


# ---------------------------------------------------------------------------
# Central gate: scheduled rides only dispatch inside the lead window
# ---------------------------------------------------------------------------

class TestScheduledDispatchGate:

    def test_scheduled_before_window_is_held(self, app):
        user_id = _create_user(app)
        booking_id, _ = _create_booking(
            app, user_id, mode="scheduled",
            pickup_time=_now() + timedelta(hours=2),
        )
        outcome = MatchingService.discover_and_offer(booking_id)
        assert outcome == {
            "success": False,
            "reason": "scheduled_not_due",
            "offers_created": 0,
        }

    def test_legacy_scheduled_with_null_pickup_time_is_held(self, app):
        user_id = _create_user(app)
        booking_id, _ = _create_booking(
            app, user_id, mode=None,
            metadata_mode="scheduled",
            with_column_mode=False,
            pickup_time=None,
        )
        outcome = MatchingService.discover_and_offer(booking_id)
        assert outcome["reason"] == "scheduled_pickup_time_unset"
        assert outcome["offers_created"] == 0

    def test_scheduled_inside_window_dispatches(self, app, monkeypatch):
        user_id = _create_user(app)
        booking_id, _ = _create_booking(
            app, user_id, mode="scheduled",
            pickup_time=_now() + timedelta(minutes=10),
        )
        from app.transport.services import matching_service as ms
        from app.transport.services.offer_service import OfferService

        notified = []
        monkeypatch.setattr(
            MatchingService, "_ranked_candidates",
            lambda booking: ([], [{"driver_id": 11, "vehicle_id": 22}]),
        )
        monkeypatch.setattr(
            OfferService, "get_offer", staticmethod(lambda *a, **k: None),
        )
        monkeypatch.setattr(
            OfferService, "create_offer",
            staticmethod(lambda *a, **k: {"status": "offered"}),
        )
        monkeypatch.setattr(
            ms, "_notify_driver_new_offer",
            lambda booking, driver_id: notified.append(driver_id),
        )

        outcome = MatchingService.discover_and_offer(booking_id)
        assert outcome["success"] is True
        assert outcome["offers_created"] == 1
        assert notified == [11]

    def test_metadata_only_scheduled_row_is_gated(self, app):
        user_id = _create_user(app)
        booking_id, _ = _create_booking(
            app, user_id, mode=None,
            metadata_mode="scheduled",
            with_column_mode=False,
            pickup_time=_now() + timedelta(hours=2),
        )
        outcome = MatchingService.discover_and_offer(booking_id)
        assert outcome["reason"] == "scheduled_not_due"

    def test_instant_row_is_not_gated(self, app):
        user_id = _create_user(app)
        booking_id, _ = _create_booking(
            app, user_id, mode="instant",
            pickup_time=_now() + timedelta(hours=2),
        )
        outcome = MatchingService.discover_and_offer(booking_id)
        assert outcome.get("reason") != "scheduled_not_due"

    def test_sweep_does_not_close_scheduled_before_window(self, app):
        user_id = _create_user(app)
        booking_id, _ = _create_booking(
            app, user_id, mode="scheduled",
            pickup_time=_now() + timedelta(hours=2),
        )
        with app.app_context():
            booking = db.session.get(Booking, booking_id)
            booking.confirmed_at = _now() - timedelta(hours=2)
            db.session.commit()

        outcome = MatchingService.check_matching_outcome(booking_id)
        assert outcome == {"terminal": False, "reason": "scheduled_not_due"}
        with app.app_context():
            assert db.session.get(Booking, booking_id).status == \
                BookingStatus.CONFIRMED.value

    def test_sweep_still_closes_instant_after_expiry(self, app):
        user_id = _create_user(app)
        booking_id, _ = _create_booking(
            app, user_id, mode="instant",
            pickup_time=_now() + timedelta(hours=2),
        )
        with app.app_context():
            booking = db.session.get(Booking, booking_id)
            booking.confirmed_at = _now() - timedelta(hours=2)
            db.session.commit()

        outcome = MatchingService.check_matching_outcome(booking_id)
        assert outcome["terminal"] is True
        assert outcome["reason"] == "no_supply"


# ---------------------------------------------------------------------------
# Scheduled release beat: confirm due cash rides, dispatch inside window
# ---------------------------------------------------------------------------

class TestScheduledBookingDispatch:

    def test_due_cash_scheduled_is_confirmed_and_dispatched(
            self, app, monkeypatch):
        user_id = _create_user(app)
        booking_id, _ = _create_booking(
            app, user_id, mode="scheduled",
            pickup_time=_now() + timedelta(minutes=20),
            status=BookingStatus.PENDING_PAYMENT,
        )
        dispatched = []
        monkeypatch.setattr(
            MatchingService, "discover_and_offer",
            staticmethod(lambda bid: dispatched.append(bid)
                         or {"success": True, "offers_created": 1}),
        )

        from app.tasks.transport_recovery import scheduled_booking_dispatch
        result = scheduled_booking_dispatch()

        assert result["confirmed"] == [booking_id]
        assert result["dispatched"] == [booking_id]
        assert dispatched == [booking_id]
        with app.app_context():
            booking = db.session.get(Booking, booking_id)
            assert booking.status == BookingStatus.CONFIRMED.value
            assert booking.confirmed_at is not None

    def test_non_cash_pending_scheduled_is_left_alone(self, app, monkeypatch):
        user_id = _create_user(app)
        booking_id, _ = _create_booking(
            app, user_id, mode="scheduled",
            pickup_time=_now() + timedelta(minutes=20),
            status=BookingStatus.PENDING_PAYMENT,
            payment_method="wallet",
        )
        monkeypatch.setattr(
            MatchingService, "discover_and_offer",
            staticmethod(lambda bid: {"success": True, "offers_created": 1}),
        )

        from app.tasks.transport_recovery import scheduled_booking_dispatch
        result = scheduled_booking_dispatch()

        assert booking_id not in result["confirmed"]
        assert booking_id not in result["dispatched"]
        assert result["skipped"].get(booking_id) == "awaiting_payment"
        with app.app_context():
            assert db.session.get(Booking, booking_id).status == \
                BookingStatus.PENDING_PAYMENT.value

    def test_not_due_scheduled_is_not_considered(self, app, monkeypatch):
        user_id = _create_user(app)
        booking_id, _ = _create_booking(
            app, user_id, mode="scheduled",
            pickup_time=_now() + timedelta(hours=3),
        )
        monkeypatch.setattr(
            MatchingService, "discover_and_offer",
            staticmethod(lambda bid: {"success": True, "offers_created": 1}),
        )

        from app.tasks.transport_recovery import scheduled_booking_dispatch
        result = scheduled_booking_dispatch()

        assert booking_id not in result["dispatched"]
        assert result["considered"] == 0

    def test_assigned_scheduled_is_excluded(self, app, monkeypatch):
        user_id = _create_user(app)
        driver_id, vehicle_id = _create_driver_with_vehicle(app)
        booking_id, _ = _create_booking(
            app, user_id, mode="scheduled",
            pickup_time=_now() + timedelta(minutes=20),
            assigned_driver_id=driver_id,
            assigned_vehicle_id=vehicle_id,
        )
        monkeypatch.setattr(
            MatchingService, "discover_and_offer",
            staticmethod(lambda bid: {"success": True, "offers_created": 1}),
        )

        from app.tasks.transport_recovery import scheduled_booking_dispatch
        result = scheduled_booking_dispatch()

        assert booking_id not in result["dispatched"]
        assert result["considered"] == 0

    def test_metadata_only_scheduled_is_dispatched(self, app, monkeypatch):
        user_id = _create_user(app)
        booking_id, _ = _create_booking(
            app, user_id, mode=None,
            metadata_mode="scheduled",
            with_column_mode=False,
            pickup_time=_now() + timedelta(minutes=20),
        )
        monkeypatch.setattr(
            MatchingService, "discover_and_offer",
            staticmethod(lambda bid: {"success": True, "offers_created": 1}),
        )

        from app.tasks.transport_recovery import scheduled_booking_dispatch
        result = scheduled_booking_dispatch()

        assert result["dispatched"] == [booking_id]


# ---------------------------------------------------------------------------
# Actual pickup/dropoff timestamps on driver trip actions
# ---------------------------------------------------------------------------

class TestDriverActualTimes:

    def test_start_stamps_pickup_actual_time(self, app):
        user_id = _create_user(app)
        driver_id, _ = _create_driver_with_vehicle(app)
        booking_id, _ = _create_booking(
            app, user_id, mode="instant",
            pickup_time=_now() + timedelta(minutes=5),
            status=BookingStatus.PICKUP_ARRIVED,
            assigned_driver_id=driver_id,
        )
        from app.transport.api.driver_routes import (
            _execute_driver_trip_action,
        )
        with app.app_context():
            booking = db.session.get(Booking, booking_id)
            profile = db.session.get(DriverProfile, driver_id)
            body, code = _execute_driver_trip_action(
                booking, profile, "start", None)
        assert code == 200 and body["success"] is True, body
        with app.app_context():
            booking = db.session.get(Booking, booking_id)
            assert booking.status == BookingStatus.IN_PROGRESS.value
            assert booking.pickup_actual_time is not None

    def test_complete_stamps_dropoff_actual_time(self, app):
        user_id = _create_user(app)
        driver_id, vehicle_id = _create_driver_with_vehicle(app)
        booking_id, _ = _create_booking(
            app, user_id, mode="instant",
            pickup_time=_now() - timedelta(minutes=4),
            status=BookingStatus.IN_PROGRESS,
            assigned_driver_id=driver_id,
            assigned_vehicle_id=vehicle_id,
        )
        from app.transport.api.driver_routes import (
            _execute_driver_trip_action,
        )
        with app.app_context():
            booking = db.session.get(Booking, booking_id)
            profile = db.session.get(DriverProfile, driver_id)
            body, code = _execute_driver_trip_action(
                booking, profile, "complete", None)
        assert code == 200 and body["success"] is True, body
        with app.app_context():
            booking = db.session.get(Booking, booking_id)
            assert booking.status == BookingStatus.COMPLETED.value
            assert booking.completed_at is not None
            assert booking.dropoff_actual_time is not None
