"""
Booking State Machine - Manages booking lifecycle transitions independently from payment.

State Flow:
DRAFT → HELD → PENDING_APPROVAL → CONFIRMED → CHECKED_IN → CHECKED_OUT → CLOSED
              ↘         ↘             ↘
               EXPIRED   CANCELLED     NO_SHOW
               
Where READY_FOR_CHECKIN is a computed state, not stored in DB.
Payment state is handled by PaymentStateMachine separately.
"""

from app.accommodation.models.booking import AccommodationBookingStatus
from datetime import date, datetime, timezone
from decimal import Decimal
import logging

logger = logging.getLogger(__name__)


class InvalidStateTransition(Exception):
    """Raised when a booking state transition is invalid"""
    pass


class BookingStateMachine:
    """
    Manages booking state transitions with validation and history logging.
    
    This state machine is INDEPENDENT from payment state.
    Payment requirements for transitions are evaluated by BookingPolicyEvaluator.
    """

    # Valid state transitions (stored states only) - NO PAYMENT DEPENDENCIES
    # PENDING_PAYMENT is a valid booking state meaning "awaiting payment" but
    # payment is NOT required to transition to CONFIRMED - policy evaluator handles that
    VALID_TRANSITIONS = {
        AccommodationBookingStatus.DRAFT: [
            AccommodationBookingStatus.HELD,
            AccommodationBookingStatus.CANCELLED,
        ],
        AccommodationBookingStatus.HELD: [
            AccommodationBookingStatus.PENDING_PAYMENT,
            AccommodationBookingStatus.PENDING_APPROVAL,
            AccommodationBookingStatus.EXPIRED,
            AccommodationBookingStatus.CANCELLED,
        ],
        AccommodationBookingStatus.PENDING_PAYMENT: [
            AccommodationBookingStatus.CONFIRMED,
            AccommodationBookingStatus.CANCELLED,
            AccommodationBookingStatus.EXPIRED,
        ],
        AccommodationBookingStatus.PENDING_APPROVAL: [
            AccommodationBookingStatus.CONFIRMED,
            AccommodationBookingStatus.CANCELLED,
        ],
        AccommodationBookingStatus.CONFIRMED: [
            AccommodationBookingStatus.CHECKED_IN,
            AccommodationBookingStatus.CANCELLED,
            AccommodationBookingStatus.NO_SHOW,
        ],
        AccommodationBookingStatus.CHECKED_IN: [
            AccommodationBookingStatus.CHECKED_OUT,
            AccommodationBookingStatus.CANCELLED,
        ],
        AccommodationBookingStatus.CHECKED_OUT: [
            AccommodationBookingStatus.CLOSED,
        ],
        AccommodationBookingStatus.CANCELLED: [
            AccommodationBookingStatus.REFUNDED,
        ],
        AccommodationBookingStatus.CLOSED: [],
        AccommodationBookingStatus.REFUNDED: [],
        AccommodationBookingStatus.EXPIRED: [],
        AccommodationBookingStatus.NO_SHOW: [],
        # Legacy states (maintained for backward compatibility)
        AccommodationBookingStatus.PENDING: [
            AccommodationBookingStatus.PENDING_APPROVAL,
            AccommodationBookingStatus.CONFIRMED,
            AccommodationBookingStatus.CANCELLED,
            AccommodationBookingStatus.EXPIRED,
        ],
        AccommodationBookingStatus.PAYMENT_PARTIAL: [
            AccommodationBookingStatus.CONFIRMED,
            AccommodationBookingStatus.CANCELLED,
        ],
    }

    @classmethod
    def can_transition(
            cls,
            booking,
            new_status: AccommodationBookingStatus
    ) -> bool:
        """
        Check if booking can transition to new_status based on booking lifecycle ONLY.
        
        Payment requirements are NOT checked here - they are evaluated by
        BookingPolicyEvaluator.can_confirm() before calling transition().
        """
        current_enum = AccommodationBookingStatus(booking.status)

        if new_status not in cls.VALID_TRANSITIONS.get(current_enum, []):
            return False

        # CHECKED_IN is the computed READY_FOR_CHECKIN transition.
        if new_status == AccommodationBookingStatus.CHECKED_IN:
            return cls._can_check_in(booking)

        # Refunds require a positive refund amount (financial check, not payment state)
        if new_status == AccommodationBookingStatus.REFUNDED:
            refund_amt = getattr(booking, "refund_amount", 0)
            return bool(refund_amt and Decimal(str(refund_amt or 0)) > 0)

        return True

    @classmethod
    def _registration_satisfied(cls, booking) -> bool:
        """
        Registration gate for check-in.

        The registration deadline is a *soft* limit. It exists to nudge guests
        into registering early so hosts can prepare - it is not a reason to turn
        a paying guest away at the door.

        Rules:
          - Fully registered            -> allow.
          - Deadline passed, incomplete -> allow (host sees an "incomplete"
                                           warning and can capture details on
                                           arrival).
          - Deadline not yet passed,
            incomplete                  -> block, the guest still has time to
                                           register online.
          - No deadline set             -> allow.
        """
        if cls._all_guests_registered(booking):
            return True

        deadline = getattr(booking, "registration_deadline", None)
        if not deadline:
            # No deadline configured - registration is not enforced here.
            return True

        if deadline.tzinfo is None:
            deadline = deadline.replace(tzinfo=timezone.utc)

        if deadline < datetime.now(timezone.utc):
            # Deadline lapsed: warn, but never block the guest.
            logger.warning(
                "Booking %s checking in with incomplete registration "
                "(deadline %s passed).",
                getattr(booking, "id", "?"),
                deadline.isoformat(),
            )
            return True

        # Still within the window - keep the pressure on to register online.
        return False

    @classmethod
    def _can_check_in(cls, booking) -> bool:
        """
        Computed READY_FOR_CHECKIN status.
        Not stored in DB - always derived from current state.
        
        Payment status is NOT checked here. Check-in eligibility is based on:
        - Booking status is CONFIRMED
        - Check-in date has arrived
        - Registration requirements satisfied
        
        Payment policy requirements for check-in are evaluated by
        BookingPolicyEvaluator.can_check_in() before calling this.
        """
        if booking.status != AccommodationBookingStatus.CONFIRMED.value:
            return False

        if booking.check_in > date.today():
            return False

        # Registration check only - NO payment status check
        return cls._registration_satisfied(booking)

    @classmethod
    def _all_guests_registered(cls, booking) -> bool:
        """
        Check if all required guests are registered for this booking.
        A guest is considered registered if a GuestRegistration record exists
        with status completed or skipped (host override).
        """
        try:
            from app.accommodation.models.guest_registration import GuestRegistration
            registrations = GuestRegistration.query.filter_by(booking_id=booking.id).all()
            if not registrations:
                return False
            return all(
                r.status in ("completed", "skipped") for r in registrations
            )
        except Exception:
            # If the model/table doesn't exist yet, fall back to legacy check
            return bool(booking.primary_guest_id or booking.guest_user_id or booking.guest_email)

    @classmethod
    def get_next_states(
            cls,
            current_status: AccommodationBookingStatus
    ) -> list:
        """Return all valid next states from current_status"""
        return cls.VALID_TRANSITIONS.get(current_status, [])

    @classmethod
    def is_terminal(
            cls,
            status: AccommodationBookingStatus
    ) -> bool:
        """Return True if status has no further transitions"""
        return len(cls.VALID_TRANSITIONS.get(status, [])) == 0

    @classmethod
    def transition(
            cls,
            booking,
            new_status: AccommodationBookingStatus,
            changed_by_user_id: int = None,
            reason: str = None,
            ip_address: str = None,
            user_agent: str = None,
            trigger: str = None,
            metadata: dict = None,
    ):
        """
        Transition booking to new_status with validation and history record.

        Args:
            booking:             The AccommodationBooking instance
            new_status:          Target AccommodationBookingStatus enum
            changed_by_user_id:  User performing the transition (None = system)
            reason:              Optional reason string
            ip_address:          Request IP for audit trail
            user_agent:          Request user-agent for audit trail
            trigger:             What triggered this transition
            metadata:            Additional context as dict

        Returns:
            The updated booking instance

        Raises:
            InvalidStateTransition: If the transition is not allowed
        """
        from app.extensions import db
        from app.accommodation.models.booking import BookingStatusHistory
        from decimal import Decimal

        # Validate transition
        if not cls.can_transition(booking, new_status):
            raise InvalidStateTransition(
                f"Cannot transition booking {booking.booking_reference or booking.id} "
                f"from '{booking.status}' to '{new_status.value}'"
            )

        old_status_string = booking.status
        new_status_string = new_status.value

        # Record transition in history with trigger and metadata
        history = BookingStatusHistory(
            booking_id=booking.id,
            from_status=old_status_string,
            to_status=new_status_string,
            changed_by=changed_by_user_id,
            trigger=trigger,
            change_metadata={
                **(metadata or {}),
                "reason": reason,
                "ip_address": ip_address,
                "user_agent": user_agent,
            },
        )
        db.session.add(history)

        # Apply the transition
        booking.status = new_status_string

        logger.info(
            f"Booking transition: {booking.booking_reference or booking.id} | "
            f"{old_status_string} → {new_status_string} | "
            f"By: {changed_by_user_id or 'system'} | "
            f"Trigger: {trigger or 'none'} | "
            f"Reason: {reason or 'none'}"
        )

        return booking