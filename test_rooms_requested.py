def inspect_rooms_requested():
    """Inspect the booking column and row count using SQLAlchemy constructs."""
    import os

    os.environ['APP_ENV'] = 'testing'
    os.environ['FLASK_ENV'] = 'testing'

    from sqlalchemy import MetaData, Table, func, select

    from app import create_app
    from app.config import TestingConfig
    from app.extensions import db

    app = create_app(config_object=TestingConfig)
    with app.app_context():
        bookings = Table(
            'accommodation_bookings', MetaData(), autoload_with=db.engine
        )
        print('Has rooms_requested:', 'rooms_requested' in bookings.c)
        print('Booking count:', db.session.scalar(select(func.count()).select_from(bookings)))


if __name__ == '__main__':
    inspect_rooms_requested()
