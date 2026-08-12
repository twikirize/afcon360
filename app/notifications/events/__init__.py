"""
AFCON360 Platform Event Backbone
================================

This subpackage is the **event layer** that sits UNDERNEATH the notification
delivery layer. It is deliberately hosted inside ``app/notifications/`` rather
than a new top-level package because:

* ``app/events/`` is already the AFCON **events business domain** (matches,
  tickets, registrations) — a new top-level ``app/events`` would collide.
* Communication (events + notifications) is one platform capability. Keeping
  them together avoids scattering the backbone across the tree.

Layering
--------

    Domain services (wallet, kyc, accommodation, transport, ...)
            |  emit_event(...)  -- same DB transaction
            v
    OutboxEvent  (transactional outbox, guaranteed durable)
            |  relay worker
            v
    DomainEvent ledger  +  Redis Streams bus
            |
            +--> NotificationConsumer --> PolicyEngine --> NotificationService
            +--> AuditConsumer
            +--> AnalyticsConsumer
            +--> WebhookConsumer (external partner subscriptions)

Key guarantees
--------------

* **Atomicity** — the event row is written in the SAME transaction as the
  business change (transactional outbox), so an event can never be lost
  because a process died between COMMIT and publish.
* **Idempotency** — every event carries a stable ``event_id``; consumers record
  ``ProcessedEvent`` rows so redelivery never double-sends an email.
* **Traceability** — ``correlation_id`` chains a whole user journey,
  ``causation_id`` links an event to the event that caused it.
* **Versioning** — ``event_version`` lets payloads evolve without breaking
  existing consumers.
* **Replay** — the ``DomainEvent`` ledger is durable and replayable into a
  single consumer without re-sending user-facing notifications.

Nothing in the existing notification delivery layer was removed; this is
strictly the missing layer beneath it.
"""

from .models import (
    DomainEvent,
    OutboxEvent,
    ProcessedEvent,
    EventSubscription,
    WebhookDelivery,
    EventStatus,
    OutboxStatus,
    SubscriptionStatus,
)
from .schemas import EventEnvelope, EventMeta
from .registry import (
    EventType,
    EventRegistry,
    event_registry,
    register_event,
)
from .publisher import (
    emit_event,
    publish_event,
    EventPublisher,
)
from .outbox import OutboxRelay
from .bus import EventBus, event_bus
from .consumers import (
    BaseConsumer,
    NotificationConsumer,
    AuditConsumer,
    AnalyticsConsumer,
    WebhookConsumer,
    ConsumerRegistry,
    consumer_registry,
)
from .policy import (
    NotificationPolicy,
    PolicyEngine,
    policy_engine,
    Audience,
    DeliveryClass,
)
from .replay import EventReplayer
from .context import (
    correlation_scope,
    get_correlation_id,
    set_correlation_id,
    new_correlation_id,
)
from .exceptions import (
    EventError,
    UnknownEventTypeError,
    EventValidationError,
    ConsumerError,
    RetryableConsumerError,
    PermanentConsumerError,
)

__all__ = [
    # models
    'DomainEvent',
    'OutboxEvent',
    'ProcessedEvent',
    'EventSubscription',
    'WebhookDelivery',
    'EventStatus',
    'OutboxStatus',
    'SubscriptionStatus',
    # schema
    'EventEnvelope',
    'EventMeta',
    # registry
    'EventType',
    'EventRegistry',
    'event_registry',
    'register_event',
    # publishing
    'emit_event',
    'publish_event',
    'EventPublisher',
    'OutboxRelay',
    'EventBus',
    'event_bus',
    # consuming
    'BaseConsumer',
    'NotificationConsumer',
    'AuditConsumer',
    'AnalyticsConsumer',
    'WebhookConsumer',
    'ConsumerRegistry',
    'consumer_registry',
    # policy
    'NotificationPolicy',
    'PolicyEngine',
    'policy_engine',
    'Audience',
    'DeliveryClass',
    # ops
    'EventReplayer',
    # tracing
    'correlation_scope',
    'get_correlation_id',
    'set_correlation_id',
    'new_correlation_id',
    # errors
    'EventError',
    'UnknownEventTypeError',
    'EventValidationError',
    'ConsumerError',
    'RetryableConsumerError',
    'PermanentConsumerError',
]
