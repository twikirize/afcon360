#!/usr/bin/env python
"""
Reset test database - Drops and recreates the test database
Run: python scripts/reset_test_db.py
"""
import os
import sys
import psycopg2
from dotenv import load_dotenv

load_dotenv()

def reset_test_database():
    """Drop and recreate test database"""
    db_url = os.environ.get('DATABASE_URL', 'postgresql://postgres:postgres@localhost:5432/afcon360')
    db_name = db_url.split('/')[-1]
    test_db_name = f'{db_name}_test'
    base_url = db_url.rsplit('/', 1)[0] + '/postgres'
    
    print(f"Resetting test database: {test_db_name}")
    
    try:
        conn = psycopg2.connect(base_url)
        conn.autocommit = True
        cur = conn.cursor()
        
        # Terminate existing connections
        cur.execute(f"""
            SELECT pg_terminate_backend(pg_stat_activity.pid)
            FROM pg_stat_activity
            WHERE pg_stat_activity.datname = '{test_db_name}'
            AND pid <> pg_backend_pid()
        """)
        
        # Drop database
        cur.execute(f"DROP DATABASE IF EXISTS {test_db_name}")
        print(f"✓ Dropped database {test_db_name}")
        
        # Create fresh database
        cur.execute(f"CREATE DATABASE {test_db_name}")
        print(f"✓ Created database {test_db_name}")
        
        cur.close()
        conn.close()
        print("✅ Test database reset successfully!")
        return True
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

if __name__ == '__main__':
    success = reset_test_database()
    sys.exit(0 if success else 1)