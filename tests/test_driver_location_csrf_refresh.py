"""CSRF-expiry recovery for the driver location ping.

Production symptom: a driver dashboard left open past ``WTF_CSRF_TIME_LIMIT``
keeps reusing the CSRF token captured once at page load, so every
``POST /api/transport/drivers/<id>/location`` is rejected with a 400 and the
driver silently stops publishing.

This reproduces that exact rejection with the session's own token, correctly
signed but back-dated past the limit, and proves the fix:
``GET /api/transport/csrf-token`` reissues a fresh, session-bound token that the
very same write then accepts.

The session token must be primed first: flask_wtf raises
"The CSRF session token is missing." (csrf.py:102) *before* it checks the age
(csrf.py:108), so an unprimed session would 400 via the wrong branch and prove
nothing about expiry. Signing the session's own value also forces the 400 to be
the age branch — a payload that matched the session but was still within its
lifetime would otherwise pass.

CSRF is disabled under ``TestingConfig``; the recovery test enables it for its
scope and restores the previous value afterwards.
"""

import time

import pytest
from itsdangerous import SignatureExpired, URLSafeTimedSerializer

from app.extensions import db

from tests.test_transport_restful_auth import _create_driver, _owner_id_in_context


def _backdated_csrf_token(app, value):
    """Sign ``value`` as a CSRF token 4000s in the past, flask_wtf's own way.

    Uses the app's real ``WTF_CSRF_SECRET_KEY`` and the ``wtf-csrf-token``
    salt, then back-dates the timestamp so validation reaches the age check
    and fails as ``SignatureExpired`` — the branch behind the observed
    'The CSRF token has expired.' 400.
    """
    secret = app.config["WTF_CSRF_SECRET_KEY"]
    serializer = URLSafeTimedSerializer(secret, salt="wtf-csrf-token")
    original_make_signer = serializer.make_signer

    def _backdated_make_signer(salt=None):
        signer = original_make_signer(salt)
        setattr(signer, "get_timestamp", lambda: int(time.time()) - 4000)
        return signer

    serializer.make_signer = _backdated_make_signer
    return serializer.dumps(value)


@pytest.fixture
def csrf_enabled(app):
    """Enable CSRF validation for this test only, then restore."""
    previous = app.config.get("WTF_CSRF_ENABLED")
    app.config["WTF_CSRF_ENABLED"] = True
    try:
        yield
    finally:
        app.config["WTF_CSRF_ENABLED"] = previous


class TestDriverLocationCsrfRefresh:
    def test_csrf_token_endpoint_requires_authentication(self, anonymous_client):
        resp = anonymous_client.get("/api/transport/csrf-token")
        assert resp.status_code == 401, (
            f"Expected 401 for anonymous, got {resp.status_code}: "
            f"{resp.get_data(as_text=True)}"
        )

    def test_csrf_token_endpoint_returns_a_token(self, authenticated_client):
        resp = authenticated_client.get("/api/transport/csrf-token")
        assert resp.status_code == 200, resp.get_data(as_text=True)
        data = resp.get_json()
        assert data.get("success") is True
        assert isinstance(data.get("csrf_token"), str) and data["csrf_token"]

    def test_expired_probe_is_actually_expired(self, app):
        token = _backdated_csrf_token(app, "expired-probe")
        serializer = URLSafeTimedSerializer(
            app.config["WTF_CSRF_SECRET_KEY"], salt="wtf-csrf-token"
        )
        # Within its true age it loads; beyond the limit it must expire.
        assert serializer.loads(token, max_age=10000) == "expired-probe"
        with pytest.raises(SignatureExpired):
            serializer.loads(token, max_age=3600)

    def test_which_validation_branch_fires(self, app, authenticated_client, csrf_enabled):
        """Primed session reaches expiry; unprimed hits 'missing' first.

        This is the guard that keeps the recovery test honest: same token,
        same signature, only the presence of the session token changes the
        reported reason.
        """
        from flask import session as flask_session
        from flask_wtf.csrf import ValidationError, validate_csrf

        primed = authenticated_client.get("/api/transport/csrf-token")
        assert primed.status_code == 200
        with authenticated_client.session_transaction() as sess:
            raw = sess["csrf_token"]
        expired = _backdated_csrf_token(app, raw)

        with app.test_request_context("/"):
            flask_session["csrf_token"] = raw
            with pytest.raises(ValidationError) as primed_exc:
                validate_csrf(expired)
            assert "expired" in str(primed_exc.value)

            flask_session.pop("csrf_token", None)
            with pytest.raises(ValidationError) as unprimed_exc:
                validate_csrf(expired)
            assert "missing" in str(unprimed_exc.value)

    def test_expired_token_rejected_then_refresh_recovers(
        self, app, authenticated_client, test_user, db_session, csrf_enabled
    ):
        owner_id = _owner_id_in_context(app, test_user)
        _, driver_id = _create_driver(app, "csrfrefresh", owner_id=owner_id)
        url = f"/api/transport/drivers/{driver_id}/location"
        payload = {"latitude": 0.35, "longitude": 32.5}

        # 1. Prime the session's CSRF token so validation reaches the age
        #    check (csrf.py:108) instead of flask_wtf's earlier
        #    "session token is missing" branch (csrf.py:102).
        primed = authenticated_client.get("/api/transport/csrf-token")
        assert primed.status_code == 200, primed.get_data(as_text=True)
        with authenticated_client.session_transaction() as sess:
            raw = sess["csrf_token"]

        # 2. The bug: the session's OWN token, back-dated past the limit, is
        #    rejected 400. The payload matches the session token, so the only
        #    validation path that can 400 is the expiry branch.
        expired = _backdated_csrf_token(app, raw)
        rejected = authenticated_client.post(
            url, json=payload, headers={"X-CSRFToken": expired}
        )
        assert rejected.status_code == 400, (
            f"Expected CSRF 400 for expired token, got {rejected.status_code}: "
            f"{rejected.get_data(as_text=True)}"
        )

        # 3. The fix: refresh the token for the same authenticated session.
        refreshed = authenticated_client.get("/api/transport/csrf-token")
        assert refreshed.status_code == 200
        fresh = refreshed.get_json()["csrf_token"]

        # 4. The very same write now succeeds — reissued, not bypassed.
        accepted = authenticated_client.post(
            url, json=payload, headers={"X-CSRFToken": fresh}
        )
        assert accepted.status_code == 204, (
            f"Expected 204 after refresh, got {accepted.status_code}: "
            f"{accepted.get_data(as_text=True)}"
        )
        assert accepted.data == b""
        from app.transport.models import DriverProfile
        with app.app_context():
            profile = db.session.get(DriverProfile, driver_id)
            assert profile.last_location["latitude"] == 0.35
            assert profile.location_updated_at is not None
