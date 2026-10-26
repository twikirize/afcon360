"""CANCEL-FEE-SCHEDULED-P1 — scheduled cancellation + no-show contract.

Covers the server-owned policy (tiers/caps/currency), rider/admin
cancellation persistence, metadata-only driver credits, the driver
no-show lifecycle/API, and the rider/driver presentation hooks.
"""
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from app.audit.models import AuditLog
from app.extensions import db
from app.identity.models.user import User
from app.transport.models import (
    Booking,
    BookingStatus,
    ComplianceStatus,
    DriverProfile,
    ServiceType,
)
from app.transport.services.booking_service import (
    BookingService,
    get_booking_service,
)
from app.utils.enums import Currency
from app.utils.exceptions import PermissionError, ValidationError

NOW = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)


def _create_user(app, label="cf"):
    with app.app_context():
        uid = uuid.uuid4().hex[:8]
        user = User(
            username=f"{label}_{uid}",
            email=f"{label}_{uid}@test.example.com",
            is_verified=True,
            is_active=True,
        )
        user.set_password("TestPass123!")
        db.session.add(user)
        db.session.commit()
        return user.id


def _create_driver(app, label="cfd"):
    user_id = _create_user(app, label)
    with app.app_context():
        driver = DriverProfile(
            user_id=user_id,
            driver_code=f"DRV-{label}-{uuid.uuid4().hex[:6].upper()}",
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
        return user_id, driver.id


def _create_booking(app, user_id, *, status=BookingStatus.CONFIRMED,
                    mode="scheduled", pickup_time=None, driver_id=None,
                    provider_id=None, fare="100.00", label="cfb",
                    created_at=None):
    pickup = pickup_time or (datetime.now(timezone.utc) + timedelta(hours=2))
    with app.app_context():
        booking = Booking(
            created_at=created_at or datetime.now(timezone.utc),
            booking_reference=(
                f"CF-{label}-{uuid.uuid4().hex[:8].upper()}"
            ),
            user_id=user_id,
            provider_id=provider_id,
            provider_type="individual_driver",
            service_type=ServiceType.ON_DEMAND,
            pickup_location={"latitude": 0.3476, "longitude": 32.5825},
            dropoff_location={"latitude": 0.3130, "longitude": 32.5812},
            pickup_time=pickup,
            pickup_mode=mode,
            request_received_at=datetime.now(timezone.utc),
            base_price=Decimal(fare),
            subtotal=Decimal(fare),
            total_amount=Decimal(fare),
            final_price=Decimal(fare),
            passenger_count=1,
            status=status,
            currency=Currency.USD,
            assigned_driver_id=driver_id,
            booking_metadata={"booking_mode": mode},
        )
        db.session.add(booking)
        db.session.commit()
        return booking.id, booking.booking_reference


def _booking_field(app, booking_id, field):
    with app.app_context():
        return getattr(db.session.get(Booking, booking_id), field)


def _login_client(client, user):
    app = client.application
    with app.app_context():
        if isinstance(user, int):
            user = db.session.get(User, user)
        uid = str(user.public_id)
        db.session.rollback()
    with client.session_transaction() as session:
        session["_user_id"] = uid
        session["_fresh"] = True


def _transient_booking(*, mode="scheduled", pickup_delta=timedelta(hours=2),
                       fare="100.00", base=NOW):
    booking = Booking()
    booking.booking_metadata = {"booking_mode": mode} if mode else {}
    booking.pickup_mode = mode
    booking.pickup_time = base + pickup_delta
    booking.final_price = Decimal(fare)
    booking.currency = Currency.USD
    return booking


class TestScheduledFeePolicy:

    def test_tier_boundaries_and_caps(self):
        service = get_booking_service()

        cases = [
            (timedelta(hours=2), "more_than_1h", "0.00"),
            (timedelta(hours=1, seconds=1), "more_than_1h", "0.00"),
            (timedelta(hours=1), "15m_to_1h", "20.00"),
            (timedelta(minutes=30), "15m_to_1h", "20.00"),
            (timedelta(minutes=15), "15m_to_1h", "20.00"),
            (timedelta(minutes=14, seconds=59), "under_15m", "40.00"),
            (timedelta(0), "under_15m", "40.00"),
            (timedelta(seconds=-1), "under_15m", "40.00"),
        ]
        for delta, expected_tier, expected_fee in cases:
            policy = service._cancellation_policy(
                _transient_booking(pickup_delta=delta), now=NOW)
            assert policy["tier"] == expected_tier, delta
            assert policy["fee"] == Decimal(expected_fee), delta

    def test_caps_and_currency_are_face_value(self):
        service = get_booking_service()
        standard = service._cancellation_policy(
            _transient_booking(
                pickup_delta=timedelta(minutes=30), fare="100000.00"),
            now=NOW,
        )
        late = service._cancellation_policy(
            _transient_booking(
                pickup_delta=timedelta(minutes=10), fare="100000.00"),
            now=NOW,
        )
        assert standard["fee"] == Decimal("10000.00")
        assert late["fee"] == Decimal("20000.00")
        assert standard["currency"] == "USD"
        assert late["currency"] == "USD"

    def test_instant_and_mode_less_are_fail_safe_zero(self):
        service = get_booking_service()
        instant = service._cancellation_policy(
            _transient_booking(mode="instant"), now=NOW)
        missing = service._cancellation_policy(
            _transient_booking(mode=None), now=NOW)
        assert instant["scheduled"] is False
        assert instant["fee"] == Decimal("0.00")
        assert instant["tier"] == "not_scheduled"
        assert missing["scheduled"] is False
        assert missing["fee"] == Decimal("0.00")


class TestRiderCancellation:

    def test_pre_assignment_persists_fee_and_refund(self, app):
        rider = _create_user(app, "cfr")
        booking_id, ref = _create_booking(
            app, rider, status=BookingStatus.CONFIRMED,
            pickup_time=datetime.now(timezone.utc) + timedelta(minutes=30),
        )
        with app.app_context():
            result = get_booking_service().cancel_booking(
                booking_id, user_id=rider)
            booking = db.session.get(Booking, booking_id)
            assert result["data"]["booking_reference"] == ref
            assert result["data"]["cancellation_fee"] == 20.0
            assert result["data"]["refund_amount"] == 80.0
            assert result["data"]["fee_tier"] == "15m_to_1h"
            assert result["data"]["currency"] == "USD"
            assert booking.status == BookingStatus.CANCELLED
            assert booking.cancellation_fee == Decimal("20.00")
            assert booking.cancellation_initiated_by == "rider"
            assert booking.cancelled_stage == "confirmed"
            cancellation = booking.booking_metadata["cancellation"]
            assert cancellation["fee"] == "20.00"
            assert cancellation["policy"] == "scheduled_v1"
            assert cancellation["recorded_uncollected"] is True
            assert cancellation["initiated_by"] == "rider"
            assert cancellation["scheduled"] is True
            assert AuditLog.query.filter_by(
                action="booking_cancellation_fee_recorded",
                resource_id=str(booking_id),
            ).count() == 1

    def test_cancel_json_returns_fee_and_refund(self, app, client):
        rider = _create_user(app, "cfj")
        booking_id, ref = _create_booking(
            app, rider, status=BookingStatus.CONFIRMED,
            pickup_time=datetime.now(timezone.utc) + timedelta(minutes=30),
        )
        _login_client(client, rider)
        response = client.post(
            f"/transport/rides/{ref}/cancel",
            json={
                "reason": "changed plans",
                "reason_category": "rider_change_of_mind",
            },
        )
        assert response.status_code == 200, response.get_data(as_text=True)
        body = response.get_json()
        assert body["status"] == "success"
        assert body["data"]["booking_reference"] == ref
        assert body["data"]["cancellation_fee"] == 20.0
        assert body["data"]["refund_amount"] == 80.0
        assert body["data"]["currency"] == "USD"
        assert _booking_field(app, booking_id, "status") == (
            BookingStatus.CANCELLED)

    def test_safety_cancellation_waives_fee(self, app):
        rider = _create_user(app, "cfs")
        booking_id, _ = _create_booking(
            app, rider,
            pickup_time=datetime.now(timezone.utc) + timedelta(minutes=5),
        )
        with app.app_context():
            result = get_booking_service().cancel_booking(
                booking_id, user_id=rider,
                reason_category="driver_vehicle_mismatch")
            booking = db.session.get(Booking, booking_id)
            assert result["data"]["cancellation_fee"] == 0.0
            assert result["data"]["fee_tier"] == "safety"
            assert booking.cancellation_fee == Decimal("0.00")
            assert booking.cancellation_safety_flag is True
            assert "driver_cancellation_credits" not in (
                booking.booking_metadata or {})

    def test_non_rider_admin_path_charges_zero(self, app):
        rider = _create_user(app, "cfn")
        provider = _create_user(app, "cfp")
        booking_id, _ = _create_booking(
            app, rider, provider_id=provider,
            pickup_time=datetime.now(timezone.utc) + timedelta(minutes=5),
        )
        with app.app_context():
            result = get_booking_service().cancel_booking(
                booking_id, user_id=provider)
            booking = db.session.get(Booking, booking_id)
            assert result["data"]["cancellation_fee"] == 0.0
            assert result["data"]["fee_tier"] == "non_rider"
            assert booking.cancellation_initiated_by == "admin"
            assert booking.cancellation_fee == Decimal("0.00")

    def test_post_assignment_credits_driver_and_releases(self, app):
        rider = _create_user(app, "cfpa")
        driver_user, driver_id = _create_driver(app, "cfpa")
        booking_id, _ = _create_booking(
            app, rider, status=BookingStatus.DRIVER_EN_ROUTE,
            driver_id=driver_id,
            pickup_time=datetime.now(timezone.utc) + timedelta(minutes=30),
        )
        with app.app_context():
            driver = db.session.get(DriverProfile, driver_id)
            before_earnings = driver.total_earnings or Decimal("0.00")

            result = get_booking_service().cancel_booking(
                booking_id, user_id=rider)
            booking = db.session.get(Booking, booking_id)
            driver = db.session.get(DriverProfile, driver_id)

            assert result["data"]["cancellation_fee"] == 20.0
            assert result["data"]["driver_credit"] == 16.0
            assert booking.status == BookingStatus.CANCELLED
            assert booking.assigned_driver_id is None
            assert booking.assigned_vehicle_id is None
            credits = booking.booking_metadata[
                "driver_cancellation_credits"
            ]
            assert len(credits) == 1
            assert credits[0]["driver_code"] == driver.driver_code
            assert credits[0]["amount"] == "16.00"
            assert credits[0]["currency"] == "USD"
            assert credits[0]["reason"] == "late_cancellation"
            assert credits[0]["recorded_uncollected"] is True
            assert (driver.total_earnings or Decimal("0.00")) == (
                before_earnings)


class TestNoShow:

    def test_after_grace_records_fee_and_is_idempotent(self, app):
        rider = _create_user(app, "cfns")
        driver_user, driver_id = _create_driver(app, "cfns")
        booking_id, _ = _create_booking(
            app, rider, status=BookingStatus.PICKUP_ARRIVED,
            driver_id=driver_id,
            pickup_time=datetime.now(timezone.utc) - timedelta(minutes=20),
            created_at=datetime.now(timezone.utc) - timedelta(hours=2),
        )
        with app.app_context():
            service = get_booking_service()
            first = service.mark_no_show(booking_id, driver_user)
            booking = db.session.get(Booking, booking_id)
            assert first["data"]["cancellation_fee"] == 40.0
            assert first["data"]["driver_credit"] == 40.0
            assert first["data"]["idempotent"] is False
            assert booking.status == BookingStatus.NO_SHOW
            assert booking.assigned_driver_id is None
            assert booking.cancellation_fee == Decimal("40.00")
            assert booking.cancelled_stage == "pickup_arrived"
            assert booking.cancellation_initiated_by == "driver"
            no_show = booking.booking_metadata["no_show"]
            assert no_show["fee"] == "40.00"
            assert no_show["driver_credit"] == "40.00"
            credits = booking.booking_metadata[
                "driver_cancellation_credits"
            ]
            assert len(credits) == 1
            assert credits[0]["reason"] == "no_show"
            assert credits[0]["amount"] == "40.00"

            second = service.mark_no_show(booking_id, driver_user)
            booking = db.session.get(Booking, booking_id)
            assert second["data"]["idempotent"] is True
            assert second["data"]["cancellation_fee"] == 40.0
            assert len(booking.booking_metadata[
                "driver_cancellation_credits"]) == 1
            assert AuditLog.query.filter_by(
                action="booking_no_show_recorded",
                resource_id=str(booking_id),
            ).count() == 1

    def test_before_grace_is_rejected_without_mutation(self, app):
        rider = _create_user(app, "cfne")
        driver_user, driver_id = _create_driver(app, "cfne")
        booking_id, _ = _create_booking(
            app, rider, status=BookingStatus.PICKUP_ARRIVED,
            driver_id=driver_id,
            pickup_time=datetime.now(timezone.utc) - timedelta(minutes=5),
            created_at=datetime.now(timezone.utc) - timedelta(hours=2),
        )
        with app.app_context():
            with pytest.raises(ValidationError):
                get_booking_service().mark_no_show(booking_id, driver_user)
            booking = db.session.get(Booking, booking_id)
            assert booking.status == BookingStatus.PICKUP_ARRIVED
            assert booking.cancellation_fee == Decimal("0.00")
            assert "no_show" not in (booking.booking_metadata or {})

    def test_wrong_driver_forbidden(self, app):
        rider = _create_user(app, "cfnw")
        _, driver_id = _create_driver(app, "cfnw1")
        other_user, _ = _create_driver(app, "cfnw2")
        booking_id, _ = _create_booking(
            app, rider, status=BookingStatus.PICKUP_ARRIVED,
            driver_id=driver_id,
            pickup_time=datetime.now(timezone.utc) - timedelta(minutes=20),
            created_at=datetime.now(timezone.utc) - timedelta(hours=2),
        )
        with app.app_context():
            with pytest.raises(PermissionError):
                get_booking_service().mark_no_show(booking_id, other_user)

    def test_instant_no_show_is_rejected(self, app):
        rider = _create_user(app, "cfni")
        driver_user, driver_id = _create_driver(app, "cfni")
        booking_id, _ = _create_booking(
            app, rider, status=BookingStatus.PICKUP_ARRIVED,
            mode="instant", driver_id=driver_id,
            pickup_time=datetime.now(timezone.utc) - timedelta(minutes=20),
            created_at=datetime.now(timezone.utc) - timedelta(hours=2),
        )
        with app.app_context():
            with pytest.raises(ValidationError):
                get_booking_service().mark_no_show(booking_id, driver_user)
            booking = db.session.get(Booking, booking_id)
            assert booking.status == BookingStatus.PICKUP_ARRIVED
            assert "no_show" not in (booking.booking_metadata or {})

    def test_driver_api_reference_keyed_returns_fee(self, app, client):
        rider = _create_user(app, "cfapi")
        driver_user, driver_id = _create_driver(app, "cfapi")
        booking_id, ref = _create_booking(
            app, rider, status=BookingStatus.PICKUP_ARRIVED,
            driver_id=driver_id,
            pickup_time=datetime.now(timezone.utc) - timedelta(minutes=20),
            created_at=datetime.now(timezone.utc) - timedelta(hours=2),
        )
        _login_client(client, driver_user)
        response = client.post(
            f"/api/transport/drivers/me/trips/{ref}/status",
            json={"action": "no_show"},
        )
        assert response.status_code == 200, response.get_json()
        body = response.get_json()
        assert body["success"] is True
        assert body["data"]["cancellation_fee"] == 40.0
        assert _booking_field(app, booking_id, "status") == (
            BookingStatus.NO_SHOW)


class TestPresentationHooks:

    def test_driver_row_gates_no_show_on_mode_and_grace(self):
        real_now = datetime.now(timezone.utc)
        before = _transient_booking(base=real_now,
                                    pickup_delta=timedelta(minutes=-5))
        before.status = BookingStatus.PICKUP_ARRIVED
        before.assigned_driver_id = 1
        after = _transient_booking(base=real_now,
                                   pickup_delta=timedelta(minutes=-20))
        after.status = BookingStatus.PICKUP_ARRIVED
        after.assigned_driver_id = 1
        instant = _transient_booking(mode="instant", base=real_now,
                                     pickup_delta=timedelta(minutes=-20))
        instant.status = BookingStatus.PICKUP_ARRIVED
        instant.assigned_driver_id = 1

        assert BookingService._driver_trip_row(before)[
            "can_mark_no_show"] is False
        after_row = BookingService._driver_trip_row(after)
        assert after_row["can_mark_no_show"] is True
        assert after_row["booking_mode"] == "scheduled"
        assert BookingService._driver_trip_row(instant)[
            "can_mark_no_show"] is False
        assert BookingService._driver_trip_row(instant)[
            "booking_mode"] == "instant"

    def test_driver_dashboard_exposes_no_show_action(self):
        template = Path(
            "templates/transport/driver/driver_dashboard.html"
        ).read_text(encoding="utf-8")
        assert 'data-action="no_show"' in template
        assert "Rider no-show" in template
        assert "active_trip.can_mark_no_show" in template

    def test_rider_page_uses_server_preview_and_currency(self, app, client):
        rider = _create_user(app, "cfui")
        _, driver_id = _create_driver(app, "cfui")
        _, ref = _create_booking(
            app, rider, status=BookingStatus.PICKUP_ARRIVED,
            driver_id=driver_id,
            pickup_time=datetime.now(timezone.utc) + timedelta(minutes=10),
        )
        _login_client(client, rider)
        response = client.get(f"/transport/rides/{ref}")
        assert response.status_code == 200
        html = response.get_data(as_text=True)
        assert 'var bookingMode = "scheduled";' in html
        assert '"fee": 40.0' in html
        assert '"currency": "USD"' in html
        assert "recorded as uncollected" in html
