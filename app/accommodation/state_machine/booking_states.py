# app/accommodation/state_machine/booking_states.py
"""
Booking State Machine - Manages booking lifecycle transitions.

State Flow:
PENDING → CONFIRMED → CHECKED_IN → CHECKED_OUT
               ↓
           CANCELLED → REFUNDED
"""

from app.accommodation.models.booking import AccommodationBookingStatus
import logging

logger = logging.getLogger(__name__)


class InvalidStateTransition(Exception):
    """Raised when a booking state transition is invalid"""
    pass


class BookingStateMachine:
    """
    Manages booking state transitions with validation and history logging.
    """

    VALID_TRANSITIONS = {
        AccommodationBookingStatus.PENDING: [
            AccommodationBookingStatus.CONFIRMED,
            AccommodationBookingStatus.CANCELLED,
        ],
        AccommodationBookingStatus.CONFIRMED: [
            AccommodationBookingStatus.CHECKED_IN,
            AccommodationBookingStatus.CANCELLED,
        ],
        AccommodationBookingStatus.CHECKED_IN: [
            AccommodationBookingStatus.CHECKED_OUT,
        ],
        AccommodationBookingStatus.CHECKED_OUT: [],   # Terminal
        AccommodationBookingStatus.CANCELLED: [
            AccommodationBookingStatus.REFUNDED,
        ],
        AccommodationBookingStatus.REFUNDED: [],      # Terminal
        AccommodationBookingStatus.NO_SHOW: [],       # Terminal
    }

    @classmethod
    def can_transition(
        cls,
        booking,
        new_status: AccommodationBookingStatus
    ) -> bool:
        """Check if booking can transition to new_status"""
        return new_status in cls.VALID_TRANSITIONS.get(booking.status, [])

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
    ):
        """
        Transition booking to new_status with validation and history record.

        Args:
            booking:             The AccommodationBooking instance
            new_status:          Target AccommodationBookingStatus
            changed_by_user_id:  User performing the transition (None = system)
            reason:              Optional reason string
            ip_address:          Request IP for audit trail
            user_agent:          Request user-agent for audit trail

        Returns:
            The updated booking instance

        Raises:
            InvalidStateTransition: If the transition is not allowed
        """
        from app.extensions import db
        from app.accommodation.models.booking import BookingStatusHistory

        if not cls.can_transition(booking, new_status):
            raise InvalidStateTransition(
                f"Cannot transition booking {booking.booking_reference} "
                f"from '{booking.status.value}' to '{new_status.value}'"
            )

        old_status = booking.status

        # Record transition in history
        history = BookingStatusHistory(
            booking_id=booking.id,
            from_status=old_status,
            to_status=new_status,
            changed_by_user_id=changed_by_user_id,
            reason=reason,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        db.session.add(history)

        # Apply the transition
        booking.status = new_status

        logger.info(
            f"Booking transition: {booking.booking_reference} | "
            f"{old_status.value} → {new_status.value} | "
            f"By: {changed_by_user_id or 'system'} | "
            f"Reason: {reason or 'none'}"
        )

        return booking