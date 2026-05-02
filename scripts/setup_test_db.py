"""
Database setup for tests - creates test database
Run this before running tests: python scripts/setup_test_db.py
"""
import os
import sys
import psycopg2
from dotenv import load_dotenv

load_dotenv()

def setup_test_database():
    """Create test database if it doesn't exist"""
    db_url = os.environ.get('DATABASE_URL', 'postgresql://postgres:postgres@localhost:5432/afcon360')
    test_db_name = db_url.split('/')[-1] + '_test'
    base_url = db_url.rsplit('/', 1)[0] + '/postgres'
    
    try:
        conn = psycopg2.connect(base_url)
        conn.autocommit = True
        cur = conn.cursor()
        
        # Check if test database exists
        cur.execute(f"SELECT 1 FROM pg_database WHERE datname = '{test_db_name}'")
        if not cur.fetchone():
            cur.execute(f"CREATE DATABASE {test_db_name}")
            print(f"Created test database: {test_db_name}")
        else:
            print(f"Test database {test_db_name} already exists")
        
        cur.close()
        conn.close()
    except Exception as e:
        print(f"Error setting up test database: {e}")
        return False
    return True

if __name__ == '__main__':
    setup_test_database()