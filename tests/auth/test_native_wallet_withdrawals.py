from decimal import Decimal
from types import SimpleNamespace
import uuid

import pytest


@pytest.fixture
def withdrawal_account(app):
    from app.extensions import db
    from app.identity.models.user import User
    from app.wallet.models.ledger import AccountModel, LedgerEntryModel, EntryType
    from app.wallet.models.transaction import TransactionModel, TransactionStatus, TransactionType

    with app.app_context():
        suffix = uuid.uuid4().hex[:10]
        user = User(
            email=f"withdrawal-{suffix}@example.com",
            username=f"withdrawal-{suffix}",
            password_hash="test-password-hash",
            is_active=True,
        )
        db.session.add(user)
        db.session.flush()
        user.set_transaction_pin("1234", session=db.session)

        account = AccountModel(
            user_id=user.id,
            owner_type="user",
            account_name="Withdrawal test UGX wallet",
            currency="UGX",
            status="active",
            is_frozen=False,
        )
        db.session.add(account)
        db.session.flush()

        funding = TransactionModel(
            client_request_id=f"withdrawal-test-fund-{suffix}",
            tx_type=TransactionType.DEPOSIT,
            status=TransactionStatus.COMPLETED,
            amount=Decimal("5000"),
            currency="UGX",
            user_id=user.id,
            account_id=account.id,
        )
        db.session.add(funding)
        db.session.flush()
        db.session.add(
            LedgerEntryModel(
                transaction_id=funding.id,
                account_id=account.id,
                entry_type=EntryType.CREDIT,
                amount=Decimal("5000"),
                currency="UGX",
            )
        )
        db.session.commit()
        result = (user.id, str(user.public_id), str(account.id))
        db.session.remove()
        return result


def _configure_withdrawal_checks(monkeypatch):
    from app.wallet.models.config import WalletSystemConfig
    from app.wallet.services.wallet_service import WalletService

    config = SimpleNamespace(
        withdrawals_enabled=True,
        max_withdrawal_amount=Decimal("100000"),
        withdrawal_fee_percent=Decimal("1.00"),
        max_daily_amount=Decimal("1000000"),
        max_monthly_amount=Decimal("10000000"),
    )
    monkeypatch.setattr(WalletSystemConfig, "get_config", classmethod(lambda cls: config))
    monkeypatch.setattr(WalletService, "_check_kyc_limits", lambda *args, **kwargs: None)
    monkeypatch.setattr(WalletService, "_check_fraud_risk", lambda *args, **kwargs: {"score": 0, "action": "allow"})
    monkeypatch.setattr(WalletService, "_check_daily_limit", lambda *args, **kwargs: None)
    monkeypatch.setattr(WalletService, "_check_monthly_limit", lambda *args, **kwargs: None)


def _create_pending_withdrawal(app, monkeypatch, withdrawal_account):
    from app.extensions import db
    from app.identity.models.user import User
    from app.wallet.models.transaction import TransactionModel
    from app.wallet.repositories.ledger_repository import LedgerRepository
    from app.wallet.services.native_withdrawal_service import NativeWithdrawalService
    from app.wallet.services.payment_gateway import PayoutResponse

    _configure_withdrawal_checks(monkeypatch)
    monkeypatch.setattr(
        NativeWithdrawalService,
        "_ensure_provider_ready",
        classmethod(lambda cls: None),
    )

    calls = []

    class FakePaymentOrchestrator:
        def initiate_withdrawal(self, payout_request):
            calls.append(payout_request)
            return PayoutResponse(
                success=True,
                payout_id=payout_request.reference,
                provider_reference="flw-transfer-991",
                status="pending",
                message="Transfer queued",
                amount=str(payout_request.amount),
                currency=payout_request.currency,
                reference=payout_request.reference,
            )

    monkeypatch.setattr(
        "app.wallet.services.payment_gateway.PaymentOrchestrator",
        FakePaymentOrchestrator,
    )

    with app.app_context():
        user_id, public_id, account_id = withdrawal_account
        user = db.session.get(User, user_id)
        quote = NativeWithdrawalService.create_quote(
            user,
            amount="1000",
            currency="UGX",
            network="MTN",
            phone_number="0700123456",
            beneficiary_name="Amina Nakato",
        )
        result = NativeWithdrawalService.confirm_quote(
            user,
            quote_token=quote["quote_token"],
            pin="1234",
        )
        tx = db.session.query(TransactionModel).filter_by(
            client_request_id=result["reference"]
        ).one()
        balance = LedgerRepository().get_balance(account_id, "UGX")
        snapshot = {
            "reference": result["reference"],
            "status": result["status"],
            "balance": balance,
            "provider_calls": len(calls),
            "payout_amount": tx.tx_metadata["payout_amount"],
            "fee_amount": tx.tx_metadata["fee_amount"],
            "total_wallet_debit": tx.tx_metadata["total_wallet_debit"],
        }
        db.session.remove()
        return snapshot, calls


def test_native_withdrawal_quote_masks_destination_and_shows_configured_fee(app, monkeypatch, withdrawal_account):
    from app.extensions import db
    from app.identity.models.user import User
    from app.wallet.services.native_withdrawal_service import NativeWithdrawalService

    _configure_withdrawal_checks(monkeypatch)
    monkeypatch.setattr(
        NativeWithdrawalService,
        "_ensure_provider_ready",
        classmethod(lambda cls: None),
    )

    with app.app_context():
        user = db.session.get(User, withdrawal_account[0])
        quote = NativeWithdrawalService.create_quote(
            user,
            amount="1000",
            currency="UGX",
            network="MTN",
            phone_number="+256700123456",
            beneficiary_name="Amina Nakato",
        )
        assert quote["amount"] == "1000"
        assert quote["platform_fee"] == "10.00"
        assert quote["total_wallet_debit"] == "1010.00"
        assert quote["network"] == "MTN"
        assert quote["masked_phone"].endswith("456")
        assert "0700123456" not in quote["quote_token"]
        assert "256700123456" not in quote["quote_token"]
        db.session.remove()


def test_native_withdrawal_reserves_funds_and_duplicate_confirmation_submits_once(app, monkeypatch, withdrawal_account):
    from app.extensions import db
    from app.identity.models.user import User
    from app.wallet.models.transaction import TransactionModel
    from app.wallet.repositories.ledger_repository import LedgerRepository
    from app.wallet.services.native_withdrawal_service import NativeWithdrawalService
    from app.wallet.services.payment_gateway import PayoutResponse

    _configure_withdrawal_checks(monkeypatch)
    monkeypatch.setattr(
        NativeWithdrawalService,
        "_ensure_provider_ready",
        classmethod(lambda cls: None),
    )
    calls = []

    class FakePaymentOrchestrator:
        def initiate_withdrawal(self, payout_request):
            calls.append(payout_request)
            return PayoutResponse(
                success=True,
                payout_id=payout_request.reference,
                provider_reference="flw-transfer-991",
                status="pending",
                message="Transfer queued",
                amount=str(payout_request.amount),
                currency=payout_request.currency,
                reference=payout_request.reference,
            )

    monkeypatch.setattr("app.wallet.services.payment_gateway.PaymentOrchestrator", FakePaymentOrchestrator)

    with app.app_context():
        user = db.session.get(User, withdrawal_account[0])
        quote = NativeWithdrawalService.create_quote(
            user,
            amount="1000",
            currency="UGX",
            network="MTN",
            phone_number="0700123456",
            beneficiary_name="Amina Nakato",
        )
        first = NativeWithdrawalService.confirm_quote(user, quote_token=quote["quote_token"], pin="1234")
        second = NativeWithdrawalService.confirm_quote(user, quote_token=quote["quote_token"], pin="1234")

        tx = db.session.query(TransactionModel).filter_by(client_request_id=first["reference"]).one()
        balance = LedgerRepository().get_balance(tx.account_id, "UGX")

        assert first["status"] == "pending"
        assert second["reference"] == first["reference"]
        assert second["status"] == "pending"
        assert balance == Decimal("3990.00")
        assert tx.status == "pending"
        assert tx.amount == Decimal("1010.00")
        assert tx.tx_metadata["payout_state"] == "processing"
        assert len(calls) == 1
        assert calls[0].recipient_bank_code == "MTN"
        assert calls[0].recipient_account == "256700123456"
        db.session.remove()


def test_verified_failed_payout_reverses_wallet_debit_once(app, monkeypatch, withdrawal_account):
    from app.extensions import db
    from app.identity.models.user import User
    from app.wallet.models.transaction import TransactionModel, TransactionStatus
    from app.wallet.repositories.ledger_repository import LedgerRepository
    from app.wallet.services.native_withdrawal_service import NativeWithdrawalService

    snapshot, _calls = _create_pending_withdrawal(app, monkeypatch, withdrawal_account)
    with app.app_context():
        NativeWithdrawalService.handle_provider_event(
            snapshot["reference"],
            "flutterwave",
            {
                "id": "flw-transfer-991",
                "reference": snapshot["reference"],
                "status": "FAILED",
                "amount": "1000",
                "currency": "UGX",
                "complete_message": "Beneficiary wallet rejected the payout",
            },
        )
        tx = db.session.query(TransactionModel).filter_by(
            client_request_id=snapshot["reference"]
        ).one()
        balance_after_first = LedgerRepository().get_balance(tx.account_id, "UGX")
        assert tx.status == TransactionStatus.FAILED
        assert tx.tx_metadata["payout_state"] == "failed"
        assert balance_after_first == Decimal("5000.00")

        NativeWithdrawalService.handle_provider_event(
            snapshot["reference"],
            "flutterwave",
            {
                "id": "flw-transfer-991",
                "reference": snapshot["reference"],
                "status": "FAILED",
                "amount": "1000",
                "currency": "UGX",
                "complete_message": "Duplicate provider event",
            },
        )
        balance_after_duplicate = LedgerRepository().get_balance(tx.account_id, "UGX")
        reversal_count = db.session.query(TransactionModel).filter_by(
            client_request_id=f"{snapshot['reference']}-REV"
        ).count()
        assert balance_after_duplicate == Decimal("5000.00")
        assert reversal_count == 1
        db.session.remove()


def test_payout_event_with_wrong_amount_does_not_complete_withdrawal(app, monkeypatch, withdrawal_account):
    from app.extensions import db
    from app.wallet.models.transaction import TransactionModel, TransactionStatus
    from app.wallet.services.native_withdrawal_service import NativeWithdrawalError, NativeWithdrawalService

    snapshot, _calls = _create_pending_withdrawal(app, monkeypatch, withdrawal_account)
    with app.app_context():
        with pytest.raises(NativeWithdrawalError, match="Payout amount"):
            NativeWithdrawalService.handle_provider_event(
                snapshot["reference"],
                "flutterwave",
                {
                    "id": "flw-transfer-991",
                    "reference": snapshot["reference"],
                    "status": "SUCCESSFUL",
                    "amount": "999",
                    "currency": "UGX",
                },
            )
        tx = db.session.query(TransactionModel).filter_by(
            client_request_id=snapshot["reference"]
        ).one()
        assert tx.status == TransactionStatus.PENDING
        assert tx.tx_metadata["payout_state"] == "processing"
        db.session.remove()


def test_verified_success_completes_without_reversing_reserved_funds(app, monkeypatch, withdrawal_account):
    from app.extensions import db
    from app.wallet.models.transaction import TransactionModel, TransactionStatus
    from app.wallet.repositories.ledger_repository import LedgerRepository
    from app.wallet.services.native_withdrawal_service import NativeWithdrawalService

    snapshot, _calls = _create_pending_withdrawal(app, monkeypatch, withdrawal_account)
    with app.app_context():
        NativeWithdrawalService.handle_provider_event(
            snapshot["reference"],
            "flutterwave",
            {
                "id": "flw-transfer-991",
                "reference": snapshot["reference"],
                "status": "SUCCESSFUL",
                "amount": "1000",
                "currency": "UGX",
            },
        )
        tx = db.session.query(TransactionModel).filter_by(
            client_request_id=snapshot["reference"]
        ).one()
        assert tx.status == TransactionStatus.COMPLETED
        assert tx.tx_metadata["payout_state"] == "completed"
        assert LedgerRepository().get_balance(tx.account_id, "UGX") == Decimal("3990.00")
        assert db.session.query(TransactionModel).filter_by(
            client_request_id=f"{snapshot['reference']}-REV"
        ).count() == 0
        db.session.remove()


def test_native_withdrawal_api_routes_return_safe_quote_and_pending_state(client, monkeypatch):
    from app.auth import mobile_api
    from app.wallet.services.native_withdrawal_service import NativeWithdrawalService

    user = SimpleNamespace(id=991, public_id="user-public-withdrawal-991")

    monkeypatch.setattr(
        mobile_api,
        "require_mobile_context",
        lambda expected_client=None: ({"user": user}, None),
    )
    monkeypatch.setattr(
        NativeWithdrawalService,
        "create_quote",
        lambda owner, **kwargs: {
            "quote_id": "quote-123",
            "quote_token": "signed-quote",
            "amount": "1000",
            "currency": "UGX",
            "platform_fee": "10.00",
            "total_wallet_debit": "1010.00",
            "masked_phone": "+256 *** ***456",
        },
    )
    monkeypatch.setattr(
        NativeWithdrawalService,
        "confirm_quote",
        lambda owner, **kwargs: {
            "reference": "NATWD-TEST",
            "status": "pending",
            "amount": "1000",
            "currency": "UGX",
        },
    )
    monkeypatch.setattr(
        NativeWithdrawalService,
        "get_status",
        lambda owner, reference: {
            "reference": reference,
            "status": "pending",
            "amount": "1000",
            "currency": "UGX",
        },
    )

    headers = {"Authorization": "Bearer native-test-token"}
    quote = client.post(
        "/api/mobile/v1/wallet/withdrawals/quote",
        json={
            "amount": "1000",
            "currency": "UGX",
            "network": "MTN",
            "phone_number": "0700123456",
            "beneficiary_name": "Amina Nakato",
        },
        headers=headers,
    )
    assert quote.status_code == 200
    assert quote.get_json()["data"]["quote_token"] == "signed-quote"

    confirmed = client.post(
        "/api/mobile/v1/wallet/withdrawals",
        json={"quote_token": "signed-quote", "pin": "1234"},
        headers=headers,
    )
    assert confirmed.status_code == 202
    assert confirmed.get_json()["data"]["status"] == "pending"

    status = client.get("/api/mobile/v1/wallet/withdrawals/NATWD-TEST", headers=headers)
    assert status.status_code == 202
    assert status.get_json()["data"]["reference"] == "NATWD-TEST"
