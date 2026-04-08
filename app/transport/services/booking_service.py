#app/transport/services/booking_service.py"""
"""AFCON360 Transport Module - Booking Service
Handles booking creation, management, and lifecycle
"""
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Dict, List, Optional, Any
import random
import string
import logging
from flask import current_app
from sqlalchemy import func
from sqlalchemy.exc import SQLAlchemyError

from app.extensions import db, cache
from app.transport.models import Booking, BookingStatus, ServiceType, VehicleClass
from app.utils.exceptions import ValidationError, NotFoundError, PermissionError, ServiceUnavailableError
from app.utils.security import sanitize_input
from app.utils.validators import validate_booking_request
from app.utils.monitoring import monitor_endpoint, record_metric, start_span
from app.utils.audit import audit_log

# Module-level logger (doesn't need app context)
logger = logging.getLogger(__name__)


class BookingService:
    """Instance-based service for managing transport bookings"""

    CACHE_PREFIX = "transport:booking"
    BOOKING_CACHE_TTL = 300  # 5 minutes

    def __init__(self):
        self.cache_prefix = self.CACHE_PREFIX
        self.cache_ttl = self.BOOKING_CACHE_TTL
        logger.debug("BookingService initialized")

    # =========================================================
    # Core Booking Operations
    # =========================================================

    @monitor_endpoint("create_booking")
    def create_booking(self, customer_id: int, booking_data: Dict[str, Any],
                       request_id: Optional[str] = None) -> Dict[str, Any]:
        span = start_span("create_booking")
        try:
            sanitized_data = sanitize_input(booking_data)
            validation = validate_booking_request(sanitized_data)
            if not validation["valid"]:
                raise ValidationError(
                    message="Booking validation failed",
                    details=validation["errors"]
                )

            estimated_price = self._calculate_estimated_price(sanitized_data)

            booking = Booking(
                booking_code=self._generate_booking_code(),
                customer_id=customer_id,
                service_type=ServiceType(sanitized_data["service_type"]),
                pickup_location=sanitized_data["pickup_location"],
                dropoff_location=sanitized_data["dropoff_location"],
                pickup_time=datetime.fromisoformat(sanitized_data["pickup_time"]),
                passenger_count=sanitized_data.get("passenger_count", 1),
                luggage_count=sanitized_data.get("luggage_count", 0),
                vehicle_class_preference=sanitized_data.get("vehicle_class", VehicleClass.COMFORT.value),
                special_requirements=sanitized_data.get("special_requirements", ""),
                estimated_price=estimated_price,
                estimated_distance_km=sanitized_data.get("estimated_distance"),
                estimated_duration_minutes=sanitized_data.get("estimated_duration"),
                payment_method=sanitized_data.get("payment_method", "cash"),
                status=BookingStatus.PENDING,
                metadata={
                    "customer_id": customer_id,
                    "request_id": request_id,
                    "created_at": datetime.now(timezone.utc).isoformat()
                }
            )

            db.session.add(booking)
            db.session.commit()

            self._invalidate_listing_caches()

            record_metric("booking_created", tags={
                "service_type": booking.service_type.value,
                "vehicle_class": booking.vehicle_class_preference
            }, value=1)

            audit_log(
                action="booking_created",
                entity_type="booking",
                entity_id=booking.id,
                user_id=customer_id,
                details={
                    "booking_code": booking.booking_code,
                    "service_type": booking.service_type.value,
                    "estimated_price": float(estimated_price)
                },
                request_id=request_id
            )

            return {
                "success": True,
                "message": "Booking created successfully",
                "data": {
                    "booking_id": booking.id,
                    "booking_code": booking.booking_code,
                    "estimated_price": float(estimated_price),
                    "status": booking.status.value,
                    "pickup_time": booking.pickup_time.isoformat()
                }
            }

        except ValidationError as e:
            db.session.rollback()
            span.set_status("ERROR", str(e))
            record_metric("booking_creation", tags={"status": "failed", "error_type": "validation"}, value=1)
            raise

        except SQLAlchemyError as e:
            db.session.rollback()
            logger.error(f"Database error in booking creation: {e}", exc_info=True)
            span.set_status("ERROR", f"Database error: {str(e)}")
            record_metric("booking_creation", tags={"status": "failed", "error_type": "database"}, value=1)
            raise ServiceUnavailableError("Booking service temporarily unavailable")

        finally:
            span.end()

    @monitor_endpoint("get_booking")
    def get_booking(self, booking_id: int) -> Dict[str, Any]:
        cache_key = f"{self.cache_prefix}:{booking_id}"
        cached = cache.get(cache_key)
        if cached:
            return cached

        try:
            booking = Booking.query.get(booking_id)
            if not booking or booking.is_deleted:
                raise NotFoundError("Booking not found", resource_type="booking", resource_id=booking_id)

            result = booking.to_dict()
            cache.set(cache_key, result, timeout=self.cache_ttl)
            return result

        except NotFoundError:
            raise
        except Exception as e:
            logger.error(f"Error getting booking {booking_id}: {e}", exc_info=True)
            raise ServiceUnavailableError("Could not retrieve booking details")

    @monitor_endpoint("cancel_booking")
    def cancel_booking(self, booking_id: int, user_id: int,
                       reason: Optional[str] = None) -> Dict[str, Any]:
        span = start_span("cancel_booking")
        try:
            booking = Booking.query.get(booking_id)
            if not booking:
                raise NotFoundError("Booking not found", resource_type="booking", resource_id=booking_id)

            if booking.customer_id != user_id and booking.driver_id != user_id and booking.provider_id != user_id:
                raise PermissionError("Cannot cancel another user's booking")

            if booking.status not in [BookingStatus.PENDING, BookingStatus.CONFIRMED]:
                raise ValidationError(f"Cannot cancel booking in {booking.status.value} status")

            booking.status = BookingStatus.CANCELLED
            booking.cancelled_at = datetime.now(timezone.utc)
            booking.cancellation_reason = reason
            booking.cancellation_fee = self._calculate_cancellation_fee(booking)

            db.session.commit()
            self._invalidate_booking_caches(booking_id)

            record_metric("booking_cancelled", tags={"status": "success"}, value=1)

            return {
                "success": True,
                "message": "Booking cancelled successfully",
                "data": {
                    "booking_id": booking_id,
                    "cancellation_fee": float(booking.cancellation_fee),
                    "refund_amount": float(booking.final_price - booking.cancellation_fee)  # using final_price
                }
            }

        except (NotFoundError, PermissionError, ValidationError) as e:
            db.session.rollback()
            span.set_status("ERROR", str(e))
            record_metric("booking_cancelled", tags={"status": "failed", "error_type": type(e).__name__}, value=1)
            raise
        except SQLAlchemyError as e:
            db.session.rollback()
            logger.error(f"Database error cancelling booking {booking_id}: {e}", exc_info=True)
            span.set_status("ERROR", str(e))
            record_metric("booking_cancelled", tags={"status": "failed", "error_type": "database"}, value=1)
            raise ServiceUnavailableError("Could not cancel booking")
        finally:
            span.end()

    # =========================================================
    # List & Analytics (Enhanced for Admin Dashboard)
    # =========================================================

    @monitor_endpoint("count_bookings")
    def count_bookings(self) -> int:
        """Count total number of active bookings"""
        try:
            return Booking.query.filter_by(is_deleted=False).count()
        except Exception as e:
            logger.error(f"Error counting bookings: {e}", exc_info=True)
            return 0

    @monitor_endpoint("count_bookings_by_status")
    def count_bookings_by_status(self, status: str) -> int:
        """Count bookings with specific status (for dashboard)"""
        try:
            # Map input string to BookingStatus enum
            status_upper = status.upper()
            # If status is something like 'pending', we need to map to BookingStatus.PENDING
            # Using getattr to safely get enum member
            status_enum = getattr(BookingStatus, status_upper, None)
            if status_enum is None:
                logger.error(f"Invalid status string: {status}")
                return 0

            return Booking.query.filter_by(
                status=status_enum,
                is_deleted=False
            ).count()
        except Exception as e:
            logger.error(f"Error counting bookings by status: {e}", exc_info=True)
            return 0

    @monitor_endpoint("get_recent_bookings")
    def get_recent_bookings(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get most recent bookings (for dashboard)"""
        try:
            bookings = Booking.query.filter_by(
                is_deleted=False
            ).order_by(
                Booking.created_at.desc()
            ).limit(limit).all()
            return [b.to_dict() for b in bookings]
        except Exception as e:
            logger.error(f"Error getting recent bookings: {e}", exc_info=True)
            return []

    @monitor_endpoint("get_today_bookings_count")
    def get_today_bookings_count(self) -> int:
        """Get number of bookings created today"""
        try:
            today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
            return Booking.query.filter(
                Booking.created_at >= today_start,
                Booking.is_deleted == False
            ).count()
        except Exception as e:
            logger.error(f"Error counting today's bookings: {e}", exc_info=True)
            return 0

    @monitor_endpoint("get_today_revenue")
    def get_today_revenue(self) -> float:
        """Get total revenue from today's completed bookings"""
        try:
            today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
            # Use final_price as the actual paid amount
            revenue = db.session.query(func.sum(Booking.final_price)).filter(
                Booking.created_at >= today_start,
                Booking.status == BookingStatus.COMPLETED,
                Booking.is_deleted == False
            ).scalar() or 0
            return float(revenue)
        except Exception as e:
            logger.error(f"Error calculating today's revenue: {e}", exc_info=True)
            return 0.0

    @monitor_endpoint("get_active_bookings_count")
    def get_active_bookings_count(self) -> int:
        """Get count of active bookings (in progress, confirmed, assigned)"""
        try:
            return Booking.query.filter(
                Booking.status.in_([
                    BookingStatus.CONFIRMED,
                    BookingStatus.ASSIGNED,
                    BookingStatus.IN_PROGRESS
                ]),
                Booking.is_deleted == False
            ).count()
        except Exception as e:
            logger.error(f"Error counting active bookings: {e}", exc_info=True)
            return 0

    @monitor_endpoint("generate_booking_report")
    def generate_booking_report(self, days: int = 30) -> Dict[str, Any]:
        """Generate comprehensive booking report for dashboard"""
        try:
            cutoff = datetime.now(timezone.utc) - timedelta(days=days)

            # Total bookings in period
            total = Booking.query.filter(
                Booking.created_at >= cutoff,
                Booking.is_deleted == False
            ).count()

            # Bookings by status
            by_status = {}
            for status_enum in BookingStatus:
                count = Booking.query.filter(
                    Booking.created_at >= cutoff,
                    Booking.status == status_enum,
                    Booking.is_deleted == False
                ).count()
                by_status[status_enum.value] = count

            # Revenue metrics - using final_price for completed/confirmed
            revenue = db.session.query(func.sum(Booking.final_price)).filter(
                Booking.created_at >= cutoff,
                Booking.status.in_([BookingStatus.COMPLETED, BookingStatus.CONFIRMED]),
                Booking.is_deleted == False
            ).scalar() or 0

            # Daily breakdown for charts
            daily_data = []
            for i in range(days):
                day = cutoff + timedelta(days=i)
                next_day = day + timedelta(days=1)
                day_count = Booking.query.filter(
                    Booking.created_at >= day,
                    Booking.created_at < next_day,
                    Booking.is_deleted == False
                ).count()
                daily_data.append({
                    'date': day.strftime('%Y-%m-%d'),
                    'count': day_count
                })

            return {
                "period_days": days,
                "total_bookings": total,
                "by_status": by_status,
                "total_revenue": float(revenue),
                "average_booking_value": float(revenue / total) if total else 0,
                "daily_breakdown": daily_data
            }

        except Exception as e:
            logger.error(f"Error generating booking report: {e}", exc_info=True)
            return {
                "period_days": days,
                "total_bookings": 0,
                "by_status": {},
                "total_revenue": 0,
                "average_booking_value": 0,
                "daily_breakdown": []
            }

    # =========================================================
    # Private Helper Methods
    # =========================================================

    def _calculate_estimated_price(self, booking_data: Dict[str, Any]) -> Decimal:
        base_prices = {"on_demand": 10, "airport_transfer": 25, "stadium_shuttle": 15,
                       "hotel_transfer": 20, "city_tour": 30}
        distance_rate = Decimal("2.5")
        class_multipliers = {"economy": 1.0, "comfort": 1.2, "premium": 1.5, "van": 1.8, "luxury": 2.0}

        base = Decimal(str(base_prices.get(booking_data.get("service_type", "on_demand"), 10)))
        distance = Decimal(str(booking_data.get("estimated_distance", 5)))
        multiplier = Decimal(str(class_multipliers.get(booking_data.get("vehicle_class", "comfort"), 1.0)))
        total = (base + distance * distance_rate) * multiplier

        # surge pricing
        hour = datetime.now().hour
        surge = Decimal("1.3") if 7 <= hour <= 9 or 17 <= hour <= 19 else Decimal("1.0")
        return total * surge

    def _calculate_cancellation_fee(self, booking: Booking) -> Decimal:
        hours = (booking.pickup_time - datetime.now(timezone.utc)).total_seconds() / 3600
        if hours > 24:
            return Decimal("0.0")
        elif hours > 2:
            return booking.final_price * Decimal("0.1")
        else:
            return booking.final_price * Decimal("0.5")

    def _generate_booking_code(self) -> str:
        letters = ''.join(random.choices(string.ascii_uppercase, k=3))
        numbers = ''.join(random.choices(string.digits, k=3))
        return f"AFC{letters}{numbers}"

    def _invalidate_booking_caches(self, booking_id: int):
        cache.delete(f"{self.cache_prefix}:{booking_id}")
        self._invalidate_listing_caches()

    def _invalidate_listing_caches(self):
        try:
            for key in cache.cache._client.scan_iter(f"{self.cache_prefix}:list:*"):
                cache.delete(key)
        except Exception:
            cache.delete(f"{self.cache_prefix}:list:recent")
            cache.delete(f"{self.cache_prefix}:list:all")


# =========================================================
# Singleton getter
# =========================================================
from threading import Lock

_booking_service_instance = None
_booking_service_lock = Lock()


def get_booking_service() -> BookingService:
    """Get singleton instance of BookingService"""
    global _booking_service_instance
    if _booking_service_instance is None:
        with _booking_service_lock:
            if _booking_service_instance is None:
                _booking_service_instance = BookingService()
                logger.debug("BookingService singleton created")
    return _booking_service_instance
