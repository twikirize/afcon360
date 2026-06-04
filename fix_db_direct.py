import os
import sys

# Add the project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath('.')))

# Direct database connection without loading Flask app
import psycopg2

# Get database URL from environment
DATABASE_URL = os.getenv('DATABASE_URL')
if not DATABASE_URL:
    print('DATABASE_URL not found in environment')
    print('Please set DATABASE_URL environment variable')
    sys.exit(1)

# Parse connection string
import re
match = re.match(r'postgresql://([^:]+):([^@]+)@([^:]+):(\d+)/(.+)', DATABASE_URL)
if match:
    user, password, host, port, dbname = match.groups()
    
    conn = psycopg2.connect(
        host=host,
        port=port,
        dbname=dbname,
        user=user,
        password=password
    )
    conn.autocommit = True
    cur = conn.cursor()
    
    # Add missing columns
    print('Adding missing columns to events table...')
    
    cur.execute('''
        DO  
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                          WHERE table_name='events' AND column_name='is_deleted') THEN
                ALTER TABLE events ADD COLUMN is_deleted BOOLEAN DEFAULT FALSE;
                RAISE NOTICE 'Added is_deleted column';
            END IF;
            
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                          WHERE table_name='events' AND column_name='published_at') THEN
                ALTER TABLE events ADD COLUMN published_at TIMESTAMP;
                RAISE NOTICE 'Added published_at column';
            END IF;
            
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                          WHERE table_name='events' AND column_name='published_by_id') THEN
                ALTER TABLE events ADD COLUMN published_by_id BIGINT;
                RAISE NOTICE 'Added published_by_id column';
            END IF;
        END ;
    ''')
    
    print('✅ Missing columns added successfully')
    
    cur.close()
    conn.close()
else:
    print('Could not parse DATABASE_URL')
    print(f'URL format: {DATABASE_URL}')
