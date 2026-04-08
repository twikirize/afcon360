# app/admin/owner/__init__.py
from flask import Blueprint

# Create owner blueprint
owner_bp = Blueprint(
    'owner',
    __name__,
    url_prefix='/owner',
    template_folder='templates'
)

# Import routes
from app.admin.owner import routes
