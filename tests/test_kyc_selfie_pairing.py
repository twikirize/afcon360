"""Regression tests for the cross-device KYC selfie pairing ("scan & selfie").

These tests follow the direct view-function invocation style of
test_kyc_upload_validation.py: no full app, no live Redis. A tiny in-memory
Redis stub stands in for the pairing store so the pending -> ready -> consumed
state machine can be exercised deterministically.
"""

from io import BytesIO
from types import SimpleNamespace
from unittest.mock import MagicMock

from flask import Flask

from app.kyc import selfie_pair as sp
from app.kyc.selfie_pair import (
    load_selfie_pair_token,
    make_selfie_pair_token,
    consume_pair,
    create_pair_session,
)
from app.kyc.routes import kyc_bp, verify_upload


class FakeRedis:
    """Minimal in-memory Redis stand-in: get/set/setex/delete only."""

    def __init__(self):
        self.store = {}

    def get(self, key):
        raw = self.store.get(key)
        return raw.encode("utf-8") if raw else None

    def set(self, key, value, ex=None):
        self.store[key] = value

    def setex(self, key, ttl, value):
        self.store[key] = value

    def delete(self, key):
        self.store.pop(key, None)


def _unwrap(fn):
    while hasattr(fn, "__wrapped__"):
        fn = fn.__wrapped__
    return fn


def _make_app():
    from pathlib import Path

    templates_dir = str(Path(__file__).resolve().parent.parent / "templates")
    test_app = Flask(__name__, template_folder=templates_dir)
    test_app.secret_key = "test-secret"
    test_app.register_blueprint(kyc_bp)
    return test_app


# ── Token signing / loading ────────────────────────────────────────────────


def test_token_roundtrip():
    token = make_selfie_pair_token("abc123", "userpub")
    payload = load_selfie_pair_token(token)
    assert payload == {"kind": "selfie_pair", "nonce": "abc123", "owner_public_id": "userpub"}


def test_token_rejects_garbage():
    try:
        load_selfie_pair_token("not-a-fernet-token!")
    except ValueError:
        return
    raise AssertionError("expected ValueError")


# ── Pairing session state machine (stubbed Redis) ─────────────────────────


def test_pair_session_pending_to_ready_to_consumed(monkeypatch):
    r = FakeRedis()
    monkeypatch.setattr(sp, "_redis", lambda: r)

    nonce = "nonce123"
    assert create_pair_session(7, "ownerpub", nonce) is True

    session = sp.get_pair_session(nonce)
    assert session["status"] == "pending"
    assert session["user_id"] == 7

    done = sp.mark_pair_ready(nonce, "https://media.example/selfie.jpg")
    assert done is True
    assert sp.get_pair_session(nonce)["status"] == "ready"

    media_url, reason = consume_pair(nonce, 7)
    assert reason == "ok"
    assert media_url == "https://media.example/selfie.jpg"
    # single-use: consuming again must not return the media
    media_url, reason = consume_pair(nonce, 7)
    assert reason == "expired"


def test_pair_consume_bound_to_user(monkeypatch):
    r = FakeRedis()
    monkeypatch.setattr(sp, "_redis", lambda: r)

    nonce = "nonceX"
    create_pair_session(7, "ownerpub", nonce)
    sp.mark_pair_ready(nonce, "https://media.example/s.jpg")

    media_url, reason = consume_pair(nonce, 99)
    assert reason == "forbidden"
    assert media_url is None


# ── Routes ─────────────────────────────────────────────────────────────────


def test_pair_create_requires_login():
    """Pairing creation must be refused for anonymous users."""
    app = _make_app()
    view = app.view_functions["kyc.selfie_pair"]
    with app.test_request_context("/kyc/selfie/pair", method="POST"):
        resp = view()
    assert resp[1] == 401


def test_companion_page_rejects_garbage_token():
    app = _make_app()
    with app.test_request_context("/kyc/selfie/companion?token=bogus"):
        view = app.view_functions["kyc.selfie_companion"]
        resp = view()
    body = resp[0] if isinstance(resp, tuple) else resp
    status = resp[1] if isinstance(resp, tuple) else 200
    assert status == 410
    assert "Link Expired" in str(body)


def test_verify_upload_consumes_pair_nonce(monkeypatch):
    """verify_upload must consume a ready pairing nonce into selfie_url."""
    r = FakeRedis()
    monkeypatch.setattr(sp, "_redis", lambda: r)

    nonce = "consume-me"
    create_pair_session(7, "ownerpub", nonce)
    sp.mark_pair_ready(nonce, "https://media.example/paired-selfie.jpg")

    fake_user = SimpleNamespace(id=7, public_id="ownerpub")

    from app.kyc import routes as kyc_routes

    query = MagicMock()
    query.filter_by.return_value.order_by.return_value.all.return_value = []
    query.filter.return_value.order_by.return_value.all.return_value = []
    monkeypatch.setattr(kyc_routes.KycRecord, "query", query)
    monkeypatch.setattr(kyc_routes, "current_user", fake_user)
    monkeypatch.setattr(kyc_routes, "_get_user_organisations", lambda: [])
    monkeypatch.setattr(kyc_routes, "is_acting_as_organization", lambda: False)
    monkeypatch.setattr(kyc_routes, "_get_verified_id_types", lambda uid: [])
    monkeypatch.setattr(kyc_routes, "_save_uploaded_file", lambda _f, _k: "doc-url")

    captured = {}
    def fake_submit_kyc(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(public_id="record-pub")

    monkeypatch.setattr(kyc_routes.KycService, "submit_kyc", fake_submit_kyc)

    app = _make_app()
    handler = _unwrap(verify_upload)
    with app.test_request_context(
        "/kyc/verify/upload",
        method="POST",
        data={
            "kyc_type": "individual",
            "id_type": "national_id",
            "id_number": "CM1234567890",
            "selfie_pair_nonce": nonce,
            "kyc_doc_file": (BytesIO(b"doc"), "doc.png", "image/png"),
        },
        content_type="multipart/form-data",
    ):
        resp = handler()

    assert resp.status_code == 302
    assert captured["selfie_url"] == "https://media.example/paired-selfie.jpg"
    # pairing is consumed exactly once
    media_url, reason = consume_pair(nonce, 7)
    assert reason == "expired"