#!/usr/bin/env python3
"""
Final test user creation script
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.extensions import db
from app.identity.models.user import User
from app.auth.roles import ALL_GLOBAL_ROLES, assign_global_role
from app import create_app

def main():
    app = create_app()

    with app.app_context():
        try:
            print("Creating test users for all roles...")

            test_users = [
                ('owner', 'owner@afcon360.com', 'owner'),
                ('superadmin', 'superadmin@afcon360.com', 'super_admin'),
                ('admin', 'admin@afcon360.com', 'admin'),
                ('auditor', 'auditor@afcon360.com', 'auditor'),
                ('compliance', 'compliance@afcon360.com', 'compliance_officer'),
                ('moderator', 'moderator@afcon360.com', 'moderator'),
                ('support', 'support@afcon360.com', 'support'),
                ('eventmanager', 'events@afcon360.com', 'event_manager'),
                ('transportadmin', 'transport@afcon360.com', 'transport_admin'),
                ('walletadmin', 'wallet@afcon360.com', 'wallet_admin'),
                ('accommodationadmin', 'accommodation@afcon360.com', 'accommodation_admin'),
                ('tourismadmin', 'tourism@afcon360.com', 'tourism_admin'),
                ('testuser', 'user@afcon360.com', 'user'),
                ('orgadmin', 'orgadmin@afcon360.com', 'org_admin'),
                ('orgmember', 'orgmember@afcon360.com', 'org_member'),
            ]

            created_count = 0
            for username, email, role in test_users:
                existing_user = User.query.filter_by(username=username).first()
                if existing_user:
                    print(f"User {username} exists - assigning role {role}")
                    assign_global_role(existing_user.id, role)
                    continue

                user = User(
                    username=username,
                    email=email,
                    is_active=True,
                    is_verified=True
                )
                db.session.add(user)
                db.session.flush()
                assign_global_role(user.id, role)
                created_count += 1
                print(f"Created: {username} -> {role}")

            db.session.commit()
            print(f"\nCreated {created_count} new users")

            # Show current users
            users = User.query.all()
            print(f"\nTotal users: {len(users)}")
            print("\nUser list:")
            for user in users:
                print(f"  - {user.username} (ID: {user.id})")

        except Exception as e:
            db.session.rollback()
            print(f"Error: {e}")

if __name__ == "__main__":
    main()
