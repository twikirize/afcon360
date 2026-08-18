def inspect_users_table():
    """Inspect the migrated users table without handwritten SQL."""
    import os

    os.environ['APP_ENV'] = 'testing'
    os.environ['FLASK_ENV'] = 'testing'

    from sqlalchemy import inspect

    from app import create_app
    from app.config import TestingConfig
    from app.extensions import db

    app = create_app(config_object=TestingConfig)
    with app.app_context():
        inspector = inspect(db.engine)
        table_names = inspector.get_table_names()
        print('Users table present:', 'users' in table_names)
        for column in inspector.get_columns('users'):
            if column['name'] == 'email_verified_at':
                print('Column info:', column)


if __name__ == '__main__':
    inspect_users_table()
