"""
BACKLOG:1179 — Authentication & Identity Security Hardening — RED proof tests.

Each test documents a PROVEN production defect that FAILS on the current tree
and turns GREEN after the minimal repair:

  [D1] Anonymous access to decorator-guarded routes -> HTTP 500 BuildError.
       The code calls url_for("auth_routes.login") but the blueprint is
       registered as "auth" (app/auth/routes.py:23), so the endpoint does not
       exist. Proven reproduction: anonymous GET /monitor (app/monitor/routes.py
       uses @require_role with no outer @login_required) raises BuildError at
       app/auth/decorators.py:261.

  [D2] Session fixation: the Flask-Session SID is never rotated across the
       anonymous -> authenticated transition. login_user() mutates the
       pre-auth session in place and session_interface.regenerate() (exists in
       flask_session 0.8.0) is never called.

  [D3,D4,D5] MFA-enabled users cannot log in. authenticate_user() returns
       AuthResult.MFA_REQUIRED for any user with mfa_enabled=True
       (app/auth/services.py:469-492) but the login route only handles SUCCESS
       (app/auth/routes.py:795); every other result is reported as "Invalid
       username or password" (routes.py:989). No 2FA challenge exists:
       templates/login.html has no mfa_code field and
       app/auth/routes.py:/mfa/<user_id> is a stub.

Run:  pytest tests/test_backlog1179_auth_security.py -v
"""
import importlib.util
import uuid
from urllib.parse import urlparse

import pytest

from app.extensions import db
from app.identity.models.roles_permission import get_or_create_role
from app.identity.models.user import MFASecret, User, UserRole


def _make_user(app, *, mfa=False, secret=None, username=None,
               password="TestPassword123!"):
    """Create a verified 'user'-role account (same shape the sign-up pipeline
    leaves behind), optionally with an active TOTP MFA method."""
    with app.app_context():
        user_role = get_or_create_role("user", level=6)
        uname = username or f"bl1179_{uuid.uuid4().hex[:10]}"
        user = User(
            public_id=str(uuid.uuid4()),
            username=uname,
            email=f"{uname}@example.com",
        )
        user.set_password(password)
        user.is_active = True
        user.is_verified = True
        user.email_verified = True
        if mfa:
            user.mfa_enabled = True
        db.session.add(user)
        db.session.flush()
        if mfa:
            db.session.add(MFASecret(
                user_id=user.id,
                mfa_type="totp",
                secret=secret,
                is_active=True,
            ))
        db.session.add(UserRole(user_id=user.id, role_id=user_role.id))
        db.session.commit()
        return uname


def _pyotp():
    """Lazily import pyotp; skip the MFA tests when the dependency is absent
    (pyotp is required by app/auth/routes.py:_verify_mfa_token + mfa_enable
    but is NOT currently installed in the venv — see BACKLOG:1179 D6)."""
    try:
        import pyotp  # noqa: PLC0415
        return pyotp
    except ImportError:
        pytest.skip("pyotp not installed in this environment (D6 — missing dependency)")


def _login(client, username, password, mfa_code=None):
    """POST /login with real form data, clearing the Flask-Caching user cache
    first so user_loader never serves a stale detached instance."""
    from app.extensions import cache
    try:
        cache.clear()
    except Exception:
        pass
    data = {"username": username, "password": password}
    if mfa_code is not None:
        data["mfa_code"] = mfa_code
    return client.post("/login", data=data, follow_redirects=False)


def _session_sid(response):
    """Return the raw Flask-Session 'session' cookie value from a response's
    Set-Cookie headers (SESSION_USE_SIGNER is False, so the value is the SID)."""
    for header in response.headers.getlist("Set-Cookie"):
        head, _, _ = header.partition(";")
        key, sep, value = head.partition("=")
        if sep and key.strip() == "session":
            return value
    return None


# ---------------------------------------------------------------------------
# [D1] BuildError: anonymous guarded route must redirect to login, not 500
# ---------------------------------------------------------------------------

def test_d1_anonymous_guarded_route_redirects_to_login(app):
    client = app.test_client()
    resp = client.get("/monitor")
    assert resp.status_code == 302, (
        f"anonymous GET /monitor should redirect to login; got HTTP "
        f"{resp.status_code} (today: BuildError 500 at decorators.py:261)"
    )
    assert urlparse(resp.headers.get("Location", "")).path == "/login"


# ---------------------------------------------------------------------------
# [D2] Session fixation: the SID must rotate on login
# ---------------------------------------------------------------------------

def test_d2_session_sid_rotates_on_login(app):
    username = _make_user(app, mfa=False)
    client = app.test_client()

    # Anonymous pre-auth session (attacker-supplied SID): an invalid login
    # POST produces the server-side session cookie the victim would carry.
    anonymous = client.post(
        "/login",
        data={"username": "no_such_user_9230", "password": "wrongpass"},
    )
    sid_before = _session_sid(anonymous)
    assert sid_before, "anonymous request did not emit an sid cookie"

    resp = _login(client, username, "TestPassword123!")
    assert resp.status_code == 302, f"login failed: {resp.status_code}"

    sid_after = _session_sid(resp)
    assert sid_after, "no sid cookie emitted after login"
    assert sid_after != sid_before, (
        "session id was NOT rotated across the anonymous->authenticated "
        "transition (session fixation)"
    )


# ---------------------------------------------------------------------------
# [D3-D5] MFA-enabled users: challenge, then complete, then reject bad code
# ---------------------------------------------------------------------------

def test_d3_mfa_user_receives_challenge_not_generic_failure(app):
    pyotp = _pyotp()
    secret = pyotp.random_base32()
    username = _make_user(app, mfa=True, secret=secret)
    client = app.test_client()

    resp = _login(client, username, "TestPassword123!")
    body = resp.data.decode("utf-8", "replace")

    assert b"Invalid username or password." not in resp.data, (
        "a valid password for an MFA-enabled user was misreported as invalid "
        "credentials instead of presenting a 2FA challenge"
    )
    assert "mfa_code" in body, (
        "no 2FA challenge (mfa_code field) was presented to the client"
    )


def test_d4_mfa_user_completes_login_with_valid_totp(app):
    pyotp = _pyotp()
    secret = pyotp.random_base32()
    username = _make_user(app, mfa=True, secret=secret)
    client = app.test_client()

    code = pyotp.TOTP(secret).now()
    resp = _login(client, username, "TestPassword123!", mfa_code=code)
    assert resp.status_code == 302, (
        f"login with a valid TOTP code failed: HTTP {resp.status_code} "
        "(MFA-enabled accounts cannot complete login today)"
    )


def test_d5_mfa_user_rejected_with_wrong_totp(app):
    pyotp = _pyotp()
    secret = pyotp.random_base32()
    username = _make_user(app, mfa=True, secret=secret)
    client = app.test_client()

    resp = _login(client, username, "TestPassword123!", mfa_code="000000")
    assert resp.status_code == 200
    body = resp.data.decode("utf-8", "replace")
    assert "mfa_code" in body, (
        "wrong TOTP should keep the user on the 2FA challenge, not fall out "
        "to a generic credential failure"
    )