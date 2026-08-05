"""
Backward-compatible re-export from app.notifications.services.

The canonical notification service now lives in app/notifications/services.py.
This file re-exports it for backward compatibility with existing imports.
"""

from app.notifications.services import NotificationService

__all__ = ['NotificationService']