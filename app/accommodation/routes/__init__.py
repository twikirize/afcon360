# app/accommodation/routes/__init__.py
"""
Accommodation Routes - Sub-blueprints
"""

from flask import Blueprint

# Define blueprints
guest = Blueprint('accommodation_guest', __name__)
host = Blueprint('accommodation_host', __name__)
admin = Blueprint('accommodation_admin', __name__)
event = Blueprint('accommodation_event', __name__)

# Import route files (these attach routes to blueprints)
from app.accommodation.routes import guest_routes, host_routes, admin_routes

# NOTE:
# Do NOT import event_routes here (avoid circular imports)

__all__ = ['guest', 'host', 'admin', 'event']