"""
tests/wallet/test_f01_balance_boundary.py
STAGE 6-2B.2 - F-01: Wallet balance boundary repair.

F-01 root cause (class-style misuse of an instance method): the four affected
sites called ``WalletService.get_balance(account.id)`` where ``get_balance``
is an INSTANCE method expecting the internal BIGINT user id, while
``account.id`` is the Account UUID. That raises ``TypeError`` on the
accommodation paths (routes.py / wallet_processor.py) and silently zeroes the
balance on the identity/org display paths.

Repaired with the canonical account-oriented primitive
``LedgerRepository().get_balance(account_uuid, currency) -> Decimal``.

Residual boundary gap closed by this suite: the accommodation sites resolved
the account with ``AccountModel.query.filter_by(user_id=...).first()`` which
ignores the charge currency (a user paying in UGX with only a USD wallet got a
false "Insufficient balance", or a wrong-currency account was charged).
Repaired with the canonical user-oriented resolver
``WalletService.get_wallet_by_user_id(user_id, currency)``.

No wallet architecture, ledger logic, account model, or ownership semantics
are changed.
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
    AccountOwnerType,
    AccountType,
    LedgerEntryModel,
    EntryType,
)
from app.wallet.models.transaction import TransactionModel, TransactionType, TransactionStatus
from app.wallet.services.wallet_service import WalletService
from app.wallet.repositories.ledger_repository import LedgerRepository
from app.accommodation.models.booking import AccommodationBooking
from app.accommodation.models.property import Property, AccommodationCancellationPolicy


# ===========================================================================
# HELPERS
# ===========================================================================

def _make_user(tag):
    user = User(
        email=f'f01_{tag}_{uuid.uuid4().hex[:8]}@example.com',
        username=f'f01{tag}_{uuid.uuid4().hex[:8]}',
        password_hash='hashed',
        is_active=True,
        is_verified=True,
    )
    db.session.add(user)
    db.session.commit()
    return user


def _make_org(tag):
    org = Organisation(
        org_id=str(uuid.uuid4()),
        legal_name=f'F01 Org {tag} {uuid.uuid4().hex[:6]}',
        country='UG',
        region='Central',
        org_type='business',
        contact_email=f'f01-org-{tag}-{uuid.uuid4().hex[:6]}@example.com',
    )
    db.session.add(org)
    db.session.commit()
    return org


def _user_account(user_id, currency='USD'):
    """Get-or-create an individual wallet account (returns AccountModel)."""
    from app.wallet.routes import get_or_create_account
    return get_or_create_account(user_id, currency)


def _fund(account_id, currency='USD', amount=Decimal('1000')):
    """Post a completed DEPOSIT + CREDIT ledger entry (canonical test pattern)."""
    tx = TransactionModel(
        id=uuid.uuid4(),
        client_request_id=f'f01-fund-{uuid.uuid4()}',
        tx_type=TransactionType.DEPOSIT,
        amount=amount,
        currency=currency,
        status=TransactionStatus.COMPLETED,
        user_id=None,
    )
    db.session.add(tx)
    db.session.flush()
    db.session.add(LedgerEntryModel(
        transaction_id=tx.id,
        account_id=account_id,
        entry_type=EntryType.CREDIT,
        amount=amount,
        currency=currency,
    ))
    db.session.commit()


def _make_property(host):
    prop = Property(
        title='F01 Probe Property',
        slug=f'f01-prop-{uuid.uuid4().hex[:8]}',
        description='probe',
        address_line1='1 Probe Rd',
        city='Kampala',
        country='UG',
        status='active',
        is_verified=True,
        is_active=True,
        base_price_per_night=Decimal('100.00'),
        currency='USD',
        max_guests=2,
        instant_book=True,
        cancellation_policy=AccommodationCancellationPolicy.FLEXIBLE.value,
        owner_user_id=host.id,
    )
    db.session.add(prop)
    db.session.commit()
    return prop


def _make_booking(prop, guest, idempotency_key):
    booking = AccommodationBooking(
        property_id=prop.id,
        guest_user_id=guest.id,
        host_user_id=prop.owner_user_id,
        check_in=date.today() + timedelta(days=3),
        check_out=date.today() + timedelta(days=5),
        num_nights=2,
        num_guests=1,
        nightly_rate=Decimal('100.00'),
        cleaning_fee=Decimal('0.00'),
        service_fee=Decimal('0.00'),
        total_amount=Decimal('200.00'),
        amount_due=Decimal('200.00'),
        currency='USD',
        guest_name='F01 Guest',
        guest_email=guest.email,
        guest_phone='+256700000001',
        payment_status='unpaid',
        status='draft',
        booked_by_user_id=guest.id,
        booking_type='self',
        idempotency_key=idempotency_key,
    )
    booking.generate_reference()
    db.session.add(booking)
    db.session.commit()
    return booking


# ===========================================================================
# F-01 ROOT-CAUSE SHAPE (always-green contract guards)
# ===========================================================================

class TestF01ContractShape:

    def test_class_style_get_balance_with_account_uuid_raises_type_error(self, app):
        """The exact F-01 expression `WalletService.get_balance(account.id)`
        raises TypeError because get_balance is an INSTANCE method and
        account.id is an Account UUID."""
        user = _make_user('shape')
        account = _user_account(user.id, 'USD')
        db.session.refresh(account)

        with pytest.raises(TypeError):
            WalletService.get_balance(account.id)

    def test_ledger_repo_get_balance_is_canonical_decimal_primitive(self, app):
        """The correct account-oriented primitive returns a Decimal balance."""
        user = _make_user('prim')
        account = _user_account(user.id, 'USD')
        _fund(account.id, 'USD', Decimal('1000'))
        db.session.refresh(account)

        balance = LedgerRepository().get_balance(account.id, 'USD')
        assert isinstance(balance, Decimal)
        assert balance == Decimal('1000.00')

    def test_get_wallet_by_user_id_resolves_charge_currency(self, app):
        """The currency-aware resolver used by the accommodation wallet path
        returns the wallet matching the charge currency (and None when the
        user holds another currency only)."""
        user = _make_user('resolver')
        _user_account(user.id, 'USD')

        resolved = WalletService.get_wallet_by_user_id(user.id, 'USD')
        assert resolved is not None
        assert resolved.currency == 'USD'
        assert resolved.owner_type == AccountOwnerType.USER
        assert WalletService.get_wallet_by_user_id(user.id, 'UGX') is None


# ===========================================================================
# ACCOMMODATION WALLET PAYMENT PATH (WalletProcessor.charge)
# ===========================================================================

class TestWalletProcessorCharge:

    def _charge(self, guest, amount, currency, charge_guest_return=None):
        from app.accommodation.services.payment_processors.wallet_processor import WalletProcessor
        from app.accommodation.services.marketplace_service import MarketplaceService
        idempotency_key = f'f01-{uuid.uuid4()}'
        host = _make_user('host')
        prop = _make_property(host)
        _make_booking(prop, guest, idempotency_key)
        default_return = (True, 'tx-mock', None)
        with patch.object(
            MarketplaceService, 'charge_guest',
            return_value=charge_guest_return if charge_guest_return is not None else default_return,
        ) as mock_charge:
            result = WalletProcessor().charge(
                user_id=guest.id,
                amount=amount,
                currency=currency,
                description='F01 wallet checkout charge',
                idempotency_key=idempotency_key,
            )
        return result, mock_charge

    def test_sufficient_balance_reaches_marketplace(self, app):
        guest = _make_user('sufficient')
        account = _user_account(guest.id, 'USD')
        _fund(account.id, 'USD', Decimal('1000'))

        (success, txn_id, error), mock_charge = self._charge(
            guest, Decimal('200'), 'USD')
        assert mock_charge.called, f'charge did not reach marketplace: {error}'
        assert success is True, f'charge failed: {error}'
        assert txn_id == 'tx-mock'

    def test_insufficient_balance_short_circuits(self, app):
        guest = _make_user('insufficient')
        account = _user_account(guest.id, 'USD')
        _fund(account.id, 'USD', Decimal('30'))

        (success, txn_id, error), mock_charge = self._charge(
            guest, Decimal('200'), 'USD')
        assert not mock_charge.called
        assert success is False
        assert txn_id is None
        assert 'Insufficient' in str(error)

    def test_no_account_returns_not_found(self, app):
        guest = _make_user('noaccount')

        (success, txn_id, error), mock_charge = self._charge(
            guest, Decimal('200'), 'USD')
        assert not mock_charge.called
        assert success is False
        assert 'not found' in str(error).lower()

    def test_wrong_currency_only_reports_no_account(self, app):
        """A USD-funded guest charged in UGX must NOT get a false
        "Insufficient balance" against the wrong-currency account. The
        correct boundary is "no UGX wallet account". (RED before the
        currency-aware account resolution fix.)"""
        guest = _make_user('wrongccy')
        account = _user_account(guest.id, 'USD')
        _fund(account.id, 'USD', Decimal('1000'))

        (success, txn_id, error), mock_charge = self._charge(
            guest, Decimal('200'), 'UGX')
        assert not mock_charge.called
        assert success is False
        assert 'not found' in str(error).lower()

    def test_single_ugx_wallet_charged_in_ugx_succeeds(self, app):
        """A guest whose single (the app enforces one wallet per user) UGX
        wallet is funded must succeed when charged in UGX."""
        guest = _make_user('ugxwallet')
        account = _user_account(guest.id, 'UGX')
        _fund(account.id, 'UGX', Decimal('5000'))

        (success, txn_id, error), mock_charge = self._charge(
            guest, Decimal('1000'), 'UGX')
        assert success is True, f'UGX charge failed: {error}'
        assert mock_charge.called


# ===========================================================================
# IDENTITY / ORGANISATION BALANCE CONSUMERS
# ===========================================================================

class TestOrganisationWalletBalance:

    def test_funded_org_wallet_returns_real_balance(self, app):
        org = _make_org('bal')
        acct = AccountModel(
            account_name=f'F01 Org Wallet {org.id}',
            account_number=uuid.uuid4().hex[:12],
            owner_type=AccountOwnerType.ORGANISATION,
            organisation_id=org.id,
            account_type=AccountType.ORG_WALLET,
            currency='USD',
        )
        db.session.add(acct)
        db.session.commit()
        _fund(acct.id, 'USD', Decimal('1000'))

        assert org.wallet_balance == Decimal('1000.00')

    def test_no_account_returns_zero(self, app):
        org = _make_org('emptyset')
        assert org.wallet_balance == Decimal('0')


class TestOrganisationWalletPage:

    def test_org_wallet_page_shows_real_balance(self, app):
        org = _make_org('page')
        org_public_id = str(org.org_id)
        acct = AccountModel(
            account_name=f'F01 Org Wallet {org.id}',
            account_number=uuid.uuid4().hex[:12],
            owner_type=AccountOwnerType.ORGANISATION,
            organisation_id=org.id,
            account_type=AccountType.ORG_WALLET,
            currency='UGX',
        )
        db.session.add(acct)
        db.session.commit()
        _fund(acct.id, 'UGX', Decimal('7500'))

        user = _make_user('viewer')
        viewer_public_id = str(user.public_id)
        client = app.test_client()
        with client.session_transaction() as sess:
            sess['_user_id'] = viewer_public_id
            sess['_fresh'] = True

        with patch(
            'app.identity.services.organization_permissions.'
            'OrganizationPermissionService.can_manage_wallet',
            return_value=True,
        ):
            resp = client.get(f'/org/{org_public_id}/wallet')

        assert resp.status_code == 200, resp.status_code
        assert b'7,500' in resp.data, 'funded org balance missing from page'