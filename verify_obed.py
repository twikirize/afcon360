import os
import sys
from app import create_app
from app.extensions import db
from app.identity.models import User, Role, UserRole


def verify_and_promote_owner(username="OBED"):
    """
    Script to verify a specific user and assign the 'owner' role.
    Run this from the terminal: python verify_obed.py
    """
    app = create_app()

    with app.app_context():
        print(f"--- Starting verification process for user: {username} ---")

        # 1. Fetch the user
        user = User.query.filter_by(username=username).first()
        if not user:
            print(f"Error: User '{username}' not found in the database.")
            return

        # 2. Verify and Activate the user
        user.is_verified = True
        user.is_active = True

        # If UserProfile logic exists (as seen in routes.py), try to update it
        try:
            from app.profile.models import UserProfile
            profile = UserProfile.query.filter_by(user_id=user.user_id).first()
            if profile:
                profile.is_verified = True
                print("Associated user profile marked as verified.")
        except ImportError:
            pass

        # 3. Ensure 'owner' role exists in the system
        owner_role = Role.query.filter_by(name='owner').first()
        if not owner_role:
            print("Role 'owner' not found. Creating it now...")
            owner_role = Role(name='owner', description='Platform Owner with full permissions')
            db.session.add(owner_role)
            db.session.flush()  # Get the ID before committing

        # 4. Assign the 'owner' role to the user
        existing_assignment = UserRole.query.filter_by(user_id=user.id, role_id=owner_role.id).first()
        if not existing_assignment:
            new_link = UserRole(user_id=user.id, role_id=owner_role.id)
            db.session.add(new_link)
            print(f"Assigned 'owner' role to {username}.")
        else:
            print(f"User {username} already possesses the 'owner' role.")

        # 5. Commit changes
        try:
            db.session.commit()
            print(f"Successfully verified {username} and promoted to OWNER.")
        except Exception as e:
            db.session.rollback()
            print(f"Failed to save changes: {e}")


if __name__ == "__main__":
    verify_and_promote_owner()
