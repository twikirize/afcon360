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

Scheduled-route execution (TH-3-D3):

- ``transport.scheduled_route_execution`` - a beat task that resolves due
  ``ScheduledRoute`` departures into the existing executable booking/dispatch
  lifecycle. A route is due when ``next_departure`` has passed and its
  departure has not yet been claimed (``last_departure IS NULL`` or
  ``last_departure < next_departure``). The departure is claimed atomically
  (guarded UPDATE setting ``last_departure = next_departure``; exactly one
  worker wins, so concurrent beats cannot double-dispatch), then the route's
  attached CONFIRMED+unassigned bookings (via ``Booking.assigned_route_id``)
  advance through the canonical ``MatchingService.discover_and_offer`` chain
  (offer -> AssignmentService.claim -> ASSIGNED -> DriverTrip).
  ``next_departure`` is NOT auto-advanced: no code parses ``schedule_pattern``
  and the interval must not be invented; operators re-arm a route's next slot
  through the route API.
"""

import logging
import os
from datetime import datetime, timedelta, timezone

from sqlalchemy import or_

from app.celery_app import celery_app
from app.extensions import db
from app.transport.models import Booking, BookingStatus, ScheduledRoute

logger = logging.getLogger(__name__)

TRANSPORT_STALL_TIMEOUT_SECONDS = int(
    os.environ.get("TRANSPORT_STALL_TIMEOUT_SECONDS", "600")
)


@celery_app.task(name="transport.dispatch_recovery")
def dispatch_recovery() -> dict:
    """Defensive sweep of expired/orphaned Redis offers PLUS rediscovery of
    CONFIRMED+unassigned bookings (pool -> ranker -> transient offer).

    Offer TTLs are the primary expiry mechanism; the sweep is a safety net for
    orphaned offer keys. Rediscovery re-advertises ranked candidates for
    bookings that never got an offer (offer loss, Redis outage restart,
    mid-flight crash before creation). Redis is never authoritative — the
    booking stays CONFIRMED/unassigned until a driver's claim commits.

    Returns:
        dict: sweep results (checked / cleaned) and rediscovery results
            (bookings considered / offers created).
    """
    result = {"checked": 0, "cleaned": 0}
    try:
        from app.transport.services.offer_service import OfferService

        checked, cleaned = OfferService.sweep_expired()
        result = {"checked": checked, "cleaned": cleaned}
        if cleaned > 0:
            logger.info(f"Transport dispatch recovery cleaned {cleaned} expired offers")
    except Exception as e:
        logger.error(f"Transport dispatch recovery sweep failed: {e}", exc_info=True)
        result = {"checked": 0, "cleaned": 0, "error": str(e)}

    rediscovered = 0
    offers_created = 0
    try:
        from flask import current_app

        from app.transport.services.matching_service import MatchingService

        batch = int(current_app.config.get("TRANSPORT_DISPATCH_RECOVERY_BATCH", 50))
        from app.transport.services.assignment_service import CLAIMABLE_STATUSES

        candidates = (
            Booking.query.filter(
                Booking.status.in_(CLAIMABLE_STATUSES),
                Booking.assigned_driver_id.is_(None),
                Booking.is_deleted.is_(False),
            ).limit(batch).all()
        )
        for booking in candidates:
            outcome = MatchingService.discover_and_offer(booking.id)
            rediscovered += 1
            offers_created += int(outcome.get("offers_created", 0))

        result["rediscovered"] = rediscovered
        result["offers_created"] = offers_created
    except Exception as e:
        logger.error(f"Transport dispatch recovery rediscovery failed: {e}", exc_info=True)
        result["rediscovery_error"] = str(e)
    finally:
        db.session.rollback()

    if rediscovered:
        logger.info(
            f"Transport dispatch recovery rediscovered {rediscovered} booking(s), "
            f"created {offers_created} offer(s)"
        )
    return result


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
        if stall_seconds is None:
            from flask import current_app

            stall_seconds = int(
                current_app.config.get(
                    "TRANSPORT_STALL_TIMEOUT_SECONDS", TRANSPORT_STALL_TIMEOUT_SECONDS
                )
            )
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


@celery_app.task(name="transport.scheduled_route_execution")
def scheduled_route_execution(batch: int = None, dry_run: bool = False) -> dict:
    """Resolve due ScheduledRoute departures into the canonical dispatch chain.

    A ScheduledRoute is *due* when:

        next_departure <= now
        AND is_active IS TRUE
        AND is_cancelled IS FALSE
        AND is_deleted IS FALSE
        AND (last_departure IS NULL OR last_departure < next_departure)

    The ``last_departure`` guard is the idempotency/claim marker: the departure
    at a given ``next_departure`` is executed once. The claim is a guarded
    UPDATE (``SET last_departure = next_departure WHERE still unclaimed``); only
    the worker whose UPDATE returns exactly one row proceeds, so concurrent
    beats/workers cannot double-execute a departure.

    For each claimed route, the route's attached CONFIRMED+unassigned bookings
    (``Booking.assigned_route_id``) advance through the existing dispatch
    lifecycle via ``MatchingService.discover_and_offer`` -- the SAME entry point
    used by ``dispatch_recovery`` -- producing a transient offer per booking that
    a driver later accepts through the canonical ``AssignmentService.claim``
    (ASSIGNED -> DriverTrip). No new booking is created (Booking.user_id is NOT
    NULL; there is no departure-instance entity), so this is per-user scheduled
    Booking progression, not ScheduledRoute instance creation.

    ``next_departure`` is intentionally NOT rolled forward here: ``schedule_pattern``
    is never parsed anywhere and the recurrence interval must not be invented.
    Operators re-arm the next slot through the route API.

    Args:
        batch: Max routes to consider per run (default config
            ``TRANSPORT_SCHEDULED_EXECUTION_BATCH`` / 25).
        dry_run: When True, report due routes without claiming or dispatching.

    Returns:
        dict: considered / claimed / bookings dispatched / offers created.
    """
    result = {
        "candidates": [],
        "considered": 0,
        "claimed": [],
        "dry_run": dry_run,
        "bookings_dispatched": [],
        "offers_created": 0,
    }
    try:
        from flask import current_app

        from app.transport.services.assignment_service import CLAIMABLE_STATUSES
        from app.transport.services.matching_service import MatchingService

        if batch is None:
            batch = int(
                current_app.config.get("TRANSPORT_SCHEDULED_EXECUTION_BATCH", 25)
            )

        now = datetime.now(timezone.utc)
        due_routes = (
            ScheduledRoute.query.filter(
                ScheduledRoute.next_departure.is_not(None),
                ScheduledRoute.next_departure <= now,
                ScheduledRoute.is_active.is_(True),
                ScheduledRoute.is_cancelled.is_(False),
                ScheduledRoute.is_deleted.is_(False),
                or_(
                    ScheduledRoute.last_departure.is_(None),
                    ScheduledRoute.last_departure < ScheduledRoute.next_departure,
                ),
            )
            .order_by(ScheduledRoute.next_departure.asc())
            .limit(batch)
            .all()
        )

        result["considered"] = len(due_routes)
        result["candidates"] = [r.id for r in due_routes]

        for route in due_routes:
            if dry_run:
                continue

            claimed = (
                ScheduledRoute.query.filter(
                    ScheduledRoute.id == route.id,
                    or_(
                        ScheduledRoute.last_departure.is_(None),
                        ScheduledRoute.last_departure < ScheduledRoute.next_departure,
                    ),
                )
                .update(
                    {ScheduledRoute.last_departure: route.next_departure},
                    synchronize_session=False,
                )
            )
            db.session.commit()
            if claimed != 1:
                # Another worker claimed this departure between query and update.
                continue

            result["claimed"].append(route.id)

            dispatched = (
                Booking.query.filter(
                    Booking.assigned_route_id == route.id,
                    Booking.status.in_(CLAIMABLE_STATUSES),
                    Booking.assigned_driver_id.is_(None),
                    Booking.is_deleted.is_(False),
                )
                .order_by(Booking.id.asc())
                .all()
            )

            for booking in dispatched:
                outcome = MatchingService.discover_and_offer(booking.id)
                result["bookings_dispatched"].append(booking.id)
                result["offers_created"] += int(outcome.get("offers_created", 0))
                logger.info(
                    f"Scheduled route {route.id} due {route.next_departure.isoformat()} "
                    f"dispatched booking {booking.id}"
                )

        if result["claimed"]:
            logger.info(
                f"Transport scheduled-route execution claimed {len(result['claimed'])} "
                f"departure(s): {result['claimed']}, "
                f"dispatched {len(result['bookings_dispatched'])} booking(s)"
            )
    except Exception as e:
        logger.error(f"Transport scheduled-route execution failed: {e}", exc_info=True)
        result["error"] = str(e)
    finally:
        db.session.rollback()

    return result