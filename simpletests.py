from app import create_app
from app.extensions import db
from app.accommodation.models.property import Property
from sqlalchemy import inspect

app = create_app()
with app.app_context():
    inspector = inspect(db.engine)
    columns = inspector.get_columns('accommodation_properties')
    existing_columns = [col['name'] for col in columns]
    print('Existing columns in accommodation_properties:')
    for col in sorted(existing_columns):
        print(f'  - {col}')

    ota_columns = [
        'host_response_rate', 'host_response_time_hours', 'last_booked_at',
        'total_bookings', 'views_last_24h', 'overall_rating', 'total_reviews', 'is_verified'
    ]

    print('\nOTA Trust Columns Status:')
    for col in ota_columns:
        status = '✅ EXISTS' if col in existing_columns else '❌ MISSING'
        print(f'  - {col}: {status}')