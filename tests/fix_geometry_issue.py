# check_postgis.py
from app import create_app
from app.config import TestingConfig


app = create_app(config_object=TestingConfig)
with app.app_context():
    print(f"Database dialect: {app.extensions['sqlalchemy'].engine.dialect.name}")
    print(
        'PostGIS extension management is an operator/migration concern; '
        'this diagnostic does not execute extension SQL.'
    )
