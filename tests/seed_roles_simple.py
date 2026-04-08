#!/usr/bin/env python3
"""
Simple role seeding script without Unicode issues
"""
import os
import sys

# Add to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.extensions import db
from app.auth.roles import ALL_GLOBAL_ROLES
from app.identity.models.roles_permission import Role
from app import create_app

def main():
    """Main function to seed roles"""
    app = create_app()

    with app.app_context():
        try:
            created_count = 0
            updated_count = 0

            for role_name in ALL_GLOBAL_ROLES:
                # Check if role exists
                existing_role = Role.query.filter_by(name=role_name, scope='global').first()

                if existing_role:
                    updated_count += 1
                    print("Updated role: {}".format(role_name))
                else:
                    # Create new role
                    role = Role(name=role_name, scope='global')
                    db.session.add(role)
                    created_count += 1
                    print("Created role: {}".format(role_name))

            db.session.commit()
            print("\nRole seeding complete!")
            print("Created: {} roles".format(created_count))
            print("Updated: {} roles".format(updated_count))
            print("Total: {} roles processed".format(created_count + updated_count))

        except Exception as e:
            db.session.rollback()
            print("Error seeding roles: {}".format(e))
            sys.exit(1)

if __name__ == "__main__":
    main()
