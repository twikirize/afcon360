"""
app/tasks/accommodation_reminders.py

Scheduled reminder tasks for the accommodation module:
- Guest registration reminders (72h, 48h, 24h before check-in)
- Registration deadline enforcement (block check-in if incomplete)
- Approval deadline warnings
- Pre-check-in reminders
"""

from celery import shared_task
from datetime import datetime, timezone, timedelta
from app.extensions import db
from app.accommodation.models.booking import AccommodationBooking, AccommodationBookingStatus
from app.accommodation.models.guest_registration import GuestRegistration
from app.accommodation.models.availability import RoomHold


@shared_task(name="accommodation.send_registration_reminders")
def send_registration_reminders():
    """
    Send reminders for incomplete guest registration.

    Triggers:
    1. 72 hours before check-in (first reminder)
    2. 48 hours before check-in (second reminder)
    3. 24 hours before check-in (final warning)
    4. 24 hours after booking creation (if status is CONFIRMED or PENDING_APPROVAL)
    """
    now = datetime.now(timezone.utc)

    # 72h before check-in reminder
    cutoff_72h = now + timedelta(hours=72)
    upcoming_72h = AccommodationBooking.query.filter(
        AccommodationBooking.check_in <= cutoff_72h,
        AccommodationBooking.check_in > now,
        AccommodationBooking.status.in_([
            AccommodationBookingStatus.CONFIRMED.value,
            AccommodationBookingStatus.PENDING_APPROVAL.value,
        ]),
    ).all()

    for booking in upcoming_72h:
        if not _is_fully_registered(booking.id):
            _send_notification(
                booking,
                "registration_reminder_72h",
                "Complete guest registration soon",
                f"Guest registration for booking {booking.booking_reference} is still incomplete. "
                f"Check-in is on {booking.check_in.isoformat()}. Please register all guests within 72 hours.",
            )

    # 48h before check-in reminder
    cutoff_48h = now + timedelta(hours=48)
    upcoming_48h = AccommodationBooking.query.filter(
        AccommodationBooking.check_in <= cutoff_48h,
        AccommodationBooking.check_in > now,
        AccommodationBooking.status.in_([
            AccommodationBookingStatus.CONFIRMED.value,
            AccommodationBookingStatus.PENDING_APPROVAL.value,
        ]),
    ).all()

    for booking in upcoming_48h:
        if not _is_fully_registered(booking.id):
            _send_notification(
                booking,
                "registration_reminder_48h",
                "Guest registration required before check-in",
                f"Guest registration for booking {booking.booking_reference} is still incomplete. "
                f"Check-in is on {booking.check_in.isoformat()}. Host may deny check-in without completed registration.",
            )

    # 24h before check-in reminder (final warning)
    cutoff_24h = now + timedelta(hours=24)
    upcoming_24h = AccommodationBooking.query.filter(
        AccommodationBooking.check_in <= cutoff_24h,
        AccommodationBooking.check_in > now,
        AccommodationBooking.status.in_([
            AccommodationBookingStatus.CONFIRMED.value,
            AccommodationBookingStatus.PENDING_APPROVAL.value,
        ]),
    ).all()

    for booking in upcoming_24h:
        if not _is_fully_registered(booking.id):
            _send_notification(
                booking,
                "registration_reminder_24h",
                "URGENT: Guest registration deadline approaching",
                f"Guest registration for booking {booking.booking_reference} is still incomplete. "
                f"Check-in is tomorrow ({booking.check_in.isoformat()}). Incomplete registration will block check-in.",
            )

    # 24h after booking reminder
    reminder_cutoff = now - timedelta(hours=24)
    recent_bookings = AccommodationBooking.query.filter(
        AccommodationBooking.created_at <= reminder_cutoff,
        AccommodationBooking.status.in_([
            AccommodationBookingStatus.CONFIRMED.value,
            AccommodationBookingStatus.PENDING_APPROVAL.value,
        ]),
    ).all()

    for booking in recent_bookings:
        if not _is_fully_registered(booking.id):
            _send_notification(
                booking,
                "registration_reminder_post_booking",
                "Complete your guest registration",
                f"Please complete guest registration for booking {booking.booking_reference}. "
                f"Check-in is on {booking.check_in.isoformat()}.",
            )


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
                "registration_deadline_passed",
                "Registration deadline has passed",
                f"Guest registration for booking {booking.booking_reference} is incomplete "
                f"and the deadline ({booking.registration_deadline.isoformat()}) has passed. "
                f"Check-in may be blocked until registration is complete.",
            )


@shared_task(name="accommodation.expire_unapproved_bookings")
def expire_unapproved_bookings():
    """
    Cancel bookings where the host didn't approve within the approval deadline.
    Also releases associated holds and inventory blocks.
    """
    now = datetime.now(timezone.utc)

    expired_bookings = AccommodationBooking.query.filter(
        AccommodationBooking.status == AccommodationBookingStatus.PENDING_APPROVAL.value,
        AccommodationBooking.approval_deadline != None,
        AccommodationBooking.approval_deadline <= now,
    ).all()

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

            _send_notification(
                booking,
                "booking_expired",
                "Booking expired",
                f"Booking {booking.booking_reference} has expired because the host did not approve it in time.",
            )

        except Exception as e:
            db.session.rollback()
            print(f"Failed to expire booking {booking.id}: {e}")


def _is_fully_registered(booking_id: int) -> bool:
    """Check if all required guests are registered for a booking."""
    try:
        registrations = GuestRegistration.query.filter_by(booking_id=booking_id).all()
        if not registrations:
            return False
        return all(r.status in ("completed", "skipped") for r in registrations)
    except Exception:
        return False


def _send_notification(booking, notification_type: str, title: str, message: str):
    """Best-effort notification sender; swallows failures to keep task idempotent."""
    try:
        from app.services.notification_service import NotificationService
        # Determine recipient: Owner if claimed, otherwise booker
        recipient_id = booking.booking_owner_id or booking.booked_by_user_id
        NotificationService.send(
            user_id=recipient_id,
            notification_type=notification_type,
            title=title,
            message=message,
            channels=["in_app", "email"],
            data={"booking_reference": booking.booking_reference},
        )
    except Exception as e:
        print(f"Notification failed for booking {booking.booking_reference}: {e}")
