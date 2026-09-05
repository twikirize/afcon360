"""
Focused tests for the organisation-role provisioning mechanism.

The provisioning service creates per-organisation ``OrgRole`` instances and
``OrgRolePermission`` links derived from the global organisation-role
templates. These tests verify:

    1. role instances are created
    2. correct organisation ownership
    3. correct template linkage
    4. correct permission copying from the source global role
    5. idempotency (no duplicate org_roles / org_role_permissions)
    6. existing org roles are reused, not duplicated
    7. existing OrgUserRole assignments are untouched
    8. existing OrgMemberPermission records are untouched
    9. no global Role / Permission / RolePermission mutation
    10. no domain resources are created
    11. failure safety (transaction rollback leaves no partial structure)

These tests are additive. They do not modify onboarding, membership
assignment, context authorization, or any wallet/domain code.
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
from app.identity.models.roles_permission import Role, Permission, RolePermission
from app.identity.models.user import User
from app.auth.seed_roles import ORG_ROLE_TEMPLATES
from app.identity.services.organisation_role_provisioning import (
    provision_organisation_roles,
)


@pytest.fixture(autouse=True, scope="session")
def _seed_global_org_roles(app):
    """Seed global roles + permissions + role-permission links.

    The provisioning source of truth is the global ``Role`` row
    (``scope="org"``) with its ``role_permissions`` links, both produced by
    ``seed_all``.
    """
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
        legal_name=f"Provision Org {suffix}",
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
        email=f"provision-{suffix}@example.com",
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


def _global_org_role(template_name):
    """Return the global org-scoped Role row for a template name."""
    return Role.query.filter_by(name=template_name, scope="org").first()


def _global_role_permission_names(global_role):
    """Return the permission names belonging to the global org role."""
    return set(global_role.permission_names)


# ---------------------------------------------------------------------------
# 1. Creates role instances
# ---------------------------------------------------------------------------

def test_provision_creates_role_instances(db_session):
    org = _make_org(db_session)
    db_session.flush()

    result = provision_organisation_roles(org)

    expected_names = set(ORG_ROLE_TEMPLATES.keys())
    assert result.keys() == expected_names
    assert all(not item["skipped"] for item in result.values())
    assert all(item["status"] == "created" for item in result.values())

    created_names = {
        r.name
        for r in OrgRole.query.filter_by(organisation_id=org.id).all()
    }
    assert created_names == expected_names


# ---------------------------------------------------------------------------
# 2. Correct organisation ownership
# ---------------------------------------------------------------------------

def test_all_created_roles_belong_to_requested_organisation(db_session):
    org_a = _make_org(db_session)
    org_b = _make_org(db_session)
    db_session.flush()

    provision_organisation_roles(org_a)

    for role in OrgRole.query.filter_by(organisation_id=org_a.id).all():
        assert role.organisation_id == org_a.id

    # Org B should have received nothing from provisioning org A.
    assert OrgRole.query.filter_by(organisation_id=org_b.id).count() == 0


# ---------------------------------------------------------------------------
# 3. Correct template linkage
# ---------------------------------------------------------------------------

def test_provisioned_roles_retain_source_template_name(db_session):
    org = _make_org(db_session)
    db_session.flush()

    provision_organisation_roles(org)

    roles = OrgRole.query.filter_by(organisation_id=org.id).all()
    assert len(roles) == len(ORG_ROLE_TEMPLATES)
    for role in roles:
        assert role.template_name == role.name
        assert role.template_name in ORG_ROLE_TEMPLATES


# ---------------------------------------------------------------------------
# 4. Correct permissions copied from the source global role
# ---------------------------------------------------------------------------

def test_provisioned_roles_get_source_global_role_permissions(db_session):
    org = _make_org(db_session)
    db_session.flush()

    provision_organisation_roles(org)

    org_roles = OrgRole.query.filter_by(organisation_id=org.id).all()
    assert org_roles

    for org_role in org_roles:
        global_role = _global_org_role(org_role.template_name)
        assert global_role is not None, org_role.template_name

        expected = _global_role_permission_names(global_role)
        actual = set(org_role.permission_names)

        assert actual == expected, (
            f"OrgRole {org_role.name} permissions {actual} != "
            f"global role permissions {expected}"
        )


def test_provisioned_role_permission_links_reference_global_permissions(db_session):
    org = _make_org(db_session)
    db_session.flush()

    provision_organisation_roles(org)

    links = (
        OrgRolePermission.query.join(
            OrgRole,
            OrgRolePermission.org_role_id == OrgRole.id,
        )
        .filter(OrgRole.organisation_id == org.id)
        .all()
    )
    assert links

    perm_ids = {link.permission_id for link in links}
    global_perm_ids = {p.id for p in Permission.query.all()}
    assert perm_ids <= global_perm_ids


# ---------------------------------------------------------------------------
# 5. Idempotency
# ---------------------------------------------------------------------------

def test_provision_is_idempotent(db_session):
    org = _make_org(db_session)
    db_session.flush()

    provision_organisation_roles(org)
    first_count = OrgRole.query.filter_by(organisation_id=org.id).count()
    first_link_count = (
        OrgRolePermission.query.join(
            OrgRole, OrgRolePermission.org_role_id == OrgRole.id
        )
        .filter(OrgRole.organisation_id == org.id)
        .count()
    )

    provision_organisation_roles(org)
    provision_organisation_roles(org)

    second_count = OrgRole.query.filter_by(organisation_id=org.id).count()
    second_link_count = (
        OrgRolePermission.query.join(
            OrgRole, OrgRolePermission.org_role_id == OrgRole.id
        )
        .filter(OrgRole.organisation_id == org.id)
        .count()
    )

    assert second_count == first_count
    assert second_link_count == first_link_count


# ---------------------------------------------------------------------------
# 6. Existing roles are preserved / reused
# ---------------------------------------------------------------------------

def test_existing_org_role_is_reused_not_duplicated(db_session):
    org = _make_org(db_session)
    db_session.flush()

    preexisting = OrgRole(
        organisation_id=org.id,
        name="finance_manager",
        template_name="finance_manager",
        description="Pre-existing role",
    )
    db_session.add(preexisting)
    db_session.flush()
    preexisting_id = preexisting.id

    provision_organisation_roles(org, roles={"finance_manager"})

    role = OrgRole.query.filter_by(
        organisation_id=org.id, name="finance_manager"
    ).first()
    assert role is not None
    assert role.id == preexisting_id
    assert role.description == "Pre-existing role"
    assert OrgRole.query.filter_by(
        organisation_id=org.id, name="finance_manager"
    ).count() == 1


# ---------------------------------------------------------------------------
# 7. Existing assignments are untouched
# ---------------------------------------------------------------------------

def test_provisioning_untouches_org_user_role_assignments(db_session):
    org = _make_org(db_session)
    member = _add_member(db_session, org)

    org_role = OrgRole(
        organisation_id=org.id,
        name="finance_manager",
        template_name="finance_manager",
    )
    db_session.add(org_role)
    db_session.flush()

    assignment = OrgUserRole(
        organisation_member_id=member.id,
        role_id=org_role.id,
    )
    db_session.add(assignment)
    db_session.flush()
    assignment_id = assignment.id

    provision_organisation_roles(org, roles={"finance_manager"})

    # Assignment still exists, unchanged, and still references the same role.
    still = db_session.get(OrgUserRole, assignment_id)
    assert still is not None
    assert still.role_id == org_role.id
    assert _org_user_role_count(db_session, org) == 1


def _org_user_role_count(db_session, org):
    return (
        OrgUserRole.query.join(
            OrgRole, OrgUserRole.role_id == OrgRole.id
        )
        .filter(OrgRole.organisation_id == org.id)
        .count()
    )


def test_provisioning_does_not_create_org_user_roles(db_session):
    org = _make_org(db_session)
    db_session.flush()

    provision_organisation_roles(org)

    assert _org_user_role_count(db_session, org) == 0


# ---------------------------------------------------------------------------
# 8. Existing direct member overrides are untouched
# ---------------------------------------------------------------------------

def test_provisioning_untouches_org_member_permissions(db_session):
    org = _make_org(db_session)
    member = _add_member(db_session, org)

    perm = Permission.query.filter_by(name="org.members.view").first()
    assert perm is not None

    override = OrgMemberPermission(
        member_id=member.id,
        permission_id=perm.id,
        granted=True,
    )
    db_session.add(override)
    db_session.flush()
    override_id = override.id

    provision_organisation_roles(org)

    still = db_session.get(OrgMemberPermission, override_id)
    assert still is not None
    assert still.permission_id == perm.id
    assert (
        OrgMemberPermission.query.filter_by(member_id=member.id).count() == 1
    )


# ---------------------------------------------------------------------------
# 9. No global role mutation
# ---------------------------------------------------------------------------

def test_provisioning_does_not_mutate_global_roles_or_permissions(db_session):
    org = _make_org(db_session)
    db_session.flush()

    global_role_ids = {r.id for r in Role.query.all()}
    global_perm_ids = {p.id for p in Permission.query.all()}
    global_link_ids = {l.id for l in RolePermission.query.all()}

    provision_organisation_roles(org)

    assert {r.id for r in Role.query.all()} == global_role_ids
    assert {p.id for p in Permission.query.all()} == global_perm_ids
    assert {l.id for l in RolePermission.query.all()} == global_link_ids


# ---------------------------------------------------------------------------
# 10. No domain resources
# ---------------------------------------------------------------------------

def test_provisioning_creates_no_domain_resources(db_session, app):
    from sqlalchemy import inspect

    from app.extensions import db

    org = _make_org(db_session)
    db_session.flush()

    # Snapshot row counts for representative domain tables before/after.
    inspector = inspect(db.engine)
    domain_tables = [
        "events",
        "rooms",
        "vehicles",
        "trips",
        "experiences",
        "bookings",
        "accommodation_properties",
    ]
    before = {}
    for table in domain_tables:
        if inspector.has_table(table):
            before[table] = db.session.execute(
                db.text(f"SELECT COUNT(*) FROM {table}")
            ).scalar()
        else:
            before[table] = None

    provision_organisation_roles(org)

    for table in domain_tables:
        if before[table] is None:
            assert not inspector.has_table(table), table
        else:
            after = db.session.execute(
                db.text(f"SELECT COUNT(*) FROM {table}")
            ).scalar()
            assert after == before[table], table


# ---------------------------------------------------------------------------
# 11. Failure safety
# ---------------------------------------------------------------------------

def test_provisioning_rolls_back_on_partial_failure(db_session, monkeypatch):
    org = _make_org(db_session)
    db_session.flush()

    import app.identity.services.organisation_role_provisioning as provisioning

    real_find = provisioning._find_or_create_org_role
    calls = {"n": 0}

    def flaky_find(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            # First role (e.g. org_owner) is created + flushed successfully.
            return real_find(*args, **kwargs)
        # Second role creation fails -> whole operation must roll back.
        raise RuntimeError("simulated mid-provision failure")

    monkeypatch.setattr(provisioning, "_find_or_create_org_role", flaky_find)

    with pytest.raises(RuntimeError):
        provision_organisation_roles(org)

    # No partial org_roles (or their permission links) may remain after rollback.
    assert OrgRole.query.filter_by(organisation_id=org.id).count() == 0
    assert (
        OrgRolePermission.query.join(
            OrgRole, OrgRolePermission.org_role_id == OrgRole.id
        )
        .filter(OrgRole.organisation_id == org.id)
        .count()
        == 0
    )


def test_provision_requires_persisted_organisation(db_session):
    with pytest.raises(ValueError):
        provision_organisation_roles(None)
