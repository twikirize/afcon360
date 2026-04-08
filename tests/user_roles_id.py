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

    # Example query: users + organisations + roles
    cur.execute("""
        SELECT u.username, o.legal_name, m.role
        FROM users u
        JOIN organisation_members m ON u.id = m.user_id
        JOIN organisations o ON o.id = m.organisation_id
        LIMIT 10;
    """)

    rows = cur.fetchall()

    # Print results nicely
    for username, org_name, role in rows:
        print(f"User: {username}, Organisation: {org_name}, Role: {role}")

    cur.close()
    conn.close()
except Exception as e:
    print("❌ Error:", e)
