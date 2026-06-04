from app import create_app
from app.extensions import db
from sqlalchemy import text

app = create_app()
with app.app_context():
    # Check the actual column type in PostgreSQL
    result = db.session.execute(text('''
        SELECT data_type, udt_name 
        FROM information_schema.columns 
        WHERE table_name = 'events' AND column_name = 'status'
    '''))
    row = result.fetchone()
    print(f"Database status type: {row[0]}")
    print(f"PostgreSQL type name: {row[1]}")
    
    # Check if it's using the enum
    result = db.session.execute(text('''
        SELECT EXISTS (
            SELECT 1 FROM pg_type 
            WHERE typname = 'eventstatus' 
            AND oid = (
                SELECT atttypid FROM pg_attribute 
                WHERE attrelid = 'events'::regclass 
                AND attname = 'status'
            )
        )
    '''))
    uses_enum = result.fetchone()[0]
    print(f"Column uses eventstatus enum: {uses_enum}")
    
    # Check the enum values
    result = db.session.execute(text('''
        SELECT enumlabel FROM pg_enum 
        WHERE enumtypid = 'eventstatus'::regtype
    '''))
    enum_values = [row[0] for row in result.fetchall()]
    print(f"Enum values in database: {enum_values}")
