"""
Accommodation Module - Event Listener
Listens for events without creating circular imports
"""
import logging

logger = logging.getLogger(__name__)

def register_accommodation_listeners():
    """Register all event listeners for accommodation module"""
    try:
        from app.events.signals import event_registered

        @event_registered.connect
        def on_event_registered(sender, **kwargs):
            """When user registers for event, offer hotel recommendations"""
            logger.info(f"Accommodation: User {kwargs.get('user_id')} registered for event {kwargs.get('event_id')}")
            # Hotel offers would go here - STILL LOOSE COUPLING

    except ImportError:
        logger.debug("Events signals not available, accommodation listeners not registered")
