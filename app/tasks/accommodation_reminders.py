"""
app/tasks/accommodation_reminders.py

Scheduled reminder tasks for the accommodation module:
- Guest registration reminders (72h, 48h, 24h before check-in)
- Registration deadline enforcement (block check-in if incomplete)
- Approval deadline warnings
- Pre-check-in reminders
- Property completeness notifications (NEW)
"""

import logging

from celery import shared_task
from datetime import datetime, timezone, timedelta
from app.extensions import db
from app.accommodation.models.booking import AccommodationBooking, AccommodationBookingStatus
from app.accommodation.models.guest_registration import GuestRegistration
from app.accommodation.models.availability import RoomHold
from app.accommodation.models.property import Property
from app.models.system_config import SystemConfig
from app.accommodation.state_machine.booking_states import BookingStateMachine
from app.accommodation.services.readiness_service import AccommodationReadinessService
from app.notifications.models import NotificationModule, NotificationType


logger = logging.getLogger(__name__)


@shared_task(name="accommodation.send_registration_reminders", bind=True)
def send_registration_reminders(
    self,
    batch_size: int = 5,
    after_72h_id: int = 0,
    after_48h_id: int = 0,
    after_24h_id: int = 0,
    after_post_booking_id: int = 0,
):
    """
    Send bounded pages of incomplete-guest-registration reminders.

    Each reminder class has its own keyset cursor because the time windows
    overlap. A stable reminder key prevents hourly Beat runs and continuation
    pages from sending the same reminder twice for the same booking/check-in.
    """
    now = datetime.now(timezone.utc)
    batch_size = max(1, min(int(batch_size), 25))
    cursors = {
        "72h": max(0, int(after_72h_id)),
        "48h": max(0, int(after_48h_id)),
        "24h": max(0, int(after_24h_id)),
        "post_booking_24h": max(0, int(after_post_booking_id)),
    }

    status_filter = [
        AccommodationBookingStatus.CONFIRMED.value,
        AccommodationBookingStatus.PENDING_APPROVAL.value,
    ]
    cutoff_72h = now + timedelta(hours=72)
    cutoff_48h = now + timedelta(hours=48)
    cutoff_24h = now + timedelta(hours=24)
    reminder_cutoff = now - timedelta(hours=24)

    pages = {
        "72h": (
            AccommodationBooking.query.filter(
                AccommodationBooking.check_in <= cutoff_72h,
                AccommodationBooking.check_in > now,
                AccommodationBooking.status.in_(status_filter),
                AccommodationBooking.id > cursors["72h"],
            )
            .order_by(AccommodationBooking.id.asc())
            .limit(batch_size)
            .all()
        ),
        "48h": (
            AccommodationBooking.query.filter(
                AccommodationBooking.check_in <= cutoff_48h,
                AccommodationBooking.check_in > now,
                AccommodationBooking.status.in_(status_filter),
                AccommodationBooking.id > cursors["48h"],
            )
            .order_by(AccommodationBooking.id.asc())
            .limit(batch_size)
            .all()
        ),
        "24h": (
            AccommodationBooking.query.filter(
                AccommodationBooking.check_in <= cutoff_24h,
                AccommodationBooking.check_in > now,
                AccommodationBooking.status.in_(status_filter),
                AccommodationBooking.id > cursors["24h"],
            )
            .order_by(AccommodationBooking.id.asc())
            .limit(batch_size)
            .all()
        ),
        "post_booking_24h": (
            AccommodationBooking.query.filter(
                AccommodationBooking.created_at <= reminder_cutoff,
                AccommodationBooking.status.in_(status_filter),
                AccommodationBooking.id > cursors["post_booking_24h"],
            )
            .order_by(AccommodationBooking.id.asc())
            .limit(batch_size)
            .all()
        ),
    }

    templates = {
        "72h": (
            "Complete guest registration soon",
            lambda b: (
                f"Guest registration for booking {b.booking_reference} is still incomplete. "
                f"Check-in is on {b.check_in.isoformat()}. Please register all guests within 72 hours."
            ),
        ),
        "48h": (
            "Guest registration required before check-in",
            lambda b: (
                f"Guest registration for booking {b.booking_reference} is still incomplete. "
                f"Check-in is on {b.check_in.isoformat()}. Host may deny check-in without completed registration."
            ),
        ),
        "24h": (
            "URGENT: Guest registration deadline approaching",
            lambda b: (
                f"Guest registration for booking {b.booking_reference} is still incomplete. "
                f"Check-in is tomorrow ({b.check_in.isoformat()}). Incomplete registration will block check-in."
            ),
        ),
        "post_booking_24h": (
            "Complete your guest registration",
            lambda b: (
                f"Please complete guest registration for booking {b.booking_reference}. "
                f"Check-in is on {b.check_in.isoformat()}."
            ),
        ),
    }

    sent = {key: 0 for key in pages}
    examined = {key: len(rows) for key, rows in pages.items()}
    next_cursors = dict(cursors)

    for reminder_key, bookings in pages.items():
        title, message_for = templates[reminder_key]
        for booking in bookings:
            if _is_fully_registered(booking.id):
                continue
            check_in_marker = (
                booking.check_in.isoformat()
                if hasattr(booking.check_in, "isoformat")
                else str(booking.check_in)
            )
            dedupe_key = (
                f"accommodation_guest_registration:{reminder_key}:"
                f"{booking.id}:{check_in_marker}"
            )
            _send_notification(
                booking,
                NotificationType.BOOKING_UPDATE,
                title,
                message_for(booking),
                dedupe_key=dedupe_key,
            )
            sent[reminder_key] += 1

        if bookings:
            # Advance even when this category has fewer than one full page;
            # another category may be the one requiring continuation.
            next_cursors[reminder_key] = bookings[-1].id

    continuation_queued = any(
        len(pages[key]) >= batch_size for key in pages
    )
    if continuation_queued:
        try:
            self.apply_async(
                kwargs={
                    "batch_size": batch_size,
                    "after_72h_id": next_cursors["72h"],
                    "after_48h_id": next_cursors["48h"],
                    "after_24h_id": next_cursors["24h"],
                    "after_post_booking_id": next_cursors["post_booking_24h"],
                },
                countdown=5,
            )
        except Exception:
            logger.exception("Could not schedule next accommodation registration-reminder page")
            continuation_queued = False

    return {
        "sent": sent,
        "examined": examined,
        "batch_size": batch_size,
        "continuation_queued": continuation_queued,
    }

@shared_task(name="accommodation.send_pre_arrival_request_reminder", bind=True)
def send_pre_arrival_request_reminder(
    self,
    batch_size: int = 25,
    after_booking_id: int = 0,
):
    """
    Pre-arrival special-request nudge (Addendum 1 §2).

    Runs daily. For CONFIRMED bookings exactly 3 days from check-in with no
    special request on record yet, sends one reminder so the guest can flag
    anything the host should prepare for (late arrival, accessibility, etc.).

    Idempotent: a booking only ever matches the exact check-in boundary once,
    and an already-existing reminder notification for that booking suppresses
    a re-send if the task is re-run within the day.
    """
    from app.notifications.models import (
        Notification,
        NotificationModule,
        NotificationType,
    )
    from app.notifications.services import NotificationService
    from app.accommodation.services.special_request_service import SpecialRequestService

    now = datetime.now(timezone.utc)
    target_date = now.date() + timedelta(days=3)

    batch_size = max(1, min(int(batch_size), 50))
    after_booking_id = max(0, int(after_booking_id))
    candidates = (
        AccommodationBooking.query.filter(
            AccommodationBooking.check_in == target_date,
            AccommodationBooking.status == AccommodationBookingStatus.CONFIRMED.value,
            AccommodationBooking.id > after_booking_id,
        )
        .order_by(AccommodationBooking.id.asc())
        .limit(batch_size)
        .all()
    )

    sent = 0
    for booking in candidates:
        try:
            if SpecialRequestService.get_for_booking(booking.id):
                continue
            recipient_id = booking.primary_guest_id or booking.booked_by_user_id
            if not recipient_id:
                continue

            existing = Notification.query.filter_by(
                user_id=recipient_id,
                type=NotificationType.BOOKING_UPDATE.value,
                module=NotificationModule.ACCOMMODATION.value,
            ).filter(
                Notification.context["booking_reference"].astext
                == booking.booking_reference
            ).first()
            if existing:
                continue

            link = None
            try:
                from flask import url_for

                link = url_for(
                    "accommodation.guest_add_request",
                    booking_id=booking.id,
                    _external=True,
                )
            except Exception:
                link = None

            NotificationService.send(
                user_id=recipient_id,
                notification_type=NotificationType.BOOKING_UPDATE,
                module=NotificationModule.ACCOMMODATION,
                title="A few days until your stay \u2014 anything we should know?",
                message=(
                    f"Your booking {booking.booking_reference} checks in on "
                    f"{booking.check_in.isoformat()}. If you have a special "
                    "request (late arrival, accessibility, extra bedding), let "
                    "your host know now so they can prepare."
                ),
                data={
                    "booking_reference": booking.booking_reference,
                    "booking_id": booking.id,
                },
                channels=["in_app", "email"],
                link=link,
            )
            sent += 1
        except Exception as e:
            db.session.rollback()
            print(f"Pre-arrival request reminder failed for booking {booking.id}: {e}")

    continuation_queued = False
    if len(candidates) >= batch_size:
        try:
            self.apply_async(
                kwargs={
                    "batch_size": batch_size,
                    "after_booking_id": candidates[-1].id,
                },
                countdown=5,
            )
            continuation_queued = True
        except Exception:
            logger.exception("Could not schedule next pre-arrival reminder batch")

    return {
        "sent": sent,
        "batch_size": batch_size,
        "continuation_queued": continuation_queued,
    }


@shared_task(name="accommodation.enforce_registration_deadlines")
def enforce_registration_deadlines():
    """
    Check if any bookings have passed their registration deadline
    with incomplete manifests. Log warnings for hosts.
    """
    now = datetime.now(timezone.utc)

    overdue_bookings = AccommodationBooking.query.filter(
        AccommodationBooking.registration_deadline != None,
        AccommodationBooking.registration_deadline <= now,
        AccommodationBooking.status.in_([
            AccommodationBookingStatus.CONFIRMED.value,
            AccommodationBookingStatus.PENDING_APPROVAL.value,
        ]),
    ).all()

    for booking in overdue_bookings:
        if not _is_fully_registered(booking.id):
            _send_notification(
                booking,
                NotificationType.BOOKING_UPDATE,
                "Registration deadline has passed",
                f"Guest registration for booking {booking.booking_reference} is incomplete "
                f"and the deadline ({booking.registration_deadline.isoformat()}) has passed. "
                f"Check-in may be blocked until registration is complete.",
            )


@shared_task(name="accommodation.expire_unapproved_bookings", bind=True)
def expire_unapproved_bookings(
    self,
    batch_size: int = 25,
    after_booking_id: int = 0,
):
    """
    Cancel bookings where the host didn't approve within the approval deadline.
    Also releases associated holds and inventory blocks.
    """
    now = datetime.now(timezone.utc)

    batch_size = max(1, min(int(batch_size), 50))
    after_booking_id = max(0, int(after_booking_id))
    expired_bookings = (
        AccommodationBooking.query.filter(
            AccommodationBooking.status == AccommodationBookingStatus.PENDING_APPROVAL.value,
            AccommodationBooking.approval_deadline != None,
            AccommodationBooking.approval_deadline <= now,
            AccommodationBooking.id > after_booking_id,
        )
        .order_by(AccommodationBooking.id.asc())
        .limit(batch_size)
        .all()
    )

    expired_count = 0
    for booking in expired_bookings:
        try:
            # Release holds
            holds = RoomHold.query.filter(
                RoomHold.property_id == booking.property_id,
                RoomHold.check_in == booking.check_in,
                RoomHold.check_out == booking.check_out,
                RoomHold.status == "active",
            ).all()
            for hold in holds:
                hold.mark_expired()

            # Release inventory blocks
            if booking.room_type_id:
                from app.accommodation.services.availability_service import AvailabilityService
                AvailabilityService.release_room_type_blocks(
                    room_type_id=booking.room_type_id,
                    check_in=booking.check_in,
                    check_out=booking.check_out,
                    booking_id=booking.id,
                )
            else:
                from app.accommodation.services.availability_service import AvailabilityService
                AvailabilityService.release_hold(
                    property_id=booking.property_id,
                    check_in=booking.check_in,
                    check_out=booking.check_out,
                )

            booking.status = AccommodationBookingStatus.EXPIRED.value
            booking.cancelled_at = now
            booking.cancellation_reason = "Host approval expired"
            db.session.commit()
            expired_count += 1

            _send_notification(
                booking,
                "booking_expired",
                "Booking expired",
                f"Booking {booking.booking_reference} has expired because the host did not approve it in time.",
            )

        except Exception as e:
            db.session.rollback()
            print(f"Failed to expire booking {booking.id}: {e}")

    continuation_queued = False
    if len(expired_bookings) >= batch_size:
        try:
            self.apply_async(
                kwargs={
                    "batch_size": batch_size,
                    "after_booking_id": expired_bookings[-1].id,
                },
                countdown=5,
            )
            continuation_queued = True
        except Exception:
            logger.exception("Could not schedule next unapproved-booking expiry batch")

    return {
        "expired": expired_count,
        "examined": len(expired_bookings),
        "batch_size": batch_size,
        "continuation_queued": continuation_queued,
    }


@shared_task(name="accommodation.detect_no_shows", bind=True)
def detect_no_shows(
    self,
    batch_size: int = 25,
    after_booking_id: int = 0,
):
    """
    Auto-detect no-shows: a CONFIRMED booking whose check-in date has passed
    by more than the configured grace window and that was never checked in.

    This closes the gap where confirmed bookings are never moved to NO_SHOW,
    leaving stale bookings able to prompt guests for actions (e.g. special
    requests) and blocking inventory reporting.

    Idempotent: bookings already in a terminal state are excluded by the query,
    and the state machine refuses invalid transitions.
    """
    now = datetime.now(timezone.utc)
    grace_hours = int(SystemConfig.get("accommodation_no_show_grace_hours", 24))
    cutoff_date = (now - timedelta(hours=grace_hours)).date()

    batch_size = max(1, min(int(batch_size), 50))
    after_booking_id = max(0, int(after_booking_id))
    candidates = (
        AccommodationBooking.query.filter(
            AccommodationBooking.status == AccommodationBookingStatus.CONFIRMED.value,
            AccommodationBooking.check_in < cutoff_date,
            AccommodationBooking.is_checked_in == False,  # noqa: E712
            AccommodationBooking.id > after_booking_id,
        )
        .order_by(AccommodationBooking.id.asc())
        .limit(batch_size)
        .all()
    )

    processed = 0
    for booking in candidates:
        try:
            BookingStateMachine.transition(
                booking,
                AccommodationBookingStatus.NO_SHOW,
                changed_by_user_id=None,
                reason="Auto no-show detection (check-in window lapsed)",
                trigger="system_no_show",
                ip_address="system",
                user_agent="system",
            )
            booking.cancelled_at = now
            booking.cancellation_reason = "No-show (auto-detected)"
            db.session.commit()
            processed += 1

            _send_notification(
                booking,
                "booking_no_show",
                "Booking marked as no-show",
                f"Booking {booking.booking_reference} was marked as a no-show because check-in was not completed in time.",
            )
        except Exception as e:
            db.session.rollback()
            print(f"Failed to mark no-show for booking {booking.id}: {e}")

    continuation_queued = False
    if len(candidates) >= batch_size:
        try:
            self.apply_async(
                kwargs={
                    "batch_size": batch_size,
                    "after_booking_id": candidates[-1].id,
                },
                countdown=5,
            )
            continuation_queued = True
        except Exception:
            logger.exception("Could not schedule next no-show detection batch")

    return {
        "processed": processed,
        "examined": len(candidates),
        "batch_size": batch_size,
        "continuation_queued": continuation_queued,
    }


def _is_fully_registered(booking_id: int) -> bool:
    """Check registration completeness without loading every guest row."""
    try:
        registrations = GuestRegistration.query.filter_by(
            booking_id=booking_id
        )
        if not registrations.first():
            return False
        incomplete = registrations.filter(
            ~GuestRegistration.status.in_(("completed", "skipped"))
        ).first()
        return incomplete is None
    except Exception:
        return False


def _send_notification(
    booking,
    notification_type,
    title: str,
    message: str,
    dedupe_key: str = None,
):
    """Best-effort notification sender with optional durable deduplication."""
    try:
        from app.notifications.models import Notification
        from app.notifications.services import NotificationService

        # Determine recipient: Owner if claimed, otherwise booker.
        recipient_id = booking.booking_owner_id or booking.booked_by_user_id
        if not recipient_id:
            return

        context = {"booking_reference": booking.booking_reference}
        if dedupe_key:
            existing = Notification.query.filter_by(
                user_id=recipient_id,
                type=getattr(notification_type, "value", notification_type),
                module=NotificationModule.ACCOMMODATION.value,
            ).filter(
                Notification.context["reminder_key"].astext == dedupe_key
            ).first()
            if existing:
                return
            context["reminder_key"] = dedupe_key

        NotificationService.send(
            user_id=recipient_id,
            notification_type=notification_type,
            module=NotificationModule.ACCOMMODATION,
            title=title,
            message=message,
            channels=["in_app", "email"],
            data=context,
        )
    except Exception as e:
        print(f"Notification failed for booking {booking.booking_reference}: {e}")


@shared_task(name="accommodation.notify_incomplete_properties")
def notify_incomplete_properties():
    """
    Notify hosts about incomplete properties that cannot be published/booked.
    
    Runs daily to check for properties in draft/pending_review status
    that are missing required fields (room types, photos, etc.).
    Sends a notification to the host with a list of what's missing.
    """
    # Only notify about properties that are not yet published/active
    incomplete_properties = Property.query.filter(
        Property.status.in_(["draft", "submitted", "pending_review", "needs_information"]),
        Property.is_deleted == False,
    ).all()

    notified_count = 0
    for prop in incomplete_properties:
        # Check if we've already notified recently (avoid spam)
        # You could add a last_notified_at column to Property for this
        
        readiness = AccommodationReadinessService.get_completeness_score(prop)
        
        # Only notify if score is below 80% (significant missing items)
        if readiness["score"] < 80 and readiness["missing"]:
            _send_property_notification(
                prop,
                "property_incomplete",
                f"Your listing '{prop.title}' needs attention",
                f"Your property is {readiness['score']}% complete. "
                f"Missing: {', '.join(readiness['missing'][:3])}"
                f"{'...' if len(readiness['missing']) > 3 else ''}. "
                f"Complete these to publish and start earning.",
            )
            notified_count += 1

    return f"Notified {notified_count} hosts about incomplete properties"


def _send_property_notification(property_obj: Property, notification_type: str, title: str, message: str):
    """Send notification to property owner/host."""
    try:
        from app.notifications.services import NotificationService
        # Notify owner_user_id or owner_org_id
        recipient_id = property_obj.owner_user_id
        if not recipient_id and property_obj.owner_org_id:
            # For org-owned, find org admins (simplified - just use first member)
            from app.identity.models.organisation import Organisation
            org = Organisation.query.filter_by(id=property_obj.owner_org_id).first()
            if org:
                # For now, just use a placeholder - you'd want to notify all org admins
                recipient_id = org.owner_user_id if hasattr(org, 'owner_user_id') else None
        
        if recipient_id:
            NotificationService.send(
                user_id=recipient_id,
                notification_type=notification_type,
                title=title,
                message=message,
                channels=["in_app", "email"],
                data={"property_id": property_obj.id, "property_title": property_obj.title},
            )
    except Exception as e:
        print(f"Property notification failed for property {property_obj.id}: {e}")
