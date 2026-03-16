#app/transport/services/__init__.py
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
    'DashboardService',  # ← ADD THIS (was missing!)

    # Singleton getters
    'get_provider_service',
    'get_booking_service',
    'get_matching_service',
    'get_payment_service',
    'get_tracking_service',
    'get_notification_service',
    'get_promotion_service',
    'get_external_platforms',
    'get_settings_service',  # ← FIXED: removed parentheses!
    'get_dashboard_service',  # ← ADD THIS (was missing!)

    # Decorators
    'feature_enabled',
    'development_only',
    'production_only',

    # Initialization
    'init_provider_service',
    'init_booking_service',
    'init_matching_service'
]
#====================================
"""
from .provider_service import *
from .booking_service import *
from .matching_service import *
from .payment_service import *
from .tracking_service import *
from .notification_service import *
from .promotion_service import *
from .external_platforms import *
from .settings_service import *

#-----------------------------
#tree
#-----------------------------
tree
├── __init__.py
├── provider_service.py                      (450 lines)
├── booking_service.py                       (500 lines)
├── matching_service.py                      (400 lines)
├── payment_service.py                       (300 lines)
├── tracking_service.py                      (350 lines)
├── notification_service.py                  (250 lines)
├── promotion_service.py                     (300 lines)
├── external_platforms.py                    (400 lines)
└── settings_service.py                      (200 lines)

app/transport/routes.py                      (1,200 lines)
app/transport/__init__.py                    (50 lines)

app/transport/templates/
├── transport/
│   ├── base_transport.html
│   ├── homes.html                            (150 lines)
│   ├── my_trips.html                        (200 lines)
│   ├── booking_form.html                    (250 lines)
│   ├── booking_detail.html                  (180 lines)
│   └── live_tracking.html                   (220 lines)
├── provider/
│   ├── dashboard.html                       (300 lines)
│   ├── register.html                        (280 lines)
│   ├── vehicles.html                        (250 lines)
│   ├── bookings.html                        (220 lines)
│   ├── scheduled_routes.html                (200 lines)
│   └── promotions.html                      (180 lines)
└── admin/
    ├── overview.html                        (350 lines)
    ├── providers.html                       (300 lines)
    ├── live_map.html                        (280 lines)
    ├── bookings.html                        (250 lines)
    └── settings.html                        (400 lines)

    static/transport/
├── css/
│   ├── transport.css                        (300 lines)
│   └── admin.css                            (200 lines)
└── js/
    ├── booking.js                           (250 lines)
    ├── tracking.js                          (200 lines)
    └── admin_map.js                         (180 lines)

    migrations/versions/
└── YYYYMMDD_add_transport_tables.py         (200 lines)

docs/
├── INSTALLATION.md
├── API-REFERENCE.md
├── ADMIN-GUIDE.md
├── PROVIDER-GUIDE.md
└── TROUBLESHOOTING.md
"""