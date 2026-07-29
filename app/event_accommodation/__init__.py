# app/event_accommodation/__init__.py
"""
Event Accommodation Module Blueprint and Integration
"""

from flask import Blueprint

event_accommodation_bp = Blueprint(
    "event_accommodation",
    __name__,
    url_prefix="/event-accommodation"
)

from app.event_accommodation.models import badge, opportunity, visibility
