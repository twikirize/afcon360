"""
Outbox relay — moves committed outbox rows onto the event bus.

Runs as a Celery beat task (see ``app/notifications/events/tasks.py``). The
relay is the *only* component that publishes to Redis; producers never do,
which is precisely what makes publication crash-safe.

Reliability properties
----------------------
* **Row-level locking** (``SELECT ... FOR UPDATE SKIP LOCKED``) lets several
  relay workers run concurrently without publishing the same event twice.
  Falls back to an advisory claim on backends without ``SKIP LOCKED``.
* **Exponential backoff** via ``available_at`` — a Redis outage does not spin
  the relay hot; each failed attempt pushes the row further into the future.
* **Dead-lettering** after ``max_attempts`` so a permanently poisoned row stops
  consuming the retry budget and surfaces on the admin DLQ view.
* **At-least-once**, never at-most-once: a crash between ``XADD`` and the status
  update simply republishes, and consumer-side idempotency absorbs the duplicate.
"""

from __future__ import annotations

import logging
import os
import socket
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from sqlalchemy import or_
from sqlalchemy.exc import SQLAlchemyError

from app.extensions import db

from .bus import EventBus, event_bus
from .models import DomainEvent, EventStatus, OutboxEvent, OutboxStatus
from .schemas import EventEnvelope

logger = logging.getLogger(__name__)

# Backoff ladder in seconds, matching the spec's retry policy
# (10s -> 30s -> 2m -> 10m -> 1h), then capped.
BACKOFF_SCHEDULE = [10, 30, 120, 600, 3600]
MAX_BACKOFF = 3600
# A row locked longer than this is assumed orphaned by a dead worker.
STALE_LOCK_SECONDS = 300


def _worker_id() -> str:
    return f'{socket.gethostname()}:{os.getpid()}'


def _backoff_for(attempt: int) -> int:
    index = min(max(attempt - 1, 0), len(BACKOFF_SCHEDULE) - 1)
    return min(BACKOFF_SCHEDULE[index], MAX_BACKOFF)


class OutboxRelay:
    """Publishes pending outbox rows to the event bus."""

    def __init__(self, bus: Optional[EventBus] = None, batch_size: int = 100):
        self.bus = bus or event_bus
        self.batch_size = batch_size

    # ------------------------------------------------------------------
    def claim(self, limit: Optional[int] = None) -> List[OutboxEvent]:
        """
        Atomically claim a batch of due outbox rows.

        ``SKIP LOCKED`` is what allows horizontal scaling of the relay: each
        worker grabs a disjoint set of rows instead of blocking on the same head
        of the queue.
        """
        limit = limit or self.batch_size
        now = datetime.now(timezone.utc)
        stale_before = now - timedelta(seconds=STALE_LOCK_SECONDS)

        query = (
            OutboxEvent.query
            .filter(
                OutboxEvent.status.in_(
                    [OutboxStatus.PENDING.value, OutboxStatus.FAILED.value]
                ),
                OutboxEvent.available_at <= now,
                or_(
                    OutboxEvent.locked_at.is_(None),
                    OutboxEvent.locked_at < stale_before,
                ),
            )
            .order_by(OutboxEvent.available_at.asc(), OutboxEvent.id.asc())
            .limit(limit)
        )

        try:
            rows = query.with_for_update(skip_locked=True).all()
        except Exception:
            # SQLite / MySQL without SKIP LOCKED support.
            db.session.rollback()
            rows = query.all()

        worker = _worker_id()
        for row in rows:
            row.status = OutboxStatus.PUBLISHING.value
            row.locked_at = now
            row.locked_by = worker
        if rows:
            db.session.commit()
        return rows

    # ------------------------------------------------------------------
    def publish_row(self, row: OutboxEvent) -> bool:
        """Publish one row; returns True on success."""
        try:
            envelope = EventEnvelope.from_dict(row.envelope or {})
        except Exception as exc:
            # Unparseable payload will never succeed — dead-letter immediately.
            self._dead_letter(row, f'Malformed envelope: {exc}')
            return False

        try:
            self.bus.publish(envelope)
        except Exception as exc:
            self._fail(row, str(exc))
            return False

        now = datetime.now(timezone.utc)
        row.status = OutboxStatus.PUBLISHED.value
        row.published_at = now
        row.locked_at = None
        row.locked_by = None
        row.last_error = None

        ledger = DomainEvent.query.filter_by(event_id=row.event_id).first()
        if ledger is not None:
            ledger.mark_published()
        return True

    # ------------------------------------------------------------------
    def _fail(self, row: OutboxEvent, error: str) -> None:
        row.attempts = (row.attempts or 0) + 1
        row.last_error = error[:2000]
        row.locked_at = None
        row.locked_by = None

        if row.attempts >= (row.max_attempts or 8):
            self._dead_letter(row, error)
            return

        delay = _backoff_for(row.attempts)
        row.status = OutboxStatus.FAILED.value
        row.available_at = datetime.now(timezone.utc) + timedelta(seconds=delay)
        logger.warning(
            "Outbox %s publish failed (attempt %s/%s), retrying in %ss: %s",
            row.event_id, row.attempts, row.max_attempts, delay, error,
        )

    def _dead_letter(self, row: OutboxEvent, error: str) -> None:
        row.status = OutboxStatus.DEAD_LETTER.value
        row.last_error = error[:2000]
        row.locked_at = None
        row.locked_by = None
        ledger = DomainEvent.query.filter_by(event_id=row.event_id).first()
        if ledger is not None:
            ledger.mark_dead_letter()
        logger.error("Outbox %s dead-lettered after %s attempts: %s",
                     row.event_id, row.attempts, error)

    # ------------------------------------------------------------------
    def run_once(self, limit: Optional[int] = None) -> dict:
        """
        Process one batch. Returns counters for monitoring.

        Safe to call from beat every few seconds; it is a no-op when the outbox
        is empty.
        """
        if not self.bus.available():
            logger.debug('Event bus unavailable; outbox relay deferring batch')
            return {'claimed': 0, 'published': 0, 'failed': 0, 'skipped': 'bus_unavailable'}

        rows = self.claim(limit)
        if not rows:
            return {'claimed': 0, 'published': 0, 'failed': 0}

        published = failed = 0
        for row in rows:
            if self.publish_row(row):
                published += 1
            else:
                failed += 1

        try:
            db.session.commit()
        except SQLAlchemyError as exc:
            db.session.rollback()
            logger.error('Outbox relay commit failed: %s', exc, exc_info=True)
            return {'claimed': len(rows), 'published': 0, 'failed': len(rows),
                    'error': str(exc)}

        logger.info('Outbox relay: claimed=%s published=%s failed=%s',
                    len(rows), published, failed)
        return {'claimed': len(rows), 'published': published, 'failed': failed}

    # ------------------------------------------------------------------
    def dead_letters(self, limit: int = 100) -> List[OutboxEvent]:
        """Rows needing manual inspection (admin DLQ view)."""
        return (
            OutboxEvent.query
            .filter_by(status=OutboxStatus.DEAD_LETTER.value)
            .order_by(OutboxEvent.updated_at.desc())
            .limit(limit)
            .all()
        )

    def requeue(self, event_id: str) -> bool:
        """Return a dead-lettered row to the queue after the cause is fixed."""
        row = OutboxEvent.query.filter_by(event_id=event_id).first()
        if row is None:
            return False
        row.status = OutboxStatus.PENDING.value
        row.attempts = 0
        row.last_error = None
        row.locked_at = None
        row.locked_by = None
        row.available_at = datetime.now(timezone.utc)
        db.session.commit()
        logger.info('Outbox %s requeued for publication', event_id)
        return True

    def stats(self) -> dict:
        """Counts per status for the observability dashboard."""
        from sqlalchemy import func

        rows = (
            db.session.query(OutboxEvent.status, func.count(OutboxEvent.id))
            .group_by(OutboxEvent.status)
            .all()
        )
        return {status: int(count) for status, count in rows}
