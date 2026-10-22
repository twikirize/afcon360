"""
CLI maintenance commands for AFCON360 application.
"""
import click
import secrets
import string
from flask import current_app


def _random_password(length: int = 16) -> str:
    """Generate a cryptographically random password."""
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
    return "".join(secrets.choice(alphabet) for _ in range(length))


@click.command()
@click.option(
    "--password",
    default=None,
    help="Password to set for all created test users. If omitted, a random password is generated and printed once.",
)
def create_test_users(password):
    """Create test users for development with proper password hashing."""
    with current_app.app_context():
        from app.extensions import db
        from app.identity.models.user import User
        from app.auth.roles import assign_global_role

        # Generate password if not provided
        if password is None:
            password = _random_password()
            click.echo(f"🔐 Generated random password: {password}")
            click.echo("⚠️  This password will not be shown again. Store it securely.")
        else:
            click.echo("🔐 Using provided password.")

        test_users = [
            ("owner", "owner@afcon360.com", "owner"),
            ("superadmin", "superadmin@afcon360.com", "super_admin"),
            ("admin", "admin@afcon360.com", "admin"),
            ("eventadmin", "events@afcon360.com", "event_admin"),
            ("transportadmin", "transport@afcon360.com", "transport_admin"),
            ("walletadmin", "wallet@afcon360.com", "wallet_admin"),
            ("testuser", "user@afcon360.com", "user"),
        ]

        for username, email, role in test_users:
            # Check if user exists
            existing_user = User.query.filter_by(username=username).first()
            if existing_user:
                click.echo(f"✓ User {username} already exists")
                continue

            # Create user with password
            user = User(
                username=username,
                email=email,
                is_active=True,
                is_verified=True,
            )
            user.set_password(password)
            db.session.add(user)
            db.session.flush()  # Get the ID

            # Assign role
            assign_global_role(user.id, role)
            click.echo(f"+ Created user: {username} with role: {role}")

        db.session.commit()
        click.echo("\n✅ Test users created successfully!")


@click.command()
def list_routes():
    """List all application routes grouped by blueprint."""
    with current_app.app_context():
        click.echo("\n📋 Available Routes:")
        click.echo("=" * 50)

        # Group routes by blueprint
        routes = {}
        for rule in current_app.url_map.iter_rules():
            blueprint = rule.endpoint.split(".")[0] if "." in rule.endpoint else "app"
            if blueprint not in routes:
                routes[blueprint] = []
            routes[blueprint].append(f"  {rule.rule:30} -> {rule.endpoint}")

        for blueprint, route_list in sorted(routes.items()):
            click.echo(f"\n📁 {blueprint.upper()}:")
            for route in sorted(route_list):
                click.echo(route)


def register_maintenance_commands(app):
    """Register maintenance CLI commands with Flask app."""
    app.cli.add_command(create_test_users, name="create-test-users")
    app.cli.add_command(list_routes, name="list-routes")