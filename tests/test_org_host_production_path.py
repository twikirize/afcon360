"""
Stage 4B-6 / G-1 regression: organisation accommodation write via the UNPATCHED
production path.

The route entry gate ``_ensure_host_identity`` must resolve an organisation host
from the active ACCOMMODATION_HOST context (public org id) and pass the
organisation's INTERNAL id to ``get_host_identity(user, org_id=...)``. Without
that, ``get_host_identity`` always returns ``individual`` and the organisation
two-gate branch in ``host_create_listing`` is unreachable.

These tests exercise the REAL route + REAL service code (no monkeypatching of
``get_host_identity`` / ``_ensure_host_identity``):

  * eligible org + ACTIVATED        -> GET create reaches the form (200)
  * eligible org + ACTIVATED        -> POST create persists an org-owned Property
  * foreign org context (no member) -> 403
  * member lacking manage permission -> 403
  * eligible org + INTENT           -> 302 to dashboard; no Property created
  * ineligible org (RESTAURANT)     -> 302 to dashboard; no Property created

Run: pytest tests/test_org_host_production_path.py -v
"""

import json
import uuid
from types import SimpleNamespace

import pytest

from app.extensions import db
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
# Fixtures (route-level tests must NOT use db_session; app/client are committed)
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


def _make_org(session, *, org_type, verification_status="verified"):
    org = Organisation(
        org_id=f"org_{uuid.uuid4().hex[:10]}",
        legal_name=f"Org {uuid.uuid4().hex[:8]}",
        country="UG",
        business_category=org_type,
        verification_status=verification_status,
        lifecycle_state="registered",
        is_active=True,
        is_operational=True,
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
    row = ProviderParticipation(
        user_id=None,
        organisation_id=org_id,
        capability_code=ProviderCapabilityCode.ACCOMMODATION.value,
        status=status,
    )
    session.add(row)
    session.flush()
    return row


def _property_data(suffix=None):
    suffix = suffix or uuid.uuid4().hex[:6]
    return {
        "title": f"Stage 4B-6 Production {suffix}",
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


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def accommodation_module_on(app):
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


def _login(client, user):
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user.public_id)
        sess["_fresh"] = True


def _set_org_host_context(client, org_public_id):
    with client.session_transaction() as sess:
        sess["active_context_type"] = "accommodation_host"
        sess["active_context_id"] = str(org_public_id)
        sess["active_role"] = "accommodation_host"


class TestOrgWriteProductionPath:

    @staticmethod
    def _make_scenario(app, *, pp_status, org_type=OrganizationType.HOTEL, role="org_owner"):
        """Committed scenario: actor + org + membership + org PP row."""
        with app.app_context():
            actor = _make_user(db.session, owner=True)
            org = _make_org(db.session, org_type=org_type)
            org_public_id = str(org.org_id)
            _assign_org_role(db.session, actor, org, role)
            _seed_org_pp(db.session, org.id, pp_status)
            db.session.commit()
            return (
                SimpleNamespace(
                    id=actor.id,
                    public_id=actor.public_id,
                    username=actor.username,
                    email=actor.email,
                ),
                org.id,
                org_public_id,
            )

    @staticmethod
    def _count_org_properties(org_id):
        from app.accommodation.models.property import Property
        return Property.query.filter(
            Property.owner_org_id == org_id,
            Property.is_deleted.is_(False),
        ).count()

    def test_org_branch_reachable_get_create(self, app, client, accommodation_module_on):
        """Eligible + ACTIVATED org host reaches the create form via the real
        production path (was abort(403) before the entry-gate fix)."""
        actor, org_id, org_public_id = self._make_scenario(
            app, pp_status=ProviderCapabilityStatus.ACTIVATED.value,
        )
        _login(client, actor)
        _set_org_host_context(client, org_public_id)

        r = client.get("/accommodation/host/listings/create")
        assert r.status_code == 200

    def test_org_host_posts_property_via_real_route(self, app, client, accommodation_module_on):
        """Full write through the unpatched route: POST create persists an
        organisation-owned Property and redirects to the host dashboard."""
        actor, org_id, org_public_id = self._make_scenario(
            app, pp_status=ProviderCapabilityStatus.ACTIVATED.value,
        )
        _login(client, actor)
        _set_org_host_context(client, org_public_id)

        data = _property_data()
        r = client.post(
            "/accommodation/host/listings/create",
            data=data,
            follow_redirects=False,
        )
        assert r.status_code == 302
        assert "/host/dashboard" in r.headers["Location"]

        from app.accommodation.models.property import Property
        with app.app_context():
            created = (
                Property.query.filter(
                    Property.owner_org_id == org_id,
                    Property.is_deleted.is_(False),
                ).first()
            )
            assert created is not None
            assert created.owner_org_id == org_id
            assert created.owner_user_id is None

    def test_foreign_org_context_sanitized_to_personal(self, app, client, accommodation_module_on):
        """Actor who belongs only to Org A cannot act under Org B's context.
        get_active_context validates the session context against live
        memberships; no membership for Org B means the ACCOMMODATION_HOST
        context is not available -> sanitized to PERSONAL -> redirect."""
        with app.app_context():
            actor = _make_user(db.session, owner=True)
            org_a = _make_org(db.session, org_type=OrganizationType.HOTEL)
            org_b = _make_org(db.session, org_type=OrganizationType.HOTEL)
            _assign_org_role(db.session, actor, org_a, "org_owner")
            _seed_org_pp(db.session, org_a.id, ProviderCapabilityStatus.ACTIVATED.value)
            _seed_org_pp(db.session, org_b.id, ProviderCapabilityStatus.ACTIVATED.value)
            org_b_public = str(org_b.org_id)
            db.session.commit()
            actor_out = SimpleNamespace(
                id=actor.id, public_id=actor.public_id,
                username=actor.username, email=actor.email,
            )

        _login(client, actor_out)
        _set_org_host_context(client, org_b_public)

        r = client.get("/accommodation/host/listings/create", follow_redirects=False)
        assert r.status_code == 302
        assert r.headers["Location"] in ("/", "http://localhost/")

    def test_member_without_manage_permission_rejected(self, app, client, accommodation_module_on):
        """org_admin lacks org.accommodation.manage; identity falls back to
        'individual' under the org context -> entry gate aborts 403."""
        actor, org_id, org_public_id = self._make_scenario(
            app, pp_status=ProviderCapabilityStatus.ACTIVATED.value,
            role="org_admin",
        )
        _login(client, actor)
        _set_org_host_context(client, org_public_id)

        r = client.get("/accommodation/host/listings/create")
        assert r.status_code == 403

    def test_intent_capability_redirects_and_persists_nothing(
        self, app, client, accommodation_module_on,
    ):
        """Eligible org with INTENT capability: two-gate blocks at the route,
        no Property row is written."""
        actor, org_id, org_public_id = self._make_scenario(
            app, pp_status=ProviderCapabilityStatus.INTENT.value,
        )
        _login(client, actor)
        _set_org_host_context(client, org_public_id)

        r = client.get("/accommodation/host/listings/create", follow_redirects=False)
        assert r.status_code == 302
        assert "/host/dashboard" in r.headers["Location"]

        with app.app_context():
            assert self._count_org_properties(org_id) == 0

    def test_ineligible_org_type_context_not_available(
        self, app, client, accommodation_module_on,
    ):
        """RESTAURANT is not accommodation-eligible; can_org_host returns
        False so the ACCOMMODATION_HOST context is never offered -> context
        sanitizes to PERSONAL -> redirect."""
        actor, org_id, org_public_id = self._make_scenario(
            app, pp_status=ProviderCapabilityStatus.ACTIVATED.value,
            org_type=OrganizationType.RESTAURANT,
        )
        _login(client, actor)
        _set_org_host_context(client, org_public_id)

        r = client.get("/accommodation/host/listings/create", follow_redirects=False)
        assert r.status_code == 302

        with app.app_context():
            assert self._count_org_properties(org_id) == 0