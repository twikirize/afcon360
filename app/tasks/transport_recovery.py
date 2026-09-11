"""
app/tasks/transport_recovery.py

Scheduled recovery tasks for the transport dispatch system (TH-3-D2).

- ``transport.dispatch_recovery`` - defensive sweep of transient Redis
  offers. Offer TTLs are the primary expiry mechanism; this beat is a
  safety net for orphaned offer keys whose creator crashed before setting
  a TTL (or after a Redis eviction).
- ``transport.stall_recovery`` - terminal-timeout recovery: a booking that
  stays ASSIGNED with no driver en-route beyond
  ``TRANSPORT_STALL_TIMEOUT_SECONDS`` (default 600) is cancelled through the
  canonical release path and the passenger is notified. Drivers/vehicles
  are NEVER auto-replaced; the booking is left for a human/next offer.
"""

import logging
import os
from datetime import datetime, timedelta, timezone

from app.celery_app import celery_app
from app.extensions import db
from app.transport.models import Booking, BookingStatus

logger = logging.getLogger(__name__)

TRANSPORT_STALL_TIMEOUT_SECONDS = int(
    os.environ.get("TRANSPORT_STALL_TIMEOUT_SECONDS", "600")
)


@celery_app.task(name="transport.dispatch_recovery")
def dispatch_recovery() -> dict:
    """Defensive sweep of expired/orphaned transient Redis offers.

    Returns:
        dict: sweep results (checked / cleaned counts).
    """
    try:
        from app.transport.services.offer_service import OfferService

        checked, cleaned = OfferService.sweep_expired()
        if cleaned > 0:
            logger.info(f"Transport dispatch recovery cleaned {cleaned} expired offers")
        return {"checked": checked, "cleaned": cleaned}
    except Exception as e:
        logger.error(f"Transport dispatch recovery failed: {e}", exc_info=True)
        return {"checked": 0, "cleaned": 0, "error": str(e)}


@celery_app.task(name="transport.stall_recovery")
def stall_recovery(stall_seconds: int = None, dry_run: bool = False) -> dict:
    """Cancel bookings stuck ASSIGNED with no driver en-route.

    A booking satisfies the stall condition when:

        status == ASSIGNED
        AND driver_en_route_at IS NULL
        AND is_deleted IS FALSE
        AND driver_assigned_at is older than the stall timeout

    Recovered bookings transition through the canonical release path
    (AssignmentService.release, terminal status CANCELLED) so drivers and
    vehicles are freed only when no re-claimed active booking references
    them. No automatic driver replacement is attempted.

    Args:
        stall_seconds: Override for the stall timeout (default
            TRANSPORT_STALL_TIMEOUT_SECONDS env / 600).
        dry_run: When True, report candidates without mutating anything.

    Returns:
        dict: candidates found / recovered counts and booking ids.
    """
    try:
        timeout = stall_seconds or TRANSPORT_STALL_TIMEOUT_SECONDS
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=timeout)

        candidates = (
            Booking.query.filter(
                Booking.status == BookingStatus.ASSIGNED.value,
                Booking.driver_en_route_at.is_(None),
                Booking.is_deleted.is_(False),
                Booking.driver_assigned_at < cutoff,
            ).all()
        )

        recovered = []
        for booking in candidates:
            if dry_run:
                continue
            try:
                from app.transport.services.assignment_service import get_assignment_service

                get_assignment_service().release(
                    booking.id,
                    BookingStatus.CANCELLED,
                    actor=None,
                    reason="stall_timeout",
                    audit_extra={"stall_seconds": timeout},
                )
                recovered.append(booking.id)
                logger.info(
                    f"Stall recovery cancelled booking {booking.id} "
                    f"(ref {booking.booking_reference}) at timeout {timeout}s"
                )
                _notify_stall_cancelled(booking)
            except Exception as e:
                logger.warning(
                    f"Stall recovery failed to cancel booking {booking.id}: {e}",
                    exc_info=True,
                )

        if recovered:
            logger.info(
                f"Transport stall recovery handled {len(recovered)} "
                f"stalled booking(s): {recovered}"
            )
        return {
            "candidates": [b.id for b in candidates],
            "recovered": recovered,
            "dry_run": dry_run,
            "timeout_seconds": timeout,
        }
    except Exception as e:
        logger.error(f"Transport stall recovery failed: {e}", exc_info=True)
        return {"candidates": [], "recovered": [], "error": str(e)}
    finally:
        db.session.rollback()


def _notify_stall_cancelled(booking: Booking) -> None:
    """Best-effort durable passenger notification after a stall cancel.

    Never raises: a broken notification transport must not fail the task.
    """
    try:
        from app.notifications.models import NotificationModule, NotificationType
        from app.notifications.services import NotificationService

        NotificationService.send(
            user_id=booking.user_id,
            notification_type=NotificationType.BOOKING_CANCELLED,
            title="Your ride was cancelled",
            message=(
                f"Booking #{booking.booking_reference} was cancelled because "
                "the driver did not begin the trip in time."
            ),
            data={"booking_id": booking.id, "reason": "stall_timeout"},
            channels=["in_app"],
            module=NotificationModule.TRANSPORT,
        )
    except Exception as e:
        logger.warning(
            f"Stall-cancel notification for booking {booking.id} failed: {e}"
        )