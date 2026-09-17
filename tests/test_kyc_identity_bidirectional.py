"""Bidirectional canonical identity entry across KYC flows (IDENT-KYC).

Contract under test (Canonical Identity Bank, bidirectional single entry):
- Personal identity (full_name / date_of_birth) lives ONCE in UserProfile.
- Profile-first: a user who already holds canonical facts sees them rendered
  read-only on KYC forms; nothing is re-asked and nothing is overwritten.
- KYC-first: a user with NO canonical full_name is collected on the NIRA form
  (full_name + optional date_of_birth). The first legitimate source provides a
  missing fact is written to the canonical UserProfile (never overwritten), and
  all later workflows read that value - including the profile editor.
- A KYC evidence record (KycRecord) stays evidence: the NIN/id_number submitted
  is NOT copied into the canonical bank, and a different evidence document
  never overwrites the canonical identifier.
- A verified canonical profile is never written by any KYC flow.

Tests use the real DB-backed HTTP path (no monkeypatching of the write or the
identity reads), following the style of test_kyc_single_entry_national_id.py.
"""
import datetime as dt

from app.extensions import db
from app.profile.models import UserProfile, get_profile_by_user
from tests.conftest import _login_client


def _pair_user_with_profile(app, user, *, full_name="Gift Nakamya",
                            dob=None, verified=False, id_type=None, id_number=None):
    """Attach a canonical UserProfile identity bank to a committed user and
    return the user's public_id."""
    with app.app_context():
        merged = db.session.merge(user)
        profile = UserProfile(
            user_id=merged.public_id,
            full_name=full_name,
            date_of_birth=dob,
            nationality="UG",
            id_type=id_type,
            id_number=id_number,
            profile_completed=True,
            verification_status="verified" if verified else "pending",
        )
        db.session.add(profile)
        db.session.commit()
        return merged.public_id


def _nira_page(client):
    return client.get("/kyc/verify/national-id")


def _submit_nira(client, *, id_number="CM1234567890AB", full_name=None, date_of_birth=None):
    data = {"id_number": id_number, "consent": "on"}
    if full_name is not None:
        data["full_name"] = full_name
    if date_of_birth is not None:
        data["date_of_birth"] = date_of_birth
    return client.post("/kyc/verify/national-id", data=data, follow_redirects=False)


def _latest_nira_record(app, user):
    from app.kyc.models import KycRecord

    with app.app_context():
        merged = db.session.merge(user)
        return (
            KycRecord.query.filter_by(user_id=merged.id, record_type="nira_national_id")
            .order_by(KycRecord.created_at.desc())
            .first()
        )


def test_a_profile_first_nira_renders_read_only_with_no_collection_inputs(app, client, test_user):
    """Profile-first: a user who already holds canonical facts sees them
    read-only; the KYC-first collection inputs are NOT rendered."""
    _pair_user_with_profile(
        app, test_user, full_name="Gift Nakamya", dob=dt.date(1992, 6, 1)
    )
    _login_client(client, test_user)

    resp = _nira_page(client)
    assert resp.status_code == 200
    body = resp.data.decode("utf-8")

    assert "Gift Nakamya" in body
    assert "1992-06-01" in body
    assert 'name="full_name"' not in body
    assert 'id="date_of_birth"' not in body
    assert 'name="id_number"' in body


def test_b_kyc_submit_cannot_overwrite_existing_canonical_facts(app, client, test_user):
    """KYC conflicts never win: a NIRA submit carrying a competing full_name /
    date_of_birth leaves the canonical bank byte-for-byte unchanged."""
    public_id = _pair_user_with_profile(
        app, test_user, full_name="Gift Nakamya", dob=dt.date(1992, 6, 1),
        id_type="national_id", id_number="CANON-999",
    )
    _login_client(client, test_user)

    resp = _submit_nira(
        client, full_name="Hacker Name", date_of_birth="2000-01-01",
    )
    assert resp.status_code == 302

    with app.app_context():
        profile = get_profile_by_user(public_id)
        assert profile.full_name == "Gift Nakamya"
        assert profile.date_of_birth == dt.date(1992, 6, 1)
        assert profile.id_number == "CANON-999"
        assert profile.verification_status != "verified"

        record = _latest_nira_record(app, test_user)
        assert record is not None
        assert record.id_number == "CM1234567890AB"


def test_c_canonical_identifier_survives_different_evidence_document(app, client, test_user):
    """A NIN submitted as evidence never overwrites the canonical identifier on
    the profile; evidence stays in KycRecord, canonical stays in UserProfile."""
    public_id = _pair_user_with_profile(
        app, test_user, full_name="Gift Nakamya", dob=dt.date(1992, 6, 1),
        id_type="national_id", id_number="CANON-999",
    )
    _login_client(client, test_user)

    resp = _submit_nira(client, id_number="CM1234567890AB")
    assert resp.status_code == 302

    with app.app_context():
        profile = get_profile_by_user(public_id)
        assert profile.id_number == "CANON-999"
        assert profile.id_type == "national_id"

        record = _latest_nira_record(app, test_user)
        assert record is not None
        assert record.id_number == "CM1234567890AB"


def test_kyc_first_writes_missing_canonical_facts_and_keeps_evidence_separate(app, client, test_user):
    """KYC-first write (real DB path): a user with no canonical full_name is
    collected on the NIRA form once; full_name + date_of_birth land on
    UserProfile as canonical (DOB as datetime.date), while the NIN stays a
    KycRecord evidence snapshot only."""
    _login_client(client, test_user)

    page = _nira_page(client)
    assert page.status_code == 200
    page_body = page.data.decode("utf-8")
    assert 'name="full_name"' in page_body
    assert 'id="date_of_birth"' in page_body

    resp = _submit_nira(
        client, full_name="Jane Doe", date_of_birth="1991-04-10",
    )
    assert resp.status_code == 302

    with app.app_context():
        merged = db.session.merge(test_user)
        public_id = merged.public_id

        profile = get_profile_by_user(public_id)
        assert profile is not None
        assert profile.full_name == "Jane Doe"
        assert profile.date_of_birth == dt.date(1991, 4, 10)
        assert profile.verification_status != "verified"

        record = _latest_nira_record(app, test_user)
        assert record is not None
        assert record.id_number == "CM1234567890AB"
        assert profile.id_number is None
        assert profile.id_type is None


def test_f_profile_editor_reads_kyc_written_canonical_values(app, client, test_user):
    """Reverse read: after a KYC-first write, the profile editor prefills the
    same canonical values - the user is never asked to re-enter them."""
    _login_client(client, test_user)

    resp = _submit_nira(
        client, full_name="Jane Doe", date_of_birth="1991-04-10",
    )
    assert resp.status_code == 302

    edit_resp = client.get("/profile/edit")
    assert edit_resp.status_code == 200
    edit_body = edit_resp.data.decode("utf-8")

    assert 'value="Jane Doe"' in edit_body
    assert 'value="1991-04-10"' in edit_body


def test_g_kyc_first_collection_limits_fields_to_shared_identity(app, client, test_user):
    """KYC-first collection asks only for the shared personal-identity facts a
    KYC process actually needs (full_name + date_of_birth); fan/social fields
    are never collected on a KYC form."""
    _login_client(client, test_user)

    resp = _nira_page(client)
    assert resp.status_code == 200
    body = resp.data.decode("utf-8")

    assert 'name="full_name"' in body
    assert 'id="date_of_birth"' in body
    assert 'name="id_number"' in body
    for forbidden in ("bio", "display_name", "fan_team", "preferences", "likes", "nationality"):
        assert f'name="{forbidden}"' not in body


def test_h_verified_canonical_profile_is_never_written_by_kyc(app, client, test_user):
    """A verified profile is immutable: a NIRA submit (collection or not) never
    changes it, and the KYC-first collection form is not presented."""
    public_id = _pair_user_with_profile(
        app, test_user, full_name="Gift Nakamya", dob=dt.date(1992, 6, 1), verified=True
    )
    _login_client(client, test_user)

    page = _nira_page(client)
    assert page.status_code == 200
    assert 'name="full_name"' not in page.data.decode("utf-8")

    resp = _submit_nira(
        client, full_name="Hacker Name", date_of_birth="2000-01-01",
    )
    assert resp.status_code == 302

    with app.app_context():
        profile = get_profile_by_user(public_id)
        assert profile.full_name == "Gift Nakamya"
        assert profile.date_of_birth == dt.date(1992, 6, 1)
        assert profile.verification_status == "verified"