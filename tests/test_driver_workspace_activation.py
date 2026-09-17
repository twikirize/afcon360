"""
Driver Workspace activation regression tests.

Contract under test
-------------------
REGISTER  →  Driver Workspace (participation: profile / docs / vehicles /
status)  →  admin review  →  approval  →  GO-LIVE (operational access).

The Driver Workspace is a PARTICIPATION surface: ``context.py
_driver_contexts`` requires only a live ``DriverProfile``, a non-blocked
compliance state, and a resolvable public id — identity verification,
compliance approval, licence validity, and (where the operating mode
requires it) a vehicle are NOT workspace-entry gates.

Going LIVE is a separate, stricter capability composed by the single
authoritative authority ``can_go_live`` (``app/transport/services/
go_live_service.py``): KYC capability (tier >= 2), not blocked, compliance
approved, valid licence, and a current vehicle for on-demand mode.

Operational writes go through the self-service REST contract
``POST /api/transport/drivers/<id>/status``, which enforces ownership and
re-derives ``can_go_live`` before allowing the state change. It deliberately
does NOT use the obsolete ``driver:update_status`` permission (granted to no
role and therefore only reachable by the is_owner bypass). The admin
approve/reject path keeps its existing behavior via ``update_driver_status``.

Fixtures mirror ``tests/test_onboarding.py`` patterns; helpers re-implemented
locally to avoid cross-file import coupling.
"""
import datetime as dt
import uuid
from types import SimpleNamespace

import pytest

from app.extensions import db
from app.transport.models import ComplianceStatus, DriverProfile, VerificationTier


# ---------------------------------------------------------------------------
# Helpers (local mirrors of test_onboarding.py patterns)
# ---------------------------------------------------------------------------

def _session_login(client, user):
    with client.session_transaction() as sess:
        sess["_user_id"] = user.public_id
        sess["_fresh"] = True


def _make_kyc_verified(app, user):
    """Approve identity at the canonical Driver Workspace capability: verified
    phone + National ID + selfie = canonical KYC tier 2 (calculate_kyc_tier).

    Writes the approved IndividualVerification row the host can_host() gate
    reads AND flips the real User row's phone flags that tier 1 requires.
    """
    from datetime import datetime, timezone

    from app.identity.individuals.individual_verification import (
        IndividualVerification,
    )
    from app.identity.models.user import User

    with app.app_context():
        real_user = db.session.get(User, user.id)
        if real_user is not None:
            real_user.phone_verified = True
            real_user.phone_verified_at = datetime.now(timezone.utc)
            if not real_user.phone:
                real_user.phone = f"+2567{uuid.uuid4().hex[:7]}"
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


def _fresh_get(client, url, **kwargs):
    """GET that clears the Flask-Caching user cache first (avoids stale loader)."""
    from app.extensions import cache

    try:
        cache.clear()
    except Exception:
        pass
    return client.get(url, **kwargs)


def _fresh_post(client, url, data=None, **kwargs):
    """POST that clears the Flask-Caching user cache first."""
    from app.extensions import cache

    try:
        cache.clear()
    except Exception:
        pass
    return client.post(url, data=data, **kwargs)


# Shared wizard form data (step 1/2/3) — identity fields intentionally
# do NOT override canonical UserProfile values (handled server-side).
_STEP1_DATA = {
    "full_name": "Driver Test User",
    "date_of_birth": "1995-03-20",
    "nationality": "UG",
    "national_id_number": "NID-DRV-TEST-001",
}
_STEP2_DATA = {
    "licence_number": "LIC-123-ABC",
    "licence_expiry": "2033-12-31",
    "licence_class": "B",
}
_STEP3_DATA = {
    "vehicle_make": "Toyota",
    "vehicle_model": "Corolla",
    "vehicle_year": "2021",
    "plate_number": "UAX-123B",
    "vehicle_type": "comfort",
}


def _complete_wizard(client, user):
    """POST steps 1 → 2 → 3. Returns the step-3 response."""
    _session_login(client, user)
    # step 1
    r1 = _fresh_post(
        client, "/onboarding/driver/step/1", data=_STEP1_DATA, follow_redirects=False
    )
    assert r1.status_code == 302
    # step 2
    r2 = _fresh_post(
        client, "/onboarding/driver/step/2", data=_STEP2_DATA, follow_redirects=False
    )
    assert r2.status_code == 302
    # step 3 (commit)
    return _fresh_post(
        client, "/onboarding/driver/step/3", data=_STEP3_DATA, follow_redirects=False
    )


# ---------------------------------------------------------------------------
# Fixture: committed, profile-complete user + IndividualVerification row
# ---------------------------------------------------------------------------

@pytest.fixture()
def driver_user(app):
    """Committed User + UserProfile with identity verified and profile completed.

    Mirrors ``test_onboarding.verified_user`` but returns the real DB-backed
    User object (not a SimpleNamespace) so ``switch_context`` and the session
    loader resolve correctly.
    """
    from app.identity.models.user import User, UserRole
    from app.identity.models.roles_permission import get_or_create_role
    from app.profile.models import UserProfile

    with app.app_context():
        user_role = get_or_create_role("user", level=6)
        uid = uuid.uuid4().hex[:8]
        user = User(
            public_id=str(uuid.uuid4()),
            username=f"driver_{uid}",
            email=f"driver_{uid}@test.example.com",
        )
        user.set_password("TestPassword123!")
        user.is_active = True
        user.is_verified = True
        user.email_verified = True
        db.session.add(user)
        db.session.flush()
        db.session.add(UserRole(user_id=user.id, role_id=user_role.id))
        db.session.add(
            UserProfile(
                user_id=user.public_id,
                full_name="Driver Test User",
                profile_completed=True,
                date_of_birth=dt.date(1995, 3, 20),
                nationality="UG",
                id_type="national_id",
                id_number="NID-DRV-TEST-001",
            )
        )
        db.session.commit()

        # Yield a lightweight ref with all attributes the test needs
        yield SimpleNamespace(
            public_id=user.public_id,
            id=user.id,
            email=user.email,
            username=user.username,
        )


@pytest.fixture()
def kyc_driver_user(app, driver_user):
    """driver_user with an approved IndividualVerification record
    (is_fully_verified() == True)."""
    _make_kyc_verified(app, driver_user)
    return driver_user


def _set_compliance(app, user_id, status):
    """Flip the given user's DriverProfile compliance status."""
    with app.app_context():
        dp = DriverProfile.query.filter_by(
            user_id=user_id, is_deleted=False
        ).first()
        assert dp is not None, "DriverProfile must exist before compliance update"
        dp.compliance_status = status
        db.session.commit()


def _assign_active_vehicle(app, user_id):
    """Assign a compliant Vehicle + active (ended_at=None) DriverVehicleHistory
    so on-demand go-live's vehicle requirement passes.

    The onboarding wizard intentionally does NOT create a Vehicle (it is a
    separate later operation), so tests that exercise go-live-ready state must
    assign one explicitly.
    """
    from datetime import datetime, timezone

    from app.transport.models import (
        DriverVehicleHistory,
        Vehicle,
        VehicleClass,
    )

    with app.app_context():
        dp = DriverProfile.query.filter_by(
            user_id=user_id, is_deleted=False
        ).first()
        assert dp is not None, "DriverProfile must exist before vehicle assign"
        vehicle = Vehicle(
            owner_type="driver",
            owner_id=dp.id,
            license_plate=f"UAX-{uuid.uuid4().hex[:5].upper()}",
            make="Toyota",
            model="Corolla",
            year=2021,
            vehicle_type="sedan",
            vehicle_class=VehicleClass.COMFORT,
            passenger_capacity=4,
        )
        db.session.add(vehicle)
        db.session.flush()
        db.session.add(
            DriverVehicleHistory(
                driver_id=dp.id,
                vehicle_id=vehicle.id,
                started_at=datetime.now(timezone.utc),
                ended_at=None,
                assignment_reason="shift_start",
            )
        )
        db.session.commit()
        return vehicle.id


def _complete_wizard_and_get_dashboard(client, user):
    """Complete the driver wizard and return an authenticated GET of the
    driver dashboard."""
    _complete_wizard(client, user)
    return _fresh_get(client, "/transport/driver-dashboard")


# ===========================================================================
# Tests
# ===========================================================================


class TestStep3KYCGate:
    """Wizard step-3 POST enters the Driver Workspace regardless of KYC state
    (participation, not go-live)."""

    def test_unverified_user_step3_enters_workspace(self, app, client, driver_user):
        """An identity-unverified driver completing step 3 is routed into the
        Driver Workspace (participation) — NOT a KYC upload gate. Go-live is
        still refused by ``can_go_live`` at the toggle."""
        r3 = _complete_wizard(client, driver_user)

        # Must not 500
        assert r3.status_code != 500

        # Must redirect to the driver dashboard
        assert r3.status_code == 302
        location = r3.headers.get("Location", "")
        assert "/transport/driver-dashboard" in location, (
            f"Expected redirect to driver dashboard, got: {location}"
        )

        # Session MUST have been switched into driver context (participation)
        with client.session_transaction() as sess:
            assert sess.get("active_context_type") == "driver"
            assert sess.get("active_context_id") is not None
            assert sess.get("active_role") == "driver"

        # The dashboard is reachable but the online toggle is NOT rendered:
        # go-live requires KYC + approval + licence + vehicle (can_go_live).
        resp = _fresh_get(client, "/transport/driver-dashboard")
        assert resp.status_code == 200
        body = resp.data.decode("utf-8")
        assert 'id="onlineToggle"' not in body


class TestDriverWorkspaceActivation:
    """Verified driver completing step 3 enters the Driver Workspace immediately."""

    def test_verified_step3_switches_to_driver_context(
        self, app, client, kyc_driver_user
    ):
        """A KYC-verified driver completing step 3 lands on the driver dashboard
        with an active driver context in the session."""
        r3 = _complete_wizard(client, kyc_driver_user)

        assert r3.status_code != 500
        assert r3.status_code == 302
        location = r3.headers.get("Location", "")
        assert "/transport/driver-dashboard" in location, (
            f"Expected redirect to driver dashboard, got: {location}"
        )

        # Session must hold driver context
        with client.session_transaction() as sess:
            assert sess.get("active_context_type") == "driver"
            assert sess.get("active_context_id") is not None
            assert sess.get("active_role") == "driver"

    def test_pending_driver_dashboard_reachable(self, app, client, kyc_driver_user):
        """A PENDING driver can reach the dashboard (workspace access granted)
        but sees the pending-review banner and no online toggle."""
        # Complete wizard first to create the DriverProfile
        _complete_wizard(client, kyc_driver_user)

        resp = _fresh_get(client, "/transport/driver-dashboard")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
        body = resp.data.decode("utf-8")

        # Pending banner present
        assert "pending review" in body.lower(), (
            "Pending banner not found in dashboard body"
        )

        # Online toggle input must NOT be rendered for pending drivers
        assert 'id="onlineToggle"' not in body, (
            "Online toggle rendered for a PENDING driver"
        )


class TestOperationalGate:
    """Operational (go-live) actions are denied independently of workspace
    access. ``can_go_live`` is the single authority."""

    def test_approved_driver_dashboard_shows_online_toggle(
        self, app, client, kyc_driver_user
    ):
        """An APPROVED driver with licence + vehicle (go-live-ready) sees the
        online toggle on the dashboard."""
        # Complete wizard (creates live profile + licence), approve compliance
        # (admin review step), then assign an active vehicle — the wizard does
        # NOT create a Vehicle (separate later operation).
        _complete_wizard(client, kyc_driver_user)
        _set_compliance(app, kyc_driver_user.id, ComplianceStatus.APPROVED)
        _assign_active_vehicle(app, kyc_driver_user.id)

        resp = _fresh_get(client, "/transport/driver-dashboard")
        assert resp.status_code == 200
        body = resp.data.decode("utf-8")

        assert 'id="onlineToggle"' in body, (
            "Online toggle missing for go-live-ready APPROVED driver"
        )
        # Compliance badge should say 'Approved'
        assert "Approved" in body

    def test_approved_but_not_ready_driver_sees_requirements_not_toggle(
        self, app, client, kyc_driver_user
    ):
        """An APPROVED driver WITHOUT a vehicle (on-demand mode) is not
        go-live-ready: the toggle is replaced by the requirements panel."""
        _complete_wizard(client, kyc_driver_user)
        _set_compliance(app, kyc_driver_user.id, ComplianceStatus.APPROVED)

        resp = _fresh_get(client, "/transport/driver-dashboard")
        assert resp.status_code == 200
        body = resp.data.decode("utf-8")

        assert 'id="onlineToggle"' not in body, (
            "Online toggle rendered for APPROVED driver without vehicle"
        )
        # The go-live requirements panel is shown
        assert "Ready to go live" in body

    def test_pending_driver_operational_action_denied(self, app, client, kyc_driver_user):
        """A PENDING driver can reach the workspace but the go-live transition
        is refused: the REST endpoint returns 403 with the checklist because
        ``can_go_live`` is not ready."""
        _complete_wizard(client, kyc_driver_user)

        # Build the profile id
        with app.app_context():
            dp = DriverProfile.query.filter_by(
                user_id=kyc_driver_user.id, is_deleted=False
            ).first()
            assert dp is not None, "DriverProfile should exist after wizard commit"
            profile_id = dp.id

        # POST the online-toggle endpoint (driven by extra_js in the template)
        resp = _fresh_post(
            client,
            f"/api/transport/drivers/{profile_id}/status",
            json={"is_online": True, "is_available": True},
            follow_redirects=False,
        )
        # Must not 500
        assert resp.status_code != 500
        # Not ready -> 403 with go_live checklist
        assert resp.status_code == 403, (
            f"Expected 403 for pending driver go-live, got {resp.status_code}: {resp.data.decode('utf-8')}"
        )
        payload = resp.get_json() or {}
        assert payload.get("error") == "driver is not eligible to go live"
        go_live = payload.get("go_live") or {}
        assert go_live.get("ready") is False
        assert any(c.get("key") == "approval" for c in go_live.get("checks", []))

    def test_approved_ready_driver_goes_online_happy_path(
        self, app, client, kyc_driver_user
    ):
        """REAL happy path: an APPROVED, go-live-ready driver toggles online
        (is_online True) and the DB row reflects the change."""
        _complete_wizard(client, kyc_driver_user)
        _set_compliance(app, kyc_driver_user.id, ComplianceStatus.APPROVED)
        _assign_active_vehicle(app, kyc_driver_user.id)

        with app.app_context():
            dp = DriverProfile.query.filter_by(
                user_id=kyc_driver_user.id, is_deleted=False
            ).first()
            profile_id = dp.id
            assert dp.is_online is False

        resp = _fresh_post(
            client,
            f"/api/transport/drivers/{profile_id}/status",
            json={"is_online": True, "is_available": True},
            follow_redirects=False,
        )
        assert resp.status_code == 200, (
            f"Expected 200 for ready driver go-live, got {resp.status_code}: {resp.data.decode('utf-8')}"
        )
        payload = resp.get_json() or {}
        assert payload.get("success") is True
        assert payload["data"]["updates"]["is_online"] is True
        assert payload["data"]["updates"]["is_available"] is True
        assert payload["data"]["go_live"]["ready"] is True

        with app.app_context():
            dp = db.session.get(DriverProfile, profile_id)
            assert dp.is_online is True
            assert dp.is_available is True

    def test_driver_cannot_toggle_another_driver(self, app, client, kyc_driver_user):
        """Ownership boundary: driver A cannot toggle driver B's status."""
        # Driver B (kyc_driver_user) completes wizard and goes live-ready.
        _complete_wizard(client, kyc_driver_user)
        _set_compliance(app, kyc_driver_user.id, ComplianceStatus.APPROVED)
        _assign_active_vehicle(app, kyc_driver_user.id)

        with app.app_context():
            dp_b = DriverProfile.query.filter_by(
                user_id=kyc_driver_user.id, is_deleted=False
            ).first()
            profile_b = dp_b.id

        # Driver A is an entirely different user with NO DriverProfile, so
        # they cannot own B's profile (endpoint ownership => 403).
        from app.identity.models.user import User, UserRole
        from app.identity.models.roles_permission import get_or_create_role

        with app.app_context():
            user_role = get_or_create_role("user", level=6)
            uid = uuid.uuid4().hex[:8]
            user_a = User(
                public_id=str(uuid.uuid4()),
                username=f"drivera_{uid}",
                email=f"drivera_{uid}@test.example.com",
            )
            user_a.set_password("TestPassword123!")
            user_a.is_active = True
            user_a.is_verified = True
            user_a.email_verified = True
            db.session.add(user_a)
            db.session.flush()
            db.session.add(UserRole(user_id=user_a.id, role_id=user_role.id))
            db.session.commit()
            pub_a = user_a.public_id

        _session_login(client, SimpleNamespace(public_id=pub_a, id=None))
        resp = _fresh_post(
            client,
            f"/api/transport/drivers/{profile_b}/status",
            json={"is_online": True, "is_available": False},
            follow_redirects=False,
        )
        assert resp.status_code == 403, (
            f"Expected 403 for cross-driver status change, got {resp.status_code}: {resp.data.decode('utf-8')}"
        )

        with app.app_context():
            dp_b = db.session.get(DriverProfile, profile_b)
            assert dp_b.is_online is False

    def test_suspended_driver_go_live_denied(self, app, client, kyc_driver_user):
        """A SUSPENDED driver cannot go live even with licence + vehicle:
        ``can_go_live`` closes the blocked gate."""
        _complete_wizard(client, kyc_driver_user)
        _set_compliance(app, kyc_driver_user.id, ComplianceStatus.SUSPENDED)

        with app.app_context():
            dp = DriverProfile.query.filter_by(
                user_id=kyc_driver_user.id, is_deleted=False
            ).first()
            profile_id = dp.id

        resp = _fresh_post(
            client,
            f"/api/transport/drivers/{profile_id}/status",
            json={"is_online": True, "is_available": False},
            follow_redirects=False,
        )
        assert resp.status_code == 403, (
            f"Expected 403 for suspended driver go-live, got {resp.status_code}: {resp.data.decode('utf-8')}"
        )
        payload = resp.get_json() or {}
        go_live = payload.get("go_live") or {}
        assert go_live.get("ready") is False
        assert any(c.get("key") == "blocked" and not c.get("ok") for c in go_live.get("checks", []))

    def test_unvalidated_payload_rejected_400(self, app, client, kyc_driver_user):
        """A status POST with neither field is a 400 (contract validation)."""
        _complete_wizard(client, kyc_driver_user)

        with app.app_context():
            dp = DriverProfile.query.filter_by(
                user_id=kyc_driver_user.id, is_deleted=False
            ).first()
            profile_id = dp.id

        resp = _fresh_post(
            client,
            f"/api/transport/drivers/{profile_id}/status",
            json={},
            follow_redirects=False,
        )
        assert resp.status_code == 400, (
            f"Expected 400 for empty payload, got {resp.status_code}: {resp.data.decode('utf-8')}"
        )


class TestNegativeCases:
    """Negative workspace access cases."""

    def test_suspended_driver_workspace_denied(self, app, client, kyc_driver_user):
        """A SUSPENDED driver's context is blocked — workspace returns 403."""
        _complete_wizard(client, kyc_driver_user)
        _set_compliance(app, kyc_driver_user.id, ComplianceStatus.SUSPENDED)

        resp = _fresh_get(client, "/transport/driver-dashboard")
        # active_context_required aborts 403 when validate_context fails
        assert resp.status_code == 403, (
            f"Expected 403 for suspended driver, got {resp.status_code}"
        )

    def test_unauthorized_user_no_driver_workspace(self, app, client):
        """A user with no driver profile gets 403 on the driver dashboard."""
        # Create a verified user with KYC but no DriverProfile
        from app.identity.models.user import User
        from app.profile.models import UserProfile
        from app.identity.models.roles_permission import get_or_create_role
        from app.identity.models.user import UserRole

        with app.app_context():
            user_role = get_or_create_role("user", level=6)
            uid = uuid.uuid4().hex[:8]
            user = User(
                public_id=str(uuid.uuid4()),
                username=f"nodriver_{uid}",
                email=f"nodriver_{uid}@test.example.com",
            )
            user.set_password("TestPassword123!")
            user.is_active = True
            user.is_verified = True
            user.email_verified = True
            db.session.add(user)
            db.session.flush()
            db.session.add(UserRole(user_id=user.id, role_id=user_role.id))
            db.session.add(
                UserProfile(
                    user_id=user.public_id,
                    full_name="No Driver User",
                    profile_completed=True,
                )
            )
            # Canonical KYC tier stays below the go-live capability; and the
            # user has no DriverProfile at all — participation requires a live
            # profile, so the workspace is denied (403).
            from app.identity.individuals.individual_verification import (
                IndividualVerification,
            )
            db.session.add(
                IndividualVerification(
                    user_id=user.id,
                    status="verified",
                    scope={"identity": True, "address": True},
                )
            )
            db.session.commit()
            pub_id = user.public_id

        _session_login(client, SimpleNamespace(public_id=pub_id, id=None))
        resp = _fresh_get(client, "/transport/driver-dashboard")
        assert resp.status_code == 403, (
            f"Expected 403 for user without driver profile, got {resp.status_code}"
        )


class TestContextGateUnit:
    """Unit-level tests on the ``get_available_contexts`` identity gate.

    ``_driver_contexts`` resolves the DriverProfile from the database via
    ``DriverProfile.query`` (not the ``driver_profile`` attribute), so each
    test seeds a real user + PENDING DriverProfile row and wraps a lightweight
    namespace around the real DB user id.
    """

    def _seed(self, app, *, kyc=True):
        """Create a real User + PENDING DriverProfile; return a lightweight
        user namespace bound to the real DB ``id``.

        ``kyc=True`` lifts the real user to canonical KYC tier 2 (verified
        phone + National ID + selfie), the go-live capability.
        ``kyc=False`` leaves the user below tier 2 (no phone verification) —
        workspace PARTICIPATION still holds; only go-live is blocked.
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
                username=f"ctx_{uid}",
                email=f"ctx_{uid}@test.example.com",
            )
            user.is_active = True
            user.is_verified = True
            user.set_password("TestPassword123!")
            db.session.add(user)
            db.session.flush()
            db.session.add(
                DriverProfile(
                    user_id=user.id,
                    driver_code=f"CTX-{uid[:6].upper()}",
                    verification_tier=VerificationTier.PENDING,
                    compliance_status=ComplianceStatus.PENDING_REVIEW,
                    is_active=True,
                    is_online=False,
                    is_available=False,
                    max_passenger_capacity=4,
                    vehicle_classes=["comfort"],
                )
            )
            if kyc:
                user.phone_verified = True
                user.phone_verified_at = datetime.now(timezone.utc)
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

            return SimpleNamespace(id=user.id, is_active=True)

    def test_context_present_when_kyc_qualified(self, app):
        """A user with a live DriverProfile and canonical KYC tier >= 2 sees a
        DRIVER context."""
        from app.auth.context import get_available_contexts

        contexts = get_available_contexts(self._seed(app, kyc=True))
        types = [c.type.value for c in contexts]
        assert "driver" in types

    def test_context_present_when_kyc_not_qualified(self, app):
        """Workspace entry is PARTICIPATION, not go-live: a user whose
        canonical KYC tier is below the capability STILL sees a DRIVER context
        as long as they have a live, non-blocked DriverProfile. The KYC gate
        is enforced by ``can_go_live`` at go-live, never at workspace entry."""
        from app.auth.context import get_available_contexts

        contexts = get_available_contexts(self._seed(app, kyc=False))
        types = [c.type.value for c in contexts]
        assert "driver" in types

    def test_context_present_without_is_fully_verified_attribute(self, app):
        """The gate is driven by the canonical KYC authority, not the
        ``is_fully_verified`` attribute: a tier-2-qualified namespace without
        that attribute still gets a DRIVER context (unit-test fixture style,
        e.g. ``test_auth_context._user()``)."""
        from app.auth.context import get_available_contexts

        contexts = get_available_contexts(self._seed(app, kyc=True))
        types = [c.type.value for c in contexts]
        assert "driver" in types
