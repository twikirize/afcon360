"""
setup_test_db.py - Completely reset test database
Run: python scripts/setup_test_db_schema.py
"""
import sys
import os
import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

def reset_test_database():
    """Completely drop and recreate the test database"""
    
    # Connection parameters
    user = 'israeli'
    password = 'Israelipass'
    host = 'localhost'
    port = 5432
    test_db = 'afcon360_test'
    
    try:
        # Connect to postgres database (not the test db)
        conn = psycopg2.connect(
            host=host,
            port=port,
            user=user,
            password=password,
            database='postgres'
        )
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        cur = conn.cursor()
        
        # Kill all connections to test database
        cur.execute(f"""
            SELECT pg_terminate_backend(pg_stat_activity.pid)
            FROM pg_stat_activity
            WHERE pg_stat_activity.datname = '{test_db}'
            AND pid <> pg_backend_pid()
        """)
        
        # Drop test database if exists
        cur.execute(f"DROP DATABASE IF EXISTS {test_db}")
        print(f"✓ Dropped database {test_db}")
        
        # Create fresh test database
        cur.execute(f"CREATE DATABASE {test_db}")
        print(f"✓ Created database {test_db}")
        
        cur.close()
        conn.close()
        print("✅ Test database reset successfully!")
        
        # Now create schema using Flask
        from app import create_app
        from app.config import TestingConfig
        from app.extensions import db
        
        app = create_app(config_object=TestingConfig)
        with app.app_context():
            # This will work now because database is empty
            db.create_all()
            print("✓ Created all tables and indexes")
            print("✅ Test database schema ready!")
            
    except Exception as e:
        print(f"Error: {e}")
        print("\nMake sure PostgreSQL is running and credentials are correct")

if __name__ == '__main__':
    reset_test_database()
