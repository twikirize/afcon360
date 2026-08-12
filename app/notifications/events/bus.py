"""
Durable event bus backed by Redis Streams.

Why Redis Streams and not Kafka? The spec is explicit: PostgreSQL + Redis +
Celery are already in the stack, and Streams give the three properties that
matter at this stage — durability, consumer groups, and replay — without adding
new infrastructure. The :class:`EventBus` interface is intentionally narrow so
swapping in Kafka later is a single-file change.

Design
------
* One stream per top-level namespace (``afcon360:events:payment``) plus a
  firehose stream (``afcon360:events:all``) that every consumer group can read.
  Namespacing keeps a bulk analytics replay from competing with payment alerts.
* Consumer groups give at-least-once delivery with explicit ``XACK``, so a
  consumer that crashes mid-handler will see the message again.
* ``MAXLEN ~`` trimming bounds memory; the durable ledger is PostgreSQL
  (``domain_events``), not Redis, so trimming never loses history.
* Every operation degrades gracefully: if Redis is unavailable the event is
  still safely recorded in the outbox and the relay retries later.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Iterable, List, Optional, Tuple

from .exceptions import PublishError
from .schemas import EventEnvelope

logger = logging.getLogger(__name__)

STREAM_PREFIX = 'afcon360:events'
FIREHOSE_STREAM = f'{STREAM_PREFIX}:all'
DEFAULT_MAXLEN = 100_000


def stream_for(event_type: str) -> str:
    """
    Map an event type to its namespaced stream.

    ``payment.successful`` -> ``afcon360:events:payment``
    """
    namespace = (event_type or 'unknown').split('.', 1)[0]
    return f'{STREAM_PREFIX}:{namespace}'


class EventBus:
    """Thin, dependency-injected wrapper over Redis Streams."""

    def __init__(self, maxlen: int = DEFAULT_MAXLEN):
        self.maxlen = maxlen

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------
    @property
    def client(self):
        """
        Resolve the shared lazy Redis client.

        Returns ``None`` when Redis is not configured/reachable so callers can
        fall back to outbox-only mode instead of raising.
        """
        try:
            from app.extensions import redis_client
            return redis_client
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Redis client unavailable: %s", exc)
            return None

    def available(self) -> bool:
        try:
            client = self.client
            if client is None:
                return False
            client.ping()
            return True
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Producing
    # ------------------------------------------------------------------
    def publish(self, envelope: EventEnvelope) -> Optional[str]:
        """
        Append *envelope* to its namespaced stream and the firehose.

        Returns the Redis message id, or raises :class:`PublishError` so the
        outbox relay can retry with backoff.
        """
        client = self.client
        if client is None:
            raise PublishError('Redis is not configured; cannot publish event')

        fields = {'data': envelope.to_json(), 'event_type': envelope.event_type}
        try:
            message_id = client.xadd(
                stream_for(envelope.event_type),
                fields,
                maxlen=self.maxlen,
                approximate=True,
            )
            client.xadd(
                FIREHOSE_STREAM, fields, maxlen=self.maxlen, approximate=True
            )
            return message_id.decode() if isinstance(message_id, bytes) else str(message_id)
        except Exception as exc:
            raise PublishError(f'Failed to publish {envelope.event_id}: {exc}') from exc

    # ------------------------------------------------------------------
    # Consuming
    # ------------------------------------------------------------------
    def ensure_group(self, stream: str, group: str) -> bool:
        """Create the consumer group if absent (idempotent)."""
        client = self.client
        if client is None:
            return False
        try:
            client.xgroup_create(stream, group, id='0', mkstream=True)
            logger.info("Created consumer group '%s' on '%s'", group, stream)
        except Exception as exc:
            # BUSYGROUP simply means it already exists.
            if 'BUSYGROUP' not in str(exc):
                logger.warning("Could not create group '%s' on '%s': %s", group, stream, exc)
                return False
        return True

    def read(
        self,
        group: str,
        consumer: str,
        stream: str = FIREHOSE_STREAM,
        count: int = 32,
        block_ms: int = 5000,
    ) -> List[Tuple[str, EventEnvelope]]:
        """
        Read a batch of undelivered messages for *group*.

        Returns a list of ``(message_id, envelope)``. Messages remain pending
        until :meth:`ack` is called, which is what makes redelivery — and thus
        at-least-once processing — possible after a crash.
        """
        client = self.client
        if client is None:
            return []

        self.ensure_group(stream, group)
        try:
            response = client.xreadgroup(
                group, consumer, {stream: '>'}, count=count, block=block_ms
            )
        except Exception as exc:
            logger.warning("xreadgroup failed on '%s': %s", stream, exc)
            return []

        return list(self._decode(response))

    def claim_stale(
        self,
        group: str,
        consumer: str,
        stream: str = FIREHOSE_STREAM,
        min_idle_ms: int = 300_000,
        count: int = 32,
    ) -> List[Tuple[str, EventEnvelope]]:
        """
        Reclaim messages a dead consumer left pending.

        Without this, a worker that dies holding messages would strand them in
        the pending-entries list forever.
        """
        client = self.client
        if client is None:
            return []
        try:
            result = client.xautoclaim(
                stream, group, consumer, min_idle_time=min_idle_ms, count=count
            )
        except Exception as exc:
            logger.debug("xautoclaim unavailable/failed on '%s': %s", stream, exc)
            return []

        # xautoclaim returns (next_cursor, messages[, deleted]) across versions.
        messages = result[1] if isinstance(result, (list, tuple)) and len(result) > 1 else []
        decoded: List[Tuple[str, EventEnvelope]] = []
        for message_id, fields in messages or []:
            envelope = self._decode_fields(fields)
            if envelope is not None:
                decoded.append((self._as_str(message_id), envelope))
        return decoded

    def ack(self, group: str, message_id: str, stream: str = FIREHOSE_STREAM) -> None:
        """Acknowledge successful processing so the message is not redelivered."""
        client = self.client
        if client is None:
            return
        try:
            client.xack(stream, group, message_id)
        except Exception as exc:
            logger.warning("xack failed for %s on %s: %s", message_id, stream, exc)

    def pending_count(self, group: str, stream: str = FIREHOSE_STREAM) -> int:
        """Queue-depth metric for the observability dashboard."""
        client = self.client
        if client is None:
            return 0
        try:
            summary = client.xpending(stream, group)
            if isinstance(summary, dict):
                return int(summary.get('pending', 0))
            return int(summary[0]) if summary else 0
        except Exception:
            return 0

    def stream_length(self, stream: str = FIREHOSE_STREAM) -> int:
        client = self.client
        if client is None:
            return 0
        try:
            return int(client.xlen(stream))
        except Exception:
            return 0

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _as_str(value: Any) -> str:
        return value.decode() if isinstance(value, bytes) else str(value)

    @classmethod
    def _decode_fields(cls, fields: Dict[Any, Any]) -> Optional[EventEnvelope]:
        try:
            normalised = {cls._as_str(k): cls._as_str(v) for k, v in (fields or {}).items()}
            raw = normalised.get('data')
            if not raw:
                return None
            return EventEnvelope.from_json(raw)
        except Exception as exc:
            logger.error("Failed to decode event message: %s", exc)
            return None

    @classmethod
    def _decode(cls, response: Iterable) -> Iterable[Tuple[str, EventEnvelope]]:
        for _stream, messages in response or []:
            for message_id, fields in messages:
                envelope = cls._decode_fields(fields)
                if envelope is not None:
                    yield cls._as_str(message_id), envelope


event_bus = EventBus()
