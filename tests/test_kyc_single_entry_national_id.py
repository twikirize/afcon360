"""Bidirectional single-entry identity enforcement for the National ID (NIRA)
KYC flow.

Contract under test (Canonical Identity Bank / bidirectional single entry):
- Personal identity lives ONCE in the UserProfile identity bank.
- Profile-first: a user who already holds canonical facts (full_name / DOB)
  sees them rendered read-only on the NIRA page; the form never re-asks for
  surname / given_names / date_of_birth inputs.
- KYC-first: a user with NO canonical full_name renders a collection form on
  the NIRA page (full_name + optional date_of_birth entered here once, written
  to the canonical UserProfile, never re-asked anywhere). No redirect to the
  profile editor for a missing name.
- POST /kyc/verify/national-id needs only the NIN when canonical identity is
  present; surname / given_names are derived from the canonical full_name. In
  KYC-first mode the submitted full_name / date_of_birth backfill the
  canonical UserProfile AFTER format + watchlist gates pass. The first
  legitimate source wins; existing canonical values are never overwritten and
  a verified profile is never written.
- UserProfile.date_of_birth has a write path via profile.edit_profile and
  stays immutable after verification.

Tests follow the DB-backed client style of test_canonical_identity_center.py.
"""
import datetime as dt
import uuid

import pytest

from app.extensions import db
from app.identity.models.user import User
from app.profile.models import UserProfile, get_profile_by_user
from tests.conftest import _login_client


def _pair_user_with_profile(app, user, *, full_name="Canonical KYC Name",
                            dob=None, verified=False):
    """Attach a canonical UserProfile to a committed user and return the
    user's public_id. ``dob=None`` stores no date_of_birth; pass a date to
    set one."""
    with app.app_context():
        merged = db.session.merge(user)
        profile = UserProfile(
            user_id=merged.public_id,
            full_name=full_name,
            date_of_birth=dob,
            nationality="UG",
            id_type="national_id",
            id_number="NID-SINGLE-001",
            profile_completed=True,
            verification_status="verified" if verified else "pending",
        )
        db.session.add(profile)
        db.session.commit()
        return merged.public_id


def _national_id_page(client):
    return client.get("/kyc/verify/national-id")


def test_national_id_form_renders_canonical_identity_read_only(app, client, test_user):
    """The NIRA form shows canonical name/DOB from UserProfile and contains no
    editable surname / given_names / date_of_birth inputs."""
    _pair_user_with_profile(app, test_user, full_name="Gift Nakamya", dob=dt.date(1992, 6, 1))
    _login_client(client, test_user)

    resp = _national_id_page(client)
    assert resp.status_code == 200
    body = resp.data.decode("utf-8")

    assert "Gift Nakamya" in body
    assert "1992-06-01" in body
    assert 'name="surname"' not in body
    assert 'name="given_names"' not in body
    assert 'name="date_of_birth"' not in body
    assert 'name="id_number"' in body


def test_national_id_renders_kyc_first_collection_when_identity_incomplete(app, client, test_user):
    """KYC-first: a user without a canonical full_name renders the NIRA
    collection form (full_name + optional date_of_birth entered once here),
    NOT a redirect to the profile editor. No legacy surname/given_names."""
    _login_client(client, test_user)

    resp = _national_id_page(client)
    assert resp.status_code == 200
    body = resp.data.decode("utf-8")
    assert 'name="full_name"' in body
    assert 'id="date_of_birth"' in body
    assert 'name="surname"' not in body
    assert 'name="given_names"' not in body
    assert 'name="id_number"' in body


def test_national_id_submit_reads_canonical_identity_and_does_not_reverse_write(app, client, test_user):
    """POST with only the NIN creates the NIRA record using canonical identity;
    UserProfile identity is byte-for-byte unchanged afterwards."""
    public_id = _pair_user_with_profile(
        app, test_user, full_name="Gift Nakamya", dob=dt.date(1992, 6, 1)
    )
    _login_client(client, test_user)

    resp = client.post(
        "/kyc/verify/national-id",
        data={"id_number": "CM1234567890AB", "consent": "on"},
        follow_redirects=False,
    )
    assert resp.status_code == 302

    with app.app_context():
        from app.kyc.models import KycRecord

        merged = db.session.merge(test_user)
        record = (
            KycRecord.query.filter_by(user_id=merged.id, record_type="nira_national_id")
            .order_by(KycRecord.created_at.desc())
            .first()
        )
        assert record is not None, "NIRA record must be created"
        assert record.id_number == "CM1234567890AB"

        profile = get_profile_by_user(public_id)
        assert profile.full_name == "Gift Nakamya"
        assert profile.date_of_birth == dt.date(1992, 6, 1)
        assert profile.id_number == "NID-SINGLE-001"


def test_national_id_submit_uses_canonical_name_for_nira_call(app, client, test_user, monkeypatch):
    """surname/given_names passed to the NIRA verification are derived from the
    canonical full_name, not from form fields (no form fields exist anymore)."""
    called = {}

    def _capture(**kwargs):
        called.update(kwargs)
        return {
            "is_valid_format": True,
            "auto_verified": False,
            "manual_review_required": True,
            "id_number": "CM1234567890AB",
            "verification_id": "NIRA_TEST_REVIEW",
            "risk_score": 0,
        }

    _pair_user_with_profile(app, test_user, full_name="Gift Nakamya",
                           dob=dt.date(1992, 6, 1))
    _login_client(client, test_user)

    from app.kyc import routes as kyc_routes

    monkeypatch.setattr(kyc_routes, "verify_national_id", _capture)
    monkeypatch.setattr(kyc_routes, "check_id_against_watchlist", lambda n: {"recommended_action": "no_action", "risk_score": 0})
    monkeypatch.setattr(kyc_routes, "generate_nira_report", lambda user_id, verification_data: {})
    monkeypatch.setattr(kyc_routes, "db", db)

    resp = client.post(
        "/kyc/verify/national-id",
        data={"id_number": "CM1234567890AB", "consent": "on"},
        follow_redirects=False,
    )
    assert resp.status_code == 302
    assert called.get("surname") == "Nakamya"
    assert called.get("given_names") == "Gift"
    assert called.get("date_of_birth") is not None


def test_profile_editor_persists_canonical_date_of_birth(app, client, test_user):
    """profile.edit_profile now persists date_of_birth into the canonical
    UserProfile identity bank (the single entry point for DOB)."""
    public_id = _pair_user_with_profile(app, test_user, full_name="Gift Nakamya", dob=None)
    _login_client(client, test_user)

    resp = client.post(
        "/profile/edit",
        data={"full_name": "Gift Nakamya", "date_of_birth": "1992-06-01"},
        follow_redirects=False,
    )
    assert resp.status_code == 302

    with app.app_context():
        profile = get_profile_by_user(public_id)
        assert profile.date_of_birth == dt.date(1992, 6, 1)


def test_profile_editor_rejects_invalid_date_of_birth_format(app, client, test_user):
    """An unparseable date_of_birth is rejected with a flash, never persisted."""
    public_id = _pair_user_with_profile(app, test_user, full_name="Gift Nakamya", dob=None)
    _login_client(client, test_user)

    resp = client.post(
        "/profile/edit",
        data={"full_name": "Gift Nakamya", "date_of_birth": "01-06-1992"},
        follow_redirects=False,
    )
    assert resp.status_code == 302

    with app.app_context():
        profile = get_profile_by_user(public_id)
        assert profile.date_of_birth is None


def test_profile_editor_blocks_date_of_birth_change_when_verified(app, client, test_user):
    """date_of_birth stays immutable after verification; an edit attempt is
    blocked and the canonical value is unchanged."""
    public_id = _pair_user_with_profile(
        app, test_user, full_name="Gift Nakamya", dob=dt.date(1992, 6, 1), verified=True
    )
    _login_client(client, test_user)

    resp = client.post(
        "/profile/edit",
        data={"full_name": "Gift Nakamya", "date_of_birth": "2001-01-01"},
        follow_redirects=False,
    )
    assert resp.status_code == 302

    with app.app_context():
        profile = get_profile_by_user(public_id)
        assert profile.date_of_birth == dt.date(1992, 6, 1)
        assert profile.verification_status == "verified"


def test_national_id_html_has_no_identity_reentry_inputs():
    """Template-level guard: verify_national_id.html must not contain the
    legacy duplicate identity fields (surname / given_names). The KYC-first
    branch's full_name input and the date_of_birth input are the single
    canonical entry for a user who has no profile name yet - not a re-entry
    of an already-canonical value."""
    from pathlib import Path

    template = (
        Path(__file__).resolve().parent.parent / "templates" / "kyc" / "verify_national_id.html"
    )
    content = template.read_text(encoding="utf-8")

    assert 'name="surname"' not in content
    assert 'name="given_names"' not in content
    assert 'name="id_number"' in content