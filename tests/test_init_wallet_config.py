"""Regression tests for the app-factory / migration-startup defect.

Covers the owner-approved corrective fix:

  * the application factory is registration-only for wallet config — it must
    not seed wallet/system defaults before Alembic has created the schema;
  * ``flask init-wallet-config`` initializes defaults in one deliberate
    transaction;
  * initialization is idempotent;
  * a failed initialization rolls back and reports failure (non-zero exit);
  * a missing pre-migration ``system_configs`` table cannot poison the shared
    SQLAlchemy session through the factory-time CSP cache refresh.

Uses only the shared session ``app``/``client`` fixtures and the existing
project conventions. No schema or migration changes.
"""

import pytest
from sqlalchemy import text

from app import refresh_csp_strict_cache
from app.extensions import db
from app.models.system_config import SystemConfig
from app.wallet.models.config import PaymentProviderConfig
from app.admin.owner.wallet_config import (
    init_wallet_config,
    initialize_wallet_and_system_defaults,
)

SITE_NAME = "SITE_NAME"
PROVIDER = "flutterwave"


def _clean_defaults():
    """Remove the seeded default rows so a test starts from a known state."""
    SystemConfig.query.filter_by(key=SITE_NAME).delete()
    PaymentProviderConfig.query.filter_by(provider_name=PROVIDER).delete()
    db.session.commit()


# ---------------------------------------------------------------------------
# A. Factory is registration-only
# ---------------------------------------------------------------------------

def test_init_wallet_config_is_registration_only(monkeypatch):
    """``init_wallet_config(app)`` must register the blueprint and never seed."""
    from flask import Flask
    from app.wallet.models import config as wallet_model
    from app.models import system_config as sysconf_model

    calls = []

    def _forbidden(*args, **kwargs):
        calls.append(1)
        raise AssertionError("factory path must not seed wallet/system defaults")

    monkeypatch.setattr(
        wallet_model.PaymentProviderConfig, "initialize_defaults", classmethod(_forbidden)
    )
    monkeypatch.setattr(
        sysconf_model.SystemConfig, "initialize_defaults", classmethod(_forbidden)
    )

    fresh = Flask("factory_probe")
    init_wallet_config(fresh)

    assert "wallet_config" in fresh.blueprints
    assert calls == []


def test_create_app_does_not_seed_defaults(app):
    """Building the app must not create wallet/system default rows."""
    with app.app_context():
        _clean_defaults()

    from app import create_app
    from app.config import TestingConfig

    probe = create_app(config_object=TestingConfig)

    with probe.app_context():
        assert SystemConfig.query.filter_by(key=SITE_NAME).first() is None
        assert PaymentProviderConfig.query.filter_by(provider_name=PROVIDER).first() is None


# ---------------------------------------------------------------------------
# B. Explicit, deliberate initialization (CLI + helper)
# ---------------------------------------------------------------------------

def test_initialize_defaults_success(app):
    with app.app_context():
        _clean_defaults()
        counts = initialize_wallet_and_system_defaults()

        assert counts["payment_providers"] >= 1
        assert counts["system_configs"] >= 1
        assert SystemConfig.query.filter_by(key=SITE_NAME).first() is not None
        assert PaymentProviderConfig.query.filter_by(provider_name=PROVIDER).first() is not None


def test_initialize_defaults_is_idempotent(app):
    with app.app_context():
        _clean_defaults()
        first = initialize_wallet_and_system_defaults()
        second = initialize_wallet_and_system_defaults()

        assert first["payment_providers"] >= 1
        assert first["system_configs"] >= 1
        assert second["payment_providers"] == 0
        assert second["system_configs"] == 0
        assert PaymentProviderConfig.query.filter_by(provider_name=PROVIDER).count() == 1


def test_failure_rolls_back_and_does_not_persist(app, monkeypatch):
    """A failure in the second initializer must roll back the first's rows."""
    with app.app_context():
        _clean_defaults()

        def _boom(cls, commit=True):
            raise RuntimeError("simulated system-config failure")

        monkeypatch.setattr(SystemConfig, "initialize_defaults", classmethod(_boom))

        with pytest.raises(RuntimeError):
            initialize_wallet_and_system_defaults()

        # Provider rows prepared in the same transaction were rolled back.
        assert PaymentProviderConfig.query.filter_by(provider_name=PROVIDER).first() is None
        assert SystemConfig.query.filter_by(key=SITE_NAME).first() is None


def test_cli_command_initializes_defaults(app):
    with app.app_context():
        _clean_defaults()

    runner = app.test_cli_runner()
    result = runner.invoke(args=["init-wallet-config"])

    assert result.exit_code == 0, result.output
    with app.app_context():
        assert SystemConfig.query.filter_by(key=SITE_NAME).first() is not None
        assert PaymentProviderConfig.query.filter_by(provider_name=PROVIDER).first() is not None


def test_cli_command_reports_failure_with_nonzero_exit(app, monkeypatch):
    def _boom(cls, commit=True):
        raise RuntimeError("simulated failure")

    monkeypatch.setattr(SystemConfig, "initialize_defaults", classmethod(_boom))

    runner = app.test_cli_runner()
    result = runner.invoke(args=["init-wallet-config"])

    assert result.exit_code == 1
    assert "rolled back" in result.output


# ---------------------------------------------------------------------------
# C. CSP cache refresh must not poison the session
# ---------------------------------------------------------------------------

class _AbortingQuery:
    """Mimic ``SystemConfig.query`` against a missing ``system_configs`` table.

    Issues a real failing statement (which aborts the shared transaction),
    then returns as a missing-relation error would. This reproduces the
    pre-migration condition that previously left the session poisoned.
    """

    def filter_by(self, *args, **kwargs):
        return self

    def first(self):
        db.session.execute(text("SELECT value FROM system_configs_missing_probe"))
        return None


def test_csp_refresh_with_missing_table_does_not_poison_session(app, monkeypatch):
    with app.app_context():
        monkeypatch.setattr(SystemConfig, "query", _AbortingQuery())

        # Fails closed (False) and never raises.
        assert refresh_csp_strict_cache() is False

        # The session must be usable again rather than stuck in
        # InFailedSqlTransaction (the defect this fix removes).
        db.session.execute(text("SELECT 1"))
