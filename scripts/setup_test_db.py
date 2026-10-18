"""
Set up the test database schema through the Design-2 model-bootstrap path.

This is a stale near-duplicate of scripts/setup_test_db_schema.py (see that
script's docstring for the full Design-2 rationale). It is kept in sync so no
path here can produce the old false behaviour of stamping Alembic `head` on a
schema that was built from models rather than from migrations.

This script:
  1. Drops & recreates the test database.
  2. Builds the schema via app.core.model_bootstrap (marker written, Group A
     enum types pre-created, db.create_all() owns Group B types and tables).
  3. Verifies the marker; it NEVER stamps Alembic head.

Usage:
    python scripts/setup_test_db.py
"""

import os
import sys
import psycopg2
from pathlib import Path

# ---------------------------------------------------------------------------
# 1. Read connection info from the application's TestingConfig
# ---------------------------------------------------------------------------
def _get_test_db_params():
    """Build connection parameters from TestingConfig."""
    # Force the testing environment before importing the app
    os.environ["APP_ENV"] = "testing"
    os.environ["FLASK_ENV"] = "testing"          # belt-and-suspenders
    from app.config import TestingConfig
    cfg = TestingConfig()

    # Parse the SQLAlchemy URI (we expect a postgresql:// URI)
    uri = cfg.SQLALCHEMY_DATABASE_URI
    if not uri:
        raise RuntimeError("TestingConfig has no SQLALCHEMY_DATABASE_URI")

    # Simple parser for postgresql://user:pass@host:port/dbname
    prefix = "postgresql://"
    if not uri.startswith(prefix):
        raise RuntimeError(f"Unsupported database URI: {uri}")
    rest = uri[len(prefix):]
    # Split off the database name
    if "/" not in rest:
        raise RuntimeError(f"No database name in URI: {uri}")
    auth_host, dbname = rest.rsplit("/", 1)
    # Split auth_host into user:pass@host:port
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

# ---------------------------------------------------------------------------
# 2. Drop & recreate the test database
# ---------------------------------------------------------------------------
def recreate_database(params):
    """Drop the test database (if it exists) and create a fresh one."""
    conn = psycopg2.connect(
        host=params["host"],
        port=params["port"],
        user=params["user"],
        password=params["password"],
        dbname=params["maintenance_db"],
    )
    conn.autocommit = True
    cur = conn.cursor()

    dbname = params["database"]
    # Drop
    cur.execute(f"SELECT pg_terminate_backend(pg_stat_activity.pid) "
                f"FROM pg_stat_activity "
                f"WHERE pg_stat_activity.datname = '{dbname}' "
                f"AND pid <> pg_backend_pid();")
    cur.execute(f"DROP DATABASE IF EXISTS {dbname}")
    print(f"[OK] Dropped database {dbname}")

    # Create
    cur.execute(f"CREATE DATABASE {dbname}")
    print(f"[OK] Created database {dbname}")
    cur.close()
    conn.close()

# ---------------------------------------------------------------------------
# 3. Create all tables using the Design-2 model-bootstrap path
# ---------------------------------------------------------------------------
def create_tables(params):
    """Build the schema via app.core.model_bootstrap (never stamped head)."""
    os.environ["APP_ENV"] = "testing"
    os.environ["FLASK_ENV"] = "testing"
    from app import create_app
    from app.config import TestingConfig
    from app.core.model_bootstrap import bootstrap_model_schema
    from app.extensions import db
    from tests.postgres_contract import migration_heads

    app = create_app(config_object=TestingConfig)
    with app.app_context():
        result = bootstrap_model_schema(db, migration_heads())
        print(
            "[OK] Model-bootstrap schema provisioned "
            f"(tables={result.tables}, group A={result.group_a_types}, "
            f"group B={result.group_b_types})"
        )
        print(
            "[NOTE] This database is model-bootstrap, NOT migration-built, "
            "and was never stamped Alembic head."
        )

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    params = _get_test_db_params()
    print(f"[..] Using test database: {params['database']} on {params['host']}:{params['port']}")
    recreate_database(params)
    create_tables(params)
    print("[OK] Test database schema ready!")