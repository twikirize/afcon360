"""AFCON360 Transport - TH-3-D3 Reservation Tests.

Tests for the Batch 1 revision of the reservation system.
"""
import pytest
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.extensions import db
from app.transport.models import (
    TransportReservation, TransportReservationLine,
    ProviderOfferingSupply, Vehicle, TransportOffering,
    ReservationState, ReservationObligationState,
)
from app.transport.services.reservation_service import (
    TransportReservationService, SupplyCoverageError, ReservationConflictError,
)
from app.transport.services.reservation_policy_evaluator import (
    TransportReservationPolicyEvaluator, PolicyDecision, CANONICAL_PAYMENT_METHODS,
)
from app.transport.services.offering_registry import TransportOfferingRegistry


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
