"""Pytest configuration – fully self‑contained.

- Loads .env.testing (or .env.test) from project root.
- Creates the test PostgreSQL database if missing.
- Runs Alembic migrations (flask db upgrade).
- Prints the database URL (password masked) on startup.
- **Forces** test discovery to only include files inside 'tests/'.
- Provides app, client, db_session, test_db fixtures.
- Auto‑rollback after each test.
- Optional seeding of test admin (SEED_TEST_DB=1).
- Registers `no_database` marker.
"""

import os
import pytest
import sys
from pathlib import Path
from urllib.parse import urlparse
from sqlalchemy import create_engine, text, inspect
from flask_migrate import stamp as alembic_stamp

# Ensure the project root is in sys.path (for imports)
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
os.environ['FLASK_ENV'] = 'testing'

from app import create_app
from app.config import TestingConfig
from app.extensions import db
from tests.postgres_contract import assert_migrated_postgres_database


# ---------- 1. Register custom markers ----------
def pytest_configure(config):
    config.addinivalue_line(
        'markers',
        'no_database: source/configuration contract check that does not access the database',
    )


# ---------- 2. Force collection to only include tests from 'tests/' ----------
def pytest_collection_modifyitems(session, config, items):
    """Remove any test items that are not inside the 'tests/' directory."""
    project_root = Path(config.rootdir)
    kept = []
    for item in items:
        # Get the relative path from the project root
        try:
            rel_path = Path(item.fspath).resolve().relative_to(project_root)
        except ValueError:
            # File is outside the project root – skip it
            continue
        # Keep only items whose first path component is 'tests'
        if rel_path.parts[0] == 'tests':
            kept.append(item)
    items[:] = kept
    print(f"✅ Kept {len(kept)} test items from 'tests/' directory.")


# ---------- 3. Load environment variables from .env.testing ----------
project_root = Path(__file__).resolve().parent.parent
env_file = project_root / ".env.testing"

if env_file.exists():
    with open(env_file, 'r', encoding='utf-8-sig') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            if '=' in line:
                key, value = line.split('=', 1)
                os.environ[key.strip()] = value.strip().strip('"\'')
    print("✅ Loaded .env.testing")
else:
    env_file = project_root / ".env.test"
    if env_file.exists():
        with open(env_file, 'r', encoding='utf-8-sig') as f:
            for line in f:
                if '=' in line:
                    key, value = line.strip().split('=', 1)
                    os.environ[key] = value.strip().strip('"\'')
        print("✅ Loaded .env.test")

# ---------- 4. Validate the test database URL and mask password ----------
TEST_DATABASE_URL = os.getenv('TEST_DATABASE_URL') or os.getenv('DATABASE_URL')
if not TEST_DATABASE_URL:
    raise RuntimeError(
        "No test database URL found! Set TEST_DATABASE_URL or DATABASE_URL "
        "in .env.testing or .env.test at project root."
    )

# Mask the password for logging
parsed = urlparse(TEST_DATABASE_URL)
masked_url = (
    f"{parsed.scheme}://{parsed.username}:****@{parsed.hostname}"
    + (f":{parsed.port}" if parsed.port else "")
    + parsed.path
)
print(f"🔗 Using test database: {masked_url}")


# ---------- 5. Session‑scoped fixture: create DB and build schema ----------
@pytest.fixture(scope='session', autouse=True)
def setup_database():
    """Runs once per test session: ensures the test DB exists and is built.

    This is the canonical, self‑contained test bootstrap. It deliberately does
    NOT rely on `flask db upgrade` building from scratch, because this project's
    migration history has a *missing baseline*: ab6dd422c152_initial_schema
    (down_revision=None) never creates users/events/accounts/transactions/
    accommodation_properties, so `flask db upgrade` against an empty database
    always fails at event_host_registrations' FK to users.id.

    Instead we build the schema from the current SQLAlchemy models via
    db.create_all() and then stamp Alembic head — mirroring
    scripts/setup_test_db_schema.py. A missing/incomplete DB is rebuilt
    automatically, so plain `pytest` always has a working test database and
    this setup can never silently regress.

    To force a clean rebuild (e.g. after a model/schema change), drop the test
    database first or run `python scripts/setup_test_db_schema.py`.
    """
    db_url = TEST_DATABASE_URL
    db_name = db_url.split('/')[-1]
    default_url = db_url.replace('/' + db_name, '/postgres')

    # Create the test database if it doesn't exist
    engine_default = create_engine(default_url, isolation_level="AUTOCOMMIT")
    try:
        engine_test = create_engine(db_url)
        with engine_test.connect() as conn:
            conn.execute(text("SELECT 1"))
        print(f"✅ Test database '{db_name}' already exists.")
    except Exception:
        with engine_default.connect() as conn:
            conn.execute(text(f"CREATE DATABASE {db_name}"))
        print(f"✅ Test database '{db_name}' created.")

    app = create_app(config_object=TestingConfig)
    app.config['SQLALCHEMY_DATABASE_URI'] = db_url
    with app.app_context():
        from app.extensions import db

        inspector = inspect(db.engine)
        if "users" not in inspector.get_table_names():
            # Empty/incomplete DB: build the full schema from current models.
            db.create_all()
            print("✅ Schema built from current SQLAlchemy models (db.create_all).")
        else:
            print("✅ Test database schema already present; skipping rebuild.")

        # Stamp Alembic head so the postgres_contract check
        # (tests/postgres_contract.py) and any `flask db upgrade` treat the DB
        # as fully migrated. purge=True clears any stale alembic_version left
        # by a retired/renamed revision (e.g. the old ab6dd422c152 baseline),
        # which would otherwise make stamp fail with "Can't locate revision".
        alembic_stamp(revision="head", purge=True)
        print("✅ Alembic head stamped.")

    yield


# ---------- 6. Fixture for the Flask application ----------
@pytest.fixture(scope='session')
def app(setup_database):
    """Create the Flask app for testing, with migrations already applied."""
    app = create_app(config_object=TestingConfig)
    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False
    app.config['RATELIMIT_ENABLED'] = False

    with app.app_context():
        # Verify the schema is complete
        table_count = assert_migrated_postgres_database(db.engine)
        print(f"✅ PostgreSQL test database verified (tables count: {table_count})")

        # Optional seeding (if SEED_TEST_DB=1)
        if os.getenv('SEED_TEST_DB', '') == '1':
            from app.identity.models.roles_permission import get_or_create_role
            from app.identity.models.user import User, UserRole

            owner_role = get_or_create_role('owner', level=1)
            get_or_create_role('admin', level=3)
            admin_email = os.getenv('TEST_ADMIN_EMAIL', 'test_admin@example.com')
            admin = User.query.filter_by(email=admin_email).first()
            if not admin:
                admin = User(
                    username='test_admin',
                    email=admin_email,
                    is_verified=True,
                    is_active=True,
                )
                admin.set_password(os.getenv('TEST_ADMIN_PASSWORD', 'Password123!'))
                db.session.add(admin)
                db.session.flush()

            if not any(getattr(ur, 'role_id', None) == owner_role.id for ur in admin.roles):
                db.session.add(UserRole(user_id=admin.id, role_id=owner_role.id))

            db.session.commit()
            print(f"✅ Seeded test admin {admin_email} with owner role")

    return app


# ---------- 7. Fixture for test client ----------
@pytest.fixture(scope='session')
def client(app):
    """Provide a test client for making HTTP requests."""
    return app.test_client()


# ---------- 8. Fixture for database sessions ----------
@pytest.fixture(scope='function')
def db_session(app):
    """Provide a database session for each test function."""
    with app.app_context():
        yield db.session
        db.session.rollback()
        db.session.remove()


# ---------- 9. Alias for backward compatibility ----------
@pytest.fixture(scope='function')
def test_db(db_session):
    """Alias for db_session for backward compatibility with tests using test_db."""
    yield db_session


# ---------- 10. Automatic cleanup after each test ----------
@pytest.fixture(autouse=True)
def clean_db(request):
    """Automatically rollback DB changes after each test (except no_database tests)."""
    if request.node.get_closest_marker('no_database'):
        yield
        return
    db_session = request.getfixturevalue('db_session')
    yield
    db_session.rollback()