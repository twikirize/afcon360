"""
Signal handlers for Events module to maintain data consistency.
"""

from flask import current_app
from app.extensions import db
from app.events.models import TicketType
from sqlalchemy import and_, func

# Define signals here since app.events.signals doesn't exist
try:
    from blinker import signal
    event_capacity_released = signal('event-capacity-released')
    event_registered = signal('event-registered')
    event_cancelled = signal('event-cancelled')
    offer_services_after_registration = signal('offer-services-after-registration')
    service_provider_data_requested = signal('service-provider-data-requested')
except ImportError:
    # Fallback if blinker is not available
    class SimpleSignal:
        def __init__(self, name):
            self.name = name
            self.receivers = []

        def connect(self, receiver, weak=False):
            self.receivers.append(receiver)

        def send(self, sender, **kwargs):
            for receiver in self.receivers:
                try:
                    receiver(sender, **kwargs)
                except Exception as e:
                    current_app.logger.error(f"Error in signal receiver {receiver}: {e}")

    event_capacity_released = SimpleSignal('event-capacity-released')
    event_registered = SimpleSignal('event-registered')
    event_cancelled = SimpleSignal('event-cancelled')
    offer_services_after_registration = SimpleSignal('offer-services-after-registration')
    service_provider_data_requested = SimpleSignal('service-provider-data-requested')

def handle_capacity_released(sender, **kwargs):
    """
    Handle capacity released signal from Reaper task.
    Updates ticket type available seats when seats are released.
    Uses atomic SQL updates to prevent race conditions.

    This is the AFCON-proof way to release capacity back to the pool.
    """
    event_id = kwargs.get('event_id')
    ticket_type_id = kwargs.get('ticket_type_id')
    seats_released = kwargs.get('seats_released', 1)

    if not ticket_type_id:
        # Use logging module directly
        import logging
        logger = logging.getLogger(__name__)
        logger.warning("No ticket_type_id provided to handle_capacity_released")
        return

    max_retries = 3
    for attempt in range(max_retries):
        try:
            # Get ticket type to check capacity
            ticket_type = TicketType.query.filter_by(
                id=ticket_type_id,
                event_id=event_id
            ).first()

            if not ticket_type:
                # Use logging module directly
                import logging
                logger = logging.getLogger(__name__)
                logger.warning(f"Ticket type {ticket_type_id} not found for event {event_id}")
                return

            # For unlimited capacity tickets (capacity is 0 or None), just update version
            if not ticket_type.capacity or ticket_type.capacity == 0:
                # Update version only to maintain consistency
                db.session.query(TicketType).filter(
                    TicketType.id == ticket_type_id,
                    TicketType.event_id == event_id
                ).update({
                    'version': TicketType.version + 1
                })
                db.session.commit()
                # Use logging module directly
                import logging
                logger = logging.getLogger(__name__)
                logger.info(f"Updated version for unlimited capacity ticket type {ticket_type_id}")
                return

            # For limited capacity tickets, use atomic update to increment available_seats
            # Ensure we never exceed the capacity
            # Use a single atomic UPDATE query
            # This is a single atomic operation that:
            # 1. Adds seats_released to available_seats (handling NULL with coalesce)
            # 2. Caps at capacity using LEAST function
            # 3. Increments version for optimistic locking
            updated = db.session.query(TicketType).filter(
                and_(
                    TicketType.id == ticket_type_id,
                    TicketType.event_id == event_id
                )
            ).update({
                'available_seats': func.least(
                    TicketType.capacity,
                    func.coalesce(TicketType.available_seats, 0) + seats_released
                ),
                'version': TicketType.version + 1
            }, synchronize_session=False)

            if updated == 0:
                # No rows updated - this shouldn't happen, but retry
                db.session.rollback()
                if attempt == max_retries - 1:
                    # Use logging module directly
                    import logging
                    logger = logging.getLogger(__name__)
                    logger.warning(
                        f"Failed to release capacity after {max_retries} attempts for "
                        f"ticket type {ticket_type_id}."
                    )
                continue

            db.session.commit()

            # Use logging module directly
            import logging
            logger = logging.getLogger(__name__)
            logger.info(
                f"Capacity released: {seats_released} seat(s) for ticket type {ticket_type.name} "
                f"(Event ID: {event_id})."
            )
            return

        except Exception as e:
            # Use logging module directly
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Failed to handle capacity release (attempt {attempt + 1}): {e}")
            db.session.rollback()
            if attempt == max_retries - 1:
                logger.error(f"Max retries exceeded for capacity release: {e}")

# Connect the signal handler
def connect_event_signal_handlers():
    """
    Connect all signal handlers for the Events module.
    This should be called during app initialization.
    """
    event_capacity_released.connect(handle_capacity_released)
    # Use logging module directly since current_app might not be available
    import logging
    logger = logging.getLogger(__name__)
    logger.info("Events module signal handlers connected")
