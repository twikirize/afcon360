"""Expose the PostgreSQL contract to legacy root-level test probes."""

import os
import pytest

os.environ['FLASK_ENV'] = 'testing'

from app import create_app
from app.config import TestingConfig
from app.extensions import db
from tests.postgres_contract import assert_migrated_postgres_database


@pytest.fixture(scope='session')
def db_session():
    app = create_app(config_object=TestingConfig)
    with app.app_context():
        assert_migrated_postgres_database(db.engine)
        yield db.session
        db.session.rollback()
        db.session.remove()