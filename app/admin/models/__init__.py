# app/admin/models/__init__.py
"""
Admin models module - exposes all models from the admin package
"""

# Import models directly from their respective modules to avoid circular imports
from app.admin.models.emergency_access import EmergencyAccess
from app.admin.models.moderation import ContentSubmission, ModerationLog

# Import from individual model files to avoid circular imports
from app.admin.models.core import (
    ManageableCategory,
    ManageableItem,
    UserDashboardConfig,
    SystemConfiguration,
)

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
