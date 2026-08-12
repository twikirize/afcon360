"""
Event publishing — the API domain services actually call.

The golden rule this module enforces
------------------------------------
    Business domains publish FACTS. They do not orchestrate communication.

So a payment service does this::

    payment.status = 'successful'
    emit_event(EventType.PAYMENT_SUCCESSFUL,
               payload={'user_id': u.id, 'amount': 150000, 'currency': 'UGX'},
               aggregate_type='payment', aggregate_id=payment.public_id)
    db.session.commit()

…and stops. It does not know that a receipt email, a wallet-admin alert, an
audit record and an analytics point all follow.

Transactional outbox
--------------------
``emit_event`` does NOT talk to Redis. It writes two rows — the ledger row
(``domain_events``) and the outbox row (``outbox_events``) — using the caller's
existing session, WITHOUT committing. They therefore commit atomically with the
business change:

    BEGIN
      UPDATE payments SET status='successful'
      INSERT INTO domain_events  (...)
      INSERT INTO outbox_events  (...)
    COMMIT

If the transaction rolls back, no phantom event is announced. If the process
dies right after COMMIT, the outbox row survives and the relay publishes it on
the next tick. This closes the dual-write race described in the spec.

Use :func:`publish_event` only for fire-and-forget events that are not tied to a
business transaction (e.g. a heartbeat), since it commits on your behalf.
"""

from __future__ import annotations

import logging
import os
import socket
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from app.extensions import db

from .context import get_causation_id, get_correlation_id, new_event_id
from .models import DomainEvent, EventStatus, OutboxEvent, OutboxStatus
from .registry import event_registry
from .schemas import EventEnvelope, EventMeta

logger = logging.getLogger(__name__)


def _build_metadata(extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Capture ambient diagnostic context (env, host, request, client IP)."""
    meta = EventMeta(
        source='afcon360',
        environment=os.environ.get('FLASK_ENV') or os.environ.get('APP_ENV'),
        hostname=socket.gethostname(),
        extra=dict(extra or {}),
    )
    try:
        from flask import has_request_context, request

        if has_request_context():
            meta.request_id = request.headers.get('X-Request-Id')
            meta.ip_address = request.headers.get(
                'X-Forwarded-For', request.remote_addr
            )
            meta.user_agent = request.headers.get('User-Agent')
    except Exception:
        pass
    return meta.to_dict()


def _resolve_actor(
    actor_type: Optional[str], actor_id: Optional[Any]
) -> tuple[Optional[str], Optional[str]]:
    """Default the actor to the authenticated user when not supplied."""
    if actor_type or actor_id is not None:
        return actor_type, (str(actor_id) if actor_id is not None else None)
    try:
        from flask_login import current_user

        if getattr(current_user, 'is_authenticated', False):
            return 'user', str(current_user.id)
    except Exception:
        pass
    return 'system', None


class EventPublisher:
    """Builds envelopes and stages them into the ledger + outbox."""

    @staticmethod
    def build_envelope(
        event_type: str,
        payload: Optional[Dict[str, Any]] = None,
        *,
        aggregate_type: Optional[str] = None,
        aggregate_id: Optional[Any] = None,
        actor_type: Optional[str] = None,
        actor_id: Optional[Any] = None,
        correlation_id: Optional[str] = None,
        causation_id: Optional[str] = None,
        event_version: int = 1,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> EventEnvelope:
        payload = dict(payload or {})

        # Validate against the registered contract; also resolves the version.
        version = event_registry.validate(event_type, payload, event_version)

        definition = event_registry.get(event_type)
        resolved_actor_type, resolved_actor_id = _resolve_actor(actor_type, actor_id)

        return EventEnvelope(
            event_id=new_event_id(),
            event_type=event_type,
            event_version=version,
            payload=payload,
            aggregate_type=aggregate_type or (definition.aggregate_type if definition else None),
            aggregate_id=str(aggregate_id) if aggregate_id is not None else None,
            actor_type=resolved_actor_type,
            actor_id=resolved_actor_id,
            # Inherit the ambient trace so a whole journey shares one id.
            correlation_id=correlation_id or get_correlation_id(),
            causation_id=causation_id or get_causation_id(),
            occurred_at=datetime.now(timezone.utc),
            metadata=_build_metadata(metadata),
        )

    @staticmethod
    def stage(envelope: EventEnvelope, session=None) -> DomainEvent:
        """
        Write the ledger + outbox rows on *session* WITHOUT committing.

        Uses ``flush()`` (not ``commit()``) so the rows join the caller's
        transaction. This is the heart of the outbox pattern.
        """
        session = session or db.session

        ledger_row = DomainEvent(
            event_id=envelope.event_id,
            event_type=envelope.event_type,
            event_version=envelope.event_version,
            aggregate_type=envelope.aggregate_type,
            aggregate_id=envelope.aggregate_id,
            actor_type=envelope.actor_type,
            actor_id=envelope.actor_id,
            correlation_id=envelope.correlation_id,
            causation_id=envelope.causation_id,
            payload=envelope.payload,
            event_metadata=envelope.metadata,
            occurred_at=envelope.occurred_at,
            status=EventStatus.PENDING.value,
        )
        outbox_row = OutboxEvent(
            event_id=envelope.event_id,
            event_type=envelope.event_type,
            event_version=envelope.event_version,
            envelope=envelope.to_dict(),
            status=OutboxStatus.PENDING.value,
            available_at=datetime.now(timezone.utc),
        )

        session.add(ledger_row)
        session.add(outbox_row)
        session.flush()
        return ledger_row


def emit_event(
    event_type: str,
    payload: Optional[Dict[str, Any]] = None,
    *,
    aggregate_type: Optional[str] = None,
    aggregate_id: Optional[Any] = None,
    actor_type: Optional[str] = None,
    actor_id: Optional[Any] = None,
    correlation_id: Optional[str] = None,
    causation_id: Optional[str] = None,
    event_version: int = 1,
    metadata: Optional[Dict[str, Any]] = None,
    session=None,
) -> Optional[EventEnvelope]:
    """
    Record a domain event inside the caller's transaction (transactional outbox).

    **Does not commit.** Call this immediately before your own
    ``db.session.commit()`` so the event and the business change are atomic::

        booking.status = 'confirmed'
        emit_event(
            EventType.BOOKING_CONFIRMED,
            payload={'user_id': booking.user_id,
                     'booking_reference': booking.booking_reference,
                     'module': 'accommodation'},
            aggregate_type='booking',
            aggregate_id=booking.booking_reference,
        )
        db.session.commit()

    Returns the staged envelope, or ``None`` if staging failed (never raises
    into business code — a telemetry failure must not roll back a real booking).
    """
    try:
        envelope = EventPublisher.build_envelope(
            event_type,
            payload,
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            actor_type=actor_type,
            actor_id=actor_id,
            correlation_id=correlation_id,
            causation_id=causation_id,
            event_version=event_version,
            metadata=metadata,
        )
        EventPublisher.stage(envelope, session=session)
        logger.debug(
            "Staged event %s (%s) corr=%s",
            envelope.event_id, envelope.event_type, envelope.correlation_id,
        )
        return envelope
    except Exception as exc:
        # Never let event plumbing break the business operation.
        logger.error("Failed to stage event '%s': %s", event_type, exc, exc_info=True)
        return None


def publish_event(
    event_type: str,
    payload: Optional[Dict[str, Any]] = None,
    **kwargs,
) -> Optional[EventEnvelope]:
    """
    Emit an event AND commit immediately.

    Convenience wrapper for callers with no surrounding business transaction
    (schedulers, CLI tools, heartbeats). Prefer :func:`emit_event` inside
    request/service code so atomicity is preserved.
    """
    session = kwargs.pop('session', None) or db.session
    envelope = emit_event(event_type, payload, session=session, **kwargs)
    if envelope is None:
        return None
    try:
        session.commit()
    except Exception as exc:
        session.rollback()
        logger.error("Failed to commit event '%s': %s", event_type, exc, exc_info=True)
        return None
    return envelope
