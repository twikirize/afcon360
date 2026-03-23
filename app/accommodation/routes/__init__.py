# app/accommodation/routes/__init__.py
"""
Accommodation Routes - Sub-blueprints for different user types
"""

from flask import Blueprint

# Create sub-blueprints
guest = Blueprint('accommodation_guest', __name__, url_prefix='/guest')
host = Blueprint('accommodation_host', __name__, url_prefix='/host')
admin = Blueprint('accommodation_admin', __name__, url_prefix='/admin')

# Import route modules (these will populate the blueprints)

from app.accommodation.routes import guest_routes, host_routes, admin_routes

# Export
__all__ = ['guest', 'host', 'admin']

