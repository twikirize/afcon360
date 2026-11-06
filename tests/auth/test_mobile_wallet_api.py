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


def test_native_deposit_uses_existing_account_and_returns_provider_checkout_without_crediting(client, monkeypatch):
    from app.auth import mobile_api
    import app.wallet.models.ledger as ledger_models
    import app.extensions as extensions
    from app.wallet.services import deposit_intent

    user = SimpleNamespace(id=745, public_id="native-deposit-user-745")
    account = SimpleNamespace(
        id="wallet-account-745",
        owner_type="user",
        status="active",
        is_frozen=False,
    )
    stored = {}
    captured = {}

    class FakeAccountModel:
        query = _FilterQuery(account)

    class FakeRedis:
        def set(self, key, value, ex=None, nx=None):
            captured["lock"] = (key, value, ex, nx)
            return True

        def eval(self, script, number_of_keys, key, token):
            return 1

    class FakeFlutterwaveService:
        def initiate_deposit(self, **kwargs):
            captured["initiate"] = kwargs
            stored.update({
                "account_id": kwargs["account_id"],
                "user_id": kwargs["user_id"],
                "amount": str(kwargs["amount"]),
                "currency": kwargs["currency"],
                "source": "flutterwave",
                "payment_method": kwargs["payment_method"],
                "reference": kwargs["idempotency_key"],
                "authorization_url": "https://checkout.flutterwave.com/hosted/test",
                "status": "pending",
            })
            return {
                "success": True,
                "status": "pending",
                "reference": kwargs["idempotency_key"],
                "authorization_url": stored["authorization_url"],
            }

    _authenticated_mobile_user(monkeypatch, user)
    monkeypatch.setattr(ledger_models, "AccountModel", FakeAccountModel)
    monkeypatch.setattr(extensions, "redis_client", FakeRedis())
    monkeypatch.setattr(deposit_intent, "get_deposit_intent", lambda reference: dict(stored) if stored else None)
    monkeypatch.setattr(deposit_intent, "save_deposit_intent", lambda reference, data: stored.update(data))
    monkeypatch.setattr(deposit_intent, "mark_deposit_intent_status", lambda reference, status: stored.update(status=status))
    monkeypatch.setattr("app.wallet.payments.flutterwave.FlutterwaveService", FakeFlutterwaveService)

    response = client.post(
        "/api/mobile/v1/wallet/deposits",
        json={"amount": "25000.00", "currency": "UGX", "payment_method": "mobilemoney"},
        headers={
            "Authorization": "Bearer native-test-token",
            "X-Idempotency-Key": "native-deposit-request-0001",
        },
    )

    assert response.status_code == 201
    body = response.get_json()["data"]
    assert body["status"] == "pending"
    assert body["payment_provider"] == "flutterwave"
    assert body["authorization_url"] == "https://checkout.flutterwave.com/hosted/test"
    assert captured["initiate"]["account_id"] == str(account.id)
    assert captured["initiate"]["user_id"] == user.id
    assert captured["initiate"]["amount"] == Decimal("25000.00")
    assert stored["status"] == "pending"
    assert captured["lock"][2:] == (60, True)


def test_native_deposit_retry_reuses_existing_checkout_and_does_not_create_second_provider_request(client, monkeypatch):
    from app.auth import mobile_api
    import app.wallet.models.ledger as ledger_models
    from app.wallet.services import deposit_intent
    import app.wallet.payments.flutterwave as flutterwave_module

    user = SimpleNamespace(id=746, public_id="native-deposit-user-746")
    account = SimpleNamespace(id="wallet-account-746", owner_type="user", status="active", is_frozen=False)
    existing = {
        "account_id": str(account.id),
        "user_id": user.id,
        "amount": "9000.00",
        "currency": "UGX",
        "source": "flutterwave",
        "payment_method": "mobilemoney",
        "reference": "NATDEP-RETRY-REFERENCE",
        "authorization_url": "https://checkout.flutterwave.com/hosted/reused",
        "status": "pending",
    }
    captured = {}

    class FakeAccountModel:
        query = _FilterQuery(account)

    class MustNotInitiate:
        def initiate_deposit(self, **kwargs):
            pytest.fail("An existing idempotent pending checkout must be reused")

    _authenticated_mobile_user(monkeypatch, user)
    monkeypatch.setattr(ledger_models, "AccountModel", FakeAccountModel)
    monkeypatch.setattr(
        mobile_api,
        "_native_deposit_reference",
        lambda owner, key: existing["reference"],
    )
    monkeypatch.setattr(deposit_intent, "get_deposit_intent", lambda reference: dict(existing))
    monkeypatch.setattr(flutterwave_module, "FlutterwaveService", MustNotInitiate)

    response = client.post(
        "/api/mobile/v1/wallet/deposits",
        json={"amount": "9000.00", "currency": "UGX", "payment_method": "mobilemoney"},
        headers={
            "Authorization": "Bearer native-test-token",
            "X-Idempotency-Key": "native-deposit-request-0002",
        },
    )

    assert response.status_code == 200
    assert response.get_json()["data"]["authorization_url"] == existing["authorization_url"]
    assert response.get_json()["data"]["reference"] == existing["reference"]


def test_native_deposit_refresh_is_owner_scoped_and_returns_pending_when_provider_not_confirmed(client, monkeypatch):
    from app.auth import mobile_api
    import app.wallet.payments.flutterwave as flutterwave_module

    user = SimpleNamespace(id=747, public_id="native-deposit-user-747")
    intent = {
        "user_id": user.id,
        "account_id": "wallet-account-747",
        "amount": "4000.00",
        "currency": "UGX",
        "source": "flutterwave",
        "status": "pending",
    }

    class FakeFlutterwaveService:
        def verify_and_credit(self, reference):
            return {"success": False, "status": "pending", "error": "not confirmed"}

    _authenticated_mobile_user(monkeypatch, user)
    monkeypatch.setattr(
        mobile_api,
        "_native_deposit_intent",
        lambda reference, owner: dict(intent) if int(owner.id) == int(intent["user_id"]) else None,
    )
    monkeypatch.setattr(flutterwave_module, "FlutterwaveService", FakeFlutterwaveService)

    response = client.post(
        "/api/mobile/v1/wallet/deposits/NATDEP-OWNED-REFERENCE/refresh",
        headers={"Authorization": "Bearer native-test-token"},
    )

    assert response.status_code == 202
    assert response.get_json()["data"]["status"] == "pending"
    assert response.get_json()["data"]["reference"] == "NATDEP-OWNED-REFERENCE"


def test_flutterwave_verification_does_not_consume_intent_while_payment_is_pending(app, monkeypatch):
    import app.wallet.payments.flutterwave as flutterwave_module
    from app.wallet.payments.flutterwave import FlutterwaveService
    from app.wallet.services import deposit_intent

    captured = {"marked": []}
    intent = {
        "account_id": "wallet-uuid",
        "user_id": 748,
        "amount": "7000.00",
        "currency": "UGX",
        "payment_method": "mobilemoney",
        "status": "pending",
    }

    class FakeResponse:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {"data": {"status": "pending", "amount": "7000", "currency": "UGX"}}

    monkeypatch.setattr(deposit_intent, "get_deposit_intent", lambda reference: dict(intent))
    monkeypatch.setattr(
        deposit_intent,
        "mark_deposit_intent_status",
        lambda reference, status: captured["marked"].append((reference, status)),
    )
    monkeypatch.setattr(
        flutterwave_module.requests,
        "get",
        lambda *args, **kwargs: FakeResponse(),
    )

    with app.app_context():
        app.config["FLUTTERWAVE_BASE_URL"] = "https://flutterwave.test"
        app.config["FLUTTERWAVE_SECRET_KEY"] = "test-secret"
        service = FlutterwaveService.__new__(FlutterwaveService)
        service.wallet_service = SimpleNamespace(
            deposit=lambda **kwargs: pytest.fail("Pending provider payments must never credit the ledger")
        )
        result = service.verify_and_credit("NATDEP-PENDING-REFERENCE")

    assert result["success"] is False
    assert result["status"] == "pending"
    assert captured["marked"] == []


def test_flutterwave_verification_credits_only_matching_provider_amount_and_currency(app, monkeypatch):
    import app.wallet.payments.flutterwave as flutterwave_module
    from app.wallet.payments.flutterwave import FlutterwaveService
    from app.wallet.services import deposit_intent

    intent = {
        "account_id": "wallet-uuid",
        "user_id": 749,
        "amount": "7000.00",
        "currency": "UGX",
        "payment_method": "mobilemoney",
        "audit_transaction_id": "audit-deposit-749",
        "status": "pending",
    }
    captured = {"marked": [], "deposit": None}

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "data": {
                    "status": "successful",
                    "amount": "7000",
                    "currency": "UGX",
                    "id": "provider-payment-749",
                }
            }

    class FakeLedgerRepository:
        def get_balance(self, account_id, currency):
            assert account_id == "wallet-uuid"
            assert currency == "UGX"
            return Decimal("1000.00")

    class FakeWalletService:
        def deposit(self, **kwargs):
            captured["deposit"] = kwargs
            return {
                "status": "success",
                "transaction_id": "ledger-transaction-749",
                "already_processed": False,
            }

    monkeypatch.setattr(deposit_intent, "get_deposit_intent", lambda reference: dict(intent))
    monkeypatch.setattr(
        deposit_intent,
        "mark_deposit_intent_status",
        lambda reference, status: captured["marked"].append((reference, status)),
    )
    monkeypatch.setattr(
        flutterwave_module.requests,
        "get",
        lambda *args, **kwargs: FakeResponse(),
    )
    monkeypatch.setattr(
        "app.wallet.repositories.ledger_repository.LedgerRepository",
        FakeLedgerRepository,
    )
    monkeypatch.setattr(
        flutterwave_module.AuditService,
        "financial",
        lambda **kwargs: None,
    )

    with app.app_context():
        app.config["FLUTTERWAVE_BASE_URL"] = "https://flutterwave.test"
        app.config["FLUTTERWAVE_SECRET_KEY"] = "test-secret"
        service = FlutterwaveService.__new__(FlutterwaveService)
        service.wallet_service = FakeWalletService()
        result = service.verify_and_credit("NATDEP-COMPLETED-REFERENCE")

    assert result["success"] is True
    assert result["status"] == "completed"
    assert captured["deposit"]["account_id"] == "wallet-uuid"
    assert captured["deposit"]["client_request_id"] == "NATDEP-COMPLETED-REFERENCE"
    assert captured["deposit"]["system_initiated"] is True
    assert captured["deposit"]["amount"] == Decimal("7000.00")
    assert captured["marked"] == [("NATDEP-COMPLETED-REFERENCE", "completed")]


def test_flutterwave_amount_or_currency_mismatch_fails_without_wallet_credit(app, monkeypatch):
    import app.wallet.payments.flutterwave as flutterwave_module
    from app.wallet.payments.flutterwave import FlutterwaveService
    from app.wallet.services import deposit_intent

    intent = {
        "account_id": "wallet-uuid",
        "user_id": 750,
        "amount": "7000.00",
        "currency": "UGX",
        "payment_method": "mobilemoney",
        "status": "pending",
    }
    marked = []

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "data": {
                    "status": "successful",
                    "amount": "6999",
                    "currency": "UGX",
                    "id": "provider-payment-wrong-amount",
                }
            }

    monkeypatch.setattr(deposit_intent, "get_deposit_intent", lambda reference: dict(intent))
    monkeypatch.setattr(
        deposit_intent,
        "mark_deposit_intent_status",
        lambda reference, status: marked.append((reference, status)),
    )
    monkeypatch.setattr(
        flutterwave_module.requests,
        "get",
        lambda *args, **kwargs: FakeResponse(),
    )

    with app.app_context():
        app.config["FLUTTERWAVE_BASE_URL"] = "https://flutterwave.test"
        app.config["FLUTTERWAVE_SECRET_KEY"] = "test-secret"
        service = FlutterwaveService.__new__(FlutterwaveService)
        service.wallet_service = SimpleNamespace(
            deposit=lambda **kwargs: pytest.fail("A mismatched provider payment must never credit the ledger")
        )
        result = service.verify_and_credit("NATDEP-MISMATCH-REFERENCE")

    assert result["success"] is False
    assert result["status"] == "failed"
    assert marked == [("NATDEP-MISMATCH-REFERENCE", "failed")]
