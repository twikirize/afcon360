# app/events/tasks.py
"""
Celery background tasks for the Events module.

These tasks must not create financial truth or mutate payment state.
Payment state is owned by EventPaymentService / wallet.

This file handles:
  - asynchronous QR generation and confirmation email
  - reaping expired pending registrations
  - releasing capacity back to the ticket pool
  - converting waitlisted attendees when capacity becomes available
"""

import json
import logging
import os
from datetime import datetime, timezone, timedelta

from celery import Celery
from flask import current_app, has_app_context

from app.extensions import db
from app.events.services import EventService
from app.events.models import EventRegistration, Event, TicketType, Waitlist
from app.events.constants import BookingType

logger = logging.getLogger(__name__)

# Celery broker/backend URL
redis_url = os.getenv('REDIS_URL') or os.getenv('CELERY_BROKER_URL')
if not redis_url:
    flask_env = os.getenv("FLASK_ENV", "production")
    if flask_env == "production":
        raise RuntimeError(
            "REDIS_URL must be set in production for Celery. "
            "Set REDIS_URL or CELERY_BROKER_URL environment variable."
        )
    else:
        redis_url = 'redis://localhost:6379/0'
        print(
            "WARNING: Using development Redis URL for Celery - configure "
            "REDIS_URL environment variable for production"
        )

celery_app = Celery('event_tasks', broker=redis_url, backend=redis_url)


def create_flask_app():
    from app import create_app
    return create_app()


def _flask_app():
    """Return the current Flask app or create one."""
    if has_app_context():
        return current_app._get_current_object()
    return create_flask_app()


@celery_app.task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    soft_time_limit=300,
    time_limit=330,
    acks_late=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=600,
    retry_jitter=True
)
def process_event_registration(self, registration_id: int, event_slug: str, task_idempotency_key: str = None):
    """
    Background task to generate QR code and send confirmation email.

    This task is idempotent and should not modify payment state.
    """
    try:
        from app.extensions import redis_client
        if task_idempotency_key and redis_client and hasattr(redis_client, 'get'):
            cache_key = f"task_idempotency:{task_idempotency_key}"
            if redis_client.get(cache_key):
                logger.info(f"Task already processed: {task_idempotency_key}")
                return {"status": "skipped", "reason": "already_processed"}
            redis_client.setex(cache_key, 3600, "1")
    except ImportError:
        logger.warning("redis_client not available, skipping idempotency check")
    except Exception as e:
        logger.warning(f"Error checking idempotency: {e}")

    app = _flask_app()
    with app.app_context():
        try:
            registration = EventRegistration.query.with_for_update(
                of=EventRegistration, nowait=True
            ).get(registration_id)

            event = Event.query.filter_by(slug=event_slug).first()

            if not registration or not event:
                logger.error(
                    f"Task failed: Registration {registration_id} or Event {event_slug} not found."
                )
                return {"status": "failed", "reason": "not_found"}

            # Only process registrations that are already confirmed/free.
            # Do not confirm pending-payment registrations here.
            if (
                registration.status == EventRegistration.STATUS_CONFIRMED
                and registration.payment_status in (
                    EventRegistration.PAYMENT_PAID,
                    EventRegistration.PAYMENT_FREE,
                )
            ):
                logger.info(f"Registration {registration_id} already processed")
                return {"status": "skipped", "reason": "already_processed"}

            if (
                registration.status == EventRegistration.STATUS_PENDING_PAYMENT
                or registration.payment_status == EventRegistration.PAYMENT_PENDING
            ):
                logger.info(
                    f"Registration {registration_id} is pending payment; skipping QR/email."
                )
                return {"status": "skipped", "reason": "pending_payment"}

            try:
                # 1. Generate QR Code
                qr_code_base64 = EventService._generate_qr_code(
                    registration.qr_token,
                    registration.registration_ref,
                )

                if not registration.notes:
                    registration.notes = ""
                registration.notes += (
                    f"\nQR generated at: {datetime.now(timezone.utc).isoformat()}"
                )

                # 2. Send confirmation email.
                logger.info(
                    f"Sending confirmation email for registration "
                    f"{registration.registration_ref} to {registration.email}"
                )
                try:
                    from app.notifications.models import (
                        Notification as _Notification,
                        NotificationType,
                        NotificationChannel,
                        NotificationModule,
                        NotificationStatus,
                    )
                    from app.notifications.channel_handlers.email import EmailHandler

                    organizer = event.organizer

                    EmailHandler().deliver(
                        _Notification(
                            email=registration.email,
                            type=NotificationType.EVENT_REGISTERED,
                            channel=NotificationChannel.EMAIL,
                            module=NotificationModule.EVENTS,
                            status=NotificationStatus.PENDING,
                            subject=f'Registration Confirmed - {event.name}',
                            body=(
                                f'<h2>Registration Confirmed</h2>'
                                f'<p>Dear {registration.full_name},</p>'
                                f'<p>Your registration for <strong>{event.name}</strong> is confirmed.</p>'
                                f'<p>Registration Ref: <strong>{registration.registration_ref}</strong></p>'
                                f'<p>Ticket: {registration.ticket_type}</p>'
                                f'<p>Date: {event.start_date}</p>'
                                f'<p>Venue: {event.venue}, {event.city}</p>'
                            ),
                            priority='high',
                        ),
                        {'email': registration.email, 'user_id': None},
                    )

                    if organizer and organizer.email:
                        EmailHandler().deliver(
                            _Notification(
                                email=organizer.email,
                                type=NotificationType.EVENT_REGISTERED,
                                channel=NotificationChannel.EMAIL,
                                module=NotificationModule.EVENTS,
                                status=NotificationStatus.PENDING,
                                subject=f'New Registration - {event.name}',
                                body=(
                                    f'<h2>New Registration</h2>'
                                    f'<p>A new attendee has registered for '
                                    f'<strong>{event.name}</strong>.</p>'
                                    f'<p>Name: {registration.full_name}</p>'
                                    f'<p>Email: {registration.email}</p>'
                                    f'<p>Ticket: {registration.ticket_type}</p>'
                                    f'<p>Ref: {registration.registration_ref}</p>'
                                ),
                                priority='normal',
                            ),
                            {'email': organizer.email, 'user_id': None},
                        )

                except Exception as mail_error:
                    logger.warning(f'Email sending failed: {mail_error}')

                registration.status = EventRegistration.STATUS_CONFIRMED
                db.session.add(registration)
                db.session.commit()

                logger.info(
                    f"Successfully processed background task for "
                    f"registration {registration.registration_ref}"
                )

            except Exception as e:
                logger.error(
                    f"Error in background task for registration "
                    f"{registration.registration_ref}: {e}"
                )
                db.session.rollback()
                raise self.retry(exc=e, countdown=60 * (2 ** self.request.retries))

        except Exception as e:
            logger.error(f"Task setup error: {e}")
            if self.request.retries < self.max_retries:
                raise self.retry(exc=e, countdown=60 * (2 ** self.request.retries))
            else:
                logger.critical(
                    f"Max retries exceeded for registration {registration_id}"
                )


@celery_app.task(
    name='events.expire_pending_registrations',
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    soft_time_limit=300,
    time_limit=330,
    acks_late=True
)
def expire_pending_registrations(self):
    """
    REAPER TASK: Expire pending registrations after 2 hours.
    Runs every 5 minutes via Celery beat.
    """
    app = _flask_app()
    with app.app_context():
        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=2)

        expired_registrations = db.session.query(EventRegistration).filter(
            EventRegistration.payment_status == EventRegistration.PAYMENT_PENDING,
            EventRegistration.status == EventRegistration.STATUS_PENDING_PAYMENT,
            EventRegistration.created_at <= cutoff_time,
        ).with_for_update(of=EventRegistration).all()

        expired_count = 0
        capacity_released = {}

        for registration in expired_registrations:
            try:
                ticket_type_id = registration.ticket_type_id
                event_id = registration.event_id

                registration.payment_status = EventRegistration.PAYMENT_EXPIRED
                registration.status = EventRegistration.STATUS_EXPIRED
                registration.notes = (
                    f"Auto-expired by Reaper at "
                    f"{datetime.now(timezone.utc).isoformat()}"
                )

                db.session.add(registration)

                key = f"{event_id}:{ticket_type_id}"
                capacity_released[key] = capacity_released.get(key, 0) + 1
                expired_count += 1

            except Exception as e:
                logger.error(
                    f"Failed to expire registration {registration.id}: {e}"
                )

        if expired_count > 0:
            db.session.commit()

            try:
                from app.events.signal_handlers import event_capacity_released
                for key, count in capacity_released.items():
                    event_id, ticket_type_id = key.split(':')
                    event_capacity_released.send(
                        current_app._get_current_object(),
                        event_id=int(event_id),
                        ticket_type_id=int(ticket_type_id),
                        seats_released=count,
                    )
            except Exception as sig_error:
                logger.warning(
                    f"Failed to send capacity released signals: {sig_error}"
                )

            for key, count in capacity_released.items():
                event_id, ticket_type_id = key.split(':')
                try:
                    process_waitlist_auto_conversion.delay(
                        event_id=int(event_id),
                        ticket_type_id=int(ticket_type_id),
                        seats_released=count,
                    )
                    logger.info(
                        f"Triggered waitlist auto-conversion for event "
                        f"{event_id}, ticket type {ticket_type_id}, seats {count}"
                    )
                except Exception as task_error:
                    logger.error(
                        f"Failed to trigger waitlist auto-conversion task: {task_error}"
                    )

            logger.info(
                f"Reaper expired {expired_count} pending registrations, "
                f"released {len(capacity_released)} capacity buckets"
            )

            return {
                'expired_count': expired_count,
                'capacity_released': capacity_released,
                'timestamp': datetime.now(timezone.utc).isoformat(),
            }


@celery_app.task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    soft_time_limit=300,
    time_limit=330,
    acks_late=True
)
def process_waitlist_auto_conversion(self, event_id, ticket_type_id, seats_released):
    """
    Convert waitlisted entries to confirmed registrations when capacity
    becomes available.

    Uses EventService.register_for_event_optimistic() with the event slug.
    """
    app = _flask_app()
    with app.app_context():
        try:
            event = db.session.get(Event, event_id)
            if not event:
                logger.error(f"Event {event_id} not found")
                return {"status": "failed", "reason": "event_not_found"}

            ticket_type = TicketType.query.with_for_update().filter_by(
                id=ticket_type_id,
                event_id=event_id,
            ).first()

            if not ticket_type:
                logger.error(
                    f"Ticket type {ticket_type_id} not found for event {event_id}"
                )
                return {"status": "failed", "reason": "ticket_type_not_found"}

            waitlist_entries = Waitlist.query.filter(
                Waitlist.event_id == event_id,
                Waitlist.ticket_type_id == ticket_type_id,
                Waitlist.status == 'pending',
            ).order_by(Waitlist.position.asc()).limit(seats_released).all()

            converted_count = 0
            for entry in waitlist_entries:
                try:
                    user = entry.user
                    full_name = user.full_name if user else entry.email
                    email = entry.email

                    reg, qr_code, error = EventService.register_for_event_optimistic(
                        identifier=event.slug,
                        user_id=entry.user_id,
                        data={
                            'ticket_type_id': ticket_type_id,
                            'full_name': full_name,
                            'email': email,
                            'phone': entry.phone,
                        },
                        booking_type=BookingType.SELF.value,
                    )

                    if error:
                        logger.error(
                            f"Failed to register waitlist entry {entry.id}: {error}"
                        )
                        continue

                    entry.mark_converted()
                    db.session.add(entry)
                    converted_count += 1
                    logger.info(
                        f"Successfully converted waitlist entry {entry.id} "
                        f"to registration {reg.get('registration_ref') if reg else ''}"
                    )

                except Exception as e:
                    logger.error(
                        f"Failed to convert waitlist entry {entry.id}: {e}"
                    )
                    db.session.rollback()

            if converted_count:
                db.session.commit()

            logger.info(
                f"Waitlist auto-conversion: converted {converted_count} entries "
                f"for event {event_id}, ticket type {ticket_type_id}"
            )

            return {
                "status": "success",
                "converted_count": converted_count,
                "event_id": event_id,
                "ticket_type_id": ticket_type_id,
                "seats_released": seats_released,
            }

        except Exception as e:
            db.session.rollback()
            logger.error(f"Waitlist auto-conversion task failed: {e}")
            if self.request.retries < self.max_retries:
                raise self.retry(exc=e, countdown=60 * (2 ** self.request.retries))
            else:
                return {
                    "status": "failed",
                    "reason": str(e),
                    "event_id": event_id,
                    "ticket_type_id": ticket_type_id,
                }


@celery_app.task(
    name='events.release_expired_capacity',
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    soft_time_limit=300,
    time_limit=330,
    acks_late=True
)
def release_expired_capacity(self, event_id, ticket_type_id, seats_to_release=1):
    """
    Explicitly release capacity for expired registrations.
    """
    app = _flask_app()
    with app.app_context():
        try:
            updated = db.session.query(TicketType).filter(
                TicketType.id == ticket_type_id,
                TicketType.event_id == event_id,
            ).update({
                'available_seats': func.least(
                    TicketType.capacity,
                    func.coalesce(TicketType.available_seats, 0) + seats_to_release
                ),
                'version': TicketType.version + 1,
            }, synchronize_session=False)

            if updated == 0:
                logger.warning(
                    f"release_expired_capacity: no rows updated for "
                    f"ticket_type_id={ticket_type_id}"
                )
                return False

            db.session.commit()
            logger.info(
                f"Released {seats_to_release} seat(s) for "
                f"ticket_type_id={ticket_type_id}, event_id={event_id}"
            )
            return True

        except Exception as e:
            db.session.rollback()
            logger.error(f"Failed to release capacity: {e}")
            return False


@celery_app.task(
    name="events.release_expired_ticket_holds",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    soft_time_limit=300,
    time_limit=330,
    acks_late=True,
)
def release_expired_ticket_holds(self):
    """Auto-release TicketHolds whose TTL has elapsed.

    Returns their seats to the inventory pool so capacity is never stranded.
    Idempotent: a hold already released/expired is skipped by release_hold().
    """
    app = _flask_app()
    with app.app_context():
        try:
            from app.events.inventory import release_hold, ReservationStatus
            from app.events.inventory import TicketHold

            now = datetime.now(timezone.utc)
            expired = (
                db.session.query(TicketHold)
                .filter(
                    TicketHold.status == ReservationStatus.RESERVED,
                    TicketHold.expires_at <= now,
                )
                .with_for_update()
                .all()
            )
            released = 0
            for hold in expired:
                if release_hold(hold, "expired by beat"):
                    released += 1
            if released:
                db.session.commit()
                logger.info("Released %s expired ticket holds", released)
            return {"released": released}
        except Exception as e:
            logger.error("release_expired_ticket_holds failed: %s", e)
            if self.request.retries < self.max_retries:
                raise self.retry(exc=e, countdown=60)
            return {"released": 0, "error": str(e)}