#!/usr/bin/env python
"""
Fix Owner Role Assignment Script
Run: python fix_owner.py
"""

import sys
import os

# Add project to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app
from app.config import TestingConfig
from app.extensions import db
from app.identity.models.roles_permission import Role
from app.identity.models.user import User, UserRole


def fix_owner_role(email="twikirizeobed@gmail.com"):
    """Assign the owner role idempotently through mapped SQLAlchemy models."""
    app = create_app(config_object=TestingConfig)
    with app.app_context():
        user = User.query.filter_by(email=email, is_deleted=False).first()
        owner_role = Role.query.filter_by(name='owner').first()
        if not user or not owner_role:
            return False

        existing = UserRole.query.filter_by(
            user_id=user.id,
            role_id=owner_role.id,
        ).first()
        if existing:
            return True

        db.session.add(UserRole(
            user_id=user.id,
            role_id=owner_role.id,
            assigned_by=user.id,
        ))
        db.session.commit()
        return True


if __name__ == "__main__":
    raise SystemExit(0 if fix_owner_role() else 1)
