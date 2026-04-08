"""
Run this script to set up owner role and assign to user.
Usage: python setup_owner.py
"""

import sys
import os

# Add project to path if needed
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app
from app.extensions import db
from app.identity.models import User, Role, UserRole

# Initialize Flask app
app = create_app()

with app.app_context():
    # 1. Look up user by username (case-insensitive)
    user = User.query.filter(User.username.ilike('obed')).first()

    if not user:
        print("User not found.")
        exit(1)

    print(f"User: {user.username}")
    print(f"Is Verified: {user.is_verified}")
    print(f"Is Active: {user.is_active}")

    # 2. Ensure Owner role exists
    owner_role = Role.query.filter(Role.name.ilike('Owner')).first()
    if not owner_role:
        owner_role = Role(name='Owner', description='Full access to the system')
        db.session.add(owner_role)
        db.session.commit()
        print("Created Owner role.")

    # 3. Assign Owner role to user if not already assigned
    if not any(ur.role_id == owner_role.id for ur in user.roles):
        user_role = UserRole(user_id=user.id, role_id=owner_role.id)
        db.session.add(user_role)
        db.session.commit()
        print(f"Assigned Owner role to {user.username}.")
    else:
        print(f"{user.username} already has the Owner role.")

    # 4. Print all user roles
    role_names = [ur.role.name for ur in user.roles]
    print(f"Roles: {role_names}")
