from app import create_app
from app.extensions import db
from sqlalchemy import text

app = create_app()
with app.app_context():
    try:
        # Add column if it doesn't exist
        db.session.execute(text("ALTER TABLE properties ADD COLUMN IF NOT EXISTS event_metadata JSONB DEFAULT '{}'::jsonb"))
        db.session.commit()
        print("Column event_metadata added successfully")
    except Exception as e:
        print(f"Error: {e}")
        db.session.rollback()
