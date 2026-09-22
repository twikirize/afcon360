# app/geo/__init__.py
"""
AFCON360 - GEO Platform Module (independent, domain-neutral).

Ownership boundary:
    Transport / Accommodation / Events / Tourism / Booking-Discovery
        ──→ GEO (geographic infrastructure only)

GEO owns geographic operations (validation, distance, routing, geocoding,
nearby, tiles/map adapters, realtime delivery, history infrastructure).
GEO MUST NOT own business records of other modules (drivers, properties,
events, wallets, bookings).

Conventions followed:
- Blueprint created at module level (safe), routes imported lazily inside
  init_geo_module() to avoid circular imports (same pattern as tourism).
- Deep-lazy service getters (same pattern as transport/__init__.py).
- Absolute imports from project root.
"""

from flask import Blueprint

geo_bp = Blueprint(
    "geo",
    __name__,
    url_prefix="/geo",
    template_folder="templates",
    static_folder="static",
)

# DO NOT import routes here - causes circular import and app context issues.
# Routes are imported when the blueprint is registered in app factory.


def get_location_service():
    from app.geo.services import get_location_service as get
    return get()


def get_routing_service():
    from app.geo.services import get_routing_service as get
    return get()


def get_geocoding_service():
    from app.geo.services import get_geocoding_service as get
    return get()


def init_geo_module(app):
    """
    Initialize GEO platform module: import routes (registers @geo_bp.route
    decorators). No provider network calls, no schema changes.
    """
    from app.geo import routes  # noqa: F401

    app.logger.info("GEO module initialized (Deep Lazy)")


__all__ = [
    "geo_bp",
    "init_geo_module",
    "get_location_service",
    "get_routing_service",
    "get_geocoding_service",
]
