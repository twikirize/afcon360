"""
Celery tasks for the event backbone.

Three independent loops, deliberately decoupled so a slow consumer never blocks
publication and a dead partner never blocks notifications:

``events.relay_outbox``      outbox rows  -> Redis Streams        (every 10s)
``events.consume``           Redis Streams -> consumers            (every 15s)
``events.dispatch_webhooks`` queued deliveries -> partner endpoints (every 30s)

Plus maintenance: stale-message reclaim and ledger retention.

Register these in ``app/celery_app.py`` — see the README for the exact
``beat_schedule`` block and the ``include`` entry.
"""

from __future__ import annotations

import logging
import os
import socket
from datetime import datetime, timedelta, timezone

from celery import shared_task

from app.extensions import db

logger = logging.getLogger(__name__)

CONSUMER_GROUP = 'afcon360-consumers'


def _consumer_name() -> str:
    return f'{socket.gethostname()}-{os.getpid()}'


def _with_app(fn):
    """
    Run *fn* inside a Flask app context.

    Tasks may execute under a worker started without the ContextTask binding
    (e.g. `celery -A app.celery_app`), so we create one defensively.
    """
    try:
        from flask import current_app
        if current_app:
            return fn()
    except Exception:
        pass

    from app import create_app
    app = create_app()
    with app.app_context():
        return fn()


# ----------------------------------------------------------------------
@shared_task(name='events.relay_outbox', bind=True, max_retries=3)
def relay_outbox_task(self, limit: int = 200) -> dict:
    """Publish committed outbox rows to the event bus."""
    def _run():
        from .outbox import OutboxRelay
        try:
            return OutboxRelay().run_once(limit=limit)
        except Exception as exc:
            logger.error('Outbox relay task failed: %s', exc, exc_info=True)
            return {'status': 'error', 'error': str(exc)}
    return _with_app(_run)


# ----------------------------------------------------------------------
@shared_task(name='events.consume', bind=True, max_retries=3)
def consume_events_task(self, batch: int = 64, block_ms: int = 1000) -> dict:
    """
    Read a batch from the bus and dispatch to all consumers.

    Uses a short block so the task returns promptly for beat scheduling rather
    than holding a worker slot open.
    """
    def _run():
        from .bus import FIREHOSE_STREAM, event_bus
        from .consumers import consumer_registry

        if not event_bus.available():
            return {'status': 'bus_unavailable', 'processed': 0}

        consumer = _consumer_name()
        messages = event_bus.read(
            CONSUMER_GROUP, consumer, FIREHOSE_STREAM, count=batch, block_ms=block_ms
        )
        # Pick up anything a crashed worker left pending.
        messages += event_bus.claim_stale(CONSUMER_GROUP, consumer, FIREHOSE_STREAM)

        if not messages:
            return {'processed': 0}

        processed = retried = 0
        for message_id, envelope in messages:
            try:
                result = consumer_registry.dispatch(envelope)
                statuses = {r.get('status') for r in result.get('results', [])}
                if 'retry' in statuses:
                    # Leave unacked so Redis redelivers it.
                    retried += 1
                    continue
                event_bus.ack(CONSUMER_GROUP, message_id, FIREHOSE_STREAM)
                processed += 1
            except Exception as exc:
                logger.error('Failed to dispatch message %s: %s', message_id, exc,
                             exc_info=True)

        logger.info('Event consumer: processed=%s retried=%s', processed, retried)
        return {'processed': processed, 'retried': retried}

    return _with_app(_run)


# ----------------------------------------------------------------------
@shared_task(name='events.dispatch_webhooks', bind=True, max_retries=3)
def dispatch_webhooks_task(self, limit: int = 50) -> dict:
    """Deliver queued partner webhooks with signing + retry."""
    def _run():
        from .webhooks import webhook_dispatcher
        try:
            return webhook_dispatcher.run_once(limit=limit)
        except Exception as exc:
            logger.error('Webhook dispatch task failed: %s', exc, exc_info=True)
            return {'status': 'error', 'error': str(exc)}
    return _with_app(_run)


# ----------------------------------------------------------------------
@shared_task(name='events.retry_dead_letters')
def retry_dead_letters_task(limit: int = 50) -> dict:
    """
    Requeue outbox rows that dead-lettered because the bus was down.

    Only retries transport-level failures; malformed envelopes stay dead and
    require human intervention.
    """
    def _run():
        from .models import OutboxEvent, OutboxStatus
        from .outbox import OutboxRelay

        rows = (
            OutboxEvent.query
            .filter_by(status=OutboxStatus.DEAD_LETTER.value)
            .filter(~OutboxEvent.last_error.ilike('%Malformed envelope%'))
            .limit(limit)
            .all()
        )
        relay = OutboxRelay()
        requeued = sum(1 for row in rows if relay.requeue(row.event_id))
        return {'requeued': requeued, 'examined': len(rows)}

    return _with_app(_run)


# ----------------------------------------------------------------------
@shared_task(name='events.cleanup_ledger')
def cleanup_ledger_task(retention_days: int = 365, batch: int = 5000) -> dict:
    """
    Prune the event ledger past the compliance retention window.

    Defaults to 365 days. Processed outbox rows and idempotency markers are
    trimmed far more aggressively (30 days) since the ledger is the durable
    record — the outbox is only a staging queue.
    """
    def _run():
        from .models import DomainEvent, EventStatus, OutboxEvent, OutboxStatus, ProcessedEvent

        now = datetime.now(timezone.utc)
        ledger_cutoff = now - timedelta(days=retention_days)
        working_cutoff = now - timedelta(days=30)

        removed = {'events': 0, 'outbox': 0, 'processed': 0}
        try:
            removed['outbox'] = OutboxEvent.query.filter(
                OutboxEvent.status == OutboxStatus.PUBLISHED.value,
                OutboxEvent.published_at < working_cutoff,
            ).limit(batch).delete(synchronize_session=False) or 0

            removed['processed'] = ProcessedEvent.query.filter(
                ProcessedEvent.processed_at < working_cutoff,
            ).limit(batch).delete(synchronize_session=False) or 0

            removed['events'] = DomainEvent.query.filter(
                DomainEvent.occurred_at < ledger_cutoff,
                DomainEvent.status == EventStatus.PROCESSED.value,
            ).limit(batch).delete(synchronize_session=False) or 0

            db.session.commit()
        except Exception as exc:
            db.session.rollback()
            logger.error('Ledger cleanup failed: %s', exc, exc_info=True)
            return {'status': 'error', 'error': str(exc)}

        logger.info('Ledger cleanup: %s', removed)
        return removed

    return _with_app(_run)


# ----------------------------------------------------------------------
@shared_task(name='events.health_snapshot')
def health_snapshot_task() -> dict:
    """
    Point-in-time pipeline health for the admin dashboard.

    Surfaces queue depth, DLQ size and provider health in one call so the
    observability panel does not need six round trips.
    """
    def _run():
        from sqlalchemy import func

        from .bus import FIREHOSE_STREAM, event_bus
        from .models import DomainEvent, OutboxEvent, WebhookDelivery

        def _counts(model, column):
            try:
                return {
                    str(k): int(v) for k, v in
                    db.session.query(column, func.count(model.id))
                    .group_by(column).all()
                }
            except Exception:
                return {}

        snapshot = {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'bus_available': event_bus.available(),
            'stream_length': event_bus.stream_length(FIREHOSE_STREAM),
            'pending_messages': event_bus.pending_count(CONSUMER_GROUP, FIREHOSE_STREAM),
            'outbox': _counts(OutboxEvent, OutboxEvent.status),
            'events': _counts(DomainEvent, DomainEvent.status),
            'webhooks': _counts(WebhookDelivery, WebhookDelivery.status),
        }
        logger.info('event pipeline health: %s', snapshot)
        return snapshot

    return _with_app(_run)
