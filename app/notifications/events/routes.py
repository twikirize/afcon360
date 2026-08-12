"""
Admin & observability API for the platform event backbone.

Exposes the operational surface the spec asks for in section 21
("observability around the entire pipeline") and section 17 (event-level DLQ),
plus partner subscription management from section 13.

Mounted at ``/api/events`` and restricted to owner/super_admin/admin, since
these endpoints expose cross-tenant platform internals.

Route groups
------------
``/api/events/health``          pipeline health: queue depth, DLQ, provider state
``/api/events/registry``        the canonical event catalogue + policy map
``/api/events``                 browse/filter the durable event ledger
``/api/events/trace/<corr_id>`` reconstruct one full user journey
``/api/events/dead-letter``     event-level DLQ (distinct from notification DLQ)
``/api/events/replay``          targeted, idempotency-aware replay
``/api/events/subscriptions``   external partner webhook subscriptions
``/api/events/deliveries``      outbound webhook delivery history
"""

from __future__ import annotations

import logging
import secrets
from datetime import datetime, timedelta, timezone

from flask import Blueprint, jsonify, request
from flask_login import current_user, login_required
from sqlalchemy import func

from app.auth.decorators import require_role
from app.extensions import db

from .bus import FIREHOSE_STREAM, event_bus
from .consumers import consumer_registry
from .models import (
    DomainEvent,
    EventStatus,
    EventSubscription,
    OutboxEvent,
    OutboxStatus,
    ProcessedEvent,
    SubscriptionStatus,
    WebhookDelivery,
)
from .outbox import OutboxRelay
from .policy import policy_engine
from .registry import event_registry
from .replay import EventReplayer
from .tasks import CONSUMER_GROUP

logger = logging.getLogger(__name__)

events_api = Blueprint('events_api', __name__, url_prefix='/api/events')

ADMIN_ROLES = ('owner', 'super_admin', 'admin')


def _serialize_event(event: DomainEvent, include_payload: bool = False) -> dict:
    data = {
        'event_id': event.event_id,
        'event_type': event.event_type,
        'event_version': event.event_version,
        'aggregate_type': event.aggregate_type,
        'aggregate_id': event.aggregate_id,
        'actor_type': event.actor_type,
        'actor_id': event.actor_id,
        'correlation_id': event.correlation_id,
        'causation_id': event.causation_id,
        'status': event.status,
        'occurred_at': event.occurred_at.isoformat() if event.occurred_at else None,
        'published_at': event.published_at.isoformat() if event.published_at else None,
        'processed_at': event.processed_at.isoformat() if event.processed_at else None,
    }
    if include_payload:
        data['payload'] = event.payload
        data['metadata'] = event.event_metadata
    return data


def _counts(model, column) -> dict:
    try:
        return {
            str(k): int(v)
            for k, v in db.session.query(column, func.count(model.id)).group_by(column).all()
        }
    except Exception:
        return {}


# ----------------------------------------------------------------------
# Health / observability
# ----------------------------------------------------------------------
@events_api.route('/health', methods=['GET'])
@login_required
@require_role(*ADMIN_ROLES)
def pipeline_health():
    """
    End-to-end pipeline health for the admin dashboard.

    Answers, in one call: is the bus up, how deep is the queue, how many events
    are stuck, and how many partner deliveries are failing.
    """
    window = datetime.now(timezone.utc) - timedelta(hours=1)

    try:
        failed_last_hour = DomainEvent.query.filter(
            DomainEvent.status.in_([EventStatus.FAILED.value, EventStatus.DEAD_LETTER.value]),
            DomainEvent.created_at >= window,
        ).count()
    except Exception:
        failed_last_hour = 0

    return jsonify({
        'success': True,
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'bus': {
            'available': event_bus.available(),
            'stream': FIREHOSE_STREAM,
            'stream_length': event_bus.stream_length(FIREHOSE_STREAM),
            'pending_messages': event_bus.pending_count(CONSUMER_GROUP, FIREHOSE_STREAM),
        },
        'outbox': _counts(OutboxEvent, OutboxEvent.status),
        'events': _counts(DomainEvent, DomainEvent.status),
        'webhooks': _counts(WebhookDelivery, WebhookDelivery.status),
        'consumers': consumer_registry.names(),
        'failed_last_hour': failed_last_hour,
    })


@events_api.route('/registry', methods=['GET'])
@login_required
@require_role(*ADMIN_ROLES)
def registry_catalogue():
    """The canonical event catalogue and which notifications each event drives."""
    definitions = []
    for event_type, definition in sorted(event_registry.all().items()):
        policies = policy_engine.policies_for(event_type)
        definitions.append({
            'event_type': event_type,
            'version': definition.version,
            'description': definition.description,
            'aggregate_type': definition.aggregate_type,
            'required_fields': definition.required_fields,
            'audited': definition.audited,
            'externally_visible': definition.externally_visible,
            'notification_policies': [{
                'notification_type': p.notification_type,
                'audience': p.audience.value,
                'delivery_class': p.delivery_class.value,
                'channels': p.channels,
                'priority': p.priority,
                'roles': p.roles,
                'conditional': p.condition is not None,
            } for p in policies],
        })
    return jsonify({
        'success': True,
        'count': len(definitions),
        'events': definitions,
    })


# ----------------------------------------------------------------------
# Ledger browsing
# ----------------------------------------------------------------------
@events_api.route('', methods=['GET'])
@events_api.route('/', methods=['GET'])
@login_required
@require_role(*ADMIN_ROLES)
def list_events():
    """Browse the durable event ledger with filters."""
    limit = min(int(request.args.get('limit', 50)), 500)
    offset = int(request.args.get('offset', 0))

    query = DomainEvent.query
    if event_type := request.args.get('type'):
        query = query.filter(DomainEvent.event_type == event_type)
    if status := request.args.get('status'):
        query = query.filter(DomainEvent.status == status)
    if aggregate_type := request.args.get('aggregate_type'):
        query = query.filter(DomainEvent.aggregate_type == aggregate_type)
    if aggregate_id := request.args.get('aggregate_id'):
        query = query.filter(DomainEvent.aggregate_id == str(aggregate_id))
    if correlation_id := request.args.get('correlation_id'):
        query = query.filter(DomainEvent.correlation_id == correlation_id)

    total = query.count()
    events = (
        query.order_by(DomainEvent.occurred_at.desc())
        .offset(offset).limit(limit).all()
    )
    return jsonify({
        'success': True,
        'total': total,
        'limit': limit,
        'offset': offset,
        'events': [_serialize_event(e) for e in events],
    })


@events_api.route('/<event_id>', methods=['GET'])
@login_required
@require_role(*ADMIN_ROLES)
def event_detail(event_id: str):
    """Full event including payload, metadata and per-consumer outcomes."""
    event = DomainEvent.query.filter_by(event_id=event_id).first()
    if event is None:
        return jsonify({'success': False, 'error': 'Event not found'}), 404

    processed = ProcessedEvent.query.filter_by(event_id=event_id).all()
    return jsonify({
        'success': True,
        'event': _serialize_event(event, include_payload=True),
        'consumers': [{
            'consumer': p.consumer,
            'status': p.status,
            'attempts': p.attempts,
            'error': p.error,
            'processed_at': p.processed_at.isoformat() if p.processed_at else None,
        } for p in processed],
    })


@events_api.route('/trace/<correlation_id>', methods=['GET'])
@login_required
@require_role(*ADMIN_ROLES)
def trace_journey(correlation_id: str):
    """
    Reconstruct a complete user journey.

    This is the "show me everything that happened for transaction X" view:
    the ordered event chain with causal parents.
    """
    chain = EventReplayer().trace(correlation_id)
    return jsonify({
        'success': True,
        'correlation_id': correlation_id,
        'count': len(chain),
        'chain': chain,
    })


# ----------------------------------------------------------------------
# Event-level dead-letter queue
# ----------------------------------------------------------------------
@events_api.route('/dead-letter', methods=['GET'])
@login_required
@require_role(*ADMIN_ROLES)
def event_dead_letter():
    """
    Event-level DLQ — deliberately separate from the notification DLQ.

    "The notification consumer never saw payment.successful" is a different
    failure domain from "the email bounced", and they need different remedies.
    """
    limit = min(int(request.args.get('limit', 100)), 500)
    rows = OutboxRelay().dead_letters(limit=limit)
    stuck = (
        DomainEvent.query
        .filter(DomainEvent.status.in_([
            EventStatus.DEAD_LETTER.value, EventStatus.PARTIAL.value,
        ]))
        .order_by(DomainEvent.updated_at.desc())
        .limit(limit).all()
    )
    return jsonify({
        'success': True,
        'outbox_dead_letters': [{
            'event_id': r.event_id,
            'event_type': r.event_type,
            'attempts': r.attempts,
            'last_error': r.last_error,
            'updated_at': r.updated_at.isoformat() if r.updated_at else None,
        } for r in rows],
        'stuck_events': [_serialize_event(e) for e in stuck],
    })


@events_api.route('/dead-letter/<event_id>/requeue', methods=['POST'])
@login_required
@require_role(*ADMIN_ROLES)
def requeue_dead_letter(event_id: str):
    """Return a dead-lettered outbox row to the publication queue."""
    if OutboxRelay().requeue(event_id):
        logger.info('Event %s requeued by user %s', event_id, getattr(current_user, 'id', None))
        return jsonify({'success': True, 'event_id': event_id, 'status': 'requeued'})
    return jsonify({'success': False, 'error': 'Outbox row not found'}), 404


# ----------------------------------------------------------------------
# Replay
# ----------------------------------------------------------------------
@events_api.route('/replay', methods=['POST'])
@login_required
@require_role(*ADMIN_ROLES)
def replay_events():
    """
    Replay historical events to selected consumers.

    ``dry_run`` defaults to True — replay is a loaded gun (it can re-notify
    users if you target the notification consumer and reset idempotency), so
    the caller must opt in explicitly.

    Body::

        {
          "consumers": ["analytics"],
          "event_types": ["payment.successful"],
          "correlation_id": "cor_...",
          "since_hours": 24,
          "reset_consumer": false,
          "dry_run": true,
          "limit": 500
        }
    """
    body = request.get_json(silent=True) or {}

    filters = {}
    if event_types := body.get('event_types'):
        filters['event_types'] = event_types
    if correlation_id := body.get('correlation_id'):
        filters['correlation_id'] = correlation_id
    if aggregate_type := body.get('aggregate_type'):
        filters['aggregate_type'] = aggregate_type
    if aggregate_id := body.get('aggregate_id'):
        filters['aggregate_id'] = aggregate_id
    if since_hours := body.get('since_hours'):
        filters['since'] = datetime.now(timezone.utc) - timedelta(hours=int(since_hours))

    consumers = body.get('consumers') or None
    dry_run = bool(body.get('dry_run', True))
    reset = bool(body.get('reset_consumer', False))
    limit = min(int(body.get('limit', 500)), 5000)

    # Guard rail: resetting the notification consumer WILL re-send messages.
    if reset and (not consumers or 'notification' in consumers) and not body.get('confirm_resend'):
        return jsonify({
            'success': False,
            'error': (
                'Resetting the notification consumer would re-send user-facing '
                'messages. Pass "confirm_resend": true to proceed, or restrict '
                '"consumers" to non-notification consumers.'
            ),
        }), 400

    result = EventReplayer().replay(
        only=consumers, limit=limit, reset_consumer=reset, dry_run=dry_run, **filters
    )
    logger.info('Event replay by user %s: %s', getattr(current_user, 'id', None), result)
    return jsonify({'success': True, **result})


# ----------------------------------------------------------------------
# Partner subscriptions
# ----------------------------------------------------------------------
@events_api.route('/subscriptions', methods=['GET'])
@login_required
@require_role(*ADMIN_ROLES)
def list_subscriptions():
    """List partner subscriptions (secrets never returned)."""
    subs = EventSubscription.query.order_by(EventSubscription.created_at.desc()).all()
    return jsonify({
        'success': True,
        'count': len(subs),
        'subscriptions': [{
            'id': s.id,
            'subscriber': s.subscriber,
            'description': s.description,
            'event_types': s.event_types,
            'endpoint': s.endpoint,
            'status': s.status,
            'api_version': s.api_version,
            'has_secret': bool(s.secret),
            'consecutive_failures': s.consecutive_failures,
            'last_success_at': s.last_success_at.isoformat() if s.last_success_at else None,
            'last_failure_at': s.last_failure_at.isoformat() if s.last_failure_at else None,
        } for s in subs],
    })


@events_api.route('/subscriptions', methods=['POST'])
@login_required
@require_role(*ADMIN_ROLES)
def create_subscription():
    """
    Register a partner subscription.

    The signing secret is generated server-side and returned exactly once —
    it is never retrievable again, matching standard webhook practice.
    """
    body = request.get_json(silent=True) or {}
    subscriber = (body.get('subscriber') or '').strip()
    endpoint = (body.get('endpoint') or '').strip()
    event_types = body.get('event_types') or []

    if not subscriber or not endpoint:
        return jsonify({'success': False, 'error': 'subscriber and endpoint are required'}), 400
    if not endpoint.startswith('https://'):
        return jsonify({'success': False, 'error': 'endpoint must use HTTPS'}), 400
    if not event_types:
        return jsonify({'success': False, 'error': 'at least one event_type is required'}), 400

    # Reject subscriptions to events not cleared for external exposure.
    invalid = [
        t for t in event_types
        if not t.endswith('*') and not event_registry.is_externally_visible(t)
    ]
    if invalid:
        return jsonify({
            'success': False,
            'error': f'These event types are not externally visible: {", ".join(invalid)}',
        }), 400

    secret = f'whsec_{secrets.token_urlsafe(32)}'
    subscription = EventSubscription(
        subscriber=subscriber,
        description=body.get('description'),
        event_types=event_types,
        endpoint=endpoint,
        secret=secret,
        status=SubscriptionStatus.ACTIVE.value,
        max_attempts=int(body.get('max_attempts', 6)),
        timeout_seconds=int(body.get('timeout_seconds', 10)),
        owner_user_id=getattr(current_user, 'id', None),
    )
    db.session.add(subscription)
    db.session.commit()

    return jsonify({
        'success': True,
        'subscription': {
            'id': subscription.id,
            'subscriber': subscription.subscriber,
            'endpoint': subscription.endpoint,
            'event_types': subscription.event_types,
            'status': subscription.status,
        },
        # Shown once, never again.
        'secret': secret,
        'signature_scheme': 'HMAC-SHA256 over "{timestamp}.{body}", header X-AFCON360-Signature: sha256=<hex>',
    }), 201


@events_api.route('/subscriptions/<int:sub_id>/status', methods=['POST'])
@login_required
@require_role(*ADMIN_ROLES)
def set_subscription_status(sub_id: int):
    """Activate / pause / disable a subscription (also resets the circuit breaker)."""
    body = request.get_json(silent=True) or {}
    status = (body.get('status') or '').lower()
    if status not in {s.value for s in SubscriptionStatus}:
        return jsonify({'success': False, 'error': 'Invalid status'}), 400

    subscription = db.session.get(EventSubscription, sub_id)
    if subscription is None:
        return jsonify({'success': False, 'error': 'Subscription not found'}), 404

    subscription.status = status
    if status == SubscriptionStatus.ACTIVE.value:
        subscription.consecutive_failures = 0
    db.session.commit()
    return jsonify({'success': True, 'id': sub_id, 'status': status})


@events_api.route('/deliveries', methods=['GET'])
@login_required
@require_role(*ADMIN_ROLES)
def list_deliveries():
    """Outbound partner webhook delivery history."""
    limit = min(int(request.args.get('limit', 100)), 500)
    query = WebhookDelivery.query
    if status := request.args.get('status'):
        query = query.filter(WebhookDelivery.status == status)
    if sub_id := request.args.get('subscription_id'):
        query = query.filter(WebhookDelivery.subscription_id == int(sub_id))

    rows = query.order_by(WebhookDelivery.created_at.desc()).limit(limit).all()
    return jsonify({
        'success': True,
        'count': len(rows),
        'deliveries': [{
            'delivery_id': d.delivery_id,
            'subscription_id': d.subscription_id,
            'event_id': d.event_id,
            'event_type': d.event_type,
            'status': d.status,
            'attempts': d.attempts,
            'response_code': d.response_code,
            'last_error': d.last_error,
            'next_attempt_at': d.next_attempt_at.isoformat() if d.next_attempt_at else None,
            'delivered_at': d.delivered_at.isoformat() if d.delivered_at else None,
        } for d in rows],
    })


@events_api.route('/deliveries/<delivery_id>/replay', methods=['POST'])
@login_required
@require_role(*ADMIN_ROLES)
def replay_delivery(delivery_id: str):
    """Requeue a dead-lettered partner delivery."""
    from .webhooks import webhook_dispatcher

    if webhook_dispatcher.replay(delivery_id):
        return jsonify({'success': True, 'delivery_id': delivery_id, 'status': 'requeued'})
    return jsonify({'success': False, 'error': 'Delivery not found'}), 404
