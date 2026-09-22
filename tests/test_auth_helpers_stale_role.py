"""U-04: stale active-role clearing stays centralized and effective.

Sets session["active_global_role"] to a role the user no longer holds,
calls has_global_role(), and asserts the stale key is cleared.
"""
from types import SimpleNamespace

from flask import Flask, session

from app.auth.helpers import _clear_stale_active_role, has_global_role


def _request_app():
    app = Flask(__name__)
    app.secret_key = "u04-test-secret"
    return app


def _user_with_roles(*role_names):
    return SimpleNamespace(
        roles=[SimpleNamespace(role=SimpleNamespace(name=n)) for n in role_names]
    )


def test_stale_active_role_cleared_by_read():
    assert callable(_clear_stale_active_role)
    app = _request_app()
    user = _user_with_roles("user")  # does NOT hold "admin"
    with app.test_request_context("/"):
        session["active_global_role"] = "admin"
        assert has_global_role(user, "user") is True
        assert "active_global_role" not in session
