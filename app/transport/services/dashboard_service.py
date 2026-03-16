# app/transport/services/dashboard_service.py
"""
Service dedicated to collecting dashboard metrics
"""

from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
import logging
from flask import current_app
from app.extensions import cache
from app.transport.services import get_booking_service, get_provider_service
from app.utils.module_switch import check_module_enabled

# Module-level logger (doesn't need app context)
logger = logging.getLogger(__name__)


class DashboardService:
    """Collects and aggregates dashboard data from multiple services"""

    CACHE_KEY = "transport:admin:dashboard"
    CACHE_TTL = 300  # 5 minutes

    def __init__(self):
        self.booking_service = get_booking_service()
        self.provider_service = get_provider_service()
        logger.debug("DashboardService initialized")

    # =========================================================
    # Admin Dashboard
    # =========================================================

    def get_admin_dashboard_context(self) -> Dict[str, Any]:
        """Collect all data needed for admin dashboard"""
        try:
            return {
                # Booking metrics
                'total_bookings': self.booking_service.count_bookings(),
                'active_bookings': self.booking_service.get_active_bookings_count(),
                'today_bookings': self.booking_service.get_today_bookings_count(),
                'today_revenue': self.booking_service.get_today_revenue(),
                'recent_bookings': self.booking_service.get_recent_bookings(10),
                'pending_bookings': self.booking_service.count_bookings_by_status('pending'),
                'confirmed_bookings': self.booking_service.count_bookings_by_status('confirmed'),
                'completed_bookings': self.booking_service.count_bookings_by_status('completed'),
                'cancelled_bookings': self.booking_service.count_bookings_by_status('cancelled'),
                'booking_report': self.booking_service.generate_booking_report(7),

                # Provider metrics
                'pending_drivers': self.provider_service.count_pending_drivers(),
                'active_drivers': self.provider_service.count_active_drivers(),
                'pending_vehicles': self.provider_service.count_pending_vehicles(),
                'available_vehicles': self.provider_service.count_available_vehicles(),
                'total_drivers': self.provider_service.count_total_drivers(),
                'total_vehicles': self.provider_service.count_total_vehicles(),

                # System status
                'module_enabled': self._check_module_enabled(),
                'now': datetime.utcnow().strftime('%Y-%m-%d %H:%M'),
            }
        except Exception as e:
            logger.error(f"Error building dashboard context: {e}", exc_info=True)
            return self._get_fallback_context()

    def get_cached_admin_dashboard(self) -> Dict[str, Any]:
        """Get dashboard data from cache or generate fresh"""
        cached = cache.get(self.CACHE_KEY)
        if cached:
            logger.debug("Returning cached admin dashboard")
            return cached

        context = self.get_admin_dashboard_context()
        cache.set(self.CACHE_KEY, context, timeout=self.CACHE_TTL)
        logger.debug("Admin dashboard cached for 5 minutes")
        return context

    # =========================================================
    # Driver Dashboard
    # =========================================================

    def get_driver_dashboard_context(self, driver_id: int) -> Dict[str, Any]:
        """Get dashboard data for a specific driver"""
        try:
            return {
                # Driver's personal stats
                'my_total_trips': self._count_driver_bookings(driver_id),
                'my_completed_trips': self._count_driver_completed_bookings(driver_id),
                'my_upcoming_trips': self._get_driver_upcoming_bookings(driver_id, 5),
                'my_total_earnings': self._get_driver_earnings(driver_id),
                'my_rating': self._get_driver_rating(driver_id),
                'my_vehicle': self._get_driver_vehicle(driver_id),

                # Driver's recent activity
                'recent_trips': self._get_driver_recent_bookings(driver_id, 10),
                'next_booking': self._get_driver_next_booking(driver_id),

                # Driver's status
                'is_online': self._get_driver_online_status(driver_id),
                'is_available': self._get_driver_availability(driver_id),

                'now': datetime.utcnow().strftime('%Y-%m-%d %H:%M')
            }
        except Exception as e:
            logger.error(f"Error building driver dashboard: {e}", exc_info=True)
            return self._get_driver_fallback_context()

    # =========================================================
    # Organisation Dashboard
    # =========================================================

    def get_organisation_dashboard_context(self, org_id: int) -> Dict[str, Any]:
        """Get dashboard data for an organisation"""
        try:
            return {
                # Organisation stats
                'total_fleet': self._count_org_vehicles(org_id),
                'available_vehicles': self._count_org_available_vehicles(org_id),
                'total_drivers': self._count_org_drivers(org_id),
                'active_drivers': self._count_org_active_drivers(org_id),

                # Booking stats
                'total_bookings': self._count_org_bookings(org_id),
                'today_bookings': self._count_org_today_bookings(org_id),
                'total_revenue': self._get_org_revenue(org_id),

                # Lists
                'fleet_vehicles': self._get_org_vehicles(org_id, 10),
                'recent_bookings': self._get_org_recent_bookings(org_id, 10),

                'now': datetime.utcnow().strftime('%Y-%m-%d %H:%M')
            }
        except Exception as e:
            logger.error(f"Error building org dashboard: {e}", exc_info=True)
            return self._get_org_fallback_context()

    # =========================================================
    # Helper Methods (to be implemented or delegated)
    # =========================================================

    def _check_module_enabled(self) -> bool:
        """Check if transport module is enabled"""
        return check_module_enabled("transport")

    # Driver helper methods (these should be in provider_service)
    def _get_driver_rating(self, driver_id: int) -> float:
        """Get driver's rating"""
        try:
            return self.provider_service.get_driver_rating(driver_id)
        except (AttributeError, NotImplementedError):
            return 0.0

    def _get_driver_vehicle(self, driver_id: int) -> Optional[Dict]:
        """Get driver's vehicle"""
        try:
            return self.provider_service.get_driver_vehicle(driver_id)
        except (AttributeError, NotImplementedError):
            return None

    def _get_driver_online_status(self, driver_id: int) -> bool:
        """Get driver's online status"""
        try:
            return self.provider_service.get_driver_online_status(driver_id)
        except (AttributeError, NotImplementedError):
            return False

    def _get_driver_availability(self, driver_id: int) -> bool:
        """Get driver's availability"""
        try:
            return self.provider_service.get_driver_availability(driver_id)
        except (AttributeError, NotImplementedError):
            return False

    # Booking helper methods (these should be in booking_service)
    def _count_driver_bookings(self, driver_id: int) -> int:
        """Count driver's total bookings"""
        try:
            return self.booking_service.count_driver_bookings(driver_id)
        except (AttributeError, NotImplementedError):
            return 0

    def _count_driver_completed_bookings(self, driver_id: int) -> int:
        """Count driver's completed bookings"""
        try:
            return self.booking_service.count_driver_bookings_by_status(driver_id, 'completed')
        except (AttributeError, NotImplementedError):
            return 0

    def _get_driver_upcoming_bookings(self, driver_id: int, limit: int) -> List:
        """Get driver's upcoming bookings"""
        try:
            return self.booking_service.get_driver_upcoming_bookings(driver_id, limit)
        except (AttributeError, NotImplementedError):
            return []

    def _get_driver_earnings(self, driver_id: int) -> float:
        """Get driver's total earnings"""
        try:
            return self.booking_service.get_driver_earnings(driver_id)
        except (AttributeError, NotImplementedError):
            return 0.0

    def _get_driver_recent_bookings(self, driver_id: int, limit: int) -> List:
        """Get driver's recent bookings"""
        try:
            return self.booking_service.get_driver_recent_bookings(driver_id, limit)
        except (AttributeError, NotImplementedError):
            return []

    def _get_driver_next_booking(self, driver_id: int) -> Optional[Dict]:
        """Get driver's next booking"""
        try:
            return self.booking_service.get_driver_next_booking(driver_id)
        except (AttributeError, NotImplementedError):
            return None

    # Organisation helper methods
    def _count_org_vehicles(self, org_id: int) -> int:
        """Count organisation's vehicles"""
        try:
            return self.provider_service.count_org_vehicles(org_id)
        except (AttributeError, NotImplementedError):
            return 0

    def _count_org_available_vehicles(self, org_id: int) -> int:
        """Count organisation's available vehicles"""
        try:
            return self.provider_service.count_org_available_vehicles(org_id)
        except (AttributeError, NotImplementedError):
            return 0

    def _count_org_drivers(self, org_id: int) -> int:
        """Count organisation's drivers"""
        try:
            return self.provider_service.count_org_drivers(org_id)
        except (AttributeError, NotImplementedError):
            return 0

    def _count_org_active_drivers(self, org_id: int) -> int:
        """Count organisation's active drivers"""
        try:
            return self.provider_service.count_org_active_drivers(org_id)
        except (AttributeError, NotImplementedError):
            return 0

    def _count_org_bookings(self, org_id: int) -> int:
        """Count organisation's bookings"""
        try:
            return self.booking_service.count_org_bookings(org_id)
        except (AttributeError, NotImplementedError):
            return 0

    def _count_org_today_bookings(self, org_id: int) -> int:
        """Count organisation's today's bookings"""
        try:
            return self.booking_service.count_org_today_bookings(org_id)
        except (AttributeError, NotImplementedError):
            return 0

    def _get_org_revenue(self, org_id: int) -> float:
        """Get organisation's revenue"""
        try:
            return self.booking_service.get_org_revenue(org_id)
        except (AttributeError, NotImplementedError):
            return 0.0

    def _get_org_vehicles(self, org_id: int, limit: int) -> List:
        """Get organisation's vehicles"""
        try:
            return self.provider_service.get_org_vehicles(org_id, limit)
        except (AttributeError, NotImplementedError):
            return []

    def _get_org_recent_bookings(self, org_id: int, limit: int) -> List:
        """Get organisation's recent bookings"""
        try:
            return self.booking_service.get_org_recent_bookings(org_id, limit)
        except (AttributeError, NotImplementedError):
            return []

    # =========================================================
    # Fallback Contexts
    # =========================================================

    def _get_fallback_context(self) -> Dict[str, Any]:
        """Return safe fallback values if something fails"""
        return {
            'total_bookings': 0, 'active_bookings': 0, 'today_bookings': 0,
            'today_revenue': 0, 'recent_bookings': [], 'pending_bookings': 0,
            'confirmed_bookings': 0, 'completed_bookings': 0, 'cancelled_bookings': 0,
            'booking_report': {}, 'pending_drivers': 0, 'active_drivers': 0,
            'pending_vehicles': 0, 'available_vehicles': 0,
            'total_drivers': 0, 'total_vehicles': 0,
            'module_enabled': False, 'now': datetime.utcnow().strftime('%Y-%m-%d %H:%M')
        }

    def _get_driver_fallback_context(self) -> Dict[str, Any]:
        return {
            'my_total_trips': 0, 'my_completed_trips': 0, 'my_upcoming_trips': [],
            'my_total_earnings': 0, 'my_rating': 0, 'my_vehicle': None,
            'recent_trips': [], 'next_booking': None,
            'is_online': False, 'is_available': False,
            'now': datetime.utcnow().strftime('%Y-%m-%d %H:%M')
        }

    def _get_org_fallback_context(self) -> Dict[str, Any]:
        return {
            'total_fleet': 0, 'available_vehicles': 0, 'total_drivers': 0,
            'active_drivers': 0, 'total_bookings': 0, 'today_bookings': 0,
            'total_revenue': 0, 'fleet_vehicles': [], 'recent_bookings': [],
            'now': datetime.utcnow().strftime('%Y-%m-%d %H:%M')
        }


# =========================================================
# Singleton getter
# =========================================================
_dashboard_service = None


def get_dashboard_service() -> DashboardService:
    """Get singleton instance of DashboardService"""
    global _dashboard_service
    if _dashboard_service is None:
        _dashboard_service = DashboardService()
        logger.debug("DashboardService singleton created")
    return _dashboard_service