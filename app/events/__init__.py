# app/events/__init__.py
"""
Events Module — top-level blueprint for AFCON360.
Peer to: accommodation, transport, wallet, tourism.
"""
from flask import Blueprint, current_app

# Create single blueprint
events_bp = Blueprint('events', __name__, url_prefix='/events')

# ✅ STEP 1: Register settings routes FIRST (before importing routes)
from app.events.settings_routes import register_settings_routes
register_settings_routes(events_bp)
print("✅ Settings routes registered to events blueprint")  # Debug line

# ✅ STEP 2: Now import routes (which will add the rest of the routes)
from app.events import routes
from app.events.settings_model import EventSettings  # noqa: F401

# Expose service for easier imports
from app.events.services import EventService

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

    __all__ = ['events_bp', 'EventService', 'routes', 'connect_event_signal_handlers']
except ImportError as e:
    current_app.logger.error(f"Failed to import event signal handlers: {e}")
    __all__ = ['events_bp', 'EventService', 'routes']

try:
    from app.admin.moderation.registry import register_module
    register_module("event", "Events", lambda eid: f"/events/{eid}")
except Exception:
    pass
