# app/accommodation/models/__init__.py
"""
Accommodation Models - Export all models with namespaced enums
"""

# Property models
from app.accommodation.models.property import (
    Property,
    AccommodationPropertyType,
    AccommodationCancellationPolicy,
    AccommodationPropertyStatus,
    AccommodationVerificationStatus,
    PropertyPhoto,
    Amenity,
    PropertyAmenity,
    PropertyRule,
)

# Booking models
from app.accommodation.models.booking import (
    AccommodationBooking,
    AccommodationBookingStatus,
    AccommodationPaymentStatus,
    AccommodationPaymentMethod,
    BookingStatusHistory,
)

# Availability models
from app.accommodation.models.availability import (
    BlockedDate,
    AvailabilityRule,
    AccommodationBlockedReason,
    is_date_available,
    get_available_dates,
    block_dates,
    unblock_dates,
)

# Review models
from app.accommodation.models.review import Review, AccommodationReviewStatus

__all__ = [
    # Property
    'Property',
    'AccommodationPropertyType',
    'AccommodationCancellationPolicy',
    'AccommodationPropertyStatus',
    'AccommodationVerificationStatus',
    'PropertyPhoto',
    'Amenity',
    'PropertyAmenity',
    'PropertyRule',
    # Booking
    'AccommodationBooking',
    'AccommodationBookingStatus',
    'AccommodationPaymentStatus',
    'AccommodationPaymentMethod',
    'BookingStatusHistory',
    # Availability
    'BlockedDate',
    'AvailabilityRule',
    'AccommodationBlockedReason',
    'is_date_available',
    'get_available_dates',
    'block_dates',
    'unblock_dates',
    # Review
    'Review',
    'AccommodationReviewStatus',
    'BookingContextType'
]