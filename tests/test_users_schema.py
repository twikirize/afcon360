def inspect_users_schema():
    """Print users columns using SQLAlchemy inspection."""
    import os

    os.environ['APP_ENV'] = 'testing'
    os.environ['FLASK_ENV'] = 'testing'

    from sqlalchemy import inspect

    from app import create_app
    from app.config import TestingConfig
    from app.extensions import db

    app = create_app(config_object=TestingConfig)
    with app.app_context():
        for column in inspect(db.engine).get_columns('users'):
            print(column['name'], column['type'], column['nullable'])


if __name__ == '__main__':
    inspect_users_schema()
