"""BL-23 behavioral proof: transport permission guards deny the ordinary.

Covers the three fixed sites (decorators.py:841,
routes.py:1757/:1846) with real User rows on the test DB (rollback
cleaned) and the real request/route paths. Matrix mirrors
tests/test_auth_require_role.py style.
"""
import uuid

import pytest
from werkzeug.exceptions import Forbidden

pytestmark = pytest.mark.usefixtures("db_session")


def _make_user(db_session, role_names):
    from app.identity.models.roles_permission import Role
    from app.identity.models.user import User, UserRole

    uid = uuid.uuid4().hex[:8]
    user = User(username=f"b23_{uid}", email=f"b23_{uid}@x.test",
                is_verified=True, is_active=True)
    user.set_password("x")
    db_session.add(user)
    db_session.flush()
    for name in role_names:
        role = Role.query.filter_by(name=name).first()
        if role is None:
            role = Role(name=name, scope="global")
            db_session.add(role)
            db_session.flush()
        db_session.add(UserRole(user_id=user.id, role_id=role.id))
    db_session.commit()
    return user.id, str(user.public_id)


def _fresh_user(db_session, uid):
    from app.identity.models.user import User

    return db_session.get(User, uid)


def _login(client, pid):
    with client.session_transaction() as sess:
        sess["_user_id"] = pid
        sess["_fresh"] = True
    return client


def _guarded(monkeypatch, user):
    import app.auth.decorators as dec

    monkeypatch.setattr(dec, "_get_current_user", lambda: user)

    @dec.transport_permission_required("manage_drivers")
    def view():
        return "reached"

    return view


class TestDecoratorMatrix:
    def test_anonymous_redirected_to_login(self, app):
        from app.auth.decorators import transport_permission_required

        @transport_permission_required("manage_drivers")
        def view():
            return "reached"  # pragma: no cover

        with app.test_request_context("/probe"):
            resp = view()
        assert resp.status_code == 302
        assert "/login" in resp.headers.get("Location", "")

    def test_ordinary_denied(self, app, db_session, monkeypatch):
        uid, _pid = _make_user(db_session, ["user"])
        with pytest.raises(Forbidden):
            _guarded(monkeypatch, _fresh_user(db_session, uid))()

    def test_authorized_grant_holder_allowed(
        self, app, db_session, monkeypatch
    ):
        from app.core.transport_permissions import TransportPermission

        uid, _pid = _make_user(db_session, ["user"])
        TransportPermission.grant_permission(
            grantee_user_id=uid, grantee_role="admin",
            can_manage_drivers=True, can_manage_vehicles=False,
            can_view_dashboard=False, granted_by_user_id=uid,
        )
        db_session.flush()
        with app.test_request_context("/probe"):
            assert (
                _guarded(monkeypatch, _fresh_user(db_session, uid))()
                == "reached"
            )

    def test_super_admin_allowed(self, app, db_session, monkeypatch):
        uid, _pid = _make_user(db_session, ["super_admin"])
        with app.test_request_context("/probe"):
            assert (
                _guarded(monkeypatch, _fresh_user(db_session, uid))()
                == "reached"
            )

    def test_owner_allowed(self, app, db_session, monkeypatch):
        uid, _pid = _make_user(db_session, ["owner"])
        with app.test_request_context("/probe"):
            assert (
                _guarded(monkeypatch, _fresh_user(db_session, uid))()
                == "reached"
            )


class TestGrantRoute:
    def test_ordinary_denied_no_row(self, app, client, db_session):
        from app.core.transport_permissions import TransportPermission

        uid, pid = _make_user(db_session, ["user"])
        authed = _login(client, pid)
        assert TransportPermission.get_active_by_user(uid) == []
        authed.post(
            "/grant-transport-permission",
            json={"grantee_user_id": uid, "grantee_role": "admin",
                  "can_manage_drivers": True},
            follow_redirects=False,
        )
        db_session.expire_all()
        assert TransportPermission.get_active_by_user(uid) == []

    def test_owner_allowed_row_created(self, app, client, db_session):
        from app.core.transport_permissions import TransportPermission

        _oid, owner_pid = _make_user(db_session, ["owner"])
        target_uid, _tpid = _make_user(db_session, ["user"])
        authed = _login(client, owner_pid)
        # Redirect integrity (post auth.index repair): the success path
        # redirects to the transport admin dashboard — a clean 302 AFTER
        # the mutation commits. Asserted here is the security-relevant
        # behavior: the row is created for owners.
        authed.post(
            "/grant-transport-permission",
            json={"grantee_user_id": target_uid, "grantee_role": "admin",
                  "can_manage_drivers": True},
            follow_redirects=False,
        )
        db_session.expire_all()
        perms = TransportPermission.get_active_by_user(target_uid)
        assert len(perms) == 1
        assert perms[0].can_manage_drivers is True


class TestRevokeRoute:
    def _granted(self, db_session, granter_id=None):
        from app.core.transport_permissions import TransportPermission

        perm = TransportPermission.grant_permission(
            grantee_user_id=granter_id, grantee_role="admin",
            can_manage_drivers=True, can_manage_vehicles=False,
            can_view_dashboard=False, granted_by_user_id=granter_id,
        )
        db_session.flush()
        return perm.id if hasattr(perm, "id") else perm["id"]

    def test_ordinary_denied_row_remains(self, app, client, db_session):
        from app.core.transport_permissions import TransportPermission

        uid, pid = _make_user(db_session, ["user"])
        perm_id = self._granted(db_session, granter_id=uid)
        authed = _login(client, pid)
        authed.post(
            "/revoke-transport-permission",
            json={"permission_id": perm_id},
            follow_redirects=False,
        )
        db_session.expire_all()
        assert len(TransportPermission.get_active_by_user(uid)) == 1

    def test_owner_allowed_row_revoked(self, app, client, db_session):
        from app.core.transport_permissions import TransportPermission

        _oid, owner_pid = _make_user(db_session, ["owner"])
        target_uid, _tpid = _make_user(db_session, ["user"])
        perm_id = self._granted(db_session, granter_id=target_uid)
        authed = _login(client, owner_pid)
        authed.post(
            "/revoke-transport-permission",
            json={"permission_id": perm_id},
            follow_redirects=False,
        )
        db_session.expire_all()
        assert TransportPermission.get_active_by_user(target_uid) == []


class TestRedirectIntegrity:
    """Dangling auth.index follow-up: every grant/revoke response must be
    a clean redirect to a registered endpoint — never a 500."""

    def test_deny_redirects_to_user_dashboard(self, app, client, db_session):
        uid, pid = _make_user(db_session, ["user"])
        resp = _login(client, pid).post(
            "/grant-transport-permission",
            json={"grantee_user_id": uid, "grantee_role": "admin",
                  "can_manage_drivers": True},
            follow_redirects=False,
        )
        assert resp.status_code == 302, resp.status_code
        assert resp.headers.get("Location") == "/user/dashboard"

    def test_allow_redirects_to_transport_admin(
        self, app, client, db_session
    ):
        _oid, owner_pid = _make_user(db_session, ["owner"])
        target_uid, _tpid = _make_user(db_session, ["user"])
        resp = _login(client, owner_pid).post(
            "/grant-transport-permission",
            json={"grantee_user_id": target_uid, "grantee_role": "admin",
                  "can_manage_drivers": True},
            follow_redirects=False,
        )
        assert resp.status_code == 302, resp.status_code
        assert resp.headers.get("Location") == "/admin/transport-admin"

    def test_revoke_deny_redirects_to_user_dashboard(
        self, app, client, db_session
    ):
        _uid, pid = _make_user(db_session, ["user"])
        resp = _login(client, pid).post(
            "/revoke-transport-permission",
            json={"permission_id": 987654321},
            follow_redirects=False,
        )
        assert resp.status_code == 302, resp.status_code
        assert resp.headers.get("Location") == "/user/dashboard"

    def test_revoke_allow_redirects_to_transport_admin(
        self, app, client, db_session
    ):
        from app.core.transport_permissions import TransportPermission

        _oid, owner_pid = _make_user(db_session, ["owner"])
        target_uid, _tpid = _make_user(db_session, ["user"])
        perm = TransportPermission.grant_permission(
            grantee_user_id=target_uid, grantee_role="admin",
            can_manage_drivers=True, can_manage_vehicles=False,
            can_view_dashboard=False, granted_by_user_id=target_uid,
        )
        db_session.flush()
        perm_id = perm.id if hasattr(perm, "id") else perm["id"]
        resp = _login(client, owner_pid).post(
            "/revoke-transport-permission",
            json={"permission_id": perm_id},
            follow_redirects=False,
        )
        assert resp.status_code == 302, resp.status_code
        assert resp.headers.get("Location") == "/admin/transport-admin"
        db_session.expire_all()
        assert TransportPermission.get_active_by_user(target_uid) == []
