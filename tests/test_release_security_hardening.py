"""Release-hardening regressions for owner MFA and account recovery hashes."""

import hashlib
import uuid

import pytest
from werkzeug.security import check_password_hash, generate_password_hash

from app.extensions import db
from app.identity.models.roles_permission import get_or_create_role
from app.identity.models.user import User, UserRole
from app.models.system_config import SystemConfig


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
