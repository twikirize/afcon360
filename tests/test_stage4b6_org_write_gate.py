"""
Stage 4B-6 / G-1 tests: organisation operational write gate.

An organisation-owned Property may be created ONLY when BOTH conditions hold:

  1) Accommodation domain eligibility:
     AccommodationIdentityService.can_org_host(organisation_id) == True
  2) Provider capability:
     is_capability_operational("organisation", org_id, ACCOMMODATION) == True
     (ProviderParticipation status == ACTIVATED)

The gate is enforced at two layers (defense in depth):
  * written PROTECTION  -> HostService.create_property(owner_org_id=...) raises
    unless both gates pass (the actual persistence boundary, Stage 4B-6).
  * route gate          -> accommodation.host_create_listing organisation
    branch mirrors the established individual two-gate pattern.

Covers:
  * eligible + ACTIVATED        -> Property creation succeeds
  * eligible + INTENT           -> rejected; no Property created
  * eligible + DEACTIVATED      -> rejected; no Property created
  * eligible + SUSPENDED        -> rejected; no Property created
  * eligible + REVOKED          -> rejected; no Property created
  * ineligible + ACTIVATED      -> rejected; no Property created
  * eligible + no PP row        -> rejected; no Property created
  * activate -> create ; deactivate -> create rejected (real lifecycle)
  * cross-organisation authority: actor of Org A cannot act for Org B
  * route-level organisation branch enforces the two-gate before create_property

Run: pytest tests/test_stage4b6_org_write_gate.py -v
"""

import json
import uuid
from types import SimpleNamespace

import pytest

from app.extensions import db
from app.accommodation.services.host_service import HostService
from app.accommodation.services.identity_service import AccommodationIdentityService
from app.identity.models.organisation import Organisation
from app.identity.models.organisation_member import (
    OrganisationMember,
    OrgRole,
    OrgUserRole,
)
from app.identity.models.organisation_provider_capability import (
    ProviderCapabilityCode,
    ProviderCapabilityStatus,
)
from app.identity.models.organization_types import OrganizationType
from app.identity.models.provider_participation import ProviderParticipation
from app.identity.models.roles_permission import get_or_create_role
from app.identity.models.user import User, UserRole
from app.profile.models import UserProfile


# ---------------------------------------------------------------------------
# Fixtures (service-level tests may use db_session; route-level tests must NOT)
# ---------------------------------------------------------------------------

def _make_user(session, *, owner=False):
    user = User(
        public_id=str(uuid.uuid4()),
        username=f"u_{uuid.uuid4().hex[:8]}",
        email=f"u_{uuid.uuid4().hex[:8]}@example.com",
    )
    user.set_password("TestPassword123!")
    user.is_active = True
    user.is_verified = True
    user.email_verified = True
    session.add(user)
    session.flush()

    role_name, level = ("owner", 1) if owner else ("user", 6)
    role = get_or_create_role(role_name, level=level)
    session.add(UserRole(user_id=user.id, role_id=role.id))
    # Owner bypasses the KYC/profile eligibility gates (can_host True);
    # the plain user has no verification record -> can_host False.
    session.add(
        UserProfile(
            user_id=user.public_id,
            full_name="Test User",
            profile_completed=owner,
        )
    )
    session.flush()
    return SimpleNamespace(
        id=user.id,
        public_id=user.public_id,
        username=user.username,
        email=user.email,
    )


def _make_org(session, *, org_type, verification_status="verified", is_operational=True, is_active=True):
    """Fully-gated Organisation row for the given canonical type.

    ``org_type`` must be an ``OrganizationType`` member so SQLAlchemy adapts
    it to the PostgreSQL ``org_business_category`` enum (member name labels)."""
    org = Organisation(
        org_id=f"org_{uuid.uuid4().hex[:10]}",
        legal_name=f"Org {uuid.uuid4().hex[:8]}",
        country="UG",
        business_category=org_type,
        verification_status=verification_status,
        lifecycle_state="registered",
        is_active=is_active,
        is_operational=is_operational,
    )
    session.add(org)
    session.flush()
    return org


def _assign_org_role(session, user, org, role_name):
    from app.identity.services.organisation_role_provisioning import (
        provision_organisation_roles,
    )
    provision_organisation_roles(org, commit=False)
    session.flush()

    membership = OrganisationMember(
        user_id=user.id,
        organisation_id=org.id,
        is_active=True,
    )
    session.add(membership)
    session.flush()

    org_role = OrgRole.query.filter_by(
        organisation_id=org.id,
        name=role_name,
    ).first()
    assert org_role is not None

    session.add(
        OrgUserRole(
            organisation_member_id=membership.id,
            role_id=org_role.id,
            assigned_by=user.id,
        )
    )
    session.flush()
    return membership


def _seed_org_pp(session, org_id, status):
    """Insert an org provider-participation row (user_id=NULL subject)."""
    row = ProviderParticipation(
        user_id=None,
        organisation_id=org_id,
        capability_code=ProviderCapabilityCode.ACCOMMODATION.value,
        status=status,
    )
    session.add(row)
    session.flush()
    return row


def _force_org_pp_status(session, org_id, status):
    row = (
        ProviderParticipation.query.filter_by(
            organisation_id=org_id,
            user_id=None,
            capability_code=ProviderCapabilityCode.ACCOMMODATION.value,
            is_deleted=False,
        )
        .first()
    )
    if row is None:
        raise AssertionError("organisation participation row must be seeded first")
    row.status = status
    session.flush()
    return row


def _property_data(suffix=None):
    suffix = suffix or uuid.uuid4().hex[:6]
    return {
        "title": f"Stage 4B-6 Org Suite {suffix}",
        "summary": "Organisation-owned property",
        "description": "Used to prove the G-1 operational write gate",
        "property_type": "hotel",
        "listing_type": "private_room",
        "address_line1": "Nakasero Hill Road",
        "address_line2": "",
        "city": "Kampala",
        "state": "",
        "country": "UG",
        "postal_code": "",
        "max_guests": 4,
        "bedrooms": 2,
        "beds": 3,
        "bathrooms": 2.0,
        "base_price_per_night": 150.00,
        "currency": "USD",
        "cleaning_fee": 30.00,
        "service_fee_pct": 10.00,
        "min_stay_nights": 1,
        "max_stay_nights": None,
        "cancellation_policy": "moderate",
        "check_in_time": "14:00",
        "check_out_time": "11:00",
        "instant_book": True,
        "allow_pets": False,
        "allow_smoking": False,
        "allow_events": False,
        "house_rules": None,
        "main_image": "",
        "gallery_urls": "",
        "meta_title": "",
        "meta_description": "",
    }


def _org_property_count(org_id):
    from app.accommodation.models.property import Property
    return Property.query.filter(
        Property.owner_org_id == org_id,
        Property.is_deleted.is_(False),
    ).count()


# ---------------------------------------------------------------------------
# 1. Write-boundary two-gate on HostService.create_property
# ---------------------------------------------------------------------------

class TestServiceWriteBoundaryGate:

    def test_eligible_activated_allows_creation(self, db_session):
        org = _make_org(db_session, org_type=OrganizationType.HOTEL)
        _seed_org_pp(db_session, org.id, ProviderCapabilityStatus.ACTIVATED.value)

        prop = HostService.create_property(
            _property_data(), owner_user_id=None, owner_org_id=org.id,
        )
        db_session.flush()

        assert prop.id is not None
        assert prop.owner_org_id == org.id
        assert prop.owner_user_id is None
        assert _org_property_count(org.id) == 1

    def test_eligible_intent_blocked(self, db_session):
        org = _make_org(db_session, org_type=OrganizationType.HOTEL)
        _seed_org_pp(db_session, org.id, ProviderCapabilityStatus.INTENT.value)

        with pytest.raises(ValueError):
            HostService.create_property(
                _property_data(), owner_user_id=None, owner_org_id=org.id,
            )
        assert _org_property_count(org.id) == 0

    def test_eligible_deactivated_blocked(self, db_session):
        org = _make_org(db_session, org_type=OrganizationType.HOTEL)
        _seed_org_pp(db_session, org.id, ProviderCapabilityStatus.DEACTIVATED.value)

        with pytest.raises(ValueError):
            HostService.create_property(
                _property_data(), owner_user_id=None, owner_org_id=org.id,
            )
        assert _org_property_count(org.id) == 0

    def test_eligible_suspended_blocked(self, db_session):
        org = _make_org(db_session, org_type=OrganizationType.HOTEL)
        _seed_org_pp(db_session, org.id, ProviderCapabilityStatus.SUSPENDED.value)

        with pytest.raises(ValueError):
            HostService.create_property(
                _property_data(), owner_user_id=None, owner_org_id=org.id,
            )
        assert _org_property_count(org.id) == 0

    def test_eligible_revoked_blocked(self, db_session):
        org = _make_org(db_session, org_type=OrganizationType.HOTEL)
        _seed_org_pp(db_session, org.id, ProviderCapabilityStatus.REVOKED.value)

        with pytest.raises(ValueError):
            HostService.create_property(
                _property_data(), owner_user_id=None, owner_org_id=org.id,
            )
        assert _org_property_count(org.id) == 0

    def test_ineligible_activated_blocked(self, db_session):
        # RESTAURANT has can_manage_accommodation=False in the canonical mapping.
        org = _make_org(db_session, org_type=OrganizationType.RESTAURANT)
        _seed_org_pp(db_session, org.id, ProviderCapabilityStatus.ACTIVATED.value)

        with pytest.raises(ValueError) as exc:
            HostService.create_property(
                _property_data(), owner_user_id=None, owner_org_id=org.id,
            )
        assert "not eligible" in str(exc.value)
        assert _org_property_count(org.id) == 0

    def test_eligible_no_pp_row_blocked(self, db_session):
        org = _make_org(db_session, org_type=OrganizationType.HOTEL)

        with pytest.raises(ValueError) as exc:
            HostService.create_property(
                _property_data(), owner_user_id=None, owner_org_id=org.id,
            )
        assert "not activated" in str(exc.value)
        assert _org_property_count(org.id) == 0

    def test_activation_then_deactivation_toggle(self, db_session):
        # Real organisation lifecycle drives the write gate.
        from app.identity.services.provider_participation_service import (
            activate_organisation_intention,
            create_organisation_intention,
            deactivate_organisation_intention,
        )
        owner = _make_user(db_session, owner=True)
        org = _make_org(db_session, org_type=OrganizationType.HOTEL)
        _assign_org_role(db_session, owner, org, "org_owner")
        user = db.session.get(User, owner.id)

        row = create_organisation_intention(user, org.id, ProviderCapabilityCode.ACCOMMODATION.value)
        assert str(row.status) == ProviderCapabilityStatus.INTENT.value

        activate_organisation_intention(user, org.id, ProviderCapabilityCode.ACCOMMODATION.value)
        db_session.flush()
        prop = HostService.create_property(
            _property_data(), owner_user_id=None, owner_org_id=org.id,
        )
        db_session.flush()
        assert prop.id is not None
        assert _org_property_count(org.id) == 1

        deactivate_organisation_intention(user, org.id, ProviderCapabilityCode.ACCOMMODATION.value)
        db_session.flush()
        with pytest.raises(ValueError):
            HostService.create_property(
                _property_data(), owner_user_id=None, owner_org_id=org.id,
            )
        assert _org_property_count(org.id) == 1


# ---------------------------------------------------------------------------
# 2. Cross-organisation authority (actor of Org A cannot act for Org B)
# ---------------------------------------------------------------------------

class TestCrossOrganisationAuthority:

    def test_get_host_identity_denies_foreign_org(self, db_session):
        """Actor who belongs only to Org A must resolve as 'individual' for
        Org B, so the organisation write path can never target Org B."""
        user = _make_user(db_session, owner=False)
        org_a = _make_org(db_session, org_type=OrganizationType.HOTEL)
        org_b = _make_org(db_session, org_type=OrganizationType.HOTEL)
        _assign_org_role(db_session, user, org_a, "org_owner")
        real_user = db.session.get(User, user.id)

        identity_b = AccommodationIdentityService.get_host_identity(
            real_user, org_id=org_b.id,
        )
        assert identity_b["type"] == "individual"
        assert identity_b["id"] == real_user.id

        # Actor cannot manage a property owned by Org B…
        assert AccommodationIdentityService.can_manage_property(
            real_user,
            property_owner_user_id=None,
            property_owner_org_id=org_b.id,
        ) is False
        # …but can manage Org A's properties (positive control).
        assert AccommodationIdentityService.can_manage_property(
            real_user,
            property_owner_user_id=None,
            property_owner_org_id=org_a.id,
        ) is True


# ---------------------------------------------------------------------------
# 3. Route-level organisation two-gate at host_create_listing
# ---------------------------------------------------------------------------

def _login(client, user):
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user.public_id)
        sess["_fresh"] = True


def _set_org_host_context(client, org_public_id):
    with client.session_transaction() as sess:
        sess["active_context_type"] = "accommodation_host"
        sess["active_context_id"] = str(org_public_id)
        sess["active_role"] = "accommodation_host"


@pytest.fixture
def client(app):
    """Function-scoped client — avoids cross-test session leakage."""
    return app.test_client()


@pytest.fixture
def accommodation_module_on(app):
    """Temporarily enable the accommodation module for HTTP tests."""
    from app.models.system_config import SystemConfig
    from app.utils.module_toggle_service import ModuleToggleService

    with app.app_context():
        stored = SystemConfig.query.filter_by(key="MODULE_FLAGS").first()
        prev_null = stored is None or stored.value is None
        prev = ModuleToggleService._fetch_stored_flags()

        merged = dict(prev)
        merged["accommodation"] = True
        SystemConfig.set(
            "MODULE_FLAGS", json.dumps(merged), value_type="json",
            description="Module flags", commit=True,
        )
        ModuleToggleService.load_overrides_into_app()

    yield

    with app.app_context():
        if prev_null:
            row = SystemConfig.query.filter_by(key="MODULE_FLAGS").first()
            if row is not None:
                db.session.delete(row)
                db.session.commit()
        else:
            SystemConfig.set(
                "MODULE_FLAGS", json.dumps(prev), value_type="json",
                description="Module flags", commit=True,
            )
        ModuleToggleService.load_overrides_into_app()


class TestRouteOrganisationBranch:

    @staticmethod
    def _make_org_scenario(app, pp_status):
        """Create owner actor + eligible org + membership + org PP row (committed).

        The actor is made a real ``OrganisationMember`` (org_owner) so the
        organisation resolves as a live ACCOMMODATION_HOST context, which the
        route's ``_ensure_host_identity`` requires. Returns detached plain
        values (actor, org_id, org_public_id) usable outside any session."""
        with app.app_context():
            actor = _make_user(db.session, owner=True)
            org = _make_org(db.session, org_type=OrganizationType.HOTEL)
            org_public_id = str(org.org_id)
            _assign_org_role(db.session, actor, org, "org_owner")
            _seed_org_pp(db.session, org.id, pp_status)
            db.session.commit()
            actor_out = SimpleNamespace(
                id=actor.id,
                public_id=actor.public_id,
                username=actor.username,
                email=actor.email,
            )
            return actor_out, org.id, org_public_id

    def test_org_branch_allows_eligible_activated(self, app, client, accommodation_module_on, monkeypatch):
        actor, org_id, org_public_id = self._make_org_scenario(
            app, ProviderCapabilityStatus.ACTIVATED.value,
        )

        def _fake_host_identity(user, org_id=None):
            return {
                "type": "organisation",
                "id": org_id,
                "display_name": "Fake Test Org",
                "member_role": "admin",
            }

        monkeypatch.setattr(
            AccommodationIdentityService, "get_host_identity",
            staticmethod(_fake_host_identity),
        )

        _login(client, actor)
        _set_org_host_context(client, org_public_id)

        r = client.get("/accommodation/host/listings/create")
        assert r.status_code == 200

    def test_org_branch_blocks_eligible_intent(self, app, client, accommodation_module_on, monkeypatch):
        actor, org_id, org_public_id = self._make_org_scenario(
            app, ProviderCapabilityStatus.INTENT.value,
        )

        def _fake_host_identity(user, org_id=None):
            return {
                "type": "organisation",
                "id": org_id,
                "display_name": "Fake Test Org",
                "member_role": "admin",
            }

        monkeypatch.setattr(
            AccommodationIdentityService, "get_host_identity",
            staticmethod(_fake_host_identity),
        )

        _login(client, actor)
        _set_org_host_context(client, org_public_id)

        r = client.get("/accommodation/host/listings/create", follow_redirects=False)
        assert r.status_code == 302
        assert "/host/dashboard" in r.headers["Location"]

        from app.accommodation.models.property import Property
        with app.app_context():
            assert Property.query.filter(
                Property.owner_org_id == org_id,
                Property.is_deleted.is_(False),
            ).count() == 0