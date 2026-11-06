from types import SimpleNamespace

import pytest


def _authenticated_mobile_user(monkeypatch, user):
    from app.auth import mobile_api

    monkeypatch.setattr(
        mobile_api,
        "require_mobile_context",
        lambda expected_client=None: ({"user": user}, None),
    )


def test_native_accommodation_property_search_uses_bearer_user(client, monkeypatch):
    from app.accommodation.services.native_booking_service import NativeAccommodationService

    user = SimpleNamespace(id=801, public_id="native-accom-user-801")
    _authenticated_mobile_user(monkeypatch, user)
    captured = {}

    def fake_list(**kwargs):
        captured.update(kwargs)
        return {"items": [{"public_id": "property-public-1", "title": "Kampala Stay"}], "limit": 10, "offset": 0, "has_more": False}

    monkeypatch.setattr(NativeAccommodationService, "list_properties", fake_list)
    response = client.get(
        "/api/mobile/v1/accommodation/properties?q=Kampala&city=Kampala&limit=10",
        headers={"Authorization": "Bearer native-test-token"},
    )

    assert response.status_code == 200
    assert response.get_json()["data"]["items"][0]["public_id"] == "property-public-1"
    assert captured["query"] == "Kampala"
    assert captured["city"] == "Kampala"
    assert captured["limit"] == 10


def test_native_accommodation_quote_is_bound_to_authenticated_user(client, monkeypatch):
    from app.accommodation.services.native_booking_service import NativeAccommodationService

    user = SimpleNamespace(id=802, public_id="native-accom-user-802")
    _authenticated_mobile_user(monkeypatch, user)
    captured = {}

    def fake_quote(owner, **kwargs):
        captured["owner"] = owner
        captured.update(kwargs)
        return {
            "quote_id": "quote-802",
            "quote_token": "signed-quote-802",
            "total": "250000.00",
            "currency": "UGX",
            "wallet_payment_available": True,
        }

    monkeypatch.setattr(NativeAccommodationService, "quote_booking", fake_quote)
    response = client.post(
        "/api/mobile/v1/accommodation/quotes",
        json={
            "property_public_id": "property-public-1",
            "check_in": "2026-12-10",
            "check_out": "2026-12-12",
            "num_guests": 2,
            "rooms_requested": 1,
            "room_type_id": 123,
        },
        headers={"Authorization": "Bearer native-test-token"},
    )

    assert response.status_code == 200
    assert response.get_json()["data"]["quote_token"] == "signed-quote-802"
    assert captured["owner"] is user
    assert captured["property_public_id"] == "property-public-1"
    assert captured["room_type_id"] == 123


def test_native_accommodation_booking_requires_pin_and_uses_server_quote(client, monkeypatch):
    from app.accommodation.services.native_booking_service import NativeAccommodationService

    user = SimpleNamespace(id=803, public_id="native-accom-user-803")
    _authenticated_mobile_user(monkeypatch, user)
    captured = {}

    def fake_confirm(owner, **kwargs):
        captured["owner"] = owner
        captured.update(kwargs)
        return {
            "booking_reference": "ACCOM-NATIVE-803",
            "status": "confirmed",
            "payment_status": "paid",
            "amount": "250000.00",
            "currency": "UGX",
        }

    monkeypatch.setattr(NativeAccommodationService, "confirm_wallet_booking", fake_confirm)

    missing_pin = client.post(
        "/api/mobile/v1/accommodation/bookings",
        json={"quote_token": "signed-quote-803"},
        headers={"Authorization": "Bearer native-test-token"},
    )
    assert missing_pin.status_code == 400

    response = client.post(
        "/api/mobile/v1/accommodation/bookings",
        json={"quote_token": "signed-quote-803", "pin": "1234", "special_requests": "Late arrival"},
        headers={"Authorization": "Bearer native-test-token"},
    )
    assert response.status_code == 201
    assert response.get_json()["data"]["booking_reference"] == "ACCOM-NATIVE-803"
    assert captured["owner"] is user
    assert captured["quote_token"] == "signed-quote-803"
    assert captured["pin"] == "1234"
    assert captured["special_requests"] == "Late arrival"


def test_native_accommodation_booking_history_is_scoped_to_bearer_user(client, monkeypatch):
    from app.accommodation.services.native_booking_service import NativeAccommodationService

    user = SimpleNamespace(id=804, public_id="native-accom-user-804")
    _authenticated_mobile_user(monkeypatch, user)
    captured = {}

    def fake_list(owner, **kwargs):
        captured["owner"] = owner
        captured.update(kwargs)
        return {"items": [{"booking_reference": "ACCOM-804"}], "limit": 5, "offset": 10}

    monkeypatch.setattr(NativeAccommodationService, "list_bookings", fake_list)
    response = client.get(
        "/api/mobile/v1/accommodation/bookings?limit=5&offset=10",
        headers={"Authorization": "Bearer native-test-token"},
    )

    assert response.status_code == 200
    assert response.get_json()["data"]["items"][0]["booking_reference"] == "ACCOM-804"
    assert captured["owner"] is user
    assert captured["limit"] == 5
    assert captured["offset"] == 10


def test_native_accommodation_cancel_requires_idempotency_key(client, monkeypatch):
    from app.accommodation.services.native_booking_service import NativeAccommodationService

    user = SimpleNamespace(id=805, public_id="native-accom-user-805")
    _authenticated_mobile_user(monkeypatch, user)
    called = {}

    def fake_cancel(owner, reference, **kwargs):
        called.update(owner=owner, reference=reference, **kwargs)
        return {
            "booking": {"booking_reference": reference, "status": "cancelled"},
            "cancellation_message": "Booking cancelled.",
            "refund": None,
        }

    monkeypatch.setattr(NativeAccommodationService, "cancel_booking", fake_cancel)
    missing_key = client.post(
        "/api/mobile/v1/accommodation/bookings/ACCOM-805/cancel",
        json={"reason": "Plans changed"},
        headers={"Authorization": "Bearer native-test-token"},
    )
    assert missing_key.status_code == 400

    response = client.post(
        "/api/mobile/v1/accommodation/bookings/ACCOM-805/cancel",
        json={"reason": "Plans changed"},
        headers={
            "Authorization": "Bearer native-test-token",
            "Idempotency-Key": "accom-cancel-805-0001",
        },
    )
    assert response.status_code == 200
    assert response.get_json()["data"]["booking"]["status"] == "cancelled"
    assert called["owner"] is user
    assert called["reference"] == "ACCOM-805"
    assert called["idempotency_key"] == "accom-cancel-805-0001"


def test_native_accommodation_errors_use_safe_api_contract(client, monkeypatch):
    from app.accommodation.services.native_booking_service import (
        NativeAccommodationError,
        NativeAccommodationService,
    )

    user = SimpleNamespace(id=806, public_id="native-accom-user-806")
    _authenticated_mobile_user(monkeypatch, user)

    def fail(*args, **kwargs):
        raise NativeAccommodationError("property_unavailable", "This property cannot be booked.", 404)

    monkeypatch.setattr(NativeAccommodationService, "get_property", fail)
    response = client.get(
        "/api/mobile/v1/accommodation/properties/not-a-public-property",
        headers={"Authorization": "Bearer native-test-token"},
    )
    assert response.status_code == 404
    assert response.get_json()["code"] == "property_unavailable"
    assert "id" not in response.get_json()
