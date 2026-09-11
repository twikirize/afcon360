"""Temporary F-01 reproduction probe. DELETED after verification.

F-01 (6-1B finding): class-style `WalletService.get_balance(account.id)`
raises TypeError (get_balance is an INSTANCE method requiring an internal
user id). Affects accommodation/routes.py:2100, wallet_processor.py:42
(500/charge failure) and identity/routes.py:379 + organisation.py:331
(silent zero). Repairs to `LedgerRepository().get_balance(account_uuid,
currency)`.
"""
import uuid
from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch

import pytest

from app.extensions import db
from app.identity.models.user import User
from app.identity.models.organisation import Organisation
from app.wallet.models.ledger import (
    AccountModel,
    LedgerEntryModel,
    EntryType,
    AccountOwnerType,
    AccountType,
)
from app.wallet.models.transaction import TransactionModel, TransactionType, TransactionStatus
from app.wallet.services.wallet_service import WalletService
from app.wallet.repositories.ledger_repository import LedgerRepository
from app.accommodation.models.booking import AccommodationBooking
from app.accommodation.models.property import Property, AccommodationCancellationPolicy


def _make_user(tag):
    u = User(
        email=f"probe-f01-{tag}-{uuid.uuid4().hex[:6]}@example.com",
        username=f"probe_f01_{tag}_{uuid.uuid4().hex[:6]}",
        password_hash="hashed",
        email_verified=True,
        phone_verified=True,
        kyc_level=2,
        is_active=True,
    )
    db.session.add(u)
    db.session.commit()
    return u


def _make_org(tag):
    org = Organisation(
        org_id=str(uuid.uuid4()),
        legal_name=f"Probe F01 Org {tag} {uuid.uuid4().hex[:6]}",
        country="UG",
        region="Central",
        org_type="business",
        contact_email=f"probe-f01-{tag}-{uuid.uuid4().hex[:6]}@example.com",
    )
    db.session.add(org)
    db.session.commit()
    return org


def _fund_account(account_id, currency="USD", amount=Decimal("1000")):
    tx = TransactionModel(
        id=uuid.uuid4(),
        client_request_id=f"probe-f01-{uuid.uuid4()}",
        tx_type=TransactionType.DEPOSIT,
        amount=amount,
        currency=currency,
        status=TransactionStatus.COMPLETED,
    )
    db.session.add(tx)
    db.session.flush()
    db.session.add(
        LedgerEntryModel(
            transaction_id=tx.id,
            account_id=account_id,
            entry_type=EntryType.CREDIT,
            amount=amount,
            currency=currency,
        )
    )
    db.session.commit()


def test_probe_f01_shape_get_balance_is_instance_method(test_db):
    """The class-style expression used at all 4 F-01 sites raises TypeError."""
    from app.wallet.routes import get_or_create_account

    user = _make_user("shape")
    account = get_or_create_account(user.id, "USD")
    _fund_account(account.id, "USD", Decimal("1000"))
    db.session.refresh(account)

    with pytest.raises(TypeError):
        WalletService.get_balance(account.id)

    assert LedgerRepository().get_balance(account.id, "USD") == Decimal("1000.00")


def test_probe_f01_wallet_processor_charge_crashes(test_db):
    """Real WalletProcessor.charge (wallet payment path) crashes at the
    balance pre-check → charge never happens (500 / payment failure)."""
    from app.wallet.routes import get_or_create_account
    from app.accommodation.services.payment_processors.wallet_processor import WalletProcessor
    from app.accommodation.services.marketplace_service import MarketplaceService

    host = _make_user("bhost")
    guest = _make_user("bguest")
    prop = Property(
        title="Probe Property",
        slug=f"probe-f01-prop-{uuid.uuid4().hex[:8]}",
        description="probe",
        address_line1="1 Probe Rd",
        city="Kampala",
        country="UG",
        status="active",
        is_verified=True,
        is_active=True,
        base_price_per_night=Decimal("100.00"),
        currency="USD",
        max_guests=2,
        instant_book=True,
        cancellation_policy=AccommodationCancellationPolicy.FLEXIBLE.value,
        owner_user_id=host.id,
    )
    db.session.add(prop)
    db.session.commit()

    idempotency_key = f"probe-f01-idem-{uuid.uuid4()}"
    booking = AccommodationBooking(
        property_id=prop.id,
        guest_user_id=guest.id,
        host_user_id=host.id,
        check_in=date.today() + timedelta(days=3),
        check_out=date.today() + timedelta(days=5),
        num_nights=2,
        num_guests=1,
        nightly_rate=Decimal("100.00"),
        cleaning_fee=Decimal("0.00"),
        service_fee=Decimal("0.00"),
        total_amount=Decimal("200.00"),
        amount_due=Decimal("200.00"),
        currency="USD",
        guest_name="Probe Guest",
        guest_email=guest.email,
        guest_phone="+256700000001",
        payment_status="unpaid",
        status="draft",
        booked_by_user_id=guest.id,
        booking_type="self",
        idempotency_key=idempotency_key,
    )
    booking.generate_reference()
    db.session.add(booking)
    db.session.commit()

    account = get_or_create_account(guest.id, "USD")
    _fund_account(account.id, "USD", Decimal("1000"))

    with patch.object(MarketplaceService, "charge_guest", return_value=(True, "tx-mock", None)) as mock_charge:
        success, txn_id, error = WalletProcessor().charge(
            user_id=guest.id,
            amount=Decimal("200"),
            currency="USD",
            description="Probe wallet checkout charge",
            idempotency_key=idempotency_key,
        )

    assert mock_charge.called, "balance pre-check did not reach charge_guest"
    assert success is True, f"charge failed: {error}"
    assert txn_id == "tx-mock"


def test_probe_f01_org_wallet_balance_silent_zero(test_db):
    """org.wallet_balance silently returns 0 for a funded org wallet."""
    org = _make_org("corg")
    acct = AccountModel(
        account_name=f"Probe Org Wallet {org.id}",
        account_number=f"{uuid.uuid4().hex[:12]}",
        owner_type=AccountOwnerType.ORGANISATION,
        organisation_id=org.id,
        account_type=AccountType.ORG_WALLET,
        currency="USD",
    )
    db.session.add(acct)
    db.session.commit()
    _fund_account(acct.id, "USD", Decimal("1000"))

    bal = org.wallet_balance
    assert bal == Decimal("1000.00"), f"org wallet_balance returned {bal!r} for a funded account (silent zero?)"