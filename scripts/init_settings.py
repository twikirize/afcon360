#!/usr/bin/env python3
"""
Initialize default system settings for AFCON360
Run this after database migrations to populate system_settings table
"""
import os
import sys
import traceback

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

def init_system_settings():
    """Initialize default system settings"""
    try:
        from app import create_app
        from app.extensions import db
        from app.admin.owner.models import SystemSetting

        app = create_app()

        with app.app_context():
            print("Initializing system settings...")

            # Check if SystemSetting table exists
            from sqlalchemy import inspect
            inspector = inspect(db.engine)

            if 'system_settings' not in inspector.get_table_names():
                print("Creating system_settings table...")
                # Create the table for SystemSetting model only
                SystemSetting.__table__.create(bind=db.engine)
                print("Table created successfully.")

            # Initialize defaults
            SystemSetting.initialize_defaults()

            # Verify
            count = SystemSetting.query.count()
            print(f"SUCCESS: System settings initialized: {count} settings created")

            # Show some key settings
            key_settings = SystemSetting.query.filter(
                SystemSetting.key.in_([
                    'EMERGENCY_LOCKDOWN',
                    'MAINTENANCE_MODE',
                    'ENABLE_WALLET',
                    'PAYMENT_PROCESSING_ENABLED'
                ])
            ).all()

            print("\nKey settings:")
            for setting in key_settings:
                print(f"  - {setting.key}: {setting.value} ({setting.value_type})")

            return True

    except ImportError as e:
        print(f"ERROR: Import error: {e}")
        print("Make sure you're running from the project root directory")
        return False
    except Exception as e:
        print(f"ERROR: Error initializing settings: {e}")
        traceback.print_exc()
        return False

if __name__ == '__main__':
    success = init_system_settings()
    sys.exit(0 if success else 1)
