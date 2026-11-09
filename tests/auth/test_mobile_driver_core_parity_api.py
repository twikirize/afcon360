from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace


def _authenticated_driver(monkeypatch, profile):
    from app.auth import mobile_api

    user = SimpleNamespace(id=451, public_id="driver-public-451")
    context = {
        "user": user,
        "record": {"client": "driver", "session_id": "driver-session-451"},
    }
    monkeypatch.setattr(
        mobile_api,
        "require_mobile_context",
        lambda expected_client=None: (context, None),
    )
    monkeypatch.setattr(
        mobile_api,
        "_current_driver",
        lambda: (profile, None, 200),
    )
    return user


def test_mobile_driver_profile_exposes_safe_performance_and_assigned_vehicle(client, monkeypatch):
    from app.transport.services import go_live_service

    vehicle = SimpleNamespace(
        is_deleted=False,
        make="Toyota",
        model="Corolla",
        year=2022,
        license_plate="UXX 123A",
        vehicle_class=SimpleNamespace(value="comfort"),
        passenger_capacity=4,
    )
    profile = SimpleNamespace(
        driver_code="DRV-451",
        verification_tier=SimpleNamespace(value="platform_verified"),
        compliance_status=SimpleNamespace(value="approved"),
        is_online=True,
        is_available=True,
        current_vehicle=vehicle,
        reliability_score=94,
        safety_score=92,
        acceptance_rate=Decimal("96.50"),
        cancellation_rate=Decimal("2.25"),
        total_trips=125,
        completed_trips=118,
        total_distance_km=Decimal("4812.75"),
        average_rating=Decimal("4.85"),
        total_ratings=73,
    )
    _authenticated_driver(monkeypatch, profile)
    monkeypatch.setattr(
        go_live_service,
        "can_go_live",
        lambda _profile: SimpleNamespace(
            to_dict=lambda: {
                "ready": True,
                "checks": [{"key": "approval", "label": "Approval", "ok": True, "required": True}],
            }
        ),
    )

    response = client.get(
        "/api/mobile/v1/driver/me",
        headers={"Authorization": "Bearer synthetic-driver-access-token"},
    )

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["driver_code"] == "DRV-451"
    assert data["go_live"]["ready"] is True
    assert data["performance"] == {
        "reliability_score": 94,
        "safety_score": 92,
        "acceptance_rate": "96.50",
        "cancellation_rate": "2.25",
        "total_trips": 125,
        "completed_trips": 118,
        "total_distance_km": "4812.75",
        "average_rating": "4.85",
        "total_ratings": 73,
    }
    assert data["assigned_vehicle"] == {
        "make": "Toyota",
        "model": "Corolla",
        "year": 2022,
        "license_plate": "UXX 123A",
        "vehicle_class": "comfort",
        "passenger_capacity": 4,
    }
    serialized = response.get_data(as_text=True).lower()
    for forbidden in (
        "license_number",
        "license_number_encrypted",
        "emergency_contact",
        "driver_metadata",
        '"user_id"',
        '"vehicle_id"',
    ):
        assert forbidden not in serialized


def test_mobile_driver_active_trip_returns_server_capabilities_and_safe_pickup_schedule(
    app, client, monkeypatch
):
    from app.auth import mobile_api
    from app.transport.models import Booking
    from app.transport.services.booking_service import BookingService
    from app.utils.enums import BookingStatus, PaymentStatus

    profile = SimpleNamespace(id=902, user_id=451)
    _authenticated_driver(monkeypatch, profile)
    booking = SimpleNamespace(
        booking_reference="AF360-TRIP-451",
        status=BookingStatus.PICKUP_ARRIVED,
        pickup_location={"latitude": 0.31, "longitude": 32.58, "address": "Kampala Road"},
        dropoff_location={"latitude": 0.05, "longitude": 32.46, "address": "Entebbe"},
        pickup_location_text="Kampala Road, Kampala",
        dropoff_location_text="Entebbe",
        pickup_time=datetime(2026, 11, 10, 8, 30, tzinfo=timezone.utc),
        passenger_count=2,
        payment_method="cash",
        payment_status=PaymentStatus.PENDING,
        final_price=Decimal("120.00"),
        total_amount=Decimal("120.00"),
        currency="UGX",
        booking_metadata={},
        is_deleted=False,
    )

    class Query:
        def filter(self, *criteria):
            assert criteria
            return self

        def order_by(self, *criteria):
            return self

        def first(self):
            return booking

    with app.app_context():
        monkeypatch.setattr(Booking, "query", Query())
    monkeypatch.setattr(
        BookingService,
        "_driver_trip_row",
        staticmethod(lambda _booking: {
            "booking_mode": "scheduled",
            "can_mark_no_show": True,
            "pickup_schedule": {
                "utc_datetime": "2026-11-10T08:30:00+00:00",
                "local_datetime": "2026-11-10T11:30:00",
                "timezone_name": "Africa/Kampala",
                "utc_offset": "+0300",
                "display_timezone_derived": False,
                "internal_remark": "must not be exposed",
            },
        }),
    )

    response = client.get(
        "/api/mobile/v1/driver/trips/active",
        headers={"Authorization": "Bearer synthetic-driver-access-token"},
    )

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["booking_reference"] == "AF360-TRIP-451"
    assert data["booking_mode"] == "scheduled"
    assert data["can_cancel"] is True
    assert data["can_mark_no_show"] is True
    assert data["pickup_schedule"] == {
        "utc_datetime": "2026-11-10T08:30:00+00:00",
        "local_datetime": "2026-11-10T11:30:00",
        "timezone_name": "Africa/Kampala",
        "utc_offset": "+0300",
        "display_timezone_derived": False,
    }
    serialized = response.get_data(as_text=True).lower()
    assert "internal_remark" not in serialized
    assert "must not be exposed" not in serialized
    assert "booking_metadata" not in serialized
    assert "passenger_name" not in serialized


def test_mobile_driver_active_trip_cancel_capability_is_false_after_trip_start(
    app, client, monkeypatch
):
    from app.transport.models import Booking
    from app.utils.enums import BookingStatus, PaymentStatus

    profile = SimpleNamespace(id=903, user_id=452)
    _authenticated_driver(monkeypatch, profile)
    booking = SimpleNamespace(
        booking_reference="AF360-TRIP-452",
        status=BookingStatus.IN_PROGRESS,
        pickup_location={"address": "Kampala"},
        dropoff_location={"address": "Entebbe"},
        pickup_location_text="Kampala",
        dropoff_location_text="Entebbe",
        pickup_time=None,
        passenger_count=1,
        payment_method="wallet",
        payment_status=PaymentStatus.PENDING,
        final_price=Decimal("50.00"),
        total_amount=Decimal("50.00"),
        currency="UGX",
        booking_metadata={},
        is_deleted=False,
    )

    class Query:
        def filter(self, *criteria):
            return self

        def order_by(self, *criteria):
            return self

        def first(self):
            return booking

    with app.app_context():
        monkeypatch.setattr(Booking, "query", Query())
    monkeypatch.setattr(
        "app.transport.services.booking_service.BookingService._driver_trip_row",
        staticmethod(lambda _booking: {
            "booking_mode": "instant",
            "can_mark_no_show": False,
            "pickup_schedule": None,
        }),
    )

    response = client.get(
        "/api/mobile/v1/driver/trips/active",
        headers={"Authorization": "Bearer synthetic-driver-access-token"},
    )

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["can_cancel"] is False
    assert data["can_mark_no_show"] is False


def test_mobile_driver_earnings_include_completed_driver_metadata_attribution(
    client, monkeypatch
):
    from app.auth import mobile_api
    from app.transport.models import Booking
    from app.utils.enums import BookingStatus, PaymentStatus

    profile = SimpleNamespace(id=904, user_id=453, commission_rate=Decimal("15.00"))
    _authenticated_driver(monkeypatch, profile)
    captured = {}

    class Query:
        def filter(self, *criteria):
            captured["criteria"] = criteria
            return self

        def group_by(self, *columns):
            return self

        def all(self):
            return [("UGX", Decimal("100.00"))]

    fake_db = SimpleNamespace(
        session=SimpleNamespace(query=lambda *columns: Query())
    )
    monkeypatch.setattr(mobile_api, "db", fake_db)

    response = client.get(
        "/api/mobile/v1/driver/earnings",
        headers={"Authorization": "Bearer synthetic-driver-access-token"},
    )

    assert response.status_code == 200
    data = response.get_json()["data"]["by_currency"]
    assert data == [{
        "currency": "UGX",
        "gross_captured": "100.00",
        "driver_earnings": "85.00",
        "platform_commission_rate": "15.0",
    }]
    criteria_text = " ".join(str(item) for item in captured["criteria"])
    criteria_params = {}
    for expression in captured["criteria"]:
        criteria_params.update(expression.compile().params)
    assert "assigned_driver_id" in criteria_text
    assert "booking_metadata ?" in criteria_text
    assert "completed_by_driver_profile_id" in criteria_params.values()
    assert str(profile.id) in criteria_params.values()


def test_new_driver_core_parity_routes_still_require_driver_bearer(client):
    responses = [
        client.get("/api/mobile/v1/driver/me"),
        client.get("/api/mobile/v1/driver/trips/active"),
        client.get("/api/mobile/v1/driver/earnings"),
    ]
    for response in responses:
        assert response.status_code == 401
        assert response.get_json()["code"] == "mobile_auth_required"
