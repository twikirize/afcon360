"""Regression tests for the KYC per-type re-submission guard and async dispatch.

A document type that is already under review (pending / manual_review) or
already decided (verified / approved) must not be accepted a second time.
Rejected / expired records remain resubmittable.

These tests follow the direct view-function invocation style of
test_kyc_selfie_pairing.py: no full app, no live database. The guard helpers
read ``KycRecord.query``, which is stubbed with a MagicMock.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

from flask import Flask

from app.kyc import routes as kyc_routes
from app.kyc.routes import kyc_bp, verify_upload
from app.notifications import dispatch as dispatch_mod


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


def _record(status, id_type):
    return SimpleNamespace(status=status, id_type=id_type)


def _query_returning(records):
    q = MagicMock()
    q.filter_by.return_value.all.return_value = records
    q.filter_by.return_value.order_by.return_value.all.return_value = records
    return q


# ── Guard helpers ──────────────────────────────────────────────────────────


def test_open_id_types_blocks_pending_and_manual_review(monkeypatch):
    records = [
        _record("pending", "national_id"),
        _record("manual_review", "passport"),
        _record("verified", "driver_license"),
        _record("rejected", "bank_reference"),
        _record("expired", "address"),
    ]
    monkeypatch.setattr(kyc_routes.KycRecord, "query", _query_returning(records))
    assert kyc_routes._get_open_id_types(1) == {"national_id", "passport"}


def test_verified_id_types_blocks_verified_and_approved(monkeypatch):
    records = [
        _record("verified", "national_id"),
        _record("approved", "passport"),
        _record("pending", "driver_license"),
    ]
    monkeypatch.setattr(kyc_routes.KycRecord, "query", _query_returning(records))
    assert kyc_routes._get_verified_id_types(1) == {"national_id", "passport"}


# ── Upload view guard ──────────────────────────────────────────────────────


def test_verify_upload_blocks_duplicate_while_under_review(monkeypatch):
    fake_user = SimpleNamespace(id=7, public_id="pub7")
    monkeypatch.setattr(kyc_routes, "current_user", fake_user)
    monkeypatch.setattr(kyc_routes, "_get_user_organisations", lambda: [])
    monkeypatch.setattr(kyc_routes, "is_acting_as_organization", lambda: False)
    monkeypatch.setattr(kyc_routes, "_get_verified_id_types", lambda uid: set())
    monkeypatch.setattr(kyc_routes, "_get_open_id_types", lambda uid: {"passport"})
    monkeypatch.setattr(
        kyc_routes.KycRecord, "query", _query_returning([])
    )

    called = {"submit": False}

    def fake_submit_kyc(**kwargs):
        called["submit"] = True
        return SimpleNamespace(public_id="record-pub")

    monkeypatch.setattr(kyc_routes.KycService, "submit_kyc", fake_submit_kyc)

    app = _make_app()
    handler = _unwrap(verify_upload)
    with app.test_request_context(
        "/kyc/verify/upload",
        method="POST",
        data={"kyc_type": "individual", "id_type": "passport", "id_number": "X123"},
    ):
        resp = handler()

    assert resp.status_code == 302
    assert called["submit"] is False


# ── Async dispatch selection ────────────────────────────────────────────────


def test_dispatch_runs_inline_under_testing():
    app = Flask(__name__)
    app.testing = True
    seen = []
    with app.app_context():
        dispatch_mod.dispatch_notification(
            lambda **kw: seen.append(kw), user_id=1, kyc_record_id=2
        )
    assert seen == [{"user_id": 1, "kyc_record_id": 2}]


def test_dispatch_uses_thread_when_not_testing():
    import threading

    app = Flask(__name__)
    app.testing = False
    done = threading.Event()
    seen = []

    def deliver(**kw):
        seen.append(kw)
        done.set()

    with app.app_context():
        dispatch_mod.dispatch_notification(deliver, user_id=3, kyc_record_id=4)

    assert done.wait(5), "background delivery did not run"
    assert seen == [{"user_id": 3, "kyc_record_id": 4}]
