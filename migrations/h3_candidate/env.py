from __future__ import annotations

import os
import re

from alembic import context
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.pool import NullPool

try:
    from dotenv import dotenv_values
except ImportError:  # pragma: no cover
    dotenv_values = None


config = context.config
_CANDIDATE_DATABASE = re.compile(r"^afcon360_h3_candidate(?:_[a-z0-9][a-z0-9-]*)?_test$")
_POSTGRESQL_18_4 = re.compile(r"^18\.4(?:\D|$)")


def _candidate_url():
    raw = os.environ.get("H3_CANDIDATE_DATABASE_URL")
    if not raw:
        values = dict(dotenv_values(".env")) if dotenv_values is not None else {}
        raw = (
            os.environ.get("TEST_DATABASE_URL")
            or os.environ.get("DATABASE_URL")
            or os.environ.get("SQLALCHEMY_DATABASE_URI")
            or values.get("TEST_DATABASE_URL")
            or values.get("DATABASE_URL")
            or values.get("SQLALCHEMY_DATABASE_URI")
        )
        if raw:
            # Never reuse the configured test DB name: only retarget its local credentials
            # to a separately created H3 candidate database.
            url = make_url(str(raw))
            if url.get_backend_name() != "postgresql":
                raise RuntimeError("H3 candidate tests require PostgreSQL.")
            if (url.host or "").lower() not in {"localhost", "127.0.0.1", "::1"}:
                raise RuntimeError("H3 candidate tests are restricted to loopback PostgreSQL.")
            url = url.set(database="afcon360_h3_candidate_test")
        else:
            raise RuntimeError("Set H3_CANDIDATE_DATABASE_URL or provide local test connection configuration.")
    else:
        url = make_url(str(raw))

    if url.get_backend_name() != "postgresql":
        raise RuntimeError("H3 candidate tests require PostgreSQL.")
    if (url.host or "").lower() not in {"localhost", "127.0.0.1", "::1"}:
        raise RuntimeError("H3 candidate tests are restricted to loopback PostgreSQL.")
    if not _CANDIDATE_DATABASE.fullmatch(url.database or ""):
        raise RuntimeError(
            "Refusing to run the H3 candidate outside a database named afcon360_h3_candidate*_test."
        )
    expected_database = os.environ.get("H3_CANDIDATE_DATABASE_NAME")
    if expected_database and expected_database != url.database:
        raise RuntimeError("The candidate URL database does not match the explicitly selected candidate database.")
    return url


def _assert_empty_target(connection):
    server_version = str(connection.execute(text("SHOW server_version")).scalar_one())
    if not _POSTGRESQL_18_4.match(server_version):
        raise RuntimeError(
            f"H3-A replay is pinned to PostgreSQL 18.4 for this verification stage; observed {server_version!r}."
        )
    relation_count = int(
        connection.execute(
            text(
                """
                SELECT count(*)
                FROM pg_catalog.pg_class AS c
                JOIN pg_catalog.pg_namespace AS n ON n.oid = c.relnamespace
                WHERE n.nspname !~ '^pg_'
                  AND n.nspname <> 'information_schema'
                  AND c.relkind IN ('r', 'p', 'v', 'm', 'S', 'f')
                """
            )
        ).scalar_one()
    )
    type_count = int(
        connection.execute(
            text(
                """
                SELECT count(*)
                FROM pg_catalog.pg_type AS t
                JOIN pg_catalog.pg_namespace AS n ON n.oid = t.typnamespace
                WHERE n.nspname !~ '^pg_'
                  AND n.nspname <> 'information_schema'
                  AND t.typrelid = 0
                  AND t.typtype IN ('b', 'c', 'd', 'e', 'p', 'r')
                """
            )
        ).scalar_one()
    )
    routine_count = int(
        connection.execute(
            text(
                """
                SELECT count(*)
                FROM pg_catalog.pg_proc AS p
                JOIN pg_catalog.pg_namespace AS n ON n.oid = p.pronamespace
                WHERE n.nspname !~ '^pg_'
                  AND n.nspname <> 'information_schema'
                """
            )
        ).scalar_one()
    )
    extension_count = int(
        connection.execute(
            text(
                """
                SELECT count(*)
                FROM pg_catalog.pg_extension AS e
                JOIN pg_catalog.pg_namespace AS n ON n.oid = e.extnamespace
                WHERE n.nspname !~ '^pg_'
                  AND n.nspname <> 'information_schema'
                """
            )
        ).scalar_one()
    )
    extra_schema_count = int(
        connection.execute(
            text(
                """
                SELECT count(*)
                FROM pg_catalog.pg_namespace
                WHERE nspname !~ '^pg_'
                  AND nspname <> 'information_schema'
                  AND nspname <> 'public'
                """
            )
        ).scalar_one()
    )
    counts = {
        "relations": relation_count,
        "custom_types": type_count,
        "routines": routine_count,
        "extensions": extension_count,
        "extra_schemas": extra_schema_count,
    }
    if any(counts.values()):
        raise RuntimeError(
            "H3 candidate refuses a non-empty target. Use a newly created approved disposable database; "
            f"no schema change was started. Observed object counts: {counts!r}"
        )


def run_migrations_offline():
    raise RuntimeError("H3 candidate verification requires a live, local, disposable PostgreSQL database.")


def run_migrations_online():
    url = _candidate_url()
    engine = create_engine(url, poolclass=NullPool, connect_args={"connect_timeout": 5})
    try:
        with engine.connect() as connection:
            _assert_empty_target(connection)
            # Finish the read-only preflight transaction before Alembic starts its DDL transaction.
            connection.commit()
            context.configure(
                connection=connection,
                target_metadata=None,
                version_table_schema="public",
                transaction_per_migration=True,
                compare_type=False,
                compare_server_default=False,
            )
            with context.begin_transaction():
                context.run_migrations()
    finally:
        engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
