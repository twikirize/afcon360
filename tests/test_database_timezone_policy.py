"""Regression tests for AFCON360's PostgreSQL UTC session policy.

This file is intentionally runnable with --noconftest: the policy tests need
only a disposable PostgreSQL database and must not invoke the shared row
isolation fixtures or mutate application data.
"""

from pathlib import Path

import pytest
import yaml
from sqlalchemy import create_engine

from app import create_app
from app.config import TestingConfig
from app.extensions import db
from app.utils.database_timezone import assert_postgresql_utc_session


@pytest.fixture(scope="module")
def application():
    app = create_app(config_object=TestingConfig)
    yield app
    with app.app_context():
        db.session.remove()
        db.engine.dispose()


def test_app_sqlalchemy_connection_overrides_nairobi_database_default(application):
    """A raw client sees DB default Nairobi; the app's real engine must see UTC."""
    database_url = application.config["SQLALCHEMY_DATABASE_URI"]
    raw_engine = create_engine(database_url)
    try:
        with raw_engine.connect() as raw_connection:
            raw_timezone = raw_connection.exec_driver_sql("SHOW TimeZone").scalar_one()
        assert raw_timezone == "Africa/Nairobi", (
            "The CI test database must deliberately retain its Nairobi default "
            "so the application override is actually exercised."
        )

        with application.app_context():
            with db.engine.connect() as connection:
                assert assert_postgresql_utc_session(
                    connection, operation="Flask SQLAlchemy regression test"
                ) == "UTC"
    finally:
        raw_engine.dispose()


def test_utc_guard_rejects_a_nairobi_migration_session(application):
    """The shared assertion must fail rather than tolerate a regional session."""
    with application.app_context():
        with db.engine.connect() as connection:
            transaction = connection.begin()
            try:
                connection.exec_driver_sql("SET LOCAL TIME ZONE 'Africa/Nairobi'")
                with pytest.raises(RuntimeError, match="requires PostgreSQL timezone UTC"):
                    assert_postgresql_utc_session(
                        connection, operation="Alembic regression test"
                    )
            finally:
                transaction.rollback()


def test_docker_postgres_service_has_persistent_utc_default():
    """The production resource overlay must inherit the base DB startup command."""
    root = Path(__file__).resolve().parents[1]
    base = yaml.safe_load((root / "docker-compose.yml").read_text(encoding="utf-8"))
    production = yaml.safe_load(
        (root / ".codebuddy" / "docker-compose.prod.yml").read_text(encoding="utf-8-sig")
    )

    assert base["services"]["db"]["command"] == [
        "postgres", "-c", "timezone=UTC"
    ]
    assert "command" not in production["services"]["db"], (
        "The production overlay must inherit the base PostgreSQL UTC command, "
        "not override it."
    )
