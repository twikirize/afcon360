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

# Register settings routes
from app.owner.routes.settings import owner_settings
owner_bp.register_blueprint(owner_settings)

# Register escrow routes
from app.admin.owner.escrow_routes import escrow_bp
owner_bp.register_blueprint(escrow_bp)

# Register backup & restore routes
from app.admin.owner.backup_routes import owner_backup_bp
owner_bp.register_blueprint(owner_backup_bp)
