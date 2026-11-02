"""TOTP secret confidentiality and legacy plaintext upgrade contracts."""
import os
import pyotp
import pytest
from cryptography.fernet import Fernet
from sqlalchemy import inspect as sa_inspect

from app.extensions import db
from app.identity.models.user import MFASecret, User


def test_new_totp_secrets_are_encrypted_at_rest_and_round_trip(app):
    plaintext = pyotp.random_base32()
    record = MFASecret(
        user_id=1,
        mfa_type="totp",
        secret=plaintext,
        is_active=True,
    )

    record.set_totp_secret(plaintext)

    assert record.totp_secret_is_encrypted is True
    assert record.secret.startswith(MFASecret.TOTP_ENCRYPTED_PREFIX)
    assert plaintext not in record.secret
    assert record.get_totp_secret() == plaintext


def test_legacy_plaintext_secret_remains_readable_for_compatibility(app):
    plaintext = pyotp.random_base32()
    record = MFASecret(
        user_id=1,
        mfa_type="totp",
        secret=plaintext,
        is_active=True,
    )

    assert record.totp_secret_is_encrypted is False
    assert record.get_totp_secret() == plaintext
    # Reading alone does not mutate a historical record; successful verification
    # in the authentication/deletion path performs the one-time upgrade.
    assert record.secret == plaintext


def test_encrypted_secret_with_wrong_key_fails_closed(app, monkeypatch):
    from app.utils import security

    record = MFASecret(
        user_id=1,
        mfa_type="totp",
        secret=pyotp.random_base32(),
        is_active=True,
    )
    record.set_totp_secret(record.secret)
    wrong_fernet = Fernet(Fernet.generate_key())
    monkeypatch.setattr(security, "_get_fernet", lambda: wrong_fernet)

    with pytest.raises(ValueError, match="could not be decrypted"):
        record.get_totp_secret()


def test_backup_codes_use_lazy_fernet_and_never_store_plaintext(app):
    codes = ["A1B2C3D4", "E5F6A7B8"]
    record = MFASecret(user_id=1, mfa_type="totp", secret="unused")
    record.store_backup_codes(codes)

    assert all(code not in (record.backup_codes or "") for code in codes)
    assert record.get_backup_codes() == codes


def test_successful_legacy_totp_login_encrypts_the_secret(app, test_admin):
    user_pk = sa_inspect(test_admin).identity[0]
    plaintext = pyotp.random_base32()
    with app.app_context():
        user = db.session.get(User, user_pk)
        user.mfa_enabled = True
        record = MFASecret(
            user_id=user.id,
            mfa_type="totp",
            secret=plaintext,
            is_active=True,
        )
        db.session.add(record)
        db.session.commit()

        from app.auth.routes import _verify_mfa_token

        current_code = pyotp.TOTP(plaintext).now()
        assert _verify_mfa_token(user, current_code) is True
        db.session.refresh(record)
        assert record.totp_secret_is_encrypted is True
        assert record.get_totp_secret() == plaintext



def test_durable_owner_totp_proof_is_bound_to_the_current_secret(app, test_admin):
    user_pk = sa_inspect(test_admin).identity[0]
    with app.app_context():
        user = db.session.get(User, user_pk)
        first_secret = pyotp.random_base32()
        from app.auth.security_policy import record_totp_proof, totp_proof_matches

        record_totp_proof(user, secret=first_secret, commit=True)
        assert totp_proof_matches(user, first_secret) is True
        assert totp_proof_matches(user, pyotp.random_base32()) is False



def test_missing_encryption_key_fails_closed_in_docker(monkeypatch):
    from app.utils.security import get_encryption_key

    monkeypatch.delenv("ENCRYPTION_KEY", raising=False)
    monkeypatch.setenv("APP_ENV", "docker")
    # The container must not fall back to a predictable development key just
    # because this process was accidentally launched with development Flask mode.
    monkeypatch.setenv("FLASK_ENV", "development")

    with pytest.raises(RuntimeError, match="ENCRYPTION_KEY"):
        get_encryption_key()


def test_startup_key_guard_fails_closed_in_docker_even_with_development_flask_mode(monkeypatch):
    from app.utils.security import ensure_encryption_key_configured

    monkeypatch.delenv("ENCRYPTION_KEY", raising=False)
    monkeypatch.setenv("APP_ENV", "docker")
    monkeypatch.setenv("FLASK_ENV", "development")

    with pytest.raises(RuntimeError, match="ENCRYPTION_KEY"):
        ensure_encryption_key_configured()


def test_startup_key_guard_rejects_placeholder_in_production(monkeypatch):
    from app.utils.security import ensure_encryption_key_configured

    monkeypatch.setenv("ENCRYPTION_KEY", "REPLACE_WITH_A_REAL_SECRET")
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("FLASK_ENV", "production")

    with pytest.raises(RuntimeError, match="ENCRYPTION_KEY"):
        ensure_encryption_key_configured()


def test_startup_key_guard_uses_loaded_local_app_config_when_shell_env_is_unset(monkeypatch):
    from app.utils.security import ensure_encryption_key_configured

    monkeypatch.delenv("ENCRYPTION_KEY", raising=False)
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.delenv("FLASK_ENV", raising=False)

    with pytest.warns(RuntimeWarning, match="temporary local-development key"):
        key = ensure_encryption_key_configured(
            app_env="local",
            flask_env="development",
        )

    assert len(key) >= 32
    assert os.getenv("ENCRYPTION_KEY") == key


def test_startup_key_guard_generates_unlogged_local_ephemeral_key(monkeypatch):
    from app.utils.security import ensure_encryption_key_configured

    monkeypatch.delenv("ENCRYPTION_KEY", raising=False)
    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.setenv("FLASK_ENV", "development")

    with pytest.warns(RuntimeWarning, match="temporary local-development key"):
        key = ensure_encryption_key_configured()

    assert len(key) >= 32
    assert os.getenv("ENCRYPTION_KEY") == key


def test_missing_encryption_key_allows_only_local_development_fallback(monkeypatch):
    from app.utils.security import get_encryption_key

    monkeypatch.delenv("ENCRYPTION_KEY", raising=False)
    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.setenv("FLASK_ENV", "development")

    key = get_encryption_key()
    assert isinstance(key, bytes)
    assert len(key) == 44

def test_flask_signing_key_fails_closed_in_docker_with_development_flask_env(monkeypatch):
    from app.utils.security import ensure_secret_key_configured

    monkeypatch.setenv("APP_ENV", "docker")
    monkeypatch.setenv("FLASK_ENV", "development")

    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        ensure_secret_key_configured(
            None,
            app_env="docker",
            flask_env="development",
        )


def test_flask_signing_key_rejects_placeholder_in_production(monkeypatch):
    from app.utils.security import ensure_secret_key_configured

    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        ensure_secret_key_configured(
            "REPLACE_WITH_A_REAL_SECRET",
            app_env="production",
            flask_env="production",
        )


def test_flask_signing_key_allows_real_key_in_deployed_mode():
    from app.utils.security import ensure_secret_key_configured

    assert ensure_secret_key_configured(
        "a-real-secret-key",
        app_env="docker",
        flask_env="development",
    ) == "a-real-secret-key"


def test_flask_signing_key_leaves_local_development_fallback_available():
    from app.utils.security import ensure_secret_key_configured

    assert ensure_secret_key_configured(
        None,
        app_env="local",
        flask_env="development",
    ) is None
