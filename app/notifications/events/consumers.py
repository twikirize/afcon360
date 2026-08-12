"""
Event consumers.

Each consumer is an independent reader of the event stream. One event fans out
to all of them, and a failure in one must never affect the others — a bounced
email cannot undo an audit record.

Idempotency contract
--------------------
Every consumer inherits :meth:`BaseConsumer.handle`, which:

1. Checks ``processed_events`` for ``(consumer, event_id)`` and skips if present.
2. Runs the handler inside a ``correlation_scope`` so anything it emits is
   causally linked to the triggering event.
3. Records the outcome.

This is what makes at-least-once delivery safe. A replayed
``payment.successful`` will not send a second receipt, which is precisely the
property the spec calls out as separating robust systems from fragile ones.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Sequence

from sqlalchemy.exc import IntegrityError

from app.extensions import db

from .context import correlation_scope
from .exceptions import PermanentConsumerError, RetryableConsumerError
from .models import (
    DomainEvent,
    EventStatus,
    EventSubscription,
    ProcessedEvent,
    SubscriptionStatus,
    WebhookDelivery,
)
from .policy import Audience, DeliveryClass, policy_engine
from .registry import EventType, event_registry
from .schemas import EventEnvelope

logger = logging.getLogger(__name__)


class BaseConsumer:
    """Base class providing idempotency, tracing and error classification."""

    #: Unique consumer name — the idempotency key partition.
    name: str = 'base'

    def interested_in(self, envelope: EventEnvelope) -> bool:
        """Override to filter which events reach :meth:`process`."""
        return True

    def process(self, envelope: EventEnvelope) -> Any:
        raise NotImplementedError

    # ------------------------------------------------------------------
    def already_processed(self, event_id: str) -> bool:
        return (
            db.session.query(ProcessedEvent.id)
            .filter_by(consumer=self.name, event_id=event_id)
            .first()
            is not None
        )

    def _record(self, envelope: EventEnvelope, status: str, error: Optional[str] = None) -> None:
        try:
            db.session.add(ProcessedEvent(
                consumer=self.name,
                event_id=envelope.event_id,
                event_type=envelope.event_type,
                status=status,
                error=(error or None) if error is None else error[:2000],
                processed_at=datetime.now(timezone.utc),
            ))
            db.session.commit()
        except IntegrityError:
            # Concurrent worker already claimed it — benign.
            db.session.rollback()
        except Exception as exc:
            db.session.rollback()
            logger.warning('Could not record ProcessedEvent for %s: %s',
                           envelope.event_id, exc)

    def handle(self, envelope: EventEnvelope) -> Dict[str, Any]:
        """Entry point used by the dispatcher."""
        if not self.interested_in(envelope):
            return {'consumer': self.name, 'status': 'skipped'}

        if self.already_processed(envelope.event_id):
            return {'consumer': self.name, 'status': 'duplicate'}

        try:
            # Anything emitted inside inherits the trace and is caused by this event.
            with correlation_scope(envelope.correlation_id, envelope.event_id):
                result = self.process(envelope)
            self._record(envelope, 'success')
            return {'consumer': self.name, 'status': 'success', 'result': result}

        except PermanentConsumerError as exc:
            db.session.rollback()
            logger.error('[%s] permanent failure on %s: %s',
                         self.name, envelope.event_id, exc)
            self._record(envelope, 'dead_letter', str(exc))
            return {'consumer': self.name, 'status': 'dead_letter', 'error': str(exc)}

        except RetryableConsumerError as exc:
            db.session.rollback()
            logger.warning('[%s] retryable failure on %s: %s',
                           self.name, envelope.event_id, exc)
            # Not recorded => the event will be retried on redelivery.
            return {'consumer': self.name, 'status': 'retry', 'error': str(exc)}

        except Exception as exc:
            db.session.rollback()
            logger.error('[%s] unexpected failure on %s: %s',
                         self.name, envelope.event_id, exc, exc_info=True)
            return {'consumer': self.name, 'status': 'retry', 'error': str(exc)}


# ----------------------------------------------------------------------
# Notification consumer
# ----------------------------------------------------------------------
class NotificationConsumer(BaseConsumer):
    """
    Turns domain events into user-facing notifications via the policy engine.

    This is the bridge between the new event backbone and the existing
    (deliberately preserved) ``NotificationService`` + ``EmailHandler``.
    """

    name = 'notification'

    def interested_in(self, envelope: EventEnvelope) -> bool:
        # Only events with at least one policy are notification-worthy.
        return bool(policy_engine.policies_for(envelope.event_type))

    def process(self, envelope: EventEnvelope) -> Dict[str, Any]:
        from app.notifications.services import NotificationService

        directives = policy_engine.resolve(envelope)
        if not directives:
            return {'sent': 0}

        sent = 0
        for directive in directives:
            try:
                if directive.audience == Audience.ROLES and directive.roles:
                    NotificationService.notify_roles(
                        roles=directive.roles,
                        notification_type=directive.notification_type,
                        title=directive.title,
                        message=directive.message,
                        link=directive.link,
                        channels=directive.channels,
                        module=directive.module,
                        data=directive.data,
                    )
                    sent += 1
                    continue

                recipients = self._resolve_recipients(directive, envelope)
                for user_id in recipients:
                    NotificationService.send(
                        user_id=user_id,
                        notification_type=directive.notification_type,
                        title=directive.title,
                        message=directive.message,
                        data=directive.data,
                        channels=directive.channels,
                        link=directive.link,
                        priority=directive.priority,
                        module=directive.module,
                        # MANDATORY classes bypass opt-out for external channels.
                        force_external=directive.force_external,
                    )
                    sent += 1
            except Exception as exc:
                logger.error(
                    'Notification directive failed for %s (%s): %s',
                    envelope.event_type, directive.notification_type, exc,
                    exc_info=True,
                )
        return {'sent': sent, 'directives': len(directives)}

    @staticmethod
    def _resolve_recipients(directive, envelope: EventEnvelope) -> List[int]:
        if directive.user_ids:
            return list(directive.user_ids)
        if directive.audience == Audience.ACTOR and envelope.actor_id:
            try:
                return [int(envelope.actor_id)]
            except (TypeError, ValueError):
                return []
        user_id = envelope.user_id
        return [user_id] if user_id else []


# ----------------------------------------------------------------------
# Audit consumer
# ----------------------------------------------------------------------
class AuditConsumer(BaseConsumer):
    """
    Writes compliance audit records.

    Separate from notification logs by design: the audit trail answers "what
    happened", notification logs answer "how we tried to tell someone". A
    failed SMS must never erase the fact that KYC was approved.
    """

    name = 'audit'

    def interested_in(self, envelope: EventEnvelope) -> bool:
        definition = event_registry.get(envelope.event_type)
        # Unregistered events are audited by default (fail safe, not silent).
        return definition.audited if definition else True

    def process(self, envelope: EventEnvelope) -> Dict[str, Any]:
        try:
            from app.audit.models import AuditLog
        except Exception as exc:
            raise PermanentConsumerError(f'Audit model unavailable: {exc}') from exc

        user_id = envelope.user_id
        meta = {
            'event_id': envelope.event_id,
            'event_type': envelope.event_type,
            'event_version': envelope.event_version,
            'correlation_id': envelope.correlation_id,
            'causation_id': envelope.causation_id,
            'payload': envelope.payload,
        }
        metadata = envelope.metadata or {}

        try:
            AuditLog.log(
                user_id=user_id,
                action=envelope.event_type.upper().replace('.', '_'),
                resource_type=envelope.aggregate_type,
                resource_id=envelope.aggregate_id,
                meta=meta,
                ip_address=metadata.get('ip_address'),
                user_agent=metadata.get('user_agent'),
            )
            db.session.commit()
        except Exception as exc:
            db.session.rollback()
            raise RetryableConsumerError(f'Audit write failed: {exc}') from exc

        return {'audited': True}


# ----------------------------------------------------------------------
# Analytics consumer
# ----------------------------------------------------------------------
class AnalyticsConsumer(BaseConsumer):
    """
    Emits structured analytics records.

    Currently structured-log based (zero new infrastructure); the interface is
    ready for a warehouse/queue sink without touching producers.
    """

    name = 'analytics'

    def process(self, envelope: EventEnvelope) -> Dict[str, Any]:
        logger.info(
            'analytics.event %s',
            json.dumps({
                'event_id': envelope.event_id,
                'event_type': envelope.event_type,
                'aggregate_type': envelope.aggregate_type,
                'aggregate_id': envelope.aggregate_id,
                'user_id': envelope.user_id,
                'correlation_id': envelope.correlation_id,
                'occurred_at': envelope.occurred_at.isoformat()
                if envelope.occurred_at else None,
            }, default=str),
        )
        return {'tracked': True}


# ----------------------------------------------------------------------
# Webhook consumer (external partner subscriptions)
# ----------------------------------------------------------------------
class WebhookConsumer(BaseConsumer):
    """
    Fans externally-visible events out to partner subscriptions.

    Implements the reliability model the spec requires for partner webhooks:
    signature, timestamp, delivery id, retry budget, DLQ and replay — tracked
    in ``webhook_deliveries``, entirely separate from user notifications.
    """

    name = 'webhook'

    def interested_in(self, envelope: EventEnvelope) -> bool:
        if not event_registry.is_externally_visible(envelope.event_type):
            return False
        try:
            return db.session.query(EventSubscription.id).filter_by(
                status=SubscriptionStatus.ACTIVE.value
            ).first() is not None
        except Exception:
            return False

    def process(self, envelope: EventEnvelope) -> Dict[str, Any]:
        subscriptions = EventSubscription.query.filter_by(
            status=SubscriptionStatus.ACTIVE.value
        ).all()
        matching = [s for s in subscriptions if s.matches(envelope.event_type)]
        if not matching:
            return {'queued': 0}

        queued = 0
        for subscription in matching:
            delivery = WebhookDelivery(
                subscription_id=subscription.id,
                event_id=envelope.event_id,
                event_type=envelope.event_type,
                delivery_id=f'whd_{envelope.event_id[4:]}_{subscription.id}',
                endpoint=subscription.endpoint,
                payload=self.build_payload(envelope, subscription),
                status='pending',
                max_attempts=subscription.max_attempts or 6,
                next_attempt_at=datetime.now(timezone.utc),
            )
            db.session.add(delivery)
            queued += 1

        try:
            db.session.commit()
        except IntegrityError:
            # Unique (subscription, event) — already queued by another worker.
            db.session.rollback()
            return {'queued': 0, 'status': 'duplicate'}
        except Exception as exc:
            db.session.rollback()
            raise RetryableConsumerError(f'Failed to queue webhooks: {exc}') from exc

        return {'queued': queued}

    @staticmethod
    def build_payload(envelope: EventEnvelope, subscription: EventSubscription) -> Dict[str, Any]:
        """Stable public contract — never leak internal metadata to partners."""
        return {
            'event': envelope.event_type,
            'version': envelope.event_version,
            'event_id': envelope.event_id,
            'timestamp': envelope.occurred_at.isoformat()
            if envelope.occurred_at else None,
            'correlation_id': envelope.correlation_id,
            'data': envelope.payload or {},
        }

    @staticmethod
    def sign(secret: str, body: str, timestamp: str) -> str:
        """
        HMAC-SHA256 over ``{timestamp}.{body}``.

        Including the timestamp in the signed material is what prevents replay
        attacks — a captured request cannot be resent later with a fresh clock.
        """
        message = f'{timestamp}.{body}'.encode()
        return hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()


# ----------------------------------------------------------------------
# Registry / dispatcher
# ----------------------------------------------------------------------
class ConsumerRegistry:
    """Holds the active consumers and dispatches one event to all of them."""

    def __init__(self):
        self._consumers: Dict[str, BaseConsumer] = {}

    def register(self, consumer: BaseConsumer) -> BaseConsumer:
        self._consumers[consumer.name] = consumer
        return consumer

    def get(self, name: str) -> Optional[BaseConsumer]:
        return self._consumers.get(name)

    def all(self) -> List[BaseConsumer]:
        return list(self._consumers.values())

    def names(self) -> List[str]:
        return list(self._consumers)

    def dispatch(
        self,
        envelope: EventEnvelope,
        only: Optional[Sequence[str]] = None,
    ) -> Dict[str, Any]:
        """
        Run every consumer against *envelope*.

        Consumers are isolated: one raising does not prevent the others from
        running. The aggregate outcome updates the ledger row so the admin view
        can distinguish fully processed from partially processed events.
        """
        targets = (
            [c for c in self.all() if c.name in set(only)]
            if only else self.all()
        )

        results = []
        for consumer in targets:
            try:
                results.append(consumer.handle(envelope))
            except Exception as exc:  # pragma: no cover - defensive
                logger.error('Consumer %s crashed on %s: %s',
                             consumer.name, envelope.event_id, exc, exc_info=True)
                results.append({'consumer': consumer.name, 'status': 'error',
                                'error': str(exc)})

        self._update_ledger(envelope, results)
        return {'event_id': envelope.event_id,
                'event_type': envelope.event_type,
                'results': results}

    @staticmethod
    def _update_ledger(envelope: EventEnvelope, results: List[Dict[str, Any]]) -> None:
        try:
            ledger = DomainEvent.query.filter_by(event_id=envelope.event_id).first()
            if ledger is None:
                return
            statuses = {r.get('status') for r in results}
            if 'retry' in statuses or 'error' in statuses:
                ledger.status = EventStatus.PROCESSING.value
            elif 'dead_letter' in statuses:
                ledger.mark_partial()
            else:
                ledger.mark_processed()
            db.session.commit()
        except Exception as exc:
            db.session.rollback()
            logger.warning('Could not update ledger for %s: %s', envelope.event_id, exc)


consumer_registry = ConsumerRegistry()
consumer_registry.register(NotificationConsumer())
consumer_registry.register(AuditConsumer())
consumer_registry.register(AnalyticsConsumer())
consumer_registry.register(WebhookConsumer())
