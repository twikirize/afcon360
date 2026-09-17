"""
Canonical Identity Center - convergence regression tests.

Contract under test (Identity Center brief):
- ONE canonical identity, MANY consumers. Person data lives only in
  UserProfile; verification / KYC state comes only from the canonical
  authorities (calculate_kyc_tier, KycRecord, IndividualVerification).
- get_canonical_identity() is the canonical read contract; it never stores a
  copy of identity data.
- The Driver Workspace is a PARTICIPATION context: any live non-blocked
  DriverProfile may enter it regardless of canonical KYC tier. The canonical
  KYC authority (calculate_kyc_tier >= tier 2 = phone + National ID + selfie)
  gates GO-LIVE (can_go_live) only — NOT workspace entry - and is never
  answered by User.is_fully_verified().
- Identity fields are editable while unverified and immutable once verified;
  missing + unverified fields are never trapped.

These tests mirror the fixture style of tests/test_onboarding.py and are
self-contained (no cross-file helper imports).
"""
import datetime as dt
import uuid
from types import SimpleNamespace

import pytest

from app.extensions import db
from app.profile.models import UserProfile, get_profile_by_user
from app.profile.services.canonical_identity import get_canonical_identity
from app.auth.kyc_compliance import (
    calculate_kyc_tier,
    driver_go_live_kyc_qualified,
)
from app.identity.models.user import User, UserRole
from app.identity.models.roles_permission import get_or_create_role
from app.identity.individuals.individual_verification import (
    IndividualVerification,
)
from app.transport.models import ComplianceStatus, DriverProfile, VerificationTier


_TIER2_SCOPE = {
    "national_id": True,
    "biometric": True,
}


def _make_user(app, *, kyc=False, phone_only=False, driver=False, verified=False):
    """Create a committed User + UserProfile mirroring registration.

    kyc=True     -> canonical tier 2 (phone + National ID + selfie) and
                    UserProfile.verification_status = "verified" (the write
                    KYC approval performs).
    phone_only   -> tier 1 only (verified phone, no National ID / selfie).
    driver=True  -> adds a PENDING DriverProfile wrapping the user.
    Returns a lightweight SimpleNamespace bound to the real DB row.
    """
    with app.app_context():
        user_role = get_or_create_role("user", level=6)
        uid = uuid.uuid4().hex[:8]
        user = User(
            public_id=str(uuid.uuid4()),
            username=f"cid_{uid}",
            email=f"cid_{uid}@test.example.com",
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
                full_name="Canonical Identity User",
                date_of_birth=dt.date(1990, 1, 15),
                nationality="UG",
                id_type="national_id",
                id_number="NID-CID-001",
                profile_completed=True,
            )
        )

        if kyc or phone_only:
            from datetime import datetime, timezone

            user.phone_verified = True
            user.phone_verified_at = datetime.now(timezone.utc)
            user.phone = f"+2567{uuid.uuid4().hex[:7]}"

        if kyc:
            db.session.add(
                IndividualVerification(
                    user_id=user.id,
                    status="verified",
                    scope=dict(_TIER2_SCOPE),
                )
            )
            if verified:
                db.session.flush()
                profile = get_profile_by_user(user.public_id)
                profile.verification_status = "verified"

        if driver:
            db.session.add(
                DriverProfile(
                    user_id=user.id,
                    driver_code=f"CID-{uid[:6].upper()}",
                    verification_tier=VerificationTier.PENDING,
                    compliance_status=ComplianceStatus.PENDING_REVIEW,
                    is_active=True,
                    is_online=False,
                    is_available=False,
                    max_passenger_capacity=4,
                    vehicle_classes=["comfort"],
                )
            )

        db.session.commit()
        return SimpleNamespace(
            public_id=user.public_id,
            id=user.id,
            email=user.email,
            username=user.username,
        )


@pytest.fixture
def base_user(app):
    return _make_user(app)


@pytest.fixture
def kyc_user(app):
    return _make_user(app, kyc=True, verified=True)


@pytest.fixture
def phone_user(app):
    return _make_user(app, phone_only=True)


@pytest.fixture
def kyc_driver_user(app):
    return _make_user(app, kyc=True, driver=True)


@pytest.fixture
def driver_user_no_kyc(app):
    return _make_user(app, driver=True)


@pytest.fixture
def client(app):
    """Fresh client per test - avoids cross-test session leakage from the
    session-scoped conftest client."""
    return app.test_client()


def _session_login(client, user):
    with client.session_transaction() as sess:
        sess["_user_id"] = user.public_id
        sess["_fresh"] = True


def _body(resp):
    return resp.data.decode("utf-8")


# ---------------------------------------------------------------------------
# Canonical read contract
# ---------------------------------------------------------------------------


class TestCanonicalIdentityContract:
    def test_composes_profile_values_and_kyc_authority(self, app, kyc_user):
        """get_canonical_identity surfaces the canonical person data AND the
        canonical KYC tier (2 = phone + National ID + selfie)."""
        with app.app_context():
            identity = get_canonical_identity(kyc_user.public_id)
            assert identity.full_name == "Canonical Identity User"
            assert identity.date_of_birth == "1990-01-15"
            assert identity.nationality == "UG"
            assert identity.id_type == "national_id"
            assert identity.id_number == "NID-CID-001"
            assert identity.verification_status == "verified"
            assert identity.kyc_tier == 2
            assert identity.is_verified() is True
            assert identity.phone_verified is True
            assert "full_name" in identity.immutable_fields
            assert "nationality" in identity.immutable_fields

    def test_kyc_authority_dominates_profile_snapshot(self, app, base_user):
        """A profile with stored identity but no canonical verification stays
        at tier 0 - the UserProfile.kyc_level label is NOT the authority."""
        with app.app_context():
            identity = get_canonical_identity(base_user.public_id)
            assert identity.kyc_tier == 0
            assert identity.is_verified() is False
            assert identity.kyc_decisions.get("tier") == 0

    def test_phone_only_identity_is_tier1(self, app, phone_user):
        """Verified phone alone = tier 1, not the Driver Workspace tier."""
        with app.app_context():
            identity = get_canonical_identity(phone_user.public_id)
            assert identity.kyc_tier == 1
            assert identity.is_verified() is False


class TestDriverWorkspaceCanonicalGate:
    """The Driver Workspace is a PARTICIPATION context (live DriverProfile,
    not blocked) regardless of canonical KYC tier. The canonical KYC authority
    — not User.is_fully_verified() (Identity Center rule 13) — gates GO-LIVE:
    ``can_go_live`` requires calculate_kyc_tier >= 2 for the toggle."""

    def test_tier2_driver_gets_workspace_context(self, app, kyc_driver_user):
        from app.auth.context import get_available_contexts

        with app.app_context():
            real = db.session.get(User, kyc_driver_user.id)
            assert calculate_kyc_tier(real.id)["tier"] == 2
            assert driver_go_live_kyc_qualified(real.id) is True
            types = [c.type.value for c in get_available_contexts(real)]
            assert "driver" in types

    def test_tier0_driver_still_gets_workspace_context(self, app, driver_user_no_kyc):
        """Workspace entry is PARTICIPATION: a driver with a live profile but
        canonical KYC tier 0 still sees a DRIVER context. The KYC tier gates
        GO-LIVE (can_go_live), not workspace participation."""
        from app.auth.context import get_available_contexts

        with app.app_context():
            real = db.session.get(User, driver_user_no_kyc.id)
            assert calculate_kyc_tier(real.id)["tier"] == 0
            assert driver_go_live_kyc_qualified(real.id) is False
            types = [c.type.value for c in get_available_contexts(real)]
            assert "driver" in types

    def test_phone_only_tier1_driver_still_gets_workspace_context(self, app, phone_user):
        """Tier 1 (phone only) is insufficient for GO-LIVE, but workspace
        participation (live DriverProfile) is granted."""
        from app.auth.context import get_available_contexts

        with app.app_context():
            real = db.session.get(User, phone_user.id)
            db.session.add(
                DriverProfile(
                    user_id=real.id,
                    driver_code="CID-P1",
                    verification_tier=VerificationTier.PENDING,
                    compliance_status=ComplianceStatus.PENDING_REVIEW,
                    is_active=True,
                    is_online=False,
                    is_available=False,
                    max_passenger_capacity=4,
                    vehicle_classes=["comfort"],
                )
            )
            db.session.commit()
            assert calculate_kyc_tier(real.id)["tier"] == 1
            assert driver_go_live_kyc_qualified(real.id) is False
            types = [c.type.value for c in get_available_contexts(real)]
            assert "driver" in types

    def test_workspace_allowed_regardless_of_kyc_tier(
        self, app, driver_user_no_kyc, phone_user, kyc_driver_user
    ):
        """Workspace access has NO KYC threshold (replaces the obsolete
        constant-equality test that tied workspace entry to the
        transport_booking activity tier). Tier 0, 1, and 2 drivers with a live
        non-blocked profile all get a DRIVER context — KYC only gates
        GO-LIVE, not participation."""
        from app.auth.context import get_available_contexts

        with app.app_context():
            real_phone = db.session.get(User, phone_user.id)
            db.session.add(
                DriverProfile(
                    user_id=real_phone.id,
                    driver_code="CID-P1",
                    verification_tier=VerificationTier.PENDING,
                    compliance_status=ComplianceStatus.PENDING_REVIEW,
                    is_active=True,
                    is_online=False,
                    is_available=False,
                    max_passenger_capacity=4,
                    vehicle_classes=["comfort"],
                )
            )
            db.session.commit()

        for user, expected_tier in (
            (driver_user_no_kyc, 0),
            (phone_user, 1),
            (kyc_driver_user, 2),
        ):
            with app.app_context():
                real = db.session.get(User, user.id)
                assert calculate_kyc_tier(real.id)["tier"] == expected_tier
                types = [c.type.value for c in get_available_contexts(real)]
                assert "driver" in types, (
                    f"tier {expected_tier} denied workspace"
                )

    def test_workspace_access_and_go_live_are_independent_gates(
        self, app, driver_user_no_kyc
    ):
        """SEPARATION: workspace access != Go Live authorization. A tier-0
        driver with a live profile gets the DRIVER context (workspace) while
        ``can_go_live`` closes the KYC gate — the two are independent."""
        from app.auth.context import get_available_contexts
        from app.transport.services.go_live_service import can_go_live

        with app.app_context():
            real = db.session.get(User, driver_user_no_kyc.id)
            profile = DriverProfile.query.filter_by(
                user_id=real.id, is_deleted=False
            ).first()

            types = [c.type.value for c in get_available_contexts(real)]
            assert "driver" in types
            assert driver_go_live_kyc_qualified(real.id) is False

            checklist = can_go_live(profile)
            assert checklist.ready is False
            kyc_check = next(c for c in checklist.checks if c.key == "kyc")
            assert kyc_check.ok is False


# ---------------------------------------------------------------------------
# Canonical display in consumers
# ---------------------------------------------------------------------------


class TestCanonicalDisplay:
    def test_account_page_shows_canonical_full_name(self, app, client, kyc_user):
        _session_login(client, kyc_user)
        resp = client.get("/account")
        assert resp.status_code == 200
        assert "Canonical Identity User" in _body(resp)

    def test_profile_edit_page_shows_canonical_values(self, app, client, kyc_user):
        _session_login(client, kyc_user)
        resp = client.get("/profile/edit")
        assert resp.status_code == 200
        assert "Canonical Identity User" in _body(resp)

    def test_driver_step1_prefills_canonical_identity(self, app, client, kyc_user):
        """Driver onboarding Step 1 prefills and locks the canonical name and
        National ID from UserProfile - it never asks to retype them."""
        _session_login(client, kyc_user)
        resp = client.get("/onboarding/driver/step/1")
        assert resp.status_code == 200
        body = _body(resp)
        assert 'value="Canonical Identity User"' in body
        assert 'value="NID-CID-001"' in body
        assert "readonly" in body


# ---------------------------------------------------------------------------
# Field editability (Identity Center rules 8/9)
# ---------------------------------------------------------------------------


class TestCanonicalFieldEditability:
    def test_unverified_identity_field_editable(self, app, client, base_user):
        """Unverified identity fields are editable - missing values are never
        trapped into immutability."""
        _session_login(client, base_user)
        resp = client.post(
            "/profile/edit",
            data={"full_name": "Editable Name", "nationality": "TZ", "country": "TZ"},
            follow_redirects=False,
        )
        assert resp.status_code == 302
        with app.app_context():
            profile = get_profile_by_user(base_user.public_id)
            assert profile.full_name == "Editable Name"
            assert profile.nationality == "TZ"

    def test_verified_identity_field_not_overwritten(self, app, client, kyc_user):
        """Verified identity fields are immutable - an attempted override is
        blocked and the canonical value is preserved."""
        _session_login(client, kyc_user)
        resp = client.post(
            "/profile/edit",
            data={"full_name": "Override Name", "nationality": "KE", "country": "UG"},
            follow_redirects=False,
        )
        assert resp.status_code == 302
        with app.app_context():
            profile = get_profile_by_user(kyc_user.public_id)
            assert profile.full_name == "Canonical Identity User"
            assert profile.nationality == "UG"

    def test_missing_unverified_field_not_trapped(self, app, client, base_user):
        """A profile missing a contact field (city/address) can still complete
        it once - the field stays editable until it is provided."""
        _session_login(client, base_user)
        resp = client.post(
            "/profile/edit",
            data={"city": "Kampala", "address": "Plot 1", "country": "UG"},
            follow_redirects=False,
        )
        assert resp.status_code == 302
        with app.app_context():
            profile = get_profile_by_user(base_user.public_id)
            assert profile.city == "Kampala"
            assert profile.address == "Plot 1"


# ---------------------------------------------------------------------------
# Identity security boundary
# ---------------------------------------------------------------------------


class TestIdentitySecurityBoundary:
    def test_cannot_read_another_users_private_identity(self, app, client, base_user, kyc_user):
        """A user viewing another user's public profile never receives that
        user's National ID, DOB, or email - those are private."""
        _session_login(client, base_user)
        resp = client.get(f"/profile/{kyc_user.public_id}")
        assert resp.status_code == 200
        body = _body(resp)
        assert "NID-CID-001" not in body
        assert "1990-01-15" not in body
        assert kyc_user.email not in body

    def test_update_settings_mutates_only_actor(self, app, client, base_user, kyc_user):
        """POST /update-settings is scoped to the authenticated actor; it can
        never mutate another user's canonical profile."""
        _session_login(client, base_user)
        client.post(
            "/update-settings",
            data={"city": "Hacked-City"},
            follow_redirects=False,
        )
        with app.app_context():
            actor = get_profile_by_user(base_user.public_id)
            target = get_profile_by_user(kyc_user.public_id)
            assert actor.city == "Hacked-City"
            assert target.city is None or target.city != "Hacked-City"

    def test_driver_wizard_does_not_change_canonical_identity(self, app, client, base_user):
        """Driver onboarding consumes identity but never writes it: after the
        wizard (entering the Driver Workspace as participation) the canonical
        UserProfile identity is byte-for-byte unchanged."""
        _session_login(client, base_user)

        assert client.get("/onboarding/driver/step/1").status_code == 200
        assert client.post(
            "/onboarding/driver/step/1",
            data={
                "full_name": "Attempted Override Name",
                "date_of_birth": "1999-09-09",
                "nationality": "TZ",
                "national_id_number": "NID-OVERRIDE-999",
            },
            follow_redirects=False,
        ).status_code == 302
        assert client.post(
            "/onboarding/driver/step/2",
            data={
                "licence_number": "LIC-CID-001",
                "licence_expiry": "2032-01-15",
                "licence_class": "B",
            },
            follow_redirects=False,
        ).status_code == 302
        r3 = client.post(
            "/onboarding/driver/step/3",
            data={
                "vehicle_make": "Toyota",
                "vehicle_model": "Hiace",
                "vehicle_year": "2019",
                "plate_number": "UBD-123C",
                "vehicle_type": "van",
            },
            follow_redirects=False,
        )
        assert r3.status_code == 302
        # Participation: step 3 enters the Driver Workspace (no KYC gate)
        assert "/transport/driver-dashboard" in r3.headers.get("Location", "")

        with app.app_context():
            profile = get_profile_by_user(base_user.public_id)
            assert profile.full_name == "Canonical Identity User"
            assert profile.nationality == "UG"
            assert profile.id_type == "national_id"
            assert profile.id_number == "NID-CID-001"