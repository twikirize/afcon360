# app/cli/__init__.py
from app.cli.owner import register_owner_commands
from app.auth.seed_roles import register_commands as register_seed_commands


def register_all_commands(app):
    """Register all CLI commands."""
    register_owner_commands(app)
    register_seed_commands(app)  # Add this line
