"""Approval-time canonical backfill (single-entry defense in depth).

Contract under test (Canonical Identity Bank / KycService):
- ``KycService.approve_kyc`` backfills canonical facts that are STILL missing
  on the UserProfile from the approved KYC record, BEFORE the profile is
  marked verified. A NIRA record carries collected facts in its ``scope``
  JSON (date_of_birth / nationality); an address-proof record carries its
  facts in its own columns (address_line1/2, city).
- Only blank/missing canonical values are ever written - never an overwrite.
- Immutable identity facts (date_of_birth, nationality) are never written to
  an already-verified profile; address facts are editable and may be filled
  whenever missing.

Companion to test_kyc_single_entry_national_id.py (submission-side backfill).
"""
import datetime as dt

import pytest

from app.extensions import db
from app.identity.models.user import User
from app.kyc.models import KycRecord
from app.kyc.services import KycService
from app.profile.models import UserProfile, get_profile_by_user
from tests.conftest import _login_client


def _mk_profile(app, user, *, dob=None, nationality="UG", address=None,
                city=None, verified=False):
    with app.app_context():
        merged = db.session.merge(user)
        profile = UserProfile(
            user_id=merged.public_id,
            full_name="Backfill Target",
            date_of_birth=dob,
            nationality=nationality,
            address=address,
            city=city,
            profile_completed=True,
            verification_status="verified" if verified else "pending",
        )
        db.session.add(profile)
        db.session.commit()
        user_id, public_id = merged.id, merged.public_id
    return user_id, public_id


def _mk_record(app, user_id, *, record_type="nira_national_id", scope=None,
               address_line1=None, address_line2=None, city=None):
    with app.app_context():
        record = KycRecord(
            user_id=user_id,
            record_type=record_type,
            id_type="national_id",
            document_type="national_id",
            id_number="CM1234567890AB",
            id_number_masked="CM**********AB",
            status="pending",
            scope=scope or {},
            address_line1=address_line1,
            address_line2=address_line2,
            city=city,
            country="UG",
        )
        db.session.add(record)
        db.session.commit()
        return record.id


def _profile_of(app, public_id):
    with app.app_context():
        profile = get_profile_by_user(public_id)
        return {
            "dob": profile.date_of_birth,
            "nationality": profile.nationality,
            "address": profile.address,
            "city": profile.city,
            "status": profile.verification_status,
        }


def test_approval_backfills_missing_dob_from_record_scope(app, client, test_user):
    """Approving a NIRA record whose scope carries a collected DOB fills the
    canonical bank's missing DOB, then marks the profile verified."""
    user_id, public_id = _mk_profile(app, test_user, dob=None)
    record_id = _mk_record(
        app, user_id, scope={"full_name": "Backfill Target", "date_of_birth": "1988-03-14"}
    )
    _login_client(client, test_user)

    with app.app_context():
        KycService.approve_kyc(record_id, reviewer_id=user_id)

    state = _profile_of(app, public_id)
    assert state["dob"] == dt.date(1988, 3, 14)
    assert state["status"] == "verified"


def test_approval_never_overwrites_existing_canonical_values(app, client, test_user):
    """An existing canonical DOB wins: the scope value on the record is
    ignored when the bank already holds the fact (single entry)."""
    user_id, public_id = _mk_profile(app, test_user, dob=dt.date(1992, 6, 1))
    record_id = _mk_record(
        app, user_id, scope={"full_name": "Backfill Target", "date_of_birth": "1980-01-01"}
    )
    _login_client(client, test_user)

    with app.app_context():
        KycService.approve_kyc(record_id, reviewer_id=user_id)

    state = _profile_of(app, public_id)
    assert state["dob"] == dt.date(1992, 6, 1)
    assert state["status"] == "verified"


def test_approval_skips_immutable_backfill_when_already_verified(app, client, test_user):
    """A verified profile is immutable through ordinary flows: the approval
    backfill must not write DOB/nationality into it."""
    user_id, public_id = _mk_profile(app, test_user, dob=None, verified=True)
    record_id = _mk_record(
        app, user_id, scope={"full_name": "Backfill Target", "date_of_birth": "1988-03-14"}
    )
    _login_client(client, test_user)

    with app.app_context():
        KycService.approve_kyc(record_id, reviewer_id=user_id)

    state = _profile_of(app, public_id)
    assert state["dob"] is None
    assert state["status"] == "verified"


def test_address_record_backfills_missing_address_and_city(app, client, test_user):
    """Approving an address-proof record fills the canonical bank's missing
    address (line1 + line2 joined) and city."""
    user_id, public_id = _mk_profile(app, test_user, address=None, city=None)
    record_id = _mk_record(
        app, user_id,
        record_type="address_verification",
        address_line1="12 Kampala Road",
        address_line2="Kabalagala",
        city="Kampala",
    )
    _login_client(client, test_user)

    with app.app_context():
        KycService.approve_kyc(record_id, reviewer_id=user_id)

    state = _profile_of(app, public_id)
    assert state["address"] == "12 Kampala Road Kabalagala"
    assert state["city"] == "Kampala"
    assert state["status"] == "verified"


def test_address_backfill_fills_only_missing_parts(app, client, test_user):
    """Existing canonical address/city parts are never overwritten; only the
    genuinely missing parts are filled from the record."""
    user_id, public_id = _mk_profile(
        app, test_user, address="Old Address 1", city=None
    )
    record_id = _mk_record(
        app, user_id,
        record_type="address_verification",
        address_line1="12 Kampala Road",
        city="Kampala",
    )
    _login_client(client, test_user)

    with app.app_context():
        KycService.approve_kyc(record_id, reviewer_id=user_id)

    state = _profile_of(app, public_id)
    assert state["address"] == "Old Address 1"
    assert state["city"] == "Kampala"
