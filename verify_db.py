import sys
import logging

logging.basicConfig(level=logging.ERROR)

try:
    from app import create_app
    from app.extensions import db

    app = create_app()
    print("DB_VERIFY_OK")
    sys.exit(0)
except Exception as e:
    print(f"ERROR: {e}")
    sys.exit(1)
