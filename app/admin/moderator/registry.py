"""
Universal Module Registry - Single source of truth for all modifiable content
"""

_REGISTRY = {}
_MODULE_INDEX = {}  # module_name -> list of entity_types

def register_module(entity_type: str, display_name: str, review_url_fn=None, module_name='general', icon='fa-file-alt'):
    """Register a module with the moderator system"""
    _REGISTRY[entity_type] = {
        "display_name": display_name,
        "review_url_fn": review_url_fn,
        "module_name": module_name,
        "icon": icon,
        "is_registered": True
    }
    
    # Update module index
    if module_name not in _MODULE_INDEX:
        _MODULE_INDEX[module_name] = []
    if entity_type not in _MODULE_INDEX[module_name]:
        _MODULE_INDEX[module_name].append(entity_type)
    
    return True

def get_registry():
    return dict(_REGISTRY)

def get_modules():
    """Return all registered modules with counts"""
    return {
        module: {
            'entity_types': types,
            'count': len(types)
        }
        for module, types in _MODULE_INDEX.items()
    }

def get_review_url(entity_type: str, entity_id: int) -> str | None:
    entry = _REGISTRY.get(entity_type)
    if entry and entry.get("review_url_fn"):
        return entry["review_url_fn"](entity_id)
    return None

def get_entity_display(entity_type: str) -> str:
    entry = _REGISTRY.get(entity_type)
    return entry["display_name"] if entry else entity_type.replace('_', ' ').title()

def get_entity_icon(entity_type: str) -> str:
    entry = _REGISTRY.get(entity_type)
    return entry.get("icon", "fa-file-alt") if entry else "fa-file-alt"

# Auto-register core modules on import
def _auto_register_core():
    """Register core entity types that are built-in"""
    # Users
    register_module('user', 'User Account', module_name='Users', icon='fa-user')
    register_module('organisation', 'Organisation', module_name='Users', icon='fa-building')
    
    # Events (if available)
    try:
        from flask import url_for
        register_module('event', 'Event',
                       review_url_fn=lambda id: url_for('events.moderate_detail', id=id),
                       module_name='Events', icon='fa-calendar')
    except:
        pass
    
    # Transport (if available)
    try:
        from flask import url_for
        register_module('transport_booking', 'Transport Booking',
                       review_url_fn=lambda id: url_for('transport.moderate_booking', id=id),
                       module_name='Transport', icon='fa-bus')
        register_module('vehicle', 'Vehicle',
                       review_url_fn=lambda id: url_for('transport.moderate_vehicle', id=id),
                       module_name='Transport', icon='fa-truck')
        register_module('driver', 'Driver',
                       review_url_fn=lambda id: url_for('transport.moderate_driver', id=id),
                       module_name='Transport', icon='fa-id-card')
    except:
        pass
    
    # Accommodation (if available)
    try:
        from flask import url_for
        register_module('accommodation_property', 'Accommodation Property',
                       review_url_fn=lambda id: url_for('accommodation.moderate_property', id=id),
                       module_name='Accommodation', icon='fa-building')
        register_module('accommodation_booking', 'Accommodation Booking',
                       review_url_fn=lambda id: url_for('accommodation.moderate_booking', id=id),
                       module_name='Accommodation', icon='fa-bed')
        register_module('accommodation_review', 'Accommodation Review',
                       review_url_fn=lambda id: url_for('accommodation.moderate_review', id=id),
                       module_name='Accommodation', icon='fa-star')
    except:
        pass
    
    # Tourism (if available)
    try:
        from flask import url_for
        register_module('tourism_listing', 'Tourism Attraction',
                       review_url_fn=lambda id: url_for('tourism.moderate_listing', id=id),
                       module_name='Tourism', icon='fa-tree')
        register_module('tourism_package', 'Tourism Package',
                       review_url_fn=lambda id: url_for('tourism.moderate_package', id=id),
                       module_name='Tourism', icon='fa-suitcase')
    except:
        pass
    
    # KYC (if available)
    try:
        from flask import url_for
        register_module('kyc_document', 'KYC Document',
                       review_url_fn=lambda id: url_for('kyc.moderate_document', id=id),
                       module_name='KYC', icon='fa-id-card')
    except:
        pass

# Run auto-registration
_auto_register_core()
