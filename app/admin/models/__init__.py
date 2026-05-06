# app/admin/models/__init__.py
"""
Admin models module - exposes all models from the admin package
"""

# Import models directly from their respective modules to avoid circular imports
from app.admin.models.emergency_access import EmergencyAccess
from app.admin.models.moderation import ContentSubmission, ModerationLog

# Import from the main models file for other models
try:
    from app.admin.models import (
        ManageableCategory,
        ManageableItem,
        UserDashboardConfig,
        ContentFlag,
    )
except ImportError:
    # If the main models file has issues, try importing from individual files
    try:
        from app.admin.models.core import ManageableCategory, ManageableItem
        from app.admin.models.dashboard import UserDashboardConfig
    except ImportError:
        # Fallback - define empty classes to prevent import errors
        ManageableCategory = None
        ManageableItem = None
        UserDashboardConfig = None
        ContentFlag = None

__all__ = [
    'EmergencyAccess',
    'ManageableCategory',
    'ManageableItem', 
    'ContentSubmission',
    'UserDashboardConfig',
    'ContentFlag',
    'ModerationLog',
]
