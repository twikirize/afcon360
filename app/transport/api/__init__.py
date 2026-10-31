# app/transport/api/__init__.py - REFACTORED (initialization only)
"""
AFCON360 Transport - REST API
Creates blueprint and API instance, then delegates registration to routes.py
"""

from flask import Blueprint
from flask_restful import Api


def init_api(app):
    """
    Initialize the REST API.
    Delegates resource registration to routes.py.
    """
    # Create a fresh blueprint and Api instance per-app to ensure there is no
    # cross-app state.
    api_bp = Blueprint("transport_api", __name__, url_prefix="/api/transport")

    # Defensive: if this blueprint name is already registered on the target app,
    # skip initialization (idempotent).
    if api_bp.name in app.blueprints:
        app.logger.info("Transport API blueprint already registered on app; skipping init_api")
        return

    api = Api(api_bp)

    # Import and call the registration function from routes.py
    from .routes import register_api_resources
    register_api_resources(api)

    # Register blueprint with the app
    app.register_blueprint(api_bp)

    app.logger.info("✅ Transport API initialized - /api/transport/* routes live")