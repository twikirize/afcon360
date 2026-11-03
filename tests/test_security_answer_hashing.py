"""Tests for salted security-answer storage and legacy hash upgrades."""
import hashlib

from app.identity.models.user import User


def _user():
    return User(
        public_id="8e1e22f8-33e0-4b27-8d2f-58eafe4be7e1",
        username="recovery_test_user",
        email="recovery-test@example.invalid",
    )


def test_new_security_answers_use_salted_scrypt_and_verify():
    user = _user()
    user.set_security_answer("First school")

    stored = user.security_answer_hash
    assert stored.startswith("scrypt:")
    assert stored != hashlib.sha256(b"First school").hexdigest()
    assert user.verify_security_answer("First school")
    assert not user.verify_security_answer("Different answer")


def test_legacy_sha256_answer_is_upgraded_after_successful_verification():
    user = _user()
    legacy = hashlib.sha256(b"First school").hexdigest()
    user.security_answer_hash = legacy

    assert user.verify_security_answer("First school")
    assert user.security_answer_hash != legacy
    assert user.security_answer_hash.startswith("scrypt:")
    assert user.verify_security_answer("First school")


def test_security_answer_setter_rejects_empty_values():
    user = _user()
    try:
        user.set_security_answer("   ")
    except ValueError:
        pass
    else:
        raise AssertionError("empty security answers must not be stored")


def test_legacy_sha256_answer_with_outer_whitespace_still_upgrades():
    user = _user()
    legacy = hashlib.sha256(b" First school ").hexdigest()
    user.security_answer_hash = legacy

    assert user.verify_security_answer(" First school ")
    assert user.security_answer_hash != legacy
    assert user.verify_security_answer("First school")



def test_legacy_profile_lowercase_sha256_upgrades_case_insensitively():
    """The older profile editor lowercased answers before storing SHA-256."""
    user = _user()
    legacy = hashlib.sha256(b"first school").hexdigest()
    user.security_answer_hash = legacy

    assert user.verify_security_answer("First School")
    assert user.security_answer_hash.startswith("scrypt:")
    assert user.verify_security_answer("FIRST SCHOOL")


def test_legacy_registration_sha256_with_outer_spaces_upgrades():
    """The old registration writer hashed the raw submitted answer."""
    user = _user()
    legacy = hashlib.sha256(b" First School ").hexdigest()
    user.security_answer_hash = legacy

    assert user.verify_security_answer(" First School ")
    assert user.security_answer_hash.startswith("scrypt:")
    assert user.verify_security_answer("first school")


def test_wallet_identity_verification_uses_shared_recovery_answer_verifier(
    app, monkeypatch
):
    from app.wallet.services.identity_verification_service import (
        IdentityVerificationService,
    )
    from app.extensions import db

    user = _user()
    user.set_security_answer("First School")

    monkeypatch.setattr(db.session, "get", lambda model, user_id: user)
    with app.app_context():
        result = IdentityVerificationService.verify_security_question(
            user_id=123,
            answer="FIRST SCHOOL",
        )

    assert result == {"success": True, "method": "security_question"}
