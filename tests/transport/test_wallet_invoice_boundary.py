"""Wallet owns marketplace invoice state; Transport keeps references/status only."""
from decimal import Decimal
from types import SimpleNamespace
import uuid

import pytest

from app.extensions import db
from app.wallet.models.marketplace_invoice import MarketplaceInvoice
from app.wallet.services.marketplace_invoice_service import (
    MarketplaceInvoiceError,
    MarketplaceInvoiceService,
)

pytestmark = pytest.mark.usefixtures("db_session")


def _configure_wallet_methods(currency="USD"):
    from app.wallet.models.payment_method import PaymentMethodConfig

    PaymentMethodConfig.initialize_defaults()
    for method_id in ("cash", "wallet"):
        method = PaymentMethodConfig.query.filter_by(method_id=method_id).first()
        assert method is not None
        method.is_enabled = True
        method.is_active = True
        currencies = list(method.supported_currencies or [])
        if currency not in {str(value).upper() for value in currencies}:
            currencies.append(currency)
        method.supported_currencies = currencies
        timings = list(method.allowed_timings or [])
        if "pay_on_completion" not in timings:
            timings.append("pay_on_completion")
        method.allowed_timings = timings
    db.session.commit()


def _create_invoice(payer_id, *, method="cash", amount="25.00", reference=None):
    reference = reference or "ride-" + uuid.uuid4().hex
    return MarketplaceInvoiceService.create_invoice(
        idempotency_key="test-invoice:" + reference,
        service_code="transport",
        service_reference=reference,
        payer_user_id=payer_id,
        amount=amount,
        currency="USD",
        payment_method=method,
        settlement_timing="pay_on_completion",
        metadata={"test_only": True},
        commit=True,
    )


def test_invoice_is_idempotent_and_creation_does_not_move_money(app, test_user):
    from app.wallet.models.transaction import TransactionModel

    with app.app_context():
        payer_id = db.session.merge(test_user).id
        _configure_wallet_methods()
        reference = "ride-" + uuid.uuid4().hex
        key = "test-invoice:" + reference
        first = MarketplaceInvoiceService.create_invoice(
            idempotency_key=key,
            service_code="transport",
            service_reference=reference,
            payer_user_id=payer_id,
            amount="25.00",
            currency="USD",
            payment_method="cash",
            settlement_timing="pay_on_completion",
            commit=True,
        )
        second = MarketplaceInvoiceService.create_invoice(
            idempotency_key=key,
            service_code="transport",
            service_reference=reference,
            payer_user_id=payer_id,
            amount="25.00",
            currency="USD",
            payment_method="cash",
            settlement_timing="pay_on_completion",
            commit=True,
        )

        assert first.id == second.id
        assert second.status == "pending"
        assert second.transaction_id is None
        assert TransactionModel.query.filter_by(
            client_request_id="MARKETPLACE-INVOICE-" + str(first.id)
        ).one_or_none() is None


def test_concurrent_invoice_creation_converges_on_one_wallet_invoice(
    app, test_user, monkeypatch
):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    with app.app_context():
        payer_id = db.session.merge(test_user).id
        _configure_wallet_methods()

    reference = "ride-concurrent-" + uuid.uuid4().hex
    idempotency_key = "test-invoice:" + reference
    barrier = Barrier(2)
    original_method_config = MarketplaceInvoiceService._method_config

    def synchronize_after_validation(method_id, **kwargs):
        result = original_method_config(method_id, **kwargs)
        barrier.wait(timeout=15)
        return result

    monkeypatch.setattr(
        MarketplaceInvoiceService,
        "_method_config",
        staticmethod(synchronize_after_validation),
    )

    def create_in_worker(_):
        with app.app_context():
            try:
                invoice = MarketplaceInvoiceService.create_invoice(
                    idempotency_key=idempotency_key,
                    service_code="transport",
                    service_reference=reference,
                    payer_user_id=payer_id,
                    amount="25.00",
                    currency="USD",
                    payment_method="cash",
                    settlement_timing="pay_on_completion",
                    metadata={"test_only": True},
                    commit=True,
                )
                return str(invoice.id)
            finally:
                db.session.remove()

    with ThreadPoolExecutor(max_workers=2) as pool:
        invoice_ids = list(pool.map(create_in_worker, (1, 2)))

    assert invoice_ids[0] == invoice_ids[1]
    with app.app_context():
        assert MarketplaceInvoice.query.filter_by(
            service_code="transport",
            service_reference=reference,
        ).count() == 1


def test_invoice_terms_cannot_be_changed_by_reusing_an_idempotency_key(app, test_user):
    with app.app_context():
        payer_id = db.session.merge(test_user).id
        _configure_wallet_methods()
        invoice = _create_invoice(payer_id, method="cash")
        with pytest.raises(MarketplaceInvoiceError) as raised:
            MarketplaceInvoiceService.create_invoice(
                idempotency_key=invoice.idempotency_key,
                service_code="transport",
                service_reference=invoice.service_reference,
                payer_user_id=payer_id,
                amount="26.00",
                currency="USD",
                payment_method="cash",
                settlement_timing="pay_on_completion",
            )
        assert raised.value.code == "invoice_idempotency_conflict"
        db.session.rollback()


def test_cash_invoice_stays_unpaid_until_wallet_records_driver_receipt(app, test_user):
    with app.app_context():
        payer_id = db.session.merge(test_user).id
        _configure_wallet_methods()
        invoice = _create_invoice(payer_id, method="cash", amount="25.00")
        due = MarketplaceInvoiceService.settle_after_completion(
            invoice_id=invoice.id,
            payer_user_id=payer_id,
            service_code="transport",
            service_reference=invoice.service_reference,
            amount="25.00",
            currency="USD",
            request_id="test-trip-complete",
        )
        assert due["status"] == "due"
        invoice = MarketplaceInvoiceService.get_invoice(invoice.id)
        assert invoice.status == "due"
        assert invoice.transaction_id is None

        receipt = MarketplaceInvoiceService.confirm_cash_receipt(
            invoice_id=invoice.id,
            payer_user_id=payer_id,
            service_code="transport",
            service_reference=invoice.service_reference,
            amount="25.00",
            currency="USD",
            driver_user_id=payer_id,
            driver_profile_id=987654,
            driver_code="TEST-DRIVER",
        )
        assert receipt["status"] == "cash_received"
        invoice = MarketplaceInvoiceService.get_invoice(invoice.id)
        assert invoice.status == "cash_received"
        assert invoice.transaction_id is None
        assert invoice.receipt_metadata["collection_channel"] == "direct_cash_to_driver"

        replay = MarketplaceInvoiceService.confirm_cash_receipt(
            invoice_id=invoice.id,
            payer_user_id=payer_id,
            service_code="transport",
            service_reference=invoice.service_reference,
            amount="25.00",
            currency="USD",
            driver_user_id=payer_id,
            driver_profile_id=987654,
            driver_code="TEST-DRIVER",
        )
        assert replay["already_processed"] is True
        with pytest.raises(MarketplaceInvoiceError) as raised:
            MarketplaceInvoiceService.confirm_cash_receipt(
                invoice_id=invoice.id,
                payer_user_id=payer_id,
                service_code="transport",
                service_reference=invoice.service_reference,
                amount="25.00",
                currency="USD",
                driver_user_id=payer_id,
                driver_profile_id=987655,
                driver_code="OTHER-DRIVER",
            )
        assert raised.value.code == "cash_already_confirmed"


def test_wallet_transfer_replay_returns_committed_transaction_before_balance_checks(
    app, test_user, monkeypatch
):
    """A post-transfer crash must not turn an already-paid invoice into insufficient funds."""
    from app.identity.models.user import User
    from app.wallet.exceptions import DuplicateTransactionError
    from app.wallet.models.transaction import TransactionStatus, TransactionType
    from app.wallet.services.wallet_service import WalletService

    with app.app_context():
        payer_id = db.session.merge(test_user).id
        source_id = uuid.uuid4()
        escrow_id = uuid.uuid4()
        transaction_id = uuid.uuid4()
        metadata = {
            "marketplace_invoice_id": str(uuid.uuid4()),
            "service_code": "transport",
            "service_reference": "ride-idempotent-replay",
            "escrow_account_id": str(escrow_id),
            "escrow_service_type": "transport",
            "request_id": "first-attempt",
        }
        source = SimpleNamespace(
            id=source_id, user_id=payer_id, currency="USD", is_frozen=False,
            frozen_reason=None,
        )
        escrow = SimpleNamespace(
            id=escrow_id, user_id=987650, currency="USD", is_frozen=False,
            frozen_reason=None,
        )
        existing = SimpleNamespace(
            id=transaction_id,
            tx_type=TransactionType.TRANSFER.value,
            status=TransactionStatus.COMPLETED.value,
            amount=Decimal("25.00"),
            currency="USD",
            user_id=payer_id,
            recipient_user_id=escrow.user_id,
            tx_metadata=metadata,
        )

        monkeypatch.setattr(
            User,
            "get_by_private_id",
            staticmethod(lambda user_id: SimpleNamespace(transaction_pin_hash=None)),
        )
        service = WalletService()
        service._validate_currency = lambda currency: None
        service._check_transaction_limit = lambda *args, **kwargs: pytest.fail(
            "a committed idempotent replay must not be blocked by a changed limit"
        )
        service.account_repo.get_by_id = lambda account_id, for_update=False: {
            str(source_id): source,
            str(escrow_id): escrow,
        }.get(str(account_id))
        service.tx_repo.get_by_client_request_id = lambda key: existing
        service.ledger_repo.get_balance = lambda account_id, currency: (
            Decimal("0.00") if str(account_id) == str(source_id) else Decimal("25.00")
        )
        service._check_daily_limit = lambda *args, **kwargs: pytest.fail(
            "completed idempotent replay must not re-check daily limits"
        )
        service._check_monthly_limit = lambda *args, **kwargs: pytest.fail(
            "completed idempotent replay must not re-check monthly limits"
        )
        service._check_kyc_limits = lambda *args, **kwargs: pytest.fail(
            "completed idempotent replay must not re-run collection eligibility"
        )
        service._check_fraud_risk = lambda *args, **kwargs: pytest.fail(
            "completed idempotent replay must not re-run collection eligibility"
        )

        result = service.transfer(
            from_account_id=str(source_id),
            to_account_id=str(escrow_id),
            amount=Decimal("25.00"),
            currency="USD",
            client_request_id="MARKETPLACE-INVOICE-REPLAY",
            metadata={**metadata, "request_id": "retry-attempt"},
            system_initiated=True,
        )
        assert result["status"] == "success"
        assert result["already_processed"] is True
        assert result["transaction_id"] == str(transaction_id)
        assert result["new_balance_from"] == "0.00"
        assert result["new_balance_to"] == "25.00"


def test_wallet_transfer_rejects_invoice_mismatch_when_insert_race_wins_late(
    app, test_user, monkeypatch
):
    """The late ON CONFLICT path must validate terms just like an early replay."""
    from app.identity.models.user import User
    from app.wallet.exceptions import DuplicateTransactionError
    from app.wallet.models.transaction import TransactionStatus, TransactionType
    from app.wallet.services.wallet_service import WalletService

    with app.app_context():
        payer_id = db.session.merge(test_user).id
        source_id, escrow_id = uuid.uuid4(), uuid.uuid4()
        source = SimpleNamespace(
            id=source_id, user_id=payer_id, currency="USD", is_frozen=False,
            frozen_reason=None,
        )
        escrow = SimpleNamespace(
            id=escrow_id, user_id=987650, currency="USD", is_frozen=False,
            frozen_reason=None,
        )
        existing = SimpleNamespace(
            id=uuid.uuid4(),
            tx_type=TransactionType.TRANSFER.value,
            status=TransactionStatus.COMPLETED.value,
            amount=Decimal("25.00"),
            currency="USD",
            user_id=payer_id,
            recipient_user_id=escrow.user_id,
            tx_metadata={
                "marketplace_invoice_id": str(uuid.uuid4()),
                "service_code": "transport",
                "service_reference": "ride-winner",
                "escrow_account_id": str(escrow_id),
                "escrow_service_type": "transport",
                "settlement_timing": "pay_on_completion",
            },
        )
        monkeypatch.setattr(
            User,
            "get_by_private_id",
            staticmethod(lambda user_id: SimpleNamespace(transaction_pin_hash=None)),
        )
        service = WalletService()
        service._validate_currency = lambda currency: None
        service._check_transaction_limit = lambda *args, **kwargs: None
        service.account_repo.get_by_id = lambda account_id, for_update=False: {
            str(source_id): source,
            str(escrow_id): escrow,
        }.get(str(account_id))
        # Simulate the first lookup missing a concurrently inserted transaction;
        # get_or_create then returns the winner's already-completed transaction.
        service.tx_repo.get_by_client_request_id = lambda key: None
        service.tx_repo.get_or_create = lambda **kwargs: existing
        service.ledger_repo.get_balance = lambda account_id, currency: Decimal("100.00")
        service._check_daily_limit = lambda *args, **kwargs: None
        service._check_monthly_limit = lambda *args, **kwargs: None
        service._check_kyc_limits = lambda *args, **kwargs: None
        service._check_fraud_risk = lambda *args, **kwargs: None

        with pytest.raises(DuplicateTransactionError):
            service.transfer(
                from_account_id=str(source_id),
                to_account_id=str(escrow_id),
                amount=Decimal("25.00"),
                currency="USD",
                client_request_id="MARKETPLACE-INVOICE-RACE",
                metadata={
                    "marketplace_invoice_id": str(uuid.uuid4()),
                    "service_code": "transport",
                    "service_reference": "ride-other",
                    "escrow_account_id": str(escrow_id),
                    "escrow_service_type": "transport",
                    "settlement_timing": "pay_on_completion",
                },
                system_initiated=True,
            )


def test_wallet_transfer_idempotency_key_cannot_be_reused_for_another_invoice(
    app, test_user, monkeypatch
):
    from app.identity.models.user import User
    from app.wallet.exceptions import DuplicateTransactionError
    from app.wallet.models.transaction import TransactionStatus, TransactionType
    from app.wallet.services.wallet_service import WalletService

    with app.app_context():
        payer_id = db.session.merge(test_user).id
        source_id, escrow_id = uuid.uuid4(), uuid.uuid4()
        source = SimpleNamespace(
            id=source_id, user_id=payer_id, currency="USD", is_frozen=False,
            frozen_reason=None,
        )
        escrow = SimpleNamespace(
            id=escrow_id, user_id=987650, currency="USD", is_frozen=False,
            frozen_reason=None,
        )
        existing = SimpleNamespace(
            id=uuid.uuid4(),
            tx_type=TransactionType.TRANSFER.value,
            status=TransactionStatus.COMPLETED.value,
            amount=Decimal("25.00"),
            currency="USD",
            user_id=payer_id,
            recipient_user_id=escrow.user_id,
            tx_metadata={
                "marketplace_invoice_id": str(uuid.uuid4()),
                "service_code": "transport",
                "service_reference": "ride-original",
                "escrow_account_id": str(escrow_id),
                "escrow_service_type": "transport",
            },
        )
        monkeypatch.setattr(
            User,
            "get_by_private_id",
            staticmethod(lambda user_id: SimpleNamespace(transaction_pin_hash=None)),
        )
        service = WalletService()
        service._validate_currency = lambda currency: None
        service.account_repo.get_by_id = lambda account_id, for_update=False: {
            str(source_id): source,
            str(escrow_id): escrow,
        }.get(str(account_id))
        service.tx_repo.get_by_client_request_id = lambda key: existing
        with pytest.raises(DuplicateTransactionError):
            service.transfer(
                from_account_id=str(source_id),
                to_account_id=str(escrow_id),
                amount=Decimal("25.00"),
                currency="USD",
                client_request_id="MARKETPLACE-INVOICE-REPLAY",
                metadata={
                    "marketplace_invoice_id": str(uuid.uuid4()),
                    "service_code": "transport",
                    "service_reference": "ride-another",
                    "escrow_account_id": str(escrow_id),
                    "escrow_service_type": "transport",
                },
                system_initiated=True,
            )


def test_wallet_collection_fails_closed_without_transport_escrow(app, test_user, monkeypatch):
    from app.wallet.repositories.account_repository import AccountRepository
    from app.wallet.services.wallet_service import WalletService

    with app.app_context():
        payer_id = db.session.merge(test_user).id
        _configure_wallet_methods()
        monkeypatch.setattr(
            MarketplaceInvoiceService,
            "_wallet_account_available",
            staticmethod(lambda _user_id, _currency: True),
        )
        invoice = _create_invoice(payer_id, method="wallet", amount="25.00")
        account = SimpleNamespace(
            id=uuid.uuid4(), currency="USD", status="active",
            is_frozen=False, owner_type="user",
        )
        monkeypatch.setattr(
            AccountRepository,
            "get_by_user_id",
            lambda self, user_id, currency="USD", for_update=False: account,
        )

        def no_escrow(_currency):
            raise MarketplaceInvoiceError(
                "transport_escrow_unavailable",
                "Transport Wallet escrow is not configured for this currency.",
            )

        monkeypatch.setattr(
            MarketplaceInvoiceService, "_get_transport_escrow_account",
            staticmethod(no_escrow),
        )
        transfer_calls = []
        monkeypatch.setattr(
            WalletService, "transfer",
            lambda *args, **kwargs: transfer_calls.append(kwargs),
        )

        with pytest.raises(MarketplaceInvoiceError) as raised:
            MarketplaceInvoiceService.settle_after_completion(
                invoice_id=invoice.id,
                payer_user_id=payer_id,
                service_code="transport",
                service_reference=invoice.service_reference,
                amount="25.00",
                currency="USD",
                request_id="test-no-escrow",
            )

        assert raised.value.code == "transport_escrow_unavailable"
        assert transfer_calls == []
        invoice = MarketplaceInvoiceService.get_invoice(invoice.id)
        assert invoice.status == "due"
        assert invoice.transaction_id is None


def test_configured_but_unintegrated_provider_fails_closed(app, test_user):
    with app.app_context():
        # Clean up any leftover invoices from other tests
        MarketplaceInvoice.query.filter_by(service_code="transport").delete(synchronize_session=False)
        db.session.commit()
        
        payer_id = db.session.merge(test_user).id
        _configure_wallet_methods()
        with pytest.raises(MarketplaceInvoiceError) as raised:
            _create_invoice(payer_id, method="mobile_money_mtn_ug")
        assert raised.value.code == "method_not_integrated"
        assert MarketplaceInvoice.query.filter_by(
            service_code="transport",
        ).count() == 0


def test_wallet_invoice_is_paid_only_after_canonical_completed_transaction(
    app, test_user, monkeypatch
):
    from app.wallet.models.transaction import TransactionModel
    from app.wallet.repositories.account_repository import AccountRepository
    from app.wallet.services.wallet_service import WalletService

    with app.app_context():
        payer_id = db.session.merge(test_user).id
        _configure_wallet_methods()
        monkeypatch.setattr(
            MarketplaceInvoiceService,
            "_wallet_account_available",
            staticmethod(lambda _user_id, _currency: True),
        )
        invoice = _create_invoice(
            payer_id, method="wallet", amount="25.00"
        )
        account = SimpleNamespace(
            id=uuid.uuid4(), currency="USD", status="active",
            is_frozen=False, owner_type="user",
        )
        from app.identity.models.user import User
        escrow_user = User(
            email=f"escrow-{uuid.uuid4().hex[:8]}@example.com",
            username=f"escrow-{uuid.uuid4().hex[:8]}",
            password_hash="not-a-real-hash",
            email_verified=True,
            phone_verified=True,
            kyc_level=2,
            is_active=True,
        )
        db.session.add(escrow_user)
        db.session.commit()
        escrow = SimpleNamespace(
            id=uuid.uuid4(), user_id=escrow_user.id, currency="USD",
        )
        monkeypatch.setattr(
            AccountRepository,
            "get_by_user_id",
            lambda self, user_id, currency="USD", for_update=False: account,
        )
        monkeypatch.setattr(
            MarketplaceInvoiceService, "_get_transport_escrow_account",
            staticmethod(lambda currency: escrow),
        )
        calls = []
        transaction_id = uuid.uuid4()

        def fake_transfer(
            self, *, from_account_id, to_account_id, amount, currency,
            client_request_id, note, metadata, system_initiated,
        ):
            calls.append({
                "from_account_id": from_account_id,
                "to_account_id": to_account_id,
                "amount": amount,
                "currency": currency,
                "client_request_id": client_request_id,
                "note": note,
                "metadata": metadata,
                "system_initiated": system_initiated,
            })
            tx = TransactionModel(
                id=transaction_id,
                client_request_id=client_request_id,
                tx_type="transfer",
                status="completed",
                amount=Decimal("25.00"),
                currency="USD",
                user_id=payer_id,
                recipient_user_id=escrow.user_id,
                tx_metadata=metadata,
            )
            db.session.add(tx)
            db.session.commit()
            return {
                "status": "success",
                "transaction_id": str(transaction_id),
                "amount": "25.00",
                "currency": "USD",
            }

        monkeypatch.setattr(WalletService, "transfer", fake_transfer)
        first = MarketplaceInvoiceService.settle_after_completion(
            invoice_id=invoice.id,
            payer_user_id=payer_id,
            service_code="transport",
            service_reference=invoice.service_reference,
            amount="25.00",
            currency="USD",
            request_id="test-wallet-settlement",
        )
        assert first["status"] == "paid"
        assert first["transaction_id"] == str(transaction_id)
        assert calls == [{
            "from_account_id": str(account.id),
            "to_account_id": str(escrow.id),
            "amount": Decimal("25.00"),
            "currency": "USD",
            "client_request_id": "MARKETPLACE-INVOICE-" + str(invoice.id),
            "note": f"Transport marketplace invoice {invoice.service_reference}",
            "metadata": {
                "marketplace_invoice_id": str(invoice.id),
                "service_code": "transport",
                "service_reference": invoice.service_reference,
                "settlement_timing": "pay_on_completion",
                "request_id": "test-wallet-settlement",
                "escrow_account_id": str(escrow.id),
                "escrow_service_type": "transport",
            },
            "system_initiated": True,
        }]

        replay = MarketplaceInvoiceService.settle_after_completion(
            invoice_id=invoice.id,
            payer_user_id=payer_id,
            service_code="transport",
            service_reference=invoice.service_reference,
            amount="25.00",
            currency="USD",
            request_id="test-wallet-settlement-retry",
        )
        assert replay["already_processed"] is True
        assert len(calls) == 1
