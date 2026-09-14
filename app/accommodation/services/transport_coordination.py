"""Accommodation-owned coordination of a Transport booking for a hotel guest.

This is the non-event (Stage 5) counterpart of the Event guest-coordination
flow. It owns only the Accommodation side: which GuestRegistration is being
coordinated and the source-side reference
(GuestRegistration.transport_booking_id). Transport-state writes (passenger
reservation, capacity, eligibility) always go through the
TransportCoordinationContract — Accommodation never writes transport tables.

Module independence rule: Accommodation owns the source customer (the
registered guest) and the source reference; the Transport module owns the
reservation, capacity and target eligibility.
"""

from __future__ import annotations

from flask import current_app, has_request_context

from app.extensions import db
from app.notifications.events.publisher import emit_event
from app.notifications.events.registry import EventType
from app.utils.module_guard import module_enabled


class AccommodationTransportCoordinationError(Exception):
    """Accommodation transport-coordination failure returned to the caller."""

    def __init__(self, code: str, message: str = ""):
        self.code = code
        self.message = message or code
        super().__init__(self.message)


# The set of Transport booking statuses this module may present as an active
# accommodation-coordinated assignment. Mirror of the Transport contract's
# assignable set; the contract revalidates authoritatively on each call.
TRANSPORT_ASSIGNABLE_STATUSES = frozenset(("confirmed", "assigned"))


def _module_available(module_name: str) -> bool:
    """Resolve module status where module_enabled is authoritative (requests)
    and default to available outside a request (workers/CLI)."""
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


def _guest_ref(registration) -> str:
    """Public identity reference for a GuestRegistration (never the internal id)."""
    from app.accommodation.models.guest_registration import GuestRegistration

    if isinstance(registration, GuestRegistration):
        return str(getattr(registration, "public_id", None) or "")
    return ""


def _forensic_audit(action, booking, registration, actor, target_booking, *, status, details):
    """Stage a forensic fact without exposing internal identity values.

    Mirrors the Events module pattern: both the attempt and the completion are
    written inside the caller's transaction, and a rejected/staging failure
    aborts the coordination so no assignment ever lands without its audit fact.
    """
    try:
        from app.audit.forensic_audit import ForensicAuditService

        entity_id = f"{booking.booking_reference}:{_guest_ref(registration)}"
        audit_details = {
            "booking_ref": booking.booking_reference,
            "guest_ref": _guest_ref(registration),
            "actor_ref": getattr(actor, "public_id", None),
            "transport_booking_ref": getattr(target_booking, "booking_reference", None),
            **details,
        }
        if status == "completed":
            audit_id = ForensicAuditService.log_attempt(
                entity_type="accommodation_guest_assignment",
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
        raise AccommodationTransportCoordinationError(
            "COORDINATION_AUDIT_FAILED",
            "The coordination audit fact could not be staged",
        ) from exc


def _assignment_info(registration, accommodation_booking, transport_booking) -> dict:
    """Human-readable summary of the assignment for the success message/UI."""
    return {
        "guest_name": registration.guest_name,
        "booking_ref": accommodation_booking.booking_reference,
        "transport_booking_ref": transport_booking.booking_reference,
        "vehicle": getattr(getattr(transport_booking, "vehicle", None), "public_id", None),
        "driver": getattr(getattr(transport_booking, "driver", None), "public_id", None),
        "pickup_time": transport_booking.pickup_time.isoformat()
        if transport_booking.pickup_time else None,
        "pickup": transport_booking.pickup_address,
        "dropoff": transport_booking.dropoff_address,
    }


def _notify_transport_customer(registration, transport_booking, *, removed: bool = False):
    """Best-effort customer notification for a transport coordination change.

    Mirrors the Events accommodation bridge: the email is gated on a valid
    guest email and delivery failures are logged, never fatal to the
    assignment. Account guests receive dual in-app + email delivery; email-only
    guests receive the email only.
    """
    email = (registration.guest_email or "").strip()
    if not email:
        return
    try:
        from app.auth.email_validation import validate_email_address

        if not validate_email_address(email).is_valid:
            current_app.logger.info(
                "Skipping transport coordination email: invalid address %r", email
            )
            return
    except Exception:
        pass
    try:
        from app.notifications.models import NotificationModule, NotificationType
        from app.notifications.services import NotificationService

        user_id = registration.guest_user_id
        # Email-only: matches Event's _email_invite pattern.  In-app
        # notification for the admin/assigner is delivered through the
        # outbox → NotificationConsumer → policy path.
        channels = ["email"]
        transport_ref = getattr(transport_booking, "booking_reference", None) or ""
        if removed:
            notification_type = NotificationType.BOOKING_UPDATE
            title = "Transport assignment removed"
            message = (
                "The transport booking previously assigned to your accommodation "
                "stay has been removed."
            )
        else:
            notification_type = NotificationType.BOOKING_CONFIRMED
            title = "Transport assigned to your stay"
            message = (
                f"A transport booking ({transport_ref}) has been assigned to your "
                "accommodation stay."
            )
        NotificationService.send(
            user_id=user_id,
            notification_type=notification_type,
            title=title,
            message=message,
            email=email,
            channels=channels,
            module=NotificationModule.TRANSPORT,
            force_external=True,
            context={
                "guest_name": registration.guest_name,
                "booking_reference": getattr(registration, "booking_reference", None),
                "transport_booking_ref": transport_ref,
                "vehicle": getattr(getattr(transport_booking, "vehicle", None), "public_id", None),
                "driver": getattr(getattr(transport_booking, "driver", None), "public_id", None),
                "pickup_time": transport_booking.pickup_time.isoformat()
                if getattr(transport_booking, "pickup_time", None) else None,
                "pickup": getattr(transport_booking, "pickup_address", None),
                "dropoff": getattr(transport_booking, "dropoff_address", None),
            },
        )
    except Exception:
        current_app.logger.exception(
            "Failed to send transport coordination notification to %r", email
        )


class GuestTransportCoordinationService:
    """Coordinate a booked Transport resource for an Accommodation guest."""

    @staticmethod
    def _authorize_booking(actor, booking_id: int):
        """Resolve the Accommodation booking and enforce the same
        registration-management gate as the guest roster page."""
        from app.accommodation.services.registration_permission_service import RegistrationPermissionService
        from app.accommodation.models.booking import AccommodationBooking

        booking = AccommodationBooking.query.filter_by(
            id=booking_id, is_deleted=False
        ).first()
        if booking is None:
            raise AccommodationTransportCoordinationError(
                "BOOKING_NOT_FOUND", "Accommodation booking was not found"
            )
        if not RegistrationPermissionService.can_manage_registrations(actor, booking):
            raise AccommodationTransportCoordinationError(
                "COORDINATION_FORBIDDEN",
                "You are not allowed to coordinate this booking",
            )
        return booking

    @staticmethod
    def _source(actor, booking_id: int, registration_id: int):
        """Resolve the active source customer (GuestRegistration) and re-check
        the registration-management gate."""
        from app.accommodation.models.guest_registration import GuestRegistration

        registration = GuestRegistration.query.filter_by(
            id=registration_id, booking_id=booking_id, is_deleted=False
        ).first()
        if registration is None:
            raise AccommodationTransportCoordinationError(
                "GUEST_NOT_FOUND", "Guest registration was not found"
            )
        booking = GuestTransportCoordinationService._authorize_booking(actor, booking_id)
        return registration, booking

    @staticmethod
    def _resolve_transport_booking(actor, transport_booking_ref: str):
        """Resolve the target Transport booking and validate ownership scope.

        Accommodation deliberately keeps transport-domain rules OUT of this
        module: driver/vehicle eligibility, status and capacity are owned by the
        Transport coordination contract and revalidated atomically on every
        reservation. This module owns only the ownership-scope check (the
        acting user booked the transport resource).
        """
        from app.transport.models import Booking

        ref = _resource_ref(transport_booking_ref)
        if not ref:
            raise AccommodationTransportCoordinationError(
                "INVALID_TRANSPORT_REFERENCE",
                "A transport booking reference is required",
            )
        booking = Booking.query.filter_by(booking_reference=ref, is_deleted=False).first()
        if booking is None and ref.isdigit():
            booking = Booking.query.filter_by(id=int(ref), is_deleted=False).first()
        if booking is None:
            raise AccommodationTransportCoordinationError(
                "TRANSPORT_BOOKING_NOT_FOUND", "Transport booking was not found"
            )
        actor_id = getattr(actor, "id", None)
        if actor_id is None or booking.user_id != actor_id:
            raise AccommodationTransportCoordinationError(
                "TRANSPORT_BOOKING_MISMATCH",
                "Transport booking is not owned by the coordinating user",
            )
        return booking

    @staticmethod
    def _transport_summary(booking) -> dict | None:
        if booking is None:
            return None
        return {
            "booking_ref": booking.booking_reference,
            "driver": getattr(getattr(booking, "driver", None), "public_id", None),
            "vehicle": getattr(getattr(booking, "vehicle", None), "public_id", None),
            "pickup_time": booking.pickup_time.isoformat() if booking.pickup_time else None,
            "pickup": booking.pickup_address,
            "dropoff": booking.dropoff_address,
        }

    @staticmethod
    def roster(actor, booking_id: int) -> dict:
        """Read-side pane data: every active guest plus its transport
        assignment (only while the referenced booking is still assignable)."""
        from app.accommodation.models.guest_registration import GuestRegistration

        booking = GuestTransportCoordinationService._authorize_booking(actor, booking_id)
        registrations = GuestRegistration.query.filter_by(
            booking_id=booking.id, is_active=True, is_deleted=False
        ).all()
        transport_ids = {
            r.transport_booking_id for r in registrations if r.transport_booking_id
        }
        transport_by_id = {}
        if transport_ids and _module_available("transport"):
            from sqlalchemy.orm import joinedload

            from app.transport.models import Booking

            transport_by_id = {
                b.id: b
                for b in Booking.query.options(
                    joinedload(Booking.driver), joinedload(Booking.vehicle)
                ).filter(
                    Booking.id.in_(transport_ids), Booking.is_deleted == False  # noqa: E712
                ).all()
            }
        assignable_ids = {
            b.id for b in transport_by_id.values()
            if _status_value(getattr(b, "status", "")) in TRANSPORT_ASSIGNABLE_STATUSES
        }
        rows = []
        for registration in registrations:
            transport_booking_id = registration.transport_booking_id
            active = transport_booking_id is not None and transport_booking_id in assignable_ids
            rows.append({
                "registration_id": registration.id,
                "guest_name": registration.guest_name,
                "guest_email": registration.guest_email,
                "guest_phone": registration.guest_phone,
                "status": _status_value(registration.status),
                "is_placeholder": registration.is_placeholder,
                "transport_booking_id": transport_booking_id if active else None,
                "transport": GuestTransportCoordinationService._transport_summary(
                    transport_by_id.get(transport_booking_id) if active else None
                ),
            })
        return {"items": rows}

    @staticmethod
    def assign_transport(
        actor, *, booking_id: int, registration_id: int, transport_booking_ref: str
    ) -> dict:
        from app.transport.models import Booking
        from app.transport.services.coordination_contract import (
            TransportCoordinationContract,
            TransportCoordinationContractError,
        )

        if not _module_available("transport"):
            raise AccommodationTransportCoordinationError(
                "TRANSPORT_UNAVAILABLE", "Transport service is currently unavailable"
            )
        registration, booking = GuestTransportCoordinationService._source(
            actor, booking_id, registration_id
        )
        try:
            target = GuestTransportCoordinationService._resolve_transport_booking(
                actor, transport_booking_ref
            )
            previous_id = registration.transport_booking_id
            previous_booking_ref = None
            if previous_id == target.id:
                return {
                    "registration_id": registration.id,
                    "transport_booking_id": target.id,
                    "assigned": True,
                    "assignment_info": _assignment_info(registration, booking, target),
                }
            if previous_id is not None:
                previous = Booking.query.filter_by(
                    id=previous_id, is_deleted=False
                ).first()
                if previous is not None:
                    previous_booking_ref = previous.booking_reference
                    try:
                        TransportCoordinationContract.release_passenger_for_guest(
                            previous.booking_reference,
                            email=registration.guest_email,
                            user_id=registration.guest_user_id,
                            removed_by_user_id=getattr(actor, "id", None),
                            reason="reassigned to another booking",
                        )
                    except TransportCoordinationContractError as exc:
                        if exc.code != "TRANSPORT_BOOKING_NOT_FOUND":
                            raise
                        current_app.logger.warning(
                            "Old passenger release skipped during reassignment "
                            "guest %s: %s", registration.id, exc,
                        )
            # Transport owns reservation, capacity and eligibility: the contract
            # locks the booking row, revalidates status/driver/vehicle/capacity
            # atomically and creates the identity-keyed passenger reservation.
            TransportCoordinationContract.ensure_passenger_reservation(
                target.booking_reference,
                event_assignment_id=None,
                event_id=None,
                full_name=registration.guest_name,
                email=registration.guest_email,
                phone=registration.guest_phone,
                user_id=registration.guest_user_id,
                reason="accommodation_coordination",
            )
            registration.transport_booking_id = target.id
            db.session.flush()
            envelope = emit_event(
                EventType.GUEST_TRANSPORT_ASSIGNED if previous_id is None
                else EventType.GUEST_TRANSPORT_CHANGED,
                payload={
                    "booking_ref": booking.booking_reference,
                    "guest_ref": _guest_ref(registration),
                    "capability": "transport",
                    "previous_transport_booking_ref": previous_booking_ref,
                    "transport_booking_ref": target.booking_reference,
                    "actor_public_id": getattr(actor, "public_id", None),
                },
                aggregate_type="accommodation_booking",
                aggregate_id=booking.booking_reference,
                actor_type="user",
                actor_id=getattr(actor, "id", None),
                session=db.session,
            )
            if envelope is None:
                db.session.rollback()
                raise AccommodationTransportCoordinationError(
                    "COORDINATION_EVENT_FAILED",
                    "The assignment audit event could not be staged",
                )
            _forensic_audit(
                "coordination_assignment",
                booking,
                registration,
                actor,
                target,
                status="completed",
                details={
                    "capability": "transport",
                    "previous_transport_booking_ref": previous_booking_ref,
                    "transport_booking_ref": target.booking_reference,
                },
            )
            _notify_transport_customer(registration, target, removed=False)
            db.session.commit()
            return {
                "registration_id": registration.id,
                "transport_booking_id": target.id,
                "assigned": True,
                "assignment_info": _assignment_info(registration, booking, target),
            }
        except AccommodationTransportCoordinationError:
            db.session.rollback()
            raise
        except TransportCoordinationContractError as exc:
            db.session.rollback()
            raise AccommodationTransportCoordinationError(exc.code, exc.message) from exc
        except Exception as exc:
            db.session.rollback()
            raise AccommodationTransportCoordinationError(
                "COORDINATION_FAILED", "The transport assignment could not be completed"
            ) from exc

    @staticmethod
    def unassign_transport(actor, *, booking_id: int, registration_id: int) -> dict:
        from app.transport.models import Booking
        from app.transport.services.coordination_contract import (
            TransportCoordinationContract,
            TransportCoordinationContractError,
        )

        registration, booking = GuestTransportCoordinationService._source(
            actor, booking_id, registration_id
        )
        try:
            previous_id = registration.transport_booking_id
            if previous_id is None:
                return {"registration_id": registration.id, "assigned": False}
            previous = None
            if _module_available("transport"):
                previous = Booking.query.filter_by(
                    id=previous_id, is_deleted=False
                ).first()
            previous_booking_ref = getattr(previous, "booking_reference", None)
            if previous is not None:
                # UNASSIGN is not CANCEL: release only the non-event passenger
                # reservation; the transport booking itself stays normal.
                try:
                    TransportCoordinationContract.release_passenger_for_guest(
                        previous.booking_reference,
                        email=registration.guest_email,
                        user_id=registration.guest_user_id,
                        removed_by_user_id=getattr(actor, "id", None),
                        reason="assignment cancelled",
                    )
                except TransportCoordinationContractError as exc:
                    if exc.code != "TRANSPORT_BOOKING_NOT_FOUND":
                        raise
                    current_app.logger.warning(
                        "Passenger release skipped while unassigning guest %s booking %s: %s",
                        registration.id, previous_id, exc,
                    )
            registration.transport_booking_id = None
            db.session.flush()
            envelope = emit_event(
                EventType.GUEST_TRANSPORT_REMOVED,
                payload={
                    "booking_ref": booking.booking_reference,
                    "guest_ref": _guest_ref(registration),
                    "capability": "transport",
                    "previous_transport_booking_ref": previous_booking_ref,
                    "actor_public_id": getattr(actor, "public_id", None),
                },
                aggregate_type="accommodation_booking",
                aggregate_id=booking.booking_reference,
                actor_type="user",
                actor_id=getattr(actor, "id", None),
                session=db.session,
            )
            if envelope is None:
                db.session.rollback()
                raise AccommodationTransportCoordinationError(
                    "COORDINATION_EVENT_FAILED",
                    "The removal audit event could not be staged",
                )
            _forensic_audit(
                "coordination_removal",
                booking,
                registration,
                actor,
                previous,
                status="completed",
                details={
                    "capability": "transport",
                    "previous_transport_booking_ref": previous_booking_ref,
                },
            )
            _notify_transport_customer(registration, previous, removed=True)
            db.session.commit()
            return {"registration_id": registration.id, "assigned": False}
        except AccommodationTransportCoordinationError:
            db.session.rollback()
            raise
        except Exception as exc:
            db.session.rollback()
            raise AccommodationTransportCoordinationError(
                "COORDINATION_FAILED",
                "The transport unassignment could not be completed",
            ) from exc