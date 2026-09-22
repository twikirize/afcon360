"""Bidirectional single-entry identity enforcement for the individual KYC
upload flow.

Contract under test (Canonical Identity Bank / bidirectional single entry):
- KYC reads canonical identity from UserProfile; the upload form does NOT
  re-enter identity already held in the profile.
- GET /kyc/verify/upload prefills/locks the ID number from the canonical
  profile when the selected document type matches, and prefills city/country.
- Partial identity (KYC-first): a user with no canonical name is NOT
  redirected to the profile editor and is NOT asked for full_name / DOB here;
  the upload form only ever collects pure evidence. Missing profile identity
  is not this form's concern.
- POST /kyc/verify/upload derives the ID number from the canonical profile
  when the document type matches, ignoring any re-typed value; the submit
  never writes back to UserProfile (no reverse copy).
- A document type different from the canonical profile type is a plain
  evidence submission; the typed number is preserved.
- Identity-bearing document uploads (national_id/passport/driver_license/
  voter_card) now require a selfie; evidence-only types
  (income_source/bank_reference/proof_of_address/tin) stay selfie-optional.
- The template exposes the canonical markers used for prefill/lock and has no
  duplicate identity re-entry inputs.

Tests follow the DB-backed client style of test_kyc_single_entry_national_id.py.
"""
import io
import uuid

import pytest

from app.extensions import db
from app.identity.models.user import User
from app.profile.models import UserProfile, get_profile_by_user
from app.kyc import routes as kyc_routes
from tests.conftest import _login_client


def _pair_complete_profile(app, user, *, full_name="Gift Nakamya", id_type="national_id",
                           id_number="CANON-999", country="UG", city="Kampala",
                           verification_status="pending"):
    """Attach a canonical UserProfile (identity bank) to a committed user and
    return the user's public_id."""
    with app.app_context():
        merged = db.session.merge(user)
        profile = UserProfile(
            user_id=merged.public_id,
            full_name=full_name,
            nationality="UG",
            id_type=id_type,
            id_number=id_number,
            country=country,
            city=city,
            profile_completed=True,
            verification_status=verification_status,
        )
        db.session.add(profile)
        db.session.commit()
        return merged.public_id


def _upload_page(client, preselect=None):
    url = "/kyc/verify/upload"
    if preselect:
        url += f"?preselect={preselect}"
    return client.get(url)


def _stub_upload_submit(monkeypatch, captured):
    """Stub storage + service so the route can be driven against the test DB
    without real file storage or audit/submission side effects."""

    def fake_save(_f, _k):
        return "https://media.example/doc.png"

    def fake_submit_kyc(**kwargs):
        captured.update(kwargs)
        return None

    monkeypatch.setattr(kyc_routes, "_save_uploaded_file", fake_save)
    monkeypatch.setattr(kyc_routes.KycService, "submit_kyc", fake_submit_kyc)


def test_upload_form_renders_canonical_identity_prefill_and_lock(app, client, test_user):
    """With a complete canonical profile and matching preselect, the ID number
    is prefilled + locked read-only from UserProfile and address prefills."""
    _pair_complete_profile(app, test_user)
    _login_client(client, test_user)

    resp = _upload_page(client, preselect="national_id")
    assert resp.status_code == 200
    body = resp.data.decode("utf-8")

    assert 'value="CANON-999"' in body
    assert 'data-canonical-number="CANON-999"' in body
    assert 'data-canonical-type="national_id"' in body
    assert "Gift Nakamya" in body
    assert 'id="city" name="city" placeholder="Kampala" value="Kampala"' in body
    assert 'id="country" name="country" value="UG"' in body
    assert 'name="full_name"' not in body
    assert 'name="surname"' not in body
    assert 'name="date_of_birth"' not in body


def test_upload_renders_with_partial_identity_without_profile_redirect(app, client, test_user):
    """Partial identity (KYC-first): a user without a canonical profile is
    NOT redirected to the profile editor; the upload form renders normally and
    never collects full_name / DOB / surname re-entry inputs."""
    _login_client(client, test_user)

    resp = _upload_page(client)
    assert resp.status_code == 200
    body = resp.data.decode("utf-8")
    assert 'name="id_number"' in body
    assert 'name="full_name"' not in body
    assert 'name="surname"' not in body
    assert 'name="given_names"' not in body
    assert 'name="date_of_birth"' not in body


def test_upload_post_uses_canonical_id_number_and_does_not_reverse_write(app, client, test_user, monkeypatch):
    """POST with a re-typed ID number still submits the canonical profile
    number when the document type matches; UserProfile is unchanged."""
    public_id = _pair_complete_profile(app, test_user, id_number="CANON-999")
    _login_client(client, test_user)

    captured = {}
    _stub_upload_submit(monkeypatch, captured)

    resp = client.post(
        "/kyc/verify/upload",
        data={
            "kyc_type": "individual",
            "id_type": "national_id",
            "id_number": "TYPED-RE-ENTRY",
            "kyc_doc_file": (io.BytesIO(b"doc"), "doc.png", "image/png"),
            "selfie_file": (io.BytesIO(b"selfie"), "selfie.png", "image/png"),
        },
        content_type="multipart/form-data",
        follow_redirects=False,
    )
    assert resp.status_code == 302
    assert captured.get("id_number") == "CANON-999"
    assert captured.get("id_type") == "national_id"
    assert captured.get("document_url") == "https://media.example/doc.png"

    with app.app_context():
        profile = get_profile_by_user(public_id)
        assert profile.id_number == "CANON-999"
        assert profile.full_name == "Gift Nakamya"


def test_upload_post_unrelated_doc_type_keeps_typed_number(app, client, test_user, monkeypatch):
    """A document type different from the canonical profile type is evidence
    for a different identifier; the typed number is preserved."""
    _pair_complete_profile(app, test_user, id_type="national_id", id_number="CANON-999")
    _login_client(client, test_user)

    captured = {}
    _stub_upload_submit(monkeypatch, captured)

    resp = client.post(
        "/kyc/verify/upload",
        data={
            "kyc_type": "individual",
            "id_type": "passport",
            "id_number": "PASSPORT-100",
            "kyc_doc_file": (io.BytesIO(b"doc"), "doc.png", "image/png"),
            "selfie_file": (io.BytesIO(b"selfie"), "selfie.png", "image/png"),
        },
        content_type="multipart/form-data",
        follow_redirects=False,
    )
    assert resp.status_code == 302
    assert captured.get("id_number") == "PASSPORT-100"


def test_upload_selfie_required_for_identity_doc_and_optional_for_evidence(app, client, test_user, monkeypatch):
    """Identity-bearing uploads are rejected without a selfie; evidence-only
    uploads (non-identity) still succeed without one."""
    _pair_complete_profile(app, test_user)
    _login_client(client, test_user)

    # The test DB's default accepted list is identity-docs only; add an
    # evidence-only type so the acceptance gate does not reject it before the
    # selfie rule is exercised.
    import app.kyc_config_schema as kcs
    monkeypatch.setattr(
        kcs, "get_kyc_settings",
        lambda: {"kyc_accepted_id_types": [
            "national_id", "passport", "driver_license", "voter_card",
            "income_source"],
        },
    )

    # 1) Identity doc (national_id) with NO selfie -> rejected before submit.
    captured_id = {}
    _stub_upload_submit(monkeypatch, captured_id)
    resp = client.post(
        "/kyc/verify/upload",
        data={
            "kyc_type": "individual",
            "id_type": "national_id",
            "id_number": "TYPED-RE-ENTRY",
            "kyc_doc_file": (io.BytesIO(b"doc"), "doc.png", "image/png"),
        },
        content_type="multipart/form-data",
        follow_redirects=False,
    )
    assert resp.status_code == 302
    assert captured_id == {}

    # 2) Evidence-only doc (income_source) with NO selfie -> submitted.
    captured_ev = {}
    _stub_upload_submit(monkeypatch, captured_ev)
    resp = client.post(
        "/kyc/verify/upload",
        data={
            "kyc_type": "individual",
            "id_type": "income_source",
            "id_number": "INCOME-1",
            "kyc_doc_file": (io.BytesIO(b"doc"), "doc.png", "image/png"),
        },
        content_type="multipart/form-data",
        follow_redirects=False,
    )
    assert resp.status_code == 302
    assert captured_ev.get("id_type") == "income_source"
    assert captured_ev.get("selfie_url") is None


def test_upload_html_has_canonical_marker_and_no_identity_reentry_inputs():
    """Template-level guard: verify_upload.html carries the canonical markers
    the single-entry prefill/lock rely on and no duplicate identity inputs."""
    from pathlib import Path

    template = (
        Path(__file__).resolve().parent.parent
        / "templates" / "kyc" / "verify_upload.html"
    )
    content = template.read_text(encoding="utf-8")

    assert "data-canonical-number" in content
    assert "data-canonical-type" in content
    assert 'name="full_name"' not in content
    assert 'name="surname"' not in content
    assert 'name="given_names"' not in content
    assert 'name="date_of_birth"' not in content
    assert 'name="id_number"' in content