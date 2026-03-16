from tests.db_connector import get_connection
import os

# App user credentials from .env
APP_USER = os.getenv("APP_USER", "afcon_app_user")
APP_PASSWORD = os.getenv("APP_PASSWORD", "default_pass")  # secure password in .env

try:
    # Connect as superuser
    conn = get_connection()
    cur = conn.cursor()
    print("✅ Connected as superuser")

    # -------------------------------
    # Step 1: Create secure app user if not exists
    # -------------------------------
    cur.execute(f"""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '{APP_USER}') THEN
                CREATE ROLE {APP_USER} WITH LOGIN PASSWORD '{APP_PASSWORD}';
            END IF;
        END
        $$;
    """)
    print(f"✅ App user '{APP_USER}' ensured")

    # Grant privileges to public schema tables
    cur.execute(f"""
        GRANT CONNECT ON DATABASE {cur.connection.info.dbname} TO {APP_USER};
        GRANT USAGE ON SCHEMA public TO {APP_USER};
        GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {APP_USER};
        ALTER DEFAULT PRIVILEGES IN SCHEMA public
        GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {APP_USER};
    """)
    print(f"✅ Privileges granted to '{APP_USER}'")

    # -------------------------------
    # Step 2: Audit Primary Keys
    # -------------------------------
    print("\n--- Primary Keys ---")
    cur.execute("""
        SELECT
            tc.table_schema,
            tc.table_name,
            kcu.column_name
        FROM information_schema.table_constraints AS tc
        JOIN information_schema.key_column_usage AS kcu
        ON tc.constraint_name = kcu.constraint_name
        WHERE tc.constraint_type = 'PRIMARY KEY'
        ORDER BY tc.table_schema, tc.table_name;
    """)
    for row in cur.fetchall():
        print(row)

    # -------------------------------
    # Step 3: Audit Foreign Keys
    # -------------------------------
    print("\n--- Foreign Keys ---")
    cur.execute("""
        SELECT
            tc.table_schema,
            tc.table_name,
            kcu.column_name,
            ccu.table_schema AS foreign_table_schema,
            ccu.table_name AS foreign_table_name,
            ccu.column_name AS foreign_column_name
        FROM information_schema.table_constraints AS tc
        JOIN information_schema.key_column_usage AS kcu
          ON tc.constraint_name = kcu.constraint_name
        JOIN information_schema.constraint_column_usage AS ccu
          ON ccu.constraint_name = tc.constraint_name
        WHERE tc.constraint_type = 'FOREIGN KEY'
        ORDER BY tc.table_schema, tc.table_name;
    """)
    for row in cur.fetchall():
        print(row)

    # -------------------------------
    # Step 4: Audit Indexes
    # -------------------------------
    print("\n--- Indexes ---")
    cur.execute("""
        SELECT
            schemaname,
            tablename,
            indexname,
            indexdef
        FROM pg_indexes
        WHERE schemaname = 'public'
        ORDER BY tablename, indexname;
    """)
    for row in cur.fetchall():
        print(row)

    # -------------------------------
    # Step 5: Table sizes
    # -------------------------------
    print("\n--- Table Sizes (MB) ---")
    cur.execute("""
        SELECT
            schemaname,
            relname AS table_name,
            pg_size_pretty(pg_total_relation_size(relid)) AS total_size
        FROM pg_catalog.pg_statio_user_tables
        ORDER BY pg_total_relation_size(relid) DESC;
    """)
    for row in cur.fetchall():
        print(row)

    # -------------------------------
    # Finish
    # -------------------------------
    cur.close()
    conn.close()
    print("\n✅ Phase 2 audit and secure user setup complete")

except Exception as e:
    print("❌ Error:", e)
