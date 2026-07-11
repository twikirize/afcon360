"""
Transport services initializer
Allows clean imports across the app
"""

# ------------------------
# Services
# ------------------------
from .provider_service import ProviderService, get_provider_service
from .booking_service import BookingService, get_booking_service
from .matching_service import MatchingService, get_matching_service
from .payment_service import PaymentService, get_payment_service
from .tracking_service import TrackingService, get_tracking_service
from .notification_service import NotificationService, get_notification_service
from .promotion_service import PromotionService, get_promotion_service
from .external_platforms import ExternalPlatformsService, get_external_platforms
from .dashboard_service import DashboardService, get_dashboard_service
from .settings_service import SettingsService, get_settings_service, feature_enabled, development_only, production_only

# ------------------------
# Initialization
# ------------------------
def init_provider_service():
    """Initialize the provider service singleton"""
    return get_provider_service()

def init_booking_service():
    """Initialize the booking service singleton"""
    return get_booking_service()

def init_matching_service():
    """Initialize the matching service singleton"""
    return get_matching_service()

# ------------------------
# Public API
# ------------------------

__all__ = [
    # Service classes
    'ProviderService',
    'BookingService',
    'MatchingService',
    'PaymentService',
    'TrackingService',
    'NotificationService',
    'PromotionService',
    'ExternalPlatformsService',
    'SettingsService',
    'DashboardService',

    # Singleton getters
    'get_provider_service',
    'get_booking_service',
    'get_matching_service',
    'get_payment_service',
    'get_tracking_service',
    'get_notification_service',
    'get_promotion_service',
    'get_external_platforms',
    'get_settings_service',
    'get_dashboard_service',

    # Decorators
    'feature_enabled',
    'development_only',
    'production_only',

    # Initialization
    'init_provider_service',
    'init_booking_service',
    'init_matching_service'
]
