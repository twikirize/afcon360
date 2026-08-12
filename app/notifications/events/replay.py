"""
Event replay.

The scenario the spec describes: the analytics consumer was down for two hours.
With a durable ledger you can re-feed those events to *that consumer only* —
crucially **without** re-sending user emails.

That safety comes from two mechanisms working together:

1. **Targeted replay** — ``only=['analytics']`` dispatches to a single consumer.
2. **Idempotency** — ``processed_events`` rows already exist for consumers that
   succeeded, so even a broad replay is a no-op for them.

``reset_consumer=True`` deliberately clears the idempotency rows for the target
consumer; that is the "I really do want this reprocessed" escape hatch and is
why it is opt-in rather than the default.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence

from app.extensions import db

from .consumers import consumer_registry
from .models import DomainEvent, EventStatus, ProcessedEvent
from .schemas import EventEnvelope

logger = logging.getLogger(__name__)


class EventReplayer:
    """Re-dispatch historical events from the durable ledger."""

    def __init__(self, registry=None):
        self.registry = registry or consumer_registry

    # ------------------------------------------------------------------
    def _query(
        self,
        event_types: Optional[Sequence[str]] = None,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
        correlation_id: Optional[str] = None,
        aggregate_type: Optional[str] = None,
        aggregate_id: Optional[str] = None,
        statuses: Optional[Sequence[str]] = None,
    ):
        query = DomainEvent.query
        if event_types:
            query = query.filter(DomainEvent.event_type.in_(list(event_types)))
        if since:
            query = query.filter(DomainEvent.occurred_at >= since)
        if until:
            query = query.filter(DomainEvent.occurred_at <= until)
        if correlation_id:
            query = query.filter(DomainEvent.correlation_id == correlation_id)
        if aggregate_type:
            query = query.filter(DomainEvent.aggregate_type == aggregate_type)
        if aggregate_id:
            query = query.filter(DomainEvent.aggregate_id == str(aggregate_id))
        if statuses:
            query = query.filter(DomainEvent.status.in_(list(statuses)))
        # Chronological order preserves causal sequence during replay.
        return query.order_by(DomainEvent.occurred_at.asc(), DomainEvent.id.asc())

    # ------------------------------------------------------------------
    def preview(self, limit: int = 100, **filters) -> List[DomainEvent]:
        """Inspect what a replay *would* touch before running it."""
        return self._query(**filters).limit(limit).all()

    def count(self, **filters) -> int:
        return self._query(**filters).count()

    # ------------------------------------------------------------------
    def replay(
        self,
        only: Optional[Sequence[str]] = None,
        limit: int = 500,
        reset_consumer: bool = False,
        dry_run: bool = False,
        **filters,
    ) -> Dict[str, Any]:
        """
        Re-dispatch matching events.

        Args:
            only: Restrict to these consumer names — the safe way to replay
                (e.g. ``['analytics']`` will not email anyone).
            reset_consumer: Delete existing ``processed_events`` rows for the
                targeted consumers first, forcing genuine reprocessing.
            dry_run: Report what would happen without dispatching.
        """
        events = self._query(**filters).limit(limit).all()
        if dry_run:
            return {
                'dry_run': True,
                'matched': len(events),
                'consumers': list(only) if only else self.registry.names(),
                'event_ids': [e.event_id for e in events[:50]],
            }

        if reset_consumer and only:
            self._reset(only, [e.event_id for e in events])

        dispatched = skipped = 0
        for event in events:
            try:
                envelope = EventEnvelope.from_model(event)
                result = self.registry.dispatch(envelope, only=only)
                statuses = {r.get('status') for r in result.get('results', [])}
                if statuses == {'duplicate'} or statuses == {'skipped'}:
                    skipped += 1
                else:
                    dispatched += 1
            except Exception as exc:
                logger.error('Replay failed for %s: %s', event.event_id, exc, exc_info=True)

        logger.info('Replay complete: matched=%s dispatched=%s skipped=%s consumers=%s',
                    len(events), dispatched, skipped, only or 'all')
        return {
            'matched': len(events),
            'dispatched': dispatched,
            'skipped': skipped,
            'consumers': list(only) if only else self.registry.names(),
        }

    # ------------------------------------------------------------------
    @staticmethod
    def _reset(consumers: Sequence[str], event_ids: Sequence[str]) -> int:
        """Clear idempotency rows so the targeted consumers reprocess."""
        if not event_ids:
            return 0
        try:
            deleted = (
                ProcessedEvent.query
                .filter(
                    ProcessedEvent.consumer.in_(list(consumers)),
                    ProcessedEvent.event_id.in_(list(event_ids)),
                )
                .delete(synchronize_session=False)
            )
            db.session.commit()
            logger.info('Reset %s processed-event rows for %s', deleted, list(consumers))
            return int(deleted or 0)
        except Exception as exc:
            db.session.rollback()
            logger.error('Failed to reset processed events: %s', exc)
            return 0

    # ------------------------------------------------------------------
    def replay_correlation(self, correlation_id: str, **kwargs) -> Dict[str, Any]:
        """Replay one complete user journey."""
        return self.replay(correlation_id=correlation_id, **kwargs)

    def replay_dead_letters(self, **kwargs) -> Dict[str, Any]:
        """Retry everything that previously dead-lettered."""
        return self.replay(statuses=[EventStatus.DEAD_LETTER.value], **kwargs)

    def trace(self, correlation_id: str) -> List[Dict[str, Any]]:
        """
        Reconstruct a full journey for incident forensics.

        Answers "show me everything that happened for transaction X" — the
        ordered chain of events plus their causal parents.
        """
        events = (
            DomainEvent.query
            .filter_by(correlation_id=correlation_id)
            .order_by(DomainEvent.occurred_at.asc())
            .all()
        )
        return [{
            'event_id': e.event_id,
            'event_type': e.event_type,
            'version': e.event_version,
            'aggregate': f'{e.aggregate_type}:{e.aggregate_id}'
            if e.aggregate_type else None,
            'actor': f'{e.actor_type}:{e.actor_id}' if e.actor_type else None,
            'causation_id': e.causation_id,
            'status': e.status,
            'occurred_at': e.occurred_at.isoformat() if e.occurred_at else None,
            'published_at': e.published_at.isoformat() if e.published_at else None,
            'processed_at': e.processed_at.isoformat() if e.processed_at else None,
        } for e in events]
