"""
HTTP-path tests for the Organisation Administration Remediation node.

These tests drive the ACTUAL routes in ``app/identity/routes.py`` through the
Flask test client and assert against the live PostgreSQL schema (canonical org
RBAC graph: ``organisation_members`` / ``org_user_roles`` / ``org_roles`` /
``org_role_permissions``).

Coverage by group:

    A. members GET gates
       - members.view holders (org_owner, org_admin, hr_manager) render 200
       - org_member / non-member are redirected (fail-closed, never 200)

    B. add-member POST (org.members.manage)
       - owner and org_admin can add (assigned_by = actor pk, audit)
       - duplicates are rejected
       - inactive and unverified users are rejected (eligibility rule)
       - legacy enum role names are rejected at the route boundary
       - an actor without ``org.members.manage`` cannot POST a member

    C. role change POST (org.members.manage_roles)
       - org_owner and org_admin can re-role a target (single canonical role)
       - non-owner actor cannot grant ``org_owner`` (no escalation)
       - owner can grant ``org_owner``
       - the organisation owner can never be re-roled
       - no self role-change
       - an actor without ``org.members.manage_roles`` is denied

    D. remove-member POST (org.members.manage or self-leave)
       - owner/admin can remove a non-owner (soft-delete + purge assignments)
       - direct member permission grants are purged
       - the organisation owner can never be removed
       - a plain member may leave themselves
       - a plain member cannot remove others

    E. templates render (no legacy ``member.role`` enum access) + fail-closed
       gates on settings / accommodation / transport

Isolation notes (matches tests/conftest.py:_login_client):
    - ``client.session_transaction()`` opens a nested request context that
      tears down the SQLAlchemy session, detaching any expired ORM instance
      created before it. Helpers therefore extract scalar handles (ids,
      emails, public ids) while instances are still attached, and assertions
      re-query fresh rows instead of reusing pre-request instances.

This suite is additive; it changes no wallet, onboarding, or domain code.
"""

import uuid

import pytest

from app.extensions import db
from app.identity.models.organisation import Organisation
from app.identity.models.organisation_member import (
    OrgMemberPermission,
    OrgUserRole,
    OrganisationMember,
)
from app.identity.models.roles_permission import Permission
from app.identity.models.user import User
from app.identity.services.organisation_role_provisioning import (
    provision_organisation_roles,
)
from app.auth.roles import assign_org_role


# ---------------------------------------------------------------------------
# Session-scoped global seeding (same contract as test_assign_revoke_org_role)
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True, scope="session")
def _seed_global_org_roles(app):
    """Seed global roles + permissions + role-permission links once."""
    from app.auth.seed_roles import seed_all

    with app.app_context():
        seed_all()
    yield


# ---------------------------------------------------------------------------
# Helpers (scalar handles only — never cross-context ORM instances)
# ---------------------------------------------------------------------------

def _make_org(tag):
    """Create + flush an org; returns the ORM instance (setup-time only)."""
    org = Organisation(
        org_id=str(uuid.uuid4()),
        legal_name=f"Remed Org {tag} {uuid.uuid4().hex[:6]}",
        country="UG",
        region="Central",
        org_type="business",
        contact_email=f"remed-{tag}-{uuid.uuid4().hex[:6]}@example.com",
    )
    db.session.add(org)
    db.session.flush()
    return org


def _org_handle(org):
    """Scalar snapshot of an org for cross-context use."""
    return {
        "id": org.id,
        "org_id": org.org_id,
        "slug": org.slug,
        "legal_name": org.legal_name,
    }


def _make_user(tag, is_active=True, verified=True):
    """Create + flush a user; returns a scalar handle."""
    user = User(
        public_id=str(uuid.uuid4()),
        username=f"{tag}_{uuid.uuid4().hex[:8]}",
        email=f"{tag}_{uuid.uuid4().hex[:8]}@example.com",
        password_hash="hashed",
        is_active=is_active,
        is_verified=verified,
        email_verified=True if verified else False,
    )
    db.session.add(user)
    db.session.flush()
    return {
        "id": user.id,
        "public_id": str(user.public_id),
        "email": user.email,
    }


def _make_member(org_handle, user_handle):
    """Create + flush an org membership; returns the ORM instance
    (setup-time only — do not touch across client requests)."""
    member = OrganisationMember(
        user_id=user_handle["id"],
        organisation_id=org_handle["id"],
        is_active=True,
    )
    db.session.add(member)
    db.session.flush()
    return member


def _setup_org(tag):
    """Provisioned org with owner + admin + hr_manager + org_member actors.

    Returns scalar handles: (org_handle, actors) where actors maps
    owner/admin/hr/plain to user handles.
    """
    org = _make_org(tag)
    provision_organisation_roles(org)
    org_handle = _org_handle(org)

    owner = _make_user(f"{tag}_owner")
    owner_member = _make_member(org_handle, owner)
    assign_org_role(owner["id"], org_handle["id"], "org_owner")
    owner_member.invalidate_permission_cache()

    admin = _make_user(f"{tag}_admin")
    admin_member = _make_member(org_handle, admin)
    assign_org_role(admin["id"], org_handle["id"], "org_admin")
    admin_member.invalidate_permission_cache()

    hr = _make_user(f"{tag}_hr")
    hr_member = _make_member(org_handle, hr)
    assign_org_role(hr["id"], org_handle["id"], "hr_manager")
    hr_member.invalidate_permission_cache()

    plain = _make_user(f"{tag}_plain")
    plain_member = _make_member(org_handle, plain)
    assign_org_role(plain["id"], org_handle["id"], "org_member")
    plain_member.invalidate_permission_cache()

    db.session.commit()
    return org_handle, {
        "owner": owner,
        "admin": admin,
        "hr": hr,
        "plain": plain,
    }


def _login(client, public_id):
    """Set Flask-Login session cookies for a scalar public-id string."""
    with client.session_transaction() as sess:
        sess["_user_id"] = public_id
        sess["_fresh"] = True


def _member_row(org_id, user_id):
    return OrganisationMember.query.filter_by(
        user_id=user_id,
        organisation_id=org_id,
    ).first()


def _member_role_names(org_id, user_id):
    member = _member_row(org_id, user_id)
    if not member:
        return set()
    return {our.role.name for our in member.roles if our.role and our.role.name}


def _count_memberships(org_id, user_id):
    return OrganisationMember.query.filter_by(
        user_id=user_id,
        organisation_id=org_id,
        is_deleted=False,
    ).count()


# ===========================================================================
# Group A — members GET gates
# ===========================================================================

class TestMembersGETGates:
    def test_owner_can_view_members(self, app):
        org, actors = _setup_org("a_owner")
        client = app.test_client()
        _login(client, actors["owner"]["public_id"])

        resp = client.get(f"/org/{org['slug']}/members")

        assert resp.status_code == 200, resp.status_code
        assert b"Team Management" in resp.data
        assert b"Owner" in resp.data

    def test_admin_can_view_members(self, app):
        org, actors = _setup_org("a_admin")
        client = app.test_client()
        _login(client, actors["admin"]["public_id"])

        resp = client.get(f"/org/{org['slug']}/members")

        assert resp.status_code == 200, resp.status_code
        assert b"Team Management" in resp.data
        assert b"Admin" in resp.data

    def test_hr_manager_can_view_members(self, app):
        org, actors = _setup_org("a_hr")
        client = app.test_client()
        _login(client, actors["hr"]["public_id"])

        resp = client.get(f"/org/{org['slug']}/members")

        assert resp.status_code == 200, resp.status_code

    def test_plain_member_redirected(self, app):
        org, actors = _setup_org("a_plain")
        client = app.test_client()
        _login(client, actors["plain"]["public_id"])

        resp = client.get(f"/org/{org['slug']}/members")

        assert resp.status_code == 302, resp.status_code
        assert "/dashboard" in resp.headers.get("Location", "")

    def test_non_member_redirected(self, app):
        org, _actors = _setup_org("a_nonmember")
        outsider = _make_user("a_outsider")
        db.session.commit()
        client = app.test_client()
        _login(client, outsider["public_id"])

        resp = client.get(f"/org/{org['slug']}/members")

        assert resp.status_code == 302, resp.status_code
        assert "/dashboard" in resp.headers.get("Location", "")

    def test_members_page_has_no_legacy_enum_values(self, app):
        org, actors = _setup_org("a_clean")
        client = app.test_client()
        _login(client, actors["owner"]["public_id"])

        resp = client.get(f"/org/{org['slug']}/members")

        assert resp.status_code == 200
        assert b"staff_member" not in resp.data
        assert b"send_invite" not in resp.data
        assert b"Add Member" in resp.data


# ===========================================================================
# Group B — add-member POST (org.members.manage)
# ===========================================================================

class TestAddMemberPOST:
    def test_owner_can_add_member_with_audit_actor(self, app):
        org, actors = _setup_org("b_owneradd")
        target = _make_user("b_target")
        db.session.commit()
        client = app.test_client()
        _login(client, actors["owner"]["public_id"])

        resp = client.post(
            f"/org/{org['slug']}/members",
            data={"user_email": target["email"], "role": "org_admin"},
            follow_redirects=False,
        )

        assert resp.status_code == 302, resp.status_code
        member = _member_row(org["id"], target["id"])
        assert member is not None
        assert member.is_active is True
        assert _member_role_names(org["id"], target["id"]) == {"org_admin"}
        our = (
            OrgUserRole.query.filter_by(organisation_member_id=member.id)
            .first()
        )
        assert our is not None
        assert our.assigned_by == actors["owner"]["id"]

    def test_admin_can_add_member(self, app):
        org, actors = _setup_org("b_adminadd")
        target = _make_user("b_target2")
        db.session.commit()
        client = app.test_client()
        _login(client, actors["admin"]["public_id"])

        resp = client.post(
            f"/org/{org['slug']}/members",
            data={"user_email": target["email"], "role": "org_member"},
            follow_redirects=False,
        )

        assert resp.status_code == 302, resp.status_code
        assert _member_role_names(org["id"], target["id"]) == {"org_member"}
        row = _member_row(org["id"], target["id"])
        our = OrgUserRole.query.filter_by(
            organisation_member_id=row.id
        ).first()
        assert our.assigned_by == actors["admin"]["id"]

    def test_duplicate_member_rejected(self, app):
        org, actors = _setup_org("b_dup")
        client = app.test_client()
        _login(client, actors["owner"]["public_id"])

        resp = client.post(
            f"/org/{org['slug']}/members",
            data={"user_email": actors["admin"]["email"], "role": "org_admin"},
            follow_redirects=False,
        )

        assert resp.status_code == 302, resp.status_code
        assert _count_memberships(org["id"], actors["admin"]["id"]) == 1

    def test_inactive_user_rejected(self, app):
        org, actors = _setup_org("b_inactive")
        inactive = _make_user("b_inactive_user", is_active=False)
        db.session.commit()
        client = app.test_client()
        _login(client, actors["owner"]["public_id"])

        resp = client.post(
            f"/org/{org['slug']}/members",
            data={"user_email": inactive["email"], "role": "org_member"},
            follow_redirects=False,
        )

        assert resp.status_code == 302, resp.status_code
        assert _count_memberships(org["id"], inactive["id"]) == 0

    def test_unverified_user_rejected(self, app):
        org, actors = _setup_org("b_unverified")
        unverified = _make_user("b_unverified_user", verified=False)
        db.session.commit()
        client = app.test_client()
        _login(client, actors["owner"]["public_id"])

        resp = client.post(
            f"/org/{org['slug']}/members",
            data={"user_email": unverified["email"], "role": "org_member"},
            follow_redirects=False,
        )

        assert resp.status_code == 302, resp.status_code
        assert _count_memberships(org["id"], unverified["id"]) == 0

    def test_legacy_enum_role_name_rejected(self, app):
        org, actors = _setup_org("b_legacy")
        target = _make_user("b_legacy_target")
        db.session.commit()
        client = app.test_client()
        _login(client, actors["owner"]["public_id"])

        resp = client.post(
            f"/org/{org['slug']}/members",
            data={"user_email": target["email"], "role": "staff_member"},
            follow_redirects=True,
        )

        assert resp.status_code == 200, resp.status_code
        assert _count_memberships(org["id"], target["id"]) == 0
        assert b"Not a valid choice" in resp.data or b"cannot be assigned" in resp.data

    def test_actor_without_manage_cannot_add(self, app):
        """org_member has no org.members.view (GET already fails) and no
        org.members.manage; a POST must never create a membership."""
        org, actors = _setup_org("b_noperm")
        target = _make_user("b_noperm_target")
        db.session.commit()
        client = app.test_client()
        _login(client, actors["plain"]["public_id"])

        resp = client.post(
            f"/org/{org['slug']}/members",
            data={"user_email": target["email"], "role": "org_member"},
            follow_redirects=False,
        )

        assert resp.status_code == 302, resp.status_code
        assert _count_memberships(org["id"], target["id"]) == 0


# ===========================================================================
# Group C — role change POST (org.members.manage_roles)
# ===========================================================================

class TestChangeMemberRole:
    def _make_target(self, tag, role="org_member"):
        org, actors = _setup_org(tag)
        target = _make_user(f"{tag}_target")
        member = _make_member(org, target)
        assign_org_role(target["id"], org["id"], role)
        member.invalidate_permission_cache()
        db.session.commit()
        return org, actors, target

    def test_admin_changes_member_role(self, app):
        org, actors, target = self._make_target("c_adminchange")

        client = app.test_client()
        _login(client, actors["admin"]["public_id"])
        resp = client.post(
            f"/org/{org['slug']}/members/{target['public_id']}/role",
            data={"role": "org_admin"},
            follow_redirects=False,
        )

        assert resp.status_code == 302, resp.status_code
        assert _member_role_names(org["id"], target["id"]) == {"org_admin"}

    def test_admin_cannot_grant_owner(self, app):
        org, actors, target = self._make_target("c_noescal")

        client = app.test_client()
        _login(client, actors["admin"]["public_id"])
        resp = client.post(
            f"/org/{org['slug']}/members/{target['public_id']}/role",
            data={"role": "org_owner"},
            follow_redirects=False,
        )

        assert resp.status_code == 302, resp.status_code
        assert "org_owner" not in _member_role_names(org["id"], target["id"])
        assert _member_role_names(org["id"], target["id"]) == {"org_member"}

    def test_owner_can_grant_owner(self, app):
        org, actors, target = self._make_target("c_owngrant")

        client = app.test_client()
        _login(client, actors["owner"]["public_id"])
        resp = client.post(
            f"/org/{org['slug']}/members/{target['public_id']}/role",
            data={"role": "org_owner"},
            follow_redirects=False,
        )

        assert resp.status_code == 302, resp.status_code
        assert "org_owner" in _member_role_names(org["id"], target["id"])

    def test_target_owner_cannot_be_changed(self, app):
        org, actors, _target = self._make_target("c_protected")
        owner = actors["owner"]

        client = app.test_client()
        _login(client, owner["public_id"])
        resp = client.post(
            f"/org/{org['slug']}/members/{owner['public_id']}/role",
            data={"role": "org_admin"},
            follow_redirects=False,
        )

        assert resp.status_code == 302, resp.status_code
        assert _member_role_names(org["id"], owner["id"]) == {"org_owner"}

    def test_self_role_change_denied(self, app):
        org, actors, _target = self._make_target("c_self")

        client = app.test_client()
        _login(client, actors["admin"]["public_id"])
        resp = client.post(
            f"/org/{org['slug']}/members/{actors['admin']['public_id']}/role",
            data={"role": "org_member"},
            follow_redirects=False,
        )

        assert resp.status_code == 302, resp.status_code
        assert _member_role_names(org["id"], actors["admin"]["id"]) == {"org_admin"}

    def test_actor_without_manage_roles_denied(self, app):
        """hr_manager holds org.members.manage but NOT org.members.manage_roles."""
        org, actors, target = self._make_target("c_hr")

        client = app.test_client()
        _login(client, actors["hr"]["public_id"])
        resp = client.post(
            f"/org/{org['slug']}/members/{target['public_id']}/role",
            data={"role": "org_admin"},
            follow_redirects=False,
        )

        assert resp.status_code == 302, resp.status_code
        assert "org_admin" not in _member_role_names(org["id"], target["id"])


# ===========================================================================
# Group D — remove-member POST (org.members.manage or self-leave)
# ===========================================================================

class TestRemoveMember:
    def _make_target(self, tag, role="org_member"):
        org, actors = _setup_org(tag)
        target = _make_user(f"{tag}_target")
        member = _make_member(org, target)
        assign_org_role(target["id"], org["id"], role)
        member.invalidate_permission_cache()
        db.session.commit()
        return org, actors, target, member.id

    def test_owner_removes_non_owner(self, app):
        org, actors, target, member_id = self._make_target("d_rmowner")

        client = app.test_client()
        _login(client, actors["owner"]["public_id"])
        resp = client.post(
            f"/org/{org['slug']}/members/{target['public_id']}/remove",
            follow_redirects=False,
        )

        assert resp.status_code == 302, resp.status_code
        row = _member_row(org["id"], target["id"])
        assert row is not None and row.is_deleted is True
        assert OrgUserRole.query.filter_by(
            organisation_member_id=member_id
        ).count() == 0

    def test_admin_removes_non_owner(self, app):
        org, actors, target, _member_id = self._make_target("d_rmadmin")

        client = app.test_client()
        _login(client, actors["admin"]["public_id"])
        resp = client.post(
            f"/org/{org['slug']}/members/{target['public_id']}/remove",
            follow_redirects=False,
        )

        assert resp.status_code == 302, resp.status_code
        assert _member_row(org["id"], target["id"]).is_deleted is True

    def test_remove_purges_direct_permissions(self, app):
        org, actors, target, member_id = self._make_target("d_purge")
        perm = Permission.query.filter_by(name="org.members.view").first()
        assert perm is not None
        db.session.add(
            OrgMemberPermission(
                member_id=member_id, permission_id=perm.id, granted=True
            )
        )
        db.session.commit()

        client = app.test_client()
        _login(client, actors["owner"]["public_id"])
        resp = client.post(
            f"/org/{org['slug']}/members/{target['public_id']}/remove",
            follow_redirects=False,
        )

        assert resp.status_code == 302, resp.status_code
        assert OrgMemberPermission.query.filter_by(member_id=member_id).count() == 0

    def test_owner_cannot_be_removed(self, app):
        org, actors, _target, _member_id = self._make_target("d_protected")

        client = app.test_client()
        _login(client, actors["owner"]["public_id"])
        resp = client.post(
            f"/org/{org['slug']}/members/{actors['owner']['public_id']}/remove",
            follow_redirects=False,
        )

        assert resp.status_code == 302, resp.status_code
        assert _member_role_names(org["id"], actors["owner"]["id"]) == {"org_owner"}
        assert _member_row(org["id"], actors["owner"]["id"]).is_deleted is False

    def test_plain_member_can_self_leave(self, app):
        org, actors, _target, _member_id = self._make_target("d_selfleave")

        client = app.test_client()
        _login(client, actors["plain"]["public_id"])
        resp = client.post(
            f"/org/{org['slug']}/members/{actors['plain']['public_id']}/remove",
            follow_redirects=False,
        )

        assert resp.status_code == 302, resp.status_code
        assert _member_row(org["id"], actors["plain"]["id"]).is_deleted is True

    def test_plain_member_cannot_remove_others(self, app):
        org, actors, target, _member_id = self._make_target("d_noperm")

        client = app.test_client()
        _login(client, actors["plain"]["public_id"])
        resp = client.post(
            f"/org/{org['slug']}/members/{target['public_id']}/remove",
            follow_redirects=False,
        )

        assert resp.status_code == 302, resp.status_code
        assert _member_row(org["id"], target["id"]).is_deleted is False


# ===========================================================================
# Group E — template render + fail-closed module gates
# ===========================================================================

class TestTemplateAndGates:
    def test_org_dashboard_renders_for_owner(self, app):
        org, actors = _setup_org("e_dash")
        client = app.test_client()
        _login(client, actors["owner"]["public_id"])

        resp = client.get(f"/org/{org['slug']}/dashboard")

        assert resp.status_code == 200, resp.status_code

    def test_org_selector_renders_with_multiple_memberships(self, app):
        org_a, actors_a = _setup_org("e_sela")
        org_b, _actors_b = _setup_org("e_selb")
        owner = actors_a["owner"]
        member_b = _make_member(org_b, owner)
        assign_org_role(owner["id"], org_b["id"], "org_admin")
        member_b.invalidate_permission_cache()
        db.session.commit()

        client = app.test_client()
        _login(client, owner["public_id"])
        resp = client.get("/org/")

        assert resp.status_code == 200, resp.status_code
        assert org_a["legal_name"].encode() in resp.data
        assert org_b["legal_name"].encode() in resp.data

    def test_settings_gate_fail_closed(self, app):
        org, actors = _setup_org("e_settings")

        owner_client = app.test_client()
        _login(owner_client, actors["owner"]["public_id"])
        assert owner_client.get(f"/org/{org['slug']}/settings").status_code == 200

        plain_client = app.test_client()
        _login(plain_client, actors["plain"]["public_id"])
        resp = plain_client.get(f"/org/{org['slug']}/settings")
        assert resp.status_code == 302, resp.status_code
        assert "/dashboard" in resp.headers.get("Location", "")

    def test_accommodation_gate_fail_closed(self, app):
        org, actors = _setup_org("e_accom")

        owner_client = app.test_client()
        _login(owner_client, actors["owner"]["public_id"])
        assert owner_client.get(f"/org/{org['slug']}/accommodation").status_code == 200

        plain_client = app.test_client()
        _login(plain_client, actors["plain"]["public_id"])
        resp = plain_client.get(f"/org/{org['slug']}/accommodation")
        assert resp.status_code == 302, resp.status_code
        assert "/dashboard" in resp.headers.get("Location", "")

    def test_transport_gate_fail_closed(self, app):
        org, actors = _setup_org("e_transport")

        owner_client = app.test_client()
        _login(owner_client, actors["owner"]["public_id"])
        assert owner_client.get(f"/org/{org['slug']}/transport").status_code == 200

        plain_client = app.test_client()
        _login(plain_client, actors["plain"]["public_id"])
        resp = plain_client.get(f"/org/{org['slug']}/transport")
        assert resp.status_code == 302, resp.status_code
        assert "/dashboard" in resp.headers.get("Location", "")