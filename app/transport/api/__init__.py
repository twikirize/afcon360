# app/transport/api/__init__.py - REFACTORED (initialization only)
"""
AFCON360 Transport — REST API
Creates blueprint and API instance, then delegates registration to routes.py
"""

from flask import Blueprint
from flask_restful import Api

# -------------------------------------------------------------------
# API Blueprint — url prefix: /api/transport/...
# -------------------------------------------------------------------
api_bp = Blueprint("transport_api", __name__, url_prefix="/api/transport")
api = Api(api_bp)


def init_api(app):
    """
    Initialize the REST API.
    Delegates resource registration to routes.py.
    """
    # Import and call the registration function from routes.py
    from .routes import register_api_resources
    register_api_resources(api)

    # Register blueprint with the app
    app.register_blueprint(api_bp)

    app.logger.info("✅ Transport API initialized — /api/transport/* routes live")
