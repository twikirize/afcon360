"""Production startup must require a dedicated refund-policy HMAC key."""
import pytest

from app.config import Config


def _valid_production_environment(monkeypatch):
    monkeypatch.setattr(Config, "FLASK_ENV", "production")
    monkeypatch.setattr(
        Config, "SQLALCHEMY_DATABASE_URI", "postgresql://afcon:secret@localhost/afcon_test"
    )
    monkeypatch.setattr(Config, "SECRET_KEY", "application-secret-key-" + "a" * 32)
    monkeypatch.setattr(Config, "SECURITY_SALT", "security-salt-" + "b" * 32)
    monkeypatch.setattr(Config, "ENCRYPTION_KEY_VALUE", "encryption-key-" + "c" * 32)


def test_production_rejects_missing_dedicated_refund_signing_key(monkeypatch):
    _valid_production_environment(monkeypatch)
    monkeypatch.delenv("REFUND_POLICY_SIGNING_KEY", raising=False)

    with pytest.raises(RuntimeError, match="REFUND_POLICY_SIGNING_KEY"):
        Config.validate_for_production()


def test_production_rejects_short_refund_signing_key(monkeypatch):
    _valid_production_environment(monkeypatch)
    monkeypatch.setenv("REFUND_POLICY_SIGNING_KEY", "too-short")

    with pytest.raises(RuntimeError, match="REFUND_POLICY_SIGNING_KEY"):
        Config.validate_for_production()


def test_production_rejects_reusing_secret_key_for_refund_signing(monkeypatch):
    _valid_production_environment(monkeypatch)
    monkeypatch.setenv("REFUND_POLICY_SIGNING_KEY", Config.SECRET_KEY)

    with pytest.raises(RuntimeError, match="REFUND_POLICY_SIGNING_KEY"):
        Config.validate_for_production()


def test_production_accepts_distinct_long_refund_signing_key(monkeypatch):
    _valid_production_environment(monkeypatch)
    monkeypatch.setenv("REFUND_POLICY_SIGNING_KEY", "refund-policy-key-" + "d" * 40)

    Config.validate_for_production()


def test_nonproduction_keeps_secret_key_fallback_compatibility(monkeypatch):
    monkeypatch.setattr(Config, "FLASK_ENV", "testing")
    monkeypatch.delenv("REFUND_POLICY_SIGNING_KEY", raising=False)

    # The production-only guard must not break development or test configs.
    Config.validate_for_production()
