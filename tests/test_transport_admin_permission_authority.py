"""Phase D0 — resolve the role-to-permission contradiction for Transport Admin.

Contradiction under test
------------------------
``transport_admin`` is the canonical global Transport-domain administrative
role, yet Gate 1 discovery proved it carried **zero** Transport permissions,
while ``admin_required`` (platform admin) and the defective
``app.transport.decorator.role_required`` decided the Transport admin surface.

Resolution under test
---------------------
The canonical runtime authorization path is the existing global permission
system (``Role`` -> ``RolePermission`` -> ``Permission`` resolved through
``app.auth.policy.can`` / ``app.auth.decorators.require_permission``):

    transport_admin  ->  transport.view
                     ->  transport.manage
    transport.settings is intentionally NOT granted (owner/super_admin only).

The ``/admin/transport-admin`` family consumes ``require_permission`` instead
of ``require_role("transport_admin")``. Driver, Organisation and Moderator
authority paths are intentionally untouched.

These tests exercise the real runtime path (seeded DB + HTTP requests + the
``can`` resolver), not a static dictionary.
"""
import uuid

import pytest

from app.extensions import db

TRANSPORT_ADMIN = "transport_admin"
ENTRY = "/admin/transport-admin"
DRIVERS_VIEW = "/admin/transport-admin/drivers"
DRIVER_VERIFY = "/admin/transport-admin/drivers/1/verify"
SETTINGS = "/admin/transport-admin/settings"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_user(tag, role_names=()):
    """Create a committed user holding the named global roles.

    Returns ``(public_id, internal_id)``.
    """
    from app.identity.models.roles_permission import Role
    from app.identity.models.user import User, UserRole

    uid = uuid.uuid4().hex[:8]
    user = User(
        public_id=str(uuid.uuid4()),
        username=f"d0_{tag}_{uid}",
        email=f"d0_{tag}_{uid}@example.com",
        is_verified=True,
        is_active=True,
        email_verified=True,
    )
    user.set_password("Password123!")
    db.session.add(user)
    db.session.flush()

    for name in role_names:
        role = Role.query.filter_by(name=name, scope="global").first()
        assert role is not None, f"global role {name!r} must be seeded"
        db.session.add(UserRole(user_id=user.id, role_id=role.id))

    db.session.commit()
    return user.public_id, user.id


def _make_driver(app, tag):
    """Create a user with a live PENDING DriverProfile and return (public_id, id)."""
    from app.identity.models.user import User, UserRole
    from app.identity.models.roles_permission import Role
    from app.transport.models import (
        ComplianceStatus,
        DriverProfile,
        VerificationTier,
    )

    uid = uuid.uuid4().hex[:8]
    user = User(
        public_id=str(uuid.uuid4()),
        username=f"d0drv_{tag}_{uid}",
        email=f"d0drv_{tag}_{uid}@example.com",
        is_verified=True,
        is_active=True,
        email_verified=True,
    )
    user.set_password("Password123!")
    db.session.add(user)
    db.session.flush()

    user_role = Role.query.filter_by(name="user", scope="global").first()
    if user_role is not None:
        db.session.add(UserRole(user_id=user.id, role_id=user_role.id))

    db.session.add(
        DriverProfile(
            user_id=user.id,
            driver_code=f"D0-{uid[:6].upper()}",
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

    driver = DriverProfile.query.filter_by(user_id=user.id, is_deleted=False).first()
    driver_context_id = str(getattr(driver, "driver_code", "") or "")
    assert driver_context_id, "driver context id (driver_code) must exist"
    return user.public_id, driver_context_id


def _login(client, public_id, *, context_type=None, context_role=None):
    with client.session_transaction() as sess:
        sess["_user_id"] = public_id
        sess["_fresh"] = True
        if context_type:
            sess["active_context_type"] = context_type
            sess["active_context_id"] = public_id
            sess["active_role"] = context_role


def _platform_login(client, public_id, role):
    """Select the PLATFORM operating context for the active global role."""
    _login(client, public_id, context_type="platform", context_role=role)


def _clear_cache():
    try:
        from app.extensions import cache

        cache.clear()
    except Exception:
        pass


def _get(client, url):
    _clear_cache()
    return client.get(url)


def _post(client, url, data=None):
    _clear_cache()
    return client.post(url, data=data or {})


def _assert_not_forbidden(resp):
    """Authorization passed: never 403 and never a bounce to login."""
    assert resp.status_code != 403, resp.status_code
    if resp.status_code == 302:
        location = resp.headers.get("Location", "")
        assert "login" not in location, location


def _assert_denied(resp):
    """Authorization denied.

    Routes under the ``admin`` blueprint convert ``abort(403)`` into a redirect
    to the safe landing page (``/``) for non-platform-admins via
    ``admin_bp.errorhandler(403)``. Denial is therefore observable as either a
    hard 403 (non-admin blueprints) or a 302 to ``/`` — never a login bounce and
    never a 200/other redirect.
    """
    if resp.status_code == 403:
        return
    assert resp.status_code == 302, (resp.status_code, resp.headers.get("Location"))
    location = resp.headers.get("Location", "")
    assert "login" not in location, location
    assert location.rstrip("/") in ("", "http:", "https:"), location


# ---------------------------------------------------------------------------
# A. Role now carries the canonical permissions (static + runtime resolver)
# ---------------------------------------------------------------------------

class TestTransportAdminPermissionMapping:
    def test_transport_admin_role_carries_view_and_manage_only(self, app):
        with app.app_context():
            from app.identity.models.roles_permission import Role

            role = Role.query.filter_by(name=TRANSPORT_ADMIN, scope="global").first()
            assert role is not None, "transport_admin role must be seeded"

            names = role.permission_names
            assert "transport.view" in names
            assert "transport.manage" in names
            assert "transport.settings" not in names

    def test_can_resolver_grants_transport_authority(self, app):
        with app.app_context():
            from app.auth.policy import can
            from app.identity.models.user import User

            _, internal_id = _make_user("resolver", [TRANSPORT_ADMIN])
            with app.test_request_context():
                user = db.session.get(User, internal_id)
                assert can(user, "transport.view") is True
                assert can(user, "transport.manage") is True
                assert can(user, "transport.settings") is False


# ---------------------------------------------------------------------------
# B/C/E. Canonical entry point
# ---------------------------------------------------------------------------

class TestCanonicalEntryPoint:
    def test_transport_admin_allowed_on_entry_point(self, app, client):
        with app.app_context():
            public_id, _ = _make_user("ta", [TRANSPORT_ADMIN])
        _platform_login(client, public_id, TRANSPORT_ADMIN)

        _assert_not_forbidden(_get(client, ENTRY))
        _assert_not_forbidden(_get(client, DRIVERS_VIEW))

    def test_ordinary_user_denied_on_entry_point(self, app, client):
        with app.app_context():
            public_id, _ = _make_user("plain", ["user"])
        _platform_login(client, public_id, "user")

        _assert_denied(_get(client, ENTRY))
        _assert_denied(_get(client, DRIVERS_VIEW))

    def test_platform_admin_retains_transport_access(self, app, client):
        with app.app_context():
            public_id, _ = _make_user("admin", ["admin"])
        _platform_login(client, public_id, "admin")

        _assert_not_forbidden(_get(client, ENTRY))
        _assert_not_forbidden(_get(client, DRIVERS_VIEW))

    def test_owner_retains_transport_access(self, app, client):
        with app.app_context():
            public_id, _ = _make_user("owner", ["owner"])
        _platform_login(client, public_id, "owner")

        _assert_not_forbidden(_get(client, ENTRY))

    def test_transport_admin_denied_settings(self, app, client):
        """transport.settings is intentionally retained for owner/super_admin."""
        with app.app_context():
            public_id, _ = _make_user("ta_settings", [TRANSPORT_ADMIN])
        _platform_login(client, public_id, TRANSPORT_ADMIN)

        _assert_denied(_get(client, SETTINGS))


# ---------------------------------------------------------------------------
# D. Driver separation
# ---------------------------------------------------------------------------

class TestDriverSeparation:
    def test_driver_workspace_allowed_and_transport_admin_denied(self, app, client):
        with app.app_context():
            public_id, driver_context_id = _make_driver(app, "sep")
        _login(client, public_id, context_type="driver", context_role="driver")
        with client.session_transaction() as sess:
            sess["active_context_id"] = driver_context_id

        workspace = _get(client, "/transport/driver-dashboard")
        assert workspace.status_code == 200, workspace.status_code

        _assert_denied(_get(client, ENTRY))


# ---------------------------------------------------------------------------
# F. View vs manage distinction
# ---------------------------------------------------------------------------

class TestViewManageDistinction:
    def test_view_only_role_can_read_but_not_mutate(self, app, client):
        with app.app_context():
            from app.identity.models.roles_permission import (
                Permission,
                assign_permission_to_role,
                get_or_create_role,
            )

            role = get_or_create_role(
                "d0_transport_view_only",
                description="Phase D0 test role (view only)",
                level=99,
            )
            perm = Permission.query.filter_by(name="transport.view").first()
            assert perm is not None, "transport.view must be seeded"
            assign_permission_to_role(role, perm)

            public_id, _ = _make_user("viewonly", [role.name])

        _login(client, public_id)

        _assert_not_forbidden(_get(client, DRIVERS_VIEW))
        _assert_denied(_post(client, DRIVER_VERIFY))

    def test_transport_admin_can_reach_mutation_guard(self, app, client):
        """transport_admin holds transport.manage, so the mutation guard passes;
        the response is not 403 (404 for a missing driver is acceptable)."""
        with app.app_context():
            public_id, _ = _make_user("ta_mutate", [TRANSPORT_ADMIN])
        _login(client, public_id)

        resp = _post(client, DRIVER_VERIFY)
        assert resp.status_code != 403, resp.status_code


# ---------------------------------------------------------------------------
# Direct contradiction test — authority is permission-driven, not role-name-driven
# ---------------------------------------------------------------------------

class TestPermissionDrivenAuthority:
    def test_role_name_alone_does_not_confer_authority(self, app):
        with app.app_context():
            from app.identity.models.roles_permission import get_or_create_role

            role = get_or_create_role(
                "d0_fake_transport_admin",
                description="Phase D0 test role (no permissions)",
                level=98,
            )
            role_id = role.id
            _, internal_id = _make_user("fakeadmin", [role.name])

        # BEFORE: a transport-admin-shaped role with no permission is denied.
        with app.test_request_context():
            from app.auth.policy import can
            from app.identity.models.user import User

            user = db.session.get(User, internal_id)
            assert can(user, "transport.view") is False

        # AFTER: the canonical permission grant is what confers authority.
        with app.app_context():
            from app.identity.models.roles_permission import (
                Permission,
                Role,
                assign_permission_to_role,
            )

            role = db.session.get(Role, role_id)
            perm = Permission.query.filter_by(name="transport.view").first()
            assert perm is not None
            assign_permission_to_role(role, perm)

        with app.test_request_context():
            from app.auth.policy import can
            from app.identity.models.user import User

            user = db.session.get(User, internal_id)
            assert can(user, "transport.view") is True
