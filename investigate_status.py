from app import create_app
from app.extensions import db
from sqlalchemy import text

app = create_app()
with app.app_context():
    print("=== INVESTIGATING EVENT STATUS ===\n")
    
    # 1. Check what values are currently in the status column
    result = db.session.execute(text('''
        SELECT DISTINCT status, COUNT(*) 
        FROM events 
        GROUP BY status 
        ORDER BY status
    '''))
    print("Current status values in database:")
    for row in result.fetchall():
        print(f"  '{row[0]}': {row[1]} records")
    
    # 2. Check if any status values won't fit in the enum
    print("\nChecking enum values vs database values...")
    result = db.session.execute(text('''
        SELECT enumlabel FROM pg_enum 
        WHERE enumtypid = 'eventstatus'::regtype 
        ORDER BY enumsortorder
    '''))
    enum_values = [row[0] for row in result.fetchall()]
    print(f"Enum allows: {enum_values}")
    
    # 3. Check for orphaned values
    result = db.session.execute(text('''
        SELECT DISTINCT status FROM events 
        WHERE status NOT IN (
            SELECT enumlabel FROM pg_enum 
            WHERE enumtypid = 'eventstatus'::regtype
        )
    '''))
    orphaned = [row[0] for row in result.fetchall()]
    if orphaned:
        print(f"\n⚠️ Found values NOT in enum: {orphaned}")
    else:
        print("\n✅ All database values match the enum")
    
    # 4. Check model definition
    from app.events.constants import EventStatus
    print(f"\nModel EventStatus values: {[s.value for s in EventStatus]}")
