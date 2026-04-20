# Create a new init_settings.py that doesn't rely on initialize_defaults

#!/usr/bin/env python3
"""Initialize default system settings for AFCON360"""
import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

def init_system_settings():
    try:
        from app import create_app
        from app.extensions import db
        from app.admin.owner.models import SystemSetting

        app = create_app()
        with app.app_context():
            print("Initializing system settings...")

            # Check if table exists
            from sqlalchemy import inspect
            inspector = inspect(db.engine)
            if 'system_settings' not in inspector.get_table_names():
                print("ERROR: system_settings table doesn't exist. Run migrations first.")
                return False

            # Default settings to create
            defaults = [
                ('EMERGENCY_LOCKDOWN', False, 'bool', 'security', 'Emergency lockdown mode'),
                ('MAINTENANCE_MODE', False, 'bool', 'security', 'Maintenance mode'),
                ('ENABLE_WALLET', True, 'bool', 'feature', 'Enable wallet module'),
                ('PAYMENT_PROCESSING_ENABLED', False, 'bool', 'feature', 'Enable payment processing'),
                ('RATE_LIMIT_ENABLED', True, 'bool', 'security', 'Enable rate limiting'),
                ('WALLET_DAILY_LIMIT_HOME', 10000, 'int', 'wallet', 'Daily wallet limit USD'),
                ('WALLET_DAILY_LIMIT_LOCAL', 37000000, 'int', 'wallet', 'Daily wallet limit UGX'),
            ]

            created = 0
            for key, value, value_type, category, description in defaults:
                existing = SystemSetting.query.filter_by(key=key).first()
                if not existing:
                    SystemSetting.set(
                        key=key,
                        value=value,
                        value_type=value_type,
                        category=category,
                        description=description
                    )
                    created += 1
                    print(f"  Created: {key} = {value}")

            db.session.commit()
            print(f"SUCCESS: {created} settings created")
            return True

    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == '__main__':
    success = init_system_settings()
    sys.exit(0 if success else 1)
