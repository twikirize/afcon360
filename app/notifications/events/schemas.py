"""
Canonical event envelope.

Every event that crosses a boundary — outbox row, Redis Streams message,
partner webhook — uses this exact shape. Having one serialization format means
a consumer written today can still read an event replayed from the ledger in
two years.

Wire format::

    {
      "event_id":       "evt_8c71...",
      "event_type":     "payment.successful",
      "event_version":  1,
      "aggregate_type": "payment",
      "aggregate_id":   "pay_123",
      "actor_type":     "user",
      "actor_id":       "456",
      "correlation_id": "cor_789",
      "causation_id":   "evt_previous",
      "occurred_at":    "2026-08-08T01:11:10+00:00",
      "payload":        {...},
      "metadata":       {...}
    }
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from .context import new_event_id


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: Optional[datetime]) -> Optional[str]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


def _parse_dt(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    return _utcnow()


@dataclass
class EventMeta:
    """Transport/diagnostic metadata that is not part of the business payload."""
    source: str = 'afcon360'
    environment: Optional[str] = None
    hostname: Optional[str] = None
    request_id: Optional[str] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    extra: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        extra = data.pop('extra', {}) or {}
        data.update(extra)
        return {k: v for k, v in data.items() if v is not None}

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> 'EventMeta':
        data = dict(data or {})
        known = {'source', 'environment', 'hostname', 'request_id', 'ip_address', 'user_agent'}
        return cls(
            source=data.pop('source', 'afcon360'),
            environment=data.pop('environment', None),
            hostname=data.pop('hostname', None),
            request_id=data.pop('request_id', None),
            ip_address=data.pop('ip_address', None),
            user_agent=data.pop('user_agent', None),
            extra={k: v for k, v in data.items() if k not in known},
        )


@dataclass
class EventEnvelope:
    """
    Immutable, serializable representation of a domain event.

    Deliberately a plain dataclass (not a SQLAlchemy object) so it can be
    handed to Celery, Redis or an HTTP client without dragging a DB session
    around, and so consumers can be unit-tested with no database at all.
    """

    event_type: str
    payload: Dict[str, Any] = field(default_factory=dict)
    event_id: str = field(default_factory=new_event_id)
    event_version: int = 1
    aggregate_type: Optional[str] = None
    aggregate_id: Optional[str] = None
    actor_type: Optional[str] = None
    actor_id: Optional[str] = None
    correlation_id: Optional[str] = None
    causation_id: Optional[str] = None
    occurred_at: datetime = field(default_factory=_utcnow)
    metadata: Dict[str, Any] = field(default_factory=dict)

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------
    def to_dict(self) -> Dict[str, Any]:
        return {
            'event_id': self.event_id,
            'event_type': self.event_type,
            'event_version': self.event_version,
            'aggregate_type': self.aggregate_type,
            'aggregate_id': self.aggregate_id,
            'actor_type': self.actor_type,
            'actor_id': self.actor_id,
            'correlation_id': self.correlation_id,
            'causation_id': self.causation_id,
            'occurred_at': _iso(self.occurred_at),
            'payload': self.payload or {},
            'metadata': self.metadata or {},
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), default=str, separators=(',', ':'))

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'EventEnvelope':
        return cls(
            event_id=data.get('event_id') or new_event_id(),
            event_type=data['event_type'],
            event_version=int(data.get('event_version', 1)),
            aggregate_type=data.get('aggregate_type'),
            aggregate_id=data.get('aggregate_id'),
            actor_type=data.get('actor_type'),
            actor_id=data.get('actor_id'),
            correlation_id=data.get('correlation_id'),
            causation_id=data.get('causation_id'),
            occurred_at=_parse_dt(data.get('occurred_at')),
            payload=data.get('payload') or {},
            metadata=data.get('metadata') or {},
        )

    @classmethod
    def from_json(cls, raw: str) -> 'EventEnvelope':
        return cls.from_dict(json.loads(raw))

    @classmethod
    def from_model(cls, event) -> 'EventEnvelope':
        """Build an envelope from a :class:`DomainEvent` row."""
        return cls(
            event_id=event.event_id,
            event_type=event.event_type,
            event_version=event.event_version or 1,
            aggregate_type=event.aggregate_type,
            aggregate_id=event.aggregate_id,
            actor_type=event.actor_type,
            actor_id=event.actor_id,
            correlation_id=event.correlation_id,
            causation_id=event.causation_id,
            occurred_at=event.occurred_at or _utcnow(),
            payload=event.payload or {},
            metadata=event.event_metadata or {},
        )

    # ------------------------------------------------------------------
    # Convenience
    # ------------------------------------------------------------------
    def get(self, key: str, default: Any = None) -> Any:
        """Read a key from the payload."""
        return (self.payload or {}).get(key, default)

    @property
    def user_id(self) -> Optional[int]:
        """
        Best-effort recipient resolution.

        Most events concern a user; this looks in the usual places so consumers
        don't each reimplement the lookup.
        """
        for key in ('user_id', 'recipient_id', 'owner_id', 'customer_id'):
            value = (self.payload or {}).get(key)
            if value is not None:
                try:
                    return int(value)
                except (TypeError, ValueError):
                    continue
        if self.actor_type == 'user' and self.actor_id:
            try:
                return int(self.actor_id)
            except (TypeError, ValueError):
                return None
        return None

    def child(self, event_type: str, payload: Dict[str, Any] = None, **kwargs) -> 'EventEnvelope':
        """
        Derive a causally-linked child event.

        The child inherits the correlation id and records this event as its
        cause, producing the payment.successful -> booking.confirmed ->
        notification.created chain used for incident forensics.
        """
        return EventEnvelope(
            event_type=event_type,
            payload=payload or {},
            correlation_id=self.correlation_id,
            causation_id=self.event_id,
            **kwargs,
        )

    def __repr__(self) -> str:
        return (
            f'<EventEnvelope {self.event_id} {self.event_type}'
            f' v{self.event_version} corr={self.correlation_id}>'
        )
