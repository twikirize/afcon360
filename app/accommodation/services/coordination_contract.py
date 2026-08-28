"""Accommodation-owned contract for cross-module event coordination.

This is the ONLY surface the Events module may use to influence accommodation
guest state. It keeps accommodation state ownership inside the accommodation
module: Events never writes GuestRegistration / BookingRegistrationLink
directly. The Events side generates and stores any raw invite token; this
contract only ever persists the SHA-256 hash of that token.

Module independence rule: Events MUST NOT import accommodation models or
write accommodation tables directly. All writes go through this contract.
"""

from sqlalchemy.exc import SQLAlchemyError

from app.extensions import db


class CoordinationContractError(Exception):
    """Accommodation contract failure returned to the caller."""

    def __init__(self, code: str, message: str = ""):
        self.code = code
        self.message = message or code
        super().__init__(self.message)


class AccommodationCoordinationContract:
    """Public write contract for Accommodation from other modules."""

    @staticmethod
    def ensure_event_guest_slot(
        booking_reference: str,
        *,
        full_name: str,
        email: str = None,
        phone: str = None,
        nationality: str = None,
        user_id: int = None,
        event_assignment_id: int = None,
    ) -> dict:
        """Create or update a GuestRegistration slot pre-filled from an event
        attendee. Idempotent by (booking_id, guest_email or guest_user_id).

        Returns a dict with ``slot_id``, ``status``, ``email_present``.
        """
        from app.accommodation.models.booking import AccommodationBooking
        from app.accommodation.models.guest_registration import GuestRegistration
        from sqlalchemy import text

        # Lock the booking row to prevent race conditions while enforcing capacity
        booking = AccommodationBooking.query.filter_by(
            booking_reference=booking_reference, is_deleted=False
        ).with_for_update().first()
        if not booking:
            raise CoordinationContractError(
                "BOOKING_NOT_FOUND", "Accommodation booking was not found"
            )

        # Acquire advisory lock on booking ID to serialize capacity checks
        # This works correctly with REPEATABLE_READ isolation level
        db.session.execute(text("SELECT pg_advisory_xact_lock(:bid)"), {"bid": booking.id})

        # Idempotent check: if an active slot already exists for this assignment, return it
        if event_assignment_id is not None:
            slot = GuestRegistration.query.filter_by(
                booking_id=booking.id,
                event_assignment_id=event_assignment_id,
                is_active=True,
            ).first()
            if slot:
                return {
                    "slot_id": slot.id,
                    "status": slot.status,
                    "email_present": bool(slot.guest_email),
                }

        email_norm = (email or "").strip().lower() or None
        slot = None
        if email_norm:
            slot = GuestRegistration.query.filter_by(
                booking_id=booking.id, guest_email=email_norm, is_active=True
            ).first()
        if slot is None and user_id:
            slot = GuestRegistration.query.filter_by(
                booking_id=booking.id, guest_user_id=user_id, is_active=True
            ).first()
        if slot is None:
            slot = GuestRegistration(booking_id=booking.id)
            db.session.add(slot)
        if event_assignment_id is not None:
            slot.event_assignment_id = event_assignment_id

        slot.guest_name = (full_name or slot.guest_name or "Guest").strip()[:255]
        if email_norm:
            slot.guest_email = email_norm[:255]
        if phone:
            slot.guest_phone = phone.strip()[:50]
        if nationality:
            slot.nationality = nationality.strip()[:100]
        if user_id:
            slot.guest_user_id = user_id
        slot.registration_source = "event_coordination"
        slot.is_placeholder = not bool(email_norm)
        slot.status = "in_progress" if (slot.guest_name and slot.guest_email) else "pending"
        db.session.flush()

        # Enforce authoritative capacity: active guest slots must not exceed the booking's allowed guests
        active_count = GuestRegistration.query.filter_by(
            booking_id=booking.id, is_active=True
        ).count()
        allowed = booking.num_guests or 0
        if active_count > allowed:
            raise CoordinationContractError(
                "BOOKING_CAPACITY_EXCEEDED",
                "Accommodation booking capacity exceeded",
            )

        return {
            "slot_id": slot.id,
            "status": slot.status,
            "email_present": bool(email_norm),
        }

    @staticmethod
    def ensure_registration_link(
        booking_reference: str,
        token_hash: str,
        *,
        max_registrants: int = None,
        expires_at=None,
    ) -> bool:
        """Persist a registration link for the booking. If one already exists,
        its ``token_hash`` is rotated to the new value (the raw token is never
        stored by Accommodation). Caller must re-email the new link.

        Returns True on success.
        """
        from app.accommodation.models.booking import AccommodationBooking
        from app.accommodation.models.booking_registration_link import BookingRegistrationLink

        booking = AccommodationBooking.query.filter_by(
            booking_reference=booking_reference, is_deleted=False
        ).first()
        if not booking:
            raise CoordinationContractError(
                "BOOKING_NOT_FOUND", "Accommodation booking was not found"
            )

        link = BookingRegistrationLink.query.filter_by(booking_id=booking.id).first()
        if link is None:
            link = BookingRegistrationLink(
                booking_id=booking.id,
                token_hash=token_hash,
                max_registrants=max(1, int(max_registrants or booking.num_guests or 1)),
                expires_at=expires_at,
            )
            db.session.add(link)
        else:
            link.token_hash = token_hash
            if expires_at is not None:
                link.expires_at = expires_at
        db.session.flush()
        return True
