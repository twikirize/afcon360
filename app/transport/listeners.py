"""
Transport Module - Event Listener
Listens for events without creating circular imports
"""
import logging

logger = logging.getLogger(__name__)

def register_event_listeners():
    """Register all event listeners for transport module"""
    try:
        from app.events.signals import event_registered, event_cancelled

        @event_registered.connect
        def on_event_registered(sender, **kwargs):
            """When user registers for event, offer transport options"""
            logger.info(f"Transport: User {kwargs.get('user_id')} registered for event {kwargs.get('event_id')}")
            # Here you would add transport offers without direct import
            # This is PURELY LOOSE COUPLING - Events module doesn't know Transport exists
            return True

        @event_cancelled.connect
        def on_event_cancelled(sender, **kwargs):
            """When registration cancelled, update transport bookings"""
            logger.info(f"Transport: Registration {kwargs.get('registration_id')} cancelled")

    except ImportError:
        # Events module not available - graceful degradation
        logger.debug("Events signals not available, transport listeners not registered")
