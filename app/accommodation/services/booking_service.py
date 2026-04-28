# app/accommodation/services/booking_service.py
"""
Booking Service - Production-grade booking creation, confirmation, and cancellation
Includes: Idempotency, anti-abuse, temporary holds, state management, and audit logging
"""

from datetime import datetime, date, timedelta
from decimal import Decimal
from typing import Union, Optional, List, Tuple
import enum
import logging

from app.extensions import db
from app.admin.models import ContentFlag
from app.accommodation.models.booking import (
    AccommodationBooking,
    AccommodationBookingStatus,
    AccommodationPaymentStatus,
    BookingContextType
)
from app.accommodation.models.availability import AccommodationBlockedReason
from app.accommodation.services.availability_service import AvailabilityService
from app.accommodation.services.pricing_service import PricingService
from app.accommodation.state_machine.booking_states import BookingStateMachine, InvalidStateTransition

logger = logging.getLogger(__name__)


def _assert_no_open_flags(entity_type: str, entity_id: int):
    """Raise ValueError if the entity has any unresolved ContentFlag records."""
    count = ContentFlag.query.filter_by(
        entity_type=entity_type,
        entity_id=entity_id,
        status="open",
    ).count()
    if count:
        raise ValueError(
            f"Cannot activate {entity_type} {entity_id}: open flags must be resolved first."
        )

def enum_value(val):
    """
    Helper to safely convert Enum to string for DB or service calls.
    If `val` is an enum, returns its `.value`, else returns val as-is.
    """
    return val.value if isinstance(val, enum.Enum) else val


class BookingService:
    """
    Production-grade booking service with:
    - Idempotency (prevents duplicate bookings)
    - Anti-abuse prevention (rate limiting, hold limits)
    - Temporary holds for pending bookings
    - Atomic transactions with rollback
    - Full state machine integration
    - Audit logging via logger
    """

    # -------------------------
    # CREATE BOOKING
    # -------------------------
    @staticmethod
    def create_booking(
        property_id: int,
        guest_user_id: int,
        host_user_id: int,
        check_in: date,
        check_out: date,
        num_guests: int,
        guest_name: str,
        guest_email: str,
        guest_phone: str = None,
        special_requests: str = None,
        idempotency_key: str = None,
        ip_address: str = None,
        user_agent: str = None,
        context_type: 'BookingContextType' = None,  # Will import at top
        context_id: str = None,
        context_metadata: dict = None,
    ) -> Tuple[Optional[AccommodationBooking], Optional[str]]:


        """
        Create a new booking with temporary hold.

        Returns:
            (booking, error_message) - booking is None if error
        """
        from app.accommodation.models.property import Property

        try:
            # 1. IDEMPOTENCY CHECK
            if idempotency_key:
                existing = AccommodationBooking.query.filter_by(
                    idempotency_key=idempotency_key,
                    guest_user_id=guest_user_id
                ).first()
                if existing:
                    logger.info(f"Duplicate booking prevented: {idempotency_key}")
                    return existing, None

            # 2. BASIC VALIDATION
            if check_out <= check_in:
                return None, "Check-out must be after check-in"

            property = Property.query.get(property_id)
            if not property:
                return None, "Property not found"

            if not property.can_be_booked():
                return None, "Property is not available for booking"

            # 3. ANTI-ABUSE PREVENTION (OPTIONAL)
            try:
                from app.accommodation.services.abuse_prevention_service import AbusePreventionService

                ok, msg = AbusePreventionService.check_user_hold_limit(guest_user_id)
                if not ok:
                    return None, msg

                ok, msg = AbusePreventionService.check_property_hold_limit(property_id)
                if not ok:
                    return None, msg

                ok, msg = AbusePreventionService.check_rate_limit(guest_user_id)
                if not ok:
                    return None, msg

                ok, msg = AbusePreventionService.detect_suspicious_behavior(guest_user_id)
                if not ok:
                    return None, msg

            except ImportError:
                logger.debug("Anti-abuse service not available, skipping checks")
            except Exception as e:
                logger.warning(f"Anti-abuse check failed: {e}")

            # 4. AVAILABILITY CHECK
            is_available, blocked_dates, error = AvailabilityService.is_range_available(
                property_id, check_in, check_out
            )
            if not is_available:
                return None, error or "Selected dates are not available"

            # 5. PRICE CALCULATION
            try:
                pricing = PricingService.calculate_total(
                    property, check_in, check_out, num_guests
                )
            except ValueError as e:
                return None, str(e)

            # 6. CREATE BOOKING (PENDING STATE)
            booking = AccommodationBooking(
                property_id=property_id,
                guest_user_id=guest_user_id,
                host_user_id=host_user_id,
                check_in=check_in,
                check_out=check_out,
                num_nights=pricing['nights'],
                num_guests=num_guests,
                nightly_rate=pricing['nightly_rate'],
                cleaning_fee=pricing['cleaning_fee'],
                service_fee=pricing['service_fee'],
                total_amount=pricing['total'],
                currency=property.currency,
                guest_name=guest_name,
                guest_email=guest_email,
                guest_phone=guest_phone,
                special_requests=special_requests,
                context_type=context_type or BookingContextType.NONE,
                context_id=context_id,
                context_metadata=context_metadata or {},
                idempotency_key=idempotency_key,
                status=AccommodationBookingStatus.PENDING.value,
                payment_status=AccommodationPaymentStatus.PENDING.value,
                expires_at=datetime.utcnow() + timedelta(minutes=15)  # 15 min hold
            )

            booking.generate_reference()
            db.session.add(booking)
            db.session.flush()  # Get booking ID before blocking dates

            # 7. TEMPORARY HOLD ON DATES
            AvailabilityService.block_dates(
                property_id=booking.property_id,
                check_in=booking.check_in,
                check_out=booking.check_out,
                reason=enum_value(AccommodationBlockedReason.TEMPORARY_HOLD),
                booking_id=booking.id,
                created_by=guest_user_id
            )

            db.session.commit()

            logger.info(
                f"Booking created: {booking.booking_reference} | "
                f"Property: {property_id} | Guest: {guest_user_id} | "
                f"Amount: ${booking.total_amount} | Dates: {check_in} → {check_out}"
            )

            return booking, None

        except Exception as e:
            db.session.rollback()
            logger.error(f"Create booking failed for property {property_id}: {e}", exc_info=True)
            return None, "Unable to create booking. Please try again."

    # -------------------------
    # CONFIRM BOOKING
    # -------------------------
    @staticmethod
    def confirm_booking(
        booking_id: int,
        wallet_transaction_id: str = None,
        ip_address: str = None,
        user_agent: str = None
    ) -> Tuple[bool, Optional[str]]:
        """
        Confirm a booking after successful payment.
        Converts temporary hold to permanent booked status.
        """
        booking = AccommodationBooking.query.get(booking_id)

        if not booking:
            return False, "Booking not found"

        if booking.payment_status == AccommodationPaymentStatus.PAID.value:
            return False, "Booking already paid and confirmed"

        if booking.status != AccommodationBookingStatus.PENDING.value:
            return False, f"Cannot confirm booking in {booking.status.value} state"

        if booking.expires_at and booking.expires_at < datetime.utcnow():
            return False, "Booking has expired. Please create a new booking."

        try:
            # 1. RE-VERIFY AVAILABILITY (Exclude own hold)
            is_available, blocked_dates, error = AvailabilityService.is_range_available(
                booking.property_id,
                booking.check_in,
                booking.check_out,
                exclude_booking_id=booking.id
            )
            if not is_available:
                return False, error or "Dates are no longer available. Please contact support."

            # Guard: cannot confirm booking if there are open ContentFlag records
            _assert_no_open_flags("accommodation_booking", booking.id)

            # 2. CONVERT TEMPORARY HOLD → PERMANENT BOOKED
            from app.accommodation.models.availability import BlockedDate
            BlockedDate.query.filter_by(booking_id=booking.id).update(
                {"reason": enum_value(AccommodationBlockedReason.BOOKED)}
            )

            # 3. UPDATE PAYMENT STATUS
            booking.payment_status = AccommodationPaymentStatus.PAID
            booking.wallet_txn_id = wallet_transaction_id
            booking.paid_at = datetime.utcnow()

            # 4. STATE TRANSITION (PENDING → CONFIRMED)
            BookingStateMachine.transition(
                booking,
                AccommodationBookingStatus.CONFIRMED,
                changed_by_user_id=booking.guest_user_id,
                reason="Payment confirmed",
                ip_address=ip_address,
                user_agent=user_agent
            )

            db.session.commit()
            logger.info(
                f"Booking confirmed: {booking.booking_reference} | "
                f"Transaction: {wallet_transaction_id} | "
                f"Amount: ${booking.total_amount}"
            )

            return True, None

        except InvalidStateTransition as e:
            db.session.rollback()
            logger.error(f"Invalid state transition for booking {booking_id}: {e}")
            return False, str(e)
        except Exception as e:
            db.session.rollback()
            logger.error(f"Confirm booking failed for {booking_id}: {e}", exc_info=True)
            return False, "Unable to confirm booking. Please contact support."

    # -------------------------
    # CANCEL BOOKING
    # -------------------------
    @staticmethod
    def cancel_booking(
        booking_id: int,
        cancelled_by_user_id: int,
        reason: str = None,
        ip_address: str = None,
        user_agent: str = None
    ) -> Tuple[bool, Optional[str], Optional[Decimal]]:
        """
        Cancel a booking and process refund if applicable.
        """
        booking = AccommodationBooking.query.get(booking_id)

        if not booking:
            return False, "Booking not found", None

        can_cancel, msg, refund = booking.can_cancel()
        if not can_cancel:
            return False, msg, None

        try:
            from app.accommodation.models.availability import BlockedDate

            # 1. RELEASE ALL BLOCKED DATES
            BlockedDate.query.filter_by(booking_id=booking.id).delete()
            logger.debug(f"Released dates for booking {booking.booking_reference}")

            # 2. STATE TRANSITION (→ CANCELLED)
            BookingStateMachine.transition(
                booking,
                AccommodationBookingStatus.CANCELLED,
                changed_by_user_id=cancelled_by_user_id,
                reason=reason,
                ip_address=ip_address,
                user_agent=user_agent
            )

            booking.cancelled_at = datetime.utcnow()
            booking.cancelled_by_user_id = cancelled_by_user_id
            booking.cancellation_reason = reason

            # 3. PROCESS REFUND IF APPLICABLE
            if refund and refund > 0:
                booking.refund_amount = refund
                booking.payment_status = AccommodationPaymentStatus.REFUNDED
                booking.refunded_at = datetime.utcnow()
                BookingStateMachine.transition(
                    booking,
                    AccommodationBookingStatus.REFUNDED,
                    changed_by_user_id=cancelled_by_user_id,
                    reason="Refund processed",
                    ip_address=ip_address,
                    user_agent=user_agent
                )
                logger.info(f"Refund of ${refund} processed for booking {booking.booking_reference}")

            db.session.commit()
            logger.info(
                f"Booking cancelled: {booking.booking_reference} | "
                f"Cancelled by: {cancelled_by_user_id} | "
                f"Refund: ${refund if refund else 0} | Reason: {reason}"
            )

            return True, msg, refund

        except InvalidStateTransition as e:
            db.session.rollback()
            logger.error(f"Invalid state transition for cancellation {booking_id}: {e}")
            return False, str(e), None
        except Exception as e:
            db.session.rollback()
            logger.error(f"Cancel booking failed for {booking_id}: {e}", exc_info=True)
            return False, "Unable to cancel booking. Please contact support.", None

    # -------------------------
    # QUERY METHODS
    # -------------------------
    @staticmethod
    def get_booking_by_reference(reference: str) -> Optional[AccommodationBooking]:
        return AccommodationBooking.query.filter_by(booking_reference=reference).first()

    @staticmethod
    def get_user_bookings(user_id: int, status: str = None, limit: int = 50, offset: int = 0) -> list:
        query = AccommodationBooking.query.filter_by(guest_user_id=user_id)
        if status:
            try:
                query = query.filter_by(status=AccommodationBookingStatus(status).value)
            except ValueError:
                logger.warning(f"Invalid status filter: {status}")
        return query.order_by(AccommodationBooking.created_at.desc()).limit(limit).offset(offset).all()

    @staticmethod
    def get_host_bookings(host_user_id: int, status: str = None, limit: int = 50, offset: int = 0) -> list:
        query = AccommodationBooking.query.filter_by(host_user_id=host_user_id)
        if status:
            try:
                query = query.filter_by(status=AccommodationBookingStatus(status))
            except ValueError:
                logger.warning(f"Invalid status filter: {status}")
        return query.order_by(AccommodationBooking.created_at.desc()).limit(limit).offset(offset).all()

    @staticmethod
    def get_property_bookings(property_id: int, status: str = None, limit: int = 100, offset: int = 0) -> list:
        query = AccommodationBooking.query.filter_by(property_id=property_id)
        if status:
            try:
                query = query.filter_by(status=AccommodationBookingStatus(status))
            except ValueError:
                logger.warning(f"Invalid status filter: {status}")
        return query.order_by(AccommodationBooking.check_in.asc()).limit(limit).offset(offset).all()

    @staticmethod
    def get_pending_expired_bookings() -> list:
        return AccommodationBooking.query.filter(
            AccommodationBooking.status == AccommodationBookingStatus.PENDING.value,
            AccommodationBooking.expires_at < datetime.utcnow()
        ).all()

    @staticmethod
    def cleanup_expired_bookings() -> int:
        expired_bookings = BookingService.get_pending_expired_bookings()
        count = 0
        for booking in expired_bookings:
            try:
                success, _, _ = BookingService.cancel_booking(
                    booking.id,
                    cancelled_by_user_id=None,
                    reason="Booking expired (payment not completed)",
                    ip_address="system",
                    user_agent="system"
                )
                if success:
                    count += 1
                    logger.info(f"Cleaned up expired booking: {booking.booking_reference}")
            except Exception as e:
                logger.error(f"Failed to clean up expired booking {booking.id}: {e}")
        return count

    from typing import Optional, Union, List

    # ... rest of your code ...

    @staticmethod
    def get_bookings_by_context(
            context_type: Union[str, BookingContextType],
            context_id: Optional[str] = None,
            limit: Optional[int] = 100
    ) -> List[AccommodationBooking]:
        """
        Get bookings for a specific context (event, tour, etc.).

        Args:
            context_type: Context type as string or BookingContextType enum.
            context_id: Optional specific context ID to filter.
            limit: Maximum number of results to return. Use None for no limit.

        Returns:
            List of AccommodationBooking instances.
        """
        # Convert string to enum safely
        if isinstance(context_type, str):
            try:
                context_type = BookingContextType(context_type)
            except ValueError:
                logger.warning(f"Invalid context_type: {context_type}")
                return []

        # Build and execute query
        query = AccommodationBooking.query.filter_by(
            context_type=context_type
        ).order_by(AccommodationBooking.created_at.desc())

        if context_id:
            query = query.filter_by(context_id=context_id)

        if limit is not None:
            query = query.limit(limit)

        return query.all()
