"""Transport settlement is separate from the ride lifecycle."""
from datetime import datetime, timezone

import pytest

from app.extensions import db
from app.transport.models import Booking, BookingPayment, BookingStatus, Currency, PaymentStatus, ProviderType, ServiceType
from app.transport.services.payment_service import PaymentService
from app.utils.exceptions import ValidationError

pytestmark = pytest.mark.usefixtures("db_session")


def _booking(user_id, status, method="cash"):
    booking = Booking(
        user_id=user_id,
        provider_type=ProviderType.INDIVIDUAL_DRIVER,
        service_type=ServiceType.ON_DEMAND,
        pickup_location={"address": "Pickup"},
        dropoff_location={"address": "Destination"},
        pickup_time=datetime.now(timezone.utc),
        passenger_count=1,
        base_price=25,
        subtotal=25,
        total_amount=25,
        final_price=25,
        payment_method=method,
        payment_status=PaymentStatus.PENDING,
        status=status,
    )
    db.session.add(booking)
    db.session.commit()
    return booking.id


def _payment_payload(method="cash"):
    return {"amount": "25.00", "currency": "USD", "payment_method": method}


def test_settlement_rejected_before_trip_completion(app, test_user, monkeypatch):
    with app.app_context():
        user_id = db.session.merge(test_user).id
        booking_id = _booking(user_id, BookingStatus.IN_PROGRESS)
        monkeypatch.setattr(
            PaymentService, "_validate_payment_method", staticmethod(lambda booking, method: None)
        )

        with pytest.raises(ValidationError, match="only after the trip is completed"):
            PaymentService.process_payment(booking_id, _payment_payload())

        db.session.expire_all()
        booking = db.session.get(Booking, booking_id)
        assert booking.status == BookingStatus.IN_PROGRESS.value
        assert booking.payment_status == PaymentStatus.PENDING.value
        assert booking.payment_captured_at is None
        payment_row = BookingPayment.query.filter_by(booking_id=booking_id).one()
        assert payment_row.payment_status == PaymentStatus.PENDING
        assert payment_row.payment_method == "cash"
        assert payment_row.payment_reference


def test_cash_stays_pending_after_trip_completion_until_receipt_confirmed(
    app, test_user, monkeypatch
):
    with app.app_context():
        user_id = db.session.merge(test_user).id
        booking_id = _booking(user_id, BookingStatus.COMPLETED, "cash")
        monkeypatch.setattr(
            PaymentService, "_validate_payment_method", staticmethod(lambda booking, method: None)
        )

        result = PaymentService.process_payment(booking_id, _payment_payload("cash"))
        db.session.expire_all()
        booking = db.session.get(Booking, booking_id)

        assert result["success"] is True
        assert result["data"]["payment_status"] == "pending"
        assert result["data"]["requires_cash_receipt_confirmation"] is True
        assert booking.status == BookingStatus.COMPLETED.value
        assert booking.payment_status == PaymentStatus.PENDING.value
        assert booking.payment_captured_at is None
        assert booking.payment_gateway_reference is None


def test_transport_choices_hide_configured_but_unimplemented_gateway_methods(monkeypatch):
    from app.transport.services import payment_methods

    configured = [
        {"code": "cash", "label": "Cash", "enabled": True},
        {"code": "wallet", "label": "Wallet", "enabled": True},
        {"code": "flutterwave", "label": "Card", "enabled": True},
        {"code": "mtn_momo", "label": "MTN Mobile Money", "enabled": True},
    ]
    monkeypatch.setattr(
        payment_methods, "get_available_payment_methods",
        lambda user_id=None, wallet_currency_code=None: configured,
    )
    monkeypatch.setattr(
        "app.transport.services.payment_config.get_user_wallet_status",
        lambda user_id, currency_code=None: True,
    )

    methods = payment_methods.get_available_transport_payment_methods(123)
    assert [method["code"] for method in methods] == ["cash", "wallet"]


def test_wallet_choice_must_match_transport_quote_currency(monkeypatch):
    from app.transport.services import payment_methods

    configured = [
        {"code": "cash", "label": "Cash", "enabled": True},
        {"code": "wallet", "label": "Wallet", "enabled": True},
    ]
    wallet_checks = []

    monkeypatch.setattr(
        payment_methods,
        "get_available_payment_methods",
        lambda user_id=None, wallet_currency_code=None: configured,
    )

    def wallet_status(user_id, currency_code=None):
        wallet_checks.append(currency_code)
        return currency_code == "USD"

    monkeypatch.setattr(
        "app.transport.services.payment_config.get_user_wallet_status",
        wallet_status,
    )

    methods = payment_methods.get_available_transport_payment_methods(123)
    assert [method["code"] for method in methods] == ["cash", "wallet"]
    assert wallet_checks[-1] == "USD"
    descriptions = {method["code"]: method["description"] for method in methods}
    assert "USD" in descriptions["cash"]
    assert "USD Wallet balance" in descriptions["wallet"]
    assert "No automatic currency conversion" in descriptions["wallet"]

    # The same rider must not be offered a UGX-wallet debit for a different
    # quote denomination unless an actual UGX account exists.
    methods_ugx = payment_methods.get_available_transport_payment_methods(
        123, currency_code="UGX"
    )
    assert [method["code"] for method in methods_ugx] == ["cash"]
    assert wallet_checks[-1] == "UGX"


def test_anonymous_transport_choices_do_not_advertise_wallet(monkeypatch):
    from app.transport.services import payment_methods

    monkeypatch.setattr(
        payment_methods, "get_available_payment_methods",
        lambda user_id=None, wallet_currency_code=None: [
            {"code": "cash", "label": "Cash", "enabled": True},
            {"code": "wallet", "label": "Wallet", "enabled": True},
        ],
    )

    methods = payment_methods.get_available_transport_payment_methods(None)
    assert [method["code"] for method in methods] == ["cash"]


def test_payment_validation_accepts_canonical_ugx_for_east_africa():
    from app.utils.validators import validate_payment

    valid, errors = validate_payment({
        "amount": "25000.00",
        "currency": "UGX",
        "payment_method": "WALLET",
    })
    assert valid, errors


def test_owner_can_retry_wallet_payment_for_completed_unpaid_trip(
    app, authenticated_client, test_user, monkeypatch
):
    with app.app_context():
        rider = db.session.merge(test_user)
        user_id = rider.id
        booking_id = _booking(user_id, BookingStatus.COMPLETED, "wallet")
        booking = db.session.get(Booking, booking_id)
        booking.booking_reference = "WALLET-RETRY-TEST"
        booking.final_price = 25
        booking.total_amount = 25
        booking.currency = Currency.USD
        booking.payment_status = PaymentStatus.PENDING
        db.session.commit()

    called = {}

    def fake_process(booking_id, payment_data, request_id=None):
        called["booking_id"] = booking_id
        called["payment_data"] = payment_data
        called["request_id"] = request_id
        return {
            "success": True,
            "data": {
                "payment_status": "captured",
                "payment_reference": "TRP-WALLET-RETRY-TEST",
                "amount": 25.0,
            },
        }

    monkeypatch.setattr(
        PaymentService, "process_payment", staticmethod(fake_process)
    )
    response = authenticated_client.post(
        "/api/transport/rides/WALLET-RETRY-TEST/payment/settle-wallet",
        json={},
    )
    assert response.status_code == 200, response.get_data(as_text=True)
    body = response.get_json()
    assert body["success"] is True
    assert body["data"]["payment_status"] == "captured"
    assert called["booking_id"] == booking_id
    assert called["payment_data"] == {
        "amount": "25",
        "currency": "USD",
        "payment_method": "wallet",
    }
    assert called["request_id"] == "trip-complete:WALLET-RETRY-TEST"


def test_rider_wallet_retry_does_not_allow_another_users_booking(
    app, authenticated_client, test_user
):
    from app.identity.models.user import User

    with app.app_context():
        other = User(
            username="wallet_retry_other_" + str(datetime.now(timezone.utc).timestamp()).replace(".", ""),
            email="wallet_retry_other_" + str(datetime.now(timezone.utc).timestamp()).replace(".", "") + "@test.example.com",
            is_active=True,
            is_verified=True,
        )
        other.set_password("TestPassword123!")
        db.session.add(other)
        db.session.commit()
        other_id = other.id
        booking_id = _booking(
            other_id, BookingStatus.COMPLETED, "wallet"
        )
        booking = db.session.get(Booking, booking_id)
        booking.booking_reference = "WALLET-RETRY-FOREIGN"
        db.session.commit()

    response = authenticated_client.post(
        "/api/transport/rides/WALLET-RETRY-FOREIGN/payment/settle-wallet",
        json={},
    )
    assert response.status_code == 404, response.get_data(as_text=True)


def test_payment_service_validates_wallet_for_the_booking_currency(monkeypatch):
    from types import SimpleNamespace
    from app.transport.services.payment_service import PaymentService
    from app.utils.enums import Currency

    seen = {}

    def wallet_status(user_id, currency_code=None):
        seen["currency"] = currency_code
        return currency_code == "USD"

    def methods_for_country(country_code, user_has_wallet=False):
        seen["has_wallet"] = user_has_wallet
        return [SimpleNamespace(code="wallet")] if user_has_wallet else []

    monkeypatch.setattr(
        "app.transport.services.payment_config.get_payment_config_service",
        lambda: SimpleNamespace(get_methods_for_country=methods_for_country),
    )
    monkeypatch.setattr(
        "app.transport.services.payment_config.get_user_country",
        lambda user_id: "UG",
    )
    monkeypatch.setattr(
        "app.transport.services.payment_config.get_user_wallet_status",
        wallet_status,
    )

    booking = SimpleNamespace(user_id=123, currency=Currency.USD)
    PaymentService._validate_payment_method(booking, "wallet")
    assert seen == {"currency": "USD", "has_wallet": True}
