"""
Celery tasks for the event backbone.

Two independent beat loops, deliberately decoupled so a slow consumer never
blocks publication and a dead partner never blocks notifications:

``events.relay_outbox``      outbox rows  -> Redis Streams        (every 10s)
``events.dispatch_webhooks`` queued deliveries -> partner endpoints (every 30s)

Stream consumption (``events.consume``) moved OUT of beat to a standalone
process: app/notifications/events/stream_consumer.py. See that module's
docstring for the reasoning. DO NOT REINTRODUCE events.consume as a beat task.

Plus maintenance: stale-message reclaim and ledger retention.
"""

from __future__ import annotations

import logging
import os
import socket
import time                       # NEW: heartbeat duration measurement
from datetime import datetime, timedelta, timezone

from celery import shared_task

from app.extensions import db

logger = logging.getLogger(__name__)

CONSUMER_GROUP = 'afcon360-consumers'


def _heartbeat(task_name: str, t0: float, status: str = "ok", **counters) -> None:
    """Machine-readable liveness line. Emitted on BOTH the success and
    the handled-error path, so absence of any heartbeat within 2x the
    schedule interval means the task did not run (not that it errored).

    Shape is load-bearing for alerting rules — do not change without
    updating the rules.
    """
    duration_ms = int((time.monotonic() - t0) * 1000)
    kv = " ".join(f"{k}={v}" for k, v in sorted(counters.items()))
    logger.info("[heartbeat] %s %s %dms %s", task_name, status, duration_ms, kv)


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
        has_context = bool(current_app)
    except Exception:
        has_context = False

    if has_context:
        # Already inside an app context: run once and let any exception
        # propagate to the caller unchanged. (A previous form wrapped
        # this call in try/except-with-fallback, which silently executed
        # raising tasks TWICE — once here, once under a fresh app —
        # duplicating heartbeats and side effects.)
        return fn()

    from app import create_app
    app = create_app()
    with app.app_context():
        return fn()


# ----------------------------------------------------------------------
@shared_task(name='events.relay_outbox', bind=True, max_retries=3)
def relay_outbox_task(self, limit: int = 200) -> dict:
    """Publish committed outbox rows to the event bus."""
    t0 = time.monotonic()
    def _run():
        from .outbox import OutboxRelay
        try:
            result = OutboxRelay().run_once(limit=limit)
            _heartbeat(
                "events.relay_outbox", t0,
                claimed=result.get("claimed", 0),
                published=result.get("published", 0),
                failed=result.get("failed", 0),
            )
            return result
        except Exception as exc:
            logger.error('Outbox relay task failed: %s', exc, exc_info=True)
            _heartbeat("events.relay_outbox", t0, status="error",
                       error=type(exc).__name__)
            return {'status': 'error', 'error': str(exc)}
    return _with_app(_run)


# events.consume moved to app/notifications/events/stream_consumer.py.
# Stream consumption is a long-poll loop, not a scheduled sweep. Running
# it from beat gave no backpressure and shared the worker pool with
# critical dispatch tasks. See that module's docstring.
# DO NOT REINTRODUCE THIS TASK.


# ----------------------------------------------------------------------
@shared_task(name='events.dispatch_webhooks', bind=True, max_retries=3)
def dispatch_webhooks_task(self, limit: int = 50) -> dict:
    """Deliver queued partner webhooks with signing + retry."""
    t0 = time.monotonic()
    def _run():
        from .webhooks import webhook_dispatcher
        try:
            result = webhook_dispatcher.run_once(limit=limit)
            _heartbeat(
                "events.dispatch_webhooks", t0,
                attempted=result.get("attempted", 0),
                delivered=result.get("delivered", 0),
                failed=result.get("failed", 0),
            )
            return result
        except Exception as exc:
            logger.error('Webhook dispatch task failed: %s', exc, exc_info=True)
            _heartbeat("events.dispatch_webhooks", t0, status="error",
                       error=type(exc).__name__)
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
    t0 = time.monotonic()
    def _run():
        from .models import OutboxEvent, OutboxStatus
        from .outbox import OutboxRelay

        try:
            rows = (
                OutboxEvent.query
                .filter_by(status=OutboxStatus.DEAD_LETTER.value)
                .filter(~OutboxEvent.last_error.ilike('%Malformed envelope%'))
                .limit(limit)
                .all()
            )
            relay = OutboxRelay()
            requeued = sum(1 for row in rows if relay.requeue(row.event_id))
            result = {'requeued': requeued, 'examined': len(rows)}
            _heartbeat("events.retry_dead_letters", t0, **result)
            return result
        except Exception as exc:
            _heartbeat("events.retry_dead_letters", t0, status="error",
                       error=type(exc).__name__)
            raise

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
    t0 = time.monotonic()
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
            _heartbeat("events.cleanup_ledger", t0, status="error",
                       error=type(exc).__name__)
            return {'status': 'error', 'error': str(exc)}

        logger.info('Ledger cleanup: %s', removed)
        _heartbeat("events.cleanup_ledger", t0, **removed)
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
    t0 = time.monotonic()
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

        try:
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
            _heartbeat("events.health_snapshot", t0,
                       bus_available=snapshot.get("bus_available"))
            return snapshot
        except Exception as exc:
            _heartbeat("events.health_snapshot", t0, status="error",
                       error=type(exc).__name__)
            raise

    return _with_app(_run)
