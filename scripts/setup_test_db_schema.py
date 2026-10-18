"""
Provision the PostgreSQL *test* schema through the Design-2 model-bootstrap
path.

Design 2 (see docs/transport/fixes/B0-FROZEN-BASELINE-ENUM-INVENTORY-AND-PLAN.md,
Addendum B):
  db.create_all() is a separately identified PostgreSQL model-bootstrap path.
  Its database is marked by the dedicated, non-Alembic table
  `afcon360_model_bootstrap` and is NEVER stamped Alembic `head`.
  H3/Alembic remains the authoritative installation and upgrade path.

Historical note: this script originally existed because the migration chain had
no usable baseline root (ab6dd422c152 created only 3 tables and ALTERed the
rest). B0 resolved that: `8a0deccce6f6_initial_full_schema_baseline.py` is a
real root migration that builds the whole schema from an empty database, so
`flask db upgrade` is now the supported migration path. The model-bootstrap
path below remains available as a *separate, explicitly marked* alternative;
the two must never be conflated.

What this script does:
  1. Drop & recreate the target database (destructive; operator-invoked only).
  2. Build the schema via app.core.model_bootstrap.bootstrap_model_schema():
       - refuses to proceed if any model domain failed to register,
       - pre-creates the 39 Group A enum types (create_type=False) from the
         reviewed inventory, refusing an incompatible existing type,
       - lets db.create_all() own the 8 Group B enum types and all tables,
       - writes the marker row as 'building' first and flips it to 'complete'
         only after validation, so a failed run never looks successful.
  3. Verify the result: marker complete with a matching fingerprint, all model
     tables and all 47 enum types present with exact labels, and
     alembic_version absent.

This is NOT the migration path. A database produced here cannot satisfy
migration-equivalence tests: tests/postgres_contract.py rejects it. Provision
a migration-built database with `flask db upgrade` against an empty database.

DO NOT reuse this for production.

Usage:
    python scripts/setup_test_db_schema.py
"""

import os
import sys
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
# 3. Build schema through the Design-2 model-bootstrap path
# ---------------------------------------------------------------------------
def build_schema_from_models():
    """
    Build the schema via app.core.model_bootstrap, deliberately — not as a
    silent fallback. Requires model_registry.py to import every domain's
    models so nothing is missing from db.metadata; the bootstrap path refuses
    to proceed if any domain failed to register.
    """
    from app import create_app
    from app.config import TestingConfig
    from app.core.model_bootstrap import bootstrap_model_schema
    from app.extensions import db
    from tests.postgres_contract import migration_heads

    app = create_app(config_object=TestingConfig)
    with app.app_context():
        registered_tables = sorted(db.metadata.tables.keys())
        print(f"[..] {len(registered_tables)} tables registered on db.metadata")

        result = bootstrap_model_schema(db, migration_heads())
        print(
            "[OK] Model-bootstrap schema provisioned "
            f"(state={result.state_code}, tables={result.tables}, "
            f"group A={result.group_a_types}, group B={result.group_b_types}, "
            f"alembic stamped={result.stamped_alembic})"
        )
        print(f"[OK] Marker fingerprint: {result.fingerprint}")


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
    Check the facts this path is responsible for:
      - the model-bootstrap marker is present and complete
      - alembic_version is ABSENT (a model-bootstrap DB is never stamped head)
      - core and accommodation tables exist
    Raises with a clear message if anything is wrong, instead of printing
    "[OK]" over an incomplete schema.
    """
    from app.core.model_bootstrap import MARKER_TABLE, MARKER_KEY

    conn = _pg_connect(params)
    cur = conn.cursor()
    issues = []

    cur.execute(
        "SELECT status FROM " + MARKER_TABLE + " WHERE marker = %s",
        (MARKER_KEY,),
    )
    marker_row = cur.fetchone()
    if marker_row is None:
        issues.append(
            "model-bootstrap marker row is missing — the bootstrap did not "
            "complete"
        )
    elif marker_row[0] != "complete":
        issues.append(
            f"model-bootstrap marker status is '{marker_row[0]}', not "
            "'complete' — the bootstrap did not finish"
        )

    cur.execute(
        "SELECT tablename FROM pg_tables WHERE schemaname = 'public' "
        "AND tablename = 'alembic_version'"
    )
    if cur.fetchone() is not None:
        issues.append(
            "alembic_version exists; a model-bootstrap database must never "
            "be stamped as an Alembic database"
        )

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
          "(marker complete, no alembic_version, core tables present)")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    params = _get_test_db_params()
    print(f"[..] Using test database: {params['database']} on {params['host']}:{params['port']}")

    recreate_database(params)
    build_schema_from_models()
    verify_schema(params)

    print("[OK] Model-bootstrap test database provisioned and verified!")
    print(
        "[NOTE] This database is model-bootstrap, NOT migration-built. It "
        "cannot satisfy migration-equivalence tests; provision a migration "
        "database with `flask db upgrade`."
    )