"""Decorators for accommodation module routes."""

from functools import wraps
from flask import abort
from flask_login import current_user
from app.accommodation.services.identity_service import AccommodationIdentityService


def property_owner_required(f):
    """Decorator to verify current user can manage the property specified by property_id."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        property_id = kwargs.get('property_id') or (args[0] if args else None)
        if property_id is None:
            abort(400, "property_id is required")
        
        from app.accommodation.models.property import Property
        prop = Property.query.get_or_404(property_id)
        
        if not AccommodationIdentityService.can_manage_property(
            current_user,
            property_owner_user_id=prop.owner_user_id,
            property_owner_org_id=prop.owner_org_id,
        ):
            abort(403)
        
        return f(*args, **kwargs)
    return decorated_function


def room_owner_required(f):
    """Decorator to verify current user can manage the room's property."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        room_id = kwargs.get('room_id') or (args[0] if args else None)
        if room_id is None:
            abort(400, "room_id is required")
        
        from app.accommodation.models.room import Room
        from app.accommodation.models.property import Property
        room = Room.query.get_or_404(room_id)
        prop = Property.query.get_or_404(room.property_id)
        
        if not AccommodationIdentityService.can_manage_property(
            current_user,
            property_owner_user_id=prop.owner_user_id,
            property_owner_org_id=prop.owner_org_id,
        ):
            abort(403)
        
        return f(*args, **kwargs)
    return decorated_function


def booking_owner_required(f):
    """Decorator to verify current user can manage the booking."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        booking_id = kwargs.get('booking_id') or (args[0] if args else None)
        if booking_id is None:
            abort(400, "booking_id is required")
        
        from app.accommodation.models.booking import AccommodationBooking
        booking = AccommodationBooking.query.get_or_404(booking_id)
        prop = booking.accommodation_property
        
        if not AccommodationIdentityService.can_manage_property(
            current_user,
            property_owner_user_id=prop.owner_user_id,
            property_owner_org_id=prop.owner_org_id,
        ):
            abort(403)
        
        return f(*args, **kwargs)
    return decorated_function
