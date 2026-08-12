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
    NotificationModule,
    MODULE_LABELS,
    MODULE_ICONS,
    MODULE_COLORS,
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
from .mock_data import (
    get_mock_data,
    seed_mock_notification_data,
    clear_mock_notification_data,
)

# ---------------------------------------------------------------------------
# Platform event backbone (the layer BENEATH notification delivery).
#
# Domain services should import `emit_event` / `EventType` from here and publish
# FACTS; the notification consumer + policy engine decide what gets sent.
# Imported lazily-tolerantly so a partially-migrated database never breaks the
# whole notifications package at boot.
# ---------------------------------------------------------------------------
try:
    from .events import (
        emit_event,
        publish_event,
        EventType,
        EventEnvelope,
        event_registry,
        register_event,
        policy_engine,
        NotificationPolicy,
        DeliveryClass,
        Audience,
        consumer_registry,
        event_bus,
        OutboxRelay,
        EventReplayer,
        correlation_scope,
        get_correlation_id,
        DomainEvent,
        OutboxEvent,
        ProcessedEvent,
        EventSubscription,
        WebhookDelivery,
    )
    _EVENTS_AVAILABLE = True
except Exception as _exc:  # pragma: no cover - defensive boot guard
    import logging
    logging.getLogger(__name__).error(
        "Event backbone unavailable: %s", _exc, exc_info=True
    )
    _EVENTS_AVAILABLE = False

__all__ = [
    'notifications_api',
    'Notification',
    'NotificationType',
    'NotificationChannel',
    'NotificationStatus',
    'NotificationModule',
    'MODULE_LABELS',
    'MODULE_ICONS',
    'MODULE_COLORS',
    'NotificationTemplate',
    'UserNotificationPreference',
    'NotificationLog',
    'NotificationDelivery',
    'DeliveryStatus',
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
    'get_mock_data',
    'seed_mock_notification_data',
    'clear_mock_notification_data',
]

if _EVENTS_AVAILABLE:
    __all__ += [
        # publishing (what domain services call)
        'emit_event',
        'publish_event',
        'EventType',
        'EventEnvelope',
        'event_registry',
        'register_event',
        # policy
        'policy_engine',
        'NotificationPolicy',
        'DeliveryClass',
        'Audience',
        # runtime
        'consumer_registry',
        'event_bus',
        'OutboxRelay',
        'EventReplayer',
        # tracing
        'correlation_scope',
        'get_correlation_id',
        # models
        'DomainEvent',
        'OutboxEvent',
        'ProcessedEvent',
        'EventSubscription',
        'WebhookDelivery',
    ]