# App/admin/owner/__init__.py
from flask import Blueprint

# Create owner blueprint
owner_bp = Blueprint(
    'owner',
    __name__,
    url_prefix='/owner',
    template_folder='templates'  # Points to app/admin/owner/templates
)

# Import routes - DO NOT import owner_bp again!
from app.admin.owner import routes  # This imports the routes, not the blueprint