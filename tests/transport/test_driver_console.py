"""Driver PWA console (Phase 1) behavioral proof.

Covers the console route guards/rendering and every driver action
through the EXISTING endpoints (no endpoint modified here):
  POST /api/transport/drivers/<id>/status
  POST /api/transport/drivers/<id>/location
  GET  /api/transport/drivers/me/offers (+ accept/decline)
  POST /api/transport/drivers/me/trips/<id>/status
"""
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.extensions import db

pytestmark = pytest.mark.usefixtures("db_session")


def _seed_driver(app, *, compliance=None, kyc=False):
    from app.identity.individuals.individual_verification import (
        IndividualVerification,
    )
    from app.identity.models.user import User
    from app.transport.models import (
        ComplianceStatus,
        DriverProfile,
        VerificationTier,
    )

    if compliance is None:
        compliance = ComplianceStatus.APPROVED
    with app.app_context():
        uid = uuid.uuid4().hex[:8]
        user = User(
            public_id=str(uuid.uuid4()),
            username=f"dc_{uid}",
            email=f"dc_{uid}@test.example.com",
        )
        user.is_active = True
        user.is_verified = True
        user.set_password("TestPassword123!")
        db.session.add(user)
        db.session.flush()

        profile = DriverProfile(
            user_id=user.id,
            driver_code=f"DC-{uid[:6].upper()}",
            verification_tier=VerificationTier.PENDING,
            compliance_status=compliance,
            is_active=True,
            is_online=False,
            is_available=False,
            max_passenger_capacity=4,
            vehicle_classes=["comfort"],
            service_types=["on_demand"],
        )
        db.session.add(profile)

        if kyc:
            user.phone_verified = True
            user.phone_verified_at = datetime.now(timezone.utc)
            if not user.phone:
                user.phone = f"+2567{uuid.uuid4().hex[:7]}"
            db.session.add(
                IndividualVerification(
                    user_id=user.id,
                    status="verified",
                    scope={
                        "identity": True,
                        "address": True,
                        "national_id": True,
                        "biometric": True,
                    },
                )
            )

        db.session.commit()
        ctx_id = getattr(profile, "public_id", None) or profile.driver_code
        return SimpleNamespace(
            id=user.id,
            public_id=user.public_id,
            driver_profile_id=profile.id,
            driver_code=profile.driver_code,
            ctx_id=ctx_id,
        )


def _enter_driver_context(client, user):
    with client.session_transaction() as sess:
        sess["_user_id"] = user.public_id
        sess["_fresh"] = True
        sess["active_context_type"] = "driver"
        sess["active_context_id"] = user.ctx_id
        sess["active_role"] = "driver"


def _login(client, user):
    with client.session_transaction() as sess:
        sess["_user_id"] = user.public_id
        sess["_fresh"] = True


def _make_ready(app, driver):
    """Licence + assigned active vehicle (go-live gates)."""
    from app.transport.models import DriverProfile, Vehicle, VehicleClass
    from app.transport.models import DriverVehicleHistory

    with app.app_context():
        profile = db.session.get(DriverProfile, driver.driver_profile_id)
        profile.license_number = f"DL-{uuid.uuid4().hex[:8].upper()}"
        profile.license_expiry = datetime.now(timezone.utc) + timedelta(days=365)
        profile.license_verified = True
        vehicle = Vehicle(
            owner_type="driver",
            owner_id=profile.id,
            license_plate=f"UGDC{uuid.uuid4().hex[:4].upper()}",
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
        db.session.add(
            DriverVehicleHistory(
                driver_id=profile.id,
                vehicle_id=vehicle.id,
                started_at=datetime.now(timezone.utc),
                ended_at=None,
                assignment_reason="shift_start",
            )
        )
        db.session.commit()
        return vehicle.id


def _make_booking(app, rider_id, status="confirmed", ref=None):
    from app.transport.models import (
        Booking,
        BookingStatus,
        ProviderType,
        ServiceType,
    )

    with app.app_context():
        booking = Booking(
            user_id=rider_id,
            booking_reference=ref or f"DCC{uuid.uuid4().hex[:8].upper()}",
            provider_type=ProviderType.INDIVIDUAL_DRIVER,
            service_type=ServiceType.ON_DEMAND,
            pickup_location={"latitude": 0.3136, "longitude": 32.5811},
            dropoff_location={"latitude": 0.3476, "longitude": 32.5825},
            pickup_time=datetime.now(timezone.utc) + timedelta(hours=2),
            passenger_count=1,
            base_price=100.0,
            currency="USD",
            status=status,
        )
        db.session.add(booking)
        db.session.commit()
        return booking.id, booking.booking_reference


def test_console_requires_login(app, anonymous_client):
    resp = anonymous_client.get("/transport/driver-console",
                                follow_redirects=False)
    assert resp.status_code == 302, resp.status_code


def test_console_redirects_to_driver_dashboard(app, client, db_session):
    driver = _seed_driver(app)
    _enter_driver_context(client, driver)

    resp = client.get("/transport/driver-console", follow_redirects=False)
    assert resp.status_code == 302, resp.status_code
    assert resp.headers.get("Location", "").endswith(
        "/transport/driver-dashboard")


def test_driver_dashboard_carries_console_location_feature(
        app, client, db_session):
    driver = _seed_driver(app)
    _enter_driver_context(client, driver)

    resp = client.get("/transport/driver-dashboard", follow_redirects=False)
    assert resp.status_code == 200, resp.status_code
    body = resp.data.decode("utf-8")
    assert driver.driver_code in body
    assert 'id="driverConsole"' in body
    assert "dcLocBadge" in body
    assert "data-ping-interval" in body
    assert body.count("dcLocBadge") == 1
    assert body.index('data-panel="home"') < body.index("dcLocBadge") < body.index(
        'data-panel="status"')


def test_console_redirects_without_profile(app, client, db_session,
                                           monkeypatch):
    from app.transport.services import provider_service

    driver = _seed_driver(app)
    _enter_driver_context(client, driver)
    monkeypatch.setattr(
        provider_service.ProviderService,
        "get_driver_profile",
        lambda self, user_id: None,
    )

    resp = client.get("/transport/driver-console", follow_redirects=False)
    assert resp.status_code == 302, resp.status_code
    assert resp.headers.get("Location", "").endswith(
        "/transport/become-driver")


def test_status_toggle_flips_online(app, client, db_session):
    from app.transport.models import DriverProfile

    driver = _seed_driver(app, kyc=True)
    _make_ready(app, driver)
    _login(client, driver)

    resp = client.post(
        f"/api/transport/drivers/{driver.driver_profile_id}/status",
        json={"is_online": True, "is_available": True},
    )
    assert resp.status_code == 200, resp.get_data(as_text=True)
    db_session.expire_all()
    profile = db_session.get(DriverProfile, driver.driver_profile_id)
    assert profile.is_online is True
    assert profile.is_available is True

    resp = client.post(
        f"/api/transport/drivers/{driver.driver_profile_id}/status",
        json={"is_online": False, "is_available": False},
    )
    assert resp.status_code == 200, resp.get_data(as_text=True)
    db_session.expire_all()
    profile = db_session.get(DriverProfile, driver.driver_profile_id)
    assert profile.is_online is False


def test_location_publish_updates_timestamp(app, client, db_session):
    from app.transport.models import DriverProfile

    driver = _seed_driver(app)
    _login(client, driver)

    resp = client.post(
        f"/api/transport/drivers/{driver.driver_profile_id}/location",
        json={"latitude": 0.3136, "longitude": 32.5811, "accuracy": 5.0},
    )
    assert resp.status_code == 200, resp.get_data(as_text=True)
    db_session.expire_all()
    profile = db_session.get(DriverProfile, driver.driver_profile_id)
    assert profile.location_updated_at is not None
    assert profile.last_location["latitude"] == 0.3136


def test_offers_empty_for_new_driver(app, client, db_session):
    driver = _seed_driver(app)
    _login(client, driver)

    resp = client.get("/api/transport/drivers/me/offers")
    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert resp.get_json()["data"]["offers"] == []


def test_accept_offer_assigns_booking(app, client, db_session, monkeypatch):
    from app.transport.models import Booking, BookingStatus, DriverProfile

    from tests.test_transport_concurrent_claim import _FakeRedis

    monkeypatch.setattr(
        "app.transport.services.offer_service.redis_client", _FakeRedis())
    driver = _seed_driver(app, kyc=True)
    vehicle_id = _make_ready(app, driver)
    _login(client, driver)

    rider = _seed_driver(app)
    booking_id, ref = _make_booking(app, rider.id, status="confirmed")

    from app.transport.services.offer_service import OfferService

    with app.app_context():
        profile = db.session.get(DriverProfile, driver.driver_profile_id)
        profile.is_online = True
        profile.is_available = True
        db.session.commit()
        OfferService.create_offer(ref, profile.id, vehicle_id)

    resp = client.post(
        f"/api/transport/drivers/me/offers/{ref}/accept")
    assert resp.status_code == 200, resp.get_data(as_text=True)
    db_session.expire_all()
    booking = db_session.get(Booking, booking_id)
    assert booking.status == BookingStatus.ASSIGNED.value
    assert booking.assigned_driver_id == driver.driver_profile_id
    assert booking.assigned_vehicle_id == vehicle_id


def test_trip_advance_full_cycle(app, client, db_session):
    from app.transport.models import Booking, BookingStatus, DriverProfile

    driver = _seed_driver(app)
    vehicle_id = _make_ready(app, driver)
    _login(client, driver)

    rider = _seed_driver(app)
    with app.app_context():
        profile = db.session.get(DriverProfile, driver.driver_profile_id)
        profile.is_online = True
        profile.is_available = True
        db.session.commit()
    booking_id, _ref = _make_booking(app, rider.id, status="assigned")
    with app.app_context():
        booking = db.session.get(Booking, booking_id)
        booking.assigned_driver_id = driver.driver_profile_id
        booking.assigned_vehicle_id = vehicle_id
        db.session.commit()

    expected = {
        "en_route": BookingStatus.DRIVER_EN_ROUTE.value,
        "arrive": BookingStatus.PICKUP_ARRIVED.value,
        "start": BookingStatus.IN_PROGRESS.value,
        "complete": BookingStatus.COMPLETED.value,
    }
    for action, want in expected.items():
        resp = client.post(
            f"/api/transport/drivers/me/trips/{booking_id}/status",
            json={"action": action},
        )
        assert resp.status_code == 200, (action, resp.get_data(as_text=True))
        db_session.expire_all()
        assert db_session.get(Booking, booking_id).status == want, action


def test_cli_ping_publishes_location(app, db_session):
    from app.transport.models import DriverProfile

    driver = _seed_driver(app)
    runner = app.test_cli_runner()
    result = runner.invoke(args=[
        "driver", "ping", str(driver.driver_profile_id),
        "0.3136", "32.5811",
    ])
    assert result.exit_code == 0, result.output
    assert "location_updated_at" in result.output
    db_session.expire_all()
    profile = db_session.get(DriverProfile, driver.driver_profile_id)
    assert profile.location_updated_at is not None
