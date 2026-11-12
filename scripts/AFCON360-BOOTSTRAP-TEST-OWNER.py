#!/usr/bin/env python3
"""Create a dedicated platform-owner account in AFCON360's local test DB.

Safety properties:
- Forces APP_ENV=phone-preview / FLASK_ENV=development.
- Requires both configured and connected DB to be exactly afcon360_test.
- Collects all user input and password before opening a DB connection.
- Refuses if any owner-role assignment already exists.
- Refuses to reuse/promote an existing user account.
- Seeds canonical roles/permissions and uses assign_global_role().
- Does not alter payment-method configuration or financial records.
"""
from __future__ import annotations

import getpass
import os
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))


def collect_inputs() -> tuple[str, str, str]:
    print("AFCON360 TEST DATABASE — CREATE A DEDICATED OWNER ACCOUNT")
    print("This creates a new owner login only in afcon360_test.")
    print("It will NOT promote your existing rider/test account.\n")

    email = input("New owner email address: ").strip().lower()
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[A-Za-z]{2,}", email):
        raise SystemExit("Invalid email address. No database connection was opened.")

    username = input("New owner username: ").strip()
    if not username or len(username) > 80:
        raise SystemExit("Username must be 1–80 characters. No database connection was opened.")

    password = getpass.getpass("New owner password (16+ characters): ")
    confirmation = getpass.getpass("Confirm new owner password: ")
    if password != confirmation:
        raise SystemExit("Passwords do not match. No database connection was opened.")
    if len(password) < 16:
        raise SystemExit("Use at least 16 characters. No database connection was opened.")
    if not (re.search(r"[a-z]", password) and re.search(r"[A-Z]", password)
            and re.search(r"\d", password) and re.search(r"[^A-Za-z0-9]", password)):
        raise SystemExit(
            "Password must include lowercase, uppercase, a number and a symbol. "
            "No database connection was opened."
        )

    print("\nThis operation will create a platform-owner account in the TEST database.")
    print("It will seed missing canonical role/permission definitions if required.")
    print("It will not enable Cash/Wallet marketplace flags or change payment settings.")
    confirmation_phrase = input("Type CREATE TEST OWNER to continue: ").strip()
    if confirmation_phrase != "CREATE TEST OWNER":
        raise SystemExit("Cancelled. No database connection was opened.")

    return email, username, password


def main() -> int:
    email, username, password = collect_inputs()

    # This script is specifically for the dedicated local phone-preview env.
    os.environ["APP_ENV"] = "phone-preview"
    os.environ["FLASK_ENV"] = "development"
    os.environ["PYTHONUNBUFFERED"] = "1"

    try:
        from sqlalchemy import text, func
        from sqlalchemy.engine import make_url
        from app import create_app
        from app.extensions import db
        from app.identity.models.user import User, UserRole
        from app.identity.models.roles_permission import Role
        from app.auth.seed_roles import seed_all
        from app.auth.roles import assign_global_role
    except Exception as exc:
        print(f"ERROR importing AFCON360: {type(exc).__name__}: {exc}")
        return 2

    app = create_app()
    with app.app_context():
        configured_uri = app.config.get("SQLALCHEMY_DATABASE_URI")
        if not configured_uri:
            print("STOP: SQLALCHEMY_DATABASE_URI is not configured.")
            return 3
        configured_db = make_url(configured_uri).database
        print(f"CONFIGURED DATABASE: {configured_db}")
        if configured_db != "afcon360_test":
            print("STOP: Refusing to run unless configured DB is exactly afcon360_test.")
            return 4

        try:
            with db.engine.connect() as connection:
                identity = connection.execute(text("""
                    SELECT current_database(), current_user, current_setting('TimeZone')
                """)).one()
        except Exception as exc:
            print(f"STOP: Could not verify the database: {type(exc).__name__}: {exc}")
            return 5

        actual_db, db_role, timezone_name = identity
        print(f"CONNECTED DATABASE: {actual_db}")
        print(f"DATABASE ROLE: {db_role}")
        print(f"SESSION TIMEZONE: {timezone_name}")
        if actual_db != "afcon360_test" or timezone_name.upper() != "UTC":
            print("STOP: Database identity/timezone safety verification failed.")
            return 6
        print("DATABASE SAFETY: PASS\n")

        # Seed canonical RBAC definitions idempotently before assigning the role.
        try:
            seed_all(verbose=True)

            existing_user = User.query.filter(func.lower(User.email) == email).first()
            if existing_user:
                db.session.rollback()
                print("STOP: That email already belongs to an account.")
                print("No existing account was modified or promoted. Choose a new test-owner email.")
                return 7

            owner_role = Role.query.filter_by(name="owner", scope="global").first()
            if owner_role is None:
                db.session.rollback()
                print("STOP: Canonical global owner role was not created.")
                return 8

            existing_owner_assignments = db.session.query(
                User.id, User.email, User.is_active
            ).join(
                UserRole, UserRole.user_id == User.id
            ).filter(
                UserRole.role_id == owner_role.id
            ).all()
            if existing_owner_assignments:
                db.session.rollback()
                print("STOP: An owner-role assignment already exists in this test DB:")
                for owner_id, owner_email, active in existing_owner_assignments:
                    safe_email = (owner_email[:1] + "***" + owner_email[owner_email.find("@"):] if "@" in owner_email else "[redacted]")
                    print(f"  user_id={owner_id}; email={safe_email}; active={bool(active)}")
                print("No additional owner was created. Review that account first.")
                return 9

            user = User(
                username=username,
                email=email,
                is_verified=True,
                is_active=True,
            )
            user.set_password(password)
            db.session.add(user)
            db.session.flush()
            new_user_id = int(user.id)

            # Use the project's RBAC assignment service, not handwritten SQL.
            assign_global_role(new_user_id, "owner", assigned_by_id=None)
            db.session.expire_all()
            verified_user = db.session.get(User, new_user_id)
            assigned_owner = any(
                link.role and link.role.name == "owner" and link.role.scope == "global"
                for link in (verified_user.roles or [])
            )
            if not assigned_owner or not verified_user.is_active:
                db.session.rollback()
                print("STOP: Post-creation owner verification failed; transaction rolled back where possible.")
                return 10

            print("\nOWNER ACCOUNT CREATED SUCCESSFULLY")
            print(f"USERNAME: {username}")
            print(f"EMAIL: {email}")
            print("ACCOUNT: active; local test account marked verified")
            print("GLOBAL ROLE: owner")
            print("PASSWORD: set securely; not displayed")
            print("PAYMENT CONFIGURATION: unchanged")
            print("FINANCIAL RECORDS: unchanged")
            print("\nSign in at http://127.0.0.1:5000/login")
            print("If owner MFA is enforced, complete the authenticator enrollment/verification flow.")
            return 0
        except Exception as exc:
            db.session.rollback()
            print(f"ERROR: {type(exc).__name__}: {exc}")
            print("The operation was rolled back where possible. Check the database before retrying.")
            return 11
        finally:
            password = ""  # Avoid retaining plaintext longer than the script needs it.
            db.session.remove()


if __name__ == "__main__":
    raise SystemExit(main())
