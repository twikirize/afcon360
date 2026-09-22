"""AFCON360 Transport Module - Booking Service
Handles booking creation, management, and lifecycle
"""
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Dict, List, Optional, Any
import random
import string
import logging
import sqlalchemy as sa
from flask import current_app
from sqlalchemy import func
from sqlalchemy.exc import SQLAlchemyError, IntegrityError

from app.extensions import db, cache
from app.transport.models import (
    Booking,
    BookingStatus,
    ServiceType,
    ProviderType,
    VehicleClass,
    Currency,
    PaymentStatus,
)
from app.core.validators import validate_coordinates
from app.utils.exceptions import ValidationError, NotFoundError, PermissionError, ServiceUnavailableError
from app.utils.security import sanitize_input
from app.utils.validators import validate_booking_request
from app.utils.monitoring import monitor_endpoint, record_metric
from app.utils.audit import audit_log

# Module-level logger (doesn't need app context)
logger = logging.getLogger(__name__)


def _validate_booking_location_coordinates(location: Any, field_name: str) -> Any:
    """Enforce the canonical geographic contract at the booking boundary.

    - Non-dict payloads (address-only / free text) pass through unchanged.
    - 'lat'/'lng' keys are REJECTED (must use 'latitude'/'longitude').
    - Canonical coordinates must be BOTH present and valid ranges.
    """
    if not isinstance(location, dict):
        return location
    if "lat" in location or "lng" in location:
        raise ValidationError(
            f"{field_name} geographic coordinates must use 'latitude'/'longitude' keys; 'lat'/'lng' are not accepted",
            field=field_name,
        )
    has_lat = location.get("latitude") is not None
    has_lng = location.get("longitude") is not None
    if has_lat != has_lng:
        raise ValidationError(
            f"{field_name} must include both 'latitude' and 'longitude'",
            field=field_name,
        )
    if has_lat:
        validate_coordinates(location["latitude"], location["longitude"])
    return location


def _resolve_canonical_location(raw_location: Any, data: Dict[str, Any],
                                prefix: str, field_name: str) -> Any:
    """Resolve a booking endpoint to its truthful representation.

    Empty-string lat/lng (which the form posts when no map pin was placed)
    are treated as ABSENT, not as coordinates. This is what the form
    actually sends — treating "" as a coordinate is the bug that produced
    'pickup_location coordinates must be numeric'.
    """
    if isinstance(raw_location, dict) and (
            raw_location.get("latitude") is not None
            or raw_location.get("longitude") is not None):
        return _validate_booking_location_coordinates(raw_location, field_name)

    def _blank(v):
        return v is None or (isinstance(v, str) and not v.strip())

    lat_raw = data.get(f"{prefix}_latitude") if isinstance(data, dict) else None
    lng_raw = data.get(f"{prefix}_longitude") if isinstance(data, dict) else None

    # No pins placed → falls back to typed address (unchanged behaviour)
    if _blank(lat_raw) and _blank(lng_raw):
        return _validate_booking_location_coordinates(raw_location, field_name)

    # One pin placed, the other missing → refuse rather than silently degrade
    if _blank(lat_raw) or _blank(lng_raw):
        raise ValidationError(
            message=f"{field_name} must include both 'latitude' and 'longitude'",
        )

    try:
        lat = float(lat_raw)
        lng = float(lng_raw)
    except (TypeError, ValueError):
        raise ValidationError(
            message=f"{field_name} coordinates must be numeric",
        )

    validate_coordinates(lat, lng)
    resolved = {"latitude": lat, "longitude": lng}
    if isinstance(raw_location, str) and raw_location.strip():
        resolved["address"] = raw_location.strip()
    elif isinstance(raw_location, dict) and raw_location.get("address"):
        resolved["address"] = raw_location.get("address")
    return resolved


def _measured_distance_km(pickup_location: Any,
                          dropoff_location: Any) -> Optional[float]:
    """GEO straight-line kilometres between two canonical endpoints,
    or None unless BOTH carry valid coordinates. Planning input only:
    explicitly not road distance, ETA, or fare distance."""
    def _coords(location: Any):
        if not isinstance(location, dict):
            return None
        try:
            lat = float(location.get("latitude"))
            lng = float(location.get("longitude"))
        except (TypeError, ValueError):
            return None
        if not (-90.0 <= lat <= 90.0 and -180.0 <= lng <= 180.0):
            return None
        return lat, lng

    origin = _coords(pickup_location)
    destination = _coords(dropoff_location)
    if origin is None or destination is None:
        return None
    from app.geo.interfaces import GeoPoint
    from app.geo.services import straight_line_distance_m
    return straight_line_distance_m(
        GeoPoint(origin[0], origin[1]),
        GeoPoint(destination[0], destination[1])) / 1000.0


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
        try:
            sanitized_data = booking_data or {}

            # Idempotency dedupe — before any fare calc or DB write
            key = (sanitized_data.get("idempotency_key") or "").strip() or None
            if key:
                existing = Booking.query.filter_by(
                    idempotency_key=key,
                    user_id=customer_id,
                    is_deleted=False,
                ).first()
                if existing:
                    existing.booking_metadata = existing.booking_metadata or {}
                    existing.booking_metadata["idempotent_replay"] = True
                    existing.booking_metadata["replayed_at"] = datetime.now(timezone.utc).isoformat()
                    return {
                        "success": True,
                        "data": {
                            "booking_id": existing.id,
                            "booking_reference": existing.booking_reference,
                            "idempotent_replay": True,
                        },
                    }

            is_valid, validation_errors = validate_booking_request(sanitized_data)
            if not is_valid:
                raise ValidationError(
                    message="; ".join(validation_errors) or "Booking validation failed"
                )

            pickup_location = _resolve_canonical_location(
                sanitized_data.get("pickup_location"), sanitized_data,
                "pickup", "pickup_location")
            dropoff_location = _resolve_canonical_location(
                sanitized_data.get("dropoff_location"), sanitized_data,
                "dropoff", "dropoff_location")

            # Measured GEO straight-line distance wins when both ends
            # resolved to coordinates; otherwise the caller-supplied
            # estimate (default 5 km planning fallback) is preserved
            # verbatim. The USED value is stored so the priced distance
            # is always explainable.
            measured_km = _measured_distance_km(pickup_location,
                                                dropoff_location)
            if measured_km is not None:
                distance_for_fare = measured_km
                distance_basis = "straight_line_planner"
            else:
                distance_for_fare = sanitized_data.get("estimated_distance", 5)
                distance_basis = "planning_default"

            # Canonical fare engine (fare node): one computation feeds the
            # stored price, the recorded surge, and the stored distance
            # basis, so they can never diverge (e.g. across an hour
            # boundary between two calls).
            # Chosen class (hailing node): the ride picker submits the
            # selected class; it is persisted in service_subtype and
            # booking_metadata for class-aware matching.
            chosen_class = sanitized_data.get("vehicle_class", "comfort")
            from app.transport.services.fare_service import calculate_estimate
            _estimate = calculate_estimate(
                service_type=sanitized_data.get("service_type", "on_demand"),
                vehicle_class=chosen_class,
                distance_km=distance_for_fare,
            )
            estimated_price = _estimate["total"]
            # Record the applied surge alongside the price (fare node):
            # the surge_multiplier column previously stayed at its 1.00
            # default even when rush pricing applied, making estimates
            # unexplainable. Same engine, same inputs — no price change.
            _applied_surge = _estimate["surge_multiplier"]

            try:
                pickup_time = datetime.fromisoformat(str(sanitized_data["pickup_time"]))
            except (ValueError, TypeError, KeyError):
                pickup_time = datetime.now(timezone.utc)

            special_req = sanitized_data.get("special_requirements") or {}
            if isinstance(special_req, str):
                special_req = {"note": special_req}

            pickup_location = _resolve_canonical_location(
                sanitized_data.get("pickup_location"), sanitized_data,
                "pickup", "pickup_location")
            dropoff_location = _resolve_canonical_location(
                sanitized_data.get("dropoff_location"), sanitized_data,
                "dropoff", "dropoff_location")

            # Measured GEO straight-line distance wins when both ends
            # resolved to coordinates; otherwise the caller-supplied
            # estimate (default 5 km planning fallback) is preserved
            # verbatim. The USED value is stored so the priced distance
            # is always explainable.
            measured_km = _measured_distance_km(pickup_location,
                                                dropoff_location)
            if measured_km is not None:
                distance_for_fare = measured_km
                distance_basis = "straight_line_planner"
            else:
                distance_for_fare = sanitized_data.get("estimated_distance", 5)
                distance_basis = "planning_default"

            booking = Booking(
                user_id=customer_id,
                provider_type=ProviderType(
                    (sanitized_data.get("provider_type") or "individual_driver").lower()
                ),
                service_type=ServiceType(sanitized_data["service_type"].lower()),
                pickup_location=pickup_location,
                dropoff_location=dropoff_location,
                pickup_time=pickup_time,
                passenger_count=int(sanitized_data.get("passenger_count") or 1),
                luggage_count=int(sanitized_data.get("luggage_count") or 0),
                special_requirements=special_req,
                accessibility_requirements=sanitized_data.get("accessibility_requirements") or [],
                base_price=estimated_price,
                surge_multiplier=_applied_surge,
                estimated_distance_km=distance_for_fare,
                estimated_duration_minutes=sanitized_data.get("estimated_duration"),
                payment_method=sanitized_data.get("payment_method", "cash"),
                payment_status=PaymentStatus.PENDING,
                status=BookingStatus.PENDING_PAYMENT,
                currency=Currency(sanitized_data.get("currency") or "USD"),
                service_subtype=chosen_class,
                idempotency_key=key,
                booking_metadata={
                    "customer_id": customer_id,
                    "request_id": request_id,
                    "vehicle_class": chosen_class,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "fare_version": _estimate.get("version"),
                    "fare_effective_from": _estimate.get("effective_from"),
                    "distance_km": float(distance_for_fare)
                    if distance_for_fare is not None else None,
                    "distance_basis": distance_basis,
                }
            )

            db.session.add(booking)
            db.session.commit()

            self._invalidate_listing_caches()

            record_metric("booking_created", tags={
                "service_type": booking.service_type.value,
                "provider_type": booking.provider_type.value
            }, value=1)

            audit_log(
                action="booking_created",
                resource_type="booking",
                resource_id=booking.id,
                user_id=customer_id,
                details={
                    "booking_reference": booking.booking_reference,
                    "service_type": booking.service_type.value,
                    "base_price": float(estimated_price),
                    "request_id": request_id,
                }
            )

            # Emit notification signal (listener notifies customer)
            try:
                from app.notifications.signals import transport_booking_created
                transport_booking_created.send(booking, booking=booking)
            except Exception as _ne:
                logger.warning(f"transport_booking_created signal failed: {_ne}")

            return {
                "success": True,
                "message": "Booking created successfully",
                "data": {
                    "booking_id": booking.id,
                    "booking_public_id": booking.booking_reference,
                    "booking_reference": booking.booking_reference,
                    "estimated_price": float(estimated_price),
                    "status": booking.status.value,
                    "pickup_time": booking.pickup_time.isoformat()
                }
            }

        except ValidationError as e:
            db.session.rollback()
            record_metric("booking_creation", tags={"status": "failed", "error_type": "validation"}, value=1)
            raise

        except IntegrityError:
            # Concurrent same-key race: two threads passed the dedupe check,
            # one INSERT won, this one hit the partial unique index. The
            # winner's booking exists — return it as a replay.
            db.session.rollback()
            if key:
                winner = Booking.query.filter_by(
                    idempotency_key=key,
                    user_id=customer_id,
                    is_deleted=False,
                ).first()
                if winner is not None:
                    winner.booking_metadata = winner.booking_metadata or {}
                    winner.booking_metadata["idempotent_replay"] = True
                    winner.booking_metadata["replayed_at"] = (
                        datetime.now(timezone.utc).isoformat()
                    )
                    db.session.commit()
                    return {
                        "success": True,
                        "message": "Booking already exists (concurrent replay)",
                        "data": {
                            "booking_id": winner.id,
                            "booking_reference": winner.booking_reference,
                            "idempotent_replay": True,
                        },
                    }
            logger.error("IntegrityError with no key — cannot recover", exc_info=True)
            raise ServiceUnavailableError("Booking service temporarily unavailable")

        except SQLAlchemyError as e:
            db.session.rollback()
            logger.error(f"Database error in booking creation: {e}", exc_info=True)
            record_metric("booking_creation", tags={"status": "failed", "error_type": "database"}, value=1)
            raise ServiceUnavailableError("Booking service temporarily unavailable")

    @monitor_endpoint("get_booking")
    def get_booking(self, booking_id: int) -> Dict[str, Any]:
        cache_key = f"{self.cache_prefix}:{booking_id}"
        cached = cache.get(cache_key)
        if cached:
            return cached

        try:
            booking = db.session.get(Booking, booking_id)
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
        try:
            booking = db.session.get(Booking, booking_id)
            if not booking:
                raise NotFoundError("Booking not found", resource_type="booking", resource_id=booking_id)

            if booking.user_id != user_id and booking.assigned_driver_id != user_id and booking.provider_id != user_id:
                raise PermissionError("Cannot cancel another user's booking")

            if booking.is_deleted:
                raise NotFoundError("Booking not found", resource_type="booking", resource_id=booking_id)

            # Race-E-safe cancellation (D2): the pre-assignment status gate is
            # enforced atomically by the conditional UPDATE. Ownership is
            # checked above (authorization), the status gate is part of the
            # guarded statement so a concurrent claim cannot slip between a
            # read and a write. rowcount == 1 is REQUIRED.
            cancellation_fee = self._calculate_cancellation_fee(booking)
            refund_amount = float(booking.final_price - cancellation_fee)

            result = db.session.execute(
                sa.update(Booking.__table__)
                .where(
                    Booking.__table__.c.id == booking_id,
                    Booking.__table__.c.status.in_([
                        BookingStatus.PENDING_PAYMENT.value,
                        BookingStatus.CONFIRMED.value,
                    ]),
                    Booking.__table__.c.is_deleted.is_(False),
                )
                .values(
                    status=BookingStatus.CANCELLED.value,
                    cancelled_at=datetime.now(timezone.utc),
                    cancellation_reason=reason,
                    cancellation_fee=cancellation_fee,
                )
                .execution_options(synchronize_session=False)
            )
            if result.rowcount != 1:
                db.session.rollback()
                raise ValidationError(
                    "Cannot cancel booking: it is no longer in a cancellable "
                    "(pre-assignment) state"
                )

            db.session.commit()
            db.session.expire_all()
            self._invalidate_booking_caches(booking_id)

            record_metric("booking_cancelled", tags={"status": "success"}, value=1)

            return {
                "success": True,
                "message": "Booking cancelled successfully",
                "data": {
                    "booking_id": booking_id,
                    "cancellation_fee": float(cancellation_fee),
                    "refund_amount": refund_amount,  # using final_price
                }
            }

        except (NotFoundError, PermissionError, ValidationError) as e:
            db.session.rollback()
            record_metric("booking_cancelled", tags={"status": "failed", "error_type": type(e).__name__}, value=1)
            raise
        except SQLAlchemyError as e:
            db.session.rollback()
            logger.error(f"Database error cancelling booking {booking_id}: {e}", exc_info=True)
            record_metric("booking_cancelled", tags={"status": "failed", "error_type": "database"}, value=1)
            raise ServiceUnavailableError("Could not cancel booking")

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

    @monitor_endpoint("get_user_bookings")
    def get_user_bookings(
        self,
        user_id: int,
        limit: int = 5,
        *,
        include_cancelled: bool = False,
        include_draft: bool = False,
    ) -> List[Dict[str, Any]]:
        """Recent bookings for one authenticated user.

        Default excludes bookings that never became rides:
          * CANCELLED — user withdrew, no trip happened
          * DRAFT     — never submitted, only a skeleton

        Callers that need the full history (e.g. My Trips list) can opt in
        via ``include_cancelled=True`` / ``include_draft=True``.

        Used by the Transport front page to render a truthful, user-scoped
        Recent Rides list. Never returns another user's bookings.
        """
        try:
            query = Booking.query.filter(
                Booking.user_id == user_id,
                Booking.is_deleted == False  # noqa: E712
            )

            excluded: List[BookingStatus] = []
            if not include_cancelled:
                excluded.append(BookingStatus.CANCELLED)
            if not include_draft:
                excluded.append(BookingStatus.DRAFT)
            if excluded:
                query = query.filter(~Booking.status.in_(excluded))

            bookings = (
                query
                .order_by(
                    Booking.created_at.desc()
                ).limit(limit).all()
            )
            # Build the light-weight dict explicitly (Booking.to_dict depends on
            # app.core.serializers.ModelSerializer which is not present).
            routes = []
            for b in bookings:
                pickup = b.pickup_address
                if not pickup and isinstance(b.pickup_location, dict):
                    pickup = b.pickup_location.get("address") or b.pickup_location.get(
                        "name") or b.pickup_location.get("label")
                dropoff = b.dropoff_address
                if not dropoff and isinstance(b.dropoff_location, dict):
                    dropoff = b.dropoff_location.get("address") or b.dropoff_location.get(
                        "name") or b.dropoff_location.get("label")
                routes.append({
                    "booking_id": b.id,
                    "booking_reference": b.booking_reference,
                    "pickup_location": pickup or "Pickup",
                    "dropoff_location": dropoff or "Destination",
                    "status": b.status.value if b.status else None,
                    "pickup_time": b.pickup_time.isoformat() if b.pickup_time else None,
                    "created_at": b.created_at.isoformat() if b.created_at else None,
                    "final_price": float(b.final_price) if b.final_price is not None else None,
                    "currency": b.currency.value if b.currency else None,
                })
            return routes
        except Exception as e:
            logger.error(f"Error getting bookings for user {user_id}: {e}", exc_info=True)
            return []

    @monitor_endpoint("count_user_bookings")
    def count_user_bookings(self, user_id: int) -> int:
        """Count the active (non-deleted) bookings for a single user."""
        try:
            return Booking.query.filter(
                Booking.user_id == user_id,
                Booking.is_deleted == False  # noqa: E712
            ).count()
        except Exception as e:
            logger.error(f"Error counting bookings for user {user_id}: {e}", exc_info=True)
            return 0

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
    # Admin Listing & Driver-scoped Queries
    # =========================================================

    @monitor_endpoint("list_all_bookings")
    def list_all_bookings(self, page: int = 1, per_page: int = 25) -> Dict[str, Any]:
        """List all bookings with pagination (admin dashboard)."""
        try:
            query = Booking.query.filter_by(
                is_deleted=False
            ).order_by(Booking.created_at.desc())
            paginated = query.paginate(page=page, per_page=per_page, error_out=False)
            return {
                'items': [b.to_dict() for b in paginated.items],
                'total': paginated.total,
                'page': page,
                'per_page': per_page,
                'pages': paginated.pages,
            }
        except Exception as e:
            logger.error(f"Error listing all bookings: {e}", exc_info=True)
            return {
                'items': [], 'total': 0,
                'page': page, 'per_page': per_page, 'pages': 0,
            }

    @monitor_endpoint("get_driver_bookings")
    def get_driver_bookings(self, driver_user_id: int) -> List[Dict[str, Any]]:
        """Get bookings assigned to a driver, looked up by the driver's user_id.

        The driver dashboard calls this to show the driver's assigned rides.
        """
        try:
            from app.transport.models import DriverProfile
            profile = DriverProfile.query.filter_by(
                user_id=driver_user_id, is_deleted=False
            ).first()
            if not profile:
                return []
            bookings = Booking.query.filter(
                Booking.assigned_driver_id == profile.id,
                Booking.is_deleted == False,  # noqa: E712
            ).order_by(Booking.created_at.desc()).limit(20).all()
            return [b.to_dict() for b in bookings]
        except Exception as e:
            logger.error(f"Error getting driver bookings for user {driver_user_id}: {e}", exc_info=True)
            return []

    @monitor_endpoint("count_bookings_since")
    def count_bookings_since(self, since: datetime) -> int:
        """Count bookings created since a given datetime."""
        try:
            return Booking.query.filter(
                Booking.created_at >= since,
                Booking.is_deleted == False,  # noqa: E712
            ).count()
        except Exception as e:
            logger.error(f"Error counting bookings since {since}: {e}", exc_info=True)
            return 0

    @monitor_endpoint("count_driver_bookings")
    def count_driver_bookings(self, driver_user_id: int) -> int:
        """Count total bookings for a driver (by user_id)."""
        try:
            from app.transport.models import DriverProfile
            profile = DriverProfile.query.filter_by(
                user_id=driver_user_id, is_deleted=False
            ).first()
            if not profile:
                return 0
            return Booking.query.filter(
                Booking.assigned_driver_id == profile.id,
                Booking.is_deleted == False,  # noqa: E712
            ).count()
        except Exception as e:
            logger.error(f"Error counting driver bookings: {e}", exc_info=True)
            return 0

    @monitor_endpoint("count_driver_bookings_by_status")
    def count_driver_bookings_by_status(self, driver_user_id: int, status: str) -> int:
        """Count driver bookings with a specific status."""
        try:
            from app.transport.models import DriverProfile
            profile = DriverProfile.query.filter_by(
                user_id=driver_user_id, is_deleted=False
            ).first()
            if not profile:
                return 0
            status_enum = getattr(BookingStatus, status.upper(), None)
            if status_enum is None:
                return 0
            return Booking.query.filter(
                Booking.assigned_driver_id == profile.id,
                Booking.status == status_enum,
                Booking.is_deleted == False,  # noqa: E712
            ).count()
        except Exception as e:
            logger.error(f"Error counting driver bookings by status: {e}", exc_info=True)
            return 0

    @monitor_endpoint("get_driver_upcoming_bookings")
    def get_driver_upcoming_bookings(self, driver_user_id: int, limit: int = 5) -> List[Dict[str, Any]]:
        """Get upcoming bookings for a driver."""
        try:
            from app.transport.models import DriverProfile
            profile = DriverProfile.query.filter_by(
                user_id=driver_user_id, is_deleted=False
            ).first()
            if not profile:
                return []
            now = datetime.now(timezone.utc)
            bookings = Booking.query.filter(
                Booking.assigned_driver_id == profile.id,
                Booking.status.in_([BookingStatus.CONFIRMED, BookingStatus.ASSIGNED, BookingStatus.DRIVER_EN_ROUTE]),
                Booking.pickup_time > now,
                Booking.is_deleted == False,  # noqa: E712
            ).order_by(Booking.pickup_time.asc()).limit(limit).all()
            return [b.to_dict() for b in bookings]
        except Exception as e:
            logger.error(f"Error getting driver upcoming bookings: {e}", exc_info=True)
            return []

    @monitor_endpoint("get_driver_earnings")
    def get_driver_earnings(self, driver_user_id: int) -> float:
        """Total driver earnings across completed + captured bookings.

        Applies the driver's commission_rate (percentage the PLATFORM keeps)
        so the returned number is the driver's payout, not the gross fare the
        rider paid.

        Note: commission_rate lives on DriverProfile, not per-booking. If the
        rate changes over time, historical completed bookings are recomputed
        at the current rate. Snapshotting the rate per booking is deferred
        (see S-18).
        """
        try:
            from app.transport.models import DriverProfile
            profile = DriverProfile.query.filter_by(
                user_id=driver_user_id, is_deleted=False
            ).first()
            if not profile:
                return 0.0

            gross = (
                db.session.query(func.sum(Booking.final_price))
                .filter(
                    Booking.assigned_driver_id == profile.id,
                    Booking.status == BookingStatus.COMPLETED,
                    Booking.payment_status == PaymentStatus.CAPTURED,
                    Booking.is_deleted == False,  # noqa: E712
                )
                .scalar()
                or 0
            )
            gross = float(gross)
            if gross <= 0:
                return 0.0

            rate = profile.commission_rate
            if rate is None:
                rate_pct = 15.0
            else:
                try:
                    rate_pct = float(rate)
                except (TypeError, ValueError):
                    rate_pct = 15.0

            if rate_pct < 0:
                rate_pct = 0.0
            elif rate_pct > 100:
                rate_pct = 100.0

            return round(gross * (1.0 - rate_pct / 100.0), 2)

        except Exception as e:
            logger.error(f"Error getting driver earnings: {e}", exc_info=True)
            return 0.0

    @monitor_endpoint("get_driver_recent_bookings")
    def get_driver_recent_bookings(self, driver_user_id: int, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent bookings for a driver."""
        try:
            from app.transport.models import DriverProfile
            profile = DriverProfile.query.filter_by(
                user_id=driver_user_id, is_deleted=False
            ).first()
            if not profile:
                return []
            bookings = Booking.query.filter(
                Booking.assigned_driver_id == profile.id,
                Booking.is_deleted == False,  # noqa: E712
            ).order_by(Booking.created_at.desc()).limit(limit).all()
            return [b.to_dict() for b in bookings]
        except Exception as e:
            logger.error(f"Error getting driver recent bookings: {e}", exc_info=True)
            return []

    @monitor_endpoint("get_driver_next_booking")
    def get_driver_next_booking(self, driver_user_id: int) -> Optional[Dict[str, Any]]:
        """Get the next upcoming booking for a driver."""
        try:
            from app.transport.models import DriverProfile
            profile = DriverProfile.query.filter_by(
                user_id=driver_user_id, is_deleted=False
            ).first()
            if not profile:
                return None
            now = datetime.now(timezone.utc)
            booking = Booking.query.filter(
                Booking.assigned_driver_id == profile.id,
                Booking.status.in_([BookingStatus.ASSIGNED, BookingStatus.DRIVER_EN_ROUTE]),
                Booking.pickup_time > now,
                Booking.is_deleted == False,  # noqa: E712
            ).order_by(Booking.pickup_time.asc()).first()
            return booking.to_dict() if booking else None
        except Exception as e:
            logger.error(f"Error getting driver next booking: {e}", exc_info=True)
            return None

    @monitor_endpoint("count_org_bookings")
    def count_org_bookings(self, org_id: int) -> int:
        """Count bookings for an organisation."""
        try:
            return Booking.query.filter(
                Booking.provider_id == org_id,
                Booking.is_deleted == False,  # noqa: E712
            ).count()
        except Exception as e:
            logger.error(f"Error counting org bookings: {e}", exc_info=True)
            return 0

    @monitor_endpoint("count_org_today_bookings")
    def count_org_today_bookings(self, org_id: int) -> int:
        """Count today's bookings for an organisation."""
        try:
            today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
            return Booking.query.filter(
                Booking.provider_id == org_id,
                Booking.created_at >= today_start,
                Booking.is_deleted == False,  # noqa: E712
            ).count()
        except Exception as e:
            logger.error(f"Error counting org today bookings: {e}", exc_info=True)
            return 0

    @monitor_endpoint("get_org_revenue")
    def get_org_revenue(self, org_id: int) -> float:
        """Get total revenue for an organisation from completed bookings."""
        try:
            revenue = db.session.query(func.sum(Booking.final_price)).filter(
                Booking.provider_id == org_id,
                Booking.status == BookingStatus.COMPLETED,
                Booking.is_deleted == False,  # noqa: E712
            ).scalar() or 0
            return float(revenue)
        except Exception as e:
            logger.error(f"Error getting org revenue: {e}", exc_info=True)
            return 0.0

    @monitor_endpoint("get_org_recent_bookings")
    def get_org_recent_bookings(self, org_id: int, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent bookings for an organisation."""
        try:
            bookings = Booking.query.filter(
                Booking.provider_id == org_id,
                Booking.is_deleted == False,  # noqa: E712
            ).order_by(Booking.created_at.desc()).limit(limit).all()
            return [b.to_dict() for b in bookings]
        except Exception as e:
            logger.error(f"Error getting org recent bookings: {e}", exc_info=True)
            return []

    # =========================================================
    # Private Helper Methods
    # =========================================================

    def _calculate_cancellation_fee(self, booking: Booking) -> Decimal:
        """Cancellation fee tiers.

        DEV/TESTING: the immediate-cancel grace window is 0 minutes — any
        pickup_time at or before now is free to cancel. This is intentional
        while the platform is under test. Before production, restore the
        industry-standard 5-minute grace window (see BACKLOG.md BL-01).

        Tiers when pickup is in the future:
          > 24h  → 0
          > 4h   → 10%
          > 2h   → 25%
          <= 2h  → 50%
        """
        now = datetime.now(timezone.utc)
        pickup = booking.pickup_time
        if pickup is None:
            return Decimal("0.00")
        if pickup.tzinfo is None:
            pickup = pickup.replace(tzinfo=timezone.utc)

        hours_before = (pickup - now).total_seconds() / 3600.0
        final_price = booking.final_price or Decimal("0.00")

        if hours_before <= 0:
            return Decimal("0.00")
        if hours_before > 24:
            return Decimal("0.00")
        if hours_before > 4:
            return final_price * Decimal("0.10")
        if hours_before > 2:
            return final_price * Decimal("0.25")
        return final_price * Decimal("0.50")

    def _generate_booking_code(self) -> str:
        letters = ''.join(random.choices(string.ascii_uppercase, k=3))
        numbers = ''.join(random.choices(string.digits, k=3))
        return f"AFC{letters}{numbers}"

    def _invalidate_booking_caches(self, booking_id: int):
        cache.delete(f"{self.cache_prefix}:{booking_id}")
        self._invalidate_listing_caches()

    def _invalidate_listing_caches(self):
        try:
            client = getattr(cache.cache, "_client", None)
            if client is not None and callable(getattr(client, "scan_iter", None)):
                for key in client.scan_iter(f"{self.cache_prefix}:list:*"):
                    cache.delete(key)
                return
        except Exception:
            pass
        cache.delete(f"{self.cache_prefix}:list:recent")
        cache.delete(f"{self.cache_prefix}:list:all")


# =========================================================
# Demand signal for GEO aggregation (roadmap GEO-17)
# =========================================================

# Demand counts submitted requests EXCEPT drafts (never submitted) and
# cancellations (withdrawn). no_show/disputed stay: a request
# demonstrably existed. Transport-owned rule: GEO aggregates the
# points but never decides which bookings count.
DEMAND_EXCLUDED_STATUSES = (BookingStatus.DRAFT, BookingStatus.CANCELLED)


def booking_request_points(since, until):
    """Read-only authoritative demand points for GEO aggregation.

    Returns (points, skipped_invalid) where points are
    (latitude, longitude, None) tuples from booking pickup locations
    created in [since, until]. Only canonical latitude/longitude
    floats count; anything else is skipped and counted (never raise,
    never fabricate). No identifiers are returned.

    Raises ValueError on missing/invalid window.
    """
    from datetime import timezone as _tz

    if since is None or until is None:
        raise ValueError("since and until are required (ISO-8601)")
    try:
        start = (since if isinstance(since, datetime)
                 else datetime.fromisoformat(str(since).strip()))
        end = (until if isinstance(until, datetime)
               else datetime.fromisoformat(str(until).strip()))
    except (ValueError, AttributeError):
        raise ValueError("since/until must be ISO-8601 datetimes") from None
    if start.tzinfo is None:
        start = start.replace(tzinfo=_tz.utc)
    if end.tzinfo is None:
        end = end.replace(tzinfo=_tz.utc)
    if start > end:
        raise ValueError("since must not be after until")

    rows = (Booking.query
            .filter(Booking.is_deleted == False)  # noqa: E712
            .filter(~Booking.status.in_(DEMAND_EXCLUDED_STATUSES))
            .filter(Booking.created_at >= start,
                    Booking.created_at <= end)
            .all())
    points: List[Any] = []
    skipped = 0
    for booking in rows:
        loc = booking.pickup_location
        if not isinstance(loc, dict):
            skipped += 1
            continue
        try:
            lat = float(loc.get("latitude"))
            lng = float(loc.get("longitude"))
        except (TypeError, ValueError):
            skipped += 1
            continue
        if not (-90.0 <= lat <= 90.0 and -180.0 <= lng <= 180.0):
            skipped += 1
            continue
        points.append((lat, lng, None))
    return points, skipped


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

