"""
Signal listeners for Accommodation module to achieve loose coupling with Events module.
This file should be imported in the Accommodation module's __init__.py or app initialization.
"""

from flask import current_app
from app.events.signals import offer_services_after_registration, service_provider_data_requested

def handle_event_registration_for_accommodation(sender, **kwargs):
    """
    Handle event registration to offer accommodation services.
    This function is called when a user registers for an event.
    """
    user_id = kwargs.get('user_id')
    event_id = kwargs.get('event_id')
    event_slug = kwargs.get('event_slug')
    event_city = kwargs.get('event_city')
    event_start_date = kwargs.get('event_start_date')

    try:
        # Import inside function to avoid circular imports
        from app.accommodation.services import AccommodationOfferService

        # Create accommodation offer for the event
        AccommodationOfferService.create_offer_for_event(
            user_id=user_id,
            event_id=event_id,
            event_slug=event_slug,
            event_city=event_city,
            event_start_date=event_start_date
        )
        current_app.logger.info(f"Created accommodation offer for user {user_id} for event {event_slug}")
    except ImportError:
        current_app.logger.warning("AccommodationOfferService not available")
    except Exception as e:
        current_app.logger.error(f"Failed to create accommodation offer: {e}")

def handle_service_provider_data_request(sender, **kwargs):
    """
    Handle request for service provider data.
    Returns accommodation-related data for the dashboard.
    """
    user_id = kwargs.get('user_id')
    dashboard_data = kwargs.get('dashboard_data', {})

    try:
        # Import inside function to avoid circular imports
        from app.accommodation.models.property import Property

        # Get user's properties
        user_properties = Property.query.filter_by(owner_user_id=user_id).all()

        # Convert to dict format
        properties_data = []
        for property in user_properties:
            properties_data.append({
                'id': property.id,
                'title': property.title,
                'description': property.description,
                'city': property.city,
                'address': property.address,
                'property_type': property.property_type.value if hasattr(property.property_type, 'value') else str(property.property_type),
                'status': property.status.value if hasattr(property.status, 'value') else str(property.status)
            })

        # Return data via the dashboard_data dict (passed by reference)
        if 'properties' not in dashboard_data:
            dashboard_data['properties'] = []
        dashboard_data['properties'].extend(properties_data)

    except ImportError:
        current_app.logger.warning("Property model not available")
    except Exception as e:
        current_app.logger.error(f"Failed to get accommodation data: {e}")

# Connect signal listeners when the module is initialized
def connect_accommodation_listeners():
    """
    Connect all signal listeners for the Accommodation module.
    This should be called during app initialization.
    """
    offer_services_after_registration.connect(handle_event_registration_for_accommodation)
    service_provider_data_requested.connect(handle_service_provider_data_request)
    current_app.logger.info("Accommodation module signal listeners connected")
