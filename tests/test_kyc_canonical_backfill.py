"""Approval-time backfill into the canonical UserProfile identity bank.

KycRecord is evidence, not a second identity store. Approval may fill missing
canonical facts, but must never overwrite existing values or write a verified
profile. Both standard and compliance approval paths share this behavior.
"""
from contextlib import nullcontext
from datetime import date
from types import SimpleNamespace

import pytest

from app.extensions import db
from app.identity.models.user import User
from app.kyc.models import KycRecord
from app.kyc.services import KycService


class _Query:
    """Small query double for the focused service tests."""

    def __init__(self, result):
        self.result = result
        self.filters = []
        self.orders = []

    def filter_by(self, **kwargs):
        self.filters.append(("filter_by", kwargs))
        return self

    def filter(self, *criteria):
        self.filters.append(("filter", criteria))
        return self

    def order_by(self, *criteria):
        self.orders.extend(criteria)
        return self

    def first(self):
        return self.result


def _install_backfill_doubles(monkeypatch, *, user, profile, address_record=None):
    from app.kyc import services

    monkeypatch.setattr(User, "query", _Query(user))
    monkeypatch.setattr(KycRecord, "query", _Query(address_record))
    monkeypatch.setattr(services, "get_profile_by_user", lambda _user: profile)
    monkeypatch.setattr(db.session, "begin_nested", lambda: nullcontext())
    monkeypatch.setattr(db.session, "add", lambda _row: None)


def test_backfill_profile_from_kyc_scope_fills_missing_dob_and_nationality(
    app, monkeypatch
):
    user = SimpleNamespace(id=41, public_id="user-public-41")
    profile = SimpleNamespace(
        verification_status="pending",
        date_of_birth=None,
        nationality=None,
        address=None,
        city=None,
    )
    record = SimpleNamespace(
        user_id=user.id,
        scope={
            "personal_details": {
                "date_of_birth": "1992-06-01",
                "nationality": "Ugandan",
            }
        },
    )
    _install_backfill_doubles(monkeypatch, user=user, profile=profile)

    with app.app_context():
        changed = KycService._backfill_profile_from_kyc_record(record)

    assert changed is True
    assert profile.date_of_birth == date(1992, 6, 1)
    assert profile.nationality == "Ugandan"


def test_backfill_profile_reads_address_and_city_from_approved_address_kyc(
    app, monkeypatch
):
    user = SimpleNamespace(id=42, public_id="user-public-42")
    profile = SimpleNamespace(
        verification_status="pending",
        date_of_birth=None,
        nationality=None,
        address=None,
        city=None,
    )
    address_record = SimpleNamespace(
        address_line1="Plot 12, Kampala Road",
        address_line2="Nakasero",
        city="Kampala",
    )
    record = SimpleNamespace(user_id=user.id, scope={})
    query = _Query(address_record)
    monkeypatch.setattr(User, "query", _Query(user))
    monkeypatch.setattr(KycRecord, "query", query)
    monkeypatch.setattr(
        "app.kyc.services.get_profile_by_user",
        lambda _user: profile,
    )
    monkeypatch.setattr(db.session, "begin_nested", lambda: nullcontext())
    monkeypatch.setattr(db.session, "add", lambda _row: None)

    with app.app_context():
        changed = KycService._backfill_profile_from_kyc_record(record)

    assert changed is True
    assert profile.address == "Plot 12, Kampala Road, Nakasero"
    assert profile.city == "Kampala"
    assert ("filter_by", {
        "user_id": user.id,
        "record_type": "address_verification",
    }) in query.filters


def test_backfill_never_overwrites_existing_canonical_profile_values(
    app, monkeypatch
):
    user = SimpleNamespace(id=43, public_id="user-public-43")
    profile = SimpleNamespace(
        verification_status="pending",
        date_of_birth=date(1988, 4, 3),
        nationality="Rwandan",
        address="Existing canonical address",
        city="Mbarara",
    )
    address_record = SimpleNamespace(
        address_line1="Different address",
        address_line2="",
        city="Kampala",
    )
    record = SimpleNamespace(
        user_id=user.id,
        scope={
            "date_of_birth": "1999-09-09",
            "nationality": "Ugandan",
        },
    )
    _install_backfill_doubles(
        monkeypatch,
        user=user,
        profile=profile,
        address_record=address_record,
    )

    with app.app_context():
        changed = KycService._backfill_profile_from_kyc_record(record)

    assert changed is False
    assert profile.date_of_birth == date(1988, 4, 3)
    assert profile.nationality == "Rwandan"
    assert profile.address == "Existing canonical address"
    assert profile.city == "Mbarara"


def test_backfill_skips_verified_profile_without_mutating_it(app, monkeypatch):
    user = SimpleNamespace(id=44, public_id="user-public-44")
    profile = SimpleNamespace(
        verification_status="verified",
        date_of_birth=None,
        nationality=None,
        address=None,
        city=None,
    )
    record = SimpleNamespace(
        user_id=user.id,
        scope={
            "date_of_birth": "1992-06-01",
            "nationality": "Ugandan",
        },
    )
    _install_backfill_doubles(monkeypatch, user=user, profile=profile)

    with app.app_context():
        changed = KycService._backfill_profile_from_kyc_record(record)

    assert changed is False
    assert profile.date_of_birth is None
    assert profile.nationality is None
    assert profile.address is None
    assert profile.city is None


def test_standard_and_compliance_approval_backfill_before_profile_is_verified(
    app, monkeypatch
):
    from app.audit.forensic_audit import ForensicAuditService
    from app.kyc import services

    observations = []
    current = {"record": None, "user": None, "profile": None}

    monkeypatch.setattr(
        db.session,
        "get",
        lambda model, _record_id: current["record"],
    )
    monkeypatch.setattr(
        User,
        "query",
        property(lambda _cls: _Query(current["user"])),
        raising=False,
    )
    monkeypatch.setattr(
        services,
        "get_profile_by_user",
        lambda _user: current["profile"],
    )
    monkeypatch.setattr(
        KycService,
        "_backfill_profile_from_kyc_record",
        staticmethod(
            lambda _record: observations.append(
                current["profile"].verification_status
            ) or True
        ),
    )
    monkeypatch.setattr(
        KycService,
        "invalidate_user_kyc_cache",
        staticmethod(lambda _user_id: None),
    )
    monkeypatch.setattr(
        KycService,
        "_sync_kyc_level_snapshot",
        staticmethod(lambda _user_id: None),
    )
    monkeypatch.setattr(db.session, "add", lambda _row: None)
    monkeypatch.setattr(db.session, "commit", lambda: None)
    monkeypatch.setattr(
        ForensicAuditService,
        "log_attempt",
        staticmethod(lambda **_kwargs: "audit-id"),
    )
    monkeypatch.setattr(
        ForensicAuditService,
        "log_completion",
        staticmethod(lambda **_kwargs: None),
    )
    monkeypatch.setattr(
        services.ComplianceLogger,
        "log_decision",
        staticmethod(lambda **_kwargs: None),
    )

    with app.app_context():
        for approval_method in (
            KycService.approve_kyc,
            KycService.compliance_approve_kyc,
        ):
            current["user"] = SimpleNamespace(id=45, public_id="user-public-45")
            current["profile"] = SimpleNamespace(
                verification_status="pending",
                rejected_reason="old rejection",
                verified_by=None,
                last_reviewed_at=None,
            )
            current["record"] = SimpleNamespace(
                id=450,
                user_id=45,
                status="pending",
                checked_by=None,
                verified_at=None,
                rejection_reason="old rejection",
                compliance_status="pending",
                compliance_reviewed_at=None,
                compliance_reviewed_by=None,
                compliance_notes=None,
                compliance_case_id=None,
                scope={},
            )

            if approval_method is KycService.approve_kyc:
                approval_method(450, reviewer_id=99)
            else:
                approval_method(450, reviewer_id=99, notes="Reviewed")

            assert current["profile"].verification_status == "verified"

    assert observations == ["pending", "pending"]
