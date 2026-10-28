import sys
from pathlib import Path
from sqlalchemy import text

# adjust this import to match how your app exposes its engine
from app import create_app, db   # <-- change if your factory/import differs

SQL_FILE = Path(__file__).resolve().parent / "audit_pickup_time.sql"

def split_statements(sql: str):
    # naive split is fine for this file (no ; inside string literals)
    return [s.strip() for s in sql.split(";") if s.strip()]

def main() -> int:
    app = create_app()
    with app.app_context():
        raw = SQL_FILE.read_text(encoding="utf-8")
        for stmt in split_statements(raw):
            # skip the transaction wrapper – SQLAlchemy manages the tx
            if stmt.upper() in ("BEGIN READ ONLY", "BEGIN", "ROLLBACK", "COMMIT"):
                continue
            for row in db.session.execute(text(stmt)):
                print(" | ".join(str(c) for c in row))
        db.session.rollback()
    return 0

if __name__ == "__main__":
    sys.exit(main())