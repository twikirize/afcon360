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
