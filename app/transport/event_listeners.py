"""
Signal listeners for Transport module to achieve loose coupling with Events module.
This file should be imported in the Transport module's __init__.py or app initialization.
"""

from flask import current_app
from app.events.signals import offer_services_after_registration, service_provider_data_requested

def handle_event_registration_for_transport(sender, **kwargs):
    """
    Handle event registration to offer transport services.
    This function is called when a user registers for an event.
    """
    user_id = kwargs.get('user_id')
    event_id = kwargs.get('event_id')
    event_slug = kwargs.get('event_slug')
    event_city = kwargs.get('event_city')

    try:
        # Import inside function to avoid circular imports
        from app.transport.services import TransportOfferService

        # Create transport offer for the event
        TransportOfferService.create_offer_for_event(
            user_id=user_id,
            event_id=event_id,
            event_slug=event_slug,
            event_city=event_city
        )
        current_app.logger.info(f"Created transport offer for user {user_id} for event {event_slug}")
    except ImportError:
        current_app.logger.warning("TransportOfferService not available")
    except Exception as e:
        current_app.logger.error(f"Failed to create transport offer: {e}")

def handle_service_provider_data_request(sender, **kwargs):
    """
    Handle request for service provider data.
    Returns transport-related data for the dashboard.
    """
    user_id = kwargs.get('user_id')
    dashboard_data = kwargs.get('dashboard_data', {})

    try:
        # Import inside function to avoid circular imports
        from app.transport.models import Vehicle

        # Get user's vehicles
        user_vehicles = Vehicle.query.filter_by(owner_user_id=user_id).all()

        # Convert to dict format
        vehicles_data = []
        for vehicle in user_vehicles:
            vehicles_data.append({
                'id': vehicle.id,
                'make': vehicle.make,
                'model': vehicle.model,
                'year': vehicle.year,
                'license_plate': vehicle.license_plate,
                'current_location': vehicle.current_location,
                'status': vehicle.status
            })

        # Return data via the dashboard_data dict (passed by reference)
        if 'vehicles' not in dashboard_data:
            dashboard_data['vehicles'] = []
        dashboard_data['vehicles'].extend(vehicles_data)

    except ImportError:
        current_app.logger.warning("Vehicle model not available")
    except Exception as e:
        current_app.logger.error(f"Failed to get transport data: {e}")

# Connect signal listeners when the module is initialized
def connect_transport_listeners():
    """
    Connect all signal listeners for the Transport module.
    This should be called during app initialization.
    """
    offer_services_after_registration.connect(handle_event_registration_for_transport)
    service_provider_data_requested.connect(handle_service_provider_data_request)
    current_app.logger.info("Transport module signal listeners connected")
