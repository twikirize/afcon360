"""
AFCON360 - Wallet Configuration CLI
===================================
Explicit, post-migration initialization of wallet payment-provider defaults
and system-config defaults.

Seeding deliberately does NOT run in the application factory: it previously
executed before Alembic had created the schema, issued a failing query and
left the shared SQLAlchemy session in an aborted transaction that obstructed
startup and migration. Run this command once, after ``flask db upgrade``:

    flask init-wallet-config

Idempotent: existing rows are left untouched, so re-running is safe.
"""

import click
from flask import current_app


def register_wallet_commands(app):
    """Register wallet CLI commands with the Flask app."""

    @app.cli.command("init-wallet-config")
    def init_wallet_config_command():
        """Seed wallet + system-config defaults after a schema migration.

        Runs both initializers in one deliberate transaction. Idempotent and
        safe to re-run. Exits non-zero (after rollback) on failure so the
        operator is never told the database was initialized when it was not.
        """
        from app.admin.owner.wallet_config import (
            initialize_wallet_and_system_defaults,
        )

        try:
            counts = initialize_wallet_and_system_defaults()
        except Exception as exc:
            current_app.logger.exception("init-wallet-config failed")
            click.echo(f"Initialization failed (rolled back): {exc}", err=True)
            raise SystemExit(1)

        click.echo(
            "Defaults initialised: "
            f"{counts['payment_providers']} payment provider(s), "
            f"{counts['system_configs']} system config(s) created."
        )
