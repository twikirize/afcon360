"""Canonical, event-scoped coordination operations.

This service deliberately keeps inventory and eligibility decisions in the
Accommodation and Transport modules.  It owns only event scope, assignment
records, stable contracts, and transaction coordination.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any
from types import SimpleNamespace

from flask import current_app, has_app_context, has_request_context
from sqlalchemy.orm import joinedload

from app.events.models import EventAssignment, EventRegistration
from app.events.permissions import (
    can_assign_accommodation,
    can_assign_transport,
    can_cancel_assignment,
    can_view_coordination,
)
from app.extensions import db
from app.notifications.events.publisher import emit_event
from app.notifications.events.registry import EventType
from app.utils.module_guard import module_enabled


def _forensic_audit(action, event, registration, actor, *, status, details):
    """Stage a forensic fact without exposing internal identity values."""
    try:
        from app.audit.forensic_audit import ForensicAuditService

        entity_id = f"{event.public_id}:{registration.registration_ref}"
        audit_details = {
            "event_ref": str(event.public_id),
            "registration_ref": registration.registration_ref,
            "actor_ref": getattr(actor, "public_id", None),
            **details,
        }
        if status == "completed":
            audit_id = ForensicAuditService.log_attempt(
                entity_type="event_assignment",
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
        elif status == "blocked":
            ForensicAuditService.log_blocked(
                entity_type="event_assignment",
                entity_id=entity_id,
                action=action,
                user_id=None,
                reason=audit_details.get("reason"),
                attempted_value=audit_details.get("booking_ref"),
            )
        else:
            raise ValueError(f"Unsupported forensic audit status: {status}")
    except Exception as exc:
        raise CoordinationError(
            "COORDINATION_AUDIT_FAILED",
            "The coordination audit fact could not be staged",
        ) from exc


@dataclass(frozen=True)
class CoordinationError(Exception):
    code: str
    message: str


class GuestCoordinationService:
    """Application service for the Event host guest-coordination contract."""

    @staticmethod
    def _require(permission, actor, event) -> None:
        allowed, message = permission(actor, event)
        if not allowed:
            raise CoordinationError("EVENT_COORDINATION_FORBIDDEN", message)

    @staticmethod
    def _module_available(module_name: str) -> bool:
        """Return the configured state without making Event depend on a module."""
        if has_request_context():
            return module_enabled(module_name)
        if not has_app_context():
            return True
        flags = current_app.config.get("MODULE_FLAGS") or {}
        # An absent flag is the legacy/default-enabled state.  A configured
        # false value is authoritative, including when no request is active.
        return bool(flags.get(module_name, True))

    @staticmethod
    def _resource_ref(value: Any) -> str | None:
        """Accept public booking references, with a validated legacy ID fallback."""
        if value is None:
            return None
        ref = str(value).strip()
        return ref or None

    @staticmethod
    def _event_dates(event) -> tuple[date | None, date | None]:
        def as_date(value):
            if value is None:
                return None
            return value.date() if isinstance(value, datetime) else value

        return as_date(getattr(event, "start_date", None)), as_date(getattr(event, "end_date", None))

    @staticmethod
    def _assignment_ref(event, registration: EventRegistration) -> str:
        return f"{event.public_id}:{registration.registration_ref}"

    @staticmethod
    def _status_value(value: Any) -> str:
        return str(getattr(value, "value", value) or "").lower()

    @staticmethod
    def _registration(event, registration_ref: str) -> EventRegistration:
        query = EventRegistration.query.filter_by(event_id=event.id, is_deleted=False)
        registration = query.filter_by(registration_ref=registration_ref).first()
        if registration is None:
            raise CoordinationError("INVALID_EVENT_REGISTRATION", "Registration is not part of this event")
        status = getattr(registration, "status", None)
        status_value = getattr(status, "value", status)
        if str(status_value).lower() != "confirmed":
            raise CoordinationError("REGISTRATION_NOT_CONFIRMED", "Only confirmed attendees can be assigned")
        return registration

    @staticmethod
    def dashboard(event, actor, *, search: str | None = None, page: int = 1, per_page: int = 25) -> dict[str, Any]:
        GuestCoordinationService._require(can_view_coordination, actor, event)
        query = EventRegistration.query.filter_by(event_id=event.id, is_deleted=False)
        if search:
            term = f"%{search.strip()}%"
            query = query.filter(
                (EventRegistration.registration_ref.ilike(term))
                | (EventRegistration.full_name.ilike(term))
                | (EventRegistration.email.ilike(term))
            )
        pagination = query.order_by(EventRegistration.id).paginate(
            page=max(1, page), per_page=min(max(1, per_page), 100), error_out=False
        )
        assignments = {}
        for assignment in EventAssignment.query.filter_by(
            event_id=event.id, is_deleted=False
        ).all():
            if assignment.registration_id is not None:
                assignments[('registration', assignment.registration_id)] = assignment
            assignments[('user', assignment.attendee_id)] = assignment
        accommodation_by_id = {}
        transport_by_id = {}
        accommodation_ids = {
            assignment.accommodation_booking_id
            for assignment in assignments.values()
            if assignment.accommodation_booking_id
        }
        transport_ids = {
            assignment.transport_booking_id
            for assignment in assignments.values()
            if assignment.transport_booking_id
        }
        if accommodation_ids and GuestCoordinationService._module_available("accommodation"):
            from app.accommodation.models.booking import AccommodationBooking
            accommodation_by_id = {
                booking.id: booking
                for booking in AccommodationBooking.query.options(
                    joinedload(AccommodationBooking.accommodation_property),
                    joinedload(AccommodationBooking.room_type),
                ).filter(
                    AccommodationBooking.id.in_(accommodation_ids),
                    AccommodationBooking.is_deleted.is_(False),
                ).all()
            }
        if transport_ids and GuestCoordinationService._module_available("transport"):
            from app.transport.models import Booking
            transport_by_id = {
                booking.id: booking
                for booking in Booking.query.options(
                    joinedload(Booking.driver), joinedload(Booking.vehicle)
                ).filter(
                    Booking.id.in_(transport_ids), Booking.is_deleted.is_(False)
                ).all()
            }
        rows = []
        for registration in pagination.items:
            assignment = assignments.get(('registration', registration.id))
            if assignment is None:
                assignment = assignments.get(('user', registration.user_id)) or assignments.get(
                    ('user', getattr(registration, "attendee_user_id", None))
                )
            rows.append({
                "registration_ref": registration.registration_ref,
                "name": registration.full_name,
                "email": registration.email,
                "phone": registration.phone,
                "registration_status": registration.status,
                "accommodation_assigned": bool(assignment and assignment.accommodation_booking_id),
                "transport_assigned": bool(assignment and assignment.transport_booking_id),
                "accommodation": GuestCoordinationService._accommodation_summary(
                    accommodation_by_id.get(getattr(assignment, "accommodation_booking_id", None))
                ),
                "transport": GuestCoordinationService._transport_summary(
                    transport_by_id.get(getattr(assignment, "transport_booking_id", None))
                ),
            })
        return {
            "items": rows,
            "page": pagination.page,
            "pages": pagination.pages,
            "total": pagination.total,
            "accommodation_assigned": EventAssignment.query.filter(
                EventAssignment.event_id == event.id,
                EventAssignment.is_deleted.is_(False),
                EventAssignment.accommodation_booking_id.is_not(None),
            ).count(),
            "transport_assigned": EventAssignment.query.filter(
                EventAssignment.event_id == event.id,
                EventAssignment.is_deleted.is_(False),
                EventAssignment.transport_booking_id.is_not(None),
            ).count(),
        }

    @staticmethod
    def _assignment(event, registration: EventRegistration) -> EventAssignment:
        attendee_id = registration.user_id or getattr(registration, "attendee_user_id", None)
        if attendee_id is None:
            raise CoordinationError(
                "REGISTRATION_IDENTITY_REQUIRED",
                "This attendee must have an account before assignment",
            )
        assignment = EventAssignment.query.filter_by(
            event_id=event.id, registration_id=registration.id
        ).with_for_update().first()
        if assignment is None:
            # Older rows may have been created before registration_id was
            # populated; resolve them by the authoritative attendee FK and
            # backfill the registration link in the same locked transaction.
            assignment = EventAssignment.query.filter_by(
                event_id=event.id, attendee_id=attendee_id
            ).with_for_update().first()
            if assignment is not None:
                assignment.registration_id = registration.id
        if assignment is not None and getattr(assignment, "is_deleted", False):
            assignment.is_deleted = False
            assignment.deleted_at = None
        if assignment is None:
            assignment = EventAssignment(
                event_id=event.id,
                attendee_id=attendee_id,
                registration_id=registration.id,
            )
            db.session.add(assignment)
        return assignment

    @staticmethod
    def _accommodation_summary(booking) -> dict[str, Any] | None:
        if booking is None:
            return None
        room_type = getattr(booking, "room_type", None)
        return {
            "booking_ref": booking.booking_reference,
            "property": getattr(getattr(booking, "accommodation_property", None), "title", None),
            "room_type": getattr(room_type, "name", None),
            "check_in": booking.check_in.isoformat() if booking.check_in else None,
            "check_out": booking.check_out.isoformat() if booking.check_out else None,
        }

    @staticmethod
    def _transport_summary(booking) -> dict[str, Any] | None:
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
    def bulk_assign(event, actor, capability: str, assignments: list[dict[str, Any]]) -> dict[str, Any]:
        """Apply independent assignments and return a result for every attendee."""
        if capability not in {"accommodation", "transport"}:
            raise CoordinationError("INVALID_COORDINATION_CAPABILITY", "Unknown coordination capability")
        if not isinstance(assignments, list) or not assignments:
            raise CoordinationError("INVALID_BULK_ASSIGNMENT", "At least one assignment is required")
        if len(assignments) > 100:
            raise CoordinationError("BULK_ASSIGNMENT_LIMIT", "A bulk request may contain at most 100 attendees")

        results = []
        for item in assignments:
            registration_ref = str(item.get("registration_ref") or "").strip()
            booking_ref = item.get("booking_ref") or item.get("resource_ref") or item.get("booking_id")
            try:
                if capability == "accommodation":
                    assignment = GuestCoordinationService.assign_accommodation(
                        event, actor, registration_ref, booking_ref
                    )
                else:
                    assignment = GuestCoordinationService.assign_transport(
                        event, actor, registration_ref, booking_ref
                    )
                results.append({
                    "registration_ref": registration_ref,
                    "success": True,
                    "assignment_ref": GuestCoordinationService._assignment_ref(
                        event, assignment.registration
                    ),
                    "status": assignment.status,
                })
            except CoordinationError as error:
                db.session.rollback()
                results.append({
                    "registration_ref": registration_ref,
                    "success": False,
                    "code": error.code,
                    "error": error.message,
                })
        return {
            "success": all(result["success"] for result in results),
            "succeeded": sum(result["success"] for result in results),
            "failed": sum(not result["success"] for result in results),
            "results": results,
        }

    @staticmethod
    def _resolve_accommodation_booking(event, resource_ref):
        from app.accommodation.models.booking import AccommodationBooking

        ref = GuestCoordinationService._resource_ref(resource_ref)
        if not ref:
            raise CoordinationError("INVALID_EVENT_RESOURCE", "Accommodation booking reference is required")

        query = AccommodationBooking.query.with_for_update()
        booking = query.filter_by(booking_reference=ref, is_deleted=False).first()
        # Keep old clients working while ensuring the numeric value is never
        # trusted without event, status, date, and capacity checks below.
        if booking is None and ref.isdigit():
            booking = query.filter_by(id=int(ref), is_deleted=False).first()
        if booking is None:
            raise CoordinationError("ACCOMMODATION_BOOKING_NOT_FOUND", "Accommodation booking was not found")
        if booking.event_id != event.id and str(booking.context_id or "") not in {
            str(event.public_id), str(getattr(event, "event_ref", "")), str(event.slug)
        }:
            raise CoordinationError("BOOKING_EVENT_MISMATCH", "Accommodation booking is not reserved for this event")
        if GuestCoordinationService._status_value(booking.status) not in {
            "held", "confirmed", "pending", "pending_approval"
        }:
            raise CoordinationError("ACCOMMODATION_BOOKING_UNAVAILABLE", "Accommodation booking is not assignable")

        event_start, event_end = GuestCoordinationService._event_dates(event)
        booking_start = GuestCoordinationService._event_dates(
            SimpleNamespace(start_date=booking.check_in, end_date=booking.check_out)
        )[0]
        booking_end = GuestCoordinationService._event_dates(
            SimpleNamespace(start_date=booking.check_in, end_date=booking.check_out)
        )[1]
        if event_start and booking_start is None:
            raise CoordinationError("ACCOMMODATION_DATES_MISMATCH", "Booking has no check-in date")
        if event_end and booking_end is None:
            raise CoordinationError("ACCOMMODATION_DATES_MISMATCH", "Booking has no check-out date")
        if event_start and booking_start > event_start:
            raise CoordinationError("ACCOMMODATION_DATES_MISMATCH", "Booking starts after the event")
        if event_end and booking_end < event_end:
            raise CoordinationError("ACCOMMODATION_DATES_MISMATCH", "Booking ends before the event")
        room_type = getattr(booking, "room_type", None)
        if room_type is not None and not room_type.is_active:
            raise CoordinationError("ACCOMMODATION_ROOM_UNAVAILABLE", "Room type is not active")
        room_capacity = getattr(room_type, "max_guests", None)
        if room_capacity is not None and int(booking.num_guests or 1) > room_capacity:
            raise CoordinationError("ACCOMMODATION_CAPACITY_EXCEEDED", "Room type capacity is insufficient")
        return booking

    @staticmethod
    def _resolve_transport_booking(event, resource_ref):
        from app.transport.models import Booking, DriverProfile, Vehicle

        ref = GuestCoordinationService._resource_ref(resource_ref)
        if not ref:
            raise CoordinationError("INVALID_EVENT_RESOURCE", "Transport booking reference is required")
        query = Booking.query.with_for_update()
        booking = query.filter_by(booking_reference=ref, is_deleted=False).first()
        if booking is None and ref.isdigit():
            booking = query.filter_by(id=int(ref), is_deleted=False).first()
        if booking is None:
            raise CoordinationError("TRANSPORT_BOOKING_NOT_FOUND", "Transport booking was not found")
        if booking.event_id != event.id:
            raise CoordinationError("BOOKING_EVENT_MISMATCH", "Transport booking is not reserved for this event")
        if GuestCoordinationService._status_value(booking.status) not in {"confirmed", "assigned"}:
            raise CoordinationError("TRANSPORT_BOOKING_UNAVAILABLE", "Transport booking is not assignable")

        driver = getattr(booking, "driver", None) or db.session.get(
            DriverProfile, booking.assigned_driver_id
        )
        vehicle = getattr(booking, "vehicle", None) or db.session.get(
            Vehicle, booking.assigned_vehicle_id
        )
        if driver is None or vehicle is None:
            raise CoordinationError("TRANSPORT_RESOURCE_INCOMPLETE", "Transport booking has no eligible driver and vehicle")
        if getattr(driver, "is_deleted", False) or not getattr(driver, "is_available", False) or not getattr(driver, "is_online", False):
            raise CoordinationError("DRIVER_UNAVAILABLE", "The assigned driver is not available")
        if GuestCoordinationService._status_value(getattr(driver, "compliance_status", None)) != "approved":
            raise CoordinationError("DRIVER_NOT_APPROVED", "The assigned driver is not approved")
        if GuestCoordinationService._status_value(getattr(driver, "verification_tier", None)) not in {
            "platform_verified", "event_certified"
        }:
            raise CoordinationError("DRIVER_NOT_APPROVED", "The assigned driver is not verified for event service")
        if getattr(vehicle, "is_deleted", False) or GuestCoordinationService._status_value(
            getattr(vehicle, "status", "")
        ) != "active":
            raise CoordinationError("VEHICLE_UNAVAILABLE", "The assigned vehicle is not active")
        if not getattr(vehicle, "is_available", False) and getattr(
            vehicle, "current_booking_id", None
        ) != booking.id:
            raise CoordinationError("VEHICLE_UNAVAILABLE", "The assigned vehicle is not available")
        capacity = getattr(vehicle, "passenger_capacity", None)
        if capacity is not None and capacity < int(booking.passenger_count or 1):
            raise CoordinationError("TRANSPORT_CAPACITY_EXCEEDED", "The vehicle has no remaining capacity")
        return booking

    @staticmethod
    def _commit_assignment(event, actor, registration, assignment, capability, resource_ref, previous_ref):
        assignment.assigned_by_id = getattr(actor, "id", None)
        assignment.managed_by = getattr(actor, "id", None)
        assignment.assigned_at = datetime.now(timezone.utc)
        assignment.status = "active"
        db.session.flush()
        event_type = {
            "accommodation": EventType.EVENT_ACCOMMODATION_ASSIGNED
            if previous_ref is None else EventType.EVENT_ACCOMMODATION_CHANGED,
            "transport": EventType.EVENT_TRANSPORT_ASSIGNED
            if previous_ref is None else EventType.EVENT_TRANSPORT_CHANGED,
        }[capability]
        envelope = emit_event(
            event_type,
            payload={
                "event_ref": str(event.public_id),
                "registration_ref": registration.registration_ref,
                "assignment_ref": GuestCoordinationService._assignment_ref(event, registration),
                "capability": capability,
                "previous_booking_ref": previous_ref,
                "booking_ref": resource_ref,
                "actor_public_id": getattr(actor, "public_id", None),
            },
            aggregate_type="event_assignment",
            aggregate_id=GuestCoordinationService._assignment_ref(event, registration),
            actor_type="user",
            actor_id=getattr(actor, "id", None),
            session=db.session,
        )
        if envelope is None:
            raise CoordinationError(
                "COORDINATION_EVENT_FAILED",
                "The assignment audit event could not be staged",
            )
        _forensic_audit(
            "coordination_assignment",
            event,
            registration,
            actor,
            status="completed",
            details={
                "capability": capability,
                "previous_booking_ref": previous_ref,
                "booking_ref": resource_ref,
            },
        )
        db.session.commit()
        return assignment

    @staticmethod
    def assign_accommodation(event, actor, registration_ref: str, booking_ref: str) -> EventAssignment:
        GuestCoordinationService._require(can_assign_accommodation, actor, event)
        if not GuestCoordinationService._module_available("accommodation"):
            raise CoordinationError("ACCOMMODATION_UNAVAILABLE", "Accommodation service is currently unavailable")
        registration = GuestCoordinationService._registration(event, registration_ref)
        try:
            booking = GuestCoordinationService._resolve_accommodation_booking(event, booking_ref)
            assignment = GuestCoordinationService._assignment(event, registration)
            previous = assignment.accommodation_booking_id
            if previous == booking.id:
                return assignment
            active_count = EventAssignment.query.filter_by(
                event_id=event.id, accommodation_booking_id=booking.id, is_deleted=False
            ).filter(EventAssignment.registration_id != registration.id).count()
            if active_count >= max(1, int(booking.num_guests or 1)):
                raise CoordinationError("ACCOMMODATION_CAPACITY_EXCEEDED", "Accommodation booking has no remaining capacity")
            assignment.accommodation_booking_id = booking.id
            previous_ref = None
            if previous:
                from app.accommodation.models.booking import AccommodationBooking
                old = db.session.get(AccommodationBooking, previous)
                previous_ref = getattr(old, "booking_reference", None)
            return GuestCoordinationService._commit_assignment(
                event, actor, registration, assignment, "accommodation", booking.booking_reference, previous_ref
            )
        except CoordinationError:
            db.session.rollback()
            raise
        except Exception as exc:
            db.session.rollback()
            raise CoordinationError("COORDINATION_FAILED", "Accommodation assignment could not be completed") from exc

    @staticmethod
    def assign_transport(event, actor, registration_ref: str, booking_ref: str) -> EventAssignment:
        GuestCoordinationService._require(can_assign_transport, actor, event)
        if not GuestCoordinationService._module_available("transport"):
            raise CoordinationError("TRANSPORT_UNAVAILABLE", "Transport service is currently unavailable")
        registration = GuestCoordinationService._registration(event, registration_ref)
        try:
            booking = GuestCoordinationService._resolve_transport_booking(event, booking_ref)
            assignment = GuestCoordinationService._assignment(event, registration)
            previous = assignment.transport_booking_id
            if previous == booking.id:
                return assignment
            active_count = EventAssignment.query.filter_by(
                event_id=event.id, transport_booking_id=booking.id, is_deleted=False
            ).filter(EventAssignment.registration_id != registration.id).count()
            if active_count >= max(1, int(booking.passenger_count or 1)):
                raise CoordinationError("TRANSPORT_CAPACITY_EXCEEDED", "Transport booking has no remaining capacity")
            assignment.transport_booking_id = booking.id
            previous_ref = None
            if previous:
                from app.transport.models import Booking
                old = db.session.get(Booking, previous)
                previous_ref = getattr(old, "booking_reference", None)
            return GuestCoordinationService._commit_assignment(
                event, actor, registration, assignment, "transport", booking.booking_reference, previous_ref
            )
        except CoordinationError:
            db.session.rollback()
            raise
        except Exception as exc:
            db.session.rollback()
            raise CoordinationError("COORDINATION_FAILED", "Transport assignment could not be completed") from exc

    @staticmethod
    def cancel(event, actor, registration_ref: str, capability: str) -> EventAssignment:
        GuestCoordinationService._require(can_cancel_assignment, actor, event)
        if capability not in {"accommodation", "transport"}:
            raise CoordinationError("INVALID_COORDINATION_CAPABILITY", "Unknown coordination capability")
        if not GuestCoordinationService._module_available(capability):
            raise CoordinationError(
                f"{capability.upper()}_UNAVAILABLE",
                f"{capability.title()} service is currently unavailable",
            )
        registration = GuestCoordinationService._registration(event, registration_ref)
        assignment = EventAssignment.query.filter_by(
            event_id=event.id, registration_id=registration.id, is_deleted=False
        ).with_for_update().first()
        if assignment is None:
            raise CoordinationError("ASSIGNMENT_NOT_FOUND", "No active assignment exists for this attendee")
        previous_id = getattr(assignment, f"{capability}_booking_id")
        if previous_id is None:
            raise CoordinationError("ASSIGNMENT_NOT_FOUND", f"No {capability} assignment exists for this attendee")
        if capability == "accommodation":
            from app.accommodation.models.booking import AccommodationBooking
            old = db.session.get(AccommodationBooking, previous_id)
        else:
            from app.transport.models import Booking
            old = db.session.get(Booking, previous_id)
        previous_ref = getattr(old, "booking_reference", None)
        if capability == "accommodation":
            assignment.accommodation_booking_id = None
        else:
            assignment.transport_booking_id = None
        assignment.status = "active" if (
            assignment.accommodation_booking_id or assignment.transport_booking_id
        ) else "cancelled"
        assignment.assigned_by_id = getattr(actor, "id", None)
        assignment.managed_by = getattr(actor, "id", None)
        assignment.assigned_at = datetime.now(timezone.utc)
        envelope = emit_event(
            EventType.EVENT_COORDINATION_CANCELLED,
            payload={
                "event_ref": str(event.public_id),
                "registration_ref": registration.registration_ref,
                "capability": capability,
                "assignment_ref": GuestCoordinationService._assignment_ref(event, registration),
                "previous_booking_ref": previous_ref,
            },
            aggregate_type="event_assignment",
            aggregate_id=GuestCoordinationService._assignment_ref(event, registration),
            actor_type="user",
            actor_id=getattr(actor, "id", None),
            session=db.session,
        )
        if envelope is None:
            db.session.rollback()
            raise CoordinationError(
                "COORDINATION_EVENT_FAILED",
                "The cancellation audit event could not be staged",
            )
        _forensic_audit(
            "coordination_cancellation",
            event,
            registration,
            actor,
            status="completed",
            details={"capability": capability, "previous_booking_ref": previous_ref},
        )
        db.session.commit()
        return assignment
