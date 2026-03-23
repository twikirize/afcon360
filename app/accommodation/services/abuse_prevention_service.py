"""
Abuse Prevention Service - Anti-fraud and rate limiting
"""

from datetime import datetime, timedelta
from typing import Tuple
import logging

logger = logging.getLogger(__name__)


class AbusePreventionService:
    """Prevents booking abuse and fraud (CAPTCHA disabled for development)"""

    MAX_USER_HOLDS = 5
    MAX_PROPERTY_HOLDS = 10

    @staticmethod
    def check_user_hold_limit(user_id: int) -> Tuple[bool, str]:
        """Check if user has too many pending holds"""
        from app.accommodation.models.booking import AccommodationBooking, AccommodationBookingStatus

        now = datetime.utcnow()

        pending_holds = AccommodationBooking.query.filter(
            AccommodationBooking.guest_user_id == user_id,
            AccommodationBooking.status == AccommodationBookingStatus.PENDING,
            AccommodationBooking.expires_at > now  # only active pending
        ).count()

        if pending_holds >= AbusePreventionService.MAX_USER_HOLDS:
            return False, "Too many active bookings. Complete or wait."

        return True, "OK"

    @staticmethod
    def check_property_hold_limit(property_id: int) -> Tuple[bool, str]:
        """Check if property has too many pending holds"""
        from app.accommodation.models.booking import AccommodationBooking, AccommodationBookingStatus

        now = datetime.utcnow()

        pending_holds = AccommodationBooking.query.filter(
            AccommodationBooking.property_id == property_id,
            AccommodationBooking.status == AccommodationBookingStatus.PENDING,
            AccommodationBooking.expires_at > now
        ).count()

        if pending_holds >= AbusePreventionService.MAX_PROPERTY_HOLDS:
            return False, "High demand. Try again shortly."

        return True, "OK"

    @staticmethod
    def check_rate_limit(user_id: int) -> Tuple[bool, str]:
        """Check if user is creating bookings too quickly"""
        from app.accommodation.models.booking import AccommodationBooking

        now = datetime.utcnow()

        # Burst limit (per minute)
        one_minute_ago = now - timedelta(minutes=1)
        recent = AccommodationBooking.query.filter(
            AccommodationBooking.guest_user_id == user_id,
            AccommodationBooking.created_at >= one_minute_ago
        ).count()

        if recent >= 3:
            return False, "Too many requests. Slow down."

        # Sustained limit (per hour)
        one_hour_ago = now - timedelta(hours=1)
        hourly = AccommodationBooking.query.filter(
            AccommodationBooking.guest_user_id == user_id,
            AccommodationBooking.created_at >= one_hour_ago
        ).count()

        if hourly >= 10:
            return False, "Too many booking attempts. Try later."

        return True, "OK"

    @staticmethod
    def detect_suspicious_behavior(user_id: int) -> Tuple[bool, str]:
        """Detect suspicious booking patterns"""
        from app.accommodation.models.booking import AccommodationBooking, AccommodationPaymentStatus

        total = AccommodationBooking.query.filter_by(
            guest_user_id=user_id
        ).count()

        if total < 5:
            return True, "OK"

        # Check for too many unpaid or failed bookings
        failed = AccommodationBooking.query.filter(
            AccommodationBooking.guest_user_id == user_id,
            AccommodationBooking.payment_status != AccommodationPaymentStatus.PAID
        ).count()

        if (failed / total) > 0.8:
            return False, "Suspicious activity detected. Please verify your account."

        return True, "OK"

    # Development-only: no CAPTCHA enforcement
    @staticmethod
    def should_trigger_captcha(user_id: int) -> bool:
        """Currently always returns False for dev/testing"""
        return False