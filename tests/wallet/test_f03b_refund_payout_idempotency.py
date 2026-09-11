"""
F-03b Refund/Payout Idempotency — RED→GREEN tests.

Proves the audit defect in MarketplaceService:

- release_host_payout builds
  ``client_request_id=f"booking_{booking_id}_payout_{uuid4().hex[:12]}"``
- refund_guest builds
  ``client_request_id=f"booking_{booking_id}_refund_{uuid4().hex[:12]}"``

A FRESH uuid4 per call defeats the DB-enforced idempotency in
WalletService.transfer → TransactionRepository.get_or_create
(PostgreSQL ON CONFLICT DO NOTHING on transactions.client_request_id), so a
concurrent duplicate or a retry-after-partial-completion can transfer money
more than once for a single logical booking operation.

Design rules honoured here (F-03b prompt):
- Every transfer is a REAL wallet transfer against the PostgreSQL ledger
  (no mocked WalletService). KYC/fraud checks are mocked only because they are
  orthogonal to idempotency (deterministic pass-through).
- current_user is the PLATFORM account owner, so the real ownership gate in
  WalletService.transfer (from_account.user_id == current_user.id) passes
  without touching authorization semantics.
- Concurrency tests use REAL threads, each with its own Flask app context,
  test request context and DB session (the pattern the existing skipped tests
  lacked).
"""

import threading
import time
import uuid
from contextlib import contextmanager
from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import Mock, patch

import pytest
from flask_login import login_user

from app.accommodation.models.booking import (
    AccommodationBooking,
    AccommodationBookingStatus,
    AccommodationPaymentStatus,
)
from app.accommodation.models.commission import BookingCommission
from app.accommodation.models.property import Property
from app.accommodation.models.room import RoomType
from app.accommodation.services.marketplace_service import MarketplaceService
from app.extensions import db
from app.identity.models.user import User
from app.wallet.models.ledger import EntryType, LedgerEntryModel
from app.wallet.models.transaction import (
    TransactionModel,
    TransactionStatus,
    TransactionType,
)
from app.wallet.repositories.ledger_repository import LedgerRepository
from app.wallet.services.fraud_detection_service import FraudDetectionService
from app.wallet.services.kyc_limit_service import KYCLimitService

REFUND_KEY_TEMPLATE = "booking_{booking_id}_refund"
PAYOUT_KEY_TEMPLATE = "booking_{booking_id}_payout"


# F-03B-TI mock-isolation contract: snapshot the REAL implementations once so we
# can prove, after every guarded run, that nothing leaked and the live attribute
# is the real implementation — never a Mock.
_KYC_CTA_ORIGINAL = KYCLimitService.check_transaction_allowed
_FRAUD_SCORE_ORIGINAL = FraudDetectionService.score_transaction
_FRAUD_BLOCK_ORIGINAL = FraudDetectionService.should_block_transaction


def _real_fn(attr):
    """Underlying function object of a class/static/instance method."""
    return getattr(attr, "__func__", attr)


def _assert_real_impls_restored():
    """Fail loudly if any KYC/fraud mock leaked process-wide (F-03B-TI)."""
    cta = KYCLimitService.check_transaction_allowed
    score = FraudDetectionService.score_transaction
    block = FraudDetectionService.should_block_transaction
    assert not isinstance(cta, Mock), (
        "KYCLimitService.check_transaction_allowed leaked as a Mock"
    )
    assert not isinstance(score, Mock), (
        "FraudDetectionService.score_transaction leaked as a Mock"
    )
    assert not isinstance(block, Mock), (
        "FraudDetectionService.should_block_transaction leaked as a Mock"
    )
    assert _real_fn(cta) is _real_fn(_KYC_CTA_ORIGINAL), (
        "check_transaction_allowed is not the real implementation"
    )
    assert _real_fn(score) is _real_fn(_FRAUD_SCORE_ORIGINAL), (
        "score_transaction is not the real implementation"
    )
    assert _real_fn(block) is _real_fn(_FRAUD_BLOCK_ORIGINAL), (
        "should_block_transaction is not the real implementation"
    )


@contextmanager
def _guarded():
    """Mock KYC/fraud checks and guarantee the REAL implementations are restored
    afterwards — any leak fails this test instead of escaping process-wide."""
    _assert_real_impls_restored()
    try:
        with patch.object(
            KYCLimitService,
            "check_transaction_allowed",
            return_value={"allowed": True, "kyc_level": 4},
        ), patch.object(
            FraudDetectionService,
            "score_transaction",
            return_value={"score": 0, "patterns": []},
        ), patch.object(
            FraudDetectionService,
            "should_block_transaction",
            return_value=False,
        ):
            yield
    finally:
        _assert_real_impls_restored()


def _guarded_call(fn):
    """Run fn with KYC/fraud checks bypassed (orthogonal to F-03b)."""
    with _guarded():
        return fn()


# ---------------- Fixtures ----------------
# `app` and `test_db` come from the central tests/conftest.py.

def _make_user(prefix):
    user = User(
        email=f"{prefix}-{uuid.uuid4().hex[:6]}@example.com",
        username=f"{prefix}-{uuid.uuid4().hex[:6]}",
        password_hash="not-a-real-hash",
        email_verified=True,
        phone_verified=True,
        kyc_level=2,
        is_active=True,
    )
    db.session.add(user)
    db.session.commit()
    return user


def _fund_account(account, amount):
    tx = TransactionModel(
        id=uuid.uuid4(),
        client_request_id=f"f03b-fund-{account.id}-{uuid.uuid4().hex}",
        tx_type=TransactionType.DEPOSIT,
        amount=amount,
        currency="USD",
        status=TransactionStatus.COMPLETED,
        user_id=account.user_id,
    )
    db.session.add(tx)
    db.session.flush()
    db.session.add(
        LedgerEntryModel(
            transaction_id=tx.id,
            account_id=account.id,
            entry_type=EntryType.CREDIT,
            amount=amount,
            currency="USD",
        )
    )
    db.session.commit()


@pytest.fixture
def platform(app, test_db):
    """A real platform USER whose account acts as the escrow (current
    production shape: _get_platform_account_id resolves through the
    user_id-keyed account lookup, and PLATFORM_ORG_ID holds that user id)."""
    with app.app_context():
        from app.wallet.routes import get_or_create_account

        platform_user = _make_user("platform")
        app.config["PLATFORM_ORG_ID"] = str(platform_user.id)
        account = get_or_create_account(platform_user.id, "USD")
        _fund_account(account, Decimal("1000.00"))
        yield {"user_id": platform_user.id, "account_id": str(account.id)}


@pytest.fixture
def guest(app, test_db):
    with app.app_context():
        from app.wallet.routes import get_or_create_account

        user = _make_user("guest")
        account = get_or_create_account(user.id, "USD")
        yield {"user_id": user.id, "account_id": str(account.id)}


@pytest.fixture
def host(app, test_db):
    with app.app_context():
        from app.wallet.routes import get_or_create_account

        user = _make_user("host")
        account = get_or_create_account(user.id, "USD")
        yield {"user_id": user.id, "account_id": str(account.id)}


@contextmanager
def _login_as(app, user_id):
    """test_request_context with the given user logged in."""
    ctx = app.test_request_context()
    ctx.push()
    login_user(db.session.get(User, user_id))
    try:
        yield
    finally:
        ctx.pop()


@pytest.fixture
def held_booking(app, test_db, platform, guest, host):
    with app.app_context():
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
            owner_user_id=host["user_id"],
        )
        db.session.add(prop)
        db.session.commit()

        room_type = RoomType(
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
        db.session.add(room_type)
        db.session.commit()

        booking = AccommodationBooking(
            property_id=prop.id,
            guest_user_id=guest["user_id"],
            host_user_id=host["user_id"],
            check_in=date.today() + timedelta(days=3),
            check_out=date.today() + timedelta(days=5),
            num_nights=2,
            num_guests=2,
            nightly_rate=Decimal("100.00"),
            cleaning_fee=Decimal("20.00"),
            service_fee=Decimal("10.00"),
            total_amount=Decimal("230.00"),
            currency="USD",
            guest_name="Test Guest",
            guest_email="guest@test.com",
            guest_phone="+256700000000",
            payment_status=AccommodationPaymentStatus.PAID.value,
            status=AccommodationBookingStatus.CONFIRMED.value,
            booked_by_user_id=guest["user_id"],
            booking_type="self",
            payment_timing="pay_now",
            payment_method="wallet",
            payment_guaranteed=True,
            guarantee_type="wallet_balance",
        )
        booking.generate_reference()
        db.session.add(booking)
        db.session.commit()

        commission = BookingCommission(
            booking_id=booking.id,
            total_amount=booking.total_amount,
            commission_amount=Decimal("23.00"),
            host_payout=Decimal("207.00"),
            platform_fee_pct=Decimal("10.0"),
            status="held",
            extra_data={
                "booking_reference": booking.booking_reference,
                "property_id": str(booking.property_id),
                "guest_user_id": str(booking.booked_by_user_id),
                "host_user_id": str(booking.host_user_id),
            },
        )
        db.session.add(commission)
        booking.wallet_txn_id = f"txn-charge-{uuid.uuid4().hex[:12]}"
        db.session.commit()
        yield booking.id


# ---------------- Thread helpers ----------------


def _run_two_threads(app, user_id, target):
    """Run target() in two real threads with separate app/request contexts.

    KYC/fraud checks are patched ONCE on the main thread around the entire
    thread-spawn/join (mirroring the thread-safe pattern used by
    tests/wallet/test_withdraw_api.py and test_ledger_concurrency.py). The
    KYC/fraud mocks are orthogonal to F-03b; patching them per-thread via
    _guarded_call races on unittest.mock.patch start/stop and leaks the
    always-allow mock process-wide, breaking unrelated suites.
    """
    original_lookup = MarketplaceService._get_account_for_user

    def _amplified_lookup(uid, currency="USD"):
        """Widen the pre-fix race window: both threads read commission.status
        'held' BEFORE the sleep, then both proceed to the wallet transfer."""
        time.sleep(0.05)
        return original_lookup(uid, currency)

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
                    outcomes.append(target())
                    db.session.remove()
        except Exception as exc:  # pragma: no cover - defensive
            errors.append(exc)

    with patch.object(
        MarketplaceService,
        "_get_account_for_user",
        new=_amplified_lookup,
    ), _guarded():
        threads = [threading.Thread(target=worker) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

    # F-03B-TI: prove nothing leaked and every patched target is the REAL
    # implementation after the concurrent run.
    _assert_real_impls_restored()
    assert MarketplaceService._get_account_for_user is original_lookup, (
        "_get_account_for_user leaked (concurrent mock patch did not restore)"
    )
    assert not errors, f"Thread errors: {errors}"
    return outcomes


def _count_transfers_for(booking_id, kind):
    prefix = f"booking_{booking_id}_{kind}%"
    return (
        db.session.query(TransactionModel)
        .filter(TransactionModel.client_request_id.like(prefix))
        .count()
    )


def _balance(account_id):
    return LedgerRepository().get_balance(account_id, "USD")


def _commission(app, booking_id):
    with app.app_context():
        return BookingCommission.query.filter_by(booking_id=booking_id).first()


# ---------------- Payout idempotency ----------------


class TestPayoutIdempotency:
    def test_sequential_duplicate_payout_single_transfer(
        self, app, platform, host, held_booking
    ):
        """GREEN contract: a second payout attempt is refused and the wallet
        transfer happened exactly once."""
        host_before = _balance(host["account_id"])
        platform_before = _balance(platform["account_id"])

        with _login_as(app, platform["user_id"]):
            ok1, err1 = _guarded_call(
                lambda: MarketplaceService.release_host_payout(held_booking)
            )
            ok2, err2 = _guarded_call(
                lambda: MarketplaceService.release_host_payout(held_booking)
            )

        assert ok1, err1
        assert ok2 is False
        assert "already" in err2.lower()

        assert _count_transfers_for(held_booking, "payout") == 1
        assert _balance(host["account_id"]) == host_before + Decimal("207.00")
        assert _balance(platform["account_id"]) == platform_before - Decimal(
            "207.00"
        )
        assert _commission(app, held_booking).status == "released"

    def test_concurrent_payout_single_transfer(
        self, app, platform, host, held_booking
    ):
        """RED→GREEN: two concurrent releases must move money exactly once."""
        host_before = _balance(host["account_id"])
        platform_before = _balance(platform["account_id"])

        outcomes = _run_two_threads(
            app,
            platform["user_id"],
            lambda: MarketplaceService.release_host_payout(held_booking),
        )

        assert _count_transfers_for(held_booking, "payout") == 1, (
            "Exactly ONE payout transfer expected; "
            f"threads returned {outcomes}"
        )
        assert _balance(host["account_id"]) == host_before + Decimal(
            "207.00"
        ), "Host must be credited exactly once"
        assert _balance(platform["account_id"]) == platform_before - Decimal(
            "207.00"
        ), "Platform must be debited exactly once"
        assert _commission(app, held_booking).status == "released"
        tx = (
            db.session.query(TransactionModel)
            .filter(
                TransactionModel.client_request_id
                == PAYOUT_KEY_TEMPLATE.format(booking_id=held_booking)
            )
            .first()
        )
        assert tx is not None
        ledger_count = (
            db.session.query(LedgerEntryModel)
            .filter_by(transaction_id=tx.id)
            .count()
        )
        assert ledger_count == 2


# ---------------- Refund idempotency ----------------


class TestRefundIdempotency:
    def test_sequential_duplicate_refund_single_transfer(
        self, app, platform, guest, held_booking
    ):
        """GREEN contract: a second refund attempt is refused and the wallet
        transfer happened exactly once."""
        guest_before = _balance(guest["account_id"])
        platform_before = _balance(platform["account_id"])

        with _login_as(app, platform["user_id"]):
            ok1, err1 = _guarded_call(
                lambda: MarketplaceService.refund_guest(
                    held_booking, Decimal("100.00")
                )
            )
            ok2, err2 = _guarded_call(
                lambda: MarketplaceService.refund_guest(
                    held_booking, Decimal("100.00")
                )
            )

        assert ok1, err1
        assert ok2 is False
        assert "already" in err2.lower()

        assert _count_transfers_for(held_booking, "refund") == 1
        assert _balance(guest["account_id"]) == guest_before + Decimal(
            "100.00"
        )
        assert _balance(platform["account_id"]) == platform_before - Decimal(
            "100.00"
        )
        commission = _commission(app, held_booking)
        assert commission.status == "refunded"
        assert commission.refund_amount == Decimal("100.00")

    def test_concurrent_refund_single_transfer(
        self, app, platform, guest, held_booking
    ):
        """RED→GREEN: two concurrent refunds must move money exactly once."""
        guest_before = _balance(guest["account_id"])
        platform_before = _balance(platform["account_id"])

        outcomes = _run_two_threads(
            app,
            platform["user_id"],
            lambda: MarketplaceService.refund_guest(
                held_booking, Decimal("100.00")
            ),
        )

        assert _count_transfers_for(held_booking, "refund") == 1, (
            "Exactly ONE refund transfer expected; "
            f"threads returned {outcomes}"
        )
        assert _balance(guest["account_id"]) == guest_before + Decimal(
            "100.00"
        ), "Guest must be credited exactly once"
        assert _balance(platform["account_id"]) == platform_before - Decimal(
            "100.00"
        ), "Platform must be debited exactly once"
        commission = _commission(app, held_booking)
        assert commission.status == "refunded"
        assert commission.refund_amount == Decimal("100.00")
        tx = (
            db.session.query(TransactionModel)
            .filter(
                TransactionModel.client_request_id
                == REFUND_KEY_TEMPLATE.format(booking_id=held_booking)
            )
            .first()
        )
        assert tx is not None
        ledger_count = (
            db.session.query(LedgerEntryModel)
            .filter_by(transaction_id=tx.id)
            .count()
        )
        assert ledger_count == 2

    def test_refund_retry_after_wallet_commit_converges(
        self, app, platform, guest, held_booking
    ):
        """RED→GREEN: if the wallet leg committed but the business leg failed
        (crash between the two commits), the retry must NOT move money again —
        it converges the business state to the recorded transfer."""
        from app.wallet.services.wallet_service import WalletService

        guest_before = _balance(guest["account_id"])
        platform_before = _balance(platform["account_id"])
        key = REFUND_KEY_TEMPLATE.format(booking_id=held_booking)

        with _login_as(app, platform["user_id"]):
            # Simulate the ORIGINAL attempt: wallet leg committed...
            _guarded_call(
                lambda: WalletService().transfer(
                    from_account_id=platform["account_id"],
                    to_account_id=guest["account_id"],
                    amount=Decimal("100.00"),
                    currency="USD",
                    client_request_id=key,
                    note="Refund: simulated wallet leg",
                )
            )
        # ...but the business leg never ran (commission still 'held').
        assert _commission(app, held_booking).status == "held"

        # Retry via the canonical service — must converge, not double-pay.
        with _login_as(app, platform["user_id"]):
            ok, err = _guarded_call(
                lambda: MarketplaceService.refund_guest(
                    held_booking, Decimal("100.00")
                )
            )
        assert ok, err

        assert _count_transfers_for(held_booking, "refund") == 1, (
            "Retry must reuse the committed transfer, not create a new one"
        )
        assert _balance(guest["account_id"]) == guest_before + Decimal(
            "100.00"
        ), "Guest must be credited exactly once across retry"
        assert _balance(platform["account_id"]) == platform_before - Decimal(
            "100.00"
        ), "Platform must be debited exactly once across retry"
        commission = _commission(app, held_booking)
        assert commission.status == "refunded"
        assert commission.refund_amount == Decimal("100.00")


# ---------------- F-03B-TI: mock isolation / concurrency proof ----------------


class TestMockIsolation:
    """F-03B-TI — prove the F-03b suite leaves the REAL KYC implementation
    installed process-wide (no thread-dependent Mock leakage)."""

    def test_concurrent_run_restores_real_kyc_check(
        self, app, platform, host, held_booking
    ):
        """After the concurrent payout path (real threads, separate app/request
        contexts), every patched target must be the real implementation — not a
        Mock — and the transfer must still have happened exactly once."""
        cta = KYCLimitService.check_transaction_allowed
        score = FraudDetectionService.score_transaction
        block = FraudDetectionService.should_block_transaction
        lookup = MarketplaceService._get_account_for_user

        outcomes = _run_two_threads(
            app,
            platform["user_id"],
            lambda: MarketplaceService.release_host_payout(held_booking),
        )

        assert _count_transfers_for(held_booking, "payout") == 1, (
            f"Concurrent payout moved money more than once: {outcomes}"
        )

        _assert_real_impls_restored()
        assert MarketplaceService._get_account_for_user is lookup, (
            "_get_account_for_user not restored to the real implementation"
        )
        assert _real_fn(KYCLimitService.check_transaction_allowed) is _real_fn(
            cta
        ), "check_transaction_allowed is not the real implementation"
        assert _real_fn(FraudDetectionService.score_transaction) is _real_fn(
            score
        ), "score_transaction is not the real implementation"
        assert _real_fn(FraudDetectionService.should_block_transaction) is _real_fn(
            block
        ), "should_block_transaction is not the real implementation"