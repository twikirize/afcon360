from types import SimpleNamespace


def _authenticated_mobile_user(monkeypatch, user):
    from app.auth import mobile_api

    monkeypatch.setattr(
        mobile_api,
        "require_mobile_context",
        lambda expected_client=None: ({"user": user}, None),
    )


def _booking_payload(*, service_type="airport_departure", booking_mode="scheduled"):
    return {
        "idempotency_key": "native-booking-parity-0001",
        "pickup": {
            "latitude": 0.3136,
            "longitude": 32.5811,
            "address": "Kampala City",
        },
        "dropoff": {
            "latitude": 0.0464,
            "longitude": 32.4435,
            "address": "Entebbe Airport",
        },
        "pickup_source": "search",
        "dropoff_source": "search",
        "pickup_geocode": {
            "label": "Kampala City",
            "latitude": 0.3136,
            "longitude": 32.5811,
            "provider": "nominatim",
            "osm_type": "relation",
            "osm_id": 123,
        },
        "dropoff_geocode": {
            "label": "Entebbe Airport",
            "latitude": 0.0464,
            "longitude": 32.4435,
            "provider": "nominatim",
            "osm_type": "relation",
            "osm_id": 456,
        },
        "service_type": service_type,
        "vehicle_class": "comfort",
        "passenger_count": 1,
        "booking_mode": booking_mode,
        "pickup_time": "2026-12-20T10:30",
        "payment_method": "cash",
        "currency": "USD",
        "fare_quote_token": "signed-fare-quote",
        "confirmed_fare_amount": "45.00",
    }


def _prepare_booking_gate(monkeypatch, user):
    from app.profile import models as profile_models
    from app.auth import kyc_compliance
    from app.transport.services import payment_methods

    _authenticated_mobile_user(monkeypatch, user)
    monkeypatch.setattr(
        profile_models,
        "get_profile_by_user",
        lambda authenticated_user: SimpleNamespace(profile_completed=True)
        if authenticated_user is user else None,
    )
    monkeypatch.setattr(
        kyc_compliance,
        "calculate_kyc_tier",
        lambda user_id: {"tier": 2, "missing_requirements": []},
    )
    monkeypatch.setattr(
        payment_methods,
        "get_available_transport_payment_methods",
        lambda user_id: [{
            "code": "cash",
            "label": "Cash",
            "enabled": True,
            "status": "ready",
        }],
    )


def test_native_scheduled_airport_booking_uses_booking_service_without_early_dispatch(
    client, monkeypatch
):
    from app.transport.services import booking_service

    user = SimpleNamespace(id=9801)
    _prepare_booking_gate(monkeypatch, user)
    captured = {}
    service_calls = {"transition": 0}

    class FakeBookingService:
        def create_booking(self, owner_id, payload):
            captured["owner_id"] = owner_id
            captured["payload"] = payload
            return {
                "success": True,
                "data": {
                    "booking_id": 771,
                    "booking_reference": "AF360-SCHEDULED-9801",
                    "booking_mode": "scheduled",
                    "pickup_time": "2026-12-20T07:30:00+00:00",
                    "status": "pending_payment",
                },
            }

        def transition_status(self, *args, **kwargs):
            service_calls["transition"] += 1
            raise AssertionError("Scheduled rides must not be confirmed/dispatched immediately")

    monkeypatch.setattr(booking_service, "get_booking_service", lambda: FakeBookingService())

    response = client.post(
        "/api/mobile/v1/transport/bookings",
        json=_booking_payload(service_type="airport_departure", booking_mode="scheduled"),
        headers={"Authorization": "Bearer native-test-token"},
    )

    assert response.status_code == 201
    body = response.get_json()
    assert body["success"] is True
    assert body["booking_kind"] == "booking"
    assert body["booking_reference"] == "AF360-SCHEDULED-9801"
    assert body["data"]["booking_mode"] == "scheduled"
    assert "booking_id" not in body["data"]
    assert body["dispatch_pending"] is False
    assert captured["owner_id"] == user.id
    assert captured["payload"]["service_type"] == "airport_departure"
    assert captured["payload"]["booking_mode"] == "scheduled"
    assert captured["payload"]["pickup_time"] == "2026-12-20T10:30"
    assert captured["payload"]["pickup_latitude"] == 0.3136
    assert captured["payload"]["dropoff_longitude"] == 32.4435
    assert captured["payload"]["pickup_address"] == "Kampala City"
    assert captured["payload"]["dropoff_address"] == "Entebbe Airport"
    assert captured["payload"]["pickup_geocode"]["provider"] == "nominatim"
    assert service_calls["transition"] == 0


def test_native_instant_airport_booking_uses_website_cash_dispatch_path(
    client, monkeypatch
):
    from app.transport.models import BookingStatus
    from app.transport.services import booking_service
    from app.transport.services.matching_service import MatchingService

    user = SimpleNamespace(id=9802)
    _prepare_booking_gate(monkeypatch, user)
    service_calls = {}
    matching_calls = []

    class FakeBookingService:
        def create_booking(self, owner_id, payload):
            return {
                "success": True,
                "data": {
                    "booking_id": 772,
                    "booking_reference": "AF360-AIRPORT-9802",
                    "booking_mode": "instant",
                    "pickup_time": "2026-11-12T10:00:00+00:00",
                    "status": "pending_payment",
                },
            }

        def transition_status(self, booking_id, status, **kwargs):
            service_calls.update(
                booking_id=booking_id,
                status=status,
                reason=kwargs.get("reason"),
                initiated_by=kwargs.get("initiated_by"),
                actor=kwargs.get("actor"),
            )

    monkeypatch.setattr(booking_service, "get_booking_service", lambda: FakeBookingService())
    monkeypatch.setattr(
        MatchingService,
        "discover_and_offer",
        lambda booking_id: matching_calls.append(booking_id) or {"offers_created": 1},
    )

    response = client.post(
        "/api/mobile/v1/transport/bookings",
        json=_booking_payload(service_type="airport_departure", booking_mode="instant"),
        headers={"Authorization": "Bearer native-test-token"},
    )

    assert response.status_code == 201
    assert response.get_json()["booking_reference"] == "AF360-AIRPORT-9802"
    assert service_calls["booking_id"] == 772
    assert service_calls["status"] == BookingStatus.CONFIRMED
    assert service_calls["reason"] == "cash_confirm"
    assert service_calls["initiated_by"] == "rider"
    assert service_calls["actor"] is user
    assert matching_calls == [772]


def test_native_instant_on_demand_booking_endpoint_rejects_wrong_lifecycle(client, monkeypatch):
    from app.transport.services import booking_service

    user = SimpleNamespace(id=9803)
    _prepare_booking_gate(monkeypatch, user)
    monkeypatch.setattr(
        booking_service,
        "get_booking_service",
        lambda: (_ for _ in ()).throw(AssertionError("Wrong service for instant Quick Ride")),
    )

    response = client.post(
        "/api/mobile/v1/transport/bookings",
        json=_booking_payload(service_type="on_demand", booking_mode="instant"),
        headers={"Authorization": "Bearer native-test-token"},
    )

    assert response.status_code == 409
    assert response.get_json()["code"] == "use_ride_request"


def test_native_scheduled_booking_requires_pickup_time(client, monkeypatch):
    user = SimpleNamespace(id=9804)
    _prepare_booking_gate(monkeypatch, user)
    payload = _booking_payload(service_type="on_demand", booking_mode="scheduled")
    payload["pickup_time"] = None

    response = client.post(
        "/api/mobile/v1/transport/bookings",
        json=payload,
        headers={"Authorization": "Bearer native-test-token"},
    )

    assert response.status_code == 400
    assert response.get_json()["code"] == "scheduled_pickup_time_required"

def test_native_booking_tracking_uses_authenticated_bearer_user(client, monkeypatch):
    from flask import jsonify
    from flask_login import current_user
    from app.transport.api import booking_routes

    user = SimpleNamespace(id=9805)
    _authenticated_mobile_user(monkeypatch, user)
    captured = {}

    class FakeBookingDetailResource:
        def get(self, booking_reference):
            captured["reference"] = booking_reference
            captured["user"] = current_user._get_current_object()
            return jsonify({
                "success": True,
                "data": {
                    "booking": {
                        "booking_reference": booking_reference,
                        "status": "pending_payment",
                    },
                    "driver_display": None,
                },
            }), 200

    monkeypatch.setattr(
        booking_routes,
        "BookingDetailResource",
        FakeBookingDetailResource,
    )

    response = client.get(
        "/api/mobile/v1/transport/bookings/AF360-SCHEDULED-9805",
        headers={"Authorization": "Bearer native-test-token"},
    )

    assert response.status_code == 200
    assert response.get_json()["data"]["booking"]["booking_reference"] == "AF360-SCHEDULED-9805"
    assert captured["reference"] == "AF360-SCHEDULED-9805"
    assert captured["user"] is user

def test_native_activity_combines_request_first_and_booking_first_trips(client, monkeypatch):
    from datetime import datetime, timezone
    from app.transport.models import Booking, RideRequest, SearchCycle
    from app.transport.services import ride_request_service

    user = SimpleNamespace(id=9806)
    _authenticated_mobile_user(monkeypatch, user)
    request_row = SimpleNamespace(
        id=88,
        public_id="RIDE-REQUEST-9806",
        status="searching",
        created_at=datetime(2026, 11, 12, 9, 0, tzinfo=timezone.utc),
    )
    cycle = SimpleNamespace(
        cycle_number=1,
        status="searching",
        terminal_reason=None,
    )
    booking_row = SimpleNamespace(
        user_id=user.id,
        is_deleted=False,
        ride_request_id=None,
        booking_reference="AF360-SCHEDULED-9806",
        status="pending_payment",
        final_price=125000,
        total_amount=125000,
        base_price=125000,
        currency=SimpleNamespace(value="UGX"),
        booking_metadata={"booking_mode": "scheduled"},
        pickup_mode="scheduled",
        service_type=SimpleNamespace(value="airport_departure"),
        assigned_driver_id=None,
        created_at=datetime(2026, 11, 12, 8, 0, tzinfo=timezone.utc),
    )

    class FakeQuery:
        def __init__(self, rows):
            self.rows = rows
            self.first_calls = 0
            self.limit_value = None

        def filter_by(self, **kwargs):
            return self

        def filter(self, *criteria):
            assert criteria
            return self

        def order_by(self, *criteria):
            return self

        def limit(self, value):
            self.limit_value = value
            return self

        def all(self):
            return self.rows

        def first(self):
            self.first_calls += 1
            return self.rows[0] if self.rows else None

    monkeypatch.setattr(RideRequest, "query", FakeQuery([request_row]))
    monkeypatch.setattr(SearchCycle, "query", FakeQuery([cycle]))
    monkeypatch.setattr(Booking, "query", FakeQuery([booking_row]))
    monkeypatch.setattr(
        ride_request_service,
        "serialize_request",
        lambda _request, _cycle: {
            "request_id": "RIDE-REQUEST-9806",
            "status": "searching",
            "created_at": request_row.created_at.isoformat(),
            "fare_estimate": {"amount": 42.5, "currency": "USD"},
        },
    )

    response = client.get(
        "/api/mobile/v1/activity",
        headers={"Authorization": "Bearer native-test-token"},
    )

    assert response.status_code == 200
    items = response.get_json()["data"]["items"]
    assert [item["kind"] for item in items] == ["request", "booking"]
    assert items[0]["booking_reference"] == "RIDE-REQUEST-9806"
    assert items[1]["request_id"] == "AF360-SCHEDULED-9806"
    assert items[1]["booking_reference"] == "AF360-SCHEDULED-9806"
    assert items[1]["status"] == "pending_payment"
    assert items[1]["booking_mode"] == "scheduled"
    assert items[1]["service_type"] == "airport_departure"
    assert items[1]["fare_estimate"] == {"amount": 125000.0, "currency": "UGX"}
    assert "booking_id" not in items[1]
