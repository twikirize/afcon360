"""Tests for the health endpoint rate-limit exemption and 429 handling.

These tests build a dedicated app with rate limiting ENABLED (the shared
conftest disables it for the normal suite) so we can prove:

* ``/api/health/ping`` is never rate limited.
* Health calls do not consume the application-wide request quota.
* Ordinary routes remain rate limited.
* A genuine ``RateLimitExceeded`` becomes HTTP 429, never 500.
* The health response contains no secrets/config.
"""
import pytest
from unittest.mock import patch

from flask import Blueprint, jsonify

from app import create_app
from app.config import TestingConfig
from app.extensions import limiter


class _RateLimitTestConfig(TestingConfig):
    """Testing config with rate limiting ON and a tiny shared quota."""

    RATELIMIT_ENABLED = True
    # Shared application-wide limit (applies to every non-exempt route).
    RATELIMIT_APPLICATION = "5 per minute"
    RATELIMIT_STORAGE_URI = "memory://"


@pytest.fixture(autouse=True)
def _reset_limiter_storage():
    """The in-memory limiter storage is a process-wide singleton, so the
    application-limit counter would otherwise persist across tests within the
    one-minute window. Clear it before/after each test for isolation."""
    try:
        limiter.storage.clear()
    except Exception:
        pass
    yield
    try:
        limiter.storage.clear()
    except Exception:
        pass


@pytest.fixture
def rl_app(monkeypatch):
    # create_app() forces RATELIMIT_STORAGE_URI to Redis whenever Redis is
    # reachable, which would make the rate-limit counter persist across tests
    # (and even across runs) in a shared Redis. Force the in-memory backend so
    # each test gets an isolated, deterministic counter.
    monkeypatch.setattr("app.REDIS_AVAILABLE", False)

    app = create_app(config_object=_RateLimitTestConfig)
    app.config["TESTING"] = True
    app.config["WTF_CSRF_ENABLED"] = False
    # Prevent the deferred startup thread from mutating the shared limiter.
    app.config["STARTUP_DONE"] = True
    app.config["RATELIMIT_STORAGE_URI"] = "memory://"

    # A normal (non-exempt) route that inherits the application-wide limit.
    bp = Blueprint("rl_test", __name__)

    @bp.route("/rl_normal")
    def rl_normal():
        return jsonify({"ok": True}), 200

    app.register_blueprint(bp)

    # Make the shared limiter deterministic: enabled, and isolate the
    # per-request dynamic toggle from DB state.
    limiter.enabled = True
    with patch(
        "app.admin.owner.rate_limit_service.RateLimitService.is_enabled",
        return_value=True,
    ):
        yield app


def test_health_ping_returns_200(rl_app):
    client = rl_app.test_client()
    resp = client.get("/api/health/ping")
    assert resp.status_code == 200
    assert resp.get_json() == {"status": "ok"}


def test_health_ping_repeated_never_429(rl_app):
    client = rl_app.test_client()
    for _ in range(5000):
        resp = client.get("/api/health/ping")
        assert resp.status_code == 200, "health ping must never be rate limited"


def test_health_does_not_consume_global_quota(rl_app):
    client = rl_app.test_client()
    # 100 exempt health calls must not drain the shared application quota.
    for _ in range(100):
        assert client.get("/api/health/ping").status_code == 200
    # The normal route still has its full 5-request application quota.
    codes = [client.get("/rl_normal").status_code for _ in range(6)]
    assert codes[:5] == [200, 200, 200, 200, 200]
    assert codes[5] == 429


def test_ordinary_route_remains_rate_limited(rl_app):
    client = rl_app.test_client()
    codes = [client.get("/rl_normal").status_code for _ in range(7)]
    assert 429 in codes
    assert codes.count(200) == 5


def test_ratelimit_exceeded_is_429_not_500(rl_app):
    client = rl_app.test_client()
    for _ in range(5):
        assert client.get("/rl_normal").status_code == 200
    resp = client.get("/rl_normal")
    assert resp.status_code == 429
    data = resp.get_json()
    assert data["status"] == 429
    assert data["error"] == "Too Many Requests"


def test_health_response_has_no_secrets(rl_app):
    client = rl_app.test_client()
    resp = client.get("/api/health/ping")
    body = resp.get_data(as_text=True).lower()
    for secret in (
        "secret",
        "password",
        "token",
        "api_key",
        "apikey",
        "database_url",
        "encryption_key",
        "redis",
        "postgresql",
        "session",
    ):
        assert secret not in body


def test_health_functionality_intact(rl_app):
    client = rl_app.test_client()
    # The dedicated health endpoint is still registered and reports ok.
    resp = client.get("/api/health/ping")
    assert resp.status_code == 200
    assert resp.get_json().get("status") == "ok"


def test_method_not_allowed_returns_405_not_500(rl_app):
    # A POST-only route hit with GET must stay 405, not be collapsed to 500
    # by the generic Exception handler (the /verify-email class of bug).
    @rl_app.route("/rl_post_only", methods=["POST"])
    def rl_post_only():
        return jsonify({"ok": True}), 200

    client = rl_app.test_client()
    resp = client.get("/rl_post_only")
    assert resp.status_code == 405
