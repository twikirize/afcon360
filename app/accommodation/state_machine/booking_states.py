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
        AccommodationBookingStatus.CHECKED_OUT: [],  # Terminal
        AccommodationBookingStatus.CANCELLED: [
            AccommodationBookingStatus.REFUNDED,
        ],
        AccommodationBookingStatus.REFUNDED: [],  # Terminal
        AccommodationBookingStatus.NO_SHOW: [],  # Terminal
    }

    @classmethod
    def can_transition(
            cls,
            booking,
            new_status: AccommodationBookingStatus
    ) -> bool:
        """
        Check if booking can transition to new_status.

        Args:
            booking: AccommodationBooking instance (status is stored as string)
            new_status: Target AccommodationBookingStatus enum

        Returns:
            bool: True if transition is valid
        """
        # Convert the stored string status to enum for comparison
        current_enum = AccommodationBookingStatus(booking.status)
        return new_status in cls.VALID_TRANSITIONS.get(current_enum, [])

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
            booking:             The AccommodationBooking instance (status is stored as string)
            new_status:          Target AccommodationBookingStatus enum
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

        # Convert the stored string status to enum for validation
        current_enum = AccommodationBookingStatus(booking.status)

        # Check if transition is valid
        if new_status not in cls.VALID_TRANSITIONS.get(current_enum, []):
            raise InvalidStateTransition(
                f"Cannot transition booking {booking.booking_reference} "
                f"from '{booking.status}' to '{new_status.value}'"
            )

        old_status_string = booking.status
        new_status_string = new_status.value

        # Record transition in history (store as strings)
        history = BookingStatusHistory(
            booking_id=booking.id,
            from_status=old_status_string,
            to_status=new_status_string,
            changed_by_user_id=changed_by_user_id,
            reason=reason,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        db.session.add(history)

        # Apply the transition (store as string)
        booking.status = new_status_string

        logger.info(
            f"Booking transition: {booking.booking_reference} | "
            f"{old_status_string} → {new_status_string} | "
            f"By: {changed_by_user_id or 'system'} | "
            f"Reason: {reason or 'none'}"
        )

        return booking
