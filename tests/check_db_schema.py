from app import create_app
from app.config import TestingConfig
from app.extensions import db
from sqlalchemy import inspect

app = create_app(config_object=TestingConfig)
with app.app_context():
    print("=== ACTUAL DATABASE SCHEMA FOR events ===\n")
    for column in inspect(db.engine).get_columns('events'):
        print(f"{column['name']}: {column['type']}")
