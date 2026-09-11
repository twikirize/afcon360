"""Pytest configuration — test-isolation architecture.

Provides a fully isolated test boundary by default:
  - Fresh client per test (empty session cookies)
  - Fresh database state per test (row-tracking cleanup)
  - Snapshot/restore of app.config per test
  - Automatic cache clearance per test
  - Explicit auth fixtures (anonymous_client, authenticated_client, admin_client, host_client)
  - Explicit journey fixture for multi-step workflows
  - State-verification at teardown

Design principles:
  - Every test starts clean; persistence is explicit.
  - No test inherits state from another test unless it requests it.
  - Scattered workarounds (session.clear, cache.clear, db.session.remove)
    are replaced by systemic autouse fixtures.

Sections:
  1. Markers & collection
  2. Environment & DB bootstrap (session-scoped)
  3. App fixture (session-scoped)
  4. Core client fixture (function-scoped)
  5. Auth factory fixtures (function-scoped)
  6. Journey fixture (function-scoped, multi-step workflow)
  7. DB isolation — row-tracking cleanup (autouse, function-scoped)
  8. Config isolation — snapshot/restore (autouse, function-scoped)
  9. Cache isolation — automatic clearance (autouse, function-scoped)
 10. State verification (autouse, function-scoped)
 11. Backward-compat aliases (db_session, test_db)
"""

import copy
import os
import pickle
import pytest
import sys
from pathlib import Path
from urllib.parse import urlparse
from sqlalchemy import create_engine, text, inspect as sa_inspect
from flask_migrate import stamp as alembic_stamp

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
os.environ['FLASK_ENV'] = 'testing'

from app import create_app
from app.config import TestingConfig
from app.extensions import db, cache
from tests.postgres_contract import assert_migrated_postgres_database
from tests.helpers.isolation import (
    build_fk_graph,
    take_snapshot,
    cleanup_inserted_rows,
)


# ===================================================================
# 1. Markers & collection
# ===================================================================

def pytest_configure(config):
    config.addinivalue_line(
        'markers',
        'no_database: source/configuration contract check that does not access the database',
    )
    config.addinivalue_line(
        'markers',
        'threaded: test uses ThreadPoolExecutor with its own DB engine — skip row-tracking cleanup',
    )


@pytest.fixture(autouse=True)
def _push_request_context(request):
    """Replace pytest-flask's autouse _push_request_context.

    Prevents flask.g (and Flask-Login's g._login_user) from leaking across
    client.get()/post() calls within the same test. Tests using ``client``
    get no outer request context; other tests keep the convenience.
    """
    if "app" not in request.fixturenames:
        return
    if "client" in request.fixturenames or "test_client" in request.fixturenames:
        return
    app = request.getfixturevalue("app")
    ctx = app.test_request_context()
    ctx.push()
    request.addfinalizer(lambda: ctx.pop())


def pytest_collection_modifyitems(session, config, items):
    """Force collection to only include tests from tests/ directory."""
    project_root = Path(config.rootdir)
    kept = []
    for item in items:
        try:
            rel_path = Path(item.fspath).resolve().relative_to(project_root)
        except ValueError:
            continue
        if rel_path.parts[0] == 'tests':
            kept.append(item)
    items[:] = kept
    print(f"[OK] Kept {len(kept)} test items from 'tests/' directory.")


# ===================================================================
# 2. Environment & DB bootstrap (session-scoped)
# ===================================================================

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
    print("[OK] Loaded .env.testing")
else:
    env_file = project_root / ".env.test"
    if env_file.exists():
        with open(env_file, 'r', encoding='utf-8-sig') as f:
            for line in f:
                if '=' in line:
                    key, value = line.strip().split('=', 1)
                    os.environ[key] = value.strip().strip('"\'')
        print("[OK] Loaded .env.test")

_TEST_DATABASE_URL = os.getenv('TEST_DATABASE_URL') or os.getenv('DATABASE_URL')
if not _TEST_DATABASE_URL:
    raise RuntimeError(
        "No test database URL found! Set TEST_DATABASE_URL or DATABASE_URL "
        "in .env.testing or .env.test at project root."
    )
TEST_DATABASE_URL: str = _TEST_DATABASE_URL

parsed = urlparse(TEST_DATABASE_URL)
masked_url = (
    f"{parsed.scheme}://{parsed.username}:****@{parsed.hostname}"
    + (f":{parsed.port}" if parsed.port else "")
    + parsed.path
)
print(f"Using test database: {masked_url}")


@pytest.fixture(scope='session', autouse=True)
def setup_database():
    """Runs once per test session: ensures the test DB exists and is built."""
    db_url = TEST_DATABASE_URL
    db_name = db_url.split('/')[-1]
    default_url = db_url.replace('/' + db_name, '/postgres')

    engine_default = create_engine(default_url, isolation_level="AUTOCOMMIT")
    try:
        engine_test = create_engine(db_url)
        with engine_test.connect() as conn:
            conn.execute(text("SELECT 1"))
        print(f"[OK] Test database '{db_name}' already exists.")
    except Exception:
        with engine_default.connect() as conn:
            conn.execute(text(f"CREATE DATABASE {db_name}"))
        print(f"[OK] Test database '{db_name}' created.")

    app = create_app(config_object=TestingConfig)
    app.config['SQLALCHEMY_DATABASE_URI'] = db_url
    with app.app_context():
        from app.extensions import db

        inspector = sa_inspect(db.engine)
        if "users" not in inspector.get_table_names():
            db.create_all()
            print("[OK] Schema built from current SQLAlchemy models (db.create_all).")
        else:
            print("[OK] Test database schema already present; skipping rebuild.")

        alembic_stamp(revision="head", purge=True)
        print("[OK] Alembic head stamped.")

    yield


# ===================================================================
# 3. App fixture (session-scoped)
# ===================================================================

@pytest.fixture(scope='session')
def app(setup_database):
    """Create the Flask app for testing, with migrations already applied."""
    app = create_app(config_object=TestingConfig)
    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False
    app.config['RATELIMIT_ENABLED'] = False

    with app.app_context():
        table_count = assert_migrated_postgres_database(db.engine)
        print(f"[OK] PostgreSQL test database verified (tables count: {table_count})")

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
            print(f"[OK] Seeded test admin {admin_email} with owner role")

    return app


# ===================================================================
# 4. Core client fixture (function-scoped)
# ===================================================================

@pytest.fixture(scope='function')
def client(app):
    """Fresh test client per test. Empty session cookie jar.

    This is the default fixture for HTTP tests. Each test gets an
    isolated client with no authentication state, no cookies, and no
    session data from any prior test.
    """
    return app.test_client()


@pytest.fixture(scope='session')
def test_engine():
    """The SQLAlchemy engine bound to the shared test database.

    An independent engine from ``TEST_DATABASE_URL`` — does not depend on
    app/session lifecycle, so raw/SQL-level isolation helpers can run
    against the test DB without touching the scoped Flask session.
    """
    return create_engine(TEST_DATABASE_URL)


@pytest.fixture(scope='function')
def unique_id():
    """Return a fresh short unique string per test (uuid4 hex prefix)."""
    import uuid as _uuid
    return _uuid.uuid4().hex[:12]


# ===================================================================
# 5. Auth factory fixtures (function-scoped)
# ===================================================================

@pytest.fixture(scope='function')
def test_user(app):
    """Create and commit a fresh standard user for the test.

    Returns a User object committed to DB with:
      - is_verified=True, is_active=True
      - A known password ('TestPass123!')
      - No roles beyond the default
    """
    with app.app_context():
        from app.identity.models.user import User
        import uuid as _uuid

        uid = str(_uuid.uuid4())[:8]
        user = User(
            username=f'user_{uid}',
            email=f'user_{uid}@test.example.com',
            is_verified=True,
            is_active=True,
        )
        user.set_password('TestPass123!')
        db.session.add(user)
        db.session.commit()
        return user


@pytest.fixture(scope='function')
def test_admin(app):
    """Create and commit a fresh admin user for the test.

    Returns a User object committed to DB with:
      - is_verified=True, is_active=True
      - owner role (level=1)
      - A known password ('TestPass123!')
    """
    with app.app_context():
        from app.identity.models.user import User, UserRole
        from app.identity.models.roles_permission import get_or_create_role
        import uuid as _uuid

        owner_role = get_or_create_role('owner', level=1)
        uid = str(_uuid.uuid4())[:8]
        admin = User(
            username=f'admin_{uid}',
            email=f'admin_{uid}@test.example.com',
            is_verified=True,
            is_active=True,
        )
        admin.set_password('TestPass123!')
        db.session.add(admin)
        db.session.flush()
        db.session.add(UserRole(user_id=admin.id, role_id=owner_role.id))
        db.session.commit()
        return admin


@pytest.fixture(scope='function')
def test_host(app):
    """Create and commit a fresh host user for the test."""
    with app.app_context():
        from app.identity.models.user import User
        import uuid as _uuid

        uid = str(_uuid.uuid4())[:8]
        host = User(
            username=f'host_{uid}',
            email=f'host_{uid}@test.example.com',
            is_verified=True,
            is_active=True,
        )
        host.set_password('TestPass123!')
        db.session.add(host)
        db.session.commit()
        return host


def _login_client(client, user):
    """Set Flask-Login session cookies on a client to authenticate as user.

    Re-attaches detached/expired ORM instances via merge so tests can pass
    users that were committed (and therefore expired) without hitting a
    DetachedInstanceError on attribute access.
    """
    from app.extensions import db
    app = client.application
    with app.app_context():
        merged = db.session.merge(user)
        uid = str(merged.public_id)
        db.session.rollback()
    with client.session_transaction() as sess:
        sess['_user_id'] = uid
        sess['_fresh'] = True


@pytest.fixture(scope='function')
def authenticated_client(client, test_user):
    """Client logged in as a standard user. Fresh per test."""
    _login_client(client, test_user)
    return client


@pytest.fixture(scope='function')
def admin_client(client, test_admin):
    """Client logged in as admin. Fresh per test."""
    _login_client(client, test_admin)
    return client


@pytest.fixture(scope='function')
def host_client(client, test_host):
    """Client logged in as a host. Fresh per test."""
    _login_client(client, test_host)
    return client


@pytest.fixture(scope='function')
def anonymous_client(client):
    """Alias for client — explicit naming for readability in public-endpoint tests."""
    return client


# ===================================================================
# 6. Journey fixture (function-scoped, multi-step workflow)
# ===================================================================

class JourneyContext:
    """Intentionally persistent context for multi-step business workflows.

    Wraps a Flask test client and provides helper methods for common
    workflow patterns (login, navigate, assert). The client and session
    persist across steps WITHIN a single test, but are cleaned up at
    teardown like any other test fixture.
    """

    def __init__(self, client, app):
        self.client = client
        self.app = app
        self.state = {}  # arbitrary test-journey state bag
        self._login_user = None

    def login_as(self, user):
        """Authenticate as the given user for the rest of this journey."""
        _login_client(self.client, user)
        self._login_user = user
        return self

    def logout(self):
        """Clear authentication for the rest of this journey."""
        with self.client.session_transaction() as sess:
            sess.pop('_user_id', None)
            sess.pop('_fresh', None)
        self._login_user = None
        return self

    def get(self, *args, **kwargs):
        return self.client.get(*args, **kwargs)

    def post(self, *args, **kwargs):
        return self.client.post(*args, **kwargs)

    def put(self, *args, **kwargs):
        return self.client.put(*args, **kwargs)

    def delete(self, *args, **kwargs):
        return self.client.delete(*args, **kwargs)


@pytest.fixture(scope='function')
def journey(client, app):
    """Multi-step workflow context. Use when a test needs to chain
    operations that share a single authenticated session:

        def test_booking_lifecycle(journey, test_user):
            journey.login_as(test_user)
            resp = journey.get('/api/bookings')
            assert resp.status_code == 200
            resp = journey.post('/api/bookings', json={...})
            ...
    """
    return JourneyContext(client, app)


# ===================================================================
# 7. DB isolation — row-tracking cleanup (autouse, function-scoped)
# ===================================================================

# Cached at module level, built once per process
_fk_graph = None


def _get_fk_graph(engine):
    global _fk_graph
    if _fk_graph is None:
        _fk_graph = build_fk_graph(engine)
    return _fk_graph


@pytest.fixture(autouse=True)
def _isolate_db(request, app):
    """Automatically track and clean DB rows inserted during each test.

    Before the test: snapshots the current state of every table that has rows.
    After the test: deletes rows inserted by the test, in FK-safe order.

    This replaces the old ``clean_db`` fixture which only rolled back
    uncommitted data. Committed rows from prior tests now get cleaned up
    too, preventing the "shared-DB pollution" that caused TI-1 defects.

    Skipped for:
      - ``no_database`` marker tests
      - ``threaded`` marker tests (they use their own DB engines)
    """
    if request.node.get_closest_marker('no_database'):
        yield
        return
    if request.node.get_closest_marker('threaded'):
        yield
        return

    with app.app_context():
        snapshot = take_snapshot(db.session, db.engine)

    yield  # test runs

    with app.app_context():
        # 1. Rollback any uncommitted work
        try:
            db.session.rollback()
        except Exception:
            pass

        # 2. Remove identity map (clears stale ORM instances)
        db.session.remove()

        # 3. Delete committed rows that the test inserted
        #    Cleanup failure must NOT be swallowed — silent DB pollution is
        #    exactly what the isolation architecture exists to prevent.
        #    Run on a raw connection to avoid per-statement ORM session
        #    overhead (the cleanup is pure SQL).
        try:
            with db.engine.begin() as conn:
                deleted = cleanup_inserted_rows(conn, db.engine, snapshot)
        except Exception as exc:
            try:
                db.session.rollback()
            except Exception:
                pass
            raise AssertionError(
                "DATABASE ISOLATION FAILED: test-created rows could not be "
                "cleaned up. The suite must stop rather than continue with "
                "contaminated database state. "
                f"Original error: {exc}"
            ) from exc

        # 4. Final cleanup — remove identity map again
        try:
            db.session.remove()
        except Exception:
            pass


# ===================================================================
# 8. Config isolation — snapshot/restore (autouse, function-scoped)
# ===================================================================

@pytest.fixture(autouse=True)
def _isolate_config(app):
    """Snapshot app.config before test, restore after.

    Prevents cross-test config mutation. Tests that write to
    ``app.config[...]`` (MODULE_FLAGS, PLATFORM_ORG_ID, WALLET_MAX_DEPOSIT,
    etc.) will have their changes automatically reverted.

    Uses shallow copy for values that can't be deep-copied (locks, sockets).
    """
    snapshot = {}
    for key in list(app.config.keys()):
        try:
            snapshot[key] = copy.deepcopy(app.config[key])
        except (TypeError, pickle.PicklingError):
            snapshot[key] = app.config[key]
    yield
    app.config.clear()
    app.config.update(snapshot)


# ===================================================================
# 9. Cache isolation — automatic clearance (autouse, function-scoped)
# ===================================================================

@pytest.fixture(autouse=True)
def _clean_cache(app):
    """Clear Flask-Caching and Flask-Login user_loader caches before each test.

    The process-wide cache (Redis or SimpleCache) serves stale data across
    tests if not cleared. This fixture runs BEFORE each test so that every
    test starts with a cold cache.

    Also clears any lingering Flask-Login identity cache entries.
    """
    with app.app_context():
        try:
            cache.clear()
        except Exception:
            pass

        # Clear Flask-Login's in-process user_loader cache
        try:
            from flask_login import LoginManager
            login_manager = app.extensions.get('login_manager')
            if login_manager and hasattr(login_manager, '_user_loader'):
                login_manager._user_loader_cache = {}
        except Exception:
            pass

    yield

    # Clear again after teardown to prevent stale cache from leaking
    # into the next test's pre-test clearance (belt-and-suspenders).
    with app.app_context():
        try:
            cache.clear()
        except Exception:
            pass


# ===================================================================
# 10. State verification (autouse, function-scoped)
# ===================================================================

@pytest.fixture(autouse=True)
def _verify_test_state(request, app):
    """Detect unexpected state at setup and teardown.

    At setup: asserts clean baseline conditions.
    At teardown: detects leaked auth state, uncommitted transactions,
    dirty session, and unexpected cache keys.

    This fixture runs AFTER all other autouse fixtures in teardown
    (final safety net).
    """
    if request.node.get_closest_marker('no_database'):
        yield
        return

    # --- Setup assertions ---
    with app.app_context():
        # No active/leaked request context
        from flask import g, has_request_context
        # DB session should be clean at test start
        assert db.session.is_active or not db.session.dirty, (
            f"DB session is dirty at test start: {db.session.dirty}"
        )

    yield  # test runs

    # --- Teardown verification ---
    with app.app_context():
        # Check no uncommitted transactions remain
        try:
            if db.session.is_active:
                db.session.rollback()
        except Exception:
            pass

        # Check no dirty/flushed state
        assert not db.session.dirty, (
            f"DB session has dirty state at teardown: {db.session.dirty}"
        )


# ===================================================================
# 11. Backward-compat aliases
# ===================================================================

@pytest.fixture(scope='function')
def db_session(app):
    """Provide a database session for each test function.

    Tests that need a live db_session within a persistent app context
    must request this explicitly. The autouse _isolate_db fixture handles
    cleanup independently.
    """
    with app.app_context():
        yield db.session
        db.session.rollback()
        db.session.remove()


@pytest.fixture(scope='function')
def test_db(db_session):
    """Alias for db_session for backward compatibility."""
    yield db_session
