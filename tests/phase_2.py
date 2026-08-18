from sqlalchemy import inspect

from app import create_app
from app.config import TestingConfig
from app.extensions import db


app = create_app(config_object=TestingConfig)
with app.app_context():
    inspector = inspect(db.engine)
    print("✅ Connected through SQLAlchemy to the dedicated PostgreSQL database")
    print("\n--- Primary Keys ---")
    for table in inspector.get_table_names():
        primary_key = inspector.get_pk_constraint(table)
        if primary_key.get('constrained_columns'):
            print(table, primary_key['constrained_columns'])

    print("\n--- Foreign Keys ---")
    for table in inspector.get_table_names():
        for foreign_key in inspector.get_foreign_keys(table):
            print(table, foreign_key)

    print("\n--- Indexes ---")
    for table in inspector.get_table_names():
        for index in inspector.get_indexes(table):
            print(table, index)

    print("\nRole and privilege changes are intentionally not performed here. "
          "Use the reviewed deployment/database provisioning workflow.")
