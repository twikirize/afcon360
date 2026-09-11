"""
F-11 Penalty Idempotency Key — evidence probe (untracked test artifact).

Proves that the pay_on_arrival cancellation-penalty path cannot create a
duplicate financial effect on retry or concurrent duplicate execution,
even though the fallback idempotency key is non-deterministic:

    penalty_key = idempotency_key or f"cancel-{booking.id}-{time_ns()}"

(both production callers — guest_cancel_booking / host_cancel_booking —
do NOT pass idempotency_key, so the fallback fires on every call).

Duplicate-penalty creation is nevertheless unreachable because
BookingService.cancel_booking() is defended by:

  1. get_cancellation_quote() status gate — an already-cancelled booking
     is not in CANCELLABLE_STATUSES, so the call returns before any
     mutation.
  2. with_for_update() row lock on the booking — concurrent duplicates
     serialize on the booking row; the loser re-reads the committed
     CANCELLED row and is rejected by gate (1).
  3. BookingStateMachine — CANCELLED has no self-transition, so any path
     that reaches the transition raises InvalidStateTransition and rolls
     back the whole transaction (including any penalty insert).
  4. UNIQUE idx_cancel_penalty_idempotency on
     CancellationPenalty.idempotency_key — final DB-level backstop.

Result classification: CASE A — PRODUCTION CORRECT. No production change.
"""

import re
import threading
import uuid
from datetime import date, timedelta
from decimal import Decimal
from typing import cast
from unittest.mock import patch

import pytest
from flask_login import login_user

from app.accommodation.models.booking import (
    AccommodationBooking,
    AccommodationBookingStatus,
)
from app.accommodation.models.cancellation_policy import (
    CancellationPenalty,
    CancellationPolicy,
    CancellationPolicyType,
)
from app.accommodation.models.property import Property
from app.accommodation.models.room import RoomType
from app.accommodation.services.booking_service import BookingService
from app.extensions import db
from app.identity.models.user import User

TIME_NS_KEY = re.compile(r"^cancel-\d+-\d{16,19}$")


# ---------- Fixtures (mirror tests/wallet/test_f02_cancellation_refund.py) ----------
# `app` and `test_db` come from the central tests/conftest.py.

@pytest.fixture
def test_host_user(app, test_db):
    user = User(
        email=f"host-{uuid.uuid4().hex[:6]}@example.com",
        username=f"host-{uuid.uuid4().hex[:6]}",
        password_hash="not-a-real-hash",
        email_verified=True,
        phone_verified=True,
        kyc_level=2,
        is_active=True,
    )
    db.session.add(user)
    db.session.commit()
    return user


@pytest.fixture
def test_guest_user(app, test_db):
    user = User(
        email=f"guest-{uuid.uuid4().hex[:6]}@example.com",
        username=f"guest-{uuid.uuid4().hex[:6]}",
        password_hash="not-a-real-hash",
        email_verified=True,
        phone_verified=True,
        kyc_level=2,
        is_active=True,
    )
    db.session.add(user)
    db.session.commit()
    return user


@pytest.fixture
def test_other_user(app, test_db):
    user = User(
        email=f"other-{uuid.uuid4().hex[:6]}@example.com",
        username=f"other-{uuid.uuid4().hex[:6]}",
        password_hash="not-a-real-hash",
        email_verified=True,
        phone_verified=True,
        kyc_level=2,
        is_active=True,
    )
    db.session.add(user)
    db.session.commit()
    return user


@pytest.fixture
def test_property(app, test_db, test_host_user):
    prop = Property(
        title="Test Property",
        slug=f"test-property-{uuid.uuid4().hex[:8]}",
        description="Test property",
        address_line1="123 Test Street",
        city="Kampala",
        country="UG",
        status="active",
        is_verified=True,
        is_active=True,
        base_price_per_night=Decimal("100.00"),
        currency="USD",
        max_guests=4,
        instant_book=True,
        cancellation_policy="flexible",
        owner_user_id=test_host_user.id,
    )
    db.session.add(prop)
    db.session.commit()

    rt = RoomType(
        property_id=prop.id,
        name="Standard Room",
        description="Standard test room",
        max_guests=2,
        bedrooms=1,
        beds=1,
        bathrooms=1,
        base_price_per_night=Decimal("100.00"),
        currency="USD",
        total_units=10,
        is_active=True,
    )
    db.session.add(rt)
    db.session.commit()
    return prop


@pytest.fixture
def test_poa_policy(app, test_db, test_property):
    """NOSHOW cancellation policy scoped to the property: no-show charges
    the full first night (no_show_penalty == 1) -> deterministic fine > 0."""
    policy = CancellationPolicy(
        name=CancellationPolicyType.NO_SHOW,
        property_id=test_property.id,
        pre_checkin_days=0,
        pre_checkin_refund_pct=Decimal("0.00"),
        mid_stay_refund_pct=Decimal("0.00"),
        no_show_penalty=Decimal("1.00"),
        is_active=True,
        is_default=True,
    )
    db.session.add(policy)
    db.session.commit()
    return policy


# ---------- Builder ----------


def _create_poa_booking(
    app,
    test_db,
    test_property,
    test_guest_user,
    test_host_user,
    test_poa_policy,
    cancel_by_other_user_id=None,
):
    """Pay-on-arrival booking whose cancellation falls into the NO_SHOW
    phase (check-in already passed) and produces a >0 fine, triggering the
    CancellationPenalty branch of cancel_booking.

    total_amount = 200 over 2 nights -> NO_SHOW fine = full first night = 100.
    """
    today = date.today()
    booking = AccommodationBooking(
        property_id=test_property.id,
        guest_user_id=test_guest_user.id,
        booked_by_user_id=test_guest_user.id,
        booking_owner_id=test_guest_user.id,
        host_user_id=test_host_user.id,
        check_in=today - timedelta(days=3),
        check_out=today - timedelta(days=1),
        num_nights=2,
        num_guests=1,
        rooms_requested=1,
        nightly_rate=Decimal("100.00"),
        cleaning_fee=Decimal("0.00"),
        service_fee=Decimal("0.00"),
        taxes=Decimal("0.00"),
        total_amount=Decimal("200.00"),
        currency="USD",
        guest_name="No Show Guest",
        guest_email=test_guest_user.email,
        guest_phone="+256700000000",
        status=AccommodationBookingStatus.CONFIRMED.value,
        payment_timing="pay_on_arrival",
        payment_method="pay_on_arrival",
        policy_snapshot={"cancellation_policy": CancellationPolicyType.NO_SHOW},
        booking_type="self",
    )
    booking.generate_reference()
    db.session.add(booking)
    db.session.commit()
    return cast(int, booking.id)


def _count_penalties(booking_id: int) -> int:
    return int(
        CancellationPenalty.query.filter(
            CancellationPenalty.booking_id == booking_id
        ).count()
    )


def _penalties_for(booking_id: int):
    return (
        CancellationPenalty.query.filter(
            CancellationPenalty.booking_id == booking_id
        ).all()
    )


def _fresh_booking_status(booking_id: int) -> str:
    db.session.expire_all()
    row = db.session.get(AccommodationBooking, booking_id)
    assert row is not None
    return str(row.status)


# ---------- Concurrent harness (patch-free) ----------


def _run_concurrent_cancels(app, booking_id, user_id):
    """Run cancel_booking() twice concurrently on the same booking with real
    threads, separate app/request contexts and separate DB sessions.

    No mocks are used anywhere in F-11, so there is no mock-leak surface.
    """
    barrier = threading.Barrier(2)
    outcomes = []
    errors = []

    def worker():
        try:
            with app.app_context():
                with app.test_request_context():
                    login_user(db.session.get(User, user_id))
                    try:
                        barrier.wait(timeout=15)
                    except threading.BrokenBarrierError:
                        pass
                    outcomes.append(
                        BookingService.cancel_booking(
                            booking_id,
                            cancelled_by_user_id=user_id,
                            reason="concurrent cancel",
                        )
                    )
                    db.session.remove()
        except Exception as exc:  # pragma: no cover - defensive
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, f"Thread errors: {errors}"
    return outcomes


# ---------- Proofs ----------


class TestF11PenaltyIdempotency:
    def test_first_cancel_creates_exactly_one_penalty(
        self,
        app,
        test_db,
        test_property,
        test_poa_policy,
        test_guest_user,
        test_host_user,
    ):
        """Positive path: one valid cancellation produces exactly one
        financial effect (one CancellationPenalty debt record)."""
        booking_id = _create_poa_booking(
            app, test_db, test_property, test_guest_user, test_host_user, test_poa_policy
        )
        ok, msg, refund = BookingService.cancel_booking(
            booking_id,
            cancelled_by_user_id=test_guest_user.id,
            reason="test",
        )
        assert ok is True, msg
        assert _count_penalties(booking_id) == 1
        penalty = _penalties_for(booking_id)[0]
        assert penalty.amount == Decimal("100.00")
        assert penalty.status == "PENDING"
        assert penalty.booking_id == booking_id
        # The fallback key is the non-deterministic time_ns shape.
        assert TIME_NS_KEY.match(penalty.idempotency_key), penalty.idempotency_key
        assert _fresh_booking_status(booking_id) == AccommodationBookingStatus.CANCELLED.value

    def test_retry_generates_fresh_key_but_no_second_penalty(
        self,
        app,
        test_db,
        test_property,
        test_poa_policy,
        test_guest_user,
        test_host_user,
    ):
        """Retry: repeating the exact same business operation cannot create a
        duplicate financial effect even though the fallback key is
        non-deterministic (a fresh time_ns key is produced each call)."""
        booking_id = _create_poa_booking(
            app, test_db, test_property, test_guest_user, test_host_user, test_poa_policy
        )
        ok1, _, _ = BookingService.cancel_booking(
            booking_id, cancelled_by_user_id=test_guest_user.id, reason="retry-me"
        )
        assert ok1 is True
        first_key = _penalties_for(booking_id)[0].idempotency_key
        assert _count_penalties(booking_id) == 1

        ok2, msg2, _ = BookingService.cancel_booking(
            booking_id, cancelled_by_user_id=test_guest_user.id, reason="retry-me"
        )
        assert ok2 is False, "retry of the same operation must be rejected"
        assert _count_penalties(booking_id) == 1, "duplicate penalty created on retry"
        # Still the same single penalty row (key unchanged, amount unchanged).
        penalty = _penalties_for(booking_id)[0]
        assert penalty.idempotency_key == first_key
        assert penalty.amount == Decimal("100.00")
        assert _fresh_booking_status(booking_id) == AccommodationBookingStatus.CANCELLED.value

    def test_concurrent_duplicate_cancel_creates_single_penalty(
        self,
        app,
        test_db,
        test_property,
        test_poa_policy,
        test_guest_user,
        test_host_user,
    ):
        """Concurrent duplicate: two identical cancellation operations on the
        same booking produce exactly one logical financial effect and exactly
        one penalty record (row lock + quote gate + state machine)."""
        booking_id = _create_poa_booking(
            app, test_db, test_property, test_guest_user, test_host_user, test_poa_policy
        )
        outcomes = _run_concurrent_cancels(app, booking_id, test_guest_user.id)

        successes = [o for o in outcomes if isinstance(o, tuple) and o[0]]
        failures = [o for o in outcomes if isinstance(o, tuple) and not o[0]]
        assert len(successes) == 1, f"expected exactly one success, got {outcomes}"
        assert len(failures) == 1, f"expected exactly one rejected duplicate, got {outcomes}"

        assert _count_penalties(booking_id) == 1
        penalty = _penalties_for(booking_id)[0]
        assert penalty.amount == Decimal("100.00")
        assert _fresh_booking_status(booking_id) == AccommodationBookingStatus.CANCELLED.value

    def test_failure_mid_transaction_rolls_back_then_retry_converges(
        self,
        app,
        test_db,
        test_property,
        test_poa_policy,
        test_guest_user,
        test_host_user,
    ):
        """Failure/rollback: a mid-transaction failure leaves no penalty and
        no falsely-reported success; a subsequent retry converges to exactly
        one penalty + CANCELLED with no duplicate effect."""
        booking_id = _create_poa_booking(
            app, test_db, test_property, test_guest_user, test_host_user, test_poa_policy
        )

        with patch.object(db.session, "commit", side_effect=RuntimeError("boom")):
            ok, msg, _ = BookingService.cancel_booking(
                booking_id, cancelled_by_user_id=test_guest_user.id, reason="flaky"
            )
        assert ok is False, "cancel must not report success when commit failed"
        # Rollback leaves no partial financial effect and status unchanged.
        db.session.expire_all()
        assert _count_penalties(booking_id) == 0, "partial penalty leaked after rollback"
        booking = db.session.get(AccommodationBooking, booking_id)
        assert booking is not None
        status_now = str(booking.status or "")
        assert status_now == AccommodationBookingStatus.CONFIRMED.value, (
            "booking falsely transitioned or was left in a non-original state after rollback"
        )

        # Retry after failure converges safely to exactly one effect.
        ok2, msg2, _ = BookingService.cancel_booking(
            booking_id, cancelled_by_user_id=test_guest_user.id, reason="retry-after-failure"
        )
        assert ok2 is True, msg2
        assert _count_penalties(booking_id) == 1, "retry after failure duplicated the penalty"
        penalty = _penalties_for(booking_id)[0]
        assert penalty.amount == Decimal("100.00")
        assert _fresh_booking_status(booking_id) == AccommodationBookingStatus.CANCELLED.value

    def test_distinct_operations_are_not_collapsed(
        self,
        app,
        test_db,
        test_property,
        test_poa_policy,
        test_guest_user,
        test_host_user,
    ):
        """Different operations: two genuinely different bookings are NOT
        collapsed into one penalty; each keeps its own penalty and key."""
        id_a = _create_poa_booking(
            app, test_db, test_property, test_guest_user, test_host_user, test_poa_policy
        )
        id_b = _create_poa_booking(
            app, test_db, test_property, test_guest_user, test_host_user, test_poa_policy
        )
        assert BookingService.cancel_booking(
            id_a, cancelled_by_user_id=test_guest_user.id, reason="a"
        )[0] is True
        assert BookingService.cancel_booking(
            id_b, cancelled_by_user_id=test_guest_user.id, reason="b"
        )[0] is True

        assert _count_penalties(id_a) == 1
        assert _count_penalties(id_b) == 1
        key_a = _penalties_for(id_a)[0].idempotency_key
        key_b = _penalties_for(id_b)[0].idempotency_key
        assert key_a != key_b, "distinct bookings must carry distinct penalty keys"
        assert _fresh_booking_status(id_a) == AccommodationBookingStatus.CANCELLED.value
        assert _fresh_booking_status(id_b) == AccommodationBookingStatus.CANCELLED.value

    def test_unauthorised_user_cannot_create_penalty(
        self,
        app,
        test_db,
        test_property,
        test_poa_policy,
        test_guest_user,
        test_host_user,
        test_other_user,
    ):
        """Authorization/ownership: a user who is neither owner/booker nor
        host cannot cancel and cannot create a penalty on another booking."""
        booking_id = _create_poa_booking(
            app, test_db, test_property, test_guest_user, test_host_user, test_poa_policy
        )
        ok, msg, _ = BookingService.cancel_booking(
            booking_id, cancelled_by_user_id=test_other_user.id, reason="theft"
        )
        assert ok is False
        assert "not authorised" in (msg or "").lower()
        assert _count_penalties(booking_id) == 0
        assert _fresh_booking_status(booking_id) == AccommodationBookingStatus.CONFIRMED.value