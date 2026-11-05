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
from functools import wraps

from sqlalchemy import and_, or_

from app.celery_app import celery_app
from app.extensions import db
from app.transport.models import Booking, BookingStatus, ScheduledRoute

logger = logging.getLogger(__name__)

TRANSPORT_STALL_TIMEOUT_SECONDS = int(
    os.environ.get("TRANSPORT_STALL_TIMEOUT_SECONDS", "600")
)


def _with_app_context(fn):
    """Run *fn* inside a Flask app context.

    Same semantics as the established ``_with_app`` helper in
    app/notifications/events/tasks.py: reuse ``current_app`` when already
    inside one (tests, inline invocation), otherwise create the app
    defensively — these tasks execute under workers started without the
    ContextTask binding (``celery -A app.celery_app`` with no app passed to
    ``make_celery``), so DB access would otherwise raise
    "Working outside of application context". Decorator form (rather than
    the nested ``_run`` form) keeps the three task bodies untouched.
    """
    @wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            from flask import current_app
            if current_app:
                return fn(*args, **kwargs)
        except Exception:
            pass

        from app import create_app
        app = create_app()
        with app.app_context():
            return fn(*args, **kwargs)

    return wrapper


@celery_app.task(name="transport.dispatch_recovery", bind=True)
@_with_app_context
def dispatch_recovery(
    self,
    batch: int = None,
    after_booking_id: int = 0,
) -> dict:
    """Defensive sweep of expired/orphaned Redis offers PLUS rediscovery of
    CONFIRMED+unassigned bookings (pool -> ranker -> transient offer).

    Offer TTLs are the primary expiry mechanism; the sweep is a safety net for
    orphaned offer keys. Rediscovery re-advertises ranked candidates for
    bookings that never got an offer (offer loss, Redis outage restart,
    mid-flight crash before creation). Redis is never authoritative — the
    booking stays CONFIRMED/unassigned until a driver's claim commits.

    MATCH-01-owned: per booking, check-then-rediscover — expired matching
    windows close as NO_MATCH (no_supply / all_rejected) instead of being
    re-offered forever.

    Returns:
        dict: sweep results (checked / cleaned), rediscovery results
            (bookings considered / offers created) and no_match results
            (closed bookings with reasons).
    """
    result = {"checked": 0, "cleaned": 0}
    rediscovered = 0
    offers_created = 0
    # MATCH-01-owned safety net (review Condition 2): per booking,
    # check-then-rediscover. check_matching_outcome closes expired windows
    # (no_supply) and exhausted pools (all_rejected) idempotently; only
    # bookings still genuinely matching are re-offered. The rider page
    # render is the fast path; this beat catches riders who closed the tab.
    no_match_closed = []
    candidates = []
    batch_size = 10
    after_booking_id = max(0, int(after_booking_id))
    try:
        from flask import current_app

        from app.transport.services.matching_service import MatchingService

        configured_batch = (
            current_app.config.get("TRANSPORT_DISPATCH_RECOVERY_BATCH", 10)
            if batch is None else batch
        )
        batch_size = max(1, min(int(configured_batch), 25))
        window = int(current_app.config.get("TRANSPORT_MATCHING_WINDOW_SECONDS", 180))
        from app.transport.services.assignment_service import CLAIMABLE_STATUSES

        candidates = (
            Booking.query.filter(
                Booking.status.in_(CLAIMABLE_STATUSES),
                Booking.assigned_driver_id.is_(None),
                Booking.is_deleted.is_(False),
                Booking.id > after_booking_id,
            )
            .order_by(Booking.id.asc())
            .limit(batch_size)
            .all()
        )
        for booking in candidates:
            try:
                outcome = MatchingService.check_matching_outcome(booking.id)
            except Exception as e:
                logger.warning(
                    f"no_match sweep failed for booking {booking.id}: {e}")
                outcome = {}
            if outcome.get("terminal"):
                no_match_closed.append(
                    {"id": booking.id, "reason": outcome.get("reason")})
                continue
            offer_outcome = MatchingService.discover_and_offer(booking.id)
            rediscovered += 1
            offers_created += int(offer_outcome.get("offers_created", 0))

        result["rediscovered"] = rediscovered
        result["offers_created"] = offers_created
        result["no_match_closed"] = no_match_closed
        result["matching_window_seconds"] = window
        if no_match_closed:
            logger.info(
                f"Transport no_match sweep closed {len(no_match_closed)} "
                f"booking(s): {no_match_closed}")
    except Exception as e:
        logger.error(f"Transport dispatch recovery rediscovery failed: {e}", exc_info=True)
        result["rediscovery_error"] = str(e)
    finally:
        db.session.rollback()

    # Continue with the next keyset page as a separate task so the worker
    # returns to the broker between small slices. Failed items are still
    # passed over in this scan and are eligible again on the next Beat run.
    if candidates and len(candidates) >= batch_size:
        try:
            self.apply_async(
                kwargs={
                    "batch": batch_size,
                    "after_booking_id": candidates[-1].id,
                },
                countdown=5,
            )
            result["continuation_queued"] = True
        except Exception:
            logger.exception("Could not schedule next dispatch-recovery page")
            result["continuation_queued"] = False
    else:
        result["continuation_queued"] = False

    # Durable request-first offers have their own PostgreSQL lifecycle.
    # Expire unanswered attempts and resume requests that committed before
    # transient dispatch failure; this recovery path never creates a Booking.
    if after_booking_id == 0:
        try:
            from app.transport.services.ride_request_dispatch_service import (
                RideRequestDispatchService,
            )
            result["request_first_recovery"] = RideRequestDispatchService.recover_expired(
                batch=max(1, min(int(os.environ.get("TRANSPORT_REQUEST_RECOVERY_BATCH", "25")), 50))
            )
        except Exception:
            logger.error("Request-first dispatch recovery failed", exc_info=True)
            result["request_first_recovery"] = {"error": "recovery_failed"}

    if rediscovered:
        logger.info(
            f"Transport dispatch recovery rediscovered {rediscovered} booking(s), "
            f"created {offers_created} offer(s)"
        )
    return result


@celery_app.task(name="transport.stall_recovery", bind=True)
@_with_app_context
def stall_recovery(
    self,
    stall_seconds: int = None,
    dry_run: bool = False,
    batch: int = 25,
    after_booking_id: int = 0,
) -> dict:
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

        batch = max(1, min(int(batch), 50))
        after_booking_id = max(0, int(after_booking_id))
        candidates = (
            Booking.query.filter(
                Booking.status == BookingStatus.ASSIGNED.value,
                Booking.driver_en_route_at.is_(None),
                Booking.is_deleted.is_(False),
                Booking.driver_assigned_at < cutoff,
                Booking.id > after_booking_id,
            )
            .order_by(Booking.id.asc())
            .limit(batch)
            .all()
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
        continuation_queued = False
        if not dry_run and len(candidates) >= batch:
            try:
                self.apply_async(
                    kwargs={
                        "stall_seconds": timeout,
                        "dry_run": False,
                        "batch": batch,
                        "after_booking_id": candidates[-1].id,
                    },
                    countdown=5,
                )
                continuation_queued = True
            except Exception:
                logger.exception(
                    "Could not schedule the next stall-recovery batch; Beat will retry"
                )

        return {
            "candidates": [b.id for b in candidates],
            "recovered": recovered,
            "dry_run": dry_run,
            "timeout_seconds": timeout,
            "batch_size": batch,
            "continuation_queued": continuation_queued,
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


@celery_app.task(name="transport.scheduled_route_execution", bind=True)
@_with_app_context
def scheduled_route_execution(
    self,
    batch: int = None,
    dry_run: bool = False,
    route_id: int = None,
    departure_marker: str = None,
    after_booking_id: int = 0,
) -> dict:
    """Claim at most one due route and dispatch a bounded page of bookings.

    A continuation is tied to the exact claimed last_departure marker.
    This allows large routes to yield between pages without requiring a
    schema change or claiming the same departure twice. The regular Beat
    invocation starts a new route scan; a failed booking remains eligible
    for the normal dispatch-recovery sweep.
    """
    result = {
        "considered": 0,
        "candidates": [],
        "claimed": [],
        "route_id": route_id,
        "bookings_dispatched": [],
        "offers_created": 0,
        "batch_size": 10,
        "continuation_queued": False,
        "dry_run": dry_run,
    }
    try:
        from flask import current_app

        from app.transport.services.assignment_service import CLAIMABLE_STATUSES
        from app.transport.services.matching_service import MatchingService

        configured_batch = (
            current_app.config.get("TRANSPORT_SCHEDULED_ROUTE_BOOKING_BATCH", 10)
            if batch is None else batch
        )
        batch_size = max(1, min(int(configured_batch), 25))
        result["batch_size"] = batch_size
        after_booking_id = max(0, int(after_booking_id))
        now = datetime.now(timezone.utc)

        if route_id is None:
            due_route = (
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
                .order_by(ScheduledRoute.next_departure.asc(), ScheduledRoute.id.asc())
                .first()
            )
            if due_route is None:
                return result

            result["considered"] = 1
            result["candidates"] = [due_route.id]
            if dry_run:
                return result

            departure_at = due_route.next_departure
            claimed = (
                ScheduledRoute.query.filter(
                    ScheduledRoute.id == due_route.id,
                    ScheduledRoute.is_active.is_(True),
                    ScheduledRoute.is_cancelled.is_(False),
                    ScheduledRoute.is_deleted.is_(False),
                    or_(
                        ScheduledRoute.last_departure.is_(None),
                        ScheduledRoute.last_departure < ScheduledRoute.next_departure,
                    ),
                )
                .update(
                    {ScheduledRoute.last_departure: departure_at},
                    synchronize_session=False,
                )
            )
            db.session.commit()
            if claimed != 1:
                result["claim_skipped"] = True
                return result

            route_id = due_route.id
            departure_marker = departure_at.isoformat()
            after_booking_id = 0
            result["route_id"] = route_id
            result["claimed"] = [route_id]
        else:
            # Continue only the exact departure originally claimed. A
            # cancelled/deleted route or changed marker stops continuation.
            route = db.session.get(ScheduledRoute, int(route_id))
            if route is None or not (
                route.is_active and not route.is_cancelled and not route.is_deleted
            ):
                result["stopped"] = "route_unavailable"
                return result
            if not departure_marker:
                result["stopped"] = "missing_departure_marker"
                return result
            try:
                expected_departure = datetime.fromisoformat(departure_marker)
            except ValueError:
                result["stopped"] = "invalid_departure_marker"
                return result
            if route.last_departure is None or route.last_departure != expected_departure:
                result["stopped"] = "departure_marker_changed"
                return result

        # The route is claimed already. Read one booking page, then return
        # control to the broker before scheduling the next page.
        bookings = (
            Booking.query.filter(
                Booking.assigned_route_id == route_id,
                Booking.status.in_(CLAIMABLE_STATUSES),
                Booking.assigned_driver_id.is_(None),
                Booking.is_deleted.is_(False),
                Booking.id > after_booking_id,
            )
            .order_by(Booking.id.asc())
            .limit(batch_size)
            .all()
        )

        for booking in bookings:
            try:
                outcome = MatchingService.discover_and_offer(booking.id)
                result["bookings_dispatched"].append(booking.id)
                result["offers_created"] += int(outcome.get("offers_created", 0))
            except Exception:
                db.session.rollback()
                logger.exception(
                    "Scheduled route %s dispatch failed for booking %s",
                    route_id,
                    booking.id,
                )

        if len(bookings) >= batch_size:
            try:
                self.apply_async(
                    kwargs={
                        "batch": batch_size,
                        "dry_run": False,
                        "route_id": route_id,
                        "departure_marker": departure_marker,
                        "after_booking_id": bookings[-1].id,
                    },
                    countdown=5,
                )
                result["continuation_queued"] = True
            except Exception:
                logger.exception(
                    "Could not schedule next scheduled-route booking page for route %s",
                    route_id,
                )

        result["examined"] = len(bookings)
        result["after_booking_id"] = (
            bookings[-1].id if bookings else after_booking_id
        )
        logger.info(
            "Scheduled route %s departure %s examined %s bookings; dispatched %s; continuation=%s",
            route_id,
            departure_marker,
            len(bookings),
            len(result["bookings_dispatched"]),
            result["continuation_queued"],
        )
    except Exception as e:
        logger.error("Scheduled-route execution failed: %s", e, exc_info=True)
        result["error"] = str(e)
    finally:
        db.session.rollback()

    return result


@celery_app.task(name="transport.scheduled_booking_dispatch", bind=True)
@_with_app_context
def scheduled_booking_dispatch(
    self,
    batch: int = None,
    dry_run: bool = False,
    after_booking_id: int = 0,
) -> dict:
    """Release a bounded page of due SCHEDULED bookings into matching.

    Uses a stable Booking.id cursor so each continuation handles a small page.
    The next regular Beat run starts again at ID zero and catches bookings
    created after an earlier continuation passed their ID.
    """
    result = {
        "considered": 0,
        "confirmed": [],
        "dispatched": [],
        "offers_created": 0,
        "skipped": {},
        "dry_run": dry_run,
        "continuation_queued": False,
    }
    due_bookings = []
    try:
        from flask import current_app

        from app.transport.services.booking_service import get_booking_service
        from app.transport.services.matching_service import MatchingService

        configured_batch = (
            current_app.config.get("TRANSPORT_SCHEDULED_DISPATCH_BATCH", 25)
            if batch is None else batch
        )
        batch = max(1, min(int(configured_batch), 50))
        after_booking_id = max(0, int(after_booking_id))

        now = datetime.now(timezone.utc)
        horizon = now + timedelta(
            minutes=MatchingService._scheduled_dispatch_lead_minutes()
        )

        scheduled_mode = or_(
            Booking.pickup_mode == "scheduled",
            and_(
                Booking.pickup_mode.is_(None),
                Booking.booking_metadata["booking_mode"].astext == "scheduled",
            ),
        )
        due_bookings = (
            Booking.query.filter(
                Booking.status.in_(
                    (
                        BookingStatus.CONFIRMED.value,
                        BookingStatus.PENDING_PAYMENT.value,
                    )
                ),
                Booking.assigned_driver_id.is_(None),
                Booking.assigned_vehicle_id.is_(None),
                Booking.is_deleted.is_(False),
                Booking.pickup_time.is_not(None),
                Booking.pickup_time <= horizon,
                scheduled_mode,
                Booking.id > after_booking_id,
            )
            .order_by(Booking.id.asc())
            .limit(batch)
            .all()
        )

        for booking in due_bookings:
            result["considered"] += 1
            if dry_run:
                result["dispatched"].append(booking.id)
                continue
            try:
                if booking.status == BookingStatus.PENDING_PAYMENT.value:
                    payment_method = str(
                        getattr(booking, "payment_method", "") or ""
                    ).strip().lower()
                    if payment_method != "cash":
                        result["skipped"][booking.id] = "awaiting_payment"
                        continue
                    get_booking_service().transition_status(
                        booking.id,
                        BookingStatus.CONFIRMED,
                        reason="scheduled_release",
                        initiated_by="system",
                    )
                    result["confirmed"].append(booking.id)

                not_due = MatchingService.scheduled_not_due_reason(booking)
                if not_due:
                    result["skipped"][booking.id] = not_due
                    continue

                outcome = MatchingService.discover_and_offer(booking.id)
                result["dispatched"].append(booking.id)
                result["offers_created"] += int(outcome.get("offers_created", 0))
            except Exception as e:
                db.session.rollback()
                logger.warning(
                    "Scheduled release failed for booking %s: %s",
                    booking.id,
                    e,
                )
                result["skipped"][booking.id] = "error"

        continuation_queued = False
        if not dry_run and len(due_bookings) >= batch:
            try:
                self.apply_async(
                    kwargs={
                        "batch": batch,
                        "dry_run": False,
                        "after_booking_id": due_bookings[-1].id,
                    },
                    countdown=5,
                )
                continuation_queued = True
            except Exception:
                logger.exception(
                    "Could not schedule the next scheduled-booking dispatch page"
                )
        result["continuation_queued"] = continuation_queued
    except Exception as e:
        logger.error(
            "Scheduled-booking dispatch failed: %s",
            e,
            exc_info=True,
        )
        result["error"] = str(e)
    finally:
        db.session.rollback()

    return result
