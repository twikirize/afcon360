# app/transport/services/assignment_service.py
"""
AFCON360 Transport - Canonical Dispatch Assignment Service (TH-3-D2).

Single authority for claim (atomic driver+vehicle assignment) and release
(resource-freeing terminal transitions). Every assignment path -- admin
assign, driver offer accept, dispatch recovery -- MUST converge here.

Decision A compliance: zero schema change. This module executes guarded
SQL UPDATE statements against the existing tables only; no new tables,
columns, enums, CHECK constraints, or migrations.
"""
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import sqlalchemy as sa
from flask import current_app

from app.extensions import db
from app.transport.models import (
    Booking,
    DriverProfile,
    Vehicle,
    BookingStatus,
    ComplianceStatus,
)
from app.utils.audit import audit_log

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Status sets -- single source of truth for active-assignment semantics
# ---------------------------------------------------------------------------

ACTIVE_ASSIGNMENT_STATUSES = frozenset({
    BookingStatus.ASSIGNED.value,
    BookingStatus.DRIVER_EN_ROUTE.value,
    BookingStatus.PICKUP_ARRIVED.value,
    BookingStatus.IN_PROGRESS.value,
    BookingStatus.DISPUTED.value,
})

TERMINAL_RELEASE_STATUSES = frozenset({
    BookingStatus.COMPLETED.value,
    BookingStatus.CANCELLED.value,
    BookingStatus.NO_SHOW.value,
})

CLAIMABLE_STATUSES = frozenset({BookingStatus.CONFIRMED.value})

VEHICLE_ACTIVE_STATUS = "active"


class DispatchClaimError(Exception):
    """Typed failure surfaced by the canonical assignment service.

    ``kind`` is a stable machine-readable code used by API layers and tests:
    booking_unavailable, driver_unavailable, vehicle_unavailable,
    unauthorized, invalid_state, offer_expired, offer_conflict.
    """

    def __init__(self, kind: str, message: str, **context: Any):
        super().__init__(message)
        self.kind = kind
        self.message = message
        self.context = context or {}


def _actor_is_admin(actor) -> bool:
    """Admin/owner/super_admin detection that does not depend on a request.

    ``flask.session`` is unavailable outside request contexts (tests, beat
    tasks), so this walks the actor's assigned roles directly.
    """
    if actor is None:
        return False
    for ur in getattr(actor, "roles", None) or []:
        role = getattr(ur, "role", None)
        if role is not None and role.name in ("admin", "super_admin", "owner"):
            return True
    return False


class AssignmentService:
    """Canonical dispatch assignment service (claim / release)."""

    # ------------------------------------------------------------------ #
    # Claim
    # ------------------------------------------------------------------ #
    @staticmethod
    def claim(
        booking_ref: str,
        driver_id: int,
        vehicle_id: int,
        *,
        actor=None,
        force: bool = False,
    ) -> Dict[str, Any]:
        """Atomically claim a CONFIRMED, unassigned booking for one
        (driver, vehicle) pair.

        All three guarded UPDATEs run in a single transaction; if any guard
        fails the whole transaction is rolled back and a typed
        ``DispatchClaimError`` is raised. A successful claim commits, frees
        the driver/vehicle from further claiming, and returns the result.

        ``force`` is admin-only and MAY relax the driver's ``is_online`` /
        readiness and the vehicle readiness gates. It NEVER relaxes the
        booking state gate, the reverse active-booking conflict check, or
        any ownership/authorization/transaction guarantee.
        """
        if force and not _actor_is_admin(actor):
            raise DispatchClaimError(
                "unauthorized",
                "force claims are restricted to admin/super_admin/owner actors",
            )

        booking_row = db.session.execute(
            sa.select(
                Booking.__table__.c.id,
                Booking.__table__.c.user_id,
                Booking.__table__.c.booking_reference,
            ).where(Booking.__table__.c.booking_reference == booking_ref)
        ).first()
        if booking_row is None:
            raise DispatchClaimError(
                "booking_unavailable", "booking not found", booking_ref=booking_ref
            )
        booking_id = booking_row.id
        passenger_user_id = booking_row.user_id

        now = datetime.now(timezone.utc)
        forced = bool(force)

        # ------------------------------------------------------------------
        # r1 - booking must be CONFIRMED and completely unassigned
        # ------------------------------------------------------------------
        r1 = db.session.execute(
            sa.update(Booking.__table__)
            .where(
                Booking.__table__.c.id == booking_id,
                Booking.__table__.c.status == BookingStatus.CONFIRMED.value,
                Booking.__table__.c.assigned_driver_id.is_(None),
                Booking.__table__.c.assigned_vehicle_id.is_(None),
                Booking.__table__.c.is_deleted.is_(False),
            )
            .values(
                status=BookingStatus.ASSIGNED.value,
                assigned_driver_id=driver_id,
                assigned_vehicle_id=vehicle_id,
                driver_assigned_at=now,
            )
            .execution_options(synchronize_session=False)
        )
        if r1.rowcount != 1:
            db.session.rollback()
            raise DispatchClaimError(
                "booking_unavailable",
                "booking is no longer claimable (already assigned, cancelled, or deleted)",
                booking_ref=booking_ref,
                booking_id=booking_id,
            )

        # ------------------------------------------------------------------
        # r2 - driver: admin-ready and not engaged on another active booking
        # ------------------------------------------------------------------
        driver_engaged_other = sa.exists(
            sa.select(sa.literal(1))
            .select_from(Booking.__table__)
            .where(
                Booking.__table__.c.assigned_driver_id == driver_id,
                Booking.__table__.c.id != booking_id,
                Booking.__table__.c.status.in_(ACTIVE_ASSIGNMENT_STATUSES),
                Booking.__table__.c.is_deleted.is_(False),
            )
        )
        r2 = db.session.execute(
            sa.update(DriverProfile.__table__)
            .where(
                DriverProfile.__table__.c.id == driver_id,
                DriverProfile.__table__.c.is_deleted.is_(False),
                DriverProfile.__table__.c.compliance_status
                == ComplianceStatus.APPROVED.value,
                sa.or_(DriverProfile.__table__.c.is_online.is_(True), forced),
                sa.or_(DriverProfile.__table__.c.is_available.is_(True), forced),
                ~driver_engaged_other,
            )
            .values(is_available=False)
            .execution_options(synchronize_session=False)
        )
        if r2.rowcount != 1:
            db.session.rollback()
            raise DispatchClaimError(
                "driver_unavailable",
                "driver is not claimable (missing, offline, busy on another "
                "active booking, unapproved, or deleted)",
                driver_id=driver_id,
                booking_ref=booking_ref,
            )

        # ------------------------------------------------------------------
        # r3 - vehicle: active and not engaged on another active booking
        # ------------------------------------------------------------------
        vehicle_engaged_other = sa.exists(
            sa.select(sa.literal(1))
            .select_from(Booking.__table__)
            .where(
                Booking.__table__.c.assigned_vehicle_id == vehicle_id,
                Booking.__table__.c.id != booking_id,
                Booking.__table__.c.status.in_(ACTIVE_ASSIGNMENT_STATUSES),
                Booking.__table__.c.is_deleted.is_(False),
            )
        )
        r3 = db.session.execute(
            sa.update(Vehicle.__table__)
            .where(
                Vehicle.__table__.c.id == vehicle_id,
                Vehicle.__table__.c.is_deleted.is_(False),
                Vehicle.__table__.c.status == VEHICLE_ACTIVE_STATUS,
                sa.or_(Vehicle.__table__.c.is_available.is_(True), forced),
                ~vehicle_engaged_other,
            )
            .values(is_available=False)
            .execution_options(synchronize_session=False)
        )
        if r3.rowcount != 1:
            db.session.rollback()
            raise DispatchClaimError(
                "vehicle_unavailable",
                "vehicle is not claimable (missing, inactive, busy on another "
                "active booking, or deleted)",
                vehicle_id=vehicle_id,
                booking_ref=booking_ref,
            )

        audit_log(
            action="dispatch_claim",
            resource_type="booking",
            resource_id=booking_id,
            user_id=getattr(actor, "id", None),
            details={
                "booking_reference": booking_ref,
                "driver_id": driver_id,
                "vehicle_id": vehicle_id,
                "force": bool(force),
            },
            db_session=db.session,
        )

        db.session.commit()
        db.session.expire_all()

        if passenger_user_id:
            AssignmentService._notify_assigned(passenger_user_id, booking_id, booking_ref)

        logger.info("Dispatch claim committed for booking %s (driver=%s, vehicle=%s)",
                    booking_ref, driver_id, vehicle_id)

        return {
            "booking_id": booking_id,
            "booking_reference": booking_ref,
            "status": BookingStatus.ASSIGNED.value,
            "driver_id": driver_id,
            "vehicle_id": vehicle_id,
            "force": bool(force),
        }

    @staticmethod
    def _notify_assigned(user_id: int, booking_id: int, booking_ref: str) -> None:
        """Best-effort durable driver_assigned notification (never fatal)."""
        try:
            from app.notifications.services import NotificationService

            booking = db.session.get(Booking, booking_id)
            if booking is None:
                return
            NotificationService.send_transport_notification(
                user_id=user_id,
                booking=booking,
                notification_type="driver_assigned",
                channel="in_app",
            )
        except Exception:
            current_app.logger.warning(
                "driver_assigned notification failed (non-fatal) for booking %s",
                booking_ref,
                exc_info=True,
            )

    # ------------------------------------------------------------------ #
    # Release
    # ------------------------------------------------------------------ #
    @staticmethod
    def release(
        booking_id: int,
        terminal_status,
        *,
        actor=None,
        reason: Optional[str] = None,
        audit_extra: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Transition a booking to a terminal status.

        If the booking currently holds an assignment, the resource-freeing
        transition runs in the SAME transaction. Late-release protection:
        a driver/vehicle that has already been re-claimed by another active
        booking is NEVER freed (guarded by a reverse ``NOT EXISTS``) -- the
        release cannot clobber a newer claim. Repeated release of an already
        terminal booking is idempotent.
        """
        terminal = (
            terminal_status.value
            if hasattr(terminal_status, "value")
            else terminal_status
        )
        if terminal not in TERMINAL_RELEASE_STATUSES:
            raise DispatchClaimError(
                "invalid_state", f"{terminal} is not a terminal release status"
            )

        row = db.session.execute(
            sa.select(
                Booking.__table__.c.id,
                Booking.__table__.c.status,
                Booking.__table__.c.assigned_driver_id,
                Booking.__table__.c.assigned_vehicle_id,
                Booking.__table__.c.booking_reference,
            ).where(Booking.__table__.c.id == booking_id)
        ).first()
        if row is None:
            raise DispatchClaimError("booking_unavailable", "booking not found")

        assigned = row.assigned_driver_id is not None or row.assigned_vehicle_id is not None

        if assigned:
            transition = db.session.execute(
                sa.update(Booking.__table__)
                .where(
                    Booking.__table__.c.id == booking_id,
                    Booking.__table__.c.status.in_(ACTIVE_ASSIGNMENT_STATUSES),
                    Booking.__table__.c.is_deleted.is_(False),
                )
                .values(
                    status=terminal,
                    assigned_driver_id=None,
                    assigned_vehicle_id=None,
                )
                .execution_options(synchronize_session=False)
            )
            if transition.rowcount != 1:
                db.session.rollback()
                raise DispatchClaimError(
                    "invalid_state",
                    "booking is not in an active assignment state",
                    booking_id=booking_id,
                )

            if row.assigned_driver_id is not None:
                db.session.execute(
                    sa.update(DriverProfile.__table__)
                    .where(
                        DriverProfile.__table__.c.id == row.assigned_driver_id,
                        DriverProfile.__table__.c.is_available.is_(False),
                        DriverProfile.__table__.c.is_deleted.is_(False),
                        ~sa.exists(
                            sa.select(sa.literal(1))
                            .select_from(Booking.__table__)
                            .where(
                                Booking.__table__.c.assigned_driver_id
                                == row.assigned_driver_id,
                                Booking.__table__.c.id != booking_id,
                                Booking.__table__.c.status.in_(ACTIVE_ASSIGNMENT_STATUSES),
                                Booking.__table__.c.is_deleted.is_(False),
                            )
                        ),
                    )
                    .values(is_available=True)
                    .execution_options(synchronize_session=False)
                )

            if row.assigned_vehicle_id is not None:
                db.session.execute(
                    sa.update(Vehicle.__table__)
                    .where(
                        Vehicle.__table__.c.id == row.assigned_vehicle_id,
                        Vehicle.__table__.c.is_available.is_(False),
                        Vehicle.__table__.c.is_deleted.is_(False),
                        ~sa.exists(
                            sa.select(sa.literal(1))
                            .select_from(Booking.__table__)
                            .where(
                                Booking.__table__.c.assigned_vehicle_id
                                == row.assigned_vehicle_id,
                                Booking.__table__.c.id != booking_id,
                                Booking.__table__.c.status.in_(ACTIVE_ASSIGNMENT_STATUSES),
                                Booking.__table__.c.is_deleted.is_(False),
                            )
                        ),
                    )
                    .values(is_available=True)
                    .execution_options(synchronize_session=False)
                )
        else:
            transition = db.session.execute(
                sa.update(Booking.__table__)
                .where(
                    Booking.__table__.c.id == booking_id,
                    Booking.__table__.c.is_deleted.is_(False),
                )
                .values(status=terminal)
                .execution_options(synchronize_session=False)
            )
            if transition.rowcount != 1:
                db.session.rollback()
                raise DispatchClaimError("invalid_state", "booking is not releasable")

        audit_log(
            action="dispatch_release",
            resource_type="booking",
            resource_id=booking_id,
            user_id=getattr(actor, "id", None),
            details={
                "status": terminal,
                "reason": reason,
                **(audit_extra or {}),
            },
            db_session=db.session,
        )

        db.session.commit()
        db.session.expire_all()

        logger.info("Dispatch release committed for booking %s -> %s",
                    row.booking_reference, terminal)

        return {
            "booking_id": booking_id,
            "booking_reference": row.booking_reference,
            "status": terminal,
            "released": assigned,
        }


def get_assignment_service():
    """Service-locator helper consistent with the transport module pattern."""
    return AssignmentService