"""
Focused tests for the repaired ``assign_org_role`` and ``revoke_org_role``
functions.

These tests verify that:
    - ``org_user_roles.role_id`` ALWAYS references an ``org_roles.id``
      (never a ``roles.id``)
    - the global ``Role`` table is never mutated or referenced as an FK target
    - organisation boundary enforcement works correctly
    - on-demand provisioning fires when ``OrgRole`` does not yet exist
    - idempotent assignment (duplicate returns existing)
    - missing membership raises ValueError
    - ``revoke_org_role`` removes the correct assignment
    - ``revoke_org_role`` returns False for non-existent data
    - Step 1 (``provision_organisation_roles``) is unbroken

These tests are additive. They do not modify onboarding, membership
assignment, context authorization, or any wallet/domain code.
"""

import uuid

import pytest

from app.extensions import db
from app.identity.models.organisation import Organisation
from app.identity.models.organisation_member import (
    OrgRole,
    OrgUserRole,
    OrganisationMember,
)
from app.identity.models.roles_permission import Role, Permission, RolePermission
from app.identity.models.user import User
from app.auth.seed_roles import ORG_ROLE_TEMPLATES
from app.auth.roles import assign_org_role, revoke_org_role
from app.identity.services.organisation_role_provisioning import (
    provision_organisation_roles,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True, scope="session")
def _seed_global_org_roles(app):
    """Seed global roles + permissions + role-permission links."""
    from app.auth.seed_roles import seed_all

    # Pop the app context BEFORE yielding (do not hold it for the whole
    # session): a session-scoped autouse fixture whose ``yield`` sits inside
    # ``with app.app_context():`` keeps the app context open for the ENTIRE
    # test session, so later HTTP (E2E) tests share one persistent ``flask.g``
    # and Flask-Login can return a detached User across requests.
    with app.app_context():
        seed_all()
    yield


def _make_org(db_session, suffix=None):
    suffix = suffix or str(uuid.uuid4())[:8]
    org = Organisation(
        legal_name=f"Assign Org {suffix}",
        org_id=str(uuid.uuid4()),
        country="US",
    )
    db_session.add(org)
    db_session.flush()
    return org


def _make_user(db_session, suffix=None):
    suffix = suffix or str(uuid.uuid4())[:8]
    user = User(
        public_id=str(uuid.uuid4()),
        email=f"assign-{suffix}@example.com",
        password_hash="hashed",
        is_active=True,
    )
    db_session.add(user)
    db_session.flush()
    return user


def _add_member(db_session, org, user=None):
    if user is None:
        user = _make_user(db_session)
    member = OrganisationMember(
        user_id=user.id,
        organisation_id=org.id,
    )
    db_session.add(member)
    db_session.flush()
    return member


def _get_org_role(org, name):
    return OrgRole.query.filter_by(
        organisation_id=org.id, name=name
    ).first()


def _get_global_role(name):
    return Role.query.filter_by(name=name, scope="org").first()


def _get_global_role_id_set():
    return {r.id for r in Role.query.all()}


# ---------------------------------------------------------------------------
# 1. assign_org_role resolves OrgRole, not global Role
# ---------------------------------------------------------------------------

def test_assign_org_role_resolves_org_role_not_global_role(db_session):
    """The OrgUserRole must reference org_roles.id, not roles.id."""
    org = _make_org(db_session)
    user = _make_user(db_session)
    member = _add_member(db_session, org, user)

    # Ensure provisioned.
    provision_organisation_roles(org, roles={"org_admin"})
    db.session.expire_all()

    org_role = _get_org_role(org, "org_admin")
    assert org_role is not None

    our = assign_org_role(user.id, org.id, "org_admin")

    assert our is not None
    assert our.role_id == org_role.id
    assert our.organisation_member_id == member.id


def test_assign_org_role_role_id_is_org_role_id_not_global_role_id(db_session):
    """Directly verify the FK points to org_roles, never roles."""
    org = _make_org(db_session)
    user = _make_user(db_session)
    _add_member(db_session, org, user)

    provision_organisation_roles(org, roles={"org_admin"})
    db.session.expire_all()

    our = assign_org_role(user.id, org.id, "org_admin")

    global_role = _get_global_role("org_admin")
    org_role = _get_org_role(org, "org_admin")

    assert global_role is not None
    assert org_role is not None
    assert global_role.id != org_role.id
    assert our.role_id == org_role.id
    assert our.role_id != global_role.id


# ---------------------------------------------------------------------------
# 2. assign_org_role provisions on demand when OrgRole not yet provisioned
# ---------------------------------------------------------------------------

def test_assign_org_role_provisions_on_demand(db_session):
    """If OrgRole does not exist yet, assign_org_role provisions it."""
    org = _make_org(db_session)
    user = _make_user(db_session)
    _add_member(db_session, org, user)

    # Ensure no org_roles exist for this org.
    assert OrgRole.query.filter_by(organisation_id=org.id).count() == 0

    our = assign_org_role(user.id, org.id, "org_admin")

    # OrgRole should now exist (on-demand provisioned).
    org_role = _get_org_role(org, "org_admin")
    assert org_role is not None
    assert our.role_id == org_role.id


def test_assign_org_role_does_not_provision_unrelated_roles(db_session):
    """On-demand provisioning only creates the requested role template."""
    org = _make_org(db_session)
    user = _make_user(db_session)
    _add_member(db_session, org, user)

    assign_org_role(user.id, org.id, "org_admin")

    org_roles = OrgRole.query.filter_by(organisation_id=org.id).all()
    role_names = {r.name for r in org_roles}
    assert role_names == {"org_admin"}


# ---------------------------------------------------------------------------
# 3. Organisation isolation
# ---------------------------------------------------------------------------

def test_org_role_from_org_a_cannot_be_used_for_org_b(db_session):
    """The boundary check ensures OrgRole belongs to the target org.

    assign_org_role resolves OrgRole by (organisation_id, name), so an
    OrgRole belonging to Org A is never matched when assigning to Org B.
    We verify the invariant: each org only sees its own org_roles.
    """
    org_a = _make_org(db_session)
    org_b = _make_org(db_session)
    user_b = _make_user(db_session)
    _add_member(db_session, org_b, user_b)

    # Provision both orgs.
    provision_organisation_roles(org_a, roles={"org_admin"})
    provision_organisation_roles(org_b, roles={"org_admin"})
    db.session.expire_all()

    org_role_a = _get_org_role(org_a, "org_admin")

    # The fundamental invariant: OrgRole for org_a belongs to org_a only.
    assert org_role_a.organisation_id == org_a.id

    # When assigning to org_b, the resolved role must be org_b's, not org_a's.
    our = assign_org_role(user_b.id, org_b.id, "org_admin")
    org_role_b = _get_org_role(org_b, "org_admin")
    assert our.role_id == org_role_b.id
    assert our.role_id != org_role_a.id


# ---------------------------------------------------------------------------
# 4. Multiple roles can be assigned to the same user
# ---------------------------------------------------------------------------

def test_assign_multiple_org_roles_to_same_user(db_session):
    org = _make_org(db_session)
    user = _make_user(db_session)
    _add_member(db_session, org, user)

    our_admin = assign_org_role(user.id, org.id, "org_admin")
    our_member = assign_org_role(user.id, org.id, "org_member")

    assert our_admin.role_id != our_member.role_id

    admin_role = _get_org_role(org, "org_admin")
    member_role = _get_org_role(org, "org_member")

    assert our_admin.role_id == admin_role.id
    assert our_member.role_id == member_role.id


# ---------------------------------------------------------------------------
# 5. Duplicate assignment is idempotent
# ---------------------------------------------------------------------------

def test_assign_org_role_is_idempotent(db_session):
    org = _make_org(db_session)
    user = _make_user(db_session)
    _add_member(db_session, org, user)

    our_first = assign_org_role(user.id, org.id, "org_admin")
    our_second = assign_org_role(user.id, org.id, "org_admin")

    assert our_first.id == our_second.id
    assert OrgUserRole.query.filter_by(
        organisation_member_id=our_first.organisation_member_id,
        role_id=our_first.role_id,
    ).count() == 1


# ---------------------------------------------------------------------------
# 6. Missing membership raises ValueError
# ---------------------------------------------------------------------------

def test_assign_org_role_raises_for_non_member(db_session):
    org = _make_org(db_session)
    user = _make_user(db_session)
    # Do NOT add as member.

    with pytest.raises(ValueError, match="not a member"):
        assign_org_role(user.id, org.id, "org_admin")


# ---------------------------------------------------------------------------
# 7. Global roles table is never mutated
# ---------------------------------------------------------------------------

def test_assign_org_role_does_not_mutate_global_roles(db_session):
    global_role_ids = _get_global_role_id_set()
    global_perm_ids = {p.id for p in Permission.query.all()}
    global_link_ids = {l.id for l in RolePermission.query.all()}

    org = _make_org(db_session)
    user = _make_user(db_session)
    _add_member(db_session, org, user)

    assign_org_role(user.id, org.id, "org_admin")

    assert {r.id for r in Role.query.all()} == global_role_ids
    assert {p.id for p in Permission.query.all()} == global_perm_ids
    assert {l.id for l in RolePermission.query.all()} == global_link_ids


# ---------------------------------------------------------------------------
# 8. Step 1 regression: provision_organisation_roles still works
# ---------------------------------------------------------------------------

def test_provision_organisation_roles_still_works(db_session):
    org = _make_org(db_session)

    result = provision_organisation_roles(org)

    expected_names = set(ORG_ROLE_TEMPLATES.keys())
    assert result.keys() == expected_names
    created_names = {
        r.name for r in OrgRole.query.filter_by(organisation_id=org.id).all()
    }
    assert created_names == expected_names


# ---------------------------------------------------------------------------
# 9. revoke_org_role resolves OrgRole and removes assignment
# ---------------------------------------------------------------------------

def test_revoke_org_role_removes_assignment(db_session):
    org = _make_org(db_session)
    user = _make_user(db_session)
    _add_member(db_session, org, user)

    our = assign_org_role(user.id, org.id, "org_admin")
    our_id = our.id

    result = revoke_org_role(user.id, org.id, "org_admin")

    assert result is True
    assert db.session.get(OrgUserRole, our_id) is None


def test_revoke_org_role_returns_false_for_nonexistent_assignment(db_session):
    org = _make_org(db_session)
    user = _make_user(db_session)
    _add_member(db_session, org, user)

    provision_organisation_roles(org, roles={"org_admin"})
    db.session.expire_all()

    result = revoke_org_role(user.id, org.id, "org_admin")

    assert result is False


def test_revoke_org_role_returns_false_for_non_member(db_session):
    org = _make_org(db_session)
    user = _make_user(db_session)
    # Do NOT add as member.

    provision_organisation_roles(org, roles={"org_admin"})
    db.session.expire_all()

    result = revoke_org_role(user.id, org.id, "org_admin")
    assert result is False


def test_revoke_org_role_returns_false_for_unprovisioned_role(db_session):
    org = _make_org(db_session)
    user = _make_user(db_session)
    _add_member(db_session, org, user)

    # No provisioning done at all.
    result = revoke_org_role(user.id, org.id, "org_admin")
    assert result is False


# ---------------------------------------------------------------------------
# 10. revoke_org_role is idempotent
# ---------------------------------------------------------------------------

def test_revoke_org_role_is_idempotent(db_session):
    org = _make_org(db_session)
    user = _make_user(db_session)
    _add_member(db_session, org, user)

    assign_org_role(user.id, org.id, "org_admin")

    first_result = revoke_org_role(user.id, org.id, "org_admin")
    assert first_result is True

    second_result = revoke_org_role(user.id, org.id, "org_admin")
    assert second_result is False


# ---------------------------------------------------------------------------
# 11. Global roles are never used as FK target in org_user_roles
# ---------------------------------------------------------------------------

def test_org_user_roles_never_reference_global_role_id(db_session):
    """Inspect the actual org_user_roles rows and verify no FK points to roles.id."""
    global_role_ids = _get_global_role_id_set()

    org = _make_org(db_session)
    user = _make_user(db_session)
    _add_member(db_session, org, user)

    our = assign_org_role(user.id, org.id, "org_admin")

    assert our.role_id not in global_role_ids
