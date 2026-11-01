"""Release-hardening regressions for owner MFA and account recovery hashes."""

import hashlib
import uuid
from datetime import datetime, timezone

import pytest
from unittest.mock import patch
from sqlalchemy import text
from werkzeug.security import check_password_hash, generate_password_hash

from app.extensions import db
from app.identity.models.roles_permission import get_or_create_role
from app.identity.models.user import MFASecret, User, UserRole
from app.models.system_config import SystemConfig
from app.utils.enums import WindowMode
from app.wallet.models.regulatory_volume import RegulatoryVolumePolicy


@pytest.mark.usefixtures("db_session")
def test_regulatory_policy_default_does_not_commit_or_close_callers_transaction(app):
    with app.app_context():
        with patch.object(RegulatoryVolumePolicy, "get_active", return_value=None):
            with db.session.begin():
                policy = RegulatoryVolumePolicy.get_active_or_default()
                assert policy.id is None
                assert policy.daily_window_mode is WindowMode.CALENDAR
                assert policy.monthly_window_mode is WindowMode.CALENDAR
                assert policy not in db.session

                # A subsequent statement must still be usable in the same
                # transaction. The legacy implementation committed the
                # session here and invalidated the caller's begin() context.
                assert db.session.execute(text("SELECT 1")).scalar_one() == 1
                assert db.session.in_transaction()


def test_legacy_security_answer_hash_is_upgraded_after_successful_verification():
    answer = "first-school"
    user = User()
    legacy_hash = hashlib.sha256(answer.encode("utf-8")).hexdigest()
    user.security_answer_hash = legacy_hash

    assert user.verify_security_answer("wrong-answer") is False
    assert user.security_answer_hash == legacy_hash

    assert user.verify_security_answer(answer) is True
    upgraded_hash = user.security_answer_hash
    assert upgraded_hash != legacy_hash
    assert check_password_hash(upgraded_hash, answer)
    assert user.verify_security_answer(answer) is True


def test_scrypt_security_answer_hash_is_supported():
    answer = "my-private-answer"
    user = User()
    user.security_answer_hash = generate_password_hash(answer, method="scrypt")

    assert user.verify_security_answer(answer) is True
    assert user.verify_security_answer("not-the-answer") is False


@pytest.mark.usefixtures("db_session")
def test_owner_mfa_setting_cannot_be_enabled_until_active_owners_are_enrolled(app):
    from app.auth.security_settings import (
        OwnerMFAEnrollmentRequired,
        get_owner_mfa_required,
        set_owner_mfa_required,
    )

    with app.app_context():
        existing_setting = SystemConfig.query.filter_by(
            key="REQUIRE_OWNER_MFA"
        ).first()
        old_setting = None
        if existing_setting is not None:
            old_setting = {
                "value": existing_setting.value,
                "value_type": existing_setting.value_type,
                "category": existing_setting.category,
                "description": existing_setting.description,
                "is_public": existing_setting.is_public,
                "requires_restart": existing_setting.requires_restart,
                "updated_by": existing_setting.updated_by,
            }

        role = get_or_create_role("owner", level=1, commit=False)
        suffix = uuid.uuid4().hex[:12]
        owner = User(
            public_id=str(uuid.uuid4()),
            username=f"mfa_gate_{suffix}",
            email=f"mfa_gate_{suffix}@example.test",
        )
        owner.set_password("StrongTestPassword123!")
        owner.is_active = True
        owner.mfa_enabled = False
        db.session.add(owner)
        db.session.flush()
        db.session.add(UserRole(user_id=owner.id, role_id=role.id))
        db.session.commit()

        try:
            with pytest.raises(OwnerMFAEnrollmentRequired):
                set_owner_mfa_required(required=True, updated_by=owner.id)
            db.session.rollback()

            owner = User.query.filter_by(public_id=owner.public_id).one()
            owner.mfa_enabled = True
            mfa_record = MFASecret(
                user_id=owner.id,
                mfa_type="totp",
                secret="JBSWY3DPEHPK3PXP",
                is_active=True,
                last_used=None,
            )
            db.session.add(mfa_record)
            db.session.commit()

            # An active secret created by an older unverified setup flow is
            # not enough evidence that the owner has enrolled successfully.
            with pytest.raises(OwnerMFAEnrollmentRequired):
                set_owner_mfa_required(required=True, updated_by=owner.id)
            db.session.rollback()

            mfa_record = MFASecret.query.filter_by(
                user_id=owner.id, mfa_type="totp"
            ).one()
            mfa_record.last_used = datetime.now(timezone.utc)
            db.session.commit()

            set_owner_mfa_required(required=True, updated_by=owner.id)
            db.session.commit()
            assert get_owner_mfa_required() is True
        finally:
            # This policy key may predate the test. Restore its prior value or
            # remove only the test-created row so the suite never leaves a
            # platform security setting changed for later tests.
            row = SystemConfig.query.filter_by(key="REQUIRE_OWNER_MFA").first()
            if old_setting is None:
                if row is not None:
                    db.session.delete(row)
            elif row is not None:
                for key, value in old_setting.items():
                    setattr(row, key, value)
            db.session.commit()


@pytest.mark.usefixtures("db_session")
def test_totp_enrollment_stays_pending_until_a_valid_code_is_confirmed(app):
    import pyotp

    from app.identity.models.user import MFASecret

    with app.app_context():
        role = get_or_create_role("user", level=6, commit=False)
        suffix = uuid.uuid4().hex[:12]
        user = User(
            public_id=str(uuid.uuid4()),
            username=f"mfa_enroll_{suffix}",
            email=f"mfa_enroll_{suffix}@example.test",
        )
        user.set_password("StrongTestPassword123!")
        user.is_active = True
        user.is_verified = True
        user.email_verified = True
        user.mfa_enabled = False
        db.session.add(user)
        db.session.flush()
        db.session.add(UserRole(user_id=user.id, role_id=role.id))
        db.session.commit()
        public_id = user.public_id
        username = user.username

    client = app.test_client()
    login = client.post(
        "/login",
        data={"username": username, "password": "StrongTestPassword123!"},
        follow_redirects=False,
    )
    assert login.status_code == 302

    setup_page = client.get("/mfa/setup")
    assert setup_page.status_code == 200

    started = client.post("/mfa/enable", data={"mfa_type": "totp"})
    assert started.status_code == 200
    payload = started.get_json()
    assert payload["success"] is True
    secret = payload["secret"]

    with app.app_context():
        saved_user = User.query.filter_by(public_id=public_id).one()
        pending = MFASecret.query.filter_by(
            user_id=saved_user.id,
            mfa_type="totp",
        ).one()
        assert pending.is_active is False
        assert saved_user.mfa_enabled is False

    rejected = client.post("/mfa/confirm", data={"mfa_code": "000000"})
    assert rejected.status_code == 302
    with app.app_context():
        saved_user = User.query.filter_by(public_id=public_id).one()
        pending = MFASecret.query.filter_by(
            user_id=saved_user.id,
            mfa_type="totp",
        ).one()
        assert pending.is_active is False
        assert saved_user.mfa_enabled is False

    valid_code = pyotp.TOTP(secret).now()
    confirmed = client.post("/mfa/confirm", data={"mfa_code": valid_code})
    assert confirmed.status_code == 302
    with app.app_context():
        saved_user = User.query.filter_by(public_id=public_id).one()
        active = MFASecret.query.filter_by(
            user_id=saved_user.id,
            mfa_type="totp",
        ).one()
        assert active.is_active is True
        assert saved_user.mfa_enabled is True
    status_page = client.get("/mfa/status")
    assert status_page.status_code == 200


@pytest.mark.usefixtures("db_session")
def test_unenrolled_owner_is_restricted_to_mfa_enrollment_when_policy_is_forced(app):
    from app.identity.models.roles_permission import get_or_create_role

    with app.app_context():
        role = get_or_create_role("owner", level=1, commit=False)
        suffix = uuid.uuid4().hex[:12]
        owner = User(
            public_id=str(uuid.uuid4()),
            username=f"mfa_owner_gate_{suffix}",
            email=f"mfa_owner_gate_{suffix}@example.test",
        )
        owner.set_password("StrongTestPassword123!")
        owner.is_active = True
        owner.is_verified = True
        owner.email_verified = True
        owner.mfa_enabled = False
        db.session.add(owner)
        db.session.flush()
        db.session.add(UserRole(user_id=owner.id, role_id=role.id))
        db.session.commit()
        username = owner.username

    app.config["REQUIRE_OWNER_MFA"] = True
    client = app.test_client()
    login = client.post(
        "/login",
        data={"username": username, "password": "StrongTestPassword123!"},
        follow_redirects=False,
    )
    assert login.status_code == 302
    assert login.headers["Location"].endswith("/mfa/setup")

    blocked = client.get("/admin/owner/dashboard", follow_redirects=False)
    assert blocked.status_code == 302
    assert blocked.headers["Location"].endswith("/mfa/setup")

    setup = client.get("/mfa/setup")
    assert setup.status_code == 200
