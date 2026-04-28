# app/transport/__init__.py
"""
AFCON360 – Transport Module
"""

from flask import Blueprint
import logging

# -------------------------------------------------------------------
# Blueprints — created at module level (safe)
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
# Lazy Service Getters
# -------------------------------------------------------------------

def get_provider_service():
    from app.transport.services.provider_service import get_provider_service as get
    return get()

def get_booking_service():
    from app.transport.services.booking_service import get_booking_service as get
    return get()

def get_dashboard_service():
    from app.transport.services.dashboard_service import get_dashboard_service as get
    return get()

def get_matching_service():
    from app.transport.services.matching_service import get_matching_service as get
    return get()

def get_payment_service():
    from app.transport.services.payment_service import get_payment_service as get
    return get()

def get_tracking_service():
    from app.transport.services.tracking_service import get_tracking_service as get
    return get()

def get_notification_service():
    from app.transport.services.notification_service import get_notification_service as get
    return get()

def get_promotion_service():
    from app.transport.services.promotion_service import get_promotion_service as get
    return get()

def get_external_platforms():
    from app.transport.services.external_platforms import get_external_platforms as get
    return get()

def get_settings_service():
    from app.transport.services.settings_service import get_settings_service as get
    return get()

def init_provider_service():
    from app.transport.services.provider_service import init_provider_service as init
    return init()

# -------------------------------------------------------------------
# Module initialization hook
# -------------------------------------------------------------------

def init_transport_module(app):
    """
    Initialize Transport module services and register all routes.
    """
    # 1. Models — imported here so they are registered with SQLAlchemy
    # but only when the module is actually initialized.
    from app.transport import models  # noqa: F401

    # 2. Import web routes (registers @transport_bp.route decorators)
    from app.transport import routes  # noqa: F401

    # 3. Initialize REST API
    from app.transport.api import init_api
    init_api(app)

    app.logger.info("✅ Transport module initialized (Deep Lazy)")


def paginate(query, page=1, per_page=25):
    per_page = min(per_page, 100)
    page = max(page, 1)
    return query.paginate(page=page, per_page=per_page, error_out=False)

__all__ = [
    "transport_bp",
    "transport_admin_bp",
    "init_transport_module",
    "get_provider_service",
    "get_booking_service",
    "get_matching_service",
    "get_payment_service",
    "get_tracking_service",
    "get_notification_status",
    "get_promotion_service",
    "get_external_platforms",
    "get_settings_service",
    "paginate"
]

try:
    from app.admin.moderation.registry import register_module
    register_module("transport", "Transport", lambda eid: f"/transport/admin/{eid}")
except Exception:
    pass
