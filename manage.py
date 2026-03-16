from app import create_app
from app.extensions import db
from flask_migrate import Migrate
import click

app = create_app()
migrate = Migrate(app, db)


@app.cli.command("seed-roles")
def seed_roles():
    """Create all default roles in the database."""
    from app.auth.seed import seed_roles as do_seed

    do_seed()
    print("✅ Roles seeded successfully")


@app.cli.command("assign-role")
@click.argument("username")
@click.argument("role")
def assign_role(username, role):
    """
    Assign a role to a user.

    Usage:
        flask assign-role OBED super_admin
    """
    from app.identity.models.user import User
    from app.auth.roles import assign_global_role

    user = User.query.filter_by(username=username).first()

    if not user:
        print(f"❌ User '{username}' not found")
        return

    assign_global_role(user_id=user.id, role_name=role)
    db.session.commit()

    print(f"✅ Role '{role}' assigned to '{username}'")
    print(f"   Current roles: {user.role_names}")


@app.cli.command("list-roles")
@click.argument("username")
def list_roles(username):
    """
    List roles for a user.

    Usage:
        flask list-roles OBED
    """
    from app.identity.models.user import User

    user = User.query.filter_by(username=username).first()

    if not user:
        print(f"❌ User '{username}' not found")
        return

    print(f"Roles for '{username}': {user.role_names}")


if __name__ == "__main__":
    app.run()