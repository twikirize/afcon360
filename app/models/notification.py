"""
Backward-compatible re-export from app.notifications.models.

The canonical notification models now live in app/notifications/models.py.
This file re-exports them for backward compatibility with existing imports.
"""

from app.notifications.models import (
    Notification,
    NotificationType,
    NotificationChannel,
    NotificationStatus,
    NotificationTemplate,
    UserNotificationPreference,
    NotificationLog,
    CommunicationSettings,
    NotificationAggregator,
    Message,
)

__all__ = [
    'Notification',
    'NotificationType',
    'NotificationChannel',
    'NotificationStatus',
    'NotificationTemplate',
    'UserNotificationPreference',
    'NotificationLog',
    'CommunicationSettings',
    'NotificationAggregator',
    'Message',
]