"""
AFCON360 Unified Notification System

Blueprint registration, service exports, and model exports.
"""

from flask import Blueprint

from .routes import notifications_api

from .models import (
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
from .services import NotificationService
from .preferences import PreferenceService
from .tasks import (
    send_notification_task,
    send_bulk_task,
    schedule_reminders_task,
    cleanup_old_notifications_task,
    resend_failed_task,
)
from .template_loader import template_loader
from .utils import calculate_backoff, generate_idempotency_key

__all__ = [
    'notifications_api',
    'Notification',
    'NotificationType',
    'NotificationChannel',
    'NotificationStatus',
    'NotificationTemplate',
    'UserNotificationPreference',
    'NotificationLog',
    'CommunicationSettings',
    'NotificationAggregator',
    'NotificationService',
    'PreferenceService',
    'send_notification_task',
    'send_bulk_task',
    'schedule_reminders_task',
    'cleanup_old_notifications_task',
    'resend_failed_task',
    'template_loader',
    'calculate_backoff',
    'generate_idempotency_key',
]