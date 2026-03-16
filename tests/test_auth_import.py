from tests.db_connector import get_connection

try:
    # Connect using our standardized connection helper
    conn = get_connection()
    cur = conn.cursor()

    # Test query
    cur.execute("SELECT current_user, current_database();")
    user, db = cur.fetchone()
    print("✅ Connection successful!")
    print(f"Connected as user: {user}, Database: {db}")

    # Close cursor and connection
    cur.close()
    conn.close()

except Exception as e:
    print("❌ Error connecting to the database:", e)

""" 
------------------------------------
import os

# Show DATABASE_URL and all environment sources
print("DATABASE_URL:", os.getenv("DATABASE_URL"))

# Optional: print all environment variables containing 'DATABASE'

for key, value in os.environ.items():
    if "DATABASE" in key:
        print(f"{key} = {value}")


--------------------------------------------------
 from sqlalchemy import create_engine, text

import os


import os
print(os.getenv("DATABASE_URL"))


""/" 
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

try:
    from app import auth

    print("✅ SUCCESS: auth.validators is visible and imported")
except ModuleNotFoundError as e:
    print("❌ ERROR:", e)
"""
""" 
from app.extensions import db
from app.auth.models import User
print(User.__table__)
"""