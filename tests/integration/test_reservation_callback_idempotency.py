"""
Fix 2.3 — Reservation Callback Idempotency integration tests.

These tests exercise TransportReservationService.apply_obligation_event()
directly, not via HTTP. The guarantee under test:

  - The FIRST call with a given wallet_transaction_reference advances the
    obligation exactly once and records the reference.
  - A DUPLICATE call with the same wallet_transaction_reference is a no-op:
    no extra obligation transition, no extra audit entry, no error, and the
    current reservation row is returned so the caller proceeds normally.
  - The same reference with a DIFFERENT target obligation is also a no-op
    (the same external financial event must be applied once).

The partial unique index ix_reservation_wallet_ref is global on
wallet_transaction_reference, so every reference used here must be unique
per run regardless of leftover rows.
"""
import uuid as _uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.extensions import db
from app.transport.models import TransportReservation, ReservationObligationState
from app.transport.services.reservation_service import TransportReservationService


def _unique_ref(prefix):
    """Per-run unique wallet_transaction_reference.

    ix_reservation_wallet_ref is GLOBAL on wallet_transaction_reference. A
    fixed value whose reservation row would collide with a fresh test on the
    next run. Unique refs keep the suite repeatable regardless of leftovers.
    """
    return f"{prefix}-{_uuid.uuid4().hex}"


def _obligation_audit_count(reservation_id):
    """Count reservation_obligation_changed entries in the audit log."""
    row = db.session.get(TransportReservation, reservation_id)
    log = row.audit_log or []
    return sum(
        1 for entry in log
        if entry.get("action") == "reservation_obligation_changed"
    )


def _setup(db_session, tag):
    """Fresh user + supply. Returns (base, user, Actor)."""
    base = datetime.now(timezone.utc) + timedelta(days=30)
    from app.identity.models.user import User

    uid = _uuid.uuid4().hex[:8]
    user = User(
        username=f'{tag}_{uid}',
        email=f'{tag}_{uid}@test.example.com',
        is_verified=True,
        is_active=True,
    )
    user.set_password('TestPass123!')
    db.session.add(user)
    db.session.commit()

    TransportReservationService.register_supply(
        provider_type="organisation", provider_id=user.id, offering_code="van",
        window_start=base, window_end=base + timedelta(hours=4),
        total_units=10,
    )

    class A:
        id = user.id
        is_authenticated = True

    return base, user, A


class TestReservationCallbackIdempotency:

    def test_first_callback_transitions_obligation(self, db_session, app):
        """First call with a new reference advances the obligation once."""
        base, user, A = _setup(db_session, "fix23-first")
        ref = _unique_ref("first")
        r = TransportReservationService.create_reservation(
            actor=A(), offering_code="van",
            provider_type="organisation", provider_id=user.id,
            window_start=base, window_end=base + timedelta(hours=4),
            required_quantity=1, mode="capacity",
            payment_method="WALLET", payment_timing="DEPOSIT",
            estimated_value=Decimal("100"),
            idempotency_key=f"fix23-first-{_uuid.uuid4().hex}",
        )
        assert r.obligation_state == "unpaid"

        result = TransportReservationService.apply_obligation_event(
            reservation_id=r.id,
            target_obligation=ReservationObligationState.DEPOSITED,
            wallet_transaction_reference=ref,
        )

        assert result is not None
        row = db.session.get(TransportReservation, r.id)
        assert row.obligation_state == "deposited"
        assert row.wallet_transaction_reference == ref
        assert _obligation_audit_count(r.id) == 1

    def test_duplicate_callback_is_noop(self, db_session, app):
        """Same reference again: no extra transition, audit, or error."""
        base, user, A = _setup(db_session, "fix23-dup")
        ref = _unique_ref("dup")
        r = TransportReservationService.create_reservation(
            actor=A(), offering_code="van",
            provider_type="organisation", provider_id=user.id,
            window_start=base, window_end=base + timedelta(hours=4),
            required_quantity=1, mode="capacity",
            payment_method="WALLET", payment_timing="DEPOSIT",
            estimated_value=Decimal("100"),
            idempotency_key=f"fix23-dup-{_uuid.uuid4().hex}",
        )

        TransportReservationService.apply_obligation_event(
            reservation_id=r.id,
            target_obligation=ReservationObligationState.DEPOSITED,
            wallet_transaction_reference=ref,
        )
        audit_before = _obligation_audit_count(r.id)
        assert audit_before == 1

        duplicate = TransportReservationService.apply_obligation_event(
            reservation_id=r.id,
            target_obligation=ReservationObligationState.DEPOSITED,
            wallet_transaction_reference=ref,
        )

        row = db.session.get(TransportReservation, r.id)
        assert duplicate is not None
        assert row.obligation_state == "deposited"
        assert row.wallet_transaction_reference == ref
        assert _obligation_audit_count(r.id) == audit_before

    def test_duplicate_callback_same_reference_different_state_is_noop(
            self, db_session, app):
        """Same external reference with a different target is still a no-op."""
        base, user, A = _setup(db_session, "fix23-diffstate")
        ref = _unique_ref("diffstate")
        r = TransportReservationService.create_reservation(
            actor=A(), offering_code="van",
            provider_type="organisation", provider_id=user.id,
            window_start=base, window_end=base + timedelta(hours=4),
            required_quantity=1, mode="capacity",
            payment_method="WALLET", payment_timing="DEPOSIT",
            estimated_value=Decimal("100"),
            idempotency_key=f"fix23-diffstate-{_uuid.uuid4().hex}",
        )

        TransportReservationService.apply_obligation_event(
            reservation_id=r.id,
            target_obligation=ReservationObligationState.DEPOSITED,
            wallet_transaction_reference=ref,
        )
        audit_before = _obligation_audit_count(r.id)
        assert audit_before == 1

        duplicate = TransportReservationService.apply_obligation_event(
            reservation_id=r.id,
            target_obligation=ReservationObligationState.PAID,
            wallet_transaction_reference=ref,
        )

        row = db.session.get(TransportReservation, r.id)
        assert duplicate is not None
        assert row.obligation_state == "deposited"
        assert row.wallet_transaction_reference == ref
        assert _obligation_audit_count(r.id) == audit_before