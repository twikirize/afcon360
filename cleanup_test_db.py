"""Direct cleanup of orphan organisation rows in the TEST database."""
from sqlalchemy import create_engine, text
from urllib.parse import quote_plus

URL = "postgresql://israeli:Israelipass@localhost:5432/afcon360_test"
engine = create_engine(URL)
with engine.begin() as conn:
    n = conn.execute(text("SELECT count(*) FROM organisations")).scalar()
    print(f"Organisations before: {n}")
    for table in ("org_user_roles", "org_role_permissions", "org_roles", "organisation_members"):
        try:
            conn.execute(text(f"DELETE FROM {table}"))
        except Exception as e:
            print(f"  could not delete {table}: {e}")
    conn.execute(text("DELETE FROM organisations"))
    n2 = conn.execute(text("SELECT count(*) FROM organisations")).scalar()
    print(f"Organisations after: {n2}")

    # Remove residual test-created users (4B-1 onboarding tests persist the
    # creator user along with the organisation transaction).
    for prefix in ("4b1-", "diag-", "org-"):
        try:
            m = conn.execute(
                text("DELETE FROM users WHERE email LIKE :p"),
                {"p": f"{prefix}%@example.com"},
            )
            print(f"Deleted {m.rowcount} users with email prefix '{prefix}'")
        except Exception as e:
            print(f"  could not delete {prefix} users: {e}")
