from app import create_app
from app.config import TestingConfig
from app.extensions import db
from sqlalchemy import MetaData, inspect, select
import json
from datetime import datetime

app = create_app(config_object=TestingConfig)
with app.app_context():
    inspector = inspect(db.engine)
    tables = [table for table in inspector.get_table_names() if table != 'alembic_version']
    metadata = MetaData()
    metadata.reflect(bind=db.engine, only=tables)
    
    # Backup data
    backup = {}
    for table in tables:
        try:
            rows = [
                dict(row)
                for row in db.session.execute(select(metadata.tables[table])).mappings()
            ]
            backup[table] = rows
            print(f'Backed up {table}: {len(rows)} rows')
        except Exception as e:
            print(f'Error backing up {table}: {e}')
    
    # Save to file
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    with open(f'backup_{timestamp}.json', 'w') as f:
        json.dump(backup, f, default=str)
    print(f'\n✅ Backup saved to backup_{timestamp}.json')
