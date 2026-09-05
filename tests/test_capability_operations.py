"""
Stage 4B-2 tests: Capability Operations (lifecycle + authority + isolation).

Covers:
  * Lifecycle transitions (intent → activated → deactivated → re-activated,
    activated → suspended → re-activated, any → revoked)
  * Invalid transition rejection
  * Authority checks (org_owner, non-owner, org member, non-member, platform admin)
  * Capability listing
  * Organisation context respect
  * Domain-resource isolation (activating a capability creates nothing else)
  * Capability does NOT grant permissions or authority
  * HTTP API endpoints (list, activate, deactivate, suspend, revoke)
"""

import uuid

import pytest
from sqlalchemy.exc import IntegrityError

from app.identity.models import (
    Organisation,
    ProviderCapabilityCode,
    ProviderCapabilityStatus,
)
from app.identity.models.provider_participation import ProviderParticipation
from app.identity.models.organisation_member import OrganisationMember, OrgUserRole, OrgRole
from app.identity.services.capability_service import (
    CapabilityNotFoundError,
    CapabilityPermissionError,
    CapabilityTransitionError,
    activate_capability,
    deactivate_capability,
    suspend_capability,
    revoke_capability,
    list_capabilities,
    get_capability,
    capability_to_dict,
)
from app.extensions import db


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_org(session, suffix=None):
    suffix = suffix or uuid.uuid4().hex[:8]
    org = Organisation(
        legal_name=f"CapOps Org {suffix}",
        org_id=str(uuid.uuid4()),
        country="UG",
    )
    session.add(org)
    session.flush()
    return org


def _make_user(session, suffix=None):
    from app.identity.models.user import User
    suffix = suffix or uuid.uuid4().hex[:8]
    user = User(
        public_id=str(uuid.uuid4()),
        username=f"capops_{suffix}",
        email=f"capops_{suffix}@example.com",
    )
    user.set_password("TestPassword123!")
    user.is_active = True
    user.is_verified = True
    user.email_verified = True
    session.add(user)
    session.flush()
    return user


def _assign_org_role(session, user, org, role_name):
    """Ensure org roles are provisioned and assign one to the user."""
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
    assert org_role is not None, f"OrgRole '{role_name}' not found after provisioning"

    session.add(
        OrgUserRole(
            organisation_member_id=membership.id,
            role_id=org_role.id,
            assigned_by=user.id,
        )
    )
    session.flush()
    return membership


def _make_owner(session, org):
    """Create a user with org_owner role in the given org."""
    user = _make_user(session, suffix=f"owner_{uuid.uuid4().hex[:8]}")
    _assign_org_role(session, user, org, "org_owner")
    return user


def _make_member(session, org):
    """Create a user with org_member role in the given org."""
    user = _make_user(session, suffix=f"member_{uuid.uuid4().hex[:8]}")
    _assign_org_role(session, user, org, "org_member")
    return user


def _add_capability(session, org, code, status=ProviderCapabilityStatus.INTENT.value):
    """Seed an organisation capability row (PP-backed, Stage 4B-3).

    Writes a ``provider_participations`` row for the organisation so the
    capability tests now exercise the canonical participation store.
    """
    cap = ProviderParticipation(
        organisation_id=org.id,
        capability_code=code,
        status=status,
        meta={},
    )
    session.add(cap)
    session.flush()
    return cap


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True, scope="session")
def _seed_org_roles(app):
    from app.auth.seed_roles import seed_all
    with app.app_context():
        seed_all()


@pytest.fixture
def org(db_session):
    return _make_org(db_session)


@pytest.fixture
def owner_user(db_session, org):
    return _make_owner(db_session, org)


@pytest.fixture
def member_user(db_session, org):
    return _make_member(db_session, org)


@pytest.fixture
def intent_capability(db_session, org):
    return _add_capability(db_session, org, ProviderCapabilityCode.ACCOMMODATION.value)


@pytest.fixture
def activated_capability(db_session, org):
    return _add_capability(
        db_session, org,
        ProviderCapabilityCode.TRANSPORT.value,
        status=ProviderCapabilityStatus.ACTIVATED.value,
    )


# ===========================================================================
# 1. Lifecycle transitions
# ===========================================================================

class TestLifecycleTransitions:

    def test_intent_to_activated(self, owner_user, org, intent_capability):
        cap = activate_capability(owner_user, org.id, "accommodation")
        assert cap.status == ProviderCapabilityStatus.ACTIVATED.value
        assert cap.activated_at is not None

    def test_activated_to_deactivated(self, owner_user, org, activated_capability):
        cap = deactivate_capability(owner_user, org.id, "transport")
        assert cap.status == ProviderCapabilityStatus.DEACTIVATED.value

    def test_deactivated_to_activated(self, owner_user, org, activated_capability):
        deactivate_capability(owner_user, org.id, "transport")
        cap = activate_capability(owner_user, org.id, "transport")
        assert cap.status == ProviderCapabilityStatus.ACTIVATED.value

    def test_activated_to_suspended(self, owner_user, org, activated_capability):
        cap = suspend_capability(owner_user, org.id, "transport")
        assert cap.status == ProviderCapabilityStatus.SUSPENDED.value

    def test_suspended_to_activated(self, owner_user, org, activated_capability):
        suspend_capability(owner_user, org.id, "transport")
        cap = activate_capability(owner_user, org.id, "transport")
        assert cap.status == ProviderCapabilityStatus.ACTIVATED.value

    def test_activated_to_revoked(self, owner_user, org, activated_capability):
        cap = revoke_capability(owner_user, org.id, "transport")
        assert cap.status == ProviderCapabilityStatus.REVOKED.value

    def test_intent_to_deactivated(self, owner_user, org, intent_capability):
        cap = deactivate_capability(owner_user, org.id, "accommodation")
        assert cap.status == ProviderCapabilityStatus.DEACTIVATED.value

    def test_activated_at_set_on_activation(self, owner_user, org, intent_capability):
        assert intent_capability.activated_at is None
        cap = activate_capability(owner_user, org.id, "accommodation")
        assert cap.activated_at is not None

    def test_activated_at_not_cleared_on_deactivation(self, owner_user, org, activated_capability):
        original_at = activated_capability.activated_at
        cap = deactivate_capability(owner_user, org.id, "transport")
        assert cap.activated_at == original_at


# ===========================================================================
# 2. Invalid transitions
# ===========================================================================

class TestInvalidTransitions:

    def test_suspended_to_deactivated_rejected(self, owner_user, org, activated_capability):
        suspend_capability(owner_user, org.id, "transport")
        with pytest.raises(CapabilityTransitionError):
            deactivate_capability(owner_user, org.id, "transport")

    def test_revoked_to_activated_rejected(self, owner_user, org, activated_capability):
        revoke_capability(owner_user, org.id, "transport")
        with pytest.raises(CapabilityTransitionError):
            activate_capability(owner_user, org.id, "transport")

    def test_revoked_to_deactivated_rejected(self, owner_user, org, activated_capability):
        revoke_capability(owner_user, org.id, "transport")
        with pytest.raises(CapabilityTransitionError):
            deactivate_capability(owner_user, org.id, "transport")

    def test_already_revoked_rejected(self, owner_user, org, activated_capability):
        revoke_capability(owner_user, org.id, "transport")
        with pytest.raises(CapabilityTransitionError):
            revoke_capability(owner_user, org.id, "transport")

    def test_deactivated_to_suspended_rejected(self, owner_user, org, activated_capability):
        deactivate_capability(owner_user, org.id, "transport")
        with pytest.raises(CapabilityTransitionError):
            suspend_capability(owner_user, org.id, "transport")


# ===========================================================================
# 3. Authority checks
# ===========================================================================

class TestAuthority:

    def test_org_owner_can_activate(self, owner_user, org, intent_capability):
        cap = activate_capability(owner_user, org.id, "accommodation")
        assert cap.status == ProviderCapabilityStatus.ACTIVATED.value

    def test_non_owner_cannot_activate(self, member_user, org, intent_capability):
        with pytest.raises(CapabilityPermissionError):
            activate_capability(member_user, org.id, "accommodation")

    def test_non_member_cannot_activate(self, db_session, org, intent_capability):
        outsider = _make_user(db_session, suffix="outsider")
        with pytest.raises(CapabilityPermissionError):
            activate_capability(outsider, org.id, "accommodation")

    def test_org_owner_can_deactivate(self, owner_user, org, activated_capability):
        cap = deactivate_capability(owner_user, org.id, "transport")
        assert cap.status == ProviderCapabilityStatus.DEACTIVATED.value

    def test_non_owner_cannot_deactivate(self, member_user, org, activated_capability):
        with pytest.raises(CapabilityPermissionError):
            deactivate_capability(member_user, org.id, "transport")

    def test_org_owner_can_suspend(self, owner_user, org, activated_capability):
        cap = suspend_capability(owner_user, org.id, "transport")
        assert cap.status == ProviderCapabilityStatus.SUSPENDED.value

    def test_non_owner_cannot_suspend(self, member_user, org, activated_capability):
        with pytest.raises(CapabilityPermissionError):
            suspend_capability(member_user, org.id, "transport")

    def test_org_owner_can_revoke(self, owner_user, org, activated_capability):
        cap = revoke_capability(owner_user, org.id, "transport")
        assert cap.status == ProviderCapabilityStatus.REVOKED.value

    def test_non_owner_cannot_revoke(self, member_user, org, activated_capability):
        with pytest.raises(CapabilityPermissionError):
            revoke_capability(member_user, org.id, "transport")

    def test_platform_admin_can_suspend(self, db_session, org, activated_capability):
        from app.identity.models.user import User, UserRole
        from app.identity.models.roles_permission import get_or_create_role

        admin_role = get_or_create_role("super_admin", level=2)
        admin = _make_user(db_session, suffix="admin")
        db_session.add(UserRole(user_id=admin.id, role_id=admin_role.id))
        db_session.flush()

        membership = OrganisationMember(
            user_id=admin.id,
            organisation_id=org.id,
            is_active=True,
        )
        db_session.add(membership)
        db_session.flush()

        cap = suspend_capability(admin, org.id, "transport")
        assert cap.status == ProviderCapabilityStatus.SUSPENDED.value

    def test_platform_admin_can_revoke(self, db_session, org, activated_capability):
        from app.identity.models.user import User, UserRole
        from app.identity.models.roles_permission import get_or_create_role

        admin_role = get_or_create_role("super_admin", level=2)
        admin = _make_user(db_session, suffix="admrev")
        db_session.add(UserRole(user_id=admin.id, role_id=admin_role.id))
        db_session.flush()

        membership = OrganisationMember(
            user_id=admin.id,
            organisation_id=org.id,
            is_active=True,
        )
        db_session.add(membership)
        db_session.flush()

        cap = revoke_capability(admin, org.id, "transport")
        assert cap.status == ProviderCapabilityStatus.REVOKED.value


# ===========================================================================
# 4. Not-found errors
# ===========================================================================

class TestNotFound:

    def test_activate_nonexistent(self, owner_user, org):
        with pytest.raises(CapabilityNotFoundError):
            activate_capability(owner_user, org.id, "nonexistent_code")

    def test_deactivate_nonexistent(self, owner_user, org):
        with pytest.raises(CapabilityNotFoundError):
            deactivate_capability(owner_user, org.id, "nonexistent_code")


# ===========================================================================
# 5. Listing and reading
# ===========================================================================

class TestCapabilityListing:

    def test_list_empty(self, owner_user, org):
        caps = list_capabilities(org.id)
        assert caps == []

    def test_list_returns_capabilities(self, owner_user, org, intent_capability):
        caps = list_capabilities(org.id)
        assert len(caps) == 1
        assert caps[0].capability_code == "accommodation"

    def test_list_excludes_deleted(self, db_session, owner_user, org):
        cap = _add_capability(db_session, org, ProviderCapabilityCode.EVENTS.value)
        cap_id = cap.id
        db_session.flush()
        cap.soft_delete()
        db_session.flush()
        caps = list_capabilities(org.id)
        assert all(c.id != cap_id for c in caps)

    def test_get_capability_found(self, owner_user, org, intent_capability):
        cap = get_capability(org.id, "accommodation")
        assert cap is not None
        assert cap.capability_code == "accommodation"

    def test_get_capability_not_found(self, owner_user, org):
        cap = get_capability(org.id, "venue")
        assert cap is None

    def test_capability_to_dict(self, owner_user, org, intent_capability):
        d = capability_to_dict(intent_capability)
        assert d["subject_type"] == "organisation"
        assert d["capability_code"] == "accommodation"
        assert d["status"] == "intent"
        assert d["activated_at"] is None
        # Dual-ID rule (AGENTS.md §12.1): internal BIGINT ids are never serialised.
        assert "id" not in d
        assert "organisation_id" not in d


# ===========================================================================
# 6. Organisation context respect
# ===========================================================================

class TestOrganisationContext:

    def test_org_a_capability_invisible_to_org_b(self, db_session):
        org_a = _make_org(db_session, suffix="A")
        org_b = _make_org(db_session, suffix="B")
        _add_capability(db_session, org_a, ProviderCapabilityCode.ACCOMMODATION.value)
        db_session.flush()

        caps_a = list_capabilities(org_a.id)
        caps_b = list_capabilities(org_b.id)
        assert len(caps_a) == 1
        assert len(caps_b) == 0

    def test_org_a_owner_cannot_activate_org_b(self, db_session):
        org_a = _make_org(db_session, suffix="A")
        org_b = _make_org(db_session, suffix="B")
        owner_a = _make_owner(db_session, org_a)
        _add_capability(db_session, org_b, ProviderCapabilityCode.EVENTS.value)
        db_session.flush()

        with pytest.raises(CapabilityPermissionError):
            activate_capability(owner_a, org_b.id, "events")

    def test_capability_unique_per_org(self, db_session, org):
        _add_capability(db_session, org, ProviderCapabilityCode.ACCOMMODATION.value)
        with pytest.raises(IntegrityError):
            _add_capability(db_session, org, ProviderCapabilityCode.ACCOMMODATION.value)
        db_session.rollback()


# ===========================================================================
# 7. Domain-resource isolation
# ===========================================================================

class TestDomainIsolation:

    def test_activate_creates_no_domain_resources(self, db_session, org, intent_capability):
        from app.accommodation.models.property import Property
        from app.transport.models import OrganisationTransportProfile

        props_before = Property.query.count()
        transport_before = OrganisationTransportProfile.query.count()

        owner = _make_owner(db_session, org)
        activate_capability(owner, org.id, "accommodation")

        assert Property.query.count() == props_before
        assert OrganisationTransportProfile.query.count() == transport_before

    def test_suspend_creates_no_domain_resources(self, db_session, org, activated_capability):
        from app.accommodation.models.property import Property
        from app.transport.models import OrganisationTransportProfile

        props_before = Property.query.count()
        transport_before = OrganisationTransportProfile.query.count()

        owner = _make_owner(db_session, org)
        suspend_capability(owner, org.id, "transport")

        assert Property.query.count() == props_before
        assert OrganisationTransportProfile.query.count() == transport_before

    def test_deactivate_does_not_delete_domain_data(self, db_session, org, activated_capability):
        from app.accommodation.models.property import Property
        from app.transport.models import OrganisationTransportProfile

        props_before = Property.query.count()
        transport_before = OrganisationTransportProfile.query.count()

        owner = _make_owner(db_session, org)
        deactivate_capability(owner, org.id, "transport")

        assert Property.query.count() == props_before
        assert OrganisationTransportProfile.query.count() == transport_before


# ===========================================================================
# 8. Capability does NOT grant permissions or authority
# ===========================================================================

class TestCapabilityDoesNotGrantAuthority:

    def test_activate_does_not_create_roles(self, db_session, org, intent_capability):
        owner = _make_owner(db_session, org)
        member_ids = [
            m.id for m in OrganisationMember.query.filter_by(
                organisation_id=org.id,
            ).all()
        ]
        roles_before = OrgUserRole.query.filter(
            OrgUserRole.organisation_member_id.in_(member_ids),
        ).count() if member_ids else 0

        activate_capability(owner, org.id, "accommodation")

        roles_after = OrgUserRole.query.filter(
            OrgUserRole.organisation_member_id.in_(member_ids),
        ).count() if member_ids else 0
        assert roles_after == roles_before

    def test_activate_does_not_create_permissions(self, db_session, org, intent_capability):
        from app.identity.models.roles_permission import Permission
        count_before = Permission.query.count()
        owner = _make_owner(db_session, org)
        activate_capability(owner, org.id, "accommodation")
        count_after = Permission.query.count()
        assert count_after == count_before


# ===========================================================================
# 9. HTTP API tests
# ===========================================================================

class TestCapabilityAPI:

    def _login(self, app, client, user):
        with app.app_context():
            with client.session_transaction() as sess:
                sess["_user_id"] = str(user.public_id)
                sess["_fresh"] = True

    def test_list_capabilities_endpoint(self, app, client, db_session, owner_user, org, intent_capability):
        self._login(app, client, owner_user)
        r = client.get(f"/org/{org.org_id}/capabilities")
        assert r.status_code == 200
        data = r.get_json()
        assert len(data["capabilities"]) == 1
        assert data["capabilities"][0]["capability_code"] == "accommodation"
        assert data["capabilities"][0]["status"] == "intent"

    def test_list_capabilities_empty(self, app, client, db_session, owner_user, org):
        self._login(app, client, owner_user)
        r = client.get(f"/org/{org.org_id}/capabilities")
        assert r.status_code == 200
        data = r.get_json()
        assert data["capabilities"] == []

    def test_activate_endpoint(self, app, client, db_session, owner_user, org, intent_capability):
        self._login(app, client, owner_user)
        r = client.post(f"/org/{org.org_id}/capabilities/accommodation/activate")
        assert r.status_code == 200
        data = r.get_json()
        assert data["capability"]["status"] == "activated"
        assert data["capability"]["activated_at"] is not None

    def test_deactivate_endpoint(self, app, client, db_session, owner_user, org, activated_capability):
        self._login(app, client, owner_user)
        r = client.post(f"/org/{org.org_id}/capabilities/transport/deactivate")
        assert r.status_code == 200
        assert r.get_json()["capability"]["status"] == "deactivated"

    def test_suspend_endpoint(self, app, client, db_session, owner_user, org, activated_capability):
        self._login(app, client, owner_user)
        r = client.post(f"/org/{org.org_id}/capabilities/transport/suspend")
        assert r.status_code == 200
        assert r.get_json()["capability"]["status"] == "suspended"

    def test_revoke_endpoint(self, app, client, db_session, owner_user, org, activated_capability):
        self._login(app, client, owner_user)
        r = client.post(f"/org/{org.org_id}/capabilities/transport/revoke")
        assert r.status_code == 200
        assert r.get_json()["capability"]["status"] == "revoked"

    def test_non_owner_gets_403(self, app, client, db_session, member_user, org, intent_capability):
        self._login(app, client, member_user)
        r = client.post(f"/org/{org.org_id}/capabilities/accommodation/activate")
        assert r.status_code == 403

    def test_invalid_code_gets_400(self, app, client, db_session, owner_user, org, intent_capability):
        self._login(app, client, owner_user)
        r = client.post(f"/org/{org.org_id}/capabilities/bogus/activate")
        assert r.status_code == 400

    def test_transition_conflict_gets_409(self, app, client, db_session, owner_user, org, activated_capability):
        self._login(app, client, owner_user)
        r = client.post(f"/org/{org.org_id}/capabilities/transport/activate")
        assert r.status_code == 409

    def test_not_found_gets_404(self, app, client, db_session, owner_user, org):
        self._login(app, client, owner_user)
        r = client.post(f"/org/{org.org_id}/capabilities/venue/activate")
        assert r.status_code == 404

    def test_unauthenticated_gets_redirect(self, app, client, db_session, org, intent_capability):
        r = client.get(f"/org/{org.org_id}/capabilities")
        assert r.status_code in (302, 401)
