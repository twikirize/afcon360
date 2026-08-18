def inspect_accommodation_schema():
    """Print selected accommodation schemas using SQLAlchemy inspection."""
    import os

    os.environ['APP_ENV'] = 'testing'
    os.environ['FLASK_ENV'] = 'testing'

    from sqlalchemy import inspect

    from app import create_app
    from app.config import TestingConfig
    from app.extensions import db

    tables = [
        'accommodation_room_types',
        'accommodation_bookings',
        'accommodation_inventory_blocks',
        'accommodation_properties',
        'accommodation_booking_policies',
    ]

    app = create_app(config_object=TestingConfig)
    with app.app_context():
        inspector = inspect(db.engine)
        for table in tables:
            cols = [column['name'] for column in inspector.get_columns(table)]
            print(f"\n{table}: {cols}")


if __name__ == '__main__':
    inspect_accommodation_schema()
