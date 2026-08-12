"""
Booking State Machine - Manages booking lifecycle transitions.

State Flow (Specification compliant):
DRAFT → HELD → PENDING_PAYMENT → CONFIRMED → [READY_FOR_CHECKIN] → CHECKED_IN → CHECKED_OUT → CLOSED
                                          ↘                          ↘            ↘
                                           CANCELLED                  NO_SHOW      CLOSED
                                               ↓                          ↑
                                         EXPIRED                (after review)

Where [READY_FOR_CHECKIN] is a computed state, not stored in DB.
"""

from app.accommodation.models.booking import AccommodationBookingStatus, AccommodationPaymentStatus
from datetime import date, datetime, timezone
import logging

logger = logging.getLogger(__name__)


class InvalidStateTransition(Exception):
    """Raised when a booking state transition is invalid"""
    pass


class BookingStateMachine:
    """
    Manages booking state transitions with validation and history logging.
    """

    # Valid state transitions (stored states only)
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
            AccommodationBookingStatus.PENDING_PAYMENT,
            AccommodationBookingStatus.CONFIRMED,
            AccommodationBookingStatus.CANCELLED,
            AccommodationBookingStatus.PENDING_APPROVAL,
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
        Check if booking can transition to new_status.
        Includes computed state logic for READY_FOR_CHECKIN.
        """
        current_enum = AccommodationBookingStatus(booking.status)

        if new_status not in cls.VALID_TRANSITIONS.get(current_enum, []):
            return False

        # CHECKED_IN is the computed READY_FOR_CHECKIN transition.
        if new_status == AccommodationBookingStatus.CHECKED_IN:
            return cls._can_check_in(booking)

        # Payment-confirmed transitions must have a settled/guaranteed payment.
        if (
            new_status == AccommodationBookingStatus.CONFIRMED
            and current_enum in [
                AccommodationBookingStatus.PENDING_PAYMENT,
                AccommodationBookingStatus.PAYMENT_PARTIAL,
            ]
        ):
            return cls._payment_satisfied(booking)

        # Host-approval transitions require the approval marker to be set first.
        if (
            new_status == AccommodationBookingStatus.CONFIRMED
            and current_enum == AccommodationBookingStatus.PENDING_APPROVAL
        ):
            return bool(getattr(booking, "host_approved_at", None))

        # Refunds must have a positive refund amount and a refunded payment status.
        if new_status == AccommodationBookingStatus.REFUNDED:
            return (
                getattr(booking, "refund_amount", 0)
                and booking.payment_status == AccommodationPaymentStatus.REFUNDED.value
            )

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
        """
        if booking.status != AccommodationBookingStatus.CONFIRMED.value:
            return False

        if booking.check_in > date.today():
            return False

        # Paid / deposit-paid bookings are always eligible.
        if booking.payment_status in [
            AccommodationPaymentStatus.PAID.value,
            AccommodationPaymentStatus.PARTIALLY_PAID.value,
        ]:
            return cls._registration_satisfied(booking)

        # Pay-on-arrival / cash bookings: allow UNPAID if guest/cash is eligible.
        if booking.payment_status == AccommodationPaymentStatus.UNPAID.value:
            return cls._cash_eligible_at_checkin(booking) and cls._registration_satisfied(booking)

        return False

    @classmethod
    def _cash_eligible_at_checkin(cls, booking) -> bool:
        """Return True when an UNPAID booking is allowed to check in with cash."""
        from app.accommodation.services.booking_service import check_cash_eligibility
        from app.identity.models.user import User
        from app.extensions import db
        guest_user_id = getattr(booking, "guest_user_id", None)
        if not guest_user_id:
            return False
        try:
            guest_user = db.session.get(User, guest_user_id)
            result = check_cash_eligibility(
                guest_user=guest_user,
                property_id=booking.property_id,
                booking_amount=booking.total_amount or 0,
            )
            return bool(result.get("allowed")) if isinstance(result, dict) else False
        except Exception:
            return False

    @classmethod
    def _payment_satisfied(cls, booking) -> bool:
        """Return True when the booking has enough payment signal to confirm."""
        return (
            booking.payment_status in [
                AccommodationPaymentStatus.PAID.value,
                AccommodationPaymentStatus.PARTIALLY_PAID.value,
            ]
            or bool(getattr(booking, "payment_guaranteed", False))
        )

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

