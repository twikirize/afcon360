"""Restore pre-wipe roles for OBEDZ (user id=2) from backup_20260603_003918.json ground truth:
   accommodation_admin, tourism_admin, moderator — all originally assigned_by=None.
HIGH_RISK (identity/roles). Uses the sanctioned service assign_global_role (idempotent)."""
import sys
sys.path.insert(0, 'C:/Users/OBED/Desktop/afcon360_app')
import os
os.environ.setdefault('DATABASE_URL', 'postgresql://israeli:Israelipass@localhost:5432/afcon360_prod')
from app import create_app
from app.extensions import db
from app.auth.roles import assign_global_role

USER_ID = 2
ROLES = ["accommodation_admin", "tourism_admin", "moderator"]

app = create_app()
with app.app_context():
    for role_name in ROLES:
        ur = assign_global_role(USER_ID, role_name, assigned_by_id=None)
        db.session.flush()
        print(f"OK  OBEDZ + '{role_name}' -> user_roles id={ur.id}")
    db.session.commit()
    print("Restore complete.")