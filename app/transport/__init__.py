# app/transport/__init__.py
"""
AFCON360 – Transport Module
Responsible for:
- Transport blueprint registration
- Ensuring transport models are visible to Alembic
- Initializing transport-related services
"""

from flask import Blueprint
import logging

# -------------------------------------------------------------------
# Blueprints (created at module level — safe, no circular imports)
# -------------------------------------------------------------------

transport_bp = Blueprint(
    "transport",
    __name__,
    url_prefix="/transport",
    template_folder="templates",
    static_folder="static",
)

transport_admin_bp = Blueprint(
    "transport_admin",
    __name__,
    url_prefix="/transport/admin",
    template_folder="templates"
)
logger = logging.getLogger("transport")

# -------------------------------------------------------------------
# Models — imported here so Alembic can detect them
# Safe because models only import from app.extensions (db)
# -------------------------------------------------------------------
from app.transport import models  # noqa: F401

# -------------------------------------------------------------------
# Service getters — lazy singletons, safe to import at module level
# -------------------------------------------------------------------
from app.transport.services import (
    get_provider_service,
    get_booking_service,
    get_dashboard_service,
    get_matching_service,
    get_payment_service,
    get_tracking_service,
    get_notification_service,
    get_promotion_service,
    get_external_platforms,
    get_settings_service,
    init_provider_service,
)

# -------------------------------------------------------------------
# Module initialization hook — called from create_app()
# Routes and API are imported HERE to avoid circular imports.
# By the time this runs, blueprints exist and Flask app is ready.
# -------------------------------------------------------------------

def init_transport_module(app):
    """
    Initialize Transport module services and register all routes.
    Must be called from create_app() AFTER blueprints are registered.
    """
    # 1. Initialize services (order matters — provider first)
    init_provider_service()
    get_dashboard_service()
    get_booking_service()
    get_matching_service()
    get_payment_service()
    get_tracking_service()
    get_notification_service()
    get_promotion_service()
    get_external_platforms()
    get_settings_service()

    # 2. Import web routes (registers @transport_bp.route decorators)
    #    This is safe here because blueprints already exist above.
    from app.transport import routes  # noqa: F401

    # 3. Initialize REST API (registers all Flask-RESTful resources)
    #    init_api() handles its own internal imports to avoid cycles.
    from app.transport.api import init_api
    init_api(app)

    app.logger.info("✅ Transport module initialized")


# -------------------------------------------------------------------
# Utility helpers
# -------------------------------------------------------------------
def paginate(query, page=1, per_page=25):
    """
    Helper to paginate a SQLAlchemy query safely.
    Usage:
        paginated = paginate(User.query, page=2, per_page=20)
    Returns a Pagination object with .items, .total, .pages, etc.
    """
    # limit per_page to 100
    per_page = min(per_page, 100)
    page = max(page, 1)
    return query.paginate(page=page, per_page=per_page, error_out=False)


# -------------------------------------------------------------------
# Public exports
# -------------------------------------------------------------------
__all__ = [
    "transport_bp",
    "transport_admin_bp",
    "init_transport_module",
    "get_provider_service",
    "get_booking_service",
    "get_matching_service",
    "get_payment_service",
    "get_tracking_service",
    "get_notification_service",
    "get_promotion_service",
    "get_external_platforms",
    "get_settings_service",
    "paginate"
]