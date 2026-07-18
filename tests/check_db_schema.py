from app import create_app
from app.extensions import db
from sqlalchemy import text

app = create_app()
with app.app_context():
    result = db.session.execute(text('''
        SELECT column_name, data_type, udt_name 
        FROM information_schema.columns 
        WHERE table_name = 'events' 
        ORDER BY ordinal_position
    '''))
    print("=== ACTUAL DATABASE SCHEMA FOR events ===\n")
    for row in result.fetchall():
        print(f"{row[0]}: {row[1]} ({row[2]})")
