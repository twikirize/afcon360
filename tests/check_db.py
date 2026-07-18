from app import create_app
from app.extensions import db
from sqlalchemy import text

app = create_app()
with app.app_context():
    print("=== CHECKING DATABASE SCHEMA ===\n")
    
    # Check events table status column
    result = db.session.execute(text("""
        SELECT data_type, udt_name 
        FROM information_schema.columns 
        WHERE table_name = 'events' AND column_name = 'status'
    """))
    row = result.fetchone()
    if row:
        print(f"events.status: data_type={row[0]}, udt_name={row[1]}")
    
    # Check if eventstatus enum exists
    result = db.session.execute(text("SELECT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'eventstatus')"))
    print(f"eventstatus enum exists: {result.fetchone()[0]}")
    
    # Check current alembic version
    result = db.session.execute(text("SELECT version_num FROM alembic_version"))
    version = result.fetchone()
    print(f"Alembic version: {version[0] if version else 'None'}")
    
    # Check if event_host_registrations table exists
    result = db.session.execute(text("""
        SELECT EXISTS (
            SELECT 1 FROM information_schema.tables 
            WHERE table_name = 'event_host_registrations'
        )
    """))
    print(f"event_host_registrations table exists: {result.fetchone()[0]}")
    
    # List all event-related tables
    result = db.session.execute(text("""
        SELECT tablename FROM pg_tables 
        WHERE schemaname='public' AND tablename LIKE '%event%'
        ORDER BY tablename
    """))
    tables = [row[0] for row in result.fetchall()]
    print(f"\nEvent-related tables: {tables}")
