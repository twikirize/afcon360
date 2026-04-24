# app/events/tasks.py
import json
import logging
from datetime import datetime
from celery import Celery
from flask import Flask, current_app
from app.extensions import db # Assuming db is initialized in app.extensions
from app.events.services import EventService
from app.events.models import EventRegistration, Event

logger = logging.getLogger(__name__)

# Initialize Celery - configuration should come from environment variables
import os

# Get Redis URL from environment or config
redis_url = os.getenv('REDIS_URL') or os.getenv('CELERY_BROKER_URL')
if not redis_url:
    flask_env = os.getenv("FLASK_ENV", "production")
    if flask_env == "production":
        raise RuntimeError(
            "REDIS_URL must be set in production for Celery. "
            "Set REDIS_URL or CELERY_BROKER_URL environment variable."
        )
    else:
        # Development fallback with warning
        redis_url = 'redis://localhost:6379/0'
        # Use print instead of logger since logger might not be initialized yet
        print(f"WARNING: Using development Redis URL for Celery - configure REDIS_URL environment variable for production")

celery_app = Celery('event_tasks', broker=redis_url, backend=redis_url)

# This is a placeholder for your Flask app creation function
# In a real app, you'd import your create_app function
def create_flask_app():
    try:
        from app import create_app # Assuming your create_app function is in app/__init__.py
        return create_app()
    except ImportError as e:
        logger.error(f"Failed to import create_app: {e}")
        # Create a minimal Flask app for testing
        from flask import Flask
        app = Flask(__name__)
        app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
        app.config['TESTING'] = True
        return app

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
    Background task to generate QR code, upload it, and send confirmation email.
    """
    # Check idempotency
    # Note: redis_client needs to be imported from app.extensions
    try:
        from app.extensions import redis_client
        if task_idempotency_key and redis_client and hasattr(redis_client, 'get'):
            cache_key = f"task_idempotency:{task_idempotency_key}"
            if redis_client.get(cache_key):
                logger.info(f"Task already processed: {task_idempotency_key}")
                return {"status": "skipped", "reason": "already_processed"}
            redis_client.setex(cache_key, 3600, "1")  # 1 hour TTL
    except ImportError:
        logger.warning("redis_client not available, skipping idempotency check")
    except Exception as e:
        logger.warning(f"Error checking idempotency: {e}")

    app = create_flask_app()
    with app.app_context():
        try:
            # Use with_for_update to lock the registration
            registration = EventRegistration.query.with_for_update(
                of=EventRegistration, nowait=True
            ).get(registration_id)

            event = Event.query.filter_by(slug=event_slug).first()

            if not registration or not event:
                logger.error(f"Task failed: Registration {registration_id} or Event {event_slug} not found.")
                return {"status": "failed", "reason": "not_found"}

            # Check if already processed
            if registration.status in ["confirmed", "processing"] and registration.payment_status in ["paid", "free"]:
                logger.info(f"Registration {registration_id} already processed")
                return {"status": "skipped", "reason": "already_processed"}

            # Update status to processing
            registration.status = "processing"
            db.session.add(registration)
            db.session.commit()

            try:
                # 1. Generate QR Code
                qr_code_base64 = EventService._generate_qr_code(registration.qr_token, registration.registration_ref)

                # Store QR code reference (in production, upload to S3)
                # For now, we'll store in metadata
                if not registration.notes:
                    registration.notes = ""
                registration.notes += f"\nQR generated at: {datetime.utcnow().isoformat()}"

                # 2. Send Confirmation Email
                logger.info(f"Sending confirmation email for registration {registration.registration_ref} to {registration.email}")
                try:
                    from app.extensions import mail
                    from flask_mail import Message
                    
                    organizer = event.organizer
                    
                    # Send attendee confirmation
                    attendee_msg = Message(
                        subject=f'Registration Confirmed - {event.name}',
                        recipients=[registration.email],
                        html=f'<h2>Registration Confirmed</h2>'
                             f'<p>Dear {registration.full_name},</p>'
                             f'<p>Your registration for <strong>{event.name}</strong> is confirmed.</p>'
                             f'<p>Registration Ref: <strong>{registration.registration_ref}</strong></p>'
                             f'<p>Ticket: {registration.ticket_type}</p>'
                             f'<p>Date: {event.start_date}</p>'
                             f'<p>Venue: {event.venue}, {event.city}</p>'
                    )
                    mail.send(attendee_msg)
                    
                    # Send organizer notification
                    if organizer and organizer.email:
                        organizer_msg = Message(
                            subject=f'New Registration - {event.name}',
                            recipients=[organizer.email],
                            html=f'<h2>New Registration</h2>'
                                 f'<p>A new attendee has registered for <strong>{event.name}</strong>.</p>'
                                 f'<p>Name: {registration.full_name}</p>'
                                 f'<p>Email: {registration.email}</p>'
                                 f'<p>Ticket: {registration.ticket_type}</p>'
                                 f'<p>Ref: {registration.registration_ref}</p>'
                        )
                        mail.send(organizer_msg)
                        
                except Exception as mail_error:
                    logger.warning(f'Email sending failed: {mail_error}')

                # Update status to completed
                registration.status = "confirmed"
                if registration.payment_status == "pending":
                    registration.payment_status = "paid"

                db.session.add(registration)
                db.session.commit()

                logger.info(f"Successfully processed background task for registration {registration.registration_ref}")

            except Exception as e:
                logger.error(f"Error in background task for registration {registration.registration_ref}: {e}")
                registration.status = "failed_processing"
                db.session.add(registration)
                db.session.commit()
                # Retry the task
                raise self.retry(exc=e, countdown=60 * (2 ** self.request.retries))

        except Exception as e:
            logger.error(f"Task setup error: {e}")
            if self.request.retries < self.max_retries:
                raise self.retry(exc=e, countdown=60 * (2 ** self.request.retries))
            else:
                logger.critical(f"Max retries exceeded for registration {registration_id}")

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
    REAPER TASK: Expires pending registrations after 2 hours
    Runs every 5 minutes via Celery beat
    """
    app = create_flask_app()
    with app.app_context():
        from app.extensions import db
        from app.events.models import EventRegistration, TicketType
        from sqlalchemy import and_
        from datetime import datetime, timedelta

        cutoff_time = datetime.utcnow() - timedelta(hours=2)

        # Find expired pending registrations with FOR UPDATE lock to prevent race conditions
        # Use constants from the model
        expired_registrations = db.session.query(EventRegistration).filter(
            and_(
                EventRegistration.payment_status == EventRegistration.PAYMENT_STATUS_PENDING,
                EventRegistration.created_at <= cutoff_time,
                EventRegistration.status == EventRegistration.STATUS_PENDING_PAYMENT
            )
        ).with_for_update(of=EventRegistration).all()

        expired_count = 0
        capacity_released = {}

        for registration in expired_registrations:
            try:
                # Record ticket type before expiry
                ticket_type_id = registration.ticket_type_id
                event_id = registration.event_id

                # Mark as expired using model constants
                registration.payment_status = EventRegistration.PAYMENT_STATUS_EXPIRED
                registration.status = EventRegistration.STATUS_EXPIRED
                registration.notes = f"Auto-expired by Reaper at {datetime.utcnow().isoformat()}"

                db.session.add(registration)

                # Track capacity to release
                key = f"{event_id}:{ticket_type_id}"
                capacity_released[key] = capacity_released.get(key, 0) + 1

                expired_count += 1

            except Exception as e:
                logger.error(f"Failed to expire registration {registration.id}: {e}")
                # Continue with other registrations

        # Commit all changes
        if expired_count > 0:
            db.session.commit()

            # Send capacity release signals for each event/ticket type
            try:
                from app.events.signal_handlers import event_capacity_released
                from flask import current_app
                for key, count in capacity_released.items():
                    event_id, ticket_type_id = key.split(':')
                    event_capacity_released.send(
                        current_app._get_current_object(),
                        event_id=int(event_id),
                        ticket_type_id=int(ticket_type_id),
                        seats_released=count
                    )
            except Exception as sig_error:
                logger.warning(f"Failed to send capacity released signals: {sig_error}")

            # Trigger waitlist auto-conversion for each released capacity bucket
            for key, count in capacity_released.items():
                event_id, ticket_type_id = key.split(':')
                try:
                    # Call the waitlist conversion task asynchronously
                    process_waitlist_auto_conversion.delay(
                        event_id=int(event_id),
                        ticket_type_id=int(ticket_type_id),
                        seats_released=count
                    )
                    logger.info(f"Triggered waitlist auto-conversion for event {event_id}, ticket type {ticket_type_id}, seats {count}")
                except Exception as task_error:
                    logger.error(f"Failed to trigger waitlist auto-conversion task: {task_error}")

            logger.info(f"Reaper expired {expired_count} pending registrations, released {len(capacity_released)} capacity buckets")

            return {
                'expired_count': expired_count,
                'capacity_released': capacity_released,
                'timestamp': datetime.utcnow().isoformat()
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
    Convert waitlisted entries to confirmed registrations when capacity becomes available.
    This task should be triggered after capacity is released (e.g., from expired registrations).
    """
    app = create_flask_app()
    with app.app_context():
        from app.extensions import db
        from app.events.models import Waitlist, TicketType, Event
        from sqlalchemy import and_

        try:
            # Lock the ticket type to prevent race conditions
            ticket_type = TicketType.query.with_for_update().filter_by(
                id=ticket_type_id,
                event_id=event_id
            ).first()

            if not ticket_type:
                logger.error(f"Ticket type {ticket_type_id} not found for event {event_id}")
                return {"status": "failed", "reason": "ticket_type_not_found"}

            # Find waitlist entries for this event and ticket type
            # Sort by position (earliest first)
            waitlist_entries = Waitlist.query.filter(
                and_(
                    Waitlist.event_id == event_id,
                    Waitlist.ticket_type_id == ticket_type_id,
                    Waitlist.status == 'pending'
                )
            ).order_by(Waitlist.position.asc()).limit(seats_released).all()

            converted_count = 0
            for entry in waitlist_entries:
                try:
                    # Use EventService to register the user from waitlist
                    # We need to import EventService here
                    from app.events.services import EventService

                    # Register the user for the event
                    registration_result = EventService.register_for_event_optimistic(
                        event_id=event_id,
                        user_id=entry.user_id,
                        ticket_type_id=ticket_type_id,
                        registration_data={
                            'full_name': entry.user.full_name if entry.user else '',
                            'email': entry.email,
                            'phone': entry.phone,
                            'registered_by': 'waitlist_auto_conversion'
                        }
                    )

                    if registration_result and registration_result.get('success'):
                        # Mark the waitlist entry as converted
                        entry.mark_converted()
                        db.session.add(entry)
                        converted_count += 1
                        logger.info(f"Successfully converted waitlist entry {entry.id} to registration")
                    else:
                        logger.error(f"Failed to register waitlist entry {entry.id}: {registration_result}")

                except Exception as e:
                    logger.error(f"Failed to convert waitlist entry {entry.id}: {e}")
                    # Continue with next entry

            # Commit all changes
            db.session.commit()

            logger.info(f"Waitlist auto-conversion: converted {converted_count} entries for event {event_id}, ticket type {ticket_type_id}")

            return {
                "status": "success",
                "converted_count": converted_count,
                "event_id": event_id,
                "ticket_type_id": ticket_type_id,
                "seats_released": seats_released
            }

        except Exception as e:
            logger.error(f"Waitlist auto-conversion task failed: {e}")
            db.session.rollback()
            # Retry the task
            if self.request.retries < self.max_retries:
                raise self.retry(exc=e, countdown=60 * (2 ** self.request.retries))
            else:
                return {
                    "status": "failed",
                    "reason": str(e),
                    "event_id": event_id,
                    "ticket_type_id": ticket_type_id
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
    Explicitly release capacity for expired registrations
    """
    app = create_flask_app()
    with app.app_context():
        from app.extensions import db
        from app.events.models import TicketType
        from sqlalchemy import func

        try:
            updated = db.session.query(TicketType).filter(
                TicketType.id == ticket_type_id,
                TicketType.event_id == event_id
            ).update({
                'available_seats': func.least(
                    TicketType.capacity,
                    func.coalesce(TicketType.available_seats, 0) + seats_to_release
                ),
                'version': TicketType.version + 1
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
