from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest


def _authenticated_mobile_user(monkeypatch, user):
    from app.auth import mobile_api

    monkeypatch.setattr(
        mobile_api,
        "require_mobile_context",
        lambda expected_client=None: ({"user": user}, None),
    )


class _FilterQuery:
    def __init__(self, row):
        self.row = row
        self.filters = None

    def filter_by(self, **kwargs):
        self.filters = kwargs
        return self

    def first(self):
        return self.row


def test_native_wallet_transfer_uses_authenticated_sender_and_canonical_service(client, monkeypatch):
    from app.auth import mobile_api
    import app.wallet.models.ledger as ledger_models
    import app.wallet.services.wallet_service as wallet_service_module

    user = SimpleNamespace(
        id=741,
        public_id="user-public-741",
        transaction_pin_hash="stored-pin-hash",
    )
    recipient = SimpleNamespace(display_name="Recipient")
    sender_account = SimpleNamespace(
        id="sender-account-uuid",
        owner_type="user",
        status="active",
        is_frozen=False,
    )
    recipient_account = SimpleNamespace(
        id="recipient-account-uuid",
        currency="UGX",
        status="active",
        is_frozen=False,
    )
    identity = SimpleNamespace(identity_type="AFCON360_ID", normalized_value="AFC-123456")
    captured = {}

    class FakeAccountModel:
        query = _FilterQuery(sender_account)

    class FakeWalletService:
        def transfer(self, **kwargs):
            captured.update(kwargs)
            return {
                "status": "success",
                "transaction_id": "transaction-uuid",
                "amount": "12500.00",
                "currency": "UGX",
                "new_balance_from": "87500.00",
                "new_balance_to": "22500.00",
                "already_processed": False,
            }

    _authenticated_mobile_user(monkeypatch, user)
    monkeypatch.setattr(ledger_models, "AccountModel", FakeAccountModel)
    monkeypatch.setattr(wallet_service_module, "WalletService", FakeWalletService)
    monkeypatch.setattr(
        mobile_api,
        "_resolve_native_wallet_recipient",
        lambda identifier, sender_currency=None: (
            identity, recipient, recipient_account, None
        ),
    )

    response = client.post(
        "/api/mobile/v1/wallet/transfers",
        json={
            "identifier": "AFC-123456",
            "amount": "12500.00",
            "currency": "UGX",
            "pin": "1234",
            "note": "Trip contribution",
        },
        headers={
            "Authorization": "Bearer native-test-token",
            "X-Idempotency-Key": "native-transfer-request-0001",
        },
    )

    assert response.status_code == 200
    body = response.get_json()
    assert body["success"] is True
    assert body["data"]["reference"] == "transaction-uuid"
    assert body["data"]["new_balance"] == "87500.00"
    assert captured["from_account_id"] == "sender-account-uuid"
    assert captured["to_account_id"] == "recipient-account-uuid"
    assert captured["client_request_id"] == "native-transfer-request-0001"
    assert captured["pin"] == "1234"
    assert FakeAccountModel.query.filters == {
        "user_id": user.id,
        "owner_type": "user",
        "currency": "UGX",
    }


def test_native_wallet_transfer_rejects_missing_pin_before_service(client, monkeypatch):
    from app.auth import mobile_api
    import app.wallet.models.ledger as ledger_models
    import app.wallet.services.wallet_service as wallet_service_module

    user = SimpleNamespace(id=742, public_id="user-public-742", transaction_pin_hash="hash")
    recipient = SimpleNamespace(display_name="Recipient")
    sender_account = SimpleNamespace(owner_type="user", status="active", is_frozen=False)
    recipient_account = SimpleNamespace(currency="UGX", status="active", is_frozen=False)

    class FakeAccountModel:
        query = _FilterQuery(sender_account)

    class MustNotTransfer:
        def transfer(self, **kwargs):
            pytest.fail("Transfer service must not run without a client-supplied PIN")

    _authenticated_mobile_user(monkeypatch, user)
    monkeypatch.setattr(ledger_models, "AccountModel", FakeAccountModel)
    monkeypatch.setattr(wallet_service_module, "WalletService", MustNotTransfer)
    monkeypatch.setattr(
        mobile_api,
        "_resolve_native_wallet_recipient",
        lambda identifier, sender_currency=None: (
            SimpleNamespace(identity_type="AFCON360_ID", normalized_value="AFC-654321"),
            recipient,
            recipient_account,
            None,
        ),
    )

    response = client.post(
        "/api/mobile/v1/wallet/transfers",
        json={"identifier": "AFC-654321", "amount": "100", "currency": "UGX"},
        headers={
            "Authorization": "Bearer native-test-token",
            "X-Idempotency-Key": "native-transfer-request-0002",
        },
    )

    assert response.status_code == 403
    assert response.get_json()["code"] == "transaction_pin_required"


def test_native_wallet_transfer_requires_currency_match_before_debit(client, monkeypatch):
    from app.auth import mobile_api
    import app.wallet.models.ledger as ledger_models
    import app.wallet.services.wallet_service as wallet_service_module

    user = SimpleNamespace(id=743, public_id="user-public-743", transaction_pin_hash="hash")
    sender_account = SimpleNamespace(owner_type="user", status="active", is_frozen=False)
    recipient_account = SimpleNamespace(currency="KES", status="active", is_frozen=False)

    class FakeAccountModel:
        query = _FilterQuery(sender_account)

    class MustNotTransfer:
        def transfer(self, **kwargs):
            pytest.fail("A cross-currency transfer without a displayed FX quote must not debit")

    _authenticated_mobile_user(monkeypatch, user)
    monkeypatch.setattr(ledger_models, "AccountModel", FakeAccountModel)
    monkeypatch.setattr(wallet_service_module, "WalletService", MustNotTransfer)
    monkeypatch.setattr(
        mobile_api,
        "_resolve_native_wallet_recipient",
        lambda identifier, sender_currency=None: (
            SimpleNamespace(identity_type="AFCON360_ID", normalized_value="AFC-111111"),
            SimpleNamespace(display_name="Recipient"),
            recipient_account,
            None,
        ),
    )

    response = client.post(
        "/api/mobile/v1/wallet/transfers",
        json={"identifier": "AFC-111111", "amount": "100", "currency": "UGX", "pin": "1234"},
        headers={
            "Authorization": "Bearer native-test-token",
            "X-Idempotency-Key": "native-transfer-request-0003",
        },
    )

    assert response.status_code == 409
    assert response.get_json()["code"] == "recipient_currency_mismatch"


def test_native_wallet_pin_status_handles_legacy_naive_lock_timestamp(client, monkeypatch):
    from app.auth import mobile_api

    user = SimpleNamespace(
        id=744,
        public_id="user-public-744",
        transaction_pin_hash="stored-pin-hash",
        transaction_pin_locked_until=datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(minutes=5),
    )
    _authenticated_mobile_user(monkeypatch, user)

    response = client.get(
        "/api/mobile/v1/wallet/pin",
        headers={"Authorization": "Bearer native-test-token"},
    )

    assert response.status_code == 200
    assert response.get_json()["data"]["pin_set"] is True
    assert response.get_json()["data"]["locked"] is True
