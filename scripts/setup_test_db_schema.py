"""
setup_test_db_schema.py - Completely reset test database and build its schema
via the REAL Alembic migration history (not db.create_all()).

Run: python scripts/setup_test_db_schema.py

Respects TEST_DATABASE_URL from the environment if set, e.g.:
    $env:TEST_DATABASE_URL="postgresql://israeli:Israelipass@localhost:5432/afcon360_test"
    python scripts/setup_test_db_schema.py

Falls back to hardcoded local defaults if TEST_DATABASE_URL is not set.
"""
import sys
import os
import subprocess
from urllib.parse import urlparse
import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


def reset_test_database():
    """Completely drop and recreate the test database, then migrate it
    to the latest schema using the project's real Alembic history."""

    # Prefer TEST_DATABASE_URL from the environment; fall back to hardcoded
    # local defaults only if it isn't set.
    test_db_url_env = os.environ.get("TEST_DATABASE_URL")

    if test_db_url_env:
        parsed = urlparse(test_db_url_env)
        user = parsed.username
        password = parsed.password
        host = parsed.hostname
        port = parsed.port or 5432
        test_db = parsed.path.lstrip("/")
    else:
        # Local defaults — only used if TEST_DATABASE_URL is not set.
        user = 'israeli'
        password = 'Israelipass'
        host = 'localhost'
        port = 5432
        test_db = 'afcon360_test'

    if not all([user, password, host, test_db]):
        print("Error: TEST_DATABASE_URL is missing one or more required parts "
              "(user, password, host, database name). Check the connection string.")
        return

    try:
        # Connect to the postgres database (not the test db) to drop/recreate it
        conn = psycopg2.connect(
            host=host,
            port=port,
            user=user,
            password=password,
            database='postgres'
        )
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        cur = conn.cursor()

        # Kill all connections to test database
        cur.execute(f"""
            SELECT pg_terminate_backend(pg_stat_activity.pid)
            FROM pg_stat_activity
            WHERE pg_stat_activity.datname = '{test_db}'
            AND pid <> pg_backend_pid()
        """)

        # Drop test database if exists
        cur.execute(f"DROP DATABASE IF EXISTS {test_db}")
        print(f"[OK] Dropped database {test_db}")

        # Create fresh test database
        cur.execute(f"CREATE DATABASE {test_db}")
        print(f"[OK] Created database {test_db}")

        cur.close()
        conn.close()
        print("[OK] Test database reset successfully!")

        # Build schema using the REAL migration history — not db.create_all(),
        # which only creates tables for whatever happens to be imported into
        # SQLAlchemy's metadata at call time and was silently skipping `users`,
        # `organisations`, `roles`, etc. Running the actual Alembic chain
        # guarantees the test DB matches production schema exactly.
        test_db_url = test_db_url_env or f"postgresql://{user}:{password}@{host}:{port}/{test_db}"

        env = os.environ.copy()
        env["DATABASE_URL"] = test_db_url
        env["FLASK_APP"] = env.get("FLASK_APP", "app:create_app")

        print(f"[..] Running 'flask db upgrade' against {test_db} ...")
        result = subprocess.run(
            ["flask", "db", "upgrade"],
            env=env,
            capture_output=True,
            text=True,
        )
        print(result.stdout)
        if result.returncode != 0:
            print(result.stderr)
            raise RuntimeError(
                "flask db upgrade failed against test database — see output above. "
                "Check that app/config.py's TestingConfig reads the same "
                "environment variable (DATABASE_URL) for SQLALCHEMY_DATABASE_URI, "
                "or this may have migrated the wrong database."
            )

        print("[OK] Test database migrated to latest revision via Alembic")
        print("[OK] Test database schema ready!")

    except Exception as e:
        print(f"Error: {e}")
        print("\nMake sure PostgreSQL is running and credentials are correct")


if __name__ == '__main__':
    reset_test_database()