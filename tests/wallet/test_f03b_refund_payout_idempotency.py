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
- Payout tests act as the check-in-confirming host; exceptional refund approval
  tests use an independent platform administrator. Routine policy refunds use
  the authenticated cancellation actor plus frozen policy and reconciliation.
  The escrow transfer is system-executed and never asks the guest to enter a PIN.
- Concurrency tests use REAL threads, each with its own Flask app context,
  test request context and DB session (the pattern the existing skipped tests
  lacked).
"""

import threading
import time
import uuid
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import Mock, patch

import pytest
from flask_login import login_user

from app.accommodation.models.booking import (
    AccommodationBooking,
    AccommodationBookingStatus,
    AccommodationPaymentStatus,
    BookingStatusHistory,
)
from app.accommodation.models.commission import BookingCommission
from app.audit.models import AuditLog
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


def _grant_global_role(user, role_name):
    from app.identity.models.roles_permission import get_or_create_role
    from app.identity.models.user import UserRole

    # Do not rewrite seeded role hierarchy levels as a side effect of a test.
    role = get_or_create_role(role_name)
    if not any(getattr(user_role, "role_id", None) == role.id for user_role in user.roles):
        db.session.add(UserRole(user_id=user.id, role_id=role.id))
        db.session.commit()


@pytest.fixture
def platform_admin(app, test_db):
    with app.app_context():
        user = _make_user("platform-admin")
        _grant_global_role(user, "admin")
        yield {"user_id": user.id}


@pytest.fixture
def platform_admin_two(app, test_db):
    with app.app_context():
        user = _make_user("platform-admin-two")
        _grant_global_role(user, "super_admin")
        yield {"user_id": user.id}


@pytest.fixture
def accommodation_admin(app, test_db):
    with app.app_context():
        user = _make_user("accommodation-admin")
        _grant_global_role(user, "accommodation_admin")
        yield {"user_id": user.id}


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
            amount_paid=Decimal("230.00"),
            status=AccommodationBookingStatus.CHECKED_IN.value,
            checked_in_by=host["user_id"],
            is_checked_in=True,
            checked_in_at=datetime.now(timezone.utc),
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

        # Build a real completed charge record and its balanced ledger legs.
        from app.wallet.models.ledger import AccountModel
        guest_account = db.session.get(AccountModel, uuid.UUID(guest["account_id"]))
        platform_account = db.session.get(AccountModel, uuid.UUID(platform["account_id"]))
        _fund_account(guest_account, Decimal("230.00"))
        charge_id = uuid.uuid4()
        charge = TransactionModel(
            id=charge_id,
            client_request_id=f"booking_{booking.id}_charge_fixture",
            tx_type=TransactionType.TRANSFER.value,
            status=TransactionStatus.COMPLETED.value,
            amount=Decimal("230.00"),
            currency="USD",
            user_id=guest["user_id"],
            recipient_user_id=platform["user_id"],
            account_id=guest_account.id,
            tx_metadata={
                "booking_id": str(booking.id),
                "booking_reference": booking.booking_reference,
            },
            completed_at=datetime.now(timezone.utc),
        )
        db.session.add(charge)
        db.session.flush()
        db.session.add_all([
            LedgerEntryModel(
                transaction_id=charge_id,
                account_id=guest_account.id,
                entry_type=EntryType.DEBIT.value,
                amount=Decimal("230.00"),
                currency="USD",
            ),
            LedgerEntryModel(
                transaction_id=charge_id,
                account_id=platform_account.id,
                entry_type=EntryType.CREDIT.value,
                amount=Decimal("230.00"),
                currency="USD",
            ),
        ])
        booking.wallet_txn_id = str(charge_id)
        booking.paid_at = datetime.now(timezone.utc)
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


def _frozen_policy_snapshot(
    booking,
    refund_amount,
    *,
    workflow_state="screening",
    requester_user_id=None,
    risk_flags=None,
):
    rules = {
        "snapshot_version": 2,
        "name": "FLEX",
        "pre_checkin_days": 1,
        "pre_checkin_refund_pct": "100.00",
        "mid_stay_refund_pct": "100.00",
        "no_show_penalty": "0.00",
        "pay_on_arrival_penalty_type": "debt",
        "deposit_refundable": True,
        "refundable_cleaning_fee": False,
        "refundable_service_fee": False,
        "refundable_taxes": False,
        "source_property_id": booking.property_id,
        "captured_at": datetime.now(timezone.utc).isoformat(),
    }
    rules["hmac_sha256"] = MarketplaceService.sign_cancellation_policy_rules(
        booking, rules
    )
    amount = Decimal(str(refund_amount)).quantize(Decimal("0.01"))
    outcome = {
        "policy": "FLEX",
        "phase": "pre_checkin",
        "refundable_base": "230.00",
        "refund": str(amount),
        "fine": str(Decimal("230.00") - amount),
        "nights_remaining": 0,
        "days_until_checkin": 3,
        "policy_snapshot_version": 2,
    }
    snapshot = {
        "cancellation_policy": "FLEX",
        "cancellation_policy_rules": rules,
        "cancellation_outcome": outcome,
        "refund_workflow": {
            "state": workflow_state,
            "proposed_amount": str(amount),
            "policy_amount": str(amount),
            "currency": "USD",
            "payment_method": "wallet",
            "requested_by_user_id": requester_user_id,
            "request_reason": "Test refund exception" if workflow_state == "pending_human_review" else "",
            "risk_flags": list(risk_flags or []),
            "submitted_at": datetime.now(timezone.utc).isoformat(),
        },
    }
    booking.policy_snapshot = snapshot
    snapshot["cancellation_outcome_hmac"] = (
        MarketplaceService.sign_cancellation_outcome(booking, outcome)
    )
    booking.policy_snapshot = snapshot
    workflow = snapshot["refund_workflow"]
    workflow["hmac_sha256"] = MarketplaceService.sign_refund_workflow(
        booking, workflow
    )
    snapshot["refund_workflow"] = workflow
    booking.policy_snapshot = snapshot
    return snapshot


def _prepare_cancelled_booking_for_review(
    app,
    booking_id,
    guest_id,
    *,
    workflow_state="pending_human_review",
    requester_user_id=None,
    payment_method="wallet",
    refund_amount=Decimal("230.00"),
    risk_flags=None,
):
    # Use the fixture's active app-context session. Opening a nested app
    # context here creates a second scoped SQLAlchemy session while the
    # held_booking fixture keeps the outer identity map alive. The test would
    # then read stale booking JSON/status and test the wrong actor.
    booking = db.session.get(AccommodationBooking, booking_id)
    booking.status = AccommodationBookingStatus.CANCELLED.value
    booking.cancelled_by_user_id = guest_id
    booking.cancellation_reason = "Guest cancellation test"
    booking.payment_method = payment_method
    booking.payment_status = AccommodationPaymentStatus.PAID.value
    booking.amount_paid = Decimal("230.00")
    booking.policy_snapshot = _frozen_policy_snapshot(
        booking,
        refund_amount,
        workflow_state=workflow_state,
        requester_user_id=requester_user_id,
        risk_flags=risk_flags,
    )
    db.session.commit()


# ---------------- Payout idempotency ----------------


class TestEscrowHumanAuthorization:
    def test_payout_requires_authorized_checkin_actor(
        self, app, platform, held_booking
    ):
        with _login_as(app, platform["user_id"]):
            ok, error = MarketplaceService.release_host_payout(held_booking)

        assert ok is False
        assert "authorised" in error.lower()
        assert _count_transfers_for(held_booking, "payout") == 0

    def test_native_bearer_user_can_authorize_own_policy_refund_without_web_session(
        self, app, guest, platform, held_booking
    ):
        """A verified bearer actor can use this boundary without Flask-Login."""
        _prepare_cancelled_booking_for_review(
            app,
            held_booking,
            guest["user_id"],
            workflow_state="screening",
            refund_amount=Decimal("230.00"),
        )
        guest_before = _balance(guest["account_id"])
        platform_before = _balance(platform["account_id"])

        # Deliberately do not call _login_as(): native mobile has no cookie session.
        ok, error = _guarded_call(
            lambda: MarketplaceService.refund_guest(
                held_booking,
                Decimal("230.00"),
                authorized_user_id=guest["user_id"],
            )
        )

        assert ok, error
        assert _count_transfers_for(held_booking, "refund") == 1
        assert _balance(guest["account_id"]) == guest_before + Decimal("230.00")
        assert _balance(platform["account_id"]) == platform_before - Decimal("230.00")
        refund_tx = (
            db.session.query(TransactionModel)
            .filter_by(client_request_id=REFUND_KEY_TEMPLATE.format(booking_id=held_booking))
            .first()
        )
        assert refund_tx is not None
        assert refund_tx.tx_metadata["authorized_by_user_id"] == guest["user_id"]
        assert refund_tx.tx_metadata["authorization_source"] == "booking_time_policy"

    def test_guest_policy_refund_is_automatic_without_wallet_pin(
        self, app, guest, platform, held_booking
    ):
        _prepare_cancelled_booking_for_review(
            app,
            held_booking,
            guest["user_id"],
            workflow_state="screening",
            refund_amount=Decimal("230.00"),
        )
        guest_before = _balance(guest["account_id"])
        platform_before = _balance(platform["account_id"])

        with _login_as(app, guest["user_id"]):
            ok, error = _guarded_call(
                lambda: MarketplaceService.refund_guest(
                    held_booking, Decimal("230.00")
                )
            )

        assert ok, error
        assert _count_transfers_for(held_booking, "refund") == 1
        assert _balance(guest["account_id"]) == guest_before + Decimal("230.00")
        assert _balance(platform["account_id"]) == platform_before - Decimal("230.00")
        refund_tx = (
            db.session.query(TransactionModel)
            .filter_by(client_request_id=REFUND_KEY_TEMPLATE.format(booking_id=held_booking))
            .first()
        )
        assert refund_tx is not None
        assert refund_tx.tx_metadata["authorization_source"] == "booking_time_policy"
        assert refund_tx.tx_metadata["authorized_by_user_id"] == guest["user_id"]
        assert refund_tx.tx_metadata["approved_by_user_id"] is None
        commission = _commission(app, held_booking)
        assert commission.status == "refunded"
        assert commission.refund_amount == Decimal("230.00")

    def test_accommodation_admin_can_approve_exception_refund(
        self, app, guest, host, accommodation_admin, held_booking
    ):
        _prepare_cancelled_booking_for_review(
            app,
            held_booking,
            guest["user_id"],
            requester_user_id=host["user_id"],
        )
        with _login_as(app, accommodation_admin["user_id"]):
            ok, error = _guarded_call(
                lambda: MarketplaceService.refund_guest_approved(
                    held_booking,
                    Decimal("230.00"),
                    approval_reason="Accommodation administrator reviewed the exception evidence",
                )
            )

        assert ok, error
        refund_tx = (
            db.session.query(TransactionModel)
            .filter_by(client_request_id=REFUND_KEY_TEMPLATE.format(booking_id=held_booking))
            .first()
        )
        assert refund_tx is not None
        assert refund_tx.tx_metadata["approved_by_user_id"] == accommodation_admin["user_id"]
        assert refund_tx.tx_metadata["authorization_source"] == "platform_human_review"
        history = BookingStatusHistory.query.filter_by(
            booking_id=held_booking,
            trigger="refund_ledger_settled",
        ).one()
        assert history.changed_by == accommodation_admin["user_id"]
        assert history.change_metadata["authorization"]["approval_reason"].startswith(
            "Accommodation administrator"
        )


    def test_policy_partial_refund_is_automatic_and_not_marked_full(
        self, app, guest, platform, held_booking
    ):
        _prepare_cancelled_booking_for_review(
            app,
            held_booking,
            guest["user_id"],
            workflow_state="screening",
            refund_amount=Decimal("100.00"),
        )
        with _login_as(app, guest["user_id"]):
            ok, error = _guarded_call(
                lambda: MarketplaceService.refund_guest(
                    held_booking,
                    Decimal("100.00"),
                )
            )

        assert ok, error
        booking = db.session.get(AccommodationBooking, held_booking)
        commission = _commission(app, held_booking)
        assert booking.refund_amount == Decimal("100.00")
        assert booking.payment_status == AccommodationPaymentStatus.PARTIAL_REFUND.value
        assert booking.status == AccommodationBookingStatus.CANCELLED.value
        assert commission.status == "partially_refunded"
        assert commission.refund_amount == Decimal("100.00")
        assert booking.policy_snapshot["refund_workflow"]["state"] == "partially_refunded"
        assert booking.policy_snapshot["refund_workflow"]["remaining_escrow_amount"] == "130.00"
        assert _count_transfers_for(held_booking, "refund") == 1


    def test_zero_policy_refund_can_be_requested_as_an_exception(
        self, app, guest, host, platform_admin, platform, held_booking
    ):
        _prepare_cancelled_booking_for_review(
            app,
            held_booking,
            guest["user_id"],
            workflow_state="pending_human_review",
            requester_user_id=guest["user_id"],
            refund_amount=Decimal("0.00"),
            risk_flags=["human_review_requested"],
        )
        booking = db.session.get(AccommodationBooking, held_booking)
        assert booking.policy_snapshot["cancellation_outcome"]["refund"] == "0.00"
        assert booking.policy_snapshot["refund_workflow"]["state"] == "pending_human_review"
        assert _count_transfers_for(held_booking, "refund") == 0

        with _login_as(app, platform_admin["user_id"]):
            ok, error = _guarded_call(
                lambda: MarketplaceService.refund_guest_approved(
                    held_booking,
                    Decimal("75.00"),
                    approval_reason="Guest requested an exception to the non-refundable policy; evidence reviewed",
                )
            )

        assert ok, error
        booking = db.session.get(AccommodationBooking, held_booking)
        assert booking.refund_amount == Decimal("75.00")
        assert booking.payment_status == AccommodationPaymentStatus.PARTIAL_REFUND.value
        assert booking.policy_snapshot["refund_workflow"]["state"] == "partially_refunded"
        assert _count_transfers_for(held_booking, "refund") == 1

    def test_provider_request_cannot_impersonate_another_authenticated_user(
        self, app, guest, host, held_booking
    ):
        with _login_as(app, guest["user_id"]):
            ok, error = MarketplaceService.submit_refund_review(
                held_booking,
                Decimal("75.00"),
                "Host requested a manual provider refund",
                requested_by_user_id=host["user_id"],
                request_source="host_manual_refund",
            )

        assert ok is False
        assert "authenticated property manager" in error.lower()
        booking = db.session.get(AccommodationBooking, held_booking)
        assert booking.policy_snapshot.get("refund_workflow", {}).get("state") != "pending_human_review"
        assert _count_transfers_for(held_booking, "refund") == 0

    def test_wallet_refund_execution_failure_is_durably_queued_for_review(
        self, app, guest, held_booking
    ):
        from app.wallet.services.wallet_service import WalletService

        _prepare_cancelled_booking_for_review(
            app,
            held_booking,
            guest["user_id"],
            workflow_state="screening",
            refund_amount=Decimal("230.00"),
        )
        with _login_as(app, guest["user_id"]):
            with patch.object(
                WalletService,
                "transfer",
                return_value={"status": "failed", "error": "wallet temporarily unavailable"},
            ):
                ok, message = MarketplaceService.refund_guest(
                    held_booking,
                    Decimal("230.00"),
                )

        assert ok is False
        assert "platform review queue" in message.lower()
        booking = db.session.get(AccommodationBooking, held_booking)
        workflow = booking.policy_snapshot["refund_workflow"]
        assert workflow["state"] == "pending_human_review"
        assert "refund_execution_reconciliation_failed" in workflow["risk_flags"]
        assert "wallet did not confirm" in workflow["last_error"].lower()
        assert booking.refunded_at is None
        assert booking.refund_amount in (None, Decimal("0.00"))
        assert _count_transfers_for(held_booking, "refund") == 0

        history = BookingStatusHistory.query.filter_by(
            booking_id=held_booking,
            trigger="refund_execution_reconciliation_queued",
        ).one()
        assert history.changed_by == guest["user_id"]
        assert history.change_metadata["risk_flag"] == (
            "refund_execution_reconciliation_failed"
        )


    def test_tampered_policy_snapshot_queues_human_review_without_transfer(
        self, app, guest, held_booking
    ):
        _prepare_cancelled_booking_for_review(
            app,
            held_booking,
            guest["user_id"],
            workflow_state="screening",
            refund_amount=Decimal("230.00"),
        )
        booking = db.session.get(AccommodationBooking, held_booking)
        snapshot = dict(booking.policy_snapshot)
        rules = dict(snapshot["cancellation_policy_rules"])
        rules["pre_checkin_refund_pct"] = "1.00"
        # Deliberately keep the original HMAC to prove the integrity gate.
        snapshot["cancellation_policy_rules"] = rules
        booking.policy_snapshot = snapshot
        db.session.commit()

        with _login_as(app, guest["user_id"]):
            ok, message = MarketplaceService.refund_guest(
                held_booking, Decimal("230.00")
            )

        assert ok is True
        assert "queue" in message.lower()
        booking = db.session.get(AccommodationBooking, held_booking)
        workflow = booking.policy_snapshot["refund_workflow"]
        assert workflow["state"] == "pending_human_review"
        assert "booking_time_policy_snapshot_integrity_failed" in workflow["risk_flags"]
        assert _count_transfers_for(held_booking, "refund") == 0
        assert booking.refunded_at is None

    def test_policy_integrity_exception_needs_explicit_admin_acknowledgement(
        self, app, guest, platform_admin, held_booking
    ):
        _prepare_cancelled_booking_for_review(
            app,
            held_booking,
            guest["user_id"],
            workflow_state="screening",
            refund_amount=Decimal("230.00"),
        )
        booking = db.session.get(AccommodationBooking, held_booking)
        snapshot = dict(booking.policy_snapshot)
        rules = dict(snapshot["cancellation_policy_rules"])
        rules["pre_checkin_refund_pct"] = "1.00"
        snapshot["cancellation_policy_rules"] = rules
        booking.policy_snapshot = snapshot
        db.session.commit()

        with _login_as(app, guest["user_id"]):
            queued, message = MarketplaceService.refund_guest(
                held_booking, Decimal("230.00")
            )
        assert queued is True
        assert "queue" in message.lower()

        with _login_as(app, platform_admin["user_id"]):
            first_ok, first_error = MarketplaceService.refund_guest_approved(
                held_booking,
                Decimal("230.00"),
                approval_reason="Reviewed the booking and policy evidence",
            )
        assert first_ok is False
        assert "integrity" in first_error.lower()
        assert _count_transfers_for(held_booking, "refund") == 0

        with _login_as(app, platform_admin["user_id"]):
            approved, approval_error = _guarded_call(
                lambda: MarketplaceService.refund_guest_approved(
                    held_booking,
                    Decimal("230.00"),
                    approval_reason="I checked the original payment and independently approved this integrity exception",
                    integrity_exception_acknowledged=True,
                )
            )

        assert approved, approval_error
        booking = db.session.get(AccommodationBooking, held_booking)
        workflow = booking.policy_snapshot["refund_workflow"]
        assert workflow["state"] == "refunded"
        assert workflow["integrity_exception_acknowledged_by_user_id"] == platform_admin["user_id"]
        assert _count_transfers_for(held_booking, "refund") == 1

    def test_tampered_cancellation_outcome_queues_review_without_transfer(
        self, app, guest, held_booking
    ):
        _prepare_cancelled_booking_for_review(
            app,
            held_booking,
            guest["user_id"],
            workflow_state="screening",
            refund_amount=Decimal("230.00"),
        )
        booking = db.session.get(AccommodationBooking, held_booking)
        snapshot = dict(booking.policy_snapshot)
        outcome = dict(snapshot["cancellation_outcome"])
        outcome["refund"] = "100.00"
        outcome["fine"] = "130.00"
        # Keep both signatures unchanged to simulate a DB-only edit.
        snapshot["cancellation_outcome"] = outcome
        booking.policy_snapshot = snapshot
        db.session.commit()

        with _login_as(app, guest["user_id"]):
            ok, message = MarketplaceService.refund_guest(
                held_booking, Decimal("100.00")
            )

        assert ok is True
        assert "queue" in message.lower()
        booking = db.session.get(AccommodationBooking, held_booking)
        workflow = booking.policy_snapshot["refund_workflow"]
        assert workflow["state"] == "pending_human_review"
        assert "cancellation_outcome_integrity_failed" in workflow["risk_flags"]
        assert MarketplaceService.verify_refund_workflow(
            booking, workflow
        )
        assert _count_transfers_for(held_booking, "refund") == 0
        assert booking.refunded_at is None

    def test_tampered_refund_workflow_state_queues_review_without_transfer(
        self, app, guest, held_booking
    ):
        _prepare_cancelled_booking_for_review(
            app,
            held_booking,
            guest["user_id"],
            workflow_state="screening",
            refund_amount=Decimal("230.00"),
        )
        booking = db.session.get(AccommodationBooking, held_booking)
        snapshot = dict(booking.policy_snapshot)
        workflow = dict(snapshot["refund_workflow"])
        workflow["state"] = "pending_human_review"
        workflow["risk_flags"] = []
        snapshot["refund_workflow"] = workflow
        booking.policy_snapshot = snapshot
        db.session.commit()

        with _login_as(app, guest["user_id"]):
            ok, message = MarketplaceService.refund_guest(
                held_booking, Decimal("230.00")
            )

        assert ok is True
        assert "integrity" in message.lower()
        booking = db.session.get(AccommodationBooking, held_booking)
        workflow = booking.policy_snapshot["refund_workflow"]
        assert workflow["state"] == "pending_human_review"
        assert "refund_workflow_integrity_failed" in workflow["risk_flags"]
        assert MarketplaceService.verify_refund_workflow(booking, workflow)
        assert _count_transfers_for(held_booking, "refund") == 0

    def test_guest_and_host_cannot_approve_platform_review(
        self, app, guest, host, held_booking
    ):
        _prepare_cancelled_booking_for_review(
            app,
            held_booking,
            guest["user_id"],
            requester_user_id=host["user_id"],
        )
        # Both business actors also hold an admin role in this test. They must
        # still be blocked by the separation-of-duties rule, not merely by RBAC.
        with app.app_context():
            _grant_global_role(db.session.get(User, guest["user_id"]), "admin")
            _grant_global_role(db.session.get(User, host["user_id"]), "admin")

        with _login_as(app, guest["user_id"]):
            guest_ok, guest_error = MarketplaceService.refund_guest_approved(
                held_booking,
                Decimal("230.00"),
                approval_reason="Guest attempts self approval",
            )
        with _login_as(app, host["user_id"]):
            host_ok, host_error = MarketplaceService.refund_guest_approved(
                held_booking,
                Decimal("230.00"),
                approval_reason="Host attempts provider self approval",
            )

        assert guest_ok is False
        assert host_ok is False
        assert "cancellation actor" in guest_error.lower()
        assert "host" in host_error.lower()
        assert _count_transfers_for(held_booking, "refund") == 0

    def test_property_owner_with_platform_admin_role_cannot_review_own_provider_case(
        self, app, guest, host, held_booking
    ):
        _prepare_cancelled_booking_for_review(
            app,
            held_booking,
            guest["user_id"],
            requester_user_id=host["user_id"],
        )
        with app.app_context():
            property_owner = _make_user("provider-property-owner")
            _grant_global_role(property_owner, "admin")
            booking = db.session.get(AccommodationBooking, held_booking)
            prop = db.session.get(Property, booking.property_id)
            prop.owner_user_id = property_owner.id
            db.session.commit()
            owner_id = property_owner.id

        with _login_as(app, owner_id):
            approve_ok, approve_error = MarketplaceService.refund_guest_approved(
                held_booking,
                Decimal("230.00"),
                approval_reason="Provider-side property owner attempts self-review",
            )
        with _login_as(app, owner_id):
            reject_ok, reject_error = MarketplaceService.reject_refund_review(
                held_booking,
                "Provider-side owner attempts to reject a refund dispute",
                reviewer_user_id=owner_id,
            )

        assert approve_ok is False
        assert reject_ok is False
        assert "property-side manager" in approve_error.lower()
        assert "property-side manager" in reject_error.lower()
        booking = db.session.get(AccommodationBooking, held_booking)
        assert booking.policy_snapshot["refund_workflow"]["state"] == "pending_human_review"
        assert _count_transfers_for(held_booking, "refund") == 0


    def test_only_independent_platform_admin_can_approve(
        self, app, guest, host, platform_admin, held_booking
    ):
        _prepare_cancelled_booking_for_review(
            app,
            held_booking,
            guest["user_id"],
            requester_user_id=host["user_id"],
        )
        with _login_as(app, platform_admin["user_id"]):
            ok, error = _guarded_call(
                lambda: MarketplaceService.refund_guest_approved(
                    held_booking,
                    Decimal("230.00"),
                    approval_reason="Reviewed the booking, original payment and policy evidence",
                )
            )

        assert ok, error
        assert _count_transfers_for(held_booking, "refund") == 1
        refund_tx = (
            db.session.query(TransactionModel)
            .filter_by(client_request_id=REFUND_KEY_TEMPLATE.format(booking_id=held_booking))
            .first()
        )
        assert refund_tx.tx_metadata["authorization_source"] == "platform_human_review"
        assert refund_tx.tx_metadata["authorized_by_user_id"] == platform_admin["user_id"]
        assert refund_tx.tx_metadata["approved_by_user_id"] == platform_admin["user_id"]

    def test_requesting_admin_cannot_approve_own_review(
        self, app, guest, platform_admin, platform_admin_two, held_booking
    ):
        _prepare_cancelled_booking_for_review(
            app,
            held_booking,
            guest["user_id"],
            requester_user_id=platform_admin["user_id"],
        )

        with _login_as(app, platform_admin["user_id"]):
            same_actor_ok, same_actor_error = MarketplaceService.refund_guest_approved(
                held_booking,
                Decimal("230.00"),
                approval_reason="Attempted maker-checker bypass",
            )
        assert same_actor_ok is False
        assert "requester" in same_actor_error.lower()
        assert _count_transfers_for(held_booking, "refund") == 0

        with _login_as(app, platform_admin_two["user_id"]):
            independent_ok, independent_error = _guarded_call(
                lambda: MarketplaceService.refund_guest_approved(
                    held_booking,
                    Decimal("230.00"),
                    approval_reason="Independent super-admin review",
                )
            )
        assert independent_ok, independent_error
        assert _count_transfers_for(held_booking, "refund") == 1

    def test_admin_rejection_is_audited_and_does_not_move_money(
        self, app, guest, host, platform_admin, held_booking
    ):
        _prepare_cancelled_booking_for_review(
            app,
            held_booking,
            guest["user_id"],
            requester_user_id=host["user_id"],
        )
        with _login_as(app, platform_admin["user_id"]):
            ok, error = MarketplaceService.reject_refund_review(
                held_booking,
                "Evidence does not support the requested exception",
                reviewer_user_id=platform_admin["user_id"],
            )

        assert ok, error
        booking = db.session.get(AccommodationBooking, held_booking)
        workflow = booking.policy_snapshot["refund_workflow"]
        assert workflow["state"] == "rejected"
        assert workflow["rejected_by_user_id"] == platform_admin["user_id"]
        assert workflow["rejection_reason"] == "Evidence does not support the requested exception"
        assert _count_transfers_for(held_booking, "refund") == 0
        assert booking.refunded_at is None
        history = BookingStatusHistory.query.filter_by(
            booking_id=held_booking,
            trigger="refund_review_rejected",
        ).one()
        assert history.changed_by == platform_admin["user_id"]
        assert history.change_metadata["rejection_reason"] == (
            "Evidence does not support the requested exception"
        )
        audit = AuditLog.query.filter_by(
            action="accommodation_refund.refund_review_rejected",
            resource_id=db.session.get(
                AccommodationBooking, held_booking
            ).booking_reference,
        ).one()
        assert audit.user_id == platform_admin["user_id"]
        assert audit.meta["rejection_reason"] == (
            "Evidence does not support the requested exception"
        )

    def test_external_refund_rejected_without_original_provider_charge_reference(
        self, app, guest, host, platform_admin, held_booking
    ):
        _prepare_cancelled_booking_for_review(
            app,
            held_booking,
            guest["user_id"],
            requester_user_id=host["user_id"],
            payment_method="card",
        )
        booking = db.session.get(AccommodationBooking, held_booking)
        booking.wallet_txn_id = None
        db.session.commit()

        with _login_as(app, platform_admin["user_id"]):
            ok, error = MarketplaceService.refund_guest_approved(
                held_booking,
                Decimal("230.00"),
                approval_reason="Attempt external refund without original provider transaction reference",
            )

        assert ok is False
        assert "external payment reference" in error.lower()
        booking = db.session.get(AccommodationBooking, held_booking)
        assert booking.refunded_at is None
        assert booking.policy_snapshot["refund_workflow"]["state"] == "pending_human_review"
        assert _count_transfers_for(held_booking, "refund") == 0

    def test_external_refund_rejected_when_payment_not_confirmed(
        self, app, guest, host, platform_admin, held_booking
    ):
        _prepare_cancelled_booking_for_review(
            app,
            held_booking,
            guest["user_id"],
            requester_user_id=host["user_id"],
            payment_method="card",
        )
        booking = db.session.get(AccommodationBooking, held_booking)
        booking.payment_status = AccommodationPaymentStatus.PENDING.value
        db.session.commit()

        with _login_as(app, platform_admin["user_id"]):
            ok, error = MarketplaceService.refund_guest_approved(
                held_booking,
                Decimal("230.00"),
                approval_reason="Attempt external refund before the original charge settled",
            )

        assert ok is False
        assert "payment has not been confirmed" in error.lower()
        booking = db.session.get(AccommodationBooking, held_booking)
        assert booking.refunded_at is None
        assert booking.policy_snapshot["refund_workflow"]["state"] == "pending_human_review"
        assert _count_transfers_for(held_booking, "refund") == 0


    def test_external_refund_requires_second_admin_to_verify_execution(
        self, app, guest, host, platform_admin, platform_admin_two,
        platform, held_booking
    ):
        _prepare_cancelled_booking_for_review(
            app,
            held_booking,
            guest["user_id"],
            requester_user_id=host["user_id"],
            payment_method="card",
            refund_amount=Decimal("230.00"),
        )
        with _login_as(app, platform_admin["user_id"]):
            approved, error = MarketplaceService.refund_guest_approved(
                held_booking,
                Decimal("230.00"),
                approval_reason="Verified card payment and cancellation entitlement",
            )
        assert approved, error
        booking = db.session.get(AccommodationBooking, held_booking)
        assert booking.policy_snapshot["refund_workflow"]["state"] == "approved_external_execution_pending"
        assert booking.refund_amount in (None, Decimal("0.00"))
        assert _count_transfers_for(held_booking, "refund") == 0

        with _login_as(app, platform_admin["user_id"]):
            same_admin_ok, same_admin_error = MarketplaceService.record_external_refund_execution(
                held_booking,
                Decimal("230.00"),
                "CARD-REFUND-001",
                verification_note="Checked the acquirer merchant portal; refund status is completed for the exact amount and card transaction reference.",
                reviewer_user_id=platform_admin["user_id"],
            )
        assert same_admin_ok is False
        assert "different platform administrator" in same_admin_error.lower()

        with _login_as(app, platform_admin_two["user_id"]):
            no_evidence_ok, no_evidence_error = MarketplaceService.record_external_refund_execution(
                held_booking,
                Decimal("230.00"),
                "CARD-REFUND-001",
                verification_note=" ",
                reviewer_user_id=platform_admin_two["user_id"],
            )
        assert no_evidence_ok is False
        assert "original provider's system" in no_evidence_error.lower()
        booking = db.session.get(AccommodationBooking, held_booking)
        assert booking.policy_snapshot["refund_workflow"]["state"] == "approved_external_execution_pending"
        assert booking.refunded_at is None

        with _login_as(app, platform_admin_two["user_id"]):
            verified, verify_error = MarketplaceService.record_external_refund_execution(
                held_booking,
                Decimal("230.00"),
                "CARD-REFUND-001",
                verification_note="Independently checked the acquirer merchant portal; refund status is completed, amount and currency match.",
                reviewer_user_id=platform_admin_two["user_id"],
            )
        assert verified, verify_error
        booking = db.session.get(AccommodationBooking, held_booking)
        workflow = booking.policy_snapshot["refund_workflow"]
        assert workflow["state"] == "refunded"
        assert workflow["external_provider_reference"] == "CARD-REFUND-001"
        assert workflow["approved_by_user_id"] == platform_admin["user_id"]
        assert workflow["execution_verified_by_user_id"] == platform_admin_two["user_id"]
        assert booking.payment_status == AccommodationPaymentStatus.REFUNDED.value
        assert booking.refund_amount == Decimal("230.00")
        assert _count_transfers_for(held_booking, "refund") == 0
        audit = AuditLog.query.filter_by(
            action="accommodation_refund.external_refund_verified",
            resource_id=booking.booking_reference,
        ).one()
        assert audit.user_id == platform_admin_two["user_id"]
        assert audit.meta["verification_method"] == (
            "independent_manual_provider_reconciliation"
        )
        assert "merchant portal" in audit.meta["verification_note"].lower()


class TestPayoutIdempotency:
    def test_sequential_duplicate_payout_single_transfer(
        self, app, platform, host, held_booking
    ):
        """GREEN contract: a second payout attempt is refused and the wallet
        transfer happened exactly once."""
        host_before = _balance(host["account_id"])
        platform_before = _balance(platform["account_id"])

        with _login_as(app, host["user_id"]):
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
        released_commission = _commission(app, held_booking)
        assert released_commission.status == "released"
        assert released_commission.released_by == host["user_id"]
        payout_tx = (
            db.session.query(TransactionModel)
            .filter_by(client_request_id=PAYOUT_KEY_TEMPLATE.format(booking_id=held_booking))
            .first()
        )
        assert payout_tx.tx_metadata["approved_by_user_id"] == host["user_id"]
        assert payout_tx.tx_metadata["approval_source"] == "host_check_in"

    def test_concurrent_payout_single_transfer(
        self, app, platform, host, held_booking
    ):
        """RED→GREEN: two concurrent releases must move money exactly once."""
        host_before = _balance(host["account_id"])
        platform_before = _balance(platform["account_id"])

        outcomes = _run_two_threads(
            app,
            host["user_id"],
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


class TestCrossOperationEscrowSettlement:
    def test_host_payout_and_guest_refund_cannot_settle_same_booking_concurrently(
        self, app, platform, guest, host, held_booking
    ):
        """A payout already authorized against CHECKED_IN state must exclude a
        cancellation/refund that arrives before the payout's wallet transfer.

        This reproduces the dangerous interleaving: payout reads CHECKED_IN and
        held escrow; the guest cancellation commits; the refund then attempts
        settlement while payout is still in flight. The shared advisory lock
        must reject the overlapping refund, and a retry after payout must route
        to human review because the escrow is no longer held.
        """
        host_before = _balance(host["account_id"])
        guest_before = _balance(guest["account_id"])
        platform_before = _balance(platform["account_id"])

        payout_authorized = threading.Event()
        allow_payout_transfer = threading.Event()
        refund_attempt_started = threading.Event()
        refund_attempt_finished = threading.Event()
        payout_outcomes = []
        refund_outcomes = []
        thread_errors = []
        original_lookup = MarketplaceService._get_account_for_user

        def _pause_after_payout_authorization(user_id, currency="USD"):
            # release_host_payout has already checked the booking and held
            # commission before it reaches its first wallet-account lookup.
            if user_id == host["user_id"] and not payout_authorized.is_set():
                payout_authorized.set()
                if not allow_payout_transfer.wait(timeout=20):
                    raise AssertionError("Timed out waiting to resume host payout")
            return original_lookup(user_id, currency)

        def _payout_worker():
            try:
                with app.app_context():
                    with app.test_request_context():
                        login_user(db.session.get(User, host["user_id"]))
                        payout_outcomes.append(
                            MarketplaceService.release_host_payout(held_booking)
                        )
                        db.session.remove()
            except Exception as exc:  # pragma: no cover - defensive
                thread_errors.append(exc)

        def _refund_worker():
            try:
                with app.app_context():
                    with app.test_request_context():
                        login_user(db.session.get(User, guest["user_id"]))
                        refund_attempt_started.set()
                        refund_outcomes.append(
                            MarketplaceService.refund_guest(
                                held_booking, Decimal("230.00")
                            )
                        )
                        db.session.remove()
            except Exception as exc:  # pragma: no cover - defensive
                thread_errors.append(exc)
            finally:
                refund_attempt_finished.set()

        payout_thread = threading.Thread(target=_payout_worker)
        refund_thread = threading.Thread(target=_refund_worker)

        with patch.object(
            MarketplaceService,
            "_get_account_for_user",
            new=_pause_after_payout_authorization,
        ), _guarded():
            try:
                payout_thread.start()
                assert payout_authorized.wait(timeout=15), (
                    "Host payout did not reach the post-authorization wallet boundary"
                )

                # The payout has already read CHECKED_IN and confirmed that
                # escrow is held. Commit the guest cancellation from a separate
                # session while payout is paused before WalletService.transfer.
                _prepare_cancelled_booking_for_review(
                    app,
                    held_booking,
                    guest["user_id"],
                    workflow_state="screening",
                    refund_amount=Decimal("230.00"),
                )

                refund_thread.start()
                assert refund_attempt_started.wait(timeout=10)
                assert refund_attempt_finished.wait(timeout=10), (
                    "The overlapping refund should fail fast on the held advisory lock"
                )
            finally:
                allow_payout_transfer.set()
                payout_thread.join(timeout=30)
                if refund_thread.ident is not None:
                    refund_thread.join(timeout=30)

        assert not payout_thread.is_alive(), "Host payout thread did not finish"
        assert not refund_thread.is_alive(), "Guest refund thread did not finish"
        assert not thread_errors, f"Settlement worker errors: {thread_errors}"
        assert len(payout_outcomes) == 1
        assert payout_outcomes[0][0] is True, payout_outcomes
        assert len(refund_outcomes) == 1
        assert refund_outcomes[0][0] is False, refund_outcomes
        assert "another refund or host payout" in refund_outcomes[0][1].lower()

        # Exactly the winning host payout moved money; the overlapping refund
        # did not create a second, differently-keyed wallet transfer.
        assert _count_transfers_for(held_booking, "payout") == 1
        assert _count_transfers_for(held_booking, "refund") == 0
        assert _balance(host["account_id"]) == host_before + Decimal("207.00")
        assert _balance(guest["account_id"]) == guest_before
        assert _balance(platform["account_id"]) == platform_before - Decimal("207.00")

        payout_tx = (
            db.session.query(TransactionModel)
            .filter_by(
                client_request_id=PAYOUT_KEY_TEMPLATE.format(
                    booking_id=held_booking
                )
            )
            .one()
        )
        payout_ledger_entries = (
            db.session.query(LedgerEntryModel)
            .filter_by(transaction_id=payout_tx.id)
            .all()
        )
        assert payout_tx.recipient_user_id == host["user_id"]
        assert payout_tx.amount == Decimal("207.00")
        assert len(payout_ledger_entries) == 2
        assert {
            getattr(entry.entry_type, "value", entry.entry_type)
            for entry in payout_ledger_entries
        } == {EntryType.DEBIT.value, EntryType.CREDIT.value}
        assert all(
            entry.amount == Decimal("207.00")
            for entry in payout_ledger_entries
        )
        assert _commission(app, held_booking).status == "released"

        # Once the payout has completed and released escrow, a safe retry of
        # the guest refund must be escalated, never automatically paid.
        with _login_as(app, guest["user_id"]):
            retry_ok, retry_message = _guarded_call(
                lambda: MarketplaceService.refund_guest(
                    held_booking, Decimal("230.00")
                )
            )
        assert retry_ok, retry_message
        assert _count_transfers_for(held_booking, "refund") == 0
        booking = db.session.get(AccommodationBooking, held_booking)
        workflow = booking.policy_snapshot["refund_workflow"]
        assert workflow["state"] == "pending_human_review"
        assert "escrow_not_held_for_automatic_refund" in workflow["risk_flags"]
        assert booking.status == AccommodationBookingStatus.CANCELLED.value
        assert _commission(app, held_booking).status == "released"


# ---------------- Refund idempotency ----------------


class TestRefundIdempotency:
    def test_sequential_duplicate_refund_single_transfer(
        self, app, platform, guest, host, platform_admin, held_booking
    ):
        _prepare_cancelled_booking_for_review(
            app,
            held_booking,
            guest["user_id"],
            requester_user_id=host["user_id"],
        )
        guest_before = _balance(guest["account_id"])
        platform_before = _balance(platform["account_id"])

        with _login_as(app, platform_admin["user_id"]):
            ok1, err1 = _guarded_call(
                lambda: MarketplaceService.refund_guest_approved(
                    held_booking,
                    Decimal("230.00"),
                    approval_reason="Independently approved full cancellation refund",
                )
            )
            ok2, err2 = _guarded_call(
                lambda: MarketplaceService.refund_guest_approved(
                    held_booking,
                    Decimal("230.00"),
                    approval_reason="Duplicate approval attempt",
                )
            )

        assert ok1, err1
        assert ok2 is False
        assert "already refunded" in err2.lower()
        assert _count_transfers_for(held_booking, "refund") == 1
        assert _balance(guest["account_id"]) == guest_before + Decimal("230.00")
        assert _balance(platform["account_id"]) == platform_before - Decimal("230.00")

        commission = _commission(app, held_booking)
        assert commission.status == "refunded"
        assert commission.refund_amount == Decimal("230.00")
        refund_tx = (
            db.session.query(TransactionModel)
            .filter_by(client_request_id=REFUND_KEY_TEMPLATE.format(booking_id=held_booking))
            .first()
        )
        assert refund_tx.tx_metadata["approved_by_user_id"] == platform_admin["user_id"]
        assert refund_tx.tx_metadata["authorization_source"] == "platform_human_review"

    def test_concurrent_refund_single_transfer(
        self, app, platform, guest, host, platform_admin, held_booking
    ):
        _prepare_cancelled_booking_for_review(
            app,
            held_booking,
            guest["user_id"],
            requester_user_id=host["user_id"],
        )
        guest_before = _balance(guest["account_id"])
        platform_before = _balance(platform["account_id"])

        outcomes = _run_two_threads(
            app,
            platform_admin["user_id"],
            lambda: MarketplaceService.refund_guest_approved(
                held_booking,
                Decimal("230.00"),
                approval_reason="Independent concurrent approval",
            ),
        )

        assert _count_transfers_for(held_booking, "refund") == 1, (
            "Exactly ONE refund transfer expected; "
            f"threads returned {outcomes}"
        )
        assert _balance(guest["account_id"]) == guest_before + Decimal("230.00")
        assert _balance(platform["account_id"]) == platform_before - Decimal("230.00")
        commission = _commission(app, held_booking)
        assert commission.status == "refunded"
        assert commission.refund_amount == Decimal("230.00")
        tx = (
            db.session.query(TransactionModel)
            .filter_by(client_request_id=REFUND_KEY_TEMPLATE.format(booking_id=held_booking))
            .first()
        )
        assert tx is not None
        assert tx.tx_metadata["approved_by_user_id"] == platform_admin["user_id"]
        assert (
            db.session.query(LedgerEntryModel)
            .filter_by(transaction_id=tx.id)
            .count()
            == 2
        )

    def test_refund_retry_after_wallet_commit_converges(
        self, app, platform, guest, host, platform_admin, held_booking
    ):
        """A committed wallet leg is reconciled after a business-state crash."""
        from app.wallet.services.wallet_service import WalletService

        _prepare_cancelled_booking_for_review(
            app,
            held_booking,
            guest["user_id"],
            requester_user_id=host["user_id"],
        )
        guest_before = _balance(guest["account_id"])
        platform_before = _balance(platform["account_id"])
        key = REFUND_KEY_TEMPLATE.format(booking_id=held_booking)

        with _login_as(app, platform_admin["user_id"]):
            _guarded_call(
                lambda: WalletService().transfer(
                    from_account_id=platform["account_id"],
                    to_account_id=guest["account_id"],
                    amount=Decimal("230.00"),
                    currency="USD",
                    client_request_id=key,
                    note="Refund: simulated wallet leg before business commit",
                    metadata={
                        "booking_id": str(held_booking),
                        "authorization_source": "platform_human_review",
                        "authorized_by_user_id": platform_admin["user_id"],
                        "approved_by_user_id": platform_admin["user_id"],
                        "approval_reason": "Independent reviewer authorized the refund",
                        "approved_at": datetime.now(timezone.utc).isoformat(),
                    },
                    system_initiated=True,
                )
            )

        assert _commission(app, held_booking).status == "held"
        with _login_as(app, platform_admin["user_id"]):
            ok, error = _guarded_call(
                lambda: MarketplaceService.refund_guest_approved(
                    held_booking,
                    Decimal("230.00"),
                    approval_reason="Retry after wallet commit",
                )
            )

        assert ok, error
        assert _count_transfers_for(held_booking, "refund") == 1
        assert _balance(guest["account_id"]) == guest_before + Decimal("230.00")
        assert _balance(platform["account_id"]) == platform_before - Decimal("230.00")
        commission = _commission(app, held_booking)
        assert commission.status == "refunded"
        assert commission.refund_amount == Decimal("230.00")


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
            host["user_id"],
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