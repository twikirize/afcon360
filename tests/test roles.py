#!/usr/bin/env python3
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_roles():
    try:
        from app.auth.roles import ALL_GLOBAL_ROLES
        print("SUCCESS: All roles imported!")
        print("\nAvailable roles for impersonation:")
        for i, role in enumerate(ALL_GLOBAL_ROLES, 1):
            print(f"  {i:2d}. {role}")
        return True
    except Exception as e:
        print(f"ERROR: Could not import roles: {e}")
        return False

def test_impersonation_routes():
    try:
        from app.admin.owner.routes import impersonate_role, impersonate_user, exit_impersonation
        print("SUCCESS: Impersonation routes imported!")
        return True
    except Exception as e:
        print(f"ERROR: Could not import impersonation routes: {e}")
        return False

def main():
    print("IMPERSONATION SYSTEM TEST")
    print("=" * 50)

    print("\n1. Testing role definitions...")
    roles_ok = test_roles()

    print("\n2. Testing impersonation routes...")
    routes_ok = test_impersonation_routes()

    print("\n3. Testing dashboard redirects...")
    try:
        from app.admin.owner.routes import dashboard_redirects
        print("SUCCESS: Dashboard redirect mappings found!")
        for role, url in dashboard_redirects.items():
            print(f"  {role:20} -> {url}")
    except Exception as e:
        print(f"ERROR: Could not import dashboard mappings: {e}")

    print("\n" + "=" * 50)
    if roles_ok and routes_ok:
        print("SUCCESS: IMPERSONATION SYSTEM IS READY!")
        print("\nNext steps:")
        print("1. Start your Flask application")
        print("2. Login as owner user")
        print("3. Navigate to /admin/owner/impersonate-page")
        print("4. Test impersonating different roles")
        print("5. Verify dashboard redirects work correctly")
    else:
        print("ERROR: IMPERSONATION SYSTEM HAS ISSUES!")

if __name__ == "__main__":
    main()
