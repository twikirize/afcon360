"""Fix 2.6 — public endpoint rate limiting proof.

Guarantee under test (and nothing else):
  POST /api/transport/ride-options
  POST /api/transport/fare/estimate
enforce 30 requests per 60-second window per caller; the 31st call
returns HTTP 429 without executing the resource body.

Keying: ``user:<current_user.id>`` when authenticated,
``ip:<request.remote_addr>`` when anonymous. Keys live in the
server-side limiter storage only — never in responses, URLs, or
templates.

Isolation: the suite runs with the limiter disabled
(``TestingConfig.RATELIMIT_ENABLED=False`` + the dev disable handler
in ``app/__init__.py``). The autouse fixture below enables it for
THIS FILE ONLY and resets the in-process memory storage before (and
after) every test, so counters never leak between tests or files.
No change to ``tests/conftest.py`` or any shared fixture.
"""

import pytest

from app.admin.owner.rate_limit_service import RateLimitService
from app.extensions import limiter
from app.transport.api.ride_options_routes import _rate_limit_key

RIDE_URL = "/api/transport/ride-options"
FARE_URL = "/api/transport/fare/estimate"
RIDE_PAYLOAD = {}
FARE_PAYLOAD = {"service_type": "on_demand", "vehicle_class": "comfort"}
LIMIT = 30


@pytest.fixture(autouse=True)
def _rate_limit_test_env(app, monkeypatch):
    """Enable Flask-Limiter for this file's tests only; reset per test.

    Self-restoring: config keys are saved and put back even if conftest's
    own isolation fixtures run in a different order.
    """
    saved = {k: app.config.get(k) for k in ("RATELIMIT_ENABLED", "DEBUG", "APP_ENV")}
    app.config["RATELIMIT_ENABLED"] = True
    app.config["DEBUG"] = False
    app.config["APP_ENV"] = "prod"
    # Keep the dynamic per-request handler (app/__init__.py) from
    # disabling the limiter while these tests run.
    monkeypatch.setattr(RateLimitService, "is_enabled", staticmethod(lambda: True))
    if limiter not in app.extensions.get("limiter", set()):
        # Canonical init through the installed extension. It is required
        # because creation-time init_app() early-returned while the limiter
        # was disabled (no check registered, no storage built), and it is
        # guarded by the extension itself against duplicate registration.
        # The session app may already have served requests (earlier files in
        # the suite run first), and Flask forbids late before_request
        # registration — so the guard flag is lowered only for this one
        # canonical call and restored immediately after. Flask reads the
        # handler list per request, so the check applies from the next
        # request onward.
        first = app._got_first_request
        app._got_first_request = False
        try:
            limiter.init_app(app)
        finally:
            app._got_first_request = first
    limiter.enabled = True
    with app.app_context():
        limiter.reset()
    yield
    with app.app_context():
        try:
            limiter.reset()
        except Exception:
            pass
    for key, value in saved.items():
        app.config[key] = value


def test_ride_options_allows_under_limit(client):
    """30 sequential anonymous calls return 200 with the success shape."""
    for _ in range(LIMIT):
        resp = client.post(RIDE_URL, json=RIDE_PAYLOAD)
        assert resp.status_code == 200
        body = resp.get_json()
    assert body["success"] is True
    assert "options" in body["data"]


def test_ride_options_returns_429_at_limit(authenticated_client):
    """31st call returns 429; the other endpoint stays available."""
    for _ in range(LIMIT):
        resp = authenticated_client.post(RIDE_URL, json=RIDE_PAYLOAD)
        assert resp.status_code == 200
    assert authenticated_client.post(RIDE_URL, json=RIDE_PAYLOAD).status_code == 429
    # Independent bucket: same caller, other endpoint unaffected.
    resp = authenticated_client.post(FARE_URL, json=FARE_PAYLOAD)
    assert resp.status_code == 200


def test_fare_estimate_returns_429_at_limit(authenticated_client):
    """Same 30-then-429 behavior for the fare endpoint (authenticated)."""
    for _ in range(LIMIT):
        resp = authenticated_client.post(FARE_URL, json=FARE_PAYLOAD)
        assert resp.status_code == 200
    assert authenticated_client.post(FARE_URL, json=FARE_PAYLOAD).status_code == 429


def test_anonymous_calls_are_limited_by_ip(app, test_user, authenticated_client):
    """Anonymous bucket exhausts by IP; authenticated key is a fresh bucket."""
    anon = app.test_client()
    for _ in range(LIMIT):
        assert anon.post(RIDE_URL, json=RIDE_PAYLOAD).status_code == 200
    assert anon.post(RIDE_URL, json=RIDE_PAYLOAD).status_code == 429
    # Same endpoint, authenticated caller key -> unaffected.
    assert authenticated_client.post(RIDE_URL, json=RIDE_PAYLOAD).status_code == 200
    # Key-function unit proof (server-side only, never rendered).
    with app.test_request_context(
        RIDE_URL, method="POST", environ_overrides={"REMOTE_ADDR": "127.0.0.1"}
    ):
        assert _rate_limit_key() == "ip:127.0.0.1"
    with app.test_request_context(
        RIDE_URL, method="POST", environ_overrides={"REMOTE_ADDR": "127.0.0.1"}
    ):
        from flask_login import login_user

        from app.extensions import db

        merged = db.session.merge(test_user)
        login_user(merged)
        assert _rate_limit_key() == f"user:{merged.id}"
        db.session.rollback()
