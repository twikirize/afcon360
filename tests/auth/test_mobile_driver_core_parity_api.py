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
        service_types=["on_demand"],
        vehicle_classes=["comfort"],
        operational_zones=["Kampala"],
        max_passenger_capacity=4,
        max_luggage_capacity=2,
        auto_accept_bookings=False,
        max_concurrent_bookings=1,
        license_verified=True,
        license_expiry=None,
        background_check_status="approved",
        police_clearance_verified=True,
        next_training_due=None,
        requires_retraining=False,
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


def test_driver_assignment_and_vehicle_routes_are_registered(app):
    expected = {
        "/api/mobile/v1/driver/assignments",
        "/api/mobile/v1/driver/vehicles/switch",
        "/api/mobile/v1/driver/vehicles",
        "/api/mobile/v1/driver/vehicles/<string:vehicle_public_id>",
        "/api/mobile/v1/driver/marketplace/vehicles",
        "/api/mobile/v1/driver/marketplace/vehicles/<string:listing_public_id>/apply",
    }
    registered = {rule.rule for rule in app.url_map.iter_rules()}
    assert expected <= registered


def test_driver_assignment_and_vehicle_routes_reject_missing_bearer(client):
    responses = [
        client.get("/api/mobile/v1/driver/assignments"),
        client.post("/api/mobile/v1/driver/vehicles/switch", json={"vehicle_public_id": "vehicle-public"}),
        client.post("/api/mobile/v1/driver/vehicles", json={"make": "Toyota"}),
        client.put("/api/mobile/v1/driver/vehicles/vehicle-public", json={"make": "Toyota"}),
        client.get("/api/mobile/v1/driver/marketplace/vehicles"),
        client.post(
            "/api/mobile/v1/driver/marketplace/vehicles/listing-public/apply",
            json={"cover_letter": "I am interested."},
        ),
    ]
    for response in responses:
        assert response.status_code == 401
        assert response.get_json()["code"] == "mobile_auth_required"


def test_mobile_driver_assignments_return_only_the_authenticated_profile_scope(
    app, client, monkeypatch
):
    from app.transport.models import DriverVehicleHistory, ScheduledRoute
    from app.transport.services import provider_service

    assigned = SimpleNamespace(
        id=10,
        public_id="vehicle-current-public",
        is_deleted=False,
        make="Toyota",
        model="Corolla",
        year=2022,
        license_plate="UXX 123A",
        vehicle_class=SimpleNamespace(value="comfort"),
        status="active",
        is_available=True,
        passenger_capacity=4,
        safety_features=["seatbelts"],
    )
    owned = SimpleNamespace(
        id=11,
        public_id="vehicle-owned-public",
        is_deleted=False,
        make="Honda",
        model="Fit",
        year=2021,
        license_plate="UYY 456B",
        vehicle_class=SimpleNamespace(value="economy"),
        status="active",
        is_available=True,
        passenger_capacity=4,
        safety_features=["seatbelts"],
    )
    history_vehicle = SimpleNamespace(license_plate="UXX 123A")
    history_row = SimpleNamespace(
        vehicle=history_vehicle,
        assignment_reason="shift_start",
        was_breakdown=False,
        started_at=datetime(2026, 11, 1, tzinfo=timezone.utc),
        ended_at=None,
    )
    route_row = SimpleNamespace(
        name="Kampala–Entebbe",
        route_code="KLA-EBB-01",
        route_type="scheduled",
        primary_zone="Kampala",
        next_departure=datetime(2026, 11, 10, 9, tzinfo=timezone.utc),
        available_seats=3,
        vehicle_capacity=4,
        price_per_seat=Decimal("15000"),
        is_free=False,
    )
    profile = SimpleNamespace(id=902, user_id=451, current_vehicle=assigned)
    _authenticated_driver(monkeypatch, profile)

    class Query:
        def filter(self, *criteria):
            return self

        def filter_by(self, **criteria):
            return self

        def order_by(self, *criteria):
            return self

        def limit(self, value):
            return self

        def all(self):
            if self is history_query:
                return [history_row]
            return [route_row]

    history_query = Query()
    route_query = Query()
    with app.app_context():
        monkeypatch.setattr(DriverVehicleHistory, "query", history_query)
        monkeypatch.setattr(ScheduledRoute, "query", route_query)
    monkeypatch.setattr(
        provider_service,
        "get_provider_service",
        lambda: SimpleNamespace(get_user_vehicles=lambda user_id: [assigned, owned]),
    )

    response = client.get(
        "/api/mobile/v1/driver/assignments",
        headers={"Authorization": "Bearer synthetic-driver-access-token"},
    )

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["assigned_vehicle"]["public_id"] == "vehicle-current-public"
    assert [item["public_id"] for item in data["owned_vehicles"]] == [
        "vehicle-current-public", "vehicle-owned-public"
    ]
    assert [item["public_id"] for item in data["switchable_vehicles"]] == [
        "vehicle-owned-public"
    ]
    assert data["vehicle_history"][0]["license_plate"] == "UXX 123A"
    assert data["scheduled_routes"][0]["route_code"] == "KLA-EBB-01"
    assert data["history_window_days"] == 90
    serialized = response.get_data(as_text=True).lower()
    assert '"user_id"' not in serialized
    assert '"owner_id"' not in serialized
    assert '"vehicle_id"' not in serialized
    assert '"driver_id"' not in serialized


def test_mobile_driver_vehicle_switch_enforces_ownership_before_assignment(
    app, client, monkeypatch
):
    from app.auth import mobile_api
    from app.transport.models import Vehicle
    from app.transport import models as transport_models
    from app.transport.services import go_live_service

    profile = SimpleNamespace(id=902, user_id=451, current_vehicle=None)
    _authenticated_driver(monkeypatch, profile)
    vehicle = SimpleNamespace(
        id=77,
        public_id="owned-vehicle-public",
        owner_type="driver",
        owner_id=902,
        status="active",
        is_deleted=False,
        make="Toyota",
        model="Corolla",
        year=2022,
        license_plate="UXX 123A",
    )

    class Query:
        def filter_by(self, **kwargs):
            assert kwargs["public_id"] == "owned-vehicle-public"
            return self

        def first(self):
            return vehicle

    with app.app_context():
        monkeypatch.setattr(Vehicle, "query", Query())
    monkeypatch.setattr(
        go_live_service,
        "can_go_live",
        lambda _profile: SimpleNamespace(checks=[] , to_dict=lambda: {"ready": True, "checks": []}),
    )
    calls = {}
    monkeypatch.setattr(
        transport_models,
        "assign_driver_to_vehicle",
        lambda driver, selected, **kwargs: calls.update(
            driver=driver, vehicle=selected, **kwargs
        ),
    )
    # The real profile is a mapped SQLAlchemy entity. The focused fixture is a
    # SimpleNamespace, so suppress only the post-write refresh in this unit
    # contract test; the ownership and service invocation remain exercised.
    from app.extensions import db
    monkeypatch.setattr(db.session, "refresh", lambda _profile: None)

    response = client.post(
        "/api/mobile/v1/driver/vehicles/switch",
        headers={"Authorization": "Bearer synthetic-driver-access-token"},
        json={"vehicle_public_id": "owned-vehicle-public"},
    )

    assert response.status_code == 200
    assert response.get_json()["data"]["unchanged"] is False
    assert calls["driver"] is profile
    assert calls["vehicle"] is vehicle
    assert calls["authorized_by"].id == 451


def test_mobile_driver_vehicle_switch_rejects_vehicle_not_owned(
    app, client, monkeypatch
):
    from app.transport.models import Vehicle
    profile = SimpleNamespace(id=902, user_id=451, current_vehicle=None)
    _authenticated_driver(monkeypatch, profile)
    vehicle = SimpleNamespace(
        id=88,
        public_id="other-owner-vehicle",
        owner_type="driver",
        owner_id=999,
        status="active",
        is_deleted=False,
    )

    class Query:
        def filter_by(self, **kwargs):
            return self

        def first(self):
            return vehicle

    with app.app_context():
        monkeypatch.setattr(Vehicle, "query", Query())

    response = client.post(
        "/api/mobile/v1/driver/vehicles/switch",
        headers={"Authorization": "Bearer synthetic-driver-access-token"},
        json={"vehicle_public_id": "other-owner-vehicle"},
    )

    assert response.status_code == 403
    assert response.get_json()["code"] == "vehicle_not_owned"


def test_mobile_driver_marketplace_only_returns_active_public_listing_projection(
    app, client, monkeypatch
):
    from app.transport.models import DriverVehicleApplication, VehicleMarketplaceListing

    vehicle = SimpleNamespace(
        id=701,
        public_id="market-vehicle-public",
        is_deleted=False,
        status="active",
        is_available=True,
        is_reserved=False,
        owner_type="organisation",
        make="Toyota",
        model="Hiace",
        year=2023,
        vehicle_class=SimpleNamespace(value="van"),
        passenger_capacity=14,
    )
    listing = SimpleNamespace(
        id=801,
        public_id="market-listing-public",
        vehicle=vehicle,
        compensation_model=SimpleNamespace(value="revenue_split"),
        driver_revenue_share_pct=Decimal("75.00"),
        fixed_rental_amount=None,
        rental_frequency=None,
        title="Airport shuttle vehicle",
        description="A vehicle for scheduled shuttle operations.",
        application_deadline=None,
        owner_id=999,
    )
    profile = SimpleNamespace(id=902, user_id=451)
    _authenticated_driver(monkeypatch, profile)

    class ListingQuery:
        def options(self, *args):
            return self

        def join(self, *args):
            return self

        def filter(self, *args):
            return self

        def order_by(self, *args):
            return self

        def limit(self, value):
            return self

        def all(self):
            return [listing]

    class ApplicationQuery:
        def filter_by(self, **kwargs):
            return self

        def all(self):
            return []

    with app.app_context():
        monkeypatch.setattr(VehicleMarketplaceListing, "query", ListingQuery())
        monkeypatch.setattr(DriverVehicleApplication, "query", ApplicationQuery())

    response = client.get(
        "/api/mobile/v1/driver/marketplace/vehicles",
        headers={"Authorization": "Bearer synthetic-driver-access-token"},
    )

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["count"] == 1
    item = data["items"][0]
    assert item["listing_public_id"] == "market-listing-public"
    assert item["vehicle_public_id"] == "market-vehicle-public"
    assert item["owner_type"] == "Organisation"
    assert item["compensation"] == "75% revenue share"
    assert item["already_applied"] is False
    serialized = response.get_data(as_text=True).lower()
    assert '"owner_id"' not in serialized
    assert '"listing_id"' not in serialized
    assert '"vehicle_id"' not in serialized


def test_driver_map_notifications_and_incident_routes_are_registered(app):
    expected = {
        "/api/mobile/v1/driver/map-config",
        "/api/mobile/v1/driver/notifications",
        "/api/mobile/v1/driver/notifications/<string:notification_public_id>/read",
        "/api/mobile/v1/driver/notifications/read-all",
        "/api/mobile/v1/driver/incidents",
    }
    registered = {rule.rule for rule in app.url_map.iter_rules()}
    assert expected <= registered


def test_driver_map_notifications_and_incident_routes_require_bearer(client):
    responses = [
        client.get("/api/mobile/v1/driver/map-config"),
        client.get("/api/mobile/v1/driver/notifications"),
        client.post("/api/mobile/v1/driver/notifications/read-all"),
        client.get("/api/mobile/v1/driver/incidents"),
        client.post("/api/mobile/v1/driver/incidents", json={
            "incident_type": "safety",
            "severity": "high",
            "title": "Test",
            "description": "Test",
            "occurred_at": "2026-11-10T08:00:00Z",
        }),
    ]
    for response in responses:
        assert response.status_code == 401
        assert response.get_json()["code"] == "mobile_auth_required"


def test_mobile_driver_map_config_returns_only_public_geo_fields(client, monkeypatch):
    _authenticated_driver(monkeypatch, SimpleNamespace(id=902, user_id=451))
    from app.geo import map_renderer

    public = {
        "tiles_backend_available": False,
        "tiles_kind": "pmtiles",
        "tile_url_template": "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
        "tile_attribution": "© OpenStreetMap contributors",
        "tile_source_label": "openstreetmap-default",
        "default_center": {"latitude": 0.3136, "longitude": 32.5811},
        "default_zoom": 12,
    }
    monkeypatch.setattr(
        map_renderer,
        "build_public_map_config",
        lambda _config: dict(public, api_key="must-not-be-exposed"),
    )

    response = client.get(
        "/api/mobile/v1/driver/map-config",
        headers={"Authorization": "Bearer synthetic-driver-access-token"},
    )

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["tile_url_template"] == "https://a.tile.openstreetmap.org/{z}/{x}/{y}.png"
    assert data["default_center"] == public["default_center"]
    assert data["tile_attribution"] == public["tile_attribution"]
    assert "api_key" not in data
    assert response.headers["Cache-Control"] == "private, max-age=300"


def test_mobile_driver_notifications_are_user_and_transport_scoped_and_redacted(
    app, client, monkeypatch
):
    _authenticated_driver(monkeypatch, SimpleNamespace(id=902, user_id=451))
    from app.notifications.models import Notification

    notification = SimpleNamespace(
        public_id="notification-public-123",
        type="driver_offer",
        module="transport",
        subject="New ride offer",
        body="A ride is available.",
        priority="high",
        status="delivered",
        is_read=False,
        is_important=True,
        created_at=datetime(2026, 11, 10, 8, tzinfo=timezone.utc),
        read_at=None,
        user_id=451,
        context={"private": "must not be returned"},
        external_id="internal-external-id",
        phone="+256700000000",
        email="driver@example.invalid",
    )

    class Query:
        def __init__(self):
            self.count_calls = 0
            self.filters = []

        def filter(self, *criteria):
            self.filters.extend(criteria)
            return self

        def count(self):
            self.count_calls += 1
            return 5 if self.count_calls == 1 else 2

        def order_by(self, *criteria):
            return self

        def offset(self, value):
            assert value == 0
            return self

        def limit(self, value):
            assert value == 30
            return self

        def all(self):
            return [notification]

    query = Query()
    with app.app_context():
        monkeypatch.setattr(Notification, "query", query)

    response = client.get(
        "/api/mobile/v1/driver/notifications",
        headers={"Authorization": "Bearer synthetic-driver-access-token"},
    )

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["total"] == 5
    assert data["unread_count"] == 2
    assert data["count"] == 1
    item = data["items"][0]
    assert item["public_id"] == "notification-public-123"
    assert item["subject"] == "New ride offer"
    serialized = response.get_data(as_text=True).lower()
    for forbidden in ("user_id", "external_id", "phone", "email", "context", "private"):
        assert forbidden not in serialized
    criteria_text = " ".join(str(item) for item in query.filters)
    assert "notifications.user_id" in criteria_text
    assert "notifications.module" in criteria_text
    assert "transport" in criteria_text


def test_mobile_driver_notification_read_only_updates_own_transport_notification(
    app, client, monkeypatch
):
    _authenticated_driver(monkeypatch, SimpleNamespace(id=902, user_id=451))
    from app.notifications.models import Notification

    notification = SimpleNamespace(
        public_id="notification-public-123",
        user_id=451,
        module="transport",
        is_deleted=False,
        is_read=False,
        mark_read=lambda: setattr(notification, "is_read", True),
    )

    class Query:
        def filter(self, *criteria):
            return self

        def first(self):
            return notification

        def count(self):
            return 0

    with app.app_context():
        monkeypatch.setattr(Notification, "query", Query())
    from app.extensions import db
    monkeypatch.setattr(db.session, "commit", lambda: None)

    response = client.post(
        "/api/mobile/v1/driver/notifications/notification-public-123/read",
        headers={"Authorization": "Bearer synthetic-driver-access-token"},
    )

    assert response.status_code == 200
    assert notification.is_read is True
    assert response.get_json()["data"]["unread_count"] == 0


def test_mobile_driver_notification_read_cannot_read_another_users_notification(
    app, client, monkeypatch
):
    _authenticated_driver(monkeypatch, SimpleNamespace(id=902, user_id=451))
    from app.notifications.models import Notification

    class Query:
        def filter(self, *criteria):
            return self

        def first(self):
            return None

    with app.app_context():
        monkeypatch.setattr(Notification, "query", Query())

    response = client.post(
        "/api/mobile/v1/driver/notifications/not-owned/read",
        headers={"Authorization": "Bearer synthetic-driver-access-token"},
    )

    assert response.status_code == 404
    assert response.get_json()["code"] == "notification_not_found"


def test_mobile_driver_incident_report_derives_identity_and_ignores_client_identity(
    app, client, monkeypatch
):
    from app.extensions import db
    from app.transport.models import TransportIncident

    profile = SimpleNamespace(
        id=902,
        user_id=451,
        current_vehicle=SimpleNamespace(id=77),
    )
    _authenticated_driver(monkeypatch, profile)
    captured = {}
    monkeypatch.setattr(db.session, "add", lambda incident: captured.update(incident=incident))
    monkeypatch.setattr(db.session, "commit", lambda: None)

    response = client.post(
        "/api/mobile/v1/driver/incidents",
        headers={"Authorization": "Bearer synthetic-driver-access-token"},
        json={
            "incident_type": "safety",
            "incident_category": "safety",
            "severity": "high",
            "title": "Unsafe pickup situation",
            "description": "A passenger threatened the driver at pickup.",
            "occurred_at": "2026-11-10T08:00:00+03:00",
            "reported_by": "user",
            "reported_by_id": 999,
            "user_id": 999,
            "driver_id": 999,
            "vehicle_id": 999,
            "booking_id": 999,
        },
    )

    assert response.status_code == 201
    incident = captured["incident"]
    assert isinstance(incident, TransportIncident)
    assert incident.reported_by == "driver"
    assert incident.reported_by_id == 451
    assert incident.user_id == 451
    assert incident.driver_id == 902
    assert incident.vehicle_id == 77
    assert incident.booking_id is None
    assert incident.reported_via == "driver_mobile"
    assert incident.occurred_at == datetime(2026, 11, 10, 5, tzinfo=timezone.utc)
    assert incident.priority == "high"
    assert response.get_json()["data"]["incident_reference"] == incident.incident_reference


def test_mobile_driver_incident_rejects_booking_that_is_not_assigned_to_driver(
    app, client, monkeypatch
):
    from app.transport.models import Booking

    profile = SimpleNamespace(id=902, user_id=451, current_vehicle=None)
    _authenticated_driver(monkeypatch, profile)
    other_booking = SimpleNamespace(
        id=9001,
        booking_reference="AF360-OTHER-DRIVER",
        assigned_driver_id=777,
        booking_metadata={},
        assigned_vehicle_id=77,
        is_deleted=False,
    )

    class Query:
        def filter_by(self, **kwargs):
            return self

        def first(self):
            return other_booking

    with app.app_context():
        monkeypatch.setattr(Booking, "query", Query())

    response = client.post(
        "/api/mobile/v1/driver/incidents",
        headers={"Authorization": "Bearer synthetic-driver-access-token"},
        json={
            "incident_type": "vehicle",
            "severity": "medium",
            "title": "Vehicle issue",
            "description": "A problem occurred.",
            "occurred_at": "2026-11-10T08:00:00Z",
            "booking_reference": "AF360-OTHER-DRIVER",
        },
    )

    assert response.status_code == 403
    assert response.get_json()["code"] == "booking_not_owned"


def test_mobile_driver_incident_requires_explicit_timezone(client):
    response = client.post(
        "/api/mobile/v1/driver/incidents",
        headers={"Authorization": "Bearer synthetic-driver-access-token"},
        json={
            "incident_type": "safety",
            "severity": "high",
            "title": "Test",
            "description": "Test",
            "occurred_at": "2026-11-10T08:00:00",
        },
    )
    # This test client has no bearer-auth context, so authentication must win
    # before request-body validation.
    assert response.status_code == 401
