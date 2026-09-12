#!/usr/bin/env python
"""
Reset test database - Drop and recreate the test database.

Run: python scripts/reset_test_db.py

Credentials + env handling mirror tests/conftest.py exactly:
  1. Loads `.env.testing` (fallback `.env.test`) into the environment with
     utf-8-sig decoding (same loader as conftest).
  2. Prefers `TEST_DATABASE_URL`, falling back to `DATABASE_URL` (same
     precedence as conftest's `_TEST_DATABASE_URL`).
  3. Derives the base/admin URL from the SAME resolved URL by replacing only
     the trailing `/<dbname>` with `/postgres`, keeping identical
     user/password/host/port — so we never authenticate with the wrong
     credentials (e.g. `postgres` when the test DB uses another user).
  4. Never drops a non-`_test` database.

Output is ASCII-only ([OK] / [FAIL] / [DROP] / [CREATE]) so it cannot crash
on a Windows cp1252 console (no emoji / non-ASCII glyphs).
"""
import os
import sys
from pathlib import Path

import psycopg2

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _load_test_env() -> bool:
    """Load .env.testing (fallback .env.test) into os.environ, like conftest.

    Returns True if an env file was loaded.
    """
    for name in (".env.testing", ".env.test"):
        env_file = PROJECT_ROOT / name
        if not env_file.exists():
            continue
        with open(env_file, "r", encoding="utf-8-sig") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                os.environ[key.strip()] = value.strip().strip("\"'")
        print(f"[OK] Loaded {name}")
        return True
    return False


def reset_test_database() -> bool:
    """Drop and recreate the test database. Returns True on success."""
    _load_test_env()

    db_url = os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")
    if not db_url:
        print("[FAIL] No TEST_DATABASE_URL / DATABASE_URL found in env.")
        return False

    db_name = db_url.split("/")[-1]
    test_db_name = f"{db_name}_test" if not db_name.endswith("_test") else db_name
    if not test_db_name.endswith("_test"):
        print(f"[FAIL] Refusing to operate on non-test database: {test_db_name}")
        return False

    # Same user/password/host/port as the test URL; only the db replaced.
    base_url = db_url.rsplit("/", 1)[0] + "/postgres"

    print(f"[OK] Resetting test database: {test_db_name}")

    try:
        conn = psycopg2.connect(base_url)
        conn.autocommit = True
        cur = conn.cursor()

        cur.execute(
            "SELECT pg_terminate_backend(pg_stat_activity.pid) "
            "FROM pg_stat_activity "
            "WHERE pg_stat_activity.datname = %s "
            "AND pid <> pg_backend_pid()",
            (test_db_name,),
        )

        cur.execute(f'DROP DATABASE IF EXISTS "{test_db_name}"')
        print(f"[DROP] Dropped database {test_db_name}")

        cur.execute(f'CREATE DATABASE "{test_db_name}"')
        print(f"[CREATE] Created database {test_db_name}")

        cur.close()
        conn.close()
        print("[OK] Test database reset successfully.")
        return True
    except Exception as e:
        print(f"[FAIL] Error: {e}")
        return False


if __name__ == "__main__":
    success = reset_test_database()
    sys.exit(0 if success else 1)
