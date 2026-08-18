from app import create_app
from app.config import TestingConfig
from app.extensions import db
from sqlalchemy import inspect

app = create_app(config_object=TestingConfig)
with app.app_context():
    print("=== CHECKING DATABASE SCHEMA ===\n")
    
    inspector = inspect(db.engine)
    event_columns = {
        column['name']: column for column in inspector.get_columns('events')
    }
    if 'status' in event_columns:
        print(f"events.status: type={event_columns['status']['type']}")

    enum_names = {enum['name'] for enum in inspector.get_enums()}
    print(f"eventstatus enum exists: {'eventstatus' in enum_names}")
    print(f"Alembic version table exists: {'alembic_version' in inspector.get_table_names()}")
    tables = [table for table in inspector.get_table_names() if 'event' in table]
    print(f"\nEvent-related tables: {tables}")
