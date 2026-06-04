from app import create_app
from app.extensions import db
from sqlalchemy import text
import json
from datetime import datetime

app = create_app()
with app.app_context():
    # Get all table names
    result = db.session.execute(text("""
        SELECT tablename FROM pg_tables 
        WHERE schemaname = 'public' AND tablename != 'alembic_version'
        ORDER BY tablename
    """))
    tables = [row[0] for row in result.fetchall()]
    
    # Backup data
    backup = {}
    for table in tables:
        try:
            result = db.session.execute(text(f'SELECT * FROM {table}'))
            rows = [dict(row._mapping) for row in result.fetchall()]
            backup[table] = rows
            print(f'Backed up {table}: {len(rows)} rows')
        except Exception as e:
            print(f'Error backing up {table}: {e}')
    
    # Save to file
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    with open(f'backup_{timestamp}.json', 'w') as f:
        json.dump(backup, f, default=str)
    print(f'\n✅ Backup saved to backup_{timestamp}.json')
