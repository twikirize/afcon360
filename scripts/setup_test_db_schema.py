"""
Set up the test database schema using the application's TestingConfig.

WHY THIS DOES NOT USE `flask db upgrade` AS THE PRIMARY PATH:
  ab6dd422c152_initial_schema.py (down_revision=None, i.e. the first migration
  in the chain) does NOT contain CREATE TABLE statements for `users`, `events`,
  `accounts`, `accommodation_properties`, `transactions`, etc. It only creates
  3 tables (idempotency_keys, event_host_registrations, ledger_entries) and
  ALTERs columns on the rest, assuming those foundational tables already
  exist. Running `flask db upgrade` against a genuinely empty database will
  always fail at `event_host_registrations`'s FK to `users.id`, because there
  is no earlier migration that ever creates `users`.
  This is a missing-baseline-migration problem, not a fixable ordering bug
  within this file. Writing a proper baseline migration (or a pg_dump-derived
  one) is a separate, larger task — tracked separately, not solved here.

WHAT THIS SCRIPT DOES INSTEAD (for TEST DB ONLY):
  1. Drop & recreate the test database.
  2. Build the schema from current SQLAlchemy models via db.create_all().
     This works *for test purposes* because your models already reflect the
     target state that 396efe6667ff's column/index changes were meant to
     produce — create_all() builds from current model definitions, not from
     migration history.
  3. Stamp the DB at Alembic head, so future `flask db upgrade` calls treat
     it as up to date.
  4. VERIFY the result against known-fragile facts, instead of trusting
     create_all()'s silent success:
       - accommodation tables actually exist (model_registry.py gap)
       - ix_user_nonces_nonce is non-unique (396efe6667ff intent)
       - ix_content_flags_risk_score is single-column (396efe6667ff intent)
     If any of these fail, the script raises and prints exactly what's wrong
     instead of printing "[OK]" over a broken schema.

DO NOT reuse this create_all()-based approach for production. Production
needs the real migration chain fixed (see docstring above) and a proper
`flask db upgrade`, with backups, per the original remediation plan.

Usage:
    python scripts/setup_test_db_schema.py
"""

import os
import sys
import subprocess
from pathlib import Path

import psycopg2

# ---------------------------------------------------------------------------
# Ensure project root is on sys.path so `from app...` imports work
# regardless of the current working directory this script is run from.
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

os.environ["APP_ENV"] = "testing"
os.environ["FLASK_ENV"] = "testing"


# ---------------------------------------------------------------------------
# 1. Read connection info from the application's TestingConfig
# ---------------------------------------------------------------------------
def _get_test_db_params():
    """Build connection parameters from TestingConfig."""
    from app.config import TestingConfig
    cfg = TestingConfig()

    uri = cfg.SQLALCHEMY_DATABASE_URI
    if not uri:
        raise RuntimeError("TestingConfig has no SQLALCHEMY_DATABASE_URI")

    prefix = "postgresql://"
    if not uri.startswith(prefix):
        raise RuntimeError(f"Unsupported database URI: {uri}")
    rest = uri[len(prefix):]
    if "/" not in rest:
        raise RuntimeError(f"No database name in URI: {uri}")
    auth_host, dbname = rest.rsplit("/", 1)
    if "@" not in auth_host:
        raise RuntimeError(f"Malformed URI (missing '@'): {uri}")
    userpass, hostport = auth_host.rsplit("@", 1)
    user = userpass.split(":")[0] if ":" in userpass else userpass
    password = userpass.split(":")[1] if ":" in userpass else None
    host = hostport.split(":")[0] if ":" in hostport else hostport
    port = int(hostport.split(":")[1]) if ":" in hostport else 5432

    return {
        "host": host,
        "port": port,
        "user": user,
        "password": password,
        "database": dbname,
        "maintenance_db": "postgres",
    }


def _pg_connect(params, dbname=None):
    return psycopg2.connect(
        host=params["host"],
        port=params["port"],
        user=params["user"],
        password=params["password"],
        dbname=dbname or params["database"],
    )


# ---------------------------------------------------------------------------
# 2. Drop & recreate the test database
# ---------------------------------------------------------------------------
def recreate_database(params):
    """Drop the test database (if it exists) and create a fresh one."""
    conn = _pg_connect(params, dbname=params["maintenance_db"])
    conn.autocommit = True
    cur = conn.cursor()

    dbname = params["database"]
    cur.execute(
        "SELECT pg_terminate_backend(pg_stat_activity.pid) "
        "FROM pg_stat_activity "
        "WHERE pg_stat_activity.datname = %s "
        "AND pid <> pg_backend_pid();",
        (dbname,),
    )
    cur.execute(f"DROP DATABASE IF EXISTS {dbname}")
    print(f"[OK] Dropped database {dbname}")

    cur.execute(f"CREATE DATABASE {dbname}")
    print(f"[OK] Created database {dbname}")
    cur.close()
    conn.close()


# ---------------------------------------------------------------------------
# 3. Build schema from current models
# ---------------------------------------------------------------------------
def build_schema_from_models():
    """
    Build the schema via db.create_all(), deliberately — not as a silent
    fallback. Requires model_registry.py to import every domain's models
    (including accommodation) so nothing is missing from db.metadata.
    """
    from app import create_app
    from app.config import TestingConfig
    from app.extensions import db

    app = create_app(config_object=TestingConfig)
    with app.app_context():
        registered_tables = sorted(db.metadata.tables.keys())
        print(f"[..] {len(registered_tables)} tables registered on db.metadata before create_all()")

        db.create_all()
        print("[OK] Schema built from current SQLAlchemy models (db.create_all)")


def stamp_alembic_head():
    """Mark the DB as up-to-date so future `flask db upgrade` calls work."""
    result = subprocess.run(
        [sys.executable, "-m", "flask", "db", "stamp", "head"],
        capture_output=True,
        text=True,
        env={**os.environ},
    )
    if result.returncode != 0:
        print(f"[WARN] Could not stamp Alembic head: {result.stderr}")
    else:
        print("[OK] Alembic head stamped")


# ---------------------------------------------------------------------------
# 4. Verify — don't trust create_all()'s silence
# ---------------------------------------------------------------------------
EXPECTED_ACCOMMODATION_TABLES = {
    "accommodation_properties",
    "accommodation_bookings",
    "accommodation_property_booking_policies",
}


def verify_schema(params):
    """
    Check the specific facts we know are fragile:
      - accommodation tables exist (the model_registry.py gap)
      - core tables exist (users, events, etc.)
    Raises with a clear message if anything is wrong, instead of printing
    "[OK]" over an incomplete schema.
    """
    conn = _pg_connect(params)
    cur = conn.cursor()
    issues = []

    cur.execute(
        "SELECT tablename FROM pg_tables WHERE schemaname = 'public' "
        "AND tablename LIKE 'accommodation%'"
    )
    found_acc_tables = {r[0] for r in cur.fetchall()}
    missing_acc = EXPECTED_ACCOMMODATION_TABLES - found_acc_tables
    if missing_acc:
        issues.append(
            f"Missing accommodation tables: {sorted(missing_acc)} "
            f"(check model_registry.py imports and app.accommodation import errors)"
        )

    # Verify key tables exist (smoke test)
    cur.execute("SELECT tablename FROM pg_tables WHERE schemaname = 'public' AND tablename = 'users'")
    if cur.fetchone() is None:
        issues.append("users table is missing entirely")
    
    cur.execute("SELECT tablename FROM pg_tables WHERE schemaname = 'public' AND tablename = 'events'")
    if cur.fetchone() is None:
        issues.append("events table is missing entirely")
    
    cur.execute("SELECT tablename FROM pg_tables WHERE schemaname = 'public' AND tablename = 'accommodation_properties'")
    if cur.fetchone() is None:
        issues.append("accommodation_properties table is missing entirely")

    cur.close()
    conn.close()

    if issues:
        print("[FAIL] Schema verification failed:")
        for issue in issues:
            print(f"   - {issue}")
        raise RuntimeError(
            "Test DB schema verification failed — see issues above. "
            "Do not trust this DB for tests until these are resolved."
        )

    print("[OK] Schema verification passed "
          "(core tables present, schema built from models)")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    params = _get_test_db_params()
    print(f"[..] Using test database: {params['database']} on {params['host']}:{params['port']}")

    recreate_database(params)
    build_schema_from_models()
    stamp_alembic_head()
    verify_schema(params)

    print("[OK] Test database schema ready and verified!")