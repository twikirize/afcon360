"""Driver pre-start cancellation (driver_cancel) behavioral proof.

The driver may cancel an accepted trip only before it starts. The ride
closes as NO_MATCH (rider is prompted to search again), never as a paid
cancellation: no fee, no wallet/earnings write, no cancellation_* fields.
Driver accountability is metadata + the canonical dispatch_release audit
row. A converted request-first request keeps its ledger; the linked Booking
is the trip authority and the rider's retry uses the legacy bridge.
"""
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.audit.models import AuditLog
from app.extensions import db
from app.identity.models.user import User
from app.transport.models import (
    Booking,
    BookingStatus,
    ComplianceStatus,
    DriverProfile,
    DriverVehicleHistory,
    RideRequest,
    ServiceType,
    Vehicle,
    VehicleClass,
)
from app.transport.services.booking_service import get_booking_service
from app.utils.enums import Currency
from app.utils.exceptions import PermissionError, ValidationError

pytestmark = pytest.mark.usefixtures("db_session")

CANCELLABLE = (
    BookingStatus.ASSIGNED,
    BookingStatus.DRIVER_EN_ROUTE,
    BookingStatus.PICKUP_ARRIVED,
)


def _create_user(app, label="dcx"):
    with app.app_context():
        uid = uuid.uuid4().hex[:8]
        user = User(
            public_id=str(uuid.uuid4()),
            username=f"{label}_{uid}",
            email=f"{label}_{uid}@test.example.com",
            is_verified=True,
            is_active=True,
        )
        user.set_password("TestPass123!")
        db.session.add(user)
        db.session.commit()
        return SimpleNamespace(id=user.id, public_id=user.public_id)


def _create_driver(app, label="dcxd"):
    user = _create_user(app, label)
    with app.app_context():
        driver = DriverProfile(
            user_id=user.id,
            driver_code=f"DX-{label}-{uuid.uuid4().hex[:6].upper()}",
            verification_tier="platform_verified",
            compliance_status=ComplianceStatus.APPROVED,
            is_active=True,
            is_online=True,
            is_available=True,
            max_passenger_capacity=4,
            vehicle_classes=["comfort"],
            service_types=["on_demand"],
        )
        db.session.add(driver)
        db.session.commit()
        return SimpleNamespace(
            id=user.id,
            public_id=user.public_id,
            driver_profile_id=driver.id,
            driver_code=driver.driver_code,
        )


def _make_ready(app, driver):
    with app.app_context():
        vehicle = Vehicle(
            owner_type="driver",
            owner_id=driver.driver_profile_id,
            license_plate=f"UGDX{uuid.uuid4().hex[:4].upper()}",
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
        db.session.flush()
        db.session.add(DriverVehicleHistory(
            driver_id=driver.driver_profile_id,
            vehicle_id=vehicle.id,
            started_at=datetime.now(timezone.utc),
            ended_at=None,
            assignment_reason="shift_start",
        ))
        db.session.commit()
        return vehicle.id


def _create_booking(app, rider_id, *, status=BookingStatus.ASSIGNED,
                    driver=None, vehicle_id=None, ref=None,
                    ride_request_id=None, metadata=None,
                    no_match_reason=None):
    with app.app_context():
        now = datetime.now(timezone.utc)
        booking = Booking(
            booking_reference=ref or f"DX-{uuid.uuid4().hex[:8].upper()}",
            user_id=rider_id,
            provider_type="individual_driver",
            service_type=ServiceType.ON_DEMAND,
            pickup_location={"latitude": 0.3136, "longitude": 32.5811},
            dropoff_location={"latitude": 0.3476, "longitude": 32.5825},
            pickup_time=now + timedelta(hours=2),
            pickup_mode="instant",
            request_received_at=now,
            passenger_count=1,
            base_price=Decimal("10.00"),
            subtotal=Decimal("10.00"),
            total_amount=Decimal("10.00"),
            final_price=Decimal("10.00"),
            currency=Currency.USD,
            status=status,
            no_match_reason=no_match_reason,
            assigned_driver_id=(
                driver.driver_profile_id if driver is not None else None
            ),
            assigned_vehicle_id=vehicle_id,
            driver_assigned_at=now if driver is not None else None,
            ride_request_id=ride_request_id,
            booking_metadata=metadata or {},
        )
        db.session.add(booking)
        db.session.commit()
        return booking.id, booking.booking_reference


def _create_converted_request(app, rider_id):
    with app.app_context():
        ref = str(uuid.uuid4())
        request = RideRequest(
            public_id=ref,
            user_id=rider_id,
            idempotency_key=f"idem-{uuid.uuid4().hex}",
            pickup_location={"latitude": 0.3136, "longitude": 32.5811},
            dropoff_location={"latitude": 0.3476, "longitude": 32.5825},
            requested_pickup_time=(
                datetime.now(timezone.utc) + timedelta(hours=1)
            ),
            service_type=ServiceType.ON_DEMAND,
            vehicle_class="comfort",
            passenger_count=1,
            fare_estimate_amount=Decimal("10.00"),
            currency_code="USD",
            payment_method="cash",
            status="converted",
            converted_at=datetime.now(timezone.utc),
            request_metadata={},
        )
        db.session.add(request)
        db.session.commit()
        return request.id, request.public_id


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


def _patch_redis(monkeypatch):
    from tests.test_transport_concurrent_claim import _FakeRedis
    fake = _FakeRedis()
    monkeypatch.setattr(
        "app.transport.services.offer_service.redis_client", fake)
    return fake


class TestDriverCancelService:

    @pytest.mark.parametrize("stage", CANCELLABLE)
    def test_cancel_from_each_prestart_stage(self, app, stage):
        rider = _create_user(app, "dcs")
        driver = _create_driver(app, "dcs")
        vehicle_id = _make_ready(app, driver)
        booking_id, ref = _create_booking(
            app, rider.id, status=stage, driver=driver,
            vehicle_id=vehicle_id,
        )

        with app.app_context():
            result = get_booking_service().driver_cancel(
                booking_id, driver.id, reason="rider_not_here")

            assert result["success"] is True
            assert result["data"]["status"] == BookingStatus.NO_MATCH.value
            assert result["data"]["no_match_reason"] == "all_rejected"
            assert result["data"]["cancelled_stage"] == stage.value
            assert result["data"]["idempotent"] is False

            booking = db.session.get(Booking, booking_id)
            assert booking.status == BookingStatus.NO_MATCH
            assert booking.no_match_reason == "all_rejected"
            assert booking.assigned_driver_id is None
            assert booking.assigned_vehicle_id is None
            assert booking.driver_assigned_at is None
            assert booking.driver_en_route_at is None
            assert booking.driver_arrived_at is None
            # NOT a paid cancellation.
            assert booking.cancelled_at is None
            assert booking.cancelled_stage is None
            assert booking.cancellation_initiated_by is None
            assert booking.cancellation_fee in (None, Decimal("0.00"))

            metadata = booking.booking_metadata
            assert metadata["no_match_cause"] == "driver_cancelled"
            record = metadata["driver_cancellations"][-1]
            assert record["driver_code"] == driver.driver_code
            assert record["stage"] == stage.value
            assert record["reason"] == "rider_not_here"
            assert record["booking_reference"] == ref
            assert booking.audit_log[-1]["action"] == (
                "driver_cancelled_before_start")

            vehicle = db.session.get(Vehicle, vehicle_id)
            assert vehicle.is_available is True

            assert AuditLog.query.filter_by(
                action="dispatch_release",
                resource_id=str(booking_id),
            ).count() == 1

    def test_in_progress_is_rejected_without_mutation(self, app):
        rider = _create_user(app, "dci")
        driver = _create_driver(app, "dci")
        vehicle_id = _make_ready(app, driver)
        booking_id, _ = _create_booking(
            app, rider.id, status=BookingStatus.IN_PROGRESS,
            driver=driver, vehicle_id=vehicle_id,
        )

        with app.app_context():
            with pytest.raises(ValidationError) as exc:
                get_booking_service().driver_cancel(booking_id, driver.id)
            assert "already started" in str(exc.value)

            booking = db.session.get(Booking, booking_id)
            assert booking.status == BookingStatus.IN_PROGRESS
            assert booking.assigned_driver_id == driver.driver_profile_id
            assert booking.assigned_vehicle_id == vehicle_id
            assert booking.no_match_reason is None

    def test_wrong_driver_is_forbidden(self, app):
        rider = _create_user(app, "dcw")
        driver = _create_driver(app, "dcw")
        other = _create_driver(app, "dcwo")
        vehicle_id = _make_ready(app, driver)
        booking_id, _ = _create_booking(
            app, rider.id, status=BookingStatus.ASSIGNED,
            driver=driver, vehicle_id=vehicle_id,
        )

        with app.app_context():
            with pytest.raises(PermissionError):
                get_booking_service().driver_cancel(
                    booking_id, other.id)
            booking = db.session.get(Booking, booking_id)
            assert booking.status == BookingStatus.ASSIGNED
            assert booking.assigned_driver_id == driver.driver_profile_id

    def test_cancel_is_idempotent(self, app):
        rider = _create_user(app, "dcid")
        driver = _create_driver(app, "dcid")
        vehicle_id = _make_ready(app, driver)
        booking_id, _ = _create_booking(
            app, rider.id, status=BookingStatus.DRIVER_EN_ROUTE,
            driver=driver, vehicle_id=vehicle_id,
        )

        with app.app_context():
            service = get_booking_service()
            first = service.driver_cancel(booking_id, driver.id)
            second = service.driver_cancel(booking_id, driver.id)

            assert first["data"]["idempotent"] is False
            assert second["data"]["idempotent"] is True
            assert second["data"]["cancelled_stage"] == (
                BookingStatus.DRIVER_EN_ROUTE.value)

            booking = db.session.get(Booking, booking_id)
            assert len(booking.booking_metadata[
                "driver_cancellations"]) == 1
            assert AuditLog.query.filter_by(
                action="dispatch_release",
                resource_id=str(booking_id),
            ).count() == 1

    def test_cancel_notifies_rider(self, app, monkeypatch):
        rider = _create_user(app, "dcn")
        driver = _create_driver(app, "dcn")
        vehicle_id = _make_ready(app, driver)
        booking_id, _ = _create_booking(
            app, rider.id, status=BookingStatus.PICKUP_ARRIVED,
            driver=driver, vehicle_id=vehicle_id,
        )

        calls = []

        def _record(*args, **kwargs):
            calls.append((args, kwargs))
            return {"success": True}

        monkeypatch.setattr(
            "app.transport.services.notification_service."
            "NotificationService.send_booking_notification",
            staticmethod(_record),
        )

        with app.app_context():
            get_booking_service().driver_cancel(booking_id, driver.id)

        assert len(calls) == 1
        args, _kwargs = calls[0]
        assert args[0] == booking_id
        assert args[1] == "driver_cancelled"

    def test_retry_after_driver_cancel_clears_cause(self, app):
        rider = _create_user(app, "dcr")
        driver = _create_driver(app, "dcr")
        vehicle_id = _make_ready(app, driver)
        booking_id, _ = _create_booking(
            app, rider.id, status=BookingStatus.ASSIGNED,
            driver=driver, vehicle_id=vehicle_id,
        )

        with app.app_context():
            service = get_booking_service()
            service.driver_cancel(booking_id, driver.id)
            service.retry_matching(booking_id, rider.id)

            booking = db.session.get(Booking, booking_id)
            assert booking.status == BookingStatus.CONFIRMED
            assert booking.no_match_reason is None
            assert "no_match_cause" not in booking.booking_metadata
            assert booking.booking_metadata.get("matching_started_at")
            # Driver-cancel history is retained for accountability.
            assert booking.booking_metadata[
                "driver_cancellations"][0]["stage"] == "assigned"


class TestDriverCancelApi:

    def test_reference_keyed_cancel_returns_no_match(self, app, client):
        rider = _create_user(app, "dca")
        driver = _create_driver(app, "dca")
        vehicle_id = _make_ready(app, driver)
        booking_id, ref = _create_booking(
            app, rider.id, status=BookingStatus.ASSIGNED,
            driver=driver, vehicle_id=vehicle_id,
        )
        _login_client(client, driver.id)

        response = client.post(
            f"/api/transport/drivers/me/trips/{ref}/status",
            json={"action": "cancel"},
        )
        assert response.status_code == 200, response.get_json()
        body = response.get_json()
        assert body["success"] is True
        assert body["data"]["status"] == BookingStatus.NO_MATCH.value
        assert body["data"]["cancelled_stage"] == "assigned"

        with app.app_context():
            booking = db.session.get(Booking, booking_id)
            assert booking.status == BookingStatus.NO_MATCH
            assert booking.assigned_driver_id is None

    def test_in_progress_cancel_returns_409(self, app, client):
        rider = _create_user(app, "dcai")
        driver = _create_driver(app, "dcai")
        vehicle_id = _make_ready(app, driver)
        booking_id, ref = _create_booking(
            app, rider.id, status=BookingStatus.IN_PROGRESS,
            driver=driver, vehicle_id=vehicle_id,
        )
        _login_client(client, driver.id)

        response = client.post(
            f"/api/transport/drivers/me/trips/{ref}/status",
            json={"action": "cancel"},
        )
        assert response.status_code == 409, response.get_json()
        with app.app_context():
            assert db.session.get(Booking, booking_id).status == (
                BookingStatus.IN_PROGRESS)


class TestDriverCancelRetryBridge:

    def test_converted_request_accepts_legacy_offer_after_retry(
            self, app, client, monkeypatch):
        from app.transport.services.offer_service import OfferService

        rider = _create_user(app, "dcb")
        driver = _create_driver(app, "dcb")
        vehicle_id = _make_ready(app, driver)
        request_id, ref = _create_converted_request(app, rider.id)
        booking_id, _ = _create_booking(
            app, rider.id, status=BookingStatus.CONFIRMED,
            ref=ref, ride_request_id=request_id,
        )
        _patch_redis(monkeypatch)
        with app.app_context():
            assert OfferService.create_offer(ref, driver.driver_profile_id,
                                             vehicle_id)

        _login_client(client, driver.id)
        response = client.post(
            f"/api/transport/drivers/me/offers/{ref}/accept", json={})
        assert response.status_code == 200, response.get_json()
        body = response.get_json()
        assert body["success"] is True

        with app.app_context():
            booking = db.session.get(Booking, booking_id)
            assert booking.status == BookingStatus.ASSIGNED
            assert booking.assigned_driver_id == driver.driver_profile_id
            request = db.session.get(RideRequest, request_id)
            assert request.status == "converted"

    def test_converted_request_without_claimable_booking_is_409(
            self, app, client):
        rider = _create_user(app, "dcb2")
        driver = _create_driver(app, "dcb2")
        request_id, ref = _create_converted_request(app, rider.id)
        _create_booking(
            app, rider.id, status=BookingStatus.NO_MATCH,
            ref=ref, ride_request_id=request_id,
            no_match_reason="all_rejected",
        )
        _login_client(client, driver.id)

        response = client.post(
            f"/api/transport/drivers/me/offers/{ref}/accept", json={})
        assert response.status_code == 409
        assert response.get_json()["code"] == "already_accepted"


class TestDriverCancelPresentation:

    def test_active_trip_can_cancel_only_prestart(self):
        from app.transport.routes import _driver_active_trip

        for stage in CANCELLABLE:
            trip = _driver_active_trip([{"status": stage.value}])
            assert trip["can_cancel"] is True

        assert _driver_active_trip(
            [{"status": BookingStatus.IN_PROGRESS.value}])[
                "can_cancel"] is False
        assert _driver_active_trip(
            [{"status": BookingStatus.DISPUTED.value}])[
                "can_cancel"] is False

    def test_driver_dashboard_exposes_cancel_action(self):
        template = Path(
            "templates/transport/driver/driver_dashboard.html"
        ).read_text(encoding="utf-8")
        assert 'data-action="cancel"' in template
        assert "Cancel trip" in template
        assert "active_trip.can_cancel" in template
        assert "No fee is charged" in template

    def test_rider_page_renders_driver_cancelled_copy(self, app, client):
        rider = _create_user(app, "dcui")
        driver = _create_driver(app, "dcui")
        vehicle_id = _make_ready(app, driver)
        booking_id, ref = _create_booking(
            app, rider.id, status=BookingStatus.ASSIGNED,
            driver=driver, vehicle_id=vehicle_id,
        )
        with app.app_context():
            get_booking_service().driver_cancel(booking_id, driver.id)

        _login_client(client, rider.id)
        response = client.get(f"/transport/rides/{ref}")
        assert response.status_code == 200, response.status_code
        body = response.data.decode("utf-8")
        assert "Your driver cancelled" in body
        assert "Search again to find another driver." in body
        assert "rejected" not in body.lower()

    def test_rider_sync_reloads_on_live_no_match(self):
        source = Path(
            "static/js/modules/transport/rider_status_sync.js"
        ).read_text(encoding="utf-8")
        assert "data-initial-status" in source
        assert "status === 'no_match'" in source
        assert "window.location.reload()" in source
