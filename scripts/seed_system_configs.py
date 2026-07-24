#!/usr/bin/env python
"""
Seed default system configuration values
Run: python scripts/seed_system_configs.py
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app import create_app
from app.extensions import db
from sqlalchemy import text

def seed_configs():
    app = create_app()
    with app.app_context():
        defaults = [
            ('accommodation_module_enabled', 'true', 'Enable accommodation module'),
            ('accommodation_max_photos', '10', 'Maximum photos per property'),
            ('accommodation_commission_rate', '10.0', 'Platform commission percentage'),
            ('accommodation_booking_hold_minutes', '15', 'Minutes to hold booking without payment'),
            ('accommodation_max_guests', '10', 'Maximum guests per property'),
            ('accommodation_enable_instant_book', 'false', 'Enable instant booking by default'),
            ('accommodation_default_cancellation_policy', 'moderate', 'Default cancellation policy'),
            ('accommodation_require_guest_verification', 'true', 'Require guest verification before booking'),
            ('accommodation_max_bookings_per_user', '5', 'Maximum active bookings per user'),
        ]

        for key, value, description in defaults:
            db.session.execute(text("""
                INSERT INTO system_configs (key, value, description)
                VALUES (:key, :value, :description)
                ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
            """), {'key': key, 'value': value, 'description': description})

        db.session.commit()
        print(f"Seeded {len(defaults)} configuration values")

if __name__ == "__main__":
    seed_configs()
