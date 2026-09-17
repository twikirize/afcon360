"""Restore lost role assignments for the platform owner (OBED).

Diagnosis: the user_roles table was emptied at some point (audit trail is
completely blank — zero rows in owner_audit_logs, admin_audit_logs,
security_event_logs). The roles catalog (21 roles) survived. Users (42 rows)
survived. Only the user↔role bindings were lost.

This script re-assigns the owner's global roles via the sanctioned service
(assign_global_role) which is idempotent, audit-logged, and uses the normal
db_transaction context.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app import create_app
from app.auth.roles import assign_global_role

OWNER_USER_ID = 1  # OBED — twikirizeobed@gmail.com

ROLES_TO_RESTORE = [
    "owner",
    "super_admin",
    "admin",
    "accommodation_admin",
]


def main():
    app = create_app()
    with app.app_context():
        for role_name in ROLES_TO_RESTORE:
            try:
                ur = assign_global_role(
                    user_id=OWNER_USER_ID,
                    role_name=role_name,
                    assigned_by_id=OWNER_USER_ID,
                )
                print(f"  assigned_by_id=OWNER_USER_ID={OWNER_USER_ID}")
                print(f"  role: {role_name} -> UserRole id={ur.id}, user_id={ur.user_id}, role_id={ur.role_id}, assigned_at={ur.assigned_at}")
            except Exception as e:
                print(f"  FAILED {role_name}: {e}")
                raise

        print("\nDone. Verify with:")
        print("  SELECT ur.id, r.name FROM user_roles ur JOIN roles r ON r.id=ur.role_id WHERE ur.user_id=1;")


if __name__ == "__main__":
    main()