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
    BookingContextType,
)

# Booking Policy models
from app.accommodation.models.booking_policy import PropertyBookingPolicy
from app.accommodation.models.property_payment_method import PropertyPaymentMethod
from app.accommodation.models.booking_payment import AccommodationBookingPayment
from app.accommodation.models.guest_identity import GuestIdentityProfile
from app.accommodation.models.platform_override import PlatformBookingPolicyOverride
from app.accommodation.models.commission import BookingCommission
from app.accommodation.models.host_profile import HostProfile, HostOrganisationProfile
from app.accommodation.models.property_document import PropertyDocument

# Availability models
from app.accommodation.models.availability import (
    BlockedDate,
    RoomHold,
    AvailabilityRule,
    AccommodationBlockedReason,
)

from app.accommodation.models.guest_registration import GuestRegistration

# Review models
from app.accommodation.models.review import Review, AccommodationReviewStatus
from app.accommodation.models.room import RoomType, Room, RoomBooking
from app.accommodation.models.wishlist import Wishlist
from app.accommodation.models.guest_profile import GuestProfile
from app.accommodation.models.feedback import (
    AccommodationComplaint,
    ComplaintCategory,
    ComplaintStatus,
    ComplaintPriority,
    AccommodationBookingAmendment,
    AmendmentType,
    AmendmentStatus,
)

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
    'RoomHold',
    'AvailabilityRule',
    'AccommodationBlockedReason',
    'GuestRegistration',
    # Review
    'Review',
    'AccommodationReviewStatus',
    'BookingContextType',
    'Wishlist',
    'GuestProfile',
    'RoomType',
    'Room',
    'RoomBooking',
    # Booking Policy
    'PropertyBookingPolicy',
    'PropertyPaymentMethod',
    'AccommodationBookingPayment',
    'GuestIdentityProfile',
    'PlatformBookingPolicyOverride',
    'BookingCommission',
    'HostProfile',
    'HostOrganisationProfile',
    'PropertyDocument',
    # Feedback
    'AccommodationComplaint',
    'ComplaintCategory',
    'ComplaintStatus',
    'ComplaintPriority',
    'AccommodationBookingAmendment',
    'AmendmentType',
    'AmendmentStatus',
]


