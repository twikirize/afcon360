from sqlalchemy import inspect

from app import create_app
from app.config import TestingConfig
from app.extensions import db


app = create_app(config_object=TestingConfig)
with app.app_context():
    inspector = inspect(db.engine)
    print("✅ PostgreSQL connection configured through SQLAlchemy")
    print(f"Database URL: {app.config['SQLALCHEMY_DATABASE_URI']}")
    print("\n--- Schemas ---")
    print(inspector.get_schema_names())
    print("\n--- Tables ---")
    print(inspector.get_table_names())
