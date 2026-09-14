"""Transport-owned contract for cross-module event coordination.

This is the ONLY surface the Events module may use to influence Transport
passenger/booking state. It keeps the transport-domain rules (capacity,
driver and vehicle eligibility, booking assignability, passenger reservation
lifecycle, and the booking -> event tag) inside the Transport module:

  - Events never writes Booking / TransportPassenger directly.
  - Events owns event scope only: which booking reference belongs to its
    event (EventAssignment.transport_booking_id pointer) and the coordination
    transaction boundary.
  - Transport owns the reservation: ``ensure_passenger_reservation``,
    ``release_passenger``, ``validate_booking_for_assignment`` and
    ``tag_booking_for_event``.

Module independence rule: Events MUST NOT import transport models or write
transport tables for assignment lifecycle; all *writes* go through this
contract. Reading transport state (dashboards, exports, summaries) remains a
read and is intentionally not routed through this contract.
"""

from datetime import datetime, timezone

from sqlalchemy import text

from app.extensions import db
from app.utils.audit import audit_log


class TransportCoordinationContractError(Exception):
    """Transport contract failure returned to the caller."""

    def __init__(self, code: str, message: str = ""):
        self.code = code
        self.message = message or code
        super().__init__(self.message)


class TransportCoordinationContract:
    """Public write contract for Transport state from other modules.

    Transport owns:
      - passenger reservation lifecycle (TransportPassenger)
      - capacity (the booking's declared seat target and the assigned
        vehicle's seat capacity)
      - driver/vehicle eligibility for event assignment
      - booking assignability (status) and the booking -> event tag
    """

    # The set of Booking statuses that may back an active event transport
    # assignment. Owned by Transport; Events reflects this set only for
    # read-side "still assignable" presentation.
    ASSIGNABLE_BOOKING_STATUSES = frozenset(("confirmed", "assigned"))

    # Verification tiers that qualify a driver for event service.
    EVENT_VERIFIED_TIERS = frozenset(("platform_verified", "event_certified"))

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _status_value(value) -> str:
        return str(getattr(value, "value", value) or "").lower()

    @classmethod
    def _load_booking(cls, booking_reference: str, *, lock: bool):
        """Resolve a Booking by public reference, with a legacy numeric-ID
        fallback that is never trusted without the eligibility checks below."""
        from app.transport.models import Booking

        ref = str(booking_reference or "").strip()
        if not ref:
            raise TransportCoordinationContractError(
                "TRANSPORT_BOOKING_NOT_FOUND",
                "Transport booking reference is required",
            )
        query = Booking.query.filter_by(booking_reference=ref, is_deleted=False)
        if lock:
            query = query.with_for_update()
        booking = query.first()
        if booking is None and ref.isdigit():
            query = Booking.query.filter_by(id=int(ref), is_deleted=False)
            if lock:
                query = query.with_for_update()
            booking = query.first()
        if booking is None:
            raise TransportCoordinationContractError(
                "TRANSPORT_BOOKING_NOT_FOUND",
                "Transport booking was not found",
            )
        return booking

    @classmethod
    def _validate_booking(cls, booking) -> None:
        """Transport-domain eligibility: status, driver, vehicle, capacity.

        This is the single source of truth for whether a Booking may back an
        active event transport assignment. Events must not re-implement these
        rules; it only resolves event scope and delegates here.
        """
        from app.transport.models import DriverProfile, Vehicle

        if cls._status_value(booking.status) not in cls.ASSIGNABLE_BOOKING_STATUSES:
            raise TransportCoordinationContractError(
                "TRANSPORT_BOOKING_UNAVAILABLE",
                "Transport booking is not assignable",
            )

        driver = getattr(booking, "driver", None) or db.session.get(
            DriverProfile, booking.assigned_driver_id
        )
        vehicle = getattr(booking, "vehicle", None) or db.session.get(
            Vehicle, booking.assigned_vehicle_id
        )
        if driver is None or vehicle is None:
            raise TransportCoordinationContractError(
                "TRANSPORT_RESOURCE_INCOMPLETE",
                "Transport booking has no eligible driver and vehicle",
            )
        if (
            getattr(driver, "is_deleted", False)
            or not getattr(driver, "is_available", False)
            or not getattr(driver, "is_online", False)
        ):
            raise TransportCoordinationContractError(
                "DRIVER_UNAVAILABLE",
                "The assigned driver is not available",
            )
        if cls._status_value(getattr(driver, "compliance_status", None)) != "approved":
            raise TransportCoordinationContractError(
                "DRIVER_NOT_APPROVED",
                "The assigned driver is not approved",
            )
        if cls._status_value(getattr(driver, "verification_tier", None)) not in cls.EVENT_VERIFIED_TIERS:
            raise TransportCoordinationContractError(
                "DRIVER_NOT_APPROVED",
                "The assigned driver is not verified for event service",
            )
        if getattr(vehicle, "is_deleted", False) or cls._status_value(
            getattr(vehicle, "status", "")
        ) != "active":
            raise TransportCoordinationContractError(
                "VEHICLE_UNAVAILABLE",
                "The assigned vehicle is not active",
            )
        if not getattr(vehicle, "is_available", False) and getattr(
            vehicle, "current_booking_id", None
        ) != booking.id:
            raise TransportCoordinationContractError(
                "VEHICLE_UNAVAILABLE",
                "The assigned vehicle is not available",
            )
        capacity = getattr(vehicle, "passenger_capacity", None)
        if capacity is not None and capacity < int(booking.passenger_count or 1):
            raise TransportCoordinationContractError(
                "TRANSPORT_CAPACITY_EXCEEDED",
                "The vehicle has no remaining capacity",
            )

    @staticmethod
    def _reservation_result(passenger) -> dict:
        return {
            "passenger_id": passenger.id,
            "passenger_public_id": passenger.public_id,
            "status": str(
                getattr(passenger.status, "value", passenger.status) or ""
            ),
            "event_assignment_id": passenger.event_assignment_id,
        }

    @classmethod
    def _apply_passenger_identity(cls, passenger, *, full_name=None, email=None, phone=None, user_id=None) -> None:
        if full_name:
            passenger.name = str(full_name).strip()[:150]
        if email:
            passenger.email = str(email).strip().lower()[:255]
        if phone:
            passenger.phone = str(phone).strip()[:30]
        if user_id:
            passenger.user_id = user_id

    # ------------------------------------------------------------------
    # Validation (read-safe preflight; never reserves a passenger)
    # ------------------------------------------------------------------

    @classmethod
    def validate_booking_for_assignment(cls, booking_reference: str) -> dict:
        """Validate that a Booking may back an event transport assignment.

        Owns the Transport eligibility rules (status, driver/vehicle presence,
        driver approval/verification/availability, vehicle availability and
        declared capacity). Does NOT reserve a passenger and does not link the
        booking to an event (Events owns event scope).
        """
        booking = cls._load_booking(booking_reference, lock=False)
        cls._validate_booking(booking)
        return {
            "booking_id": booking.id,
            "booking_reference": booking.booking_reference,
            "status": cls._status_value(booking.status),
        }

    # ------------------------------------------------------------------
    # Reservation
    # ------------------------------------------------------------------

    @classmethod
    def ensure_passenger_reservation(
        cls,
        booking_reference: str,
        *,
        event_assignment_id: int = None,
        event_id: int = None,
        full_name: str = None,
        email: str = None,
        phone: str = None,
        user_id: int = None,
        reason: str = "event_coordination",
    ) -> dict:
        """Create or reuse the single active passenger reservation owned by an
        event assignment on a Booking.

        Transport-owned lifecycle:
          * locks the booking row and serialises capacity with an advisory
            transaction lock,
          * revalidates Transport eligibility atomically,
          * tags the booking to the event only when Transport owns the write
            (never Events),
          * is idempotent: an existing active reservation for the same event
            assignment on the same booking is returned as-is,
          * reassigns atomically: an existing active reservation for the same
            event assignment on a *different* booking is retired in the same
            transaction before the new reservation is created,
          * enforces the booking's declared seat target with authoritative
            capacity (no Events-side counters).

        Returns a dict with ``passenger_id``, ``passenger_public_id``,
        ``status`` and ``event_assignment_id``. Flushes only; commit is owned
        by the caller's outer service boundary.
        """
        from app.transport.models import TransportPassenger, PassengerStatus

        booking = cls._load_booking(booking_reference, lock=True)
        db.session.execute(
            text("SELECT pg_advisory_xact_lock(:bid)"), {"bid": booking.id}
        )
        cls._validate_booking(booking)

        if event_id is not None:
            if booking.event_id is None:
                # Rerouted legacy write (Events used to set Booking.event_id
                # directly). The booking->event tag is Transport-owned.
                booking.event_id = event_id
            elif booking.event_id != event_id:
                raise TransportCoordinationContractError(
                    "TRANSPORT_BOOKING_EVENT_MISMATCH",
                    "Transport booking is reserved for another event",
                )

        if event_assignment_id is not None:
            existing = TransportPassenger.query.filter(
                TransportPassenger.event_assignment_id == event_assignment_id,
                TransportPassenger.is_deleted == False,  # noqa: E712
                TransportPassenger.status != PassengerStatus.CANCELLED,
            ).first()
            if existing is not None:
                if existing.booking_id == booking.id:
                    # Idempotent reuse of the current reservation.
                    cls._apply_passenger_identity(
                        existing, full_name=full_name, email=email,
                        phone=phone, user_id=user_id,
                    )
                    db.session.flush()
                    return cls._reservation_result(existing)
                # Reassignment onto a new booking (John -> Mary): retire the old
                # reservation in the same transaction before creating the new one.
                existing.status = PassengerStatus.CANCELLED
                metadata = dict(existing.passenger_metadata or {})
                metadata["released_at"] = datetime.now(timezone.utc).isoformat()
                metadata["release_reason"] = (reason or "reassigned").strip()
                existing.passenger_metadata = metadata

        email_norm = (email or "").strip().lower() or None
        passenger = None
        if email_norm:
            passenger = TransportPassenger.query.filter(
                TransportPassenger.booking_id == booking.id,
                TransportPassenger.email == email_norm,
                TransportPassenger.is_deleted == False,  # noqa: E712
                TransportPassenger.status != PassengerStatus.CANCELLED,
            ).first()
        if passenger is None and user_id:
            passenger = TransportPassenger.query.filter(
                TransportPassenger.booking_id == booking.id,
                TransportPassenger.user_id == user_id,
                TransportPassenger.is_deleted == False,  # noqa: E712
                TransportPassenger.status != PassengerStatus.CANCELLED,
            ).first()
        if passenger is None:
            passenger = TransportPassenger(booking_id=booking.id)
            db.session.add(passenger)
        if event_assignment_id is not None:
            passenger.event_assignment_id = event_assignment_id
        cls._apply_passenger_identity(
            passenger, full_name=full_name, email=email, phone=phone, user_id=user_id,
        )
        passenger.status = PassengerStatus.CONFIRMED
        db.session.flush()

        # Authoritative capacity: active reservations on the booking must not
        # exceed the booking's declared seat target.
        active_count = TransportPassenger.query.filter(
            TransportPassenger.booking_id == booking.id,
            TransportPassenger.is_deleted == False,  # noqa: E712
            TransportPassenger.status != PassengerStatus.CANCELLED,
        ).count()
        allowed = int(booking.passenger_count or 1)
        if active_count > allowed:
            raise TransportCoordinationContractError(
                "TRANSPORT_BOOKING_FULL",
                "Transport booking capacity exceeded",
            )

        audit_log(
            action="transport_passenger_reserved",
            resource_type="transport_booking",
            resource_id=booking.id,
            user_id=user_id,
            details={"event_assignment_id": event_assignment_id},
        )
        return cls._reservation_result(passenger)

    # ------------------------------------------------------------------
    # Release
    # ------------------------------------------------------------------

    @staticmethod
    def release_passenger(
        *,
        event_assignment_id: int = None,
        removed_by_user_id: int = None,
        reason: str = None,
    ) -> bool:
        """Retire the active Transport passenger reservation(s) owned by an
        event assignment (reassignment or cancellation).

        Transport owns passenger lifecycle. Idempotent: returns True when at
        least one active reservation was retired, False when none matched
        (already released or unknown assignment). Does NOT touch the
        EventAssignment pointer and does NOT delete history - the reservation
        moves to CANCELLED (is_deleted stays False) and carries its release
        metadata. Flushes only; commit is owned by the caller.
        """
        if event_assignment_id is None:
            return False
        from app.transport.models import TransportPassenger, PassengerStatus

        passengers = TransportPassenger.query.filter(
            TransportPassenger.event_assignment_id == event_assignment_id,
            TransportPassenger.is_deleted == False,  # noqa: E712
            TransportPassenger.status != PassengerStatus.CANCELLED,
        ).all()
        if not passengers:
            return False
        released_at = datetime.now(timezone.utc)
        release_reason = (reason or "assignment cancelled").strip()
        for passenger in passengers:
            passenger.status = PassengerStatus.CANCELLED
            metadata = dict(passenger.passenger_metadata or {})
            metadata["released_at"] = released_at.isoformat()
            metadata["release_reason"] = release_reason
            metadata["released_by_user_id"] = removed_by_user_id
            passenger.passenger_metadata = metadata
            audit_log(
                action="transport_passenger_released",
                resource_type="transport_passenger",
                resource_id=passenger.id,
                user_id=removed_by_user_id,
                details={"event_assignment_id": event_assignment_id},
            )
        db.session.flush()
        return True

    @classmethod
    def release_passenger_for_guest(
        cls,
        booking_reference: str,
        *,
        email: str = None,
        user_id: int = None,
        removed_by_user_id: int = None,
        reason: str = None,
    ) -> bool:
        """Retire the active Transport passenger reservation created for a
        non-event guest (accommodation-coordination) on one booking.

        Transport owns passenger lifecycle. The reservation is located on the
        booking by passenger identity (email or user id) and only releases
        reservations that are NOT bound to an event assignment, so releasing an
        accommodation-coordinated seat never cancels an Event-coordinated one
        (UNASSIGN is not CANCEL). Idempotent: returns True when at least one
        active reservation was retired, False when none matched. Does NOT
        delete history - the reservation moves to CANCELLED and carries its
        release metadata. Flushes only; commit is owned by the caller.
        """
        from app.transport.models import TransportPassenger, PassengerStatus

        booking = cls._load_booking(booking_reference, lock=False)
        email_norm = (email or "").strip().lower() or None
        if not email_norm and not user_id:
            raise TransportCoordinationContractError(
                "PASSENGER_IDENTITY_REQUIRED",
                "A passenger email or user id is required to release the reservation",
            )
        query = TransportPassenger.query.filter(
            TransportPassenger.booking_id == booking.id,
            TransportPassenger.event_assignment_id.is_(None),
            TransportPassenger.is_deleted == False,  # noqa: E712
            TransportPassenger.status != PassengerStatus.CANCELLED,
        )
        if email_norm and user_id:
            from sqlalchemy import or_

            query = query.filter(
                or_(
                    TransportPassenger.email == email_norm,
                    TransportPassenger.user_id == user_id,
                )
            )
        elif email_norm:
            query = query.filter(TransportPassenger.email == email_norm)
        elif user_id:
            query = query.filter(TransportPassenger.user_id == user_id)
        passengers = query.all()
        if not passengers:
            return False
        released_at = datetime.now(timezone.utc)
        release_reason = (reason or "assignment cancelled").strip()
        for passenger in passengers:
            passenger.status = PassengerStatus.CANCELLED
            metadata = dict(passenger.passenger_metadata or {})
            metadata["released_at"] = released_at.isoformat()
            metadata["release_reason"] = release_reason
            metadata["released_by_user_id"] = removed_by_user_id
            passenger.passenger_metadata = metadata
            audit_log(
                action="transport_passenger_released",
                resource_type="transport_passenger",
                resource_id=passenger.id,
                user_id=removed_by_user_id,
                details={"accommodation_guest": bool(email_norm), "reason": release_reason},
            )
        db.session.flush()
        return True

    # ------------------------------------------------------------------
    # Booking -> event tag
    # ------------------------------------------------------------------

    @classmethod
    def tag_booking_for_event(cls, booking_reference: str, event_id: int) -> bool:
        """Transport-owned write of the booking -> event cross-module reference.

        Events may route this tag (instead of writing Booking.event_id
        directly) so the booking->event linkage stays a Transport concern.
        Idempotent for the same event; tagging a booking already reserved for
        another event is rejected.
        """
        booking = cls._load_booking(booking_reference, lock=True)
        if booking.event_id is None:
            booking.event_id = event_id
            db.session.flush()
        elif booking.event_id != event_id:
            raise TransportCoordinationContractError(
                "TRANSPORT_BOOKING_EVENT_MISMATCH",
                "Transport booking is reserved for another event",
            )
        return True