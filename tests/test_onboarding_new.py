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


@pytest.fixture
def client(app):
    """Fresh client per test â€” avoids cross-test session leakage from
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
        individual chooser â€” /onboarding is the canonical entry."""
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
    """Test that verified KYC fields are preserved during host onboarding."""

    def _create_pending_profile_with_full_name(self, app, user, full_name):
        """Helper to create a profile in pending status with a full_name."""
        with app.app_context():
            profile = get_profile_by_user(user.public_id)
            profile.full_name = full_name
            profile.verification_status = "pending"
            profile.profile_completed = False
            db.session.commit()
        return profile

    def _verify_profile(self, app, user):
        """Helper to mark profile as verified."""
        with app.app_context():
            profile = get_profile_by_user(user.public_id)
            profile.verification_status = "verified"
            profile.profile_completed = True
            db.session.commit()

    def test_verified_full_name_is_prefilled_and_not_overwritten(self, client, verified_user, app):
        """When a user has a verified full_name in their profile, host onboarding step 1
        must display/prefill it and NOT modify it on submission."""
        # Step 1: Create profile in pending status and set full_name (simulates initial onboarding)
        self._create_pending_profile_with_full_name(app, verified_user, "Verified Host Name")
        # Step 2: Mark profile as verified (simulates KYC completion)
        self._verify_profile(app, verified_user)

        _session_login(client, verified_user)

        # Step 3: Submit host onboarding step 1 with a different full_name
        with client.session_transaction() as sess:
            sess["host_onboarding"] = {
                "step1": {
                    "full_name": "Different Full Name",
                    "national_id": "ID123456",
                    "proof_of_address": "Some address",
                }
            }

        # Submit step 1
        response = client.post("/onboarding/host/step/1", follow_redirects=False)
        assert response.status_code in (302, 200)

        # Step 4: Submit host onboarding step 2
        with client.session_transaction() as sess:
            sess["host_onboarding"] = {
                "step1": {
                    "full_name": "Different Full Name",
                    "national_id": "ID123456",
                    "proof_of_address": "Some address",
                },
                "step2": {
                    "property_name": "Test Property",
                    "description": "A test property",
                    "address": "123 Test St",
                    "city": "Kampala",
                    "country": "UG",
                    "property_type": "house",
                    "number_of_rooms": "2",
                },
            }

        response = client.post("/onboarding/host/step/2", follow_redirects=False)

        # Verify the verified full_name was NOT changed
        with app.app_context():
            profile = get_profile_by_user(verified_user.public_id)
            # The verified full_name should remain unchanged
            assert profile.full_name == "Verified Host Name", (
                f"Expected 'Verified Host Name' but got '{profile.full_name}'"
            )

    def test_verified_country_is_preserved_and_available(self, client, verified_user, app):
        """When a user has a verified country in their profile, host onboarding step 2
        must use the canonical country value and not overwrite it."""
        # Step 1: Create profile in pending status with country
        with app.app_context():
            profile = get_profile_by_user(verified_user.public_id)
            profile.country = "UG"
            profile.verification_status = "pending"
            profile.profile_completed = False
            db.session.commit()

        # Step 2: Mark profile as verified
        with app.app_context():
            profile = get_profile_by_user(verified_user.public_id)
            profile.verification_status = "verified"
            profile.profile_completed = True
            db.session.commit()

        _session_login(client, verified_user)

        # Submit host onboarding with a different country
        with client.session_transaction() as sess:
            sess["host_onboarding"] = {
                "step1": {
                    "full_name": "Test Host",
                    "national_id": "ID123456",
                    "proof_of_address": "Some address",
                },
                "step2": {
                    "property_name": "Test Property",
                    "description": "A test property",
                    "address": "123 Test St",
                    "city": "Kampala",
                    # Submitting "Rwanda" even though profile has "UG" verified
                    "country": "Rwanda",
                    "property_type": "house",
                    "number_of_rooms": "2",
                },
            }

        response = client.post("/onboarding/host/step/2", follow_redirects=False)

        # Verify the verified country was NOT changed
        with app.app_context():
            profile = get_profile_by_user(verified_user.public_id)
            # The verified country should remain "UG" (canonical)
            assert profile.country == "UG", (
                f"Expected 'UG' but got '{profile.country}'"
            )

    def test_missing_full_name_can_be_requested_from_user(self, client, verified_user, app):
        """When full_name is NULL/missing from verified profile, onboarding
        should allow the user to provide it."""
        # Step 1: Create profile in pending status WITHOUT full_name (NULL)
        with app.app_context():
            profile = get_profile_by_user(verified_user.public_id)
            profile.full_name = None
            profile.verification_status = "pending"
            profile.profile_completed = False
            db.session.commit()

        _session_login(client, verified_user)

        # Step 2: Submit host onboarding step 1 with a new full_name
        with client.session_transaction() as sess:
            sess["host_onboarding"] = {
                "step1": {
                    "full_name": "New Host Name",
                    "national_id": "ID123456",
                    "proof_of_address": "Some address",
                }
            }

        response = client.post("/onboarding/host/step/1", follow_redirects=False)
        assert response.status_code in (302, 200)

        # Step 3: Submit step 2
        with client.session_transaction() as sess:
            sess["host_onboarding"] = {
                "step1": {
                    "full_name": "New Host Name",
                    "national_id": "ID123456",
                    "proof_of_address": "Some address",
                },
                "step2": {
                    "property_name": "Test Property",
                    "description": "A test property",
                    "address": "123 Test St",
                    "city": "Kampala",
                    "country": "UG",
                    "property_type": "house",
                    "number_of_rooms": "2",
                },
            }

        response = client.post("/onboarding/host/step/2", follow_redirects=False)

        # Verify the new full_name was set (since it was previously NULL)
        with app.app_context():
            profile = get_profile_by_user(verified_user.public_id)
            assert profile.full_name == "New Host Name", (
                f"Expected 'New Host Name' but got '{profile.full_name}'"
            )

    def test_missing_country_can_be_requested(self, client, verified_user, app):
        """When country is NULL/missing from verified profile, onboarding
        should allow the user to provide it."""
        # Step 1: Create profile in pending status WITHOUT country
        with app.app_context():
            profile = get_profile_by_user(verified_user.public_id)
            profile.country = None
            profile.verification_status = "pending"
            profile.profile_completed = False
            db.session.commit()

        _session_login(client, verified_user)

        # Step 2: Submit host onboarding with a country
        with client.session_transaction() as sess:
            sess["host_onboarding"] = {
                "step1": {
                    "full_name": "Test Host",
                    "national_id": "ID123456",
                    "proof_of_address": "Some address",
                },
                "step2": {
                    "property_name": "Test Property",
                    "description": "A test property",
                    "address": "123 Test St",
                    "city": "Kampala",
                    "country": "Rwanda",
                    "property_type": "house",
                    "number_of_rooms": "2",
                },
            }

        response = client.post("/onboarding/host/step/2", follow_redirects=False)

        # Verify the country was set (since it was previously NULL)
        with app.app_context():
            profile = get_profile_by_user(verified_user.public_id)
            assert profile.country == "Rwanda", (
                f"Expected 'Rwanda' but got '{profile.country}'"
            )

    def test_attempting_to_change_verified_full_name_remains_preserved(self, client, verified_user, app):
        """Attempting to submit host onboarding with a different full_name
        when the profile already has a verified full_name should preserve
        the verified value - it should not be changed."""
        # Step 1: Create profile in pending status with full_name
        self._create_pending_profile_with_full_name(app, verified_user, "Verified Host Name")
        # Step 2: Mark profile as verified
        self._verify_profile(app, verified_user)

        _session_login(client, verified_user)

        # Step 3: Submit host onboarding with a different full_name
        with client.session_transaction() as sess:
            sess["host_onboarding"] = {
                "step1": {
                    "full_name": "Different Full Name",
                    "national_id": "ID123456",
                    "proof_of_address": "Some address",
                },
                "step2": {
                    "property_name": "Test Property",
                    "description": "A test property",
                    "address": "123 Test St",
                    "city": "Kampala",
                    "country": "UG",
                    "property_type": "house",
                    "number_of_rooms": "2",
                },
            }

        # This should NOT modify the verified full_name
        response = client.post("/onboarding/host/step/2", follow_redirects=False)

        # Verify the verified full_name was preserved (not changed)
        with app.app_context():
            profile = get_profile_by_user(verified_user.public_id)
            assert profile.full_name == "Verified Host Name", (
                f"Verified full_name should be preserved, got '{profile.full_name}'"
            )

    def test_host_onboarding_commits_successfully_with_verified_full_name_preserved(self, client, verified_user, app):
        """Host onboarding should commit successfully without errors when
        the verified full_name is preserved."""
        # Step 1: Create profile in pending status with full_name
        self._create_pending_profile_with_full_name(app, verified_user, "Verified Host Name")
        # Step 2: Mark profile as verified
        self._verify_profile(app, verified_user)

        _session_login(client, verified_user)

        # Step 3: Submit host onboarding with a different full_name
        with client.session_transaction() as sess:
            sess["host_onboarding"] = {
                "step1": {
                    "full_name": "Different Full Name",
                    "national_id": "ID123456",
                    "proof_of_address": "Some address",
                },
                "step2": {
                    "property_name": "Test Property",
                    "description": "A test property",
                    "address": "123 Test St",
                    "city": "Kampala",
                    "country": "UG",
                    "property_type": "house",
                    "number_of_rooms": "2",
                },
            }

        response = client.post("/onboarding/host/step/2", follow_redirects=False)

        # Should complete successfully (verified full_name preserved, not overwritten)
        assert response.status_code == 302, (
            f"Expected redirect (302) but got {response.status_code}. "
            "Host onboarding failed."
        )

        # Verify success message
        assert b"Property listed successfully" in response.data or b"success" in response.data

    def test_host_onboarding_no_longer_creates_property(self, client, verified_user, app):
        """Host onboarding completes the provider profile WITHOUT creating a
        Property record. Property creation is owned by the Accommodation
        domain via the dashboard 'Add Listing' flow (host_create_listing →
        HostService.create_property), not by the onboarding side effect."""
        from app.accommodation.models.property import Property

        _session_login(client, verified_user)

        with client.session_transaction() as sess:
            sess["host_onboarding"] = {
                "step1": {
                    "full_name": "Test Host",
                    "national_id": "ID123456",
                    "proof_of_address": "Some address",
                },
                "step2": {
                    "property_name": "Test Property",
                    "description": "A test property",
                    "address": "123 Test St",
                    "city": "Kampala",
                    "country": "UG",
                    "property_type": "house",
                    "number_of_rooms": "2",
                },
            }

        response = client.post("/onboarding/host/step/2", follow_redirects=False)

        assert response.status_code == 302, (
            f"Expected redirect (302) but got {response.status_code}. "
            "Host onboarding failed."
        )

        with app.app_context():
            profile = get_profile_by_user(verified_user.public_id)
            # Profile intent is recorded, but no domain resource is created.
            assert profile.profile_completed is True

            prop_count = Property.query.filter_by(owner_user_id=verified_user.id).count()
            assert prop_count == 0, (
                f"Host onboarding must not create a Property; found {prop_count} "
                "owned by the user. Use the accommodation dashboard 'Add Listing' "
                "flow (host_create_listing) instead."
            )

    def test_host_onboarding_legacy_create_property_flag_still_works(self, app, verified_user):
        """Back-compat: explicitly passing save_as_intent_only=False preserves
        the legacy onboarding Property-creation side effect. The default
        remains intent-only, so this must only happen on explicit opt-in."""
        from app.auth.onboarding_routes import _commit_host_onboarding
        from app.accommodation.models.property import Property
        from app.identity.models.user import User

        data = {
            "step1": {
                "full_name": "Legacy Host",
                "national_id": "ID123456",
                "proof_of_address": "Some address",
            },
            "step2": {
                "property_name": "Legacy Property",
                "description": "A legacy test property",
                "address": "123 Test St",
                "city": "Kampala",
                "country": "UG",
                "property_type": "house",
                "number_of_rooms": "2",
            },
        }

        with app.app_context():
            user = db.session.get(User, verified_user.id)
            _commit_host_onboarding(user, data, save_as_intent_only=False)

            prop = Property.query.filter_by(owner_user_id=verified_user.id).first()
            assert prop is not None, (
                "Legacy save_as_intent_only=False must create a Property"
            )
            assert prop.title == "Legacy Property"
            assert prop.city == "Kampala"
