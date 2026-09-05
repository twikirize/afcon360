"""
Focused tests for the organisation permission READ path (RBAC Step 3).

Verifies that ``has_org_permission()`` resolves permissions from the
canonical organisation-role architecture:

    OrgUserRole → OrgRole → OrgRolePermission → Permission

and correctly applies direct grant / deny overrides from OrgMemberPermission.

    1.  assigned OrgRole grants permission
    2.  missing permission denied
    3.  organisation isolation
    4.  global role ID is not used
    5.  direct grant
    6.  direct deny
    7.  no membership
    8.  multiple roles union
    9.  capability does not grant authority
    10. policy.can() integration
"""

import uuid

import pytest

from app.identity.models.organisation import Organisation
from app.identity.models.organisation_member import (
    OrgRole,
    OrgRolePermission,
    OrgUserRole,
    OrganisationMember,
    OrgMemberPermission,
)
from app.identity.models.roles_permission import Permission, Role, RolePermission
from app.identity.models.user import User
from app.auth.helpers import has_org_permission, get_org_member
from app.auth.roles import assign_org_role
from app.identity.services.organisation_role_provisioning import (
    provision_organisation_roles,
)
from app.extensions import db


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True, scope="session")
def _seed_global_roles(app):
    """Seed global roles + permissions + role-permission links once."""
    from app.auth.seed_roles import seed_all

    # Pop the app context BEFORE yielding (do not hold it for the whole
    # session): a session-scoped autouse fixture whose ``yield`` sits inside
    # ``with app.app_context():`` keeps the app context open for the ENTIRE
    # test session, so later HTTP (E2E) tests share one persistent ``flask.g``
    # and Flask-Login can return a detached User across requests.
    with app.app_context():
        seed_all()
    yield


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_org(db_session):
    suffix = str(uuid.uuid4())[:8]
    org = Organisation(
        legal_name=f"Perm Org {suffix}",
        org_id=str(uuid.uuid4()),
        country="UG",
    )
    db_session.add(org)
    db_session.flush()
    return org


def _make_user(db_session):
    suffix = str(uuid.uuid4())[:8]
    user = User(
        public_id=str(uuid.uuid4()),
        email=f"perm-{suffix}@example.com",
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


def _ensure_permission(name):
    """Get or create a global Permission row."""
    perm = Permission.query.filter_by(name=name).first()
    if not perm:
        perm = Permission(name=name, description=f"Test perm {name}")
        db.session.add(perm)
        db.session.flush()
    return perm


def _ensure_global_org_role(template_name):
    """Return the global org-scoped Role row."""
    return Role.query.filter_by(name=template_name, scope="org").first()


def _get_org_role(org, role_name):
    """Return the OrgRole for the given org and name."""
    return OrgRole.query.filter_by(
        organisation_id=org.id, name=role_name
    ).first()


# ---------------------------------------------------------------------------
# Test 1 — assigned OrgRole grants permission
# ---------------------------------------------------------------------------

def test_assigned_org_role_grants_permission(db_session):
    """Organisation member with org_admin role receives org.finance.view."""
    org = _make_org(db_session)
    user = _make_user(db_session)
    member = _add_member(db_session, org, user)

    provision_organisation_roles(org, roles={"org_admin"})
    db.session.expire_all()

    assign_org_role(user.id, org.id, "org_admin")
    db.session.expire_all()
    member = get_org_member(user, org.id)

    assert has_org_permission(user, org.id, "org.finance.view") is True


# ---------------------------------------------------------------------------
# Test 2 — missing permission denied
# ---------------------------------------------------------------------------

def test_missing_permission_denied(db_session):
    """Member with org_admin role does NOT receive org.settings.manage."""
    org = _make_org(db_session)
    user = _make_user(db_session)
    _add_member(db_session, org, user)

    provision_organisation_roles(org, roles={"org_admin"})
    db.session.expire_all()

    assign_org_role(user.id, org.id, "org_admin")

    # org_admin has org.finance.view but NOT org.settings.manage
    assert has_org_permission(user, org.id, "org.settings.manage") is False


# ---------------------------------------------------------------------------
# Test 3 — organisation isolation
# ---------------------------------------------------------------------------

def test_organisation_isolation(db_session):
    """Permission in Org A must not authorize Org B.

    org_admin in Org A gets org.finance.view via provisioning.
    Org B has no roles provisioned → member of B must NOT get the permission.
    """
    org_a = _make_org(db_session)
    org_b = _make_org(db_session)
    user = _make_user(db_session)

    # Add user as member of both orgs.
    _add_member(db_session, org_a, user)
    _add_member(db_session, org_b, user)

    # Provision only org_a with org_admin (which gets org.finance.view).
    provision_organisation_roles(org_a, roles={"org_admin"})
    db.session.expire_all()

    assign_org_role(user.id, org_a.id, "org_admin")

    # Org A: has the permission.
    assert has_org_permission(user, org_a.id, "org.finance.view") is True

    # Org B: no role assigned → no permission.
    assert has_org_permission(user, org_b.id, "org.finance.view") is False


# ---------------------------------------------------------------------------
# Test 4 — global role ID is not used
# ---------------------------------------------------------------------------

def test_global_role_id_not_used(db_session):
    """Organisation permission must never depend on roles.id.

    We assign a role to a member whose role_id contains an org_roles.id.
    Then verify that querying role_permissions with this ID returns nothing
    (because role_permissions links to roles.id, not org_roles.id).
    The permission must still be found via org_role_permissions.
    """
    org = _make_org(db_session)
    user = _make_user(db_session)
    _add_member(db_session, org, user)

    provision_organisation_roles(org, roles={"org_admin"})
    db.session.expire_all()

    assign_org_role(user.id, org.id, "org_admin")
    db.session.expire_all()
    member = get_org_member(user, org.id)

    # Collect the role IDs from the member's assignments.
    org_role_ids = [our.role_id for our in member.roles if our.role_id]

    # These IDs are org_roles.id values.
    assert len(org_role_ids) > 0

    # Verify role_permissions has NO rows for these IDs.
    rp_count = (
        RolePermission.query
        .filter(RolePermission.role_id.in_(org_role_ids))
        .count()
    )
    assert rp_count == 0, (
        f"role_permissions should not contain org_roles.id values, "
        f"but found {rp_count} rows"
    )

    # But org_role_permissions DOES have rows for these IDs.
    orp_count = (
        OrgRolePermission.query
        .filter(OrgRolePermission.org_role_id.in_(org_role_ids))
        .count()
    )
    assert orp_count > 0

    # The permission is still found through the correct path.
    assert has_org_permission(user, org.id, "org.finance.view") is True


# ---------------------------------------------------------------------------
# Test 5 — direct grant
# ---------------------------------------------------------------------------

def test_direct_grant(db_session):
    """OrgMemberPermission with granted=True grants a permission not in the role."""
    org = _make_org(db_session)
    user = _make_user(db_session)
    member = _add_member(db_session, org, user)

    provision_organisation_roles(org, roles={"org_member"})
    db.session.expire_all()

    assign_org_role(user.id, org.id, "org_member")
    db.session.expire_all()
    member = get_org_member(user, org.id)

    # org_member only has org.members.view — not org.finance.view.
    assert has_org_permission(user, org.id, "org.finance.view") is False

    # Direct grant overrides.
    perm = _ensure_permission("org.finance.view")
    dp = OrgMemberPermission(
        member_id=member.id,
        permission_id=perm.id,
        granted=True,
    )
    db.session.add(dp)
    db.session.commit()
    db.session.expire_all()
    member = get_org_member(user, org.id)

    assert has_org_permission(user, org.id, "org.finance.view") is True


# ---------------------------------------------------------------------------
# Test 6 — direct deny
# ---------------------------------------------------------------------------

def test_direct_deny(db_session):
    """OrgMemberPermission with granted=False denies a permission the role grants."""
    org = _make_org(db_session)
    user = _make_user(db_session)
    member = _add_member(db_session, org, user)

    provision_organisation_roles(org, roles={"org_admin"})
    db.session.expire_all()

    assign_org_role(user.id, org.id, "org_admin")
    db.session.expire_all()
    member = get_org_member(user, org.id)

    # org_admin has org.finance.view.
    assert has_org_permission(user, org.id, "org.finance.view") is True

    # Direct deny overrides the role grant.
    perm = _ensure_permission("org.finance.view")
    dp = OrgMemberPermission(
        member_id=member.id,
        permission_id=perm.id,
        granted=False,
    )
    db.session.add(dp)
    db.session.commit()
    db.session.expire_all()
    member = get_org_member(user, org.id)

    assert has_org_permission(user, org.id, "org.finance.view") is False


# ---------------------------------------------------------------------------
# Test 7 — no membership
# ---------------------------------------------------------------------------

def test_no_membership_denied(db_session):
    """User who is not a member of the org receives no permissions."""
    org = _make_org(db_session)
    user = _make_user(db_session)
    # NOT adding as member.

    provision_organisation_roles(org, roles={"org_admin"})
    db.session.expire_all()

    assert has_org_permission(user, org.id, "org.finance.view") is False


# ---------------------------------------------------------------------------
# Test 8 — multiple roles
# ---------------------------------------------------------------------------

def test_multiple_roles_union(db_session):
    """Member with org_admin AND finance_manager gets the union of permissions."""
    org = _make_org(db_session)
    user = _make_user(db_session)
    _add_member(db_session, org, user)

    provision_organisation_roles(org, roles={"org_admin", "finance_manager"})
    db.session.expire_all()

    assign_org_role(user.id, org.id, "org_admin")
    assign_org_role(user.id, org.id, "finance_manager")
    db.session.expire_all()

    # org_admin grants org.finance.view, org.members.view, org.settings.view
    assert has_org_permission(user, org.id, "org.finance.view") is True
    assert has_org_permission(user, org.id, "org.members.view") is True

    # finance_manager additionally grants org.finance.manage
    assert has_org_permission(user, org.id, "org.finance.manage") is True

    # org.settings.manage is only granted by org_owner — not by admin or finance_manager.
    assert has_org_permission(user, org.id, "org.settings.manage") is False


# ---------------------------------------------------------------------------
# Test 9 — capability does not grant authority
# ---------------------------------------------------------------------------

def test_capability_does_not_grant_authority(db_session):
    """Having an org capability (e.g. accommodation) does not auto-grant permissions.

    This verifies that has_org_permission does NOT consult provider
    capabilities — only the persisted role-permission chain matters.
    """
    org = _make_org(db_session)
    user = _make_user(db_session)
    member = _add_member(db_session, org, user)

    # Give the org an accommodation capability directly (simulating Stage 3).
    org.org_settings = {"capabilities": ["accommodation"]}
    db.session.commit()

    # The member has NO org role — so has_org_permission must return False
    # even though the org has the capability.
    assert has_org_permission(user, org.id, "org.accommodation.view") is False


# ---------------------------------------------------------------------------
# Test 10 — policy.can() integration
# ---------------------------------------------------------------------------

def test_policy_can_integration(db_session):
    """policy.can() with org_id delegates to has_org_permission correctly."""
    from app.auth.policy import can

    org = _make_org(db_session)
    user = _make_user(db_session)
    _add_member(db_session, org, user)

    provision_organisation_roles(org, roles={"org_admin"})
    db.session.expire_all()

    assign_org_role(user.id, org.id, "org_admin")
    db.session.expire_all()

    # policy.can with org_id should delegate to has_org_permission.
    assert can(user, "org.finance.view", org_id=org.id) is True
    assert can(user, "org.settings.manage", org_id=org.id) is False


# ---------------------------------------------------------------------------
# Regression — Step 1 provisioning still works
# ---------------------------------------------------------------------------

def test_provisioning_still_works(db_session):
    """Regression: provision_organisation_roles still creates correct links."""
    org = _make_org(db_session)
    result = provision_organisation_roles(org, roles={"org_admin"})
    db.session.expire_all()

    org_role = _get_org_role(org, "org_admin")
    assert org_role is not None
    assert org_role.organisation_id == org.id

    orp_count = OrgRolePermission.query.filter_by(org_role_id=org_role.id).count()
    assert orp_count > 0


# ---------------------------------------------------------------------------
# Regression — Step 2 assign/revoke still works
# ---------------------------------------------------------------------------

def test_assign_revoke_still_works(db_session):
    """Regression: assign_org_role / revoke_org_role still function correctly."""
    org = _make_org(db_session)
    user = _make_user(db_session)
    _add_member(db_session, org, user)

    provision_organisation_roles(org, roles={"org_admin"})
    db.session.expire_all()

    our = assign_org_role(user.id, org.id, "org_admin")
    assert our.role_id == _get_org_role(org, "org_admin").id

    from app.auth.roles import revoke_org_role
    result = revoke_org_role(user.id, org.id, "org_admin")
    assert result is True

    assert has_org_permission(user, org.id, "org.finance.view") is False
