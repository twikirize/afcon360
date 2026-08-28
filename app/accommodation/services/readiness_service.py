# app/accommodation/services/readiness_service.py
"""
Accommodation Readiness Service - Validates operational prerequisites before a property can be publicly booked.
"""

from typing import Tuple, List, Dict, Any
from app.accommodation.models.property import Property
from app.accommodation.models.room import RoomType

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

        # 7. Room type check (NEW)
        active_room_types = [rt for rt in property.room_types if rt.is_active]
        if not active_room_types:
            failures.append("At least one active room type is required.")
        else:
            # Check if room types have valid configuration
            for rt in active_room_types:
                if not rt.max_guests or rt.max_guests < 1:
                    failures.append(f"Room type '{rt.name}' must have max_guests >= 1.")
                if not rt.base_price_per_night or rt.base_price_per_night <= 0:
                    failures.append(f"Room type '{rt.name}' must have a valid base price.")
                if rt.total_units is None or rt.total_units < 1:
                    failures.append(f"Room type '{rt.name}' must have at least 1 unit.")

        can_be_booked = (len(failures) == 0)
        return can_be_booked, failures

    @staticmethod
    def get_completeness_score(property: Property) -> Dict[str, Any]:
        """
        Calculate property completeness as a percentage with detailed breakdown.
        Returns dict with score (0-100), breakdown, and missing items.
        """
        checks = {
            "address": {
                "weight": 15,
                "pass": bool(property.address_line1 and property.city and property.country),
                "label": "Address (street, city, country)"
            },
            "photos": {
                "weight": 15,
                "pass": bool(property.main_image or (property.gallery and len(property.gallery) > 0)),
                "label": "Photos (main image or gallery)"
            },
            "pricing": {
                "weight": 10,
                "pass": bool(property.base_price_per_night and property.base_price_per_night > 0),
                "label": "Base price per night"
            },
            "capacity": {
                "weight": 10,
                "pass": bool(property.max_guests and property.max_guests >= 1),
                "label": "Maximum guests capacity"
            },
            "policies": {
                "weight": 10,
                "pass": bool(property.cancellation_policy),
                "label": "Cancellation policy"
            },
            "status": {
                "weight": 5,
                "pass": property.status not in ["suspended", "archived", "rejected"],
                "label": "Valid status for booking"
            },
            "room_types": {
                "weight": 25,
                "pass": any(rt.is_active for rt in property.room_types),
                "label": "At least one active room type"
            },
            "room_config": {
                "weight": 10,
                "pass": all(
                    rt.max_guests and rt.max_guests >= 1 and
                    rt.base_price_per_night and rt.base_price_per_night > 0 and
                    rt.total_units and rt.total_units >= 1
                    for rt in property.room_types if rt.is_active
                ) if any(rt.is_active for rt in property.room_types) else False,
                "label": "Room types fully configured"
            }
        }

        total_weight = sum(c["weight"] for c in checks.values())
        earned_weight = sum(c["weight"] for c in checks.values() if c["pass"])
        score = int((earned_weight / total_weight) * 100) if total_weight > 0 else 0

        missing = [c["label"] for c in checks.values() if not c["pass"]]
        breakdown = {k: {"weight": v["weight"], "pass": v["pass"], "label": v["label"]} for k, v in checks.items()}

        return {
            "score": score,
            "total_weight": total_weight,
            "earned_weight": earned_weight,
            "breakdown": breakdown,
            "missing": missing,
            "is_ready": score >= 100
        }
