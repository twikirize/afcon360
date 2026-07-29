# app/event_accommodation/services/matching_service.py
"""
Matching Service - Matches eligible verified properties with event accommodation opportunities.
"""

from typing import List
from app.accommodation.models.property import Property
from app.event_accommodation.models.opportunity import EventAccommodationOpportunity

class MatchingService:
    """Service for matching properties to event opportunities."""

    @staticmethod
    def find_matching_properties(opportunity: EventAccommodationOpportunity) -> List[Property]:
        """Finds active, verified properties matching an event opportunity location and criteria."""
        query = Property.query.filter_by(status="active", is_verified=True, is_active=True)
        
        if opportunity.location:
            query = query.filter(Property.city.ilike(f"%{opportunity.location}%"))
            
        properties = query.all()
        matched = []
        for prop in properties:
            # Check capacity
            if opportunity.required_beds and prop.max_guests < opportunity.required_beds:
                continue
            # Check accepted types
            if opportunity.accepted_property_types and prop.property_type not in opportunity.accepted_property_types:
                continue
            matched.append(prop)
            
        return matched
