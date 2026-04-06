# app/events/__init__.py
"""
Events Module — top-level blueprint for AFCON360.
Peer to: accommodation, transport, wallet, tourism.
"""
from flask import Blueprint

# Create single blueprint
events_bp = Blueprint('events', __name__, url_prefix='/events')

# Import routes directly
from app.events import routes

# Expose service for easier imports
from app.events.services import EventService

__all__ = ['events_bp', 'EventService']