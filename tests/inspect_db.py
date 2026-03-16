from sqlalchemy import inspect, text

from app import create_app
from app.extensions import db

app = create_app()

with app.app_context():
    insp = inspect(db.engine)

    print("TABLES:")
    print(insp.get_table_names())

    print("\nUSERS COLUMNS:")
    print([c["name"] for c in insp.get_columns("users")])

    print("\nUSER_ROLES COLUMNS:")
    print([c["name"] for c in insp.get_columns("user_roles")])

    print("\nUSER_ROLES FKs:")
    for fk in insp.get_foreign_keys("user_roles"):
        print(fk)

    if "audit_logs" in insp.get_table_names():
        print("\nAUDIT_LOGS FKs:")
        for fk in insp.get_foreign_keys("audit_logs"):
            print(fk)
    else:
        print("\nAUDIT_LOGS: not present")

    print("\nSAMPLE ROWS:")
    for t in ("users", "user_roles", "audit_logs"):
        if t in insp.get_table_names():
            rows = db.session.execute(
                text(f"SELECT * FROM {t} LIMIT 3")
            ).fetchall()
            print(f"{t}:", rows)
