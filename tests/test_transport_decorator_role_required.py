"""T-08 behavioral proof: role_required gates on actual global roles.

The old body compared a role-name string against UserRole ORM objects
(which define no __eq__), so the check was always True and every
decorated route redirected — even for admins and owners. These cases
use a minimal app (no transport routes, no database): stub users with
UserRole-shaped roles exercise the real decorator + the real
has_global_role.
"""
import pytest
from flask import Blueprint, Flask
from flask_login import LoginManager

from app.transport.decorator import role_required


class _StubRole:
    def __init__(self, name):
        self.name = name


class _StubUserRole:
    def __init__(self, name):
        self.role = _StubRole(name)


class _StubUser:
    def __init__(self, uid, role_names, authenticated=True):
        self.id = uid
        self.is_authenticated = authenticated
        self.is_active = True
        self.roles = [_StubUserRole(n) for n in role_names]

    def get_id(self):
        return str(self.id)


@pytest.fixture()
def mini_app():
    app = Flask(__name__)
    app.secret_key = "t08-test-secret"
    store = {}
    app.extensions["t08_store"] = store

    login_manager = LoginManager(app)

    @login_manager.user_loader
    def load_user(uid):
        return store.get(str(uid))

    auth_bp = Blueprint("auth", __name__)

    @auth_bp.route("/login")
    def login():
        return "login-page"

    transport_bp = Blueprint("transport", __name__)

    @transport_bp.route("/home")
    def home():
        return "transport-home"

    @transport_bp.route("/guarded")
    @role_required("admin")
    def guarded():
        return "guarded-ok"

    app.register_blueprint(auth_bp)
    app.register_blueprint(transport_bp)
    return app


def _login_as(mini_app, user):
    mini_app.extensions["t08_store"][str(user.id)] = user
    client = mini_app.test_client()
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user.id)
        sess["_fresh"] = True
    return client


def test_anonymous_redirects_to_login_with_next(mini_app):
    resp = mini_app.test_client().get("/guarded")
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]
    assert "next=" in resp.headers["Location"]


def test_non_admin_redirects_to_transport_home(mini_app):
    client = _login_as(mini_app, _StubUser("u1", ["user"]))
    resp = client.get("/guarded")
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/home")
    with client.session_transaction() as sess:
        flashes = [m for _c, m in sess.get("_flashes", [])]
    assert any("do not have permission" in m for m in flashes)


def test_admin_reaches_view(mini_app):
    client = _login_as(mini_app, _StubUser("a1", ["admin"]))
    resp = client.get("/guarded")
    assert resp.status_code == 200
    assert resp.get_data(as_text=True) == "guarded-ok"


def test_owner_bypass_reaches_view(mini_app):
    client = _login_as(mini_app, _StubUser("o1", ["owner"]))
    resp = client.get("/guarded")
    assert resp.status_code == 200
    assert resp.get_data(as_text=True) == "guarded-ok"
