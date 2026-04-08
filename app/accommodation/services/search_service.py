# app/accommodation/services/search_service.py
"""
Search service - Handles property search and retrieval
Phase 1: Mixed mode (hardcoded + DB fallback)
"""

from typing import List, Dict, Optional
from flask import current_app
# FIX 1: Was `PropertyStatus` — that name does not exist. Correct name is AccommodationPropertyStatus.
# This bad import was the root cause of the duplicate-table crash on startup.
from app.accommodation.models.property import Property, AccommodationPropertyStatus
import logging

logger = logging.getLogger(__name__)

# Hardcoded data for fallback (keeps existing functionality)
HARDCODED_PROPERTIES = [
    {
        "id": 1,
        "slug": "central-hotel",
        "name": "Central Hotel",
        "price": 80,
        "currency": "USD",
        "summary": "Close to the stadium",
        "description": "Conveniently located near the main stadium, Central Hotel offers comfortable rooms with modern amenities. Perfect for football fans.",
        "city": "Kampala",
        "address": "123 Main Street",
        "max_guests": 2,
        "bedrooms": 1,
        "beds": 1,
        "bathrooms": 1,
        "images": [],
        "rating": 4.5,
        "reviews": 23
    },
    {
        "id": 2,
        "slug": "riverside-lodge",
        "name": "Riverside Lodge",
        "price": 60,
        "currency": "USD",
        "summary": "Peaceful riverside location",
        "description": "Relax by the river at this peaceful lodge. Enjoy nature while being close to the city.",
        "city": "Jinja",
        "address": "45 River Road",
        "max_guests": 4,
        "bedrooms": 2,
        "beds": 2,
        "bathrooms": 1,
        "images": [],
        "rating": 4.2,
        "reviews": 15
    },
]


def search_properties(city: Optional[str] = None,
                      check_in: Optional[str] = None,
                      check_out: Optional[str] = None,
                      guests: int = 2) -> List[Dict]:
    """
    Search for properties with filters.
    Returns list of property dicts for display.
    """
    try:
        # Try to get from database
        query = Property.query.filter(
            Property.status == AccommodationPropertyStatus.ACTIVE,  # FIX 1 applied here
            Property.is_verified == True,
            Property.is_deleted == False,
            Property.is_active == True
        )

        if city:
            query = query.filter(Property.city.ilike(f'%{city}%'))

        if guests:
            query = query.filter(Property.max_guests >= guests)

        properties = query.limit(50).all()

        if properties:
            return [_property_to_dict(p) for p in properties]

    except Exception as e:
        # Database not ready or error - use hardcoded
        logger.warning(f"DB search failed, using hardcoded data: {e}")

    # Fallback to hardcoded
    results = HARDCODED_PROPERTIES.copy()
    if city:
        results = [p for p in results if p["city"].lower() == city.lower()]
    if guests:
        results = [p for p in results if p["max_guests"] >= guests]

    return results


def get_property_by_identifier(identifier: str) -> Optional[Dict]:
    """
    Get a single property by ID or slug.
    """
    try:
        # Try to get from database
        if identifier.isdigit():
            prop = Property.query.get(int(identifier))
        else:
            prop = Property.query.filter_by(slug=identifier).first()

        if prop and prop.status == AccommodationPropertyStatus.ACTIVE and prop.is_verified:  # FIX 1 applied here
            return _property_to_dict(prop)

    except Exception as e:
        logger.warning(f"DB lookup failed, using hardcoded: {e}")

    # Fallback to hardcoded
    for p in HARDCODED_PROPERTIES:
        if str(p["id"]) == identifier or p["slug"] == identifier:
            return p.copy()

    return None


# app/accommodation/services/search_service.py

def _property_to_dict(property: Property) -> Dict:
    """Convert Property model to dict for API/templates"""
    return {
        "id": property.id,
        "slug": property.slug,
        "name": property.title,
        "price": float(property.base_price_per_night),
        "currency": property.currency,
        "summary": property.summary or property.description[:100],
        "description": property.description,
        "city": property.city,
        "country": property.country,
        "address": property.address_line1,
        "max_guests": property.max_guests,
        "bedrooms": property.bedrooms,
        "beds": property.beds,
        "bathrooms": property.bathrooms,
        "images": property.gallery or [property.main_image] if property.main_image else [],
        "rating": float(property.overall_rating) if property.overall_rating else None,
        "reviews": property.total_reviews,
        "amenities": [a.amenity.name for a in property.amenities] if property.amenities else [],
        "house_rules": property.house_rules,
        "check_in_time": property.check_in_time,
        "check_out_time": property.check_out_time,
        "cancellation_policy": property.cancellation_policy.value if property.cancellation_policy else None,
        "min_stay_nights": property.min_stay_nights,
        "instant_book": property.instant_book
    }

# Keep old function names for backward compatibility
def list_hotels():
    """Legacy function - returns hardcoded hotels"""
    return HARDCODED_PROPERTIES


def get_hotel(hotel_id):
    """Legacy function - gets hardcoded hotel"""
    return get_property_by_identifier(str(hotel_id))
