"""
Driver Workspace Phase C2 section tests.

Contract under test
-------------------
The Driver Workspace home (``transport.driver_dashboard``) presents the
operational sections (Active Trip, Ride Offers, Scheduled Work, Recent Trips,
Vehicles, Vehicle Switching, Earnings, Notifications, Safety, Compliance,
Performance, Support, Settings, Opportunities) by orchestrating EXISTING
transport services and REST endpoints. Phase C2 adds no models, no schema and
no business rules — it is presentation-only consolidation.

These tests verify:

* every workspace section renders from the orchestrating view context;
* live ride offers render with accept/decline actions (transient store);
* the assigned active trip renders with the correct next-action button;
* scheduled work assigned to the driver renders;
* vehicle switching (self-service) renders the owned-but-unassigned vehicles and
  that the canonical ``driver_me_vehicle_switch`` endpoint enforces ownership,
  active-state and idempotency;
* the notifications preview renders the user's transport-scoped notifications;
* open safety incidents render.

Fixtures/helpers mirror ``tests/test_driver_workspace_consolidation.py`` —
local mirrors are re-implemented here to avoid cross-file import coupling.
"""
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.extensions import db
from app.notifications.models import (
    Notification,
    NotificationChannel,
    NotificationModule,
    NotificationType,
)
from app.transport.models import (
    Booking,
    BookingStatus,
    ComplianceStatus,
    Currency,
    DriverProfile,
    DriverVehicleHistory,
    IncidentSeverity,
    PaymentStatus,
    ProviderType,
    ScheduledRoute,
    ServiceType,
    TransportIncident,
    Vehicle,
    VehicleClass,
    VerificationTier,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fresh_get(client, url, **kwargs):
    """GET that clears the Flask-Caching user cache first (avoids stale loader)."""
    from app.extensions import cache

    try:
        cache.clear()
    except Exception:
        pass
    return client.get(url, **kwargs)


def _seed_driver(app, *, compliance=ComplianceStatus.PENDING_REVIEW, kyc=False):
    """Create a real User + DriverProfile and return a lightweight ref."""
    from app.identity.individuals.individual_verification import (
        IndividualVerification,
    )
    from app.identity.models.user import User

    with app.app_context():
        uid = uuid.uuid4().hex[:8]
        user = User(
            public_id=str(uuid.uuid4()),
            username=f"sec_{uid}",
            email=f"sec_{uid}@test.example.com",
        )
        user.is_active = True
        user.is_verified = True
        user.set_password("TestPassword123!")
        db.session.add(user)
        db.session.flush()

        profile = DriverProfile(
            user_id=user.id,
            driver_code=f"SEC-{uid[:6].upper()}",
            verification_tier=VerificationTier.PENDING,
            compliance_status=compliance,
            is_active=True,
            is_online=False,
            is_available=False,
            max_passenger_capacity=4,
            vehicle_classes=["comfort"],
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
            ctx_id=ctx_id,
        )


def _enter_driver_context(client, user):
    with client.session_transaction() as sess:
        sess["_user_id"] = user.public_id
        sess["_fresh"] = True
        sess["active_context_type"] = "driver"
        sess["active_context_id"] = user.ctx_id
        sess["active_role"] = "driver"


def _add_owned_vehicle(app, driver_profile_id, plate, *, status="active"):
    with app.app_context():
        vehicle = Vehicle(
            owner_type="driver",
            owner_id=driver_profile_id,
            license_plate=plate,
            make="Toyota",
            model="Corolla",
            year=2021,
            vehicle_type="sedan",
            vehicle_class=VehicleClass.COMFORT,
            passenger_capacity=4,
            status=status,
        )
        db.session.add(vehicle)
        db.session.commit()
        return vehicle.id


def _assign_vehicle(app, driver_profile_id, vehicle_id):
    with app.app_context():
        db.session.add(
            DriverVehicleHistory(
                driver_id=driver_profile_id,
                vehicle_id=vehicle_id,
                started_at=datetime.now(timezone.utc),
                ended_at=None,
                assignment_reason="shift_start",
            )
        )
        db.session.commit()


def _make_go_live_ready(app, driver):
    """APPROVED + KYC + valid licence + one assigned active owned vehicle.

    Matches the ``can_go_live`` gates (go_live_service.py): an on-demand
    driver needs a licence number + un-expired expiry AND a current_vehicle
    (a DriverVehicleHistory row with ended_at=None). license_verified is set
    as belt-and-suspenders; can_go_live itself keys off license_number/expiry.
    """
    with app.app_context():
        profile = DriverProfile.query.filter_by(
            id=driver.driver_profile_id, is_deleted=False
        ).first()
        profile.license_number = f"DL-{uuid.uuid4().hex[:8].upper()}"
        profile.license_expiry = datetime.now(timezone.utc) + timedelta(days=365 * 5)
        profile.license_verified = True
        db.session.commit()
    v_id = _add_owned_vehicle(app, driver.driver_profile_id, "GL-001")
    _assign_vehicle(app, driver.driver_profile_id, v_id)
    return v_id


def _make_booking(app, driver_user_id, driver_profile_id, vehicle_id, *,
                  status=BookingStatus.ASSIGNED, ref=None):
    """Create a transport booking linked to the driver profile."""
    with app.app_context():
        booking = Booking(
            user_id=driver_user_id,
            provider_type=ProviderType.INDIVIDUAL_DRIVER,
            service_type=ServiceType.ON_DEMAND,
            pickup_location={"latitude": 0.3136, "longitude": 32.5811},
            dropoff_location={"latitude": 0.3476, "longitude": 32.5825},
            pickup_address="Kampala Road, Kampala",
            dropoff_address="Kololo, Kampala",
            pickup_time=datetime.now(timezone.utc) + timedelta(hours=2),
            passenger_count=2,
            base_price=50000,
            subtotal=50000,
            total_amount=50000,
            final_price=50000,
            currency=Currency.UGX,
            payment_status=PaymentStatus.PENDING,
            status=status,
            booking_reference=ref or f"TB{uuid.uuid4().hex[:10].upper()}",
            assigned_driver_id=driver_profile_id,
            assigned_vehicle_id=vehicle_id,
        )
        db.session.add(booking)
        db.session.commit()
        return SimpleNamespace(
            id=booking.id,
            booking_reference=booking.booking_reference,
        )


def _make_route(app, driver_profile_id, label):
    """Create an active scheduled route assigned to the driver."""
    uid = uuid.uuid4().hex[:6]
    with app.app_context():
        route = ScheduledRoute(
            provider_type="system",
            provider_id=1,
            name=f"{label}_{uid}",
            route_type="shuttle",
            route_code=f"RT{uid[:4].upper()}",
            schedule_pattern={"frequency": "manual"},
            timezone="UTC",
            stops=[
                {"name": "Start", "latitude": 0.3476, "longitude": 32.5825},
                {"name": "End", "latitude": 0.3130, "longitude": 32.5812},
            ],
            vehicle_capacity=4,
            booked_seats=1,
            available_seats=3,
            price_per_seat=20000,
            is_free=False,
            duration_minutes=45,
            primary_zone="Kampala",
            next_departure=datetime.now(timezone.utc) + timedelta(hours=5),
            current_driver_id=driver_profile_id,
            is_active=True,
            is_cancelled=False,
        )
        db.session.add(route)
        db.session.commit()
        return route.id


def _make_incident(app, driver_profile_id, title):
    with app.app_context():
        incident = TransportIncident(
            incident_reference=f"INC-{uuid.uuid4().hex[:8].upper()}",
            incident_type="vehicle",
            incident_category="vehicle",
            severity=IncidentSeverity.HIGH,
            reported_by="driver",
            title=title,
            description="Test incident description.",
            occurred_at=datetime.now(timezone.utc),
            driver_id=driver_profile_id,
            status="reported",
            priority="high",
        )
        db.session.add(incident)
        db.session.commit()
        return incident.id


def _make_notification(app, user_id, subject, body):
    with app.app_context():
        n = Notification(
            user_id=user_id,
            module=NotificationModule.TRANSPORT,
            type=NotificationType.BOOKING_CONFIRMED,
            channel=NotificationChannel.IN_APP,
            subject=subject,
            body=body,
            link="/transport/driver-dashboard",
        )
        db.session.add(n)
        db.session.commit()
        return n.id


# ===========================================================================
# Section rendering tests
# ===========================================================================

class TestWorkspaceSectionsRender:
    """The full workspace section set renders on the driver home."""

    def test_all_workspace_section_headings_render(self, app, client):
        driver = _seed_driver(app, compliance=ComplianceStatus.PENDING_REVIEW)
        _enter_driver_context(client, driver)

        body = _fresh_get(client, "/transport/driver-dashboard").data.decode("utf-8")

        for heading in [
            "Active Trip",
            "Upcoming Assignments",
            "Ride Offers",
            "Scheduled Work",
            "Recent Trips",
            "Vehicles",
            "Vehicle Switching",
            "Earnings",
            "Notifications",
            "Safety",
            "Compliance",
            "Opportunities",
            "Support",
            "Settings",
        ]:
            assert heading in body, f"Missing workspace section: {heading!r}"

    def test_upcoming_section_present(self, app, client):
        """Upcoming Assignments section is part of the workspace contract."""
        driver = _seed_driver(app, compliance=ComplianceStatus.APPROVED)
        _enter_driver_context(client, driver)

        body = _fresh_get(client, "/transport/driver-dashboard").data.decode("utf-8")

        assert "Upcoming Assignments" in body

    def test_performance_section_renders_metrics(self, app, client):
        driver = _seed_driver(app, compliance=ComplianceStatus.PENDING_REVIEW)
        _enter_driver_context(client, driver)

        body = _fresh_get(client, "/transport/driver-dashboard").data.decode("utf-8")

        assert "Performance" in body
        assert "Acceptance Rate" in body
        assert "Cancellation Rate" in body
        assert "Reliability Score" in body
        assert "Total Distance" in body


class TestActiveTripSection:
    """The assigned mid-flight booking surfaces in the ACTIVE TRIP card."""

    def test_assigned_booking_renders_action_button(self, app, client):
        """The ACTIVE TRIP card must render a lifecycle button so the driver
        can advance the trip from the dashboard (not just view it)."""
        driver = _seed_driver(app, compliance=ComplianceStatus.APPROVED)
        v_id = _add_owned_vehicle(app, driver.driver_profile_id, "ACT-999")
        _assign_vehicle(app, driver.driver_profile_id, v_id)
        booking = _make_booking(
            app, driver.id, driver.driver_profile_id, v_id,
            status=BookingStatus.ASSIGNED,
        )
        _enter_driver_context(client, driver)

        body = _fresh_get(client, "/transport/driver-dashboard").data.decode("utf-8")

        assert 'class="btn btn-primary btn-sm trip-action"' in body
        # Reference-keyed action contract (BACKLOG active-trip entry):
        # no internal booking id crosses into the page (AGENTS.md 12.1).
        assert f"/api/transport/drivers/me/trips/{booking.booking_reference}/status" in body
        assert f"/api/transport/drivers/me/trips/{booking.id}/status" not in body
        assert 'data-action="en_route"' in body

    def test_no_active_trip_shows_empty_state(self, app, client):
        driver = _seed_driver(app, compliance=ComplianceStatus.APPROVED)
        v_id = _add_owned_vehicle(app, driver.driver_profile_id, "ACT-101")
        _assign_vehicle(app, driver.driver_profile_id, v_id)
        _enter_driver_context(client, driver)

        body = _fresh_get(client, "/transport/driver-dashboard").data.decode("utf-8")

        # Shipped card title (workspace-consolidation rename, BACKLOG drift
        # note) + honest empty state for the Active Trip section.
        assert "Active trip" in body
        assert "No active trip" in body


class TestOffersSection:
    """Ride offers render from the transient offer store (monkeypatched)."""

    def test_offers_render_with_accept_decline(self, app, client, monkeypatch):
        from app.transport.services.offer_service import OfferService

        driver = _seed_driver(app, compliance=ComplianceStatus.APPROVED)
        v_id = _add_owned_vehicle(app, driver.driver_profile_id, "OFF-201")
        _assign_vehicle(app, driver.driver_profile_id, v_id)
        booking = _make_booking(
            app, driver.id, driver.driver_profile_id, v_id,
            status=BookingStatus.CONFIRMED, ref="TBOFF201",
        )

        def fake_list(driver_id):
            return [{
                "booking_reference": booking.booking_reference,
                "driver_id": driver_id,
                "vehicle_id": v_id,
                "status": "offered",
            }]

        monkeypatch.setattr(OfferService, "list_driver_offers", fake_list)
        _enter_driver_context(client, driver)

        body = _fresh_get(client, "/transport/driver-dashboard").data.decode("utf-8")

        assert "Ride Offers" in body
        assert booking.booking_reference in body
        assert "/api/transport/drivers/me/offers/TBOFF201/accept" in body
        assert "/api/transport/drivers/me/offers/TBOFF201/decline" in body

    def test_no_offers_shows_honest_empty_state(self, app, client, monkeypatch):
        from app.transport.services.offer_service import OfferService

        driver = _seed_driver(app, compliance=ComplianceStatus.APPROVED)
        monkeypatch.setattr(
            OfferService, "list_driver_offers", lambda driver_id: []
        )
        _enter_driver_context(client, driver)

        body = _fresh_get(client, "/transport/driver-dashboard").data.decode("utf-8")

        assert "Ride Offers" in body
        assert "No live ride offers right now" in body


class TestScheduledWorkSection:
    """Scheduled routes assigned to the driver render."""

    def test_scheduled_route_renders(self, app, client):
        driver = _seed_driver(app, compliance=ComplianceStatus.APPROVED)
        _make_route(app, driver.driver_profile_id, "AirportLink")
        _enter_driver_context(client, driver)

        body = _fresh_get(client, "/transport/driver-dashboard").data.decode("utf-8")

        assert "Scheduled Work" in body
        assert "AirportLink" in body

    def test_no_scheduled_work_empty_state(self, app, client):
        driver = _seed_driver(app, compliance=ComplianceStatus.APPROVED)
        _enter_driver_context(client, driver)

        body = _fresh_get(client, "/transport/driver-dashboard").data.decode("utf-8")

        assert "No scheduled routes assigned yet" in body


class TestRecentTripsSection:
    """Completed trips show under RECENT TRIPS for an approved driver."""

    def test_completed_trip_renders_as_recent(self, app, client):
        driver = _seed_driver(app, compliance=ComplianceStatus.APPROVED, kyc=True)
        v_id = _add_owned_vehicle(app, driver.driver_profile_id, "RCT-301")
        _assign_vehicle(app, driver.driver_profile_id, v_id)
        booking = _make_booking(
            app, driver.id, driver.driver_profile_id, v_id,
            status=BookingStatus.COMPLETED,
            ref="TBRECENT",
        )
        _enter_driver_context(client, driver)

        body = _fresh_get(client, "/transport/driver-dashboard").data.decode("utf-8")

        assert "Recent Trips" in body
        assert booking.booking_reference in body
        assert "Completed" in body


class TestVehicleSwitchingSection:
    """Owned-but-unassigned vehicles appear with a switch action."""

    def test_switchable_vehicle_renders(self, app, client):
        driver = _seed_driver(app, compliance=ComplianceStatus.APPROVED)
        v1 = _add_owned_vehicle(app, driver.driver_profile_id, "SW-401")
        v2 = _add_owned_vehicle(app, driver.driver_profile_id, "SW-402")
        _assign_vehicle(app, driver.driver_profile_id, v1)
        _enter_driver_context(client, driver)

        body = _fresh_get(client, "/transport/driver-dashboard").data.decode("utf-8")

        assert "Vehicle Switching" in body
        assert "SW-402" in body
        assert "vehicle-switch" in body
        assert f"/api/transport/drivers/{driver.driver_profile_id}/vehicles/switch" in body

    def test_no_switchable_vehicle_honest_copy(self, app, client):
        driver = _seed_driver(app, compliance=ComplianceStatus.APPROVED)
        _enter_driver_context(client, driver)

        body = _fresh_get(client, "/transport/driver-dashboard").data.decode("utf-8")

        assert "Vehicle Switching" in body
        assert "Register another vehicle to enable switching" in body


class TestNotificationsPreviewSection:
    """Transport-scoped notifications preview renders on the home."""

    def test_notification_preview_renders(self, app, client):
        driver = _seed_driver(app, compliance=ComplianceStatus.APPROVED)
        _make_notification(
            app, driver.id, "New trip assigned", "Pickup at Kampala Road"
        )
        _enter_driver_context(client, driver)

        body = _fresh_get(client, "/transport/driver-dashboard").data.decode("utf-8")

        assert "Notifications" in body
        assert "New trip assigned" in body
        assert "View all notifications" in body


class TestSafetySection:
    """Open incidents render inside the SAFETY card."""

    def test_open_incident_renders(self, app, client):
        driver = _seed_driver(app, compliance=ComplianceStatus.APPROVED)
        _make_incident(app, driver.driver_profile_id, "Flat tyre on approach")
        _enter_driver_context(client, driver)

        body = _fresh_get(client, "/transport/driver-dashboard").data.decode("utf-8")

        assert "Safety" in body
        assert "Open incidents" in body
        assert "Flat tyre on approach" in body

    def test_no_incidents_clean_message(self, app, client):
        driver = _seed_driver(app, compliance=ComplianceStatus.APPROVED)
        _enter_driver_context(client, driver)

        body = _fresh_get(client, "/transport/driver-dashboard").data.decode("utf-8")

        assert "None" in body


# ===========================================================================
# Vehicle switching API (canonical DriverVehicleSwitchResource)
# ===========================================================================

class TestVehicleSwitchApi:
    """Self-service vehicle switching enforces the participation contract."""

    def test_switch_success(self, app, client):
        driver = _seed_driver(app, compliance=ComplianceStatus.APPROVED)
        v1 = _add_owned_vehicle(app, driver.driver_profile_id, "API-501")
        v2 = _add_owned_vehicle(app, driver.driver_profile_id, "API-502")
        _assign_vehicle(app, driver.driver_profile_id, v1)
        _enter_driver_context(client, driver)

        resp = client.post(
            f"/api/transport/drivers/{driver.driver_profile_id}/vehicles/switch",
            json={"vehicle_id": v2, "reason": "shift_start"},
        )

        assert resp.status_code == 200
        body = resp.get_json()
        assert body["success"] is True
        assert body["data"]["unchanged"] is False
        assert body["data"]["assigned_vehicle"]["license_plate"] == "API-502"

        with app.app_context():
            profile = DriverProfile.query.filter_by(
                id=driver.driver_profile_id, is_deleted=False
            ).first()
            assert profile.current_vehicle is not None
            assert profile.current_vehicle.id == v2

    def test_switch_to_current_is_idempotent(self, app, client):
        driver = _seed_driver(app, compliance=ComplianceStatus.APPROVED)
        v1 = _add_owned_vehicle(app, driver.driver_profile_id, "API-503")
        _assign_vehicle(app, driver.driver_profile_id, v1)
        _enter_driver_context(client, driver)

        resp = client.post(
            f"/api/transport/drivers/{driver.driver_profile_id}/vehicles/switch",
            json={"vehicle_id": v1},
        )

        assert resp.status_code == 200
        body = resp.get_json()
        assert body["success"] is True
        assert body["data"]["unchanged"] is True

    def test_switch_to_foreign_vehicle_denied(self, app, client):
        driver = _seed_driver(app, compliance=ComplianceStatus.APPROVED)
        other = _seed_driver(app, compliance=ComplianceStatus.APPROVED)
        v1 = _add_owned_vehicle(app, driver.driver_profile_id, "API-504")
        _assign_vehicle(app, driver.driver_profile_id, v1)
        foreign_v = _add_owned_vehicle(app, other.driver_profile_id, "API-505")
        _enter_driver_context(client, driver)

        resp = client.post(
            f"/api/transport/drivers/{driver.driver_profile_id}/vehicles/switch",
            json={"vehicle_id": foreign_v},
        )

        assert resp.status_code == 403
        body = resp.get_json()
        assert body["success"] is False
        assert "own" in body["error"]

    def test_switch_to_inactive_vehicle_rejected(self, app, client):
        driver = _seed_driver(app, compliance=ComplianceStatus.APPROVED)
        v1 = _add_owned_vehicle(app, driver.driver_profile_id, "API-506")
        v2 = _add_owned_vehicle(
            app, driver.driver_profile_id, "API-507", status="maintenance"
        )
        _assign_vehicle(app, driver.driver_profile_id, v1)
        _enter_driver_context(client, driver)

        resp = client.post(
            f"/api/transport/drivers/{driver.driver_profile_id}/vehicles/switch",
            json={"vehicle_id": v2},
        )

        assert resp.status_code == 422
        assert resp.get_json()["success"] is False

    def test_switch_requires_vehicle_id(self, app, client):
        driver = _seed_driver(app, compliance=ComplianceStatus.APPROVED)
        _enter_driver_context(client, driver)

        resp = client.post(
            f"/api/transport/drivers/{driver.driver_profile_id}/vehicles/switch",
            json={},
        )

        assert resp.status_code == 400
        assert "vehicle_id is required" in resp.get_json()["error"]

    def test_switch_requires_driver_ownership_of_profile(self, app, client):
        owner = _seed_driver(app, compliance=ComplianceStatus.APPROVED)
        other = _seed_driver(app, compliance=ComplianceStatus.APPROVED)
        v1 = _add_owned_vehicle(app, owner.driver_profile_id, "API-508")
        _assign_vehicle(app, owner.driver_profile_id, v1)
        _enter_driver_context(client, other)

        resp = client.post(
            f"/api/transport/drivers/{owner.driver_profile_id}/vehicles/switch",
            json={"vehicle_id": v1},
        )

        assert resp.status_code == 403


class TestOnlineToggleContract:
    """The availability toggle must target the canonical driver_status endpoint
    (registered as ``transport_api.driver_go_live_status``), never a dead
    ``/me/status`` alias — otherwise a driver silently believes they went
    online while the server was never told."""

    def test_online_toggle_targets_canonical_status_endpoint(self, app, client):
        driver = _seed_driver(app, compliance=ComplianceStatus.APPROVED, kyc=True)
        _make_go_live_ready(app, driver)
        _enter_driver_context(client, driver)

        body = _fresh_get(client, "/transport/driver-dashboard").data.decode("utf-8")

        assert 'id="onlineToggle"' in body
        # The canonical endpoint reachable from the rendered page.
        assert (
            f"/api/transport/drivers/{driver.driver_profile_id}/status" in body
        )
        # The old dead /me/status URL must never be shipped.
        assert "/api/transport/drivers/me/status" not in body

    def test_no_dead_status_url_is_ever_shipped(self, app, client):
        """Even with a non-ready driver (toggle absent) no dead URL leaks."""
        driver = _seed_driver(app, compliance=ComplianceStatus.APPROVED, kyc=True)
        _enter_driver_context(client, driver)

        body = _fresh_get(client, "/transport/driver-dashboard").data.decode("utf-8")

        assert "/api/transport/drivers/me/status" not in body