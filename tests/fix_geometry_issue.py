# check_postgis.py
from app import create_app

app = create_app()

with app.app_context():
    from app.extensions import db
    from sqlalchemy import text

    try:
        # Try a PostGIS function
        result = db.session.execute(text("SELECT PostGIS_version()")).fetchone()
        print(f"✅ PostGIS is installed: {result[0]}")
    except Exception as e:
        print(f"❌ PostGIS is NOT available: {e}")
        print("\nYou need to install it:")
        print("1. Open pgAdmin")
        print("2. Connect to database: afcon360_p")
        print("3. Run: CREATE EXTENSION postgis;")
