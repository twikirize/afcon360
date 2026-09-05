"""One-off cleanup: remove orphan org rows left by debug scripts."""
import os
os.environ.setdefault("APP_ENV", "local")
from app import create_app
app = create_app()
with app.app_context():
    from app import db
    from sqlalchemy import text
    # Check existing orgs first
    rows = db.session.execute(text("SELECT id, org_id, legal_name, country, tax_id FROM organisations")).fetchall()
    print(f"Found {len(rows)} organisations:")
    for r in rows:
        print(f"  id={r[0]} org_id={r[1]} legal_name={r[2]} country={r[3]} tax_id={r[4]!r}")
    # Delete all orgs (dependents cascade in proper order)
    for table in ("org_user_roles", "org_role_permissions", "org_roles", "organisation_members"):
        try:
            db.session.execute(text(f"DELETE FROM {table}"))
        except Exception as e:
            print(f"  could not delete {table}: {e}")
    try:
        db.session.execute(text("DELETE FROM organisations"))
        print("Deleted all organisations")
    except Exception as e:
        print(f"  could not delete organisations: {e}")
    db.session.commit()
    rows = db.session.execute(text("SELECT id, org_id, legal_name FROM organisations")).fetchall()
    print(f"After cleanup, {len(rows)} organisations remain")
