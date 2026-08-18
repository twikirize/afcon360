from app import create_app
from app.config import TestingConfig
from app.extensions import db
from sqlalchemy import inspect

app = create_app(config_object=TestingConfig)
with app.app_context():
    column = next(
        column for column in inspect(db.engine).get_columns('events')
        if column['name'] == 'status'
    )
    print(f"Database status type: {column['type']}")
    print(f"PostgreSQL enum types: {inspect(db.engine).get_enums()}")
