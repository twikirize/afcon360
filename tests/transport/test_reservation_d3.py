"""AFCON360 Transport - TH-3-D3 / TH-3-D3-B Reservation Tests.

Tests for the Batch 1 reservation system plus the TH-3-D3-B reservation /
concurrency cleanup (application-level vehicle locking + half-open overlap
guard replacing the retired GiST exclusion-constraint design).
"""
import uuid as _uuid
import sqlalchemy as sa
import pytest
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from threading import Barrier, Thread

from app.extensions import db
from app.transport.models import (
    TransportReservation, TransportReservationLine,
    ProviderOfferingSupply, Vehicle, TransportOffering,
    ReservationState, ReservationObligationState,
)
from app.transport.services.reservation_service import (
    TransportReservationService, SupplyCoverageError, ReservationConflictError,
)
from app.transport.services.reservation_expiry_service import (
    TransportReservationExpiryService,
)
from app.transport.services.reservation_policy_evaluator import (
    TransportReservationPolicyEvaluator, PolicyDecision, CANONICAL_PAYMENT_METHODS,
)
from app.transport.services.offering_registry import TransportOfferingRegistry
from app.transport.services.reservation_state_machine import (
    InvalidObligationTransition, TransportReservationStateMachine,
)


class TestObligationStateMachine:
    @pytest.mark.parametrize("current,target", [
        (ReservationObligationState.UNPAID, ReservationObligationState.DEPOSITED),
        (ReservationObligationState.UNPAID, ReservationObligationState.PAID),
        (ReservationObligationState.DEPOSITED, ReservationObligationState.PAID),
    ])
    def test_allows_monotonic_transitions(self, current, target):
        assert TransportReservationStateMachine.can_transition_obligation(current, target)

    @pytest.mark.parametrize("current,target", [
        (ReservationObligationState.DEPOSITED, ReservationObligationState.UNPAID),
        (ReservationObligationState.PAID, ReservationObligationState.UNPAID),
        (ReservationObligationState.PAID, ReservationObligationState.DEPOSITED),
    ])
    def test_rejects_backward_transitions(self, current, target):
        assert not TransportReservationStateMachine.can_transition_obligation(current, target)


class TestPolicyEvaluatorStrict:

    def _actor(self):
        class A:
            id = 1
            is_authenticated = True
        return A()

    def test_rejects_unknown_method(self):
        now = datetime.now(timezone.utc)
        d = TransportReservationPolicyEvaluator.evaluate(
            actor=self._actor(), offering_code="cab_family",
            provider_type="organisation", provider_id=1,
            quantity=1,
            window_start=now, window_end=now + timedelta(hours=1),
            payment_method="BITCOIN", payment_timing="NOW",
        )
        assert not d.allowed
        assert "payment_method" in d.reason.lower()

    def test_rejects_unknown_timing(self):
        now = datetime.now(timezone.utc)
        d = TransportReservationPolicyEvaluator.evaluate(
            actor=self._actor(), offering_code="cab_family",
            provider_type="organisation", provider_id=1,
            quantity=1,
            window_start=now, window_end=now + timedelta(hours=1),
            payment_method="CASH", payment_timing="MAYBE_LATER",
        )
        assert not d.allowed

    def test_negotiated_is_not_a_method(self):
        assert "NEGOTIATED" not in CANONICAL_PAYMENT_METHODS
        assert "INVOICE" not in CANONICAL_PAYMENT_METHODS

    def test_now_requires_obligation_paid_for_reserved(self):
        now = datetime.now(timezone.utc)
        d = TransportReservationPolicyEvaluator.evaluate(
            actor=self._actor(), offering_code="cab_family",
            provider_type="organisation", provider_id=1,
            quantity=1,
            window_start=now, window_end=now + timedelta(hours=1),
            payment_method="WALLET", payment_timing="NOW",
        )
        assert d.allowed
        assert d.required_obligation_for_reserved == frozenset({"PAID"})

    def test_deposit_requires_deposited_for_reserved(self):
        now = datetime.now(timezone.utc) + timedelta(days=10)
        d = TransportReservationPolicyEvaluator.evaluate(
            actor=self._actor(), offering_code="cab_family",
            provider_type="organisation", provider_id=1,
            quantity=1,
            window_start=now, window_end=now + timedelta(hours=1),
            payment_method="CARD", payment_timing="DEPOSIT",
            estimated_value=Decimal("100"),
        )
        assert d.allowed
        assert d.required_obligation_for_reserved == frozenset({"DEPOSITED", "PAID"})

    def test_end_of_trip_allows_unpaid(self):
        now = datetime.now(timezone.utc)
        d = TransportReservationPolicyEvaluator.evaluate(
            actor=self._actor(), offering_code="cab_family",
            provider_type="organisation", provider_id=1,
            quantity=1,
            window_start=now, window_end=now + timedelta(hours=1),
            payment_method="CASH", payment_timing="END_OF_TRIP",
        )
        assert d.allowed
        assert "UNPAID" in d.required_obligation_for_reserved

    def test_invoice_allows_unpaid(self):
        now = datetime.now(timezone.utc)
        d = TransportReservationPolicyEvaluator.evaluate(
            actor=self._actor(), offering_code="cab_family",
            provider_type="organisation", provider_id=1,
            quantity=1,
            window_start=now, window_end=now + timedelta(hours=1),
            payment_method="BANK_TRANSFER", payment_timing="INVOICE",
        )
        assert d.allowed
        assert "UNPAID" in d.required_obligation_for_reserved


class TestSupplyCoverage:

    def test_supply_gap_rejected(self, db_session, app):
        base = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0) + timedelta(days=30)
        # Supply 08–12 and 14–18, request 11–15.
        db.session.add(ProviderOfferingSupply(
            provider_type="organisation", provider_id=99, offering_code="van",
            window_start=base + timedelta(hours=8),
            window_end=base + timedelta(hours=12),
            total_units=100,
        ))
        db.session.add(ProviderOfferingSupply(
            provider_type="organisation", provider_id=99, offering_code="van",
            window_start=base + timedelta(hours=14),
            window_end=base + timedelta(hours=18),
            total_units=100,
        ))
        db.session.commit()

        from app.identity.models.user import User
        import uuid as _uuid

        uid = str(_uuid.uuid4())[:8]
        user = User(
            username=f'user_{uid}',
            email=f'user_{uid}@test.example.com',
            is_verified=True,
            is_active=True,
        )
        user.set_password('TestPass123!')
        db.session.add(user)
        db.session.commit()

        with app.app_context():
            TransportOfferingRegistry.ensure_defaults()

        class A:
            id = user.id
            is_authenticated = True

        with pytest.raises(SupplyCoverageError):
            TransportReservationService.create_reservation(
                actor=A(), offering_code="van",
                provider_type="organisation", provider_id=99,
                window_start=base + timedelta(hours=11),
                window_end=base + timedelta(hours=15),
                required_quantity=40, mode="capacity",
                payment_method="CASH", payment_timing="NOW",
                idempotency_key="gap-test-1",
            )

    def test_overlapping_supply_rejected(self, db_session, app):
        base = datetime.now(timezone.utc) + timedelta(days=30)
        from app.utils.exceptions import ConflictError

        TransportReservationService.register_supply(
            provider_type="organisation", provider_id=100, offering_code="van",
            window_start=base, window_end=base + timedelta(hours=4),
            total_units=10,
        )
        with pytest.raises(ConflictError):
            TransportReservationService.register_supply(
                provider_type="organisation", provider_id=100, offering_code="van",
                window_start=base + timedelta(hours=2),
                window_end=base + timedelta(hours=6),
                total_units=10,
            )

    def test_adjacent_supply_declarations_are_valid(self, db_session, app):
        base = datetime.now(timezone.utc) + timedelta(days=30)
        first = TransportReservationService.register_supply(
            provider_type="organisation", provider_id=101, offering_code="van",
            window_start=base, window_end=base + timedelta(hours=3), total_units=10,
        )
        second = TransportReservationService.register_supply(
            provider_type="organisation", provider_id=101, offering_code="van",
            window_start=base + timedelta(hours=3), window_end=base + timedelta(hours=6),
            total_units=10,
        )
        assert first.id != second.id


class TestSpecificCapacityPool:

    def test_specific_and_abstract_commitments_share_supply(self, db_session, app):
        base = datetime.now(timezone.utc) + timedelta(days=30)
        from app.identity.models.user import User
        import uuid as _uuid

        uid = str(_uuid.uuid4())[:8]
        user = User(username=f'user_{uid}', email=f'user_{uid}@test.example.com',
                    is_verified=True, is_active=True)
        user.set_password('TestPass123!')
        db.session.add(user)
        db.session.commit()
        vehicle = Vehicle(
            owner_type="organisation", owner_id=user.id, license_plate=f"T{uid}",
            make="Test", model="Van", year=2025, vehicle_type="van",
            vehicle_class="van", passenger_capacity=12, is_available=True, status="active",
        )
        db.session.add(vehicle)
        db.session.commit()
        TransportReservationService.register_supply(
            provider_type="organisation", provider_id=user.id, offering_code="van",
            window_start=base, window_end=base + timedelta(hours=4), total_units=1,
        )

        class A:
            id = user.id
            is_authenticated = True

        TransportReservationService.create_reservation(
            actor=A(), offering_code="van", provider_type="organisation", provider_id=user.id,
            window_start=base, window_end=base + timedelta(hours=3), required_quantity=1,
            mode="specific", specific_vehicle_ids=[vehicle.id], payment_method="CASH",
            payment_timing="END_OF_TRIP", idempotency_key="specific-consumes-pool",
        )
        with pytest.raises(ReservationConflictError):
            TransportReservationService.create_reservation(
                actor=A(), offering_code="van", provider_type="organisation", provider_id=user.id,
                window_start=base, window_end=base + timedelta(hours=3), required_quantity=1,
                mode="capacity", payment_method="CASH", payment_timing="END_OF_TRIP",
                idempotency_key="abstract-cannot-bypass-pool",
            )


class TestIdempotency:

    def test_same_key_returns_same_reservation(self, db_session, app):
        base = datetime.now(timezone.utc) + timedelta(days=30)
        from app.identity.models.user import User
        import uuid as _uuid

        uid = str(_uuid.uuid4())[:8]
        user = User(
            username=f'user_{uid}',
            email=f'user_{uid}@test.example.com',
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
        r1 = TransportReservationService.create_reservation(
            actor=A(), offering_code="van",
            provider_type="organisation", provider_id=user.id,
            window_start=base, window_end=base + timedelta(hours=4),
            required_quantity=3, mode="capacity",
            payment_method="CASH", payment_timing="END_OF_TRIP",
            idempotency_key="retry-001",
        )
        r2 = TransportReservationService.create_reservation(
            actor=A(), offering_code="van",
            provider_type="organisation", provider_id=user.id,
            window_start=base, window_end=base + timedelta(hours=4),
            required_quantity=3, mode="capacity",
            payment_method="CASH", payment_timing="END_OF_TRIP",
            idempotency_key="retry-001",
        )
        assert r1.id == r2.id

    def test_same_key_with_different_material_request_conflicts(self, db_session, app):
        base = datetime.now(timezone.utc) + timedelta(days=30)
        from app.identity.models.user import User
        import uuid as _uuid
        from app.utils.exceptions import ConflictError

        uid = str(_uuid.uuid4())[:8]
        user = User(username=f'user_{uid}', email=f'user_{uid}@test.example.com',
                    is_verified=True, is_active=True)
        user.set_password('TestPass123!')
        db.session.add(user)
        db.session.commit()
        TransportReservationService.register_supply(
            provider_type="organisation", provider_id=user.id, offering_code="van",
            window_start=base, window_end=base + timedelta(hours=4), total_units=10,
        )

        class A:
            id = user.id
            is_authenticated = True

        request = dict(
            actor=A(), offering_code="van", provider_type="organisation", provider_id=user.id,
            window_start=base, window_end=base + timedelta(hours=4),
            required_quantity=1, mode="capacity", payment_method="CASH",
            payment_timing="END_OF_TRIP", idempotency_key="same-key-different-request",
        )
        TransportReservationService.create_reservation(**request)
        with pytest.raises(ConflictError):
            TransportReservationService.create_reservation(
                **{**request, "required_quantity": 2}
            )


class TestObligationGating:

    def test_wallet_now_stays_held_until_obligation_paid(self, db_session, app):
        base = datetime.now(timezone.utc) + timedelta(days=30)
        from app.identity.models.user import User
        import uuid as _uuid

        uid = str(_uuid.uuid4())[:8]
        user = User(
            username=f'user_{uid}',
            email=f'user_{uid}@test.example.com',
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
        r = TransportReservationService.create_reservation(
            actor=A(), offering_code="van",
            provider_type="organisation", provider_id=user.id,
            window_start=base, window_end=base + timedelta(hours=4),
            required_quantity=1, mode="capacity",
            payment_method="WALLET", payment_timing="NOW",
            estimated_value=Decimal("100"),
            idempotency_key="now-001",
        )
        # NOW requires PAID before RESERVED.
        assert r.state == "held"
        # Apply obligation event
        TransportReservationService.apply_obligation_event(
            reservation_id=r.id,
            target_obligation=ReservationObligationState.PAID,
        )
        r2 = db.session.get(TransportReservation, r.id)
        assert r2.state == "reserved"

    def test_end_of_trip_goes_reserved_immediately(self, db_session, app):
        base = datetime.now(timezone.utc) + timedelta(days=30)
        from app.identity.models.user import User
        import uuid as _uuid

        uid = str(_uuid.uuid4())[:8]
        user = User(
            username=f'user_{uid}',
            email=f'user_{uid}@test.example.com',
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
        r = TransportReservationService.create_reservation(
            actor=A(), offering_code="van",
            provider_type="organisation", provider_id=user.id,
            window_start=base, window_end=base + timedelta(hours=4),
            required_quantity=1, mode="capacity",
            payment_method="CASH", payment_timing="END_OF_TRIP",
            idempotency_key="eot-001",
        )
        assert r.state == "reserved"
        assert r.obligation_state == "unpaid"


class TestObligationFailClosed:
    """B-1/B-2/B-3 adversarial-review blockers: obligation events must fail
    closed and never manufacture payment amounts."""

    def _setup(self, db_session, app):
        base = datetime.now(timezone.utc) + timedelta(days=30)
        from app.identity.models.user import User
        import uuid as _uuid

        uid = str(_uuid.uuid4())[:8]
        user = User(
            username=f'user_{uid}',
            email=f'user_{uid}@test.example.com',
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

    def test_paid_without_required_total_is_rejected(self, db_session, app):
        from app.utils.exceptions import ValidationError
        base, user, A = self._setup(db_session, app)
        r = TransportReservationService.create_reservation(
            actor=A(), offering_code="van",
            provider_type="organisation", provider_id=user.id,
            window_start=base, window_end=base + timedelta(hours=4),
            required_quantity=1, mode="capacity",
            payment_method="WALLET", payment_timing="NOW",
            idempotency_key="paid-no-total",
        )
        # No estimated_value => required_total_amount is NULL.
        assert r.required_total_amount is None
        with pytest.raises(ValidationError):
            TransportReservationService.apply_obligation_event(
                reservation_id=r.id,
                target_obligation=ReservationObligationState.PAID,
            )
        r2 = db.session.get(TransportReservation, r.id)
        assert r2.obligation_state == "unpaid"
        assert r2.state == "held"

    def test_paid_with_insufficient_amount_is_rejected(self, db_session, app):
        from app.utils.exceptions import ValidationError
        base, user, A = self._setup(db_session, app)
        r = TransportReservationService.create_reservation(
            actor=A(), offering_code="van",
            provider_type="organisation", provider_id=user.id,
            window_start=base, window_end=base + timedelta(hours=4),
            required_quantity=1, mode="capacity",
            payment_method="WALLET", payment_timing="NOW",
            estimated_value=Decimal("100"),
            idempotency_key="paid-short",
        )
        assert r.required_total_amount == Decimal("100")
        with pytest.raises(ValidationError):
            TransportReservationService.apply_obligation_event(
                reservation_id=r.id,
                target_obligation=ReservationObligationState.PAID,
                amount_received=Decimal("25"),
            )
        r2 = db.session.get(TransportReservation, r.id)
        assert r2.obligation_state == "unpaid"

    def test_deposited_without_deposit_reference_is_rejected(self, db_session, app):
        from app.utils.exceptions import ValidationError
        base, user, A = self._setup(db_session, app)
        # DEPOSIT timing without estimated_value => deposit_required=True,
        # deposit_amount remains NULL (B-2 fail-open trigger).
        r = TransportReservationService.create_reservation(
            actor=A(), offering_code="van",
            provider_type="organisation", provider_id=user.id,
            window_start=base, window_end=base + timedelta(hours=4),
            required_quantity=1, mode="capacity",
            payment_method="WALLET", payment_timing="DEPOSIT",
            idempotency_key="dep-no-ref",
        )
        assert r.deposit_required is True
        assert r.deposit_amount is None
        with pytest.raises(ValidationError):
            TransportReservationService.apply_obligation_event(
                reservation_id=r.id,
                target_obligation=ReservationObligationState.DEPOSITED,
            )
        r2 = db.session.get(TransportReservation, r.id)
        assert r2.obligation_state == "unpaid"

    def test_deposited_with_insufficient_deposit_is_rejected(self, db_session, app):
        from app.utils.exceptions import ValidationError
        base, user, A = self._setup(db_session, app)
        r = TransportReservationService.create_reservation(
            actor=A(), offering_code="van",
            provider_type="organisation", provider_id=user.id,
            window_start=base, window_end=base + timedelta(hours=4),
            required_quantity=1, mode="capacity",
            payment_method="WALLET", payment_timing="DEPOSIT",
            estimated_value=Decimal("100"),
            idempotency_key="dep-short",
        )
        assert r.deposit_required is True
        assert r.deposit_amount == Decimal("20")
        with pytest.raises(ValidationError):
            TransportReservationService.apply_obligation_event(
                reservation_id=r.id,
                target_obligation=ReservationObligationState.DEPOSITED,
                amount_received=Decimal("10"),
            )
        r2 = db.session.get(TransportReservation, r.id)
        assert r2.obligation_state == "unpaid"

    def test_valid_deposit_reaches_deposited(self, db_session, app):
        base, user, A = self._setup(db_session, app)
        r = TransportReservationService.create_reservation(
            actor=A(), offering_code="van",
            provider_type="organisation", provider_id=user.id,
            window_start=base, window_end=base + timedelta(hours=4),
            required_quantity=1, mode="capacity",
            payment_method="WALLET", payment_timing="DEPOSIT",
            estimated_value=Decimal("100"),
            idempotency_key="dep-ok",
        )
        TransportReservationService.apply_obligation_event(
            reservation_id=r.id,
            target_obligation=ReservationObligationState.DEPOSITED,
        )
        r2 = db.session.get(TransportReservation, r.id)
        assert r2.obligation_state == "deposited"
        assert r2.amount_received == Decimal("20")

    def test_terminal_reservation_rejects_new_payment_event(self, db_session, app):
        from app.utils.exceptions import ValidationError
        base, user, A = self._setup(db_session, app)
        r = TransportReservationService.create_reservation(
            actor=A(), offering_code="van",
            provider_type="organisation", provider_id=user.id,
            window_start=base, window_end=base + timedelta(hours=4),
            required_quantity=1, mode="capacity",
            payment_method="WALLET", payment_timing="END_OF_TRIP",
            estimated_value=Decimal("100"),
            idempotency_key="term-pay",
        )
        assert r.state == "reserved"
        # Cancel puts the reservation in a terminal state.
        TransportReservationService.cancel_reservation(
            actor=A(), reservation_id=r.id,
        )
        r2 = db.session.get(TransportReservation, r.id)
        assert r2.state in ("cancelled",)
        with pytest.raises(ValidationError):
            TransportReservationService.apply_obligation_event(
                reservation_id=r.id,
                target_obligation=ReservationObligationState.PAID,
            )
        r3 = db.session.get(TransportReservation, r.id)
        assert r3.obligation_state == "unpaid"
        assert r3.state == "cancelled"

    def test_terminal_reservation_still_allows_idempotent_replay(self, db_session, app):
        """A no-op replay on an already-paid terminal reservation must remain
        idempotent and not raise (target == current)."""
        base, user, A = self._setup(db_session, app)
        r = TransportReservationService.create_reservation(
            actor=A(), offering_code="van",
            provider_type="organisation", provider_id=user.id,
            window_start=base, window_end=base + timedelta(hours=4),
            required_quantity=1, mode="capacity",
            payment_method="WALLET", payment_timing="NOW",
            estimated_value=Decimal("100"),
            idempotency_key="term-replay",
        )
        TransportReservationService.apply_obligation_event(
            reservation_id=r.id,
            target_obligation=ReservationObligationState.PAID,
        )
        r2 = db.session.get(TransportReservation, r.id)
        assert r2.obligation_state == "paid"
        TransportReservationService.cancel_reservation(
            actor=A(), reservation_id=r.id,
        )
        r3 = db.session.get(TransportReservation, r.id)
        assert r3.state == "cancelled"
        # Replay the SAME payment event: no-op, must not raise.
        TransportReservationService.apply_obligation_event(
            reservation_id=r.id,
            target_obligation=ReservationObligationState.PAID,
            amount_received=Decimal("100"),
        )
        r4 = db.session.get(TransportReservation, r.id)
        assert r4.obligation_state == "paid"
        assert r4.state == "cancelled"


# =====================================================================
# TH-3-D3-B: half-open [start, end) vehicle overlap guard (sequential)
# =====================================================================

def _d3b_org_setup(db_session, tag):
    """Org-owned vehicle + generous supply. Returns (base, user, Actor, vehicle)."""
    from app.identity.models.user import User
    base = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(days=30)
    uid = _uuid.uuid4().hex[:8]
    user = User(
        username=f"{tag}_{uid}",
        email=f"{tag}_{uid}@test.example.com",
        is_verified=True,
        is_active=True,
    )
    user.set_password("TestPass123!")
    db.session.add(user)
    db.session.commit()
    vehicle = Vehicle(
        owner_type="organisation", owner_id=user.id,
        license_plate=f"V{uid}", make="Test", model="Van", year=2025,
        vehicle_type="van", vehicle_class="van",
        passenger_capacity=12, is_available=True, status="active",
    )
    db.session.add(vehicle)
    db.session.commit()
    TransportOfferingRegistry.ensure_defaults()
    TransportReservationService.register_supply(
        provider_type="organisation", provider_id=user.id, offering_code="van",
        window_start=base, window_end=base + timedelta(hours=24), total_units=100,
    )

    class A:
        id = user.id
        is_authenticated = True

    return base, user, A, vehicle


def _d3b_specific_request(A, provider_id, vehicle, base, start_h, end_h, key):
    return dict(
        actor=A(), offering_code="van", provider_type="organisation",
        provider_id=provider_id,
        window_start=base + timedelta(hours=start_h),
        window_end=base + timedelta(hours=end_h),
        required_quantity=1, mode="specific",
        specific_vehicle_ids=[vehicle.id],
        payment_method="CASH", payment_timing="END_OF_TRIP",
        idempotency_key=key,
    )


class TestSpecificVehicleOverlap:
    """TH-3-D3-B sequential guard: overlapping windows conflict, adjacent
    half-open boundaries do not."""

    def test_overlapping_window_conflicts(self, db_session, app):
        base, user, A, vehicle = _d3b_org_setup(db_session, "ovl")
        TransportReservationService.create_reservation(
            **_d3b_specific_request(A, user.id, vehicle, base, 10, 16, "ovl-first"))
        with pytest.raises(ReservationConflictError):
            TransportReservationService.create_reservation(
                **_d3b_specific_request(A, user.id, vehicle, base, 13, 15, "ovl-second"))

    def test_identical_window_conflicts(self, db_session, app):
        base, user, A, vehicle = _d3b_org_setup(db_session, "idt")
        TransportReservationService.create_reservation(
            **_d3b_specific_request(A, user.id, vehicle, base, 10, 16, "idt-first"))
        with pytest.raises(ReservationConflictError):
            TransportReservationService.create_reservation(
                **_d3b_specific_request(A, user.id, vehicle, base, 10, 16, "idt-second"))

    def test_adjacent_windows_are_allowed(self, db_session, app):
        base, user, A, vehicle = _d3b_org_setup(db_session, "adj")
        r1 = TransportReservationService.create_reservation(
            **_d3b_specific_request(A, user.id, vehicle, base, 10, 13, "adj-first"))
        r2 = TransportReservationService.create_reservation(
            **_d3b_specific_request(A, user.id, vehicle, base, 13, 16, "adj-second"))
        assert r1.state == "reserved"
        assert r2.state == "reserved"

    def test_boundary_touches_do_not_conflict(self, db_session, app):
        base, user, A, vehicle = _d3b_org_setup(db_session, "bnd")
        # Existing ends exactly where the next begins (and vice versa).
        TransportReservationService.create_reservation(
            **_d3b_specific_request(A, user.id, vehicle, base, 9, 12, "bnd-mid"))
        TransportReservationService.create_reservation(
            **_d3b_specific_request(A, user.id, vehicle, base, 12, 14, "bnd-after"))
        TransportReservationService.create_reservation(
            **_d3b_specific_request(A, user.id, vehicle, base, 7, 9, "bnd-before"))

    def test_fully_separated_windows_are_allowed(self, db_session, app):
        base, user, A, vehicle = _d3b_org_setup(db_session, "sep")
        TransportReservationService.create_reservation(
            **_d3b_specific_request(A, user.id, vehicle, base, 10, 16, "sep-mid"))
        TransportReservationService.create_reservation(
            **_d3b_specific_request(A, user.id, vehicle, base, 2, 6, "sep-early"))
        TransportReservationService.create_reservation(
            **_d3b_specific_request(A, user.id, vehicle, base, 18, 22, "sep-late"))


class TestSpecificVehicleRelease:
    """TH-3-D3-B: cancellation and expiry actually release the vehicle."""

    def test_cancel_releases_vehicle(self, db_session, app):
        base, user, A, vehicle = _d3b_org_setup(db_session, "rel")
        r1 = TransportReservationService.create_reservation(
            **_d3b_specific_request(A, user.id, vehicle, base, 10, 16, "rel-first"))
        assert r1.state == "reserved"
        TransportReservationService.cancel_reservation(
            actor=A(), reservation_id=r1.id, reason="release-test")
        r1b = db.session.get(TransportReservation, r1.id)
        assert r1b.state == "cancelled"
        r2 = TransportReservationService.create_reservation(
            **_d3b_specific_request(A, user.id, vehicle, base, 10, 16, "rel-second"))
        assert r2.state == "reserved"

    def test_expiry_releases_vehicle(self, db_session, app):
        from app.identity.models.user import User
        base = datetime.now(timezone.utc).replace(microsecond=0) - timedelta(days=10)
        uid = _uuid.uuid4().hex[:8]
        user = User(
            username=f"exp_{uid}",
            email=f"exp_{uid}@test.example.com",
            is_verified=True,
            is_active=True,
        )
        user.set_password("TestPass123!")
        db.session.add(user)
        db.session.commit()
        vehicle = Vehicle(
            owner_type="organisation", owner_id=user.id,
            license_plate=f"V{uid}", make="Test", model="Van", year=2025,
            vehicle_type="van", vehicle_class="van",
            passenger_capacity=12, is_available=True, status="active",
        )
        db.session.add(vehicle)
        db.session.commit()
        TransportOfferingRegistry.ensure_defaults()
        TransportReservationService.register_supply(
            provider_type="organisation", provider_id=user.id, offering_code="van",
            window_start=base, window_end=base + timedelta(hours=6), total_units=100,
        )

        class A:
            id = user.id
            is_authenticated = True

        r1 = TransportReservationService.create_reservation(
            actor=A(), offering_code="van", provider_type="organisation",
            provider_id=user.id,
            window_start=base, window_end=base + timedelta(hours=3),
            required_quantity=1, mode="specific",
            specific_vehicle_ids=[vehicle.id],
            payment_method="CASH", payment_timing="DEPOSIT",
            idempotency_key="expiry-release-1",
        )
        assert r1.state == "held"
        summary = TransportReservationExpiryService.expire_due_held_reservations()
        assert summary["expired"] >= 1
        r1b = db.session.get(TransportReservation, r1.id)
        assert r1b.state == "expired"
        r2 = TransportReservationService.create_reservation(
            actor=A(), offering_code="van", provider_type="organisation",
            provider_id=user.id,
            window_start=base, window_end=base + timedelta(hours=3),
            required_quantity=1, mode="specific",
            specific_vehicle_ids=[vehicle.id],
            payment_method="CASH", payment_timing="END_OF_TRIP",
            idempotency_key="expiry-release-2",
        )
        assert r2.state == "reserved"


# =====================================================================
# TH-3-D3-B: real PostgreSQL concurrency (threaded — D2 precedent).
# Each test cleans its transport rows; user rows are left behind, matching
# the existing D2 threaded-tests precedent (_isolate_db skips them).
# =====================================================================

def _d3b_org_user(app, tag):
    with app.app_context():
        from app.identity.models.user import User
        uid = _uuid.uuid4().hex[:8]
        u = User(
            username=f"{tag}_{uid}",
            email=f"{tag}_{uid}@test.example.com",
            is_verified=True, is_active=True,
        )
        u.set_password("TestPass123!")
        db.session.add(u)
        db.session.commit()
        return u.id


def _d3b_thread_vehicle(app, owner_user_id, tag):
    with app.app_context():
        v = Vehicle(
            owner_type="organisation", owner_id=owner_user_id,
            license_plate=f"CT{tag}-{_uuid.uuid4().hex[:4].upper()}",
            make="Toyota", model="Hiace", year=2023,
            vehicle_type="van", vehicle_class="van",
            passenger_capacity=12, status="active", is_available=True,
        )
        db.session.add(v)
        db.session.commit()
        return v.id


def _d3b_cleanup(app, *, reservation_ids=None, supply_id=None, vehicle_id=None):
    with app.app_context():
        reservation_ids = reservation_ids or []
        if reservation_ids:
            db.session.execute(
                sa.delete(TransportReservationLine).where(
                    TransportReservationLine.reservation_id.in_(list(reservation_ids)),
                )
            )
            db.session.execute(
                sa.delete(TransportReservation).where(
                    TransportReservation.id.in_(list(reservation_ids)),
                )
            )
        if supply_id:
            supply_pk = getattr(supply_id, "id", supply_id)
            db.session.execute(
                sa.delete(ProviderOfferingSupply).where(
                    ProviderOfferingSupply.id == int(supply_pk))
            )
        if vehicle_id:
            veh = db.session.get(Vehicle, int(vehicle_id))
            if veh is not None:
                db.session.delete(veh)
        db.session.commit()


@pytest.mark.threaded
class TestConcurrentSpecificVehicleReservation:
    """TH-3-D3-B: two concurrent requests for the same physical vehicle must
    produce exactly one winner and one overlap conflict."""

    def test_same_vehicle_same_window_one_wins(self, app):
        with app.app_context():
            TransportOfferingRegistry.ensure_defaults()
        user1 = _d3b_org_user(app, "cspv")   # provider org (vehicle owner)
        user2 = _d3b_org_user(app, "cspv2")  # independent actor
        base = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(days=30)
        vehicle_id = _d3b_thread_vehicle(app, user1, "cspv")
        with app.app_context():
            supply_id = TransportReservationService.register_supply(
                provider_type="organisation", provider_id=user1, offering_code="van",
                window_start=base, window_end=base + timedelta(hours=6), total_units=100,
            ).id

        barrier = Barrier(2)
        results = [None, None]
        errors = [None, None]

        def reserve(idx, actor_id, key):
            with app.app_context():
                from app.identity.models.user import User
                actor = db.session.get(User, actor_id)
                barrier.wait(timeout=10)
                try:
                    r = TransportReservationService.create_reservation(
                        actor=actor, offering_code="van",
                        provider_type="organisation", provider_id=user1,
                        window_start=base, window_end=base + timedelta(hours=3),
                        required_quantity=1, mode="specific",
                        specific_vehicle_ids=[vehicle_id],
                        payment_method="CASH", payment_timing="END_OF_TRIP",
                        idempotency_key=key,
                    )
                    results[idx] = r.id
                except ReservationConflictError as e:
                    errors[idx] = e

        t0 = Thread(target=reserve, args=(0, user1, "conc-sv-key-a"))
        t1 = Thread(target=reserve, args=(1, user2, "conc-sv-key-b"))
        t0.start(); t1.start()
        t0.join(timeout=30); t1.join(timeout=30)

        wins = [r for r in results if r is not None]
        losses = [e for e in errors if e is not None]
        assert len(wins) == 1, f"expected exactly 1 success, got {results=} {errors=}"
        assert len(losses) == 1, f"expected exactly 1 conflict, got {results=} {errors=}"

        _d3b_cleanup(app, reservation_ids=[int(w) for w in wins],
                     supply_id=supply_id, vehicle_id=vehicle_id)

    def test_capacity_race_60_plus_60_on_100(self, app):
        """The supply `FOR UPDATE` (unchanged by D3-B) still serializes a
        60+60 capacity race on a 100-unit pool: exactly one wins."""
        with app.app_context():
            TransportOfferingRegistry.ensure_defaults()
        user1 = _d3b_org_user(app, "capr")
        user2 = _d3b_org_user(app, "capr2")
        base = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(days=30)
        with app.app_context():
            supply_id = TransportReservationService.register_supply(
                provider_type="organisation", provider_id=user1, offering_code="van",
                window_start=base, window_end=base + timedelta(hours=6), total_units=100,
            ).id

        barrier = Barrier(2)
        results = [None, None]
        errors = [None, None]

        def reserve(idx, actor_id, key):
            with app.app_context():
                from app.identity.models.user import User
                actor = db.session.get(User, actor_id)
                barrier.wait(timeout=10)
                try:
                    r = TransportReservationService.create_reservation(
                        actor=actor, offering_code="van",
                        provider_type="organisation", provider_id=user1,
                        window_start=base, window_end=base + timedelta(hours=3),
                        required_quantity=60, mode="capacity",
                        payment_method="CASH", payment_timing="END_OF_TRIP",
                        idempotency_key=key,
                    )
                    results[idx] = r.id
                except ReservationConflictError as e:
                    errors[idx] = e

        t0 = Thread(target=reserve, args=(0, user1, "conc-cap-key-a"))
        t1 = Thread(target=reserve, args=(1, user2, "conc-cap-key-b"))
        t0.start(); t1.start()
        t0.join(timeout=30); t1.join(timeout=30)

        wins = [r for r in results if r is not None]
        losses = [e for e in errors if e is not None]
        assert len(wins) == 1, f"expected exactly 1 success, got {results=} {errors=}"
        assert len(losses) == 1, f"expected exactly 1 conflict, got {results=} {errors=}"

        _d3b_cleanup(app, reservation_ids=[int(w) for w in wins], supply_id=supply_id)
