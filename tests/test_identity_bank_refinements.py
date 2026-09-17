"""Regression tests for the canonical identity bank + KYC refinements.

Coverage:
- Refinement D: ordinary KYC no longer *requires* a selfie just because the
  submitted document is a National ID / passport / driver licence. All selfie
  capture, upload, and cross-device pairing infrastructure stays intact.
- Refinement A: reads of canonical person data (nationality, full name, DOB)
  resolve through UserProfile (the identity bank), never through non-existent
  User columns.
- Refinement C: the owner manual KYC upgrade syncs UserProfile so the profile
  gate and the verification authority agree.

Tests follow the direct view-function style of test_kyc_upload_validation.py
for KYC routes and the DB-backed client style of test_canonical_identity_center.py
for the owner/admin flow.
"""

import datetime as dt
import uuid

import pytest
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import MagicMock

from flask import Flask

from app.extensions import db
from app.kyc import routes as kyc_routes
from app.kyc.routes import kyc_bp, verify_upload


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


def _individual_submit_runtime(monkeypatch, captured):
    """Stub the individual KYC submit surface so verify_upload can be driven
    directly without a live DB / storage, mirroring test_kyc_upload_validation.py."""
    fake_user = SimpleNamespace(id=7, public_id="user-public-id")
    query = MagicMock()
    query.filter_by.return_value.order_by.return_value.all.return_value = []
    query.filter.return_value.order_by.return_value.all.return_value = []
    monkeypatch.setattr(kyc_routes.KycRecord, "query", query)
    monkeypatch.setattr(kyc_routes, "current_user", fake_user)
    monkeypatch.setattr(kyc_routes, "_get_user_organisations", lambda: [])
    monkeypatch.setattr(kyc_routes, "is_acting_as_organization", lambda: False)
    monkeypatch.setattr(kyc_routes, "_get_verified_id_types", lambda uid: [])

    def fake_save(_f, _k):
        return "doc-url"

    monkeypatch.setattr(kyc_routes, "_save_uploaded_file", fake_save)

    def fake_submit_kyc(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(public_id="record-pub")

    monkeypatch.setattr(kyc_routes.KycService, "submit_kyc", fake_submit_kyc)


# ---------------------------------------------------------------------------
# Refinement D - no universal selfie gate on ordinary identity documents
# ---------------------------------------------------------------------------


def test_identity_doc_submission_without_selfie_is_accepted(monkeypatch):
    """national_id + document with NO selfie must submit successfully - a
    selfie is not universal anymore (it remains enhanced assurance)."""
    captured = {}
    _individual_submit_runtime(monkeypatch, captured)

    handler = _unwrap(verify_upload)
    app = _make_app()
    with app.test_request_context(
        "/kyc/verify/upload",
        method="POST",
        data={
            "kyc_type": "individual",
            "id_type": "national_id",
            "id_number": "CM1234567890",
            "kyc_doc_file": (BytesIO(b"doc"), "doc.png", "image/png"),
        },
        content_type="multipart/form-data",
    ):
        resp = handler()

    assert resp.status_code == 302
    assert captured.get("id_type") == "national_id"


def test_all_identity_doc_types_accepted_without_selfie(monkeypatch):
    """Every previously-gated identity document type submits without selfie."""
    for doc_type in ("passport", "driver_license", "voter_card"):
        captured = {}
        _individual_submit_runtime(monkeypatch, captured)

        handler = _unwrap(verify_upload)
        app = _make_app()
        with app.test_request_context(
            "/kyc/verify/upload",
            method="POST",
            data={
                "kyc_type": "individual",
                "id_type": doc_type,
                "id_number": f"N-{doc_type}",
                "kyc_doc_file": (BytesIO(b"doc"), "doc.png", "image/png"),
            },
            content_type="multipart/form-data",
        ):
            resp = handler()

        assert resp.status_code == 302, f"{doc_type} rejected without selfie"
        assert captured.get("id_type") == doc_type


def test_selfie_is_still_accepted_as_evidence(monkeypatch):
    """A submitted selfie still flows into the record as evidence - the
    mechanism was not removed, only the upload-time requirement."""
    captured = {}
    _individual_submit_runtime(monkeypatch, captured)

    handler = _unwrap(verify_upload)
    app = _make_app()
    with app.test_request_context(
        "/kyc/verify/upload",
        method="POST",
        data={
            "kyc_type": "individual",
            "id_type": "national_id",
            "id_number": "CM1234567890",
            "selfie_url": "https://media.example/selfie.jpg",
            "kyc_doc_file": (BytesIO(b"doc"), "doc.png", "image/png"),
        },
        content_type="multipart/form-data",
    ):
        resp = handler()

    assert resp.status_code == 302
    assert captured.get("selfie_url") == "https://media.example/selfie.jpg"


def test_client_guard_function_removed():
    """The client-side '__selfieRequiredForSubmit' guard must no longer exist
    in the upload template so the form does not block identity submissions."""
    from pathlib import Path

    template = Path(__file__).resolve().parent.parent / "templates" / "kyc" / "verify_upload.html"
    content = template.read_text(encoding="utf-8")
    assert "__selfieRequiredForSubmit" not in content


# ---------------------------------------------------------------------------
# Refinement A - canonical identity reads for person data
# ---------------------------------------------------------------------------


def test_kyc_record_enhanced_risk_reads_profile_dob(app):
    """KycRecord.calculate_enhanced_risk must resolve date_of_birth from the
    UserProfile identity bank, not from User.date_of_birth (which does not
    exist and previously crashed the computation)."""
    from app.identity.models.user import User
    from app.kyc.models import KycRecord
    from app.profile.models import UserProfile

    uid = uuid.uuid4().hex[:8]
    with app.app_context():
        user = User(
            public_id=str(uuid.uuid4()),
            username=f"kr_{uid}",
            email=f"kr_{uid}@test.example.com",
            is_verified=True,
            is_active=True,
        )
        user.set_password("TestPassword123!")
        db.session.add(user)
        db.session.flush()
        db.session.add(
            UserProfile(
                user_id=user.public_id,
                full_name="Risk Identity Name",
                date_of_birth=dt.date(2008, 5, 5),
                nationality="UG",
                profile_completed=True,
            )
        )
        db.session.flush()
        db.session.add(
            KycRecord(
                user_id=user.id,
                record_type="national_id_verification",
                id_type="national_id",
                id_number="NID-RISK-001",
                status="pending",
            )
        )
        db.session.commit()

        record = KycRecord.query.filter_by(record_type="national_id_verification").first()
        result = record.calculate_enhanced_risk()
        assert "under_age" in result["risk_factors"] or "under_21" in result["risk_factors"]


def test_kyc_record_enhanced_risk_survives_missing_profile(app):
    """calculate_enhanced_risk degrades gracefully when no profile exists."""
    from app.identity.models.user import User
    from app.kyc.models import KycRecord

    uid = uuid.uuid4().hex[:8]
    with app.app_context():
        user = User(
            public_id=str(uuid.uuid4()),
            username=f"krnp_{uid}",
            email=f"krnp_{uid}@test.example.com",
            is_verified=True,
            is_active=True,
        )
        user.set_password("TestPassword123!")
        db.session.add(user)
        db.session.flush()
        db.session.add(
            KycRecord(
                user_id=user.id,
                record_type="passport_verification",
                id_type="passport",
                id_number="P-RISK-001",
                status="pending",
            )
        )
        db.session.commit()

        record = KycRecord.query.filter_by(record_type="passport_verification").first()
        result = record.calculate_enhanced_risk()
        assert "risk_factors" in result


def test_canonical_identity_surfaces_profile_nationality(app):
    """The canonical read the events/wallet consumers now use must surface
    profile nationality/full name - the data the User row cannot provide."""
    from app.identity.models.user import User
    from app.profile.models import UserProfile
    from app.profile.services.canonical_identity import get_canonical_identity

    uid = uuid.uuid4().hex[:8]
    with app.app_context():
        user = User(
            public_id=str(uuid.uuid4()),
            username=f"ci_{uid}",
            email=f"ci_{uid}@test.example.com",
            is_verified=True,
            is_active=True,
        )
        user.set_password("TestPassword123!")
        db.session.add(user)
        db.session.flush()
        db.session.add(
            UserProfile(
                user_id=user.public_id,
                full_name="Consumer Read Name",
                nationality="RW",
                date_of_birth=dt.date(1992, 3, 3),
                profile_completed=True,
            )
        )
        db.session.commit()

        identity = get_canonical_identity(user.public_id)
        assert identity.full_name == "Consumer Read Name"
        assert identity.nationality == "RW"


# ---------------------------------------------------------------------------
# Refinement C - owner manual upgrade syncs the profile gate
# ---------------------------------------------------------------------------


def test_manual_kyc_upgrade_syncs_profile_verification(app, client, test_admin, test_user):
    """The owner manual KYC upgrade must flip UserProfile.verification_status
    to 'verified' so profile gates agree with the verification authority."""
    from app.identity.models.user import User
    from app.profile.models import UserProfile, get_profile_by_user
    from tests.conftest import _login_client

    with app.app_context():
        merged_target = db.session.merge(test_user)
        db.session.add(
            UserProfile(
                user_id=merged_target.public_id,
                full_name="Sync Target",
                date_of_birth=dt.date(1995, 8, 8),
                nationality="UG",
                id_type="national_id",
                id_number="NID-SYNC-001",
                profile_completed=True,
            )
        )
        db.session.commit()
        target_id = merged_target.id

    _login_client(client, test_admin)

    resp = client.post(
        f"/admin/owner/kyc/manual-upgrade/{target_id}",
        data={"tier": "2", "reason": "Regression test manual upgrade"},
        follow_redirects=False,
    )
    assert resp.status_code == 302

    with app.app_context():
        target_user = db.session.merge(test_user)
        profile = get_profile_by_user(target_user.public_id)
        assert profile.verification_status == "verified"


def test_manual_kyc_upgrade_tier0_leaves_profile_pending(app, client, test_admin, test_user):
    """A manual downgrade to tier 0 must NOT flip the profile, because the
    profile gate only asserts canonical 'verified' state for real tiers."""
    from app.identity.models.user import User
    from app.profile.models import UserProfile, get_profile_by_user
    from tests.conftest import _login_client

    with app.app_context():
        merged_target = db.session.merge(test_user)
        db.session.add(
            UserProfile(
                user_id=merged_target.public_id,
                full_name="Sync Target Zero",
                date_of_birth=dt.date(1995, 8, 8),
                nationality="UG",
                profile_completed=True,
            )
        )
        db.session.commit()
        target_id = merged_target.id

    _login_client(client, test_admin)

    resp = client.post(
        f"/admin/owner/kyc/manual-upgrade/{target_id}",
        data={"tier": "0", "reason": "Regression test tier zero"},
        follow_redirects=False,
    )
    assert resp.status_code == 302

    with app.app_context():
        target_user = db.session.merge(test_user)
        profile = get_profile_by_user(target_user.public_id)
        assert profile.verification_status != "verified"