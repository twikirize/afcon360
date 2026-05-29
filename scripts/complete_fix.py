#!/usr/bin/env python3
"""Complete database fix - creates all missing tables automatically"""

import sys
sys.path.insert(0, '/app')

from app import create_app
from app.extensions import db
from sqlalchemy import inspect, text
from sqlalchemy.exc import ProgrammingError

def create_missing_tables():
    app = create_app()
    
    with app.app_context():
        inspector = inspect(db.engine)
        existing = set(inspector.get_table_names())
        
        # Get all expected tables from metadata
        # First, load all models
        try:
            from app import models
            from app.wallet import models as wallet_models
            from app.transport import models as transport_models
            from app.accommodation import models as accommodation_models
            from app.events import models as events_models
            from app.admin import models as admin_models
            from app.identity import models as identity_models
            from app.audit import models as audit_models
            from app.kyc import models as kyc_models
            from app.fan import models as fan_models
        except Exception as e:
            print(f"Model loading warning: {e}")
        
        expected = set(db.metadata.tables.keys())
        missing = expected - existing
        
        print(f"Existing tables: {len(existing)}")
        print(f"Expected tables: {len(expected)}")
        print(f"Missing tables: {len(missing)}")
        
        if not missing:
            print("\n✅ All tables exist!")
            return True
        
        print(f"\nMissing: {', '.join(sorted(missing)[:20])}...")
        
        # Try to create missing tables with retries
        max_attempts = 5
        for attempt in range(max_attempts):
            print(f"\n--- Attempt {attempt + 1}/{max_attempts} ---")
            created = 0
            
            for table_name in sorted(missing):
                if table_name in existing:
                    continue
                    
                try:
                    table = db.metadata.tables.get(table_name)
                    if table:
                        table.create(db.engine, checkfirst=True)
                        print(f"  ✅ Created: {table_name}")
                        created += 1
                        existing.add(table_name)
                    else:
                        print(f"  ⚠️ No metadata: {table_name}")
                except Exception as e:
                    error = str(e)
                    if "already exists" in error.lower():
                        existing.add(table_name)
                    elif "does not exist" in error.lower():
                        print(f"  ⏳ Waiting for dependencies: {table_name}")
                    else:
                        if attempt == max_attempts - 1:
                            print(f"  ❌ Failed: {table_name} - {error[:50]}")
            
            if created == 0:
                if attempt < max_attempts - 1:
                    print("  No progress, waiting 2 seconds...")
                    import time
                    time.sleep(2)
                else:
                    break
        
        # Final count
        final_count = len(inspector.get_table_names())
        print(f"\n{'='*50}")
        print(f"Final table count: {final_count}")
        print(f"Success rate: {final_count}/{len(expected)} ({final_count*100//len(expected)}%)")
        
        # Critical tables check
        critical = ['users', 'transactions', 'organisations', 'events', 'audit_logs', 'webhook_events']
        print("\nCritical tables:")
        for table in critical:
            if inspector.has_table(table):
                print(f"  ✅ {table}")
            else:
                print(f"  ❌ {table}")
        
        return final_count == len(expected)

if __name__ == "__main__":
    success = create_missing_tables()
    sys.exit(0 if success else 1)
