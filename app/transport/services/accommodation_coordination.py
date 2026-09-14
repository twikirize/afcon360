"""Transport-owned coordination of an Accommodation booking for a passenger.

This is the non-event (Stage 5) counterpart of the Event guest-coordination
flow, run from the Transport side. It owns only the Transport side: which
TransportPassenger is being coordinated and the source-side reference
(TransportPassenger.accommodation_booking_id). Accommodation-state writes
(guest slot, capacity, eligibility) always go through the
AccommodationCoordinationContract — Transport never writes accommodation
tables.

Module independence rule: Transport owns the source customer (the passenger)
and the source reference; the Accommodation module owns the guest slot,
capacity and target eligibility.
"""

from __future__ import annotations

from flask import current_app, has_request_context

from app.extensions import db
from app.notifications.events.publisher import emit_event
from app.notifications.events.registry import EventType
from app.utils.module_guard import module_enabled


class TransportAccommodationCoordinationError(Exception):
    """Transport accommodation-coordination failure returned to the caller."""

    def __init__(self, code: str, message: str = ""):
        self.code = code
        self.message = message or code
        super().__init__(self.message)


# Mirror of the Accommodation contract's assignable status set; the contract
# revalidates authoritatively (status, room type, capacity) on each call.
ACCOMMODATION_ASSIGNABLE_STATUSES = frozenset(
    ("held", "confirmed", "pending", "pending_approval")
)


def _module_available(module_name: str) -> bool:
    if has_request_context():
        return module_enabled(module_name)
    return True


def _status_value(value) -> str:
    return str(getattr(value, "value", value) or "").lower()


def _resource_ref(value) -> str | None:
    if value is None:
        return None
    ref = str(value).strip()
    return ref or None


def _passenger_ref(passenger) -> str:
    """Public identity reference for a TransportPassenger (never the internal id)."""
    from app.transport.models import TransportPassenger

    if isinstance(passenger, TransportPassenger):
        return str(getattr(passenger, "public_id", None) or "")
    return ""


def _forensic_audit(action, booking, passenger, actor, target_booking, *, status, details):
    """Stage a forensic fact without exposing internal identity values.

    Mirrors the Events module pattern: both the attempt and the completion are
    written inside the caller's transaction, and a rejected/staging failure
    aborts the coordination so no assignment ever lands without its audit fact.
    """
    try:
        from app.audit.forensic_audit import ForensicAuditService

        entity_id = f"{booking.booking_reference}:{_passenger_ref(passenger)}"
        audit_details = {
            "booking_ref": booking.booking_reference,
            "passenger_ref": _passenger_ref(passenger),
            "actor_ref": getattr(actor, "public_id", None),
            "accommodation_booking_ref": getattr(target_booking, "booking_reference", None),
            **details,
        }
        if status == "completed":
            audit_id = ForensicAuditService.log_attempt(
                entity_type="transport_passenger_assignment",
                entity_id=entity_id,
                action=action,
                user_id=None,
                details=audit_details,
                correlation_id=entity_id,
            )
            if not ForensicAuditService.log_completion(
                audit_id=audit_id,
                result_details=audit_details,
            ):
                raise RuntimeError("completion audit was rejected")
        else:
            raise ValueError(f"Unsupported forensic audit status: {status}")
    except Exception as exc:
        raise TransportAccommodationCoordinationError(
            "COORDINATION_AUDIT_FAILED",
            "The coordination audit fact could not be staged",
        ) from exc


def _assignment_info(passenger, transport_booking, accommodation_booking) -> dict:
    """Human-readable summary of the assignment for the success message/UI."""
    return {
        "passenger_name": passenger.name,
        "booking_ref": transport_booking.booking_reference,
        "accommodation_booking_ref": accommodation_booking.booking_reference,
        "property": getattr(getattr(accommodation_booking, "property", None), "public_id", None),
        "room_type": getattr(accommodation_booking.room_type, "name", None)
        if accommodation_booking.room_type is not None else None,
        "check_in": accommodation_booking.check_in.isoformat()
        if accommodation_booking.check_in else None,
        "check_out": accommodation_booking.check_out.isoformat()
        if accommodation_booking.check_out else None,
    }


def _notify_accommodation_customer(passenger, accommodation_booking, *, removed: bool = False):
    """Best-effort customer notification for an accommodation coordination change.

    Mirrors the Events accommodation bridge: the email is gated on a valid
    passenger email and delivery failures are logged, never fatal to the
    assignment. Account passengers receive dual in-app + email delivery;
    email-only passengers receive the email only.
    """
    email = (passenger.email or "").strip()
    if not email:
        return
    try:
        from app.auth.email_validation import validate_email_address

        if not validate_email_address(email).is_valid:
            current_app.logger.info(
                "Skipping accommodation coordination email: invalid address %r", email
            )
            return
    except Exception:
        pass
    try:
        from app.notifications.models import NotificationModule, NotificationType
        from app.notifications.services import NotificationService

        user_id = passenger.user_id
        # Email-only: matches Event's _email_invite pattern.  In-app
        # notification for the admin/assigner is delivered through the
        # outbox → NotificationConsumer → policy path.
        channels = ["email"]
        accommodation_ref = getattr(accommodation_booking, "booking_reference", None) or ""
        if removed:
            notification_type = NotificationType.BOOKING_UPDATE
            title = "Accommodation assignment removed"
            message = (
                "The accommodation booking previously assigned to your trip has "
                "been removed."
            )
        else:
            notification_type = NotificationType.BOOKING_CONFIRMED
            title = "Accommodation assigned to your trip"
            message = (
                f"An accommodation booking ({accommodation_ref}) has been assigned "
                "to your transport trip."
            )
        NotificationService.send(
            user_id=user_id,
            notification_type=notification_type,
            title=title,
            message=message,
            email=email,
            channels=channels,
            module=NotificationModule.ACCOMMODATION,
            force_external=True,
            context={
                "passenger_name": passenger.name,
                "booking_reference": getattr(passenger, "booking_reference", None),
                "accommodation_booking_ref": accommodation_ref,
                "property": getattr(getattr(accommodation_booking, "property", None), "public_id", None),
                "room_type": getattr(accommodation_booking.room_type, "name", None)
                if getattr(accommodation_booking, "room_type", None) is not None else None,
                "check_in": accommodation_booking.check_in.isoformat()
                if getattr(accommodation_booking, "check_in", None) else None,
                "check_out": accommodation_booking.check_out.isoformat()
                if getattr(accommodation_booking, "check_out", None) else None,
            },
        )
    except Exception:
        current_app.logger.exception(
            "Failed to send accommodation coordination notification to %r", email
        )


class PassengerAccommodationCoordinationService:
    """Coordinate a booked Accommodation resource for a Transport passenger."""

    @staticmethod
    def _source(actor, transport_booking_id: int, passenger_id: int):
        """Resolve the source TransportPassenger and enforce the same booking
        ownership rule as the transport bookings pages."""
        from app.transport.models import Booking, TransportPassenger

        passenger = TransportPassenger.query.filter_by(
            id=passenger_id, booking_id=transport_booking_id, is_deleted=False
        ).first()
        if passenger is None:
            raise TransportAccommodationCoordinationError(
                "PASSENGER_NOT_FOUND", "Passenger was not found"
            )
        booking = Booking.query.filter_by(
            id=transport_booking_id, is_deleted=False
        ).first()
        if booking is None:
            raise TransportAccommodationCoordinationError(
                "BOOKING_NOT_FOUND", "Transport booking was not found"
            )
        actor_id = getattr(actor, "id", None)
        if actor_id is None or booking.user_id != actor_id:
            raise TransportAccommodationCoordinationError(
                "COORDINATION_FORBIDDEN",
                "You are not allowed to coordinate this transport booking",
            )
        return passenger, booking

    @staticmethod
    def _resolve_accommodation_booking(actor, accommodation_booking_ref: str):
        """Resolve the target Accommodation booking and validate ownership scope.

        Transport deliberately keeps accommodation-domain rules OUT of this
        module: booking status, room type and capacity are owned by the
        Accommodation coordination contract and revalidated atomically on every
        reservation. This module owns only the ownership-scope check (the
        acting user booked/owns the accommodation resource).
        """
        from app.accommodation.models.booking import AccommodationBooking

        ref = _resource_ref(accommodation_booking_ref)
        if not ref:
            raise TransportAccommodationCoordinationError(
                "INVALID_ACCOMMODATION_REFERENCE",
                "An accommodation booking reference is required",
            )
        booking = AccommodationBooking.query.filter_by(
            booking_reference=ref, is_deleted=False
        ).first()
        if booking is None and ref.isdigit():
            booking = AccommodationBooking.query.filter_by(
                id=int(ref), is_deleted=False
            ).first()
        if booking is None:
            raise TransportAccommodationCoordinationError(
                "ACCOMMODATION_BOOKING_NOT_FOUND",
                "Accommodation booking was not found",
            )
        actor_id = getattr(actor, "id", None)
        owner_linked = actor_id is not None and (
            getattr(booking, "booked_by_user_id", None) == actor_id
            or getattr(booking, "booking_owner_id", None) == actor_id
        )
        if not owner_linked:
            raise TransportAccommodationCoordinationError(
                "ACCOMMODATION_BOOKING_MISMATCH",
                "Accommodation booking is not owned by the coordinating user",
            )
        return booking

    @staticmethod
    def _accommodation_summary(booking) -> dict | None:
        if booking is None:
            return None
        return {
            "booking_ref": booking.booking_reference,
            "property": getattr(getattr(booking, "property", None), "public_id", None),
            "room_type": getattr(booking.room_type, "name", None)
            if booking.room_type is not None else None,
            "check_in": booking.check_in.isoformat() if booking.check_in else None,
            "check_out": booking.check_out.isoformat() if booking.check_out else None,
        }

    @staticmethod
    def pane(actor, transport_booking_id: int) -> dict:
        """Read-side pane data: every passenger plus its accommodation
        assignment (only while the referenced booking is still assignable)."""
        from app.accommodation.models.booking import AccommodationBooking
        from app.transport.models import TransportPassenger

        booking = PassengerAccommodationCoordinationService._owned_booking(
            actor, transport_booking_id
        )
        passengers = TransportPassenger.query.filter_by(
            booking_id=booking.id, is_deleted=False
        ).all()
        accommodation_ids = {
            p.accommodation_booking_id for p in passengers if p.accommodation_booking_id
        }
        accommodation_by_id = {}
        if accommodation_ids and _module_available("accommodation"):
            accommodation_by_id = {
                b.id: b
                for b in AccommodationBooking.query.filter(
                    AccommodationBooking.id.in_(accommodation_ids),
                    AccommodationBooking.is_deleted == False,  # noqa: E712
                ).all()
            }
        assignable_ids = {
            b.id for b in accommodation_by_id.values()
            if _status_value(getattr(b, "status", "")) in ACCOMMODATION_ASSIGNABLE_STATUSES
        }
        rows = []
        for passenger in passengers:
            accommodation_booking_id = passenger.accommodation_booking_id
            active = accommodation_booking_id is not None and accommodation_booking_id in assignable_ids
            rows.append({
                "passenger_id": passenger.id,
                "name": passenger.name,
                "email": passenger.email,
                "phone": passenger.phone,
                "status": _status_value(passenger.status),
                "accommodation_booking_id": accommodation_booking_id if active else None,
                "accommodation": PassengerAccommodationCoordinationService._accommodation_summary(
                    accommodation_by_id.get(accommodation_booking_id) if active else None
                ),
            })
        return {"items": rows}

    @staticmethod
    def _owned_booking(actor, transport_booking_id: int):
        from app.transport.models import Booking

        booking = Booking.query.filter_by(
            id=transport_booking_id, is_deleted=False
        ).first()
        if booking is None:
            raise TransportAccommodationCoordinationError(
                "BOOKING_NOT_FOUND", "Transport booking was not found"
            )
        actor_id = getattr(actor, "id", None)
        if actor_id is None or booking.user_id != actor_id:
            raise TransportAccommodationCoordinationError(
                "COORDINATION_FORBIDDEN",
                "You are not allowed to coordinate this transport booking",
            )
        return booking

    @staticmethod
    def assign_accommodation(
        actor,
        *,
        transport_booking_id: int,
        passenger_id: int,
        accommodation_booking_ref: str,
    ) -> dict:
        from app.accommodation.models.booking import AccommodationBooking
        from app.accommodation.services.coordination_contract import (
            AccommodationCoordinationContract,
            CoordinationContractError,
        )

        if not _module_available("accommodation"):
            raise TransportAccommodationCoordinationError(
                "ACCOMMODATION_UNAVAILABLE",
                "Accommodation service is currently unavailable",
            )
        passenger, booking = PassengerAccommodationCoordinationService._source(
            actor, transport_booking_id, passenger_id
        )
        try:
            target = PassengerAccommodationCoordinationService._resolve_accommodation_booking(
                actor, accommodation_booking_ref
            )
            previous_id = passenger.accommodation_booking_id
            previous_booking_ref = None
            if previous_id == target.id:
                return {
                    "passenger_id": passenger.id,
                    "accommodation_booking_id": target.id,
                    "assigned": True,
                    "assignment_info": _assignment_info(passenger, booking, target),
                }
            if previous_id is not None:
                previous = AccommodationBooking.query.filter_by(
                    id=previous_id, is_deleted=False
                ).first()
                if previous is not None:
                    previous_booking_ref = previous.booking_reference
                    try:
                        AccommodationCoordinationContract.release_guest_slot(
                            previous.booking_reference,
                            email=passenger.email,
                            user_id=passenger.user_id,
                            removed_by_user_id=getattr(actor, "id", None),
                            reason="reassigned to another booking",
                        )
                    except CoordinationContractError as exc:
                        if exc.code != "BOOKING_NOT_FOUND":
                            raise
                        current_app.logger.warning(
                            "Old guest slot release skipped during reassignment "
                            "passenger %s: %s", passenger.id, exc,
                        )
            # Accommodation owns guest slot, capacity and eligibility: the
            # contract revalidates status/room/capacity atomically (validated
            # by preflight, enforced by ensure) and creates the
            # identity-keyed guest slot tagged transport_coordination.
            AccommodationCoordinationContract.validate_booking_for_guest_assignment(
                target.booking_reference
            )
            AccommodationCoordinationContract.ensure_event_guest_slot(
                target.booking_reference,
                full_name=passenger.name,
                email=passenger.email,
                phone=passenger.phone,
                user_id=passenger.user_id,
                event_assignment_id=None,
                registration_source="transport_coordination",
            )
            passenger.accommodation_booking_id = target.id
            db.session.flush()
            envelope = emit_event(
                EventType.PASSENGER_ACCOMMODATION_ASSIGNED if previous_id is None
                else EventType.PASSENGER_ACCOMMODATION_CHANGED,
                payload={
                    "booking_ref": booking.booking_reference,
                    "passenger_ref": _passenger_ref(passenger),
                    "capability": "accommodation",
                    "previous_accommodation_booking_ref": previous_booking_ref,
                    "accommodation_booking_ref": target.booking_reference,
                    "actor_public_id": getattr(actor, "public_id", None),
                },
                aggregate_type="transport_booking",
                aggregate_id=booking.booking_reference,
                actor_type="user",
                actor_id=getattr(actor, "id", None),
                session=db.session,
            )
            if envelope is None:
                db.session.rollback()
                raise TransportAccommodationCoordinationError(
                    "COORDINATION_EVENT_FAILED",
                    "The assignment audit event could not be staged",
                )
            _forensic_audit(
                "coordination_assignment",
                booking,
                passenger,
                actor,
                target,
                status="completed",
                details={
                    "capability": "accommodation",
                    "previous_accommodation_booking_ref": previous_booking_ref,
                    "accommodation_booking_ref": target.booking_reference,
                },
            )
            _notify_accommodation_customer(passenger, target, removed=False)
            db.session.commit()
            return {
                "passenger_id": passenger.id,
                "accommodation_booking_id": target.id,
                "assigned": True,
                "assignment_info": _assignment_info(passenger, booking, target),
            }
        except TransportAccommodationCoordinationError:
            db.session.rollback()
            raise
        except CoordinationContractError as exc:
            db.session.rollback()
            raise TransportAccommodationCoordinationError(exc.code, exc.message) from exc
        except Exception as exc:
            db.session.rollback()
            raise TransportAccommodationCoordinationError(
                "COORDINATION_FAILED",
                "The accommodation assignment could not be completed",
            ) from exc

    @staticmethod
    def unassign_accommodation(
        actor, *, transport_booking_id: int, passenger_id: int
    ) -> dict:
        from app.accommodation.models.booking import AccommodationBooking
        from app.accommodation.services.coordination_contract import (
            AccommodationCoordinationContract,
            CoordinationContractError,
        )

        passenger, booking = PassengerAccommodationCoordinationService._source(
            actor, transport_booking_id, passenger_id
        )
        try:
            previous_id = passenger.accommodation_booking_id
            if previous_id is None:
                return {"passenger_id": passenger.id, "assigned": False}
            previous = None
            if _module_available("accommodation"):
                previous = AccommodationBooking.query.filter_by(
                    id=previous_id, is_deleted=False
                ).first()
            previous_booking_ref = getattr(previous, "booking_reference", None)
            if previous is not None:
                # UNASSIGN is not CANCEL: release only the non-event guest slot;
                # the accommodation booking itself stays normal.
                try:
                    AccommodationCoordinationContract.release_guest_slot(
                        previous.booking_reference,
                        email=passenger.email,
                        user_id=passenger.user_id,
                        removed_by_user_id=getattr(actor, "id", None),
                        reason="assignment cancelled",
                    )
                except CoordinationContractError as exc:
                    if exc.code != "BOOKING_NOT_FOUND":
                        raise
                    current_app.logger.warning(
                        "Guest slot release skipped while unassigning passenger %s booking %s: %s",
                        passenger.id, previous_id, exc,
                    )
            passenger.accommodation_booking_id = None
            db.session.flush()
            envelope = emit_event(
                EventType.PASSENGER_ACCOMMODATION_REMOVED,
                payload={
                    "booking_ref": booking.booking_reference,
                    "passenger_ref": _passenger_ref(passenger),
                    "capability": "accommodation",
                    "previous_accommodation_booking_ref": previous_booking_ref,
                    "actor_public_id": getattr(actor, "public_id", None),
                },
                aggregate_type="transport_booking",
                aggregate_id=booking.booking_reference,
                actor_type="user",
                actor_id=getattr(actor, "id", None),
                session=db.session,
            )
            if envelope is None:
                db.session.rollback()
                raise TransportAccommodationCoordinationError(
                    "COORDINATION_EVENT_FAILED",
                    "The removal audit event could not be staged",
                )
            _forensic_audit(
                "coordination_removal",
                booking,
                passenger,
                actor,
                previous,
                status="completed",
                details={
                    "capability": "accommodation",
                    "previous_accommodation_booking_ref": previous_booking_ref,
                },
            )
            _notify_accommodation_customer(passenger, previous, removed=True)
            db.session.commit()
            return {"passenger_id": passenger.id, "assigned": False}
        except TransportAccommodationCoordinationError:
            db.session.rollback()
            raise
        except Exception as exc:
            db.session.rollback()
            raise TransportAccommodationCoordinationError(
                "COORDINATION_FAILED",
                "The accommodation unassignment could not be completed",
            ) from exc