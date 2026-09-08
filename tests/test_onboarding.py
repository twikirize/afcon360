"""
Onboarding entry & partner gate tests (approved architecture).

Under test:
    verified User -> login -> /user/dashboard            (no forced onboarding)
    /user/dashboard -> "Become a Partner" -> /onboarding (choose)
    /onboarding -> Individual Partner | Organisation
    Individual  -> Driver | Accommodation Host | Event Organiser
    Organisation-> Transport | Hotel/Lodge | Consumer Organisation

Partner selection is OPTIONAL and ADDITIVE. A verified User is a normal
customer immediately; partnership never blocks or replaces the customer
experience, and a User may enable more than one capability over time.

Run with: pytest tests/test_onboarding.py -v
"""
import uuid
from types import SimpleNamespace

import pytest

from app import create_app
from app.config import TestingConfig
from app.extensions import db
from app.identity.models.user import User, UserRole
from app.identity.models.roles_permission import get_or_create_role
from app.profile.models import UserProfile, get_profile_by_user


@pytest.fixture
def verified_user(app):
    """A freshly OTP-verified AFCON 360 System User:
    default global role 'user', profile profile_completed=False
    (the exact state the real sign-up pipeline leaves behind).
    """
    with app.app_context():
        user_role = get_or_create_role("user", level=6)

        user = User(
            public_id=str(uuid.uuid4()),
            username=f"customer_{uuid.uuid4().hex[:8]}",
            email=f"customer_{uuid.uuid4().hex[:8]}@example.com",
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
                full_name="Test Customer",
                profile_completed=False,
            )
        )
        db.session.commit()
        # Return a lightweight ref holding only scalar, pre-loaded attributes.
        yield SimpleNamespace(
            public_id=user.public_id,
            id=user.id,
            email=user.email,
            username=user.username,
        )


@pytest.fixture
def completed_profile_user(app, verified_user):
    """A verified user whose profile is already completed."""
    with app.app_context():
        profile = get_profile_by_user(verified_user.public_id)
        profile.profile_completed = True
        profile.full_name = "Test Customer"
        profile.city = "Kampala"
        profile.country = "UG"
        db.session.commit()
    yield verified_user


def _session_login(client, user):
    with client.session_transaction() as sess:
        sess["_user_id"] = user.public_id
        sess["_fresh"] = True


def _fresh_get(client, url, **kwargs):
    """GET that clears the Flask-Caching user cache first."""
    from app.extensions import cache
    try:
        cache.clear()
    except Exception:
        pass
    return client.get(url, **kwargs)


def _post_form(client, url, data=None, **kwargs):
    """POST with real form data, clearing the Flask-Caching user cache first
    (mirrors the stage-4 helper so the user_loader never returns a stale
    detached instance from a previous request's session scope)."""
    from app.extensions import cache
    try:
        cache.clear()
    except Exception:
        pass
    return client.post(url, data=data, **kwargs)


def _make_kyc_verified(app, user):
    """Approve identity verification for *user* so is_fully_verified() is True.

    can_host() — the runtime gate that makes the accommodation_host context
    eligible for switch_context — reads IndividualVerification records, NOT
    UserProfile.verification_status. Completion tests therefore create an
    approved IndividualVerification row, mirroring the owner/admin approval
    path (app/admin/owner/routes.py) that makes a host context available.
    """
    from app.identity.individuals.individual_verification import IndividualVerification

    with app.app_context():
        db.session.add(
            IndividualVerification(
                user_id=user.id,
                status="verified",
                scope={"identity": True, "address": True},
            )
        )
        db.session.commit()


@pytest.fixture
def client(app):
    """Fresh client per test — avoids cross-test session leakage from
    the session-scoped conftest client."""
    return app.test_client()


class TestVerifiedUserNormalCustomer:
    """A verified User is immediately a normal customer."""

    def test_real_login_lands_on_user_dashboard(self, client, verified_user):
        """POST /login for a verified user redirects to /user/dashboard."""
        response = client.post(
            "/login",
            data={"username": verified_user.email, "password": "TestPassword123!"},
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert "/user/dashboard" in response.headers["Location"]

    def test_user_dashboard_reachable_without_partner_onboarding(self, client, verified_user):
        """A user who never enters the partner gate can open /user/dashboard."""
        _session_login(client, verified_user)
        response = client.get("/user/dashboard")
        assert response.status_code == 200
        assert b"Become a Partner" in response.data

    def test_dashboard_partner_cta_points_to_onboarding(self, client, verified_user):
        """The dashboard partner CTA leads to /onboarding (the canonical gate)."""
        _session_login(client, verified_user)
        response = client.get("/user/dashboard")
        assert response.status_code == 200
        assert b'href="/onboarding/choose"' in response.data

    def test_dashboard_partner_card_does_not_skip_gate(self, client, verified_user):
        """The dashboard partner card must NOT bypass the gate into the
        individual chooser — /onboarding is the canonical entry."""
        _session_login(client, verified_user)
        response = client.get("/user/dashboard")
        assert response.status_code == 200
        assert b"/onboarding/choose/individual" not in response.data


class TestPartnerGate:
    """/onboarding is the canonical partner entry, not an account-creation gate."""

    def test_partner_gate_requires_login(self, client):
        response = client.get("/onboarding/choose")
        assert response.status_code == 302
        assert "login" in response.headers["Location"].lower()

    def test_partner_gate_shows_two_paths(self, client, verified_user):
        """Updated to match current choose.html copy (frozen architecture):
        heading is 'Do More with AFCON 360', partner cards are labelled
        'Individual' and 'Organisation'. The older 'Become a Partner' /
        'Individual Partner' copy was replaced during the template redesign."""
        _session_login(client, verified_user)
        response = client.get("/onboarding/choose")
        assert response.status_code == 200
        assert b"Do More" in response.data
        assert b"Individual" in response.data
        assert b"Organisation" in response.data

    def test_partner_gate_copy_is_partner_not_account_creation(self, client, verified_user):
        """The gate must not imply the user is creating a new personal account.
        Updated: current choose.html says 'One account. Many possibilities.'
        instead of the older 'You already have an AFCON 360 account'."""
        _session_login(client, verified_user)
        response = client.get("/onboarding/choose")
        assert response.status_code == 200
        assert b"Create your account" not in response.data
        assert b"One account" in response.data

    def test_partner_gate_accessible_after_profile_completed(self, client, app, verified_user):
        """An already-onboarded user must still reach the gate (no redirect
        back to the dashboard) so more capabilities can be added.
        Updated: current choose.html heading is 'Do More with AFCON 360'."""
        with app.app_context():
            profile = get_profile_by_user(verified_user.public_id)
            profile.profile_completed = True
            db.session.commit()

        _session_login(client, verified_user)
        response = client.get("/onboarding/choose")
        assert response.status_code == 200
        assert b"Do More" in response.data


class TestIndividualPaths:
    """The individual capability chooser."""

    def test_individual_chooser_shows_partner_capabilities(self, client, verified_user):
        _session_login(client, verified_user)
        response = client.get("/onboarding/choose/individual")
        assert response.status_code == 200
        assert b"You already have your AFCON 360 account" in response.data
        assert b"Driver" in response.data
        assert b"Accommodation Host" in response.data
        assert b"Event Organiser" in response.data

    def test_standard_account_not_presented_as_capability(self, client, verified_user):
        """'Standard Account' must not appear as a partner capability."""
        _session_login(client, verified_user)
        response = client.get("/onboarding/choose/individual")
        assert response.status_code == 200
        assert b"Standard Account" not in response.data

    def test_fan_copy_removed_from_individual_chooser(self, client, verified_user):
        """Stale 'Start as a Fan' language must be gone."""
        _session_login(client, verified_user)
        response = client.get("/onboarding/choose/individual")
        assert response.status_code == 200
        assert b"Start as a Fan" not in response.data

    def test_driver_path_reachable(self, client, verified_user):
        _session_login(client, verified_user)
        response = client.get("/onboarding/driver")
        assert response.status_code == 200

    def test_host_path_reachable(self, client, verified_user):
        _session_login(client, verified_user)
        response = client.get("/onboarding/host")
        assert response.status_code == 200

    def test_event_organiser_path_reachable(self, client, verified_user):
        _session_login(client, verified_user)
        response = client.get("/onboarding/event-organiser")
        assert response.status_code == 200


class TestOrganisationPaths:
    """The organisation chooser and onboarding entry."""

    def test_organisation_chooser_shows_type_selector(self, client, verified_user):
        _session_login(client, verified_user)
        response = client.get("/onboarding/choose/organisation")
        assert response.status_code == 200
        assert b"Set up your organisation" in response.data
        assert b"What kind of organisation are you?" in response.data

    def test_organisation_chooser_shows_provider_capabilities(self, client, verified_user):
        _session_login(client, verified_user)
        response = client.get("/onboarding/choose/organisation")
        assert response.status_code == 200
        assert b"What services do you want to provide?" in response.data
        assert b"Accommodation" in response.data
        assert b"Transport" in response.data
        assert b"Events" in response.data
        assert b"Tourism" in response.data
        assert b"Venue" in response.data

    def test_organisation_chooser_has_no_consumer_type(self, client, verified_user):
        _session_login(client, verified_user)
        response = client.get("/onboarding/choose/organisation")
        assert response.status_code == 200
        # Consumer is NOT an organisation type. No consumer option must appear.
        assert b"Consumer Organisation" not in response.data
        assert b'value="consumer"' not in response.data

    def test_organisation_onboarding_entry_reachable(self, client, verified_user):
        """Direct GET to /onboarding/organisation redirects to the type
        chooser when no organisation type is in the session.  This is
        correct type-first behaviour: the user must select a type before
        entering the details wizard."""
        _session_login(client, verified_user)
        response = client.get("/onboarding/organisation")
        assert response.status_code == 302
        assert "/onboarding/choose/organisation" in response.headers["Location"]


class TestAdditivePartnership:
    """Partner choices must not be mutually exclusive."""

    def test_gate_remains_accessible_after_profile_completed(self, client, completed_profile_user):
        """After completing a profile, the gate and all capability choices remain reachable.
        Updated: current choose.html uses 'Individual' (not 'Individual Partner')."""
        _session_login(client, completed_profile_user)
        response = client.get("/onboarding/choose")
        assert response.status_code == 200
        assert b"Individual" in response.data

    def test_individual_chooser_accessible_after_profile_completed(self, client, completed_profile_user):
        _session_login(client, completed_profile_user)
        response = client.get("/onboarding/choose/individual")
        assert response.status_code == 200
        assert b"Driver" in response.data
        assert b"Accommodation Host" in response.data
        assert b"Event Organiser" in response.data

    def test_organisation_chooser_accessible_after_profile_completed(self, client, completed_profile_user):
        _session_login(client, completed_profile_user)
        response = client.get("/onboarding/choose/organisation")
        assert response.status_code == 200
        assert b"What kind of organisation are you?" in response.data
        assert b"What services do you want to provide?" in response.data


class TestHostOnboardingVerifiedFields:
    """Test that verified KYC fields are preserved during host onboarding.

    Contract under test (approved architecture): onboarding extends existing
    UserProfile/KYC state instead of re-registering it. The verified profile
    is the source of truth - verified values win and are pre-filled/locked;
    missing values may be provided; unverified/editable values may be
    replaced. Valid submissions return 302 to the host dashboard.
    """

    STEP1_FIELDS = {
        "full_name": "Form Full Name",
        "national_id": "FORM-ID-001",
        "proof_of_address": "",
        "country": "UG",
    }

    def _create_verified_profile_with(self, app, user, *, full_name, country=None, id_number=None):
        """Schema-valid verified profile state (full_name is NOT NULL).

        Identity fields are set while the profile is still pending, then the
        profile is flipped to verified in a second commit so the immutable
        after-verification listener never sees a verified-field change.
        """
        with app.app_context():
            profile = get_profile_by_user(user.public_id)
            profile.full_name = full_name
            profile.verification_status = "pending"
            profile.profile_completed = False
            profile.country = country
            profile.id_type = "national_id" if id_number else None
            profile.id_number = id_number
            db.session.commit()

        with app.app_context():
            profile = get_profile_by_user(user.public_id)
            profile.verification_status = "verified"
            profile.profile_completed = True
            db.session.commit()
        return profile

    def _create_pending_profile_with(self, app, user, *, full_name=None, country=None):
        """Schema-valid unverified profile state (placeholder names allowed)."""
        with app.app_context():
            profile = get_profile_by_user(user.public_id)
            profile.full_name = full_name or "AFCON 360 User"
            profile.verification_status = "pending"
            profile.profile_completed = False
            profile.country = country
            profile.id_type = None
            profile.id_number = None
            db.session.commit()
        return profile

    def _submit_host_wizard(self, client, step1):
        """POST through the real single-step host onboarding HTTP flow."""
        r = _post_form(
            client,
            "/onboarding/host/step/1",
            data=step1,
            follow_redirects=False,
        )
        assert r.status_code == 302, (
            f"Host onboarding expected redirect (302) but got {r.status_code}"
        )
        return r

    def test_verified_full_name_is_prefilled_and_not_overwritten(self, client, verified_user, app):
        """Step 1 GET displays the canonical verified full_name; submission
        with a different name completes with 302 and preserves the value."""
        self._create_verified_profile_with(app, verified_user, full_name="Verified Host Name")
        _session_login(client, verified_user)
        _make_kyc_verified(app, verified_user)

        get_resp = _fresh_get(client, "/onboarding/host/step/1")
        assert get_resp.status_code == 200
        assert b'value="Verified Host Name"' in get_resp.data

        r2 = self._submit_host_wizard(
            client,
            {**self.STEP1_FIELDS, "full_name": "Different Full Name"},
        )
        assert r2.status_code == 302, (
            f"Expected redirect (302) but got {r2.status_code}. Host onboarding failed."
        )

        with app.app_context():
            profile = get_profile_by_user(verified_user.public_id)
            assert profile.full_name == "Verified Host Name", (
                f"Expected 'Verified Host Name' but got '{profile.full_name}'"
            )

    def test_verified_national_id_is_locked(self, client, verified_user, app):
        """A verified national id may not be replaced by onboarded form data."""
        self._create_verified_profile_with(
            app, verified_user, full_name="Verified Host Name", id_number="VERIFIED-42"
        )
        _session_login(client, verified_user)
        _make_kyc_verified(app, verified_user)

        r2 = self._submit_host_wizard(client, self.STEP1_FIELDS)
        assert r2.status_code == 302

        with app.app_context():
            profile = get_profile_by_user(verified_user.public_id)
            assert profile.id_type == "national_id"
            assert profile.id_number == "VERIFIED-42", (
                f"Expected 'VERIFIED-42' but got '{profile.id_number}'"
            )

    def test_verified_country_is_preserved_and_available(self, client, verified_user, app):
        """Host step 1 GET pre-fills the verified country; submitting a
        different country cannot overwrite the canonical value."""
        self._create_verified_profile_with(
            app, verified_user, full_name="Verified Host Name", country="UG"
        )
        _session_login(client, verified_user)
        _make_kyc_verified(app, verified_user)

        get_resp = _fresh_get(client, "/onboarding/host/step/1")
        assert get_resp.status_code == 200
        assert b'value="UG"' in get_resp.data

        r1 = _post_form(
            client,
            "/onboarding/host/step/1",
            data={**self.STEP1_FIELDS, "country": "Rwanda"},
            follow_redirects=False,
        )
        assert r1.status_code == 302

        with app.app_context():
            profile = get_profile_by_user(verified_user.public_id)
            assert profile.country == "UG", (
                f"Expected 'UG' but got '{profile.country}'"
            )

    def test_missing_full_name_can_be_requested_from_user(self, client, verified_user, app):
        """An unverified profile with only the placeholder name accepts the
        submitted real name (schema-valid placeholder, never NULL)."""
        self._create_pending_profile_with(app, verified_user, full_name="AFCON 360 User")
        _session_login(client, verified_user)

        r2 = self._submit_host_wizard(
            client,
            {**self.STEP1_FIELDS, "full_name": "New Host Name"},
        )
        assert r2.status_code == 302
        assert "kyc" in r2.headers["Location"].lower()

        with app.app_context():
            profile = get_profile_by_user(verified_user.public_id)
            assert profile.full_name == "New Host Name", (
                f"Expected 'New Host Name' but got '{profile.full_name}'"
            )

    def test_missing_country_can_be_requested(self, client, verified_user, app):
        """A missing country accepts the submitted value, normalized to ISO
        alpha-2 ('Rwanda' -> 'RW'; an empty submission never becomes 'UG')."""
        self._create_pending_profile_with(app, verified_user, full_name="Test Host")
        _session_login(client, verified_user)

        r2 = self._submit_host_wizard(
            client,
            {**self.STEP1_FIELDS, "country": "Rwanda"},
        )
        assert r2.status_code == 302
        assert "kyc" in r2.headers["Location"].lower()

        with app.app_context():
            profile = get_profile_by_user(verified_user.public_id)
            assert profile.country == "RW", (
                f"Expected 'RW' but got '{profile.country}'"
            )

    def test_unverified_profile_accepts_submitted_national_id(self, client, verified_user, app):
        """An unverified profile with no stored id accepts the submitted
        national id after validation."""
        self._create_pending_profile_with(app, verified_user, full_name="Test Host")
        _session_login(client, verified_user)

        r2 = self._submit_host_wizard(client, self.STEP1_FIELDS)
        assert r2.status_code == 302
        assert "kyc" in r2.headers["Location"].lower()

        with app.app_context():
            profile = get_profile_by_user(verified_user.public_id)
            assert profile.id_type == "national_id"
            assert profile.id_number == "FORM-ID-001"
            assert profile.profile_completed is True

    def test_attempting_to_change_verified_full_name_preserves_it(self, client, verified_user, app):
        """Attempting to alter a verified full_name through onboarding leaves
        the canonical value untouched and still completes successfully."""
        self._create_verified_profile_with(app, verified_user, full_name="Verified Host Name")
        _session_login(client, verified_user)
        _make_kyc_verified(app, verified_user)

        r2 = self._submit_host_wizard(
            client,
            {**self.STEP1_FIELDS, "full_name": "Different Full Name"},
        )
        assert r2.status_code == 302

        with app.app_context():
            profile = get_profile_by_user(verified_user.public_id)
            assert profile.full_name == "Verified Host Name", (
                f"Verified full_name should be preserved, got '{profile.full_name}'"
            )

    def test_host_onboarding_commits_successfully_with_verified_full_name_preserved(self, client, verified_user, app):
        """A verified profile completes host onboarding with a redirect to the
        host dashboard; verified fields are preserved."""
        self._create_verified_profile_with(app, verified_user, full_name="Verified Host Name")
        _session_login(client, verified_user)
        _make_kyc_verified(app, verified_user)

        r2 = self._submit_host_wizard(
            client,
            {**self.STEP1_FIELDS, "full_name": "Different Full Name"},
        )
        assert r2.status_code == 302
        assert "host" in r2.headers["Location"].lower()

        with app.app_context():
            profile = get_profile_by_user(verified_user.public_id)
            assert profile.full_name == "Verified Host Name"
            assert profile.profile_completed is True


def test_unverified_host_onboarding_is_routed_to_kyc_gate(app, client, verified_user):
    """The KYC gate: an individual who is not is_fully_verified() may save
    their host profile and provider intention, but is routed to the KYC
    document flow instead of the host dashboard. The accommodation capability
    stays at INTENT (activation is gated on identity verification), because
    switch_context to the accommodation_host context requires
    AccommodationIdentityService.can_host == True (which demands
    is_fully_verified())."""
    from app.identity.services.provider_participation_service import (
        get_individual_intention,
    )
    from app.identity.models.organisation_provider_capability import (
        ProviderCapabilityCode,
        ProviderCapabilityStatus,
    )

    _session_login(client, verified_user)

    r1 = _post_form(
        client,
        "/onboarding/host/step/1",
        data={
            "full_name": "Test Host",
            "national_id": "ID123456",
            "proof_of_address": "Some address",
            "country": "UG",
        },
        follow_redirects=False,
    )
    assert r1.status_code == 302
    assert "kyc" in r1.headers["Location"].lower()
    assert "host" not in r1.headers["Location"].lower()

    with app.app_context():
        profile = get_profile_by_user(verified_user.public_id)
        assert profile.profile_completed is True
        assert profile.full_name == "Test Customer"

        participation = get_individual_intention(
            verified_user.id, ProviderCapabilityCode.ACCOMMODATION.value
        )
        assert participation is not None, (
            "Host onboarding must record the accommodation provider intention "
            "even when KYC is not yet verified."
        )
        assert str(participation.status) == ProviderCapabilityStatus.INTENT.value, (
            f"Accommodation capability must stay at INTENT while KYC is "
            f"unverified; got '{participation.status}'"
        )