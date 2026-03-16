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

# Import and register owner blueprint
from app.admin.owner import owner_bp
admin_bp.register_blueprint(owner_bp)

# Future admin types - COMMENT OUT until they exist
# from app.admin.super_admin import super_admin_bp
# admin_bp.register_blueprint(super_admin_bp)

# Import route modules so they register with admin_bp
from app.admin import routes  # noqa: F401,E402