# app/accommodation/services/__init__.py
"""
Accommodation Services - Export all service modules
"""

from app.accommodation.services.search_service import (
    search_properties,
    get_property_by_identifier,
    list_hotels,
    get_hotel,
)
from app.accommodation.services.identity_service import AccommodationIdentityService
from app.accommodation.services.booking_service import BookingService
from app.accommodation.services.availability_service import AvailabilityService
from app.accommodation.services.pricing_service import PricingService
from app.accommodation.services.wallet_service import WalletService
from app.accommodation.services.abuse_prevention_service import AbusePreventionService
from app.accommodation.services.events_services import EventService

__all__ = [
    'search_properties',
    'get_property_by_identifier',
    'list_hotels',
    'get_hotel',
    'AccommodationIdentityService',
    'BookingService',
    'AvailabilityService',
    'PricingService',
    'WalletService',
    'AbusePreventionService',
    'EventService',
]
"""
📋 Summary of Phase 2 Components Created
File	Purpose
state_machine/__init__.py	Booking state transitions with validation
services/availability_service.py	Check availability, block/unblock dates
services/pricing_service.py	Calculate totals and refunds
services/booking_service.py	Create, confirm, cancel bookings
services/wallet_service.py	Wallet integration (placeholder)
"""