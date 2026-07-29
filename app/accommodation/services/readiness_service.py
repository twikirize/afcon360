# app/accommodation/services/readiness_service.py
"""
Accommodation Readiness Service - Validates operational prerequisites before a property can be publicly booked.
"""

from typing import Tuple, List
from app.accommodation.models.property import Property

class AccommodationReadinessService:
    """Validates property setup readiness for booking."""

    @staticmethod
    def check_readiness(property: Property) -> Tuple[bool, List[str]]:
        """
        Validates all property operational prerequisites.
        Returns (can_be_booked, failure_reasons).
        """
        failures = []

        # 1. Address check
        if not property.address_line1 or not property.city or not property.country:
            failures.append("Incomplete address information (street, city, and country are required).")

        # 2. Photos check
        if not property.main_image and (not property.gallery or len(property.gallery) == 0):
            failures.append("At least one main photo or gallery image is required.")

        # 3. Pricing check
        if not property.base_price_per_night or property.base_price_per_night <= 0:
            failures.append("Base price per night must be set and greater than zero.")

        # 4. Capacity check
        if not property.max_guests or property.max_guests < 1:
            failures.append("Maximum guests capacity must be at least 1.")

        # 5. Policies check
        if not property.cancellation_policy:
            failures.append("Cancellation policy must be configured.")

        # 6. Status check
        if property.status in ["suspended", "archived", "rejected"]:
            failures.append(f"Property status '{property.status}' does not allow public booking.")

        can_be_booked = (len(failures) == 0)
        return can_be_booked, failures
