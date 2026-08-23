"""Pytest configuration for AFCON360 tests.

This file provides:
- Automatic test database creation and migration (via Flask-Migrate).
- An `app` fixture that returns a configured Flask application.
- A `db_session` fixture for database interactions.
- Optional overrides for testing (CSRF disabled, rate limiting off).
"""

import os
import pytest
from sqlalchemy import create_engine, text
from flask_migrate import upgrade
from app import create_app
from app.config import TestingConfig
from app.extensions import db
from tests.postgres_contract import assert_migrated_postgres_database


@pytest.fixture(scope='session')
def app():
    """Create the Flask app and ensure the PostgreSQL test database is migrated."""
    # Build the app with testing configuration
    app = create_app(config_object=TestingConfig)
    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False
    app.config['RATELIMIT_ENABLED'] = False

    with app.app_context():
        db_url = app.config['SQLALCHEMY_DATABASE_URI']

        # --- Step 1: Create the test database if it doesn't exist ---
        db_name = db_url.split('/')[-1]
        # Connect to the default 'postgres' database to issue CREATE DATABASE
        default_url = db_url.replace('/' + db_name, '/postgres')
        engine_default = create_engine(default_url, isolation_level="AUTOCOMMIT")
        try:
            # Try connecting to the test DB
            engine_test = create_engine(db_url)
            with engine_test.connect() as conn:
                conn.execute(text("SELECT 1"))
        except Exception:
            # Test DB does not exist – create it
            with engine_default.connect() as conn:
                conn.execute(text(f"CREATE DATABASE {db_name}"))
            print(f"✅ Test database '{db_name}' created.")

        # --- Step 2: Apply all Alembic migrations ---
        # This is equivalent to running `flask db upgrade` from the command line.
        upgrade()
        print("✅ Migrations applied to test database.")

        # --- Step 3: Verify the migration completed successfully ---
        # This function checks that essential tables (alembic_version, users, etc.) exist.
        table_count = assert_migrated_postgres_database(db.engine)
        print(f"✅ PostgreSQL test database verified (tables count: {table_count})")

    return app


@pytest.fixture(scope='function')
def db_session(app):
    """Provide a database session for each test function.

    Rolls back any changes after the test to keep the database clean.
    """
    with app.app_context():
        yield db.session
        db.session.rollback()
        db.session.remove()


# Optional: If you have other fixtures that need the app or db, they can use these.