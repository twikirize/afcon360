"""
Outbound partner webhook dispatcher.

Separate from ``channel_handlers/webhook.py`` (which delivers a *notification*
to a URL). This module delivers *platform events* to registered external
subscribers, with the stronger reliability contract partners require.

Security headers sent with every request::

    X-AFCON360-Event-Id     evt_...      (idempotency key for the partner)
    X-AFCON360-Delivery-Id  whd_...      (this specific attempt chain)
    X-AFCON360-Event-Type   booking.confirmed
    X-AFCON360-Timestamp    1754...      (unix seconds, signed)
    X-AFCON360-Signature    sha256=...   (HMAC over "{timestamp}.{body}")

Partners verify by recomputing the HMAC with their shared secret and rejecting
timestamps outside their tolerance window, which defeats replay attacks.

A circuit breaker disables a subscription after sustained failure so one dead
partner endpoint cannot degrade the queue for everyone else.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from app.extensions import db

from .consumers import WebhookConsumer
from .models import EventSubscription, SubscriptionStatus, WebhookDelivery

logger = logging.getLogger(__name__)

# Same ladder as the outbox: 10s, 30s, 2m, 10m, 1h.
BACKOFF_SCHEDULE = [10, 30, 120, 600, 3600]
# Consecutive failures before a subscription is auto-paused.
CIRCUIT_BREAKER_THRESHOLD = 20


def _backoff_for(attempt: int) -> int:
    index = min(max(attempt - 1, 0), len(BACKOFF_SCHEDULE) - 1)
    return BACKOFF_SCHEDULE[index]


class WebhookDispatcher:
    """Delivers queued :class:`WebhookDelivery` rows to partner endpoints."""

    def __init__(self, batch_size: int = 50):
        self.batch_size = batch_size

    # ------------------------------------------------------------------
    def due(self, limit: Optional[int] = None) -> List[WebhookDelivery]:
        now = datetime.now(timezone.utc)
        return (
            WebhookDelivery.query
            .filter(
                WebhookDelivery.status.in_(['pending', 'retrying']),
                WebhookDelivery.next_attempt_at <= now,
            )
            .order_by(WebhookDelivery.next_attempt_at.asc())
            .limit(limit or self.batch_size)
            .all()
        )

    # ------------------------------------------------------------------
    def deliver(self, delivery: WebhookDelivery) -> bool:
        """Attempt one delivery; returns True on 2xx."""
        try:
            import requests
        except ImportError:
            logger.error('requests not installed; cannot dispatch webhooks')
            return False

        subscription = db.session.get(EventSubscription, delivery.subscription_id)
        if subscription is None:
            delivery.status = 'cancelled'
            delivery.last_error = 'Subscription no longer exists'
            return False

        body = json.dumps(delivery.payload or {}, default=str, separators=(',', ':'))
        timestamp = str(int(datetime.now(timezone.utc).timestamp()))

        headers = {
            'Content-Type': 'application/json',
            'User-Agent': 'AFCON360-Webhooks/1.0',
            'X-AFCON360-Event-Id': delivery.event_id,
            'X-AFCON360-Delivery-Id': delivery.delivery_id,
            'X-AFCON360-Event-Type': delivery.event_type,
            'X-AFCON360-Timestamp': timestamp,
        }
        if subscription.secret:
            signature = WebhookConsumer.sign(subscription.secret, body, timestamp)
            headers['X-AFCON360-Signature'] = f'sha256={signature}'

        delivery.attempts = (delivery.attempts or 0) + 1

        try:
            response = requests.post(
                delivery.endpoint,
                data=body,
                headers=headers,
                timeout=subscription.timeout_seconds or 10,
            )
            delivery.response_code = response.status_code
            delivery.response_body = (response.text or '')[:2000]

            if 200 <= response.status_code < 300:
                self._succeed(delivery, subscription)
                return True

            self._fail(delivery, subscription,
                       f'HTTP {response.status_code}: {delivery.response_body[:200]}')
            return False

        except Exception as exc:
            delivery.response_code = None
            self._fail(delivery, subscription, str(exc))
            return False

    # ------------------------------------------------------------------
    def _succeed(self, delivery: WebhookDelivery, subscription: EventSubscription) -> None:
        now = datetime.now(timezone.utc)
        delivery.status = 'delivered'
        delivery.delivered_at = now
        delivery.last_error = None
        delivery.next_attempt_at = None
        subscription.consecutive_failures = 0
        subscription.last_success_at = now

    def _fail(
        self,
        delivery: WebhookDelivery,
        subscription: EventSubscription,
        error: str,
    ) -> None:
        now = datetime.now(timezone.utc)
        delivery.last_error = error[:2000]
        subscription.last_failure_at = now
        subscription.consecutive_failures = (subscription.consecutive_failures or 0) + 1

        if delivery.attempts >= (delivery.max_attempts or 6):
            delivery.status = 'dead_letter'
            delivery.next_attempt_at = None
            logger.error('Webhook %s dead-lettered after %s attempts: %s',
                         delivery.delivery_id, delivery.attempts, error)
        else:
            delay = _backoff_for(delivery.attempts)
            delivery.status = 'retrying'
            delivery.next_attempt_at = now + timedelta(seconds=delay)
            logger.warning('Webhook %s failed (attempt %s), retrying in %ss: %s',
                           delivery.delivery_id, delivery.attempts, delay, error)

        # Circuit breaker: stop hammering a persistently dead endpoint.
        if subscription.consecutive_failures >= CIRCUIT_BREAKER_THRESHOLD:
            subscription.status = SubscriptionStatus.PAUSED.value
            logger.error(
                'Subscription %s auto-paused after %s consecutive failures',
                subscription.subscriber, subscription.consecutive_failures,
            )

    # ------------------------------------------------------------------
    def run_once(self, limit: Optional[int] = None) -> Dict[str, Any]:
        deliveries = self.due(limit)
        if not deliveries:
            return {'attempted': 0, 'delivered': 0, 'failed': 0}

        delivered = failed = 0
        for delivery in deliveries:
            if self.deliver(delivery):
                delivered += 1
            else:
                failed += 1

        try:
            db.session.commit()
        except Exception as exc:
            db.session.rollback()
            logger.error('Webhook dispatcher commit failed: %s', exc, exc_info=True)
            return {'attempted': len(deliveries), 'delivered': 0,
                    'failed': len(deliveries), 'error': str(exc)}

        return {'attempted': len(deliveries), 'delivered': delivered, 'failed': failed}

    # ------------------------------------------------------------------
    def replay(self, delivery_id: str) -> bool:
        """Requeue a dead-lettered delivery after the partner is fixed."""
        delivery = WebhookDelivery.query.filter_by(delivery_id=delivery_id).first()
        if delivery is None:
            return False
        delivery.status = 'pending'
        delivery.attempts = 0
        delivery.last_error = None
        delivery.next_attempt_at = datetime.now(timezone.utc)
        db.session.commit()
        return True


webhook_dispatcher = WebhookDispatcher()
