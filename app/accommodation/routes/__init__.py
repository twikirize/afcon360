# app/accommodation/routes/__init__.py
"""
Accommodation Routes - Sub-blueprints
"""

from flask import Blueprint

# Import blueprint instances from their respective files
from .guest_routes import guest_bp as guest
from .host_routes import host_bp as host
from .admin_routes import admin_bp as admin

# No longer needed as event routes are not defined here
# event = Blueprint('accommodation_event', __name__)

__all__ = ['guest', 'host', 'admin']
