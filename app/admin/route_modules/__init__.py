"""
Admin Routes Package - AFCON360
Imports and registers all admin route modules.
"""

# Import the main routes file to register core admin routes
from ..routes import *

# Import all route modules to register them with the admin blueprint
from . import event_manager
from . import transport_admin
from . import wallet_admin
from . import accommodation_admin
from . import tourism_admin
from . import org_admin
from . import org_member

# Make sure all route modules are available
__all__ = [
    'routes',
    'event_manager',
    'transport_admin', 
    'wallet_admin',
    'accommodation_admin',
    'tourism_admin',
    'org_admin',
    'org_member'
]
