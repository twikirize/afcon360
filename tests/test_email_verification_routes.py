"""Regression tests for the email-verification routes.

Guards the reported bug where a clicked "verify" link / push notification
issued GET /verify-email and hit a 405. The endpoint must accept GET
(renders the code-entry form) instead of collapsing to 405/500.
"""
import pytest
from unittest.mock import patch

from app import create_app
from app.config import TestingConfig
from app.extensions import limiter


class _VerifyCfg(TestingConfig):
    RATELIMIT_ENABLED = True


@pytest.fixture
def app(monkeypatch):
    monkeypatch.setattr("app.REDIS_AVAILABLE", False)
    app = create_app(config_object=_VerifyCfg)
    app.config["TESTING"] = True
    app.config["WTF_CSRF_ENABLED"] = False
    app.config["STARTUP_DONE"] = True
    app.config["RATELIMIT_STORAGE_URI"] = "memory://"
    limiter.enabled = True
    yield app


@pytest.fixture(autouse=True)
def _reset_storage():
    try:
        limiter.storage.clear()
    except Exception:
        pass
    yield
    try:
        limiter.storage.clear()
    except Exception:
        pass


def test_verify_email_get_is_not_405(app):
    client = app.test_client()
    # Unauthenticated GET must redirect (login) or render — never 405/500.
    resp = client.get("/verify-email")
    assert resp.status_code != 405
    assert resp.status_code in (200, 302, 303, 401)


def test_verify_email_post_rejected_without_code(app):
    client = app.test_client()
    # POST without a code should be handled (redirect/flash), not 500.
    resp = client.post("/verify-email", data={"code": ""})
    assert resp.status_code != 405
    assert resp.status_code in (200, 302, 303, 401)
