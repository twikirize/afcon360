# fix_events_schema.py
from app import create_app
from app.extensions import db
from sqlalchemy import text

def fix_schema():
    app = create_app()
    with app.app_context():
        print("Connecting to database...")
        
        # 1. Create event_ticket_types table
        create_ticket_types_table = """
        CREATE TABLE IF NOT EXISTS event_ticket_types (
            id BIGSERIAL PRIMARY KEY,
            event_id BIGINT NOT NULL REFERENCES events(id) ON DELETE CASCADE,
            name VARCHAR(100) NOT NULL,
            description TEXT,
            price NUMERIC(10, 2) DEFAULT 0,
            capacity INTEGER,
            available_from TIMESTAMP,
            available_until TIMESTAMP,
            is_active BOOLEAN DEFAULT TRUE
        );
        """
        
        # 2. Add ticket_type_id to event_registrations
        add_column = """
        ALTER TABLE event_registrations 
        ADD COLUMN IF NOT EXISTS ticket_type_id BIGINT REFERENCES event_ticket_types(id) ON DELETE SET NULL;
        """
        
        try:
            with db.engine.connect() as conn:
                print("Creating event_ticket_types table...")
                conn.execute(text(create_ticket_types_table))
                
                print("Adding ticket_type_id column to event_registrations...")
                conn.execute(text(add_column))
                
                conn.commit()
                print("✅ Database schema updated successfully!")
        except Exception as e:
            print(f"❌ Error updating schema: {e}")

if __name__ == "__main__":
    fix_schema()
