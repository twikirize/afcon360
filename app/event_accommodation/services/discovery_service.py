# app/event_accommodation/services/discovery_service.py
"""
Discovery Service - Handles event marketplace discovery and public vs event marketplace visibility rules.
"""

from typing import List
from app.accommodation.models.property import Property
from app.event_accommodation.services.badge_service import BadgeService

class DiscoveryService:
    """Service for discovering public and event-specific accommodation listings."""

    @staticmethod
    def get_public_properties() -> List[Property]:
        """Returns properties eligible for public marketplace discovery."""
        return Property.query.filter_by(
            status="active",
            is_verified=True,
            is_active=True,
            is_publicly_visible=True
        ).filter(Property.visibility.in_(["public"])).all()

    @staticmethod
    def get_event_properties(event_id: int) -> List[Property]:
        """Returns properties discoverable for a specific event based on active valid badges."""
        all_active = Property.query.filter_by(
            status="active",
            is_verified=True,
            is_active=True
        ).all()

        event_properties = []
        for prop in all_active:
            if BadgeService.validate_badge(event_id, prop.id):
                event_properties.append(prop)

        return event_properties
