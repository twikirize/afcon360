"""SEC-FALLBACK behavioral proof: require_role denies the role-less.

Regression for the bound-method defect at app/auth/decorators.py:280,
where `user.is_super_admin` (uncalled) was truthy for every
authenticated user, granting all require_role-gated routes. The matrix
proves the fix denies A/B while preserving C-F. No database rows are
created; the TransportPermission fallback query runs against the test
DB and returns empty for the stub ids.
"""
import uuid

import pytest
from werkzeug.exceptions import Forbidden

from app.auth import decorators as decorators_mod
from app.auth.decorators import require_role

_MOD = ("moderator", "admin", "super_admin", "owner")


def _make_user(db_session, role_names):
    """Real (flushed, uncommitted) User row so session merge works.

    Rows vanish with the db_session rollback at teardown — no cleanup.
    """
    from app.identity.models.roles_permission import Role
    from app.identity.models.user import User, UserRole

    uid = uuid.uuid4().hex[:8]
    user = User(
        username=f"srfb_{uid}",
        email=f"srfb_{uid}@x.test",
        is_verified=True,
        is_active=True,
    )
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
    db_session.flush()
    # Expire so role walks hit the DB like production reads.
    db_session.expire_all()
    return db_session.merge(user)


def _guarded():
    @require_role(*_MOD)
    def view():
        return "guarded-ok"

    return view


def _run(app, db_session, user, monkeypatch):
    monkeypatch.setattr(decorators_mod, "_get_current_user", lambda: user)
    with app.test_request_context("/probe"):
        return _guarded()()


def test_anonymous_redirected_to_login(app, db_session, monkeypatch):
    # CASE 1: no identity at all -> login redirect (not 403).
    monkeypatch.setattr(decorators_mod, "_get_current_user", lambda: None)
    with app.test_request_context("/probe"):
        resp = _guarded()()
    assert resp.status_code == 302
    assert "/login" in resp.headers.get("Location", "")


def test_a_no_role_denied(app, db_session, monkeypatch):
    with pytest.raises(Forbidden):
        _run(app, db_session, _make_user(db_session, []), monkeypatch)


def test_b_user_only_denied(app, db_session, monkeypatch):
    with pytest.raises(Forbidden):
        _run(app, db_session, _make_user(db_session, ["user"]), monkeypatch)


def test_c_moderator_allowed(app, db_session, monkeypatch):
    assert (
        _run(app, db_session, _make_user(db_session, ["moderator"]), monkeypatch)
        == "guarded-ok"
    )


def test_d_admin_allowed(app, db_session, monkeypatch):
    assert (
        _run(app, db_session, _make_user(db_session, ["admin"]), monkeypatch)
        == "guarded-ok"
    )


def test_e_super_admin_allowed(app, db_session, monkeypatch):
    assert (
        _run(app, db_session, _make_user(db_session, ["super_admin"]), monkeypatch)
        == "guarded-ok"
    )


def test_f_owner_allowed(app, db_session, monkeypatch):
    assert (
        _run(app, db_session, _make_user(db_session, ["owner"]), monkeypatch)
        == "guarded-ok"
    )
