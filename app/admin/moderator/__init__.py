# app/admin/moderator/__init__.py
"""Moderator dashboard module"""

from app.admin.moderator.routes import moderator_bp

# Auto-discover and register modules on import
def _discover_modules():
    """Try to import module registrations from all modules"""
    try:
        # Try to import transport module registration
        from app.transport import transport_bp
        # Transport module exists, registry will handle via _auto_register_core
    except ImportError:
        pass
    
    try:
        # Try to import accommodation module registration
        from app.accommodation import accommodation_bp
    except ImportError:
        pass
    
    try:
        # Try to import tourism module registration
        from app.tourism import tourism_bp
    except ImportError:
        pass
    
    try:
        # Try to import events module registration
        from app.events import events_bp
    except ImportError:
        pass

# Run discovery
_discover_modules()

__all__ = ['moderator_bp']
