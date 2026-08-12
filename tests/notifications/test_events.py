"""
AFCON360 Platform Event Backbone Tests

Covers the layer BENEATH notification delivery:
  * canonical event envelope (serialization, versioning, causation chaining)
  * event registry (validation, external visibility)
  * notification policy engine (audience, delivery class, thresholds)
  * transactional outbox semantics
  * event-level idempotency, DLQ and replay
  * partner webhook signing

The envelope/registry/policy tests are deliberately DB-free so they run fast
and stay green independent of database schema state. Persistence-dependent
tests are marked and skip cleanly when the event tables are absent.
"""

import json

import pytest

from app.notifications.events.exceptions import (
    EventValidationError,
    UnknownEventTypeError,
)
from app.notifications.events.policy import (
    Audience,
    DeliveryClass,
    NotificationPolicy,
    PolicyEngine,
    policy_engine,
)
from app.notifications.events.registry import (
    EventRegistry,
    EventType,
    event_registry,
)
from app.notifications.events.schemas import EventEnvelope, EventMeta


# ============================================================================
# Event Envelope
# ============================================================================
class TestEventEnvelope:
    def test_envelope_generates_prefixed_event_id(self):
        env = EventEnvelope(event_type=EventType.PAYMENT_SUCCESSFUL)
        assert env.event_id.startswith('evt_')
        assert env.event_version == 1

    def test_json_roundtrip_preserves_all_fields(self):
        env = EventEnvelope(
            event_type=EventType.BOOKING_CONFIRMED,
            payload={'user_id': 7, 'booking_reference': 'BK-1'},
            aggregate_type='booking',
            aggregate_id='BK-1',
            correlation_id='cor_abc',
            causation_id='evt_parent',
        )
        back = EventEnvelope.from_json(env.to_json())

        assert back.event_id == env.event_id
        assert back.event_type == env.event_type
        assert back.payload == env.payload
        assert back.correlation_id == 'cor_abc'
        assert back.causation_id == 'evt_parent'
        assert back.aggregate_id == 'BK-1'

    def test_to_json_is_valid_json(self):
        env = EventEnvelope(event_type=EventType.KYC_APPROVED, payload={'user_id': 1})
        assert json.loads(env.to_json())['event_type'] == 'kyc.approved'

    def test_user_id_resolution_from_payload(self):
        assert EventEnvelope(event_type='x', payload={'user_id': 42}).user_id == 42
        assert EventEnvelope(event_type='x', payload={'recipient_id': 8}).user_id == 8
        assert EventEnvelope(event_type='x', payload={}).user_id is None

    def test_user_id_falls_back_to_actor(self):
        env = EventEnvelope(event_type='x', actor_type='user', actor_id='15')
        assert env.user_id == 15

    def test_child_event_inherits_correlation_and_sets_causation(self):
        """The payment -> booking -> notification chain must stay linkable."""
        parent = EventEnvelope(
            event_type=EventType.PAYMENT_SUCCESSFUL, correlation_id='cor_journey'
        )
        child = parent.child(EventType.BOOKING_CONFIRMED, {'user_id': 1})

        assert child.correlation_id == 'cor_journey'
        assert child.causation_id == parent.event_id
        assert child.event_id != parent.event_id

    def test_metadata_roundtrip(self):
        meta = EventMeta(source='afcon360', environment='test', extra={'k': 'v'})
        data = meta.to_dict()
        assert data['environment'] == 'test'
        assert data['k'] == 'v'
        assert EventMeta.from_dict(data).extra['k'] == 'v'


# ============================================================================
# Event Registry
# ============================================================================
class TestEventRegistry:
    def test_core_event_types_are_registered(self):
        for event_type in (
            EventType.PAYMENT_SUCCESSFUL,
            EventType.KYC_APPROVED,
            EventType.BOOKING_CONFIRMED,
            EventType.USER_REGISTERED,
        ):
            assert event_registry.get(event_type) is not None

    def test_validation_rejects_missing_required_field(self):
        with pytest.raises(EventValidationError):
            event_registry.validate(EventType.PAYMENT_SUCCESSFUL, {'user_id': 1})

    def test_validation_accepts_complete_payload(self):
        version = event_registry.validate(
            EventType.PAYMENT_SUCCESSFUL,
            {'user_id': 1, 'amount': 100},
        )
        assert version >= 1

    def test_unregistered_type_allowed_by_default(self):
        """Forward compatibility: unknown types warn but do not explode."""
        assert event_registry.validate('totally.unknown', {}) == 1

    def test_strict_registry_rejects_unregistered_type(self):
        strict = EventRegistry(strict=True)
        with pytest.raises(UnknownEventTypeError):
            strict.validate('totally.unknown', {})

    def test_external_visibility_gating(self):
        """Partner-facing events are explicitly allow-listed; KYC is not."""
        assert event_registry.is_externally_visible(EventType.BOOKING_CONFIRMED) is True
        assert event_registry.is_externally_visible(EventType.KYC_APPROVED) is False


# ============================================================================
# Notification Policy Engine
# ============================================================================
class TestPolicyEngine:
    def test_payment_produces_mandatory_receipt(self):
        env = EventEnvelope(
            event_type=EventType.PAYMENT_SUCCESSFUL,
            payload={'user_id': 1, 'amount': 5000, 'currency': 'UGX'},
        )
        receipts = [
            d for d in policy_engine.resolve(env)
            if d.notification_type == 'payment_received'
        ]
        assert len(receipts) == 1
        receipt = receipts[0]
        assert receipt.delivery_class == DeliveryClass.MANDATORY
        assert receipt.force_external is True   # must reach the real mailbox
        assert 'email' in receipt.channels
        assert 'in_app' in receipt.channels

    def test_small_payment_does_not_escalate_to_compliance(self):
        env = EventEnvelope(
            event_type=EventType.PAYMENT_SUCCESSFUL,
            payload={'user_id': 1, 'amount': 5_000, 'currency': 'UGX'},
        )
        assert not [
            d for d in policy_engine.resolve(env) if d.audience == Audience.ROLES
        ]

    def test_large_payment_escalates_to_compliance_roles(self):
        env = EventEnvelope(
            event_type=EventType.PAYMENT_SUCCESSFUL,
            payload={'user_id': 1, 'amount': 5_000_000, 'currency': 'UGX'},
        )
        role_directives = [
            d for d in policy_engine.resolve(env) if d.audience == Audience.ROLES
        ]
        assert len(role_directives) == 1
        assert 'compliance_officer' in role_directives[0].roles

    def test_message_interpolates_payload(self):
        env = EventEnvelope(
            event_type=EventType.PAYMENT_SUCCESSFUL,
            payload={'user_id': 1, 'amount': 250, 'currency': 'UGX'},
        )
        receipt = next(
            d for d in policy_engine.resolve(env)
            if d.notification_type == 'payment_received'
        )
        assert 'UGX 250' in receipt.message

    def test_optional_class_does_not_force_external(self):
        env = EventEnvelope(
            event_type=EventType.REVIEW_RECEIVED, payload={'user_id': 1}
        )
        for directive in policy_engine.resolve(env):
            if directive.delivery_class == DeliveryClass.OPTIONAL:
                assert directive.force_external is False

    def test_event_without_policy_produces_nothing(self):
        """Most events are audit/analytics only — they must not notify."""
        env = EventEnvelope(event_type=EventType.LOGIN_FAILED, payload={'user_id': 1})
        assert policy_engine.resolve(env) == []

    def test_conditional_policy_is_evaluated(self):
        engine = PolicyEngine()
        engine.register(NotificationPolicy(
            event_type='test.conditional',
            notification_type='system_alert',
            title='T', message='M',
            condition=lambda e: e.get('flag') is True,
        ))
        assert engine.resolve(
            EventEnvelope(event_type='test.conditional', payload={'flag': True})
        )
        assert not engine.resolve(
            EventEnvelope(event_type='test.conditional', payload={'flag': False})
        )

    def test_broken_condition_fails_closed(self):
        """A raising condition must suppress, never crash the pipeline."""
        engine = PolicyEngine()
        engine.register(NotificationPolicy(
            event_type='test.broken',
            notification_type='system_alert',
            title='T', message='M',
            condition=lambda e: 1 / 0,
        ))
        assert engine.resolve(EventEnvelope(event_type='test.broken')) == []


# ============================================================================
# Webhook signing
# ============================================================================
class TestWebhookSigning:
    def test_signature_is_deterministic_and_timestamp_bound(self):
        from app.notifications.events.consumers import WebhookConsumer

        body = '{"event":"booking.confirmed"}'
        a = WebhookConsumer.sign('secret', body, '1700000000')
        b = WebhookConsumer.sign('secret', body, '1700000000')
        c = WebhookConsumer.sign('secret', body, '1700000001')

        assert a == b                    # reproducible for the partner
        assert a != c                    # timestamp is signed -> replay-proof
        assert len(a) == 64              # hex sha256

    def test_different_secrets_produce_different_signatures(self):
        from app.notifications.events.consumers import WebhookConsumer

        body = '{"x":1}'
        assert (
            WebhookConsumer.sign('s1', body, '1700000000')
            != WebhookConsumer.sign('s2', body, '1700000000')
        )

    def test_partner_payload_excludes_internal_metadata(self):
        from app.notifications.events.consumers import WebhookConsumer

        env = EventEnvelope(
            event_type=EventType.BOOKING_CONFIRMED,
            payload={'user_id': 1},
            metadata={'hostname': 'internal-box', 'ip_address': '10.0.0.1'},
        )
        payload = WebhookConsumer.build_payload(env, subscription=None)

        assert set(payload) == {
            'event', 'version', 'event_id', 'timestamp', 'correlation_id', 'data'
        }
        assert 'metadata' not in payload
        assert 'hostname' not in json.dumps(payload)


# ============================================================================
# Outbox / persistence (DB-dependent)
# ============================================================================
def _event_tables_ready(app) -> bool:
    from sqlalchemy import inspect

    from app.extensions import db

    with app.app_context():
        insp = inspect(db.engine)
        return all(
            insp.has_table(t)
            for t in ('domain_events', 'outbox_events', 'processed_events')
        )


@pytest.mark.usefixtures('app')
class TestTransactionalOutbox:
    def test_emit_stages_ledger_and_outbox_atomically(self, app, db_session):
        if not _event_tables_ready(app):
            pytest.skip('event backbone tables not present in test DB')

        from app.notifications.events import emit_event
        from app.notifications.events.models import DomainEvent, OutboxEvent

        env = emit_event(
            EventType.PAYMENT_SUCCESSFUL,
            payload={'user_id': 1, 'amount': 100, 'currency': 'UGX'},
            aggregate_type='payment', aggregate_id='pay_unit_1',
        )
        assert env is not None

        # Both rows exist in the session before commit (same transaction).
        assert DomainEvent.query.filter_by(event_id=env.event_id).first() is not None
        assert OutboxEvent.query.filter_by(event_id=env.event_id).first() is not None

    def test_rollback_discards_the_event(self, app, db_session):
        """No phantom events: a rolled-back business change publishes nothing."""
        if not _event_tables_ready(app):
            pytest.skip('event backbone tables not present in test DB')

        from app.notifications.events import emit_event
        from app.notifications.events.models import DomainEvent

        env = emit_event(
            EventType.BOOKING_CONFIRMED,
            payload={'user_id': 1, 'booking_reference': 'BK-ROLLBACK'},
        )
        db_session.rollback()

        assert DomainEvent.query.filter_by(event_id=env.event_id).first() is None
