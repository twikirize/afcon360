# app/cli.py
"""
CLI commands for AFCON360 application
"""
import click
from flask import current_app
from app.extensions import db
from app.auth.seed_roles import seed_roles

@click.command()
@click.option('--force', is_flag=True, help='Force recreate all roles')
def seed_roles_command(force):
    """Seed all roles in the database"""
    with current_app.app_context():
        if force:
            # Delete existing roles
            from app.identity.models.roles_permission import Role
            Role.query.delete()
            db.session.commit()
            print("🗑️  Cleared existing roles")

        seed_roles()

def register_cli_commands(app):
    """Register CLI commands with Flask app"""
    app.cli.add_command(seed_roles_command, name='seed-roles')

# Add more CLI commands as needed
@click.command()
def create_test_users():
    """Create test users for development"""
    with current_app.app_context():
        from app.identity.models.user import User
        from app.auth.roles import assign_global_role

        test_users = [
            ('owner', 'owner@afcon360.com', 'owner'),
            ('superadmin', 'superadmin@afcon360.com', 'super_admin'),
            ('admin', 'admin@afcon360.com', 'admin'),
            ('eventmanager', 'events@afcon360.com', 'event_manager'),
            ('transportadmin', 'transport@afcon360.com', 'transport_admin'),
            ('walletadmin', 'wallet@afcon360.com', 'wallet_admin'),
            ('testuser', 'user@afcon360.com', 'user'),
        ]

        for username, email, role in test_users:
            # Check if user exists
            existing_user = User.query.filter_by(username=username).first()
            if existing_user:
                print(f"✓ User {username} already exists")
                continue

            # Create user (you'll need to set a password separately)
            user = User(
                username=username,
                email=email,
                is_active=True,
                is_verified=True
            )
            db.session.add(user)
            db.session.flush()  # Get the ID

            # Assign role
            assign_global_role(user.id, role)
            print(f"+ Created user: {username} with role: {role}")

        db.session.commit()
        print("\n✅ Test users created successfully!")
        print("⚠️  Remember to set passwords for these users!")

@click.command()
def list_routes():
    """List all application routes"""
    from flask import url_for

    with current_app.app_context():
        print("\n📋 Available Routes:")
        print("=" * 50)

        # Group routes by blueprint
        routes = {}
        for rule in current_app.url_map.iter_rules():
            blueprint = rule.endpoint.split('.')[0] if '.' in rule.endpoint else 'app'
            if blueprint not in routes:
                routes[blueprint] = []
            routes[blueprint].append(f"  {rule.rule:30} -> {rule.endpoint}")

        for blueprint, route_list in sorted(routes.items()):
            print(f"\n📁 {blueprint.upper()}:")
            for route in sorted(route_list):
                print(route)

def register_all_cli_commands(app):
    """Register all CLI commands"""
    register_cli_commands(app)
    app.cli.add_command(create_test_users, name='create-test-users')
    app.cli.add_command(list_routes, name='list-routes')
