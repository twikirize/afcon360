"""
Pytest configuration - asserts the dedicated PostgreSQL test database is
already prepared by the reviewed Alembic migration workflow.
"""
import pytest
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
os.environ['FLASK_ENV'] = 'testing'

from app.config import TestingConfig
from tests.postgres_contract import assert_migrated_postgres_database

def pytest_configure(config):
    """Keep pytest configuration intentionally database-contract focused."""
    config.addinivalue_line(
        'markers',
        'no_database: source/configuration contract check that does not access the database',
    )

@pytest.fixture(scope='session')
def app():
    """Create the application against the migrated PostgreSQL test database."""
    from app import create_app

    app = create_app(config_object=TestingConfig)
    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False
    app.config['RATELIMIT_ENABLED'] = False

    with app.app_context():
        from app.extensions import db

        table_count = assert_migrated_postgres_database(db.engine)
        print(f"PostgreSQL test database ready with {table_count} tables")

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
            print(f"Seeded test admin {admin_email} with owner role")

        yield app

@pytest.fixture(scope='session')
def client(app):
    return app.test_client()

@pytest.fixture(scope='session')
def db_session(app):
    from app.extensions import db
    with app.app_context():
        yield db.session
        db.session.remove()



@pytest.fixture(scope='session')
def test_db(db_session):
    """Alias for db_session for backward compatibility with tests using test_db"""
    yield db_session

@pytest.fixture(autouse=True)
def clean_db(request):
    if request.node.get_closest_marker('no_database'):
        yield
        return
    db_session = request.getfixturevalue('db_session')
    yield
    db_session.rollback()
