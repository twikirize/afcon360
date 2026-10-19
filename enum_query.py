"""Read-only PostgreSQL enum inventory for a local dedicated test database.

Set TEST_DATABASE_URL in the current shell. This utility rejects non-local
hosts and database names that do not end with the _test suffix. It never reads
application .env files, prints the connection string, or issues DDL/DML.
"""
from __future__ import annotations

import os
import sys
from urllib.parse import urlparse


LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


def validate_local_test_dsn(dsn: str) -> str:
    """Validate and normalize a local PostgreSQL test DSN without connecting."""
    parsed = urlparse(dsn)
    scheme = parsed.scheme
    database = parsed.path.lstrip("/")

    if scheme not in {"postgres", "postgresql", "postgresql+psycopg2"}:
        raise ValueError("TEST_DATABASE_URL must use a PostgreSQL driver URL")
    if not parsed.hostname:
        raise ValueError("TEST_DATABASE_URL must include a local hostname")
    if parsed.hostname not in LOCAL_HOSTS:
        raise ValueError("refusing a non-local PostgreSQL host")
    if not database.endswith("_test"):
        raise ValueError("refusing a database whose name does not end with '_test'")

    # psycopg2 accepts postgresql://, not SQLAlchemy's driver-qualified scheme.
    if scheme == "postgresql+psycopg2":
        return "postgresql://" + dsn.split("://", 1)[1]
    return dsn


def main() -> int:
    configured_dsn = os.environ.get("TEST_DATABASE_URL")
    if not configured_dsn:
        print(
            "ERROR: Set TEST_DATABASE_URL to a local dedicated *_test database; "
            "no .env file or fallback database is used.",
            file=sys.stderr,
        )
        return 2

    try:
        dsn = validate_local_test_dsn(configured_dsn)
    except ValueError as exc:
        print(f"ERROR: Refusing enum inventory connection: {exc}", file=sys.stderr)
        return 2

    try:
        import psycopg2
    except ImportError:
        print("ERROR: psycopg2 is required to run this read-only inventory.", file=sys.stderr)
        return 2

    connection = None
    try:
        connection = psycopg2.connect(
            dsn,
            options="-c default_transaction_read_only=on",
            connect_timeout=5,
        )
        connection.set_session(readonly=True)
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT n.nspname AS schema,
                       t.typname AS enum_name,
                       array_agg(e.enumlabel ORDER BY e.enumsortorder) AS labels
                FROM pg_catalog.pg_type AS t
                JOIN pg_catalog.pg_namespace AS n ON n.oid = t.typnamespace
                JOIN pg_catalog.pg_enum AS e ON e.enumtypid = t.oid
                WHERE n.nspname NOT IN ('pg_catalog', 'information_schema')
                GROUP BY n.nspname, t.typname
                ORDER BY n.nspname, t.typname
                """
            )
            for row in cursor.fetchall():
                print(row)
        connection.rollback()
        return 0
    except Exception as exc:
        print(
            f"ERROR: Read-only enum inventory failed ({type(exc).__name__}).",
            file=sys.stderr,
        )
        return 1
    finally:
        if connection is not None:
            connection.close()


if __name__ == "__main__":
    raise SystemExit(main())
