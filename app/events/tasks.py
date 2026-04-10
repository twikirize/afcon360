# app/events/tasks.py
import logging
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
    from app import create_app # Assuming your create_app function is in app/__init__.py
    return create_app()

@celery_app.task
def process_event_registration(registration_id: int, event_slug: str):
    """
    Background task to generate QR code, upload it, and send confirmation email.
    """
    app = create_flask_app()
    with app.app_context():
        registration = EventRegistration.query.get(registration_id)
        event = Event.query.filter_by(slug=event_slug).first()

        if not registration or not event:
            logger.error(f"Task failed: Registration {registration_id} or Event {event_slug} not found.")
            return

        try:
            # 1. Generate QR Code
            qr_code_base64 = EventService._generate_qr_code(registration.qr_token, registration.registration_ref)

            # TODO: Implement actual QR code storage (e.g., S3, local file system)
            # For now, we'll just log it or store it in metadata if needed
            # registration.qr_code_url = "url_to_stored_qr_code"
            # db.session.add(registration)
            # db.session.commit()

            # 2. Send Confirmation Email (Placeholder for SendGrid/other service)
            # This would involve rendering an email template and sending it
            logger.info(f"Sending confirmation email for registration {registration.registration_ref} to {registration.email}")
            logger.info(f"QR Code for {registration.registration_ref}: {qr_code_base64[:50]}...") # Log first 50 chars

            # Example: send_email_with_qr(registration.email, event.name, qr_code_base64)

            logger.info(f"Successfully processed background task for registration {registration.registration_ref}")

        except Exception as e:
            logger.error(f"Error in background task for registration {registration.registration_ref}: {e}")
            # Optionally, update registration status to 'failed_email_send' or similar
            db.session.rollback()
