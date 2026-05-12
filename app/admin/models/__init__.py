# app/admin/models/__init__.py
"""
Admin models module - exposes all models from the admin package
"""

# Import models directly from their respective modules to avoid circular imports
# Lazy import to prevent blueprint registration during model loading
try:
    from app.admin.models.emergency_access import EmergencyAccess
except ImportError:
    EmergencyAccess = None

try:
    from app.admin.models.moderation import ContentSubmission, ModerationLog
except ImportError:
    ContentSubmission = None
    ModerationLog = None

# Import from individual model files to avoid circular imports
try:
    from app.admin.models.core import (
        ManageableCategory,
        ManageableItem,
        UserDashboardConfig,
        SystemConfiguration,
    )
except ImportError:
    ManageableCategory = None
    ManageableItem = None
    UserDashboardConfig = None
    SystemConfiguration = None

# Import ContentFlag from moderation module
try:
    from app.admin.models.moderation import ContentFlag
except ImportError:
    ContentFlag = None

__all__ = [
    'EmergencyAccess',
    'ManageableCategory', 
    'ManageableItem',
    'ContentSubmission',
    'UserDashboardConfig',
    'ContentFlag',
    'ModerationLog',
    'SystemConfiguration',
]

# Filter out None values from __all__
__all__ = [name for name in __all__ if locals().get(name) is not None]
