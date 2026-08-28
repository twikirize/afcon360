def inspect_policy_table():
    """Inspect the booking-policy table through SQLAlchemy reflection."""
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
        table_name = 'accommodation_booking_policies'
        table_names = inspector.get_table_names()
        print(f'{table_name} exists:', table_name in table_names)
        if table_name in table_names:
            print('Columns:', [column['name'] for column in inspector.get_columns(table_name)])


if __name__ == '__main__':
    inspect_policy_table()
