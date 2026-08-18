"""Shared fail-fast checks for the migration-managed PostgreSQL test database."""

import os
from pathlib import Path

from alembic.config import Config as AlembicConfig
from alembic.script import ScriptDirectory
from sqlalchemy import MetaData, Table, inspect, literal, select
from sqlalchemy.engine import make_url


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _migration_heads():
    alembic_config = AlembicConfig(str(PROJECT_ROOT / "migrations" / "alembic.ini"))
    alembic_config.set_main_option(
        "script_location", str(PROJECT_ROOT / "migrations")
    )
    return tuple(ScriptDirectory.from_config(alembic_config).get_heads())


def assert_migrated_postgres_database(engine):
    """Raise when *engine* is not the current, dedicated migrated test DB."""
    database_url = make_url(str(engine.url))
    if database_url.get_backend_name() != "postgresql":
        raise RuntimeError(
            "Tests require PostgreSQL; configure TEST_DATABASE_URL with a "
            f"PostgreSQL URL, got '{database_url.get_backend_name()}'."
        )
    if not database_url.database or not database_url.database.endswith("_test"):
        raise RuntimeError(
            "Tests require a dedicated PostgreSQL database whose name ends "
            "with '_test'; do not point TEST_DATABASE_URL at production."
        )

    configured_url = os.getenv("TEST_DATABASE_URL")
    if configured_url:
        configured_database_url = make_url(configured_url)
        if (
            configured_database_url.get_backend_name() != "postgresql"
            or configured_database_url.host != database_url.host
            or configured_database_url.port != database_url.port
            or configured_database_url.database != database_url.database
            or configured_database_url.username != database_url.username
        ):
            raise RuntimeError(
                "Pytest must use the same PostgreSQL host, port, database, and "
                "user configured by TEST_DATABASE_URL."
            )

    heads = _migration_heads()
    if len(heads) != 1:
        raise RuntimeError(
            "The migration tree must have exactly one head before pytest; "
            f"found {', '.join(heads) or 'none'}."
        )

    try:
        with engine.connect() as connection:
            if connection.scalar(select(literal(1))) != 1:
                raise RuntimeError(
                    "PostgreSQL connectivity check returned an unexpected value"
                )

            inspector = inspect(connection)
            tables = inspector.get_table_names()
            required_tables = {"alembic_version", "users"}
            missing_tables = required_tables.difference(tables)
            if missing_tables:
                raise RuntimeError(
                    "The PostgreSQL test database is missing migrated tables: "
                    f"{', '.join(sorted(missing_tables))}. Apply the reviewed "
                    "Alembic migrations before running pytest."
                )

            required_user_columns = {
                "email_verified_at",
                "phone_verified_at",
                "activated_at",
            }
            actual_user_columns = {
                column["name"] for column in inspector.get_columns("users")
            }
            missing_user_columns = required_user_columns.difference(
                actual_user_columns
            )
            if missing_user_columns:
                raise RuntimeError(
                    "The PostgreSQL test database schema is stale; users is "
                    f"missing: {', '.join(sorted(missing_user_columns))}. Apply "
                    "the reviewed Alembic migrations before running pytest."
                )

            version_table = Table(
                "alembic_version", MetaData(), autoload_with=connection
            )
            revisions = tuple(
                connection.execute(select(version_table.c.version_num)).scalars()
            )
    except RuntimeError:
        raise
    except Exception as exc:
        raise RuntimeError(
            "The PostgreSQL test database is unavailable. Apply the reviewed "
            "Alembic migrations and check TEST_DATABASE_URL."
        ) from exc

    if revisions != heads:
        raise RuntimeError(
            "The PostgreSQL test database is not at the repository migration "
            f"head. Database revision(s): {', '.join(revisions) or 'none'}; "
            f"expected: {', '.join(heads)}. Apply the reviewed Alembic "
            "migrations before running pytest."
        )

    return len(tables)