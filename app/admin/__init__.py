# app/admin/__init__.py
"""
Admin module - General administration and Owner oversight
"""

from flask import Blueprint

# Main admin blueprint
admin_bp = Blueprint(
    "admin",
    __name__,
    url_prefix="/admin",
    template_folder="templates"
)

# Import regular admin routes
from app.admin import routes

# Register owner blueprint as a child of admin
from app.admin.owner import owner_bp
admin_bp.register_blueprint(owner_bp)

# Import models for Alembic to track
from app.admin import models  # noqa: F401

# Import route modules so they register with admin_bp
from app.admin import routes  # noqa: F401,E402

__all__ = ["admin_bp"]
