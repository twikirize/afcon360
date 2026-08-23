# app/events/__init__.py
"""
Events Module - top-level blueprint for AFCON360.

Peer modules:
  - accommodation
  - transport
  - wallet
  - tourism

This module owns event creation, registration, payment, moderation,
coordination/assignment, settings, and community-host compatibility routes.
"""

import logging

from flask import Blueprint

logger = logging.getLogger(__name__)

# Create the single top-level events blueprint.
events_bp = Blueprint('events', __name__, url_prefix='/events')


# ---------------------------------------------------------------------------
# Bulk registration blueprint
# ---------------------------------------------------------------------------
# The canonical module is app/events/bulk_registration.py.
# A compatibility import is kept for older deployments that still have
# app/events/bulk_upload.py.
try:
    from app.events.bulk_registration import bulk_bp
except ImportError:
    from app.events.bulk_upload import bulk_bp

events_bp.register_blueprint(bulk_bp)


# ---------------------------------------------------------------------------
# Coordination/assignment blueprint
# ---------------------------------------------------------------------------
# The canonical module is app/events/routes/assignment.py.
# A compatibility import is kept for deployments that have it at the top level.
try:
    from app.events.routes.assignment import assignment_bp
except ImportError:
    from app.events.assignment import assignment_bp

events_bp.register_blueprint(assignment_bp, name_prefix='')

# Guest management / journey / communication blueprint (Event Guest Operations)
from app.events.guest_management import guest_management_bp

events_bp.register_blueprint(guest_management_bp, name_prefix='')


# ---------------------------------------------------------------------------
# Settings routes
# ---------------------------------------------------------------------------
# Settings routes are registered before the main event routes so that the
# admin settings endpoints are available during app startup.
from app.events.settings_routes import register_settings_routes

register_settings_routes(events_bp)
logger.info("Events settings routes registered")


# ---------------------------------------------------------------------------
# Event-manager quick-action admin pages (registrations / organizers /
# ticketing / analytics)
# ---------------------------------------------------------------------------
from app.events.admin_pages import register_admin_pages

register_admin_pages(events_bp)
logger.info("Events admin pages registered")


# ---------------------------------------------------------------------------
# Main event routes and compatibility route modules
# ---------------------------------------------------------------------------
from app.events import routes  # noqa: E402,F401
from app.events import routes_community_hosts  # noqa: E402,F401
from app.events import routes_accommodation  # noqa: E402,F401
from app.events import routes_organizer  # noqa: E402,F401
from app.events.api import event_favorites_api_bp  # noqa: E402,F401


# ---------------------------------------------------------------------------
# Model imports
# ---------------------------------------------------------------------------
# Keep Alembic aware of payment configuration models where they are attached
# to this module.  The payment_config module is a compatibility re-export and
# does not own schema.
from app.events import payment_config  # noqa: E402,F401


# ---------------------------------------------------------------------------
# Signal handlers
# ---------------------------------------------------------------------------
# Connect signal handlers once when this blueprint is registered with the app.
# This avoids module-level Flask current_app access outside an app context.
try:
    from app.events.signal_handlers import connect_event_signal_handlers

    @events_bp.record_once
    def on_load(state):
        """Connect event signal handlers after the app context exists."""
        with state.app.app_context():
            try:
                connect_event_signal_handlers()
                state.app.logger.info(
                    "Events module signal handlers connected"
                )
            except Exception as exc:
                state.app.logger.error(
                    "Failed to connect event signal handlers: %s",
                    exc,
                )

    __all__ = [
        'events_bp',
        'event_favorites_api_bp',
        'assignment_bp',
        'routes',
        'connect_event_signal_handlers',
    ]
except ImportError as exc:
    logger.error("Failed to import event signal handlers: %s", exc)
    __all__ = [
        'events_bp',
        'event_favorites_api_bp',
        'assignment_bp',
        'routes',
    ]


# ---------------------------------------------------------------------------
# Moderator registry
# ---------------------------------------------------------------------------
# Register the Events module in the moderation review registry.
try:
    from app.admin.moderator.registry import register_module
    from flask import url_for

    register_module(
        'event',
        'Event',
        review_url_fn=lambda id: url_for('events.moderate_detail', id=id),
        module_name='Events',
        icon='fa-calendar',
    )
except Exception as exc:
    logger.warning("Moderator registry registration failed: %s", exc)