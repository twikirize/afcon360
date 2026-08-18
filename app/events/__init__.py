# app/events/__init__.py
"""
Events Module - top-level blueprint for AFCON360.
Peer to: accommodation, transport, wallet, tourism.
"""
from flask import Blueprint, current_app
from app.events.bulk_upload import bulk_bp

# Create single blueprint
events_bp = Blueprint('events', __name__, url_prefix='/events')
events_bp.register_blueprint(bulk_bp)

# Coordination routes are part of the Event boundary, but remain in their own
# blueprint so the service is the single implementation for assignment actions.
from app.events.assignment import assignment_bp
events_bp.register_blueprint(assignment_bp, name_prefix='')

# STEP 1: Register settings routes FIRST (before importing routes)
from app.events.settings_routes import register_settings_routes
register_settings_routes(events_bp)
print("Settings routes registered to events blueprint")  # Debug line

# STEP 2: Now import routes (which will add the rest of the routes)
from app.events import routes
from app.events import routes_community_hosts
from app.events import routes_accommodation  # noqa: F401 - registers compatibility routes
from app.events.api import event_favorites_api_bp

# IMPORTANT: Force Alembic to see these models so it doesn't drop the tables
from app.events import payment_config  # noqa: F401

# Import signal handlers and connect them
try:
    from app.events.signal_handlers import connect_event_signal_handlers

    @events_bp.record_once
    def on_load(state):
        """Called when the blueprint is registered with the app"""
        with state.app.app_context():
            try:
                connect_event_signal_handlers()
                state.app.logger.info("Events module signal handlers connected")
            except Exception as e:
                state.app.logger.error(f"Failed to connect event signal handlers: {e}")

    __all__ = ['events_bp', 'event_favorites_api_bp', 'assignment_bp', 'routes', 'connect_event_signal_handlers']
except ImportError as e:
    current_app.logger.error(f"Failed to import event signal handlers: {e}")
    __all__ = ['events_bp', 'event_favorites_api_bp', 'assignment_bp', 'routes']

try:
    from app.admin.moderator.registry import register_module
    from flask import url_for
    register_module('event', 'Event',
                   review_url_fn=lambda id: url_for('events.moderate_detail', id=id),
                   module_name='Events', icon='fa-calendar')
except Exception:
    pass