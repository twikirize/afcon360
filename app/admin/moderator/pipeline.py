from app.admin.services import create_flag
from datetime import datetime

def _score_priority(entity_type: str, submitted_by_user) -> str:
    """
    Simple risk scoring. Returns priority string.
    Extend this later with ML hooks.
    """
    # New/unverified accounts are higher risk
    if not getattr(submitted_by_user, 'is_verified', True):
        return "high"
    return "normal"

def submit_for_moderation(entity_type: str, object_id: int, reason: str, submitted_by_user, priority: str = None):
    """
    Universal moderation entry point for ALL modules.
    Wraps create_flag(). Does NOT change entity state.
    """
    if priority is None:
        priority = _score_priority(entity_type, submitted_by_user)
    return create_flag(
        submitted_by_user,
        entity_type,
        object_id,
        reason,
        priority=priority,
    )


def validate_submission(category_slug: str, data: dict) -> tuple[bool, list[str]]:
    """Validate submission data before creating flag."""
    errors = []
    
    validators = {
        'vehicle': _validate_vehicle,
        'property': _validate_property,
        'event': _validate_event,
        'driver': _validate_driver,
    }
    
    validator = validators.get(category_slug)
    if validator:
        errors = validator(data)
    
    return len(errors) == 0, errors


def _validate_vehicle(data):
    errors = []
    if not data.get('registration_number'):
        errors.append('Registration number required')
    if data.get('year') and not (1900 <= data['year'] <= datetime.now().year):
        errors.append('Invalid year')
    return errors


def _validate_property(data):
    errors = []
    if not data.get('title'):
        errors.append('Property title required')
    if not data.get('address'):
        errors.append('Property address required')
    if data.get('max_guests') and data['max_guests'] < 1:
        errors.append('Must accommodate at least 1 guest')
    return errors


def _validate_event(data):
    errors = []
    if not data.get('name'):
        errors.append('Event name required')
    if not data.get('start_date'):
        errors.append('Start date required')
    if data.get('max_capacity') and data['max_capacity'] < 0:
        errors.append('Capacity cannot be negative')
    return errors


def _validate_driver(data):
    errors = []
    if not data.get('name'):
        errors.append('Driver name required')
    if not data.get('license_number'):
        errors.append('License number required')
    return errors
