def inspect_accommodation_schemas():
    """Print accommodation columns using the migrated PostgreSQL test DB."""
    import os

    os.environ['APP_ENV'] = 'testing'
    os.environ['FLASK_ENV'] = 'testing'

    from sqlalchemy import inspect

    from app import create_app
    from app.config import TestingConfig
    from app.extensions import db

    tables = [
        'accommodation_properties',
        'accommodation_room_types',
        'accommodation_bookings',
        'accommodation_inventory_blocks',
    ]

    app = create_app(config_object=TestingConfig)
    with app.app_context():
        inspector = inspect(db.engine)
        for table in tables:
            cols = [column['name'] for column in inspector.get_columns(table)]
            print(f"\n{table} ({len(cols)} columns):")
            print(cols)


if __name__ == '__main__':
    inspect_accommodation_schemas()
