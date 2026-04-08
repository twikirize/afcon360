# app/auth/seed_roles.py
"""
Seed all roles in the database.
Run with: flask seed-roles
"""

from app.extensions import db
from app.identity.models.roles_permission import Role
from app.auth.roles import ALL_GLOBAL_ROLES

def seed_roles():
    """Create all roles if they don't exist."""

    role_descriptions = {
        'owner': 'System owner with full access to all features',
        'super_admin': 'Super administrator with system-wide access',
        'admin': 'Administrator with limited system access',
        'auditor': 'Read-only access to audit logs',
        'compliance_officer': 'AML review and compliance management',
        'moderator': 'Content moderation and user management',
        'support': 'Customer support and user assistance',
        'event_manager': 'Event management and approval',
        'transport_admin': 'Transport system administration',
        'wallet_admin': 'Wallet and transaction management',
        'accommodation_admin': 'Accommodation property management',
        'tourism_admin': 'Tourism content and destination management',
        'user': 'Regular user with basic access',
        'org_admin': 'Organization administrator',
        'org_member': 'Organization member'
    }

    role_levels = {
        'owner': 100,
        'super_admin': 90,
        'admin': 80,
        'auditor': 70,
        'compliance_officer': 75,
        'moderator': 60,
        'support': 55,
        'event_manager': 65,
        'transport_admin': 70,
        'wallet_admin': 75,
        'accommodation_admin': 70,
        'tourism_admin': 65,
        'user': 10,
        'org_admin': 50,
        'org_member': 30
    }

    created_count = 0
    updated_count = 0

    for role_name in ALL_GLOBAL_ROLES:
        # Check if role exists
        existing_role = Role.query.filter_by(name=role_name, scope='global').first()

        if existing_role:
            # Update existing role
            existing_role.description = role_descriptions.get(role_name, '')
            existing_role.level = role_levels.get(role_name, None)
            updated_count += 1
            print("✓ Updated role: {}".format(role_name))
        else:
            # Create new role
            role = Role(
                name=role_name,
                scope='global',
                description=role_descriptions.get(role_name, ''),
                level=role_levels.get(role_name, None)
            )
            db.session.add(role)
            created_count += 1
            print("+ Created role: {}".format(role_name))

    # Also create org roles
    org_roles = ['org_admin', 'org_member']
    for role_name in org_roles:
        existing_role = Role.query.filter_by(name=role_name, scope='org').first()

        if existing_role:
            existing_role.description = role_descriptions.get(role_name, '')
            existing_role.level = role_levels.get(role_name, None)
            updated_count += 1
            print(f"✓ Updated org role: {role_name}")
        else:
            role = Role(
                name=role_name,
                scope='org',
                description=role_descriptions.get(role_name, ''),
                level=role_levels.get(role_name, None)
            )
            db.session.add(role)
            created_count += 1
            print("+ Created org role: {}".format(role_name))

    try:
        db.session.commit()
        print("\n✅ Role seeding complete!")
        print("   Created: {} roles".format(created_count))
        print("   Updated: {} roles".format(updated_count))
        print("   Total: {} roles processed".format(created_count + updated_count))

    except Exception as e:
        db.session.rollback()
        print("\n❌ Error seeding roles: {}".format(e))
        raise

if __name__ == "__main__":
    seed_roles()
