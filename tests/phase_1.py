import psycopg2

try:
    # 1️⃣ Connect to your PostgreSQL database
    conn = psycopg2.connect(
        host="localhost",
        port=5432,
        dbname="afcon360_prod",
        user="israeli",
        password="Israelipass"  # replace with your password
    )
    print("✅ Connection successful!")

    # 2️⃣ Create a cursor to execute queries
    cur = conn.cursor()

    print("\n--- Step 1: Environment & Server ---")
    cur.execute("""
        SELECT
            current_database() AS database,
            current_user AS user,
            inet_server_addr() AS server_ip,
            inet_server_port() AS port,
            version() AS postgres_version;
    """)
    for row in cur.fetchall():
        print(row)

    print("\n--- Step 2: Roles & Privileges ---")
    cur.execute("""
        SELECT
            rolname,
            rolsuper,
            rolcreatedb,
            rolcreaterole,
            rolcanlogin
        FROM pg_roles
        ORDER BY rolname;
    """)
    for row in cur.fetchall():
        print(row)

    print("\n--- Step 3: Schemas ---")
    cur.execute("""
        SELECT schema_name
        FROM information_schema.schemata
        ORDER BY schema_name;
    """)
    for row in cur.fetchall():
        print(row)

    print("\n--- Step 4: Tables ---")
    cur.execute("""
        SELECT
            table_schema,
            table_name
        FROM information_schema.tables
        WHERE table_type = 'BASE TABLE'
        ORDER BY table_schema, table_name;
    """)
    for row in cur.fetchall():
        print(row)

    # 3️⃣ Close cursor and connection
    cur.close()
    conn.close()

except Exception as e:
    print("❌ Error connecting to the database or running queries:", e)
