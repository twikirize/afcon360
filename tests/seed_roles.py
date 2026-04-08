#!/usr/bin/env python3
"""
Standalone script to seed roles
Run with: python seed_roles.py
"""
import os
import sys

# Add the app directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.extensions import db
from app.auth.seed_roles import seed_roles
from app import create_app

def main():
    """Main function to seed roles"""
    app = create_app()

    with app.app_context():
        try:
            seed_roles()
            print("\n✅ Roles seeded successfully!")
            print("🎯 You can now test impersonation functionality")
        except Exception as e:
            print(f"\n❌ Error seeding roles: {e}")
            sys.exit(1)

if __name__ == "__main__":
    main()
