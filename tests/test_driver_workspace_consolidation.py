"""
Driver Workspace consolidation regression tests (Phase C).

Contract under test
-------------------
The Driver Workspace is ONE coherent participation surface reached through
``transport.driver_dashboard`` (``/transport/driver-dashboard``). Consolidation
is presentation-only: the view reuses existing transport services and its
authorization is unchanged.

Invariants asserted here:

* the workspace renders inside the dedicated driver shell and never renders
  the transport admin/operations navigation;
* entry is gated by an active DRIVER context — a PERSONAL context cannot enter;
* a PENDING driver can enter (participation) but has no online toggle, while a
  blocked driver is refused;
* My Vehicles is the driver-owned ``transport.vehicle_dashboard`` surface and
  must never fall back to the global vehicle registry
  (``transport.vehicles_index``);
* owned vehicles (``owner_type='driver'``, ``owner_id=DriverProfile.id``) and
  the assigned/current vehicle are distinct concepts — assigning a vehicle
  must not make it owned;
* the go-live rule set composed by ``can_go_live`` is unchanged.

Fixtures mirror ``tests/test_driver_workspace_activation.py`` patterns; helpers
are re-implemented locally to avoid cross-file import coupling.
"""
import uuid
from types import SimpleNamespace

import pytest

from app.extensions import db
from app.transport.models import (
    ComplianceStatus,
    DriverProfile,
    DriverVehicleHistory,
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
    """Create a real User + DriverProfile and return a lightweight ref.

    The returned namespace carries the public ``ctx_id`` the canonical context
    resolver expects in ``session['active_context_id']``.
    """
    from datetime import datetime, timezone

    from app.identity.individuals.individual_verification import (
        IndividualVerification,
    )
    from app.identity.models.user import User

    with app.app_context():
        uid = uuid.uuid4().hex[:8]
        user = User(
            public_id=str(uuid.uuid4()),
            username=f"cons_{uid}",
            email=f"cons_{uid}@test.example.com",
        )
        user.is_active = True
        user.is_verified = True
        user.set_password("TestPassword123!")
        db.session.add(user)
        db.session.flush()

        profile = DriverProfile(
            user_id=user.id,
            driver_code=f"CONS-{uid[:6].upper()}",
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


def _login(client, user):
    with client.session_transaction() as sess:
        sess["_user_id"] = user.public_id
        sess["_fresh"] = True


def _enter_driver_context(client, user):
    with client.session_transaction() as sess:
        sess["_user_id"] = user.public_id
        sess["_fresh"] = True
        sess["active_context_type"] = "driver"
        sess["active_context_id"] = user.ctx_id
        sess["active_role"] = "driver"


def _add_owned_vehicle(app, driver_profile_id, plate):
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
        )
        db.session.add(vehicle)
        db.session.commit()
        return vehicle.id


def _add_foreign_vehicle(app, other_driver_profile_id, plate):
    with app.app_context():
        vehicle = Vehicle(
            owner_type="driver",
            owner_id=other_driver_profile_id,
            license_plate=plate,
            make="Nissan",
            model="Note",
            year=2019,
            vehicle_type="sedan",
            vehicle_class=VehicleClass.ECONOMY,
            passenger_capacity=4,
        )
        db.session.add(vehicle)
        db.session.commit()
        return vehicle.id


def _assign_vehicle(app, driver_profile_id, vehicle_id):
    from datetime import datetime, timezone

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


# ===========================================================================
# Tests
# ===========================================================================


class TestDriverWorkspaceRendering:
    """The consolidated home renders inside the driver shell only."""

    def test_driver_workspace_renders(self, app, client):
        driver = _seed_driver(app, compliance=ComplianceStatus.PENDING_REVIEW)
        _enter_driver_context(client, driver)

        resp = _fresh_get(client, "/transport/driver-dashboard")

        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
        assert "Driver Dashboard" in resp.data.decode("utf-8")

    def test_driver_workspace_has_driver_shell(self, app, client):
        driver = _seed_driver(app, compliance=ComplianceStatus.PENDING_REVIEW)
        _enter_driver_context(client, driver)

        body = _fresh_get(client, "/transport/driver-dashboard").data.decode("utf-8")

        assert "t-sidebar" in body
        assert "My Transport" in body
        assert "Register Vehicle" in body

    def test_driver_workspace_has_no_admin_navigation(self, app, client):
        driver = _seed_driver(app, compliance=ComplianceStatus.PENDING_REVIEW)
        _enter_driver_context(client, driver)

        body = _fresh_get(client, "/transport/driver-dashboard").data.decode("utf-8")

        forbidden = [
            'href="/transport/drivers"',
            'href="/transport/vehicles"',
            "drivers_verification",
            "drivers_location",
            "drivers_history",
            "Driver Roster",
            "Trip History",
            "My Location",
            "Verification Status",
        ]
        for needle in forbidden:
            assert needle not in body, f"Admin/operations surface leaked: {needle!r}"


class TestDriverContextGate:
    """Workspace entry requires an active DRIVER context, nothing more."""

    def test_driver_context_required(self, app, client):
        driver = _seed_driver(app, compliance=ComplianceStatus.PENDING_REVIEW)
        _login(client, driver)

        resp = _fresh_get(client, "/transport/driver-dashboard")

        assert resp.status_code == 403

    def test_personal_context_cannot_enter_driver_workspace(self, app, client):
        driver = _seed_driver(app, compliance=ComplianceStatus.PENDING_REVIEW)
        with client.session_transaction() as sess:
            sess["_user_id"] = driver.public_id
            sess["_fresh"] = True
            sess["active_context_type"] = "personal"
            sess["active_role"] = "user"

        resp = _fresh_get(client, "/transport/driver-dashboard")

        assert resp.status_code == 403

    def test_workspace_allowed_before_go_live(self, app, client):
        """KYC-qualified but not-yet-approved driver: workspace yes, go-live no."""
        driver = _seed_driver(app, compliance=ComplianceStatus.PENDING_REVIEW, kyc=True)
        _enter_driver_context(client, driver)

        resp = _fresh_get(client, "/transport/driver-dashboard")
        body = resp.data.decode("utf-8")

        assert resp.status_code == 200
        assert 'id="onlineToggle"' not in body

    def test_workspace_allowed_for_pending_driver(self, app, client):
        driver = _seed_driver(app, compliance=ComplianceStatus.UNDER_REVIEW)
        _enter_driver_context(client, driver)

        resp = _fresh_get(client, "/transport/driver-dashboard")

        assert resp.status_code == 200
        assert "pending review" in resp.data.decode("utf-8").lower()

    def test_workspace_denied_for_blocked_driver(self, app, client):
        driver = _seed_driver(app, compliance=ComplianceStatus.SUSPENDED, kyc=True)
        _enter_driver_context(client, driver)

        resp = _fresh_get(client, "/transport/driver-dashboard")

        assert resp.status_code == 403


class TestVehicleOwnershipSemantics:
    """My Vehicles (owned) and the assigned vehicle stay distinct."""

    def test_my_vehicles_is_driver_owned(self, app, client):
        from app.transport.services import get_provider_service

        owner = _seed_driver(app, compliance=ComplianceStatus.PENDING_REVIEW)
        other = _seed_driver(app, compliance=ComplianceStatus.PENDING_REVIEW)
        _add_owned_vehicle(app, owner.driver_profile_id, "OWN-001")
        _add_foreign_vehicle(app, other.driver_profile_id, "OTHER-999")

        with app.app_context():
            plates = {
                v.license_plate for v in get_provider_service().get_user_vehicles(owner.id)
            }

        assert plates == {"OWN-001"}

        _enter_driver_context(client, owner)
        body = _fresh_get(client, "/transport/driver-dashboard").data.decode("utf-8")
        assert "OWN-001" in body
        assert "OTHER-999" not in body

    def test_assigned_vehicle_does_not_become_owned_vehicle(self, app):
        from app.transport.services import get_provider_service

        owner = _seed_driver(app, compliance=ComplianceStatus.PENDING_REVIEW)
        fleet_owner = _seed_driver(app, compliance=ComplianceStatus.APPROVED)
        foreign_vehicle_id = _add_foreign_vehicle(
            app, fleet_owner.driver_profile_id, "FLEET-777"
        )
        _assign_vehicle(app, owner.driver_profile_id, foreign_vehicle_id)

        with app.app_context():
            profile = DriverProfile.query.filter_by(
                user_id=owner.id, is_deleted=False
            ).first()
            assigned = profile.current_vehicle
            owned = get_provider_service().get_user_vehicles(owner.id)

        assert assigned is not None
        assert assigned.license_plate == "FLEET-777"
        assert owned == []

    def test_driver_home_links_only_registered_driver_surfaces(self, app, client):
        driver = _seed_driver(app, compliance=ComplianceStatus.PENDING_REVIEW)
        _enter_driver_context(client, driver)

        body = _fresh_get(client, "/transport/driver-dashboard").data.decode("utf-8")

        assert 'href="/transport/vehicle-dashboard"' in body
        assert 'href="/transport/vehicles"' not in body


class TestGoLiveRulePreservation:
    """Consolidation must not change the go-live capability."""

    def test_existing_go_live_rules_unchanged(self, app):
        from app.transport.services.go_live_service import can_go_live

        driver = _seed_driver(app, compliance=ComplianceStatus.PENDING_REVIEW, kyc=True)

        with app.app_context():
            profile = DriverProfile.query.filter_by(
                user_id=driver.id, is_deleted=False
            ).first()
            checklist = can_go_live(profile)

        assert [c.key for c in checklist.checks] == [
            "profile",
            "kyc",
            "blocked",
            "approval",
            "licence",
            "vehicle",
        ]
        assert checklist.ready is False
