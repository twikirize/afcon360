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


def test_configured_but_unintegrated_provider_fails_closed(app, test_user):
    with app.app_context():
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
        account = SimpleNamespace(id=uuid.uuid4(), currency="USD")
        monkeypatch.setattr(
            AccountRepository,
            "get_by_user_id",
            lambda self, user_id, currency="USD", for_update=False: account,
        )
        calls = []
        transaction_id = uuid.uuid4()

        def fake_withdraw(
            self, *, account_id, amount, currency, client_request_id, metadata,
            payment_method, payment_provider, actor_id, system_initiated,
        ):
            calls.append({
                "account_id": account_id,
                "amount": amount,
                "currency": currency,
                "client_request_id": client_request_id,
                "metadata": metadata,
                "payment_method": payment_method,
                "payment_provider": payment_provider,
                "actor_id": actor_id,
                "system_initiated": system_initiated,
            })
            tx = TransactionModel(
                id=transaction_id,
                client_request_id=client_request_id,
                tx_type="withdraw",
                status="completed",
                amount=Decimal("25.00"),
                currency="USD",
                user_id=payer_id,
            )
            db.session.add(tx)
            db.session.commit()
            return {
                "status": "success",
                "transaction_id": str(transaction_id),
                "amount": "25.00",
                "currency": "USD",
            }

        monkeypatch.setattr(WalletService, "withdraw", fake_withdraw)
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
            "account_id": str(account.id),
            "amount": Decimal("25.00"),
            "currency": "USD",
            "client_request_id": "MARKETPLACE-INVOICE-" + str(invoice.id),
            "metadata": {
                "marketplace_invoice_id": str(invoice.id),
                "service_code": "transport",
                "service_reference": invoice.service_reference,
                "settlement_timing": "pay_on_completion",
                "request_id": "test-wallet-settlement",
            },
            "payment_method": "wallet",
            "payment_provider": "afcon360_wallet",
            "actor_id": payer_id,
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
