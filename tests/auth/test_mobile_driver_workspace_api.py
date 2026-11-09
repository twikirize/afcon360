from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace


class FakeQuery:
    def __init__(self, rows=None, count=0):
        self.rows = list(rows or [])
        self.count_value = count
        self.calls = []

    def options(self, *args, **kwargs):
        self.calls.append(("options", args, kwargs))
        return self

    def filter(self, *args, **kwargs):
        self.calls.append(("filter", args, kwargs))
        return self

    def filter_by(self, **kwargs):
        self.calls.append(("filter_by", kwargs))
        return self

    def order_by(self, *args, **kwargs):
        self.calls.append(("order_by", args, kwargs))
        return self

    def limit(self, value):
        self.calls.append(("limit", value))
        return self

    def all(self):
        return list(self.rows)

    def first(self):
        return self.rows[0] if self.rows else None

    def count(self):
        return self.count_value


def _driver_mobile_context(monkeypatch, **overrides):
    from app.auth import mobile_api

    user = SimpleNamespace(id=451, public_id="driver-public-451")
    profile_values = {
        "id": 902,
        "user_id": user.id,
        "driver_code": "DRV-TEST-01",
        "verification_tier": "basic_verified",
        "compliance_status": "approved",
        "is_online": True,
        "is_available": True,
        "license_verified": True,
        "license_expiry": datetime(2027, 1, 1, tzinfo=timezone.utc),
        "background_check_status": "clear",
        "police_clearance_verified": True,
        "police_clearance_date": datetime(2026, 1, 1, tzinfo=timezone.utc),
        "next_training_due": datetime(2027, 1, 1, tzinfo=timezone.utc),
        "requires_retraining": False,
        "reliability_score": 97,
        "safety_score": 91,
        "acceptance_rate": Decimal("96.50"),
        "cancellation_rate": Decimal("2.50"),
        "total_trips": 120,
        "completed_trips": 112,
        "total_duration_minutes": 3450,
        "total_distance_km": Decimal("4521.70"),
        "average_rating": Decimal("4.85"),
        "total_ratings": 105,
        "service_types": ["on_demand", "scheduled"],
        "vehicle_classes": ["comfort", "premium"],
        "operational_zones": ["Kampala Central", "Wakiso"],
        "max_passenger_capacity": 4,
        "max_luggage_capacity": 3,
        "auto_accept_bookings": False,
        "max_concurrent_bookings": 1,
        "emergency_contact_name": "Emergency Contact",
        "emergency_contact_phone": "+256700000000",
        "emergency_contact_relationship": "Sibling",
        "current_vehicle": None,
        "is_deleted": False,
    }
    profile_values.update(overrides)
    profile = SimpleNamespace(**profile_values)
    calls = {}

    def require_context(expected_client=None):
        calls["expected_client"] = expected_client
        return {"user": user, "record": {"client": "driver"}}, None

    monkeypatch.setattr(mobile_api, "require_mobile_context", require_context)
    monkeypatch.setattr(mobile_api, "_current_driver", lambda: (profile, None, 200))
    return user, profile, calls


def _driver_headers():
    return {"Authorization": "Bearer synthetic-driver-access-token"}


def test_driver_workspace_routes_are_registered(app):
    expected = {
        "/api/mobile/v1/driver/assignments": {"GET"},
        "/api/mobile/v1/driver/vehicles/switch": {"POST"},
        "/api/mobile/v1/driver/marketplace/vehicles": {"GET"},
        "/api/mobile/v1/driver/marketplace/vehicles/<string:listing_public_id>/apply": {"POST"},
        "/api/mobile/v1/driver/safety": {"GET"},
        "/api/mobile/v1/driver/notifications": {"GET"},
        "/api/mobile/v1/driver/opportunities": {"GET"},
        "/api/mobile/v1/driver/map/config": {"GET"},
    }
    registered = {}
    for rule in app.url_map.iter_rules():
        if rule.rule in expected:
            registered[rule.rule] = set(rule.methods)
    assert set(registered) == set(expected)
    for path, methods in expected.items():
        assert methods <= registered[path]


def test_driver_workspace_read_endpoints_require_bearer(client):
    endpoints = [
        "/api/mobile/v1/driver/assignments",
        "/api/mobile/v1/driver/marketplace/vehicles",
        "/api/mobile/v1/driver/safety",
        "/api/mobile/v1/driver/notifications",
        "/api/mobile/v1/driver/opportunities",
        "/api/mobile/v1/driver/map/config",
    ]
    for endpoint in endpoints:
        response = client.get(endpoint)
        assert response.status_code == 401, endpoint
        assert response.get_json()["code"] == "mobile_auth_required"


def test_driver_profile_exposes_read_only_preferences_performance_and_compliance(
    client, monkeypatch
):
    from app.transport.services import go_live_service

    _user, _profile, calls = _driver_mobile_context(monkeypatch)
    checklist = SimpleNamespace(
        to_dict=lambda: {
            "ready": True,
            "checks": [{"key": "profile", "label": "Active driver profile", "ok": True, "required": True}],
        }
    )
    monkeypatch.setattr(go_live_service, "can_go_live", lambda profile: checklist)

    response = client.get("/api/mobile/v1/driver/me", headers=_driver_headers())
    assert response.status_code == 200
    assert calls["expected_client"] == "driver"
    data = response.get_json()["data"]

    assert data["performance"] == {
        "total_trips": 120,
        "completed_trips": 112,
        "reliability_score": 97,
        "safety_score": 91,
        "acceptance_rate": "96.50",
        "cancellation_rate": "2.50",
        "total_distance_km": "4521.70",
        "total_duration_minutes": 3450,
        "average_rating": "4.85",
        "total_ratings": 105,
    }
    assert data["operational_preferences"]["service_types"] == ["on_demand", "scheduled"]
    assert data["operational_preferences"]["vehicle_classes"] == ["comfort", "premium"]
    assert data["operational_preferences"]["operational_zones"] == ["Kampala Central", "Wakiso"]
    assert data["operational_preferences"]["max_passenger_capacity"] == 4
    assert data["operational_preferences"]["auto_accept_bookings"] is False
    assert data["compliance"]["license_verified"] is True
    assert data["compliance"]["background_check_status"] == "clear"
    assert data["emergency_contact"]["name"] == "Emergency Contact"
    serialized = response.get_data(as_text=True).lower()
    for forbidden in ("license_number_encrypted", "license_number", "driver_metadata"):
        assert forbidden not in serialized


def test_driver_trip_history_all_scope_uses_booking_service_and_redacts_rows(
    client, monkeypatch
):
    from app.transport.services.booking_service import BookingService

    _user, profile, _calls = _driver_mobile_context(monkeypatch)
    called = {}

    def all_bookings(self, driver_user_id):
        called["driver_user_id"] = driver_user_id
        return [{
            "booking_reference": "AF360-ALL-001",
            "status": "completed",
            "booking_mode": "scheduled",
            "pickup_time": datetime(2026, 11, 8, 8, 0, tzinfo=timezone.utc),
            "pickup_schedule": {"local_datetime": "2026-11-08T11:00:00", "timezone_name": "Africa/Kampala"},
            "pickup_location_text": "Kampala",
            "dropoff_location_text": "Entebbe",
            "passenger_count": 1,
            "final_price": Decimal("80.00"),
            "currency": "UGX",
            "payment_method": "cash",
            "payment_status": "captured",
            "can_mark_no_show": False,
            "passenger_phone": "+256700000000",
            "booking_metadata": {"private": "do not return"},
        }]

    monkeypatch.setattr(BookingService, "get_driver_bookings", all_bookings)
    response = client.get(
        "/api/mobile/v1/driver/trips?scope=all&limit=5",
        headers=_driver_headers(),
    )
    assert response.status_code == 200
    assert called["driver_user_id"] == profile.user_id
    data = response.get_json()["data"]
    assert data["scope"] == "all"
    assert data["count"] == 1
    assert data["items"][0]["booking_reference"] == "AF360-ALL-001"
    assert data["items"][0]["pickup_schedule"]["timezone_name"] == "Africa/Kampala"
    serialized = response.get_data(as_text=True).lower()
    assert "+256700000000" not in serialized
    assert "booking_metadata" not in serialized
    assert "do not return" not in serialized


def test_driver_assignments_are_self_scoped_and_return_90_day_vehicle_history(
    app, client, monkeypatch
):
    from app.transport.models import DriverVehicleHistory, ScheduledRoute, Vehicle

    assigned = SimpleNamespace(
        id=51, public_id="vehicle-assigned-public", make="Toyota", model="Prius",
        year=2022, license_plate="UAB 100A", vehicle_class="comfort", status="active",
        is_available=True, passenger_capacity=4, safety_features=["seatbelts", "first_aid_kit"],
    )
    owned = SimpleNamespace(
        id=52, public_id="vehicle-owned-public", make="Honda", model="Fit",
        year=2021, license_plate="UAB 200B", vehicle_class="economy", status="active",
        is_available=True, passenger_capacity=4, safety_features=["seatbelts"],
    )
    history_row = SimpleNamespace(
        vehicle=assigned, assignment_reason="shift_start", was_breakdown=False,
        started_at=datetime(2026, 11, 1, tzinfo=timezone.utc),
        ended_at=None,
    )
    route_row = SimpleNamespace(
        name="Kampala–Entebbe", route_code="KLA-EBB", route_type="shuttle",
        primary_zone="Kampala", next_departure=datetime(2026, 11, 10, 8, tzinfo=timezone.utc),
        available_seats=3, vehicle_capacity=14, price_per_seat=Decimal("25000.00"),
        is_free=False,
    )
    _user, profile, _calls = _driver_mobile_context(monkeypatch, current_vehicle=assigned)
    with app.app_context():
        monkeypatch.setattr(Vehicle, "query", FakeQuery([assigned, owned]))
        monkeypatch.setattr(DriverVehicleHistory, "query", FakeQuery([history_row]))
        monkeypatch.setattr(ScheduledRoute, "query", FakeQuery([route_row]))

    response = client.get("/api/mobile/v1/driver/assignments", headers=_driver_headers())
    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["assigned_vehicle"]["public_id"] == "vehicle-assigned-public"
    assert [v["public_id"] for v in data["owned_vehicles"]] == [
        "vehicle-assigned-public", "vehicle-owned-public"
    ]
    assert [v["public_id"] for v in data["switchable_vehicles"]] == ["vehicle-owned-public"]
    assert data["vehicle_history"][0]["license_plate"] == "UAB 100A"
    assert data["scheduled_routes"][0]["route_code"] == "KLA-EBB"
    assert data["history_window_days"] == 90
    serialized = response.get_data(as_text=True).lower()
    for forbidden in ('"id":', "driver_id", "vehicle_id", "assigned_driver_id"):
        assert forbidden not in serialized


def test_driver_vehicle_switch_uses_public_reference_and_redacts_internal_id(
    client, monkeypatch
):
    from app.extensions import db
    from app.transport.api.driver_routes import DriverVehicleSwitchResource

    assigned = SimpleNamespace(
        public_id="vehicle-public-target", make="Toyota", model="Vitz", year=2020,
        license_plate="UAB 300C", vehicle_class="economy", status="active",
        is_available=True, passenger_capacity=4, safety_features=[],
    )
    _user, profile, _calls = _driver_mobile_context(monkeypatch, current_vehicle=assigned)
    captured = {}
    monkeypatch.setattr(
        DriverVehicleSwitchResource,
        "post",
        lambda self, driver_id: captured.update(driver_id=driver_id) or {
            "success": True,
            "data": {"unchanged": False, "reason": "shift_start", "assigned_vehicle": {"id": 999}},
        },
    )
    monkeypatch.setattr(db.session, "expire", lambda *args, **kwargs: None)
    monkeypatch.setattr(db.session, "refresh", lambda *args, **kwargs: None)

    response = client.post(
        "/api/mobile/v1/driver/vehicles/switch",
        json={"vehicle_public_id": "vehicle-public-target", "reason": "shift_start"},
        headers=_driver_headers(),
    )
    assert response.status_code == 200
    assert captured["driver_id"] == profile.id
    data = response.get_json()["data"]
    assert data["assigned_vehicle"]["public_id"] == "vehicle-public-target"
    assert "vehicle_id" not in response.get_data(as_text=True).lower()
    assert '"id"' not in response.get_data(as_text=True).lower()


def test_driver_vehicle_switch_resolves_public_id_through_canonical_resource(
    app, client, monkeypatch
):
    from app.auth import helpers
    from app.extensions import db
    from app.transport.api.driver_routes import DriverVehicleSwitchResource
    from app.transport.models import Vehicle
    from app.transport.services import go_live_service

    previous = SimpleNamespace(id=41, license_plate="UAA 100A")
    target = SimpleNamespace(
        id=999,
        public_id="vehicle-public-target",
        owner_type="driver",
        owner_id=902,
        status="active",
        license_plate="UAB 999Z",
        make="Toyota",
        model="Vitz",
        year=2022,
        vehicle_class="economy",
        is_available=True,
        passenger_capacity=4,
        safety_features=["seatbelts"],
    )
    _user, profile, _calls = _driver_mobile_context(monkeypatch, current_vehicle=previous)
    monkeypatch.setattr(
        DriverVehicleSwitchResource,
        "_profile_or_error",
        lambda self, driver_id: (profile, None, None),
    )
    monkeypatch.setattr(helpers, "has_global_role", lambda *args: False)
    monkeypatch.setattr(
        go_live_service,
        "can_go_live",
        lambda driver: SimpleNamespace(checks=[SimpleNamespace(key="blocked", ok=True)]),
    )
    from app.transport import models as transport_models
    captured = {}

    def assign(driver, vehicle, **kwargs):
        captured.update(driver=driver, vehicle=vehicle, kwargs=kwargs)
        driver.current_vehicle = vehicle

    with app.app_context():
        monkeypatch.setattr(Vehicle, "query", FakeQuery([target]))
        monkeypatch.setattr(transport_models, "assign_driver_to_vehicle", assign)
        monkeypatch.setattr(db.session, "expire", lambda *args, **kwargs: None)
        monkeypatch.setattr(db.session, "refresh", lambda *args, **kwargs: None)

    response = client.post(
        "/api/mobile/v1/driver/vehicles/switch",
        json={"vehicle_public_id": "vehicle-public-target", "reason": "shift_start"},
        headers=_driver_headers(),
    )
    assert response.status_code == 200, response.get_data(as_text=True)
    assert captured["driver"] is profile
    assert captured["vehicle"] is target
    assert captured["kwargs"]["reason"] == "shift_start"
    data = response.get_json()["data"]
    assert data["assigned_vehicle"]["public_id"] == "vehicle-public-target"
    assert '"id"' not in response.get_data(as_text=True).lower()
    assert "vehicle_id" not in response.get_data(as_text=True).lower()


def test_driver_vehicle_switch_rejects_missing_public_reference(client, monkeypatch):
    _driver_mobile_context(monkeypatch)
    response = client.post("/api/mobile/v1/driver/vehicles/switch", json={}, headers=_driver_headers())
    assert response.status_code == 400
    assert response.get_json()["code"] == "driver_vehicle_public_id_required"


def test_driver_marketplace_lists_only_public_eligible_vehicles_and_no_internal_ids(
    app, client, monkeypatch
):
    from app.transport.models import Vehicle, VehicleMarketplaceListing
    from app.transport.services.marketplace_service import get_marketplace_service

    vehicle = SimpleNamespace(
        id=500, public_id="vehicle-market-public", is_deleted=False,
        make="Toyota", model="Noah", year=2021, vehicle_class="van",
        passenger_capacity=7, owner_type="organisation",
    )
    listing = SimpleNamespace(
        id=600, public_id="listing-market-public", vehicle=vehicle,
        title="Family shuttle vehicle", description="Available for contracted work",
        compensation_model="revenue_split", driver_revenue_share_pct=Decimal("75"),
        fixed_rental_amount=None, rental_frequency=None, application_deadline=None,
        listing_status="active", visibility="public", owner_id=777,
    )
    _user, profile, _calls = _driver_mobile_context(monkeypatch)
    with app.app_context():
        monkeypatch.setattr(Vehicle, "query", FakeQuery([]))
        monkeypatch.setattr(VehicleMarketplaceListing, "query", FakeQuery([listing]))
    monkeypatch.setattr(
        "app.transport.services.marketplace_service.get_marketplace_service",
        lambda: SimpleNamespace(_check_driver_eligibility=lambda driver, item: driver is profile),
    )

    response = client.get("/api/mobile/v1/driver/marketplace/vehicles", headers=_driver_headers())
    assert response.status_code == 200
    item = response.get_json()["data"]["items"][0]
    assert item["listing_public_id"] == "listing-market-public"
    assert item["vehicle_public_id"] == "vehicle-market-public"
    assert item["compensation"] == "75% revenue share"
    serialized = response.get_data(as_text=True).lower()
    assert '"id"' not in serialized
    assert "vehicle_id" not in serialized


def test_driver_marketplace_application_uses_canonical_service_and_public_listing_ref(
    app, client, monkeypatch
):
    from app.transport.models import VehicleMarketplaceListing

    listing = SimpleNamespace(
        id=600, public_id="listing-market-public",
        listing_status="active", visibility="public", is_deleted=False,
    )
    application = SimpleNamespace(
        public_id="application-public",
        status="pending",
        applied_at=datetime(2026, 11, 9, tzinfo=timezone.utc),
    )
    _user, profile, _calls = _driver_mobile_context(monkeypatch)
    with app.app_context():
        monkeypatch.setattr(VehicleMarketplaceListing, "query", FakeQuery([listing]))
    captured = {}
    monkeypatch.setattr(
        "app.transport.services.marketplace_service.get_marketplace_service",
        lambda: SimpleNamespace(
            submit_application=lambda user_id, listing_id, data: (
                captured.update(user_id=user_id, listing_id=listing_id, data=data) or application
            )
        ),
    )

    response = client.post(
        "/api/mobile/v1/driver/marketplace/vehicles/listing-market-public/apply",
        json={
            "cover_letter": "I have experience with passenger transport.",
            "proposed_schedule": {"days": ["Monday", "Tuesday"]},
            "proposed_hours_per_week": 40,
            "expected_earnings": "250000",
            "references": ["Ref A"],
        },
        headers=_driver_headers(),
    )
    assert response.status_code == 201
    assert captured["user_id"] == profile.user_id
    assert captured["listing_id"] == listing.id
    assert captured["data"]["proposed_hours_per_week"] == 40
    data = response.get_json()["data"]
    assert data["application_public_id"] == "application-public"
    assert "listing_id" not in response.get_data(as_text=True).lower()


def test_driver_safety_is_scoped_to_own_incidents_and_redacted(app, client, monkeypatch):
    from app.transport.models import TransportIncident

    incident = SimpleNamespace(
        incident_reference="INC12345678", title="Tyre puncture",
        incident_type="vehicle", incident_category="safety",
        severity="medium", status="reported", priority="medium",
        occurred_at=datetime(2026, 11, 8, tzinfo=timezone.utc),
        created_at=datetime(2026, 11, 8, tzinfo=timezone.utc),
        investigation_notes="PRIVATE INVESTIGATION NOTES",
        location={"latitude": 0.3, "longitude": 32.5},
    )
    _user, profile, _calls = _driver_mobile_context(monkeypatch)
    profile.current_vehicle = SimpleNamespace(safety_features=["seatbelts", "first_aid_kit"])
    with app.app_context():
        monkeypatch.setattr(TransportIncident, "query", FakeQuery([incident]))

    response = client.get("/api/mobile/v1/driver/safety", headers=_driver_headers())
    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["safety_score"] == 91
    assert data["assigned_vehicle_safety_features"] == ["seatbelts", "first_aid_kit"]
    assert data["open_incidents"][0]["incident_reference"] == "INC12345678"
    serialized = response.get_data(as_text=True).lower()
    assert "investigation_notes" not in serialized
    assert "private investigation notes" not in serialized
    assert "location" not in data["open_incidents"][0]


def test_driver_notifications_are_scoped_to_authenticated_user_transport_module(
    app, client, monkeypatch
):
    from app.notifications.models import Notification

    rows = [
        SimpleNamespace(
            public_id="notification-public-1",
            subject="Trip updated",
            body="Your scheduled pickup has changed.",
            is_read=False,
            created_at=datetime(2026, 11, 9, tzinfo=timezone.utc),
        )
    ]
    fake = FakeQuery(rows, count=2)
    with app.app_context():
        monkeypatch.setattr(Notification, "query", fake)
    _user, profile, _calls = _driver_mobile_context(monkeypatch)

    response = client.get("/api/mobile/v1/driver/notifications", headers=_driver_headers())
    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["unread_count"] == 2
    assert data["items"][0]["public_id"] == "notification-public-1"
    filter_calls = [call[1] for call in fake.calls if call[0] == "filter_by"]
    assert {"user_id": profile.user_id, "module": "transport", "is_deleted": False} in filter_calls


def test_driver_opportunities_returns_aggregate_count_only(app, client, monkeypatch):
    from app.transport.models import Booking

    fake = FakeQuery(count=14)
    with app.app_context():
        monkeypatch.setattr(Booking, "query", fake)
    _driver_mobile_context(monkeypatch)

    response = client.get("/api/mobile/v1/driver/opportunities", headers=_driver_headers())
    assert response.status_code == 200
    assert response.get_json()["data"] == {"open_requests_count": 14}
    assert response.get_data(as_text=True).count("14") == 1


def test_driver_map_config_contains_only_public_geo_settings(client, monkeypatch):
    from app.geo import config as geo_config
    from app.geo import map_renderer

    _driver_mobile_context(monkeypatch)
    monkeypatch.setattr(geo_config, "load_geo_config", lambda app: SimpleNamespace())
    monkeypatch.setattr(
        map_renderer,
        "build_public_map_config",
        lambda cfg: {
            "tile_url_template": "https://tiles.example.test/{z}/{x}/{y}.png",
            "tile_attribution": "Tiles by Test",
            "tile_source_label": "operator-external",
            "default_center": {"latitude": 0.3136, "longitude": 32.5811},
            "default_zoom": 12,
            "tiles_backend_available": True,
            "tiles_kind": "external",
        },
    )

    response = client.get("/api/mobile/v1/driver/map/config", headers=_driver_headers())
    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["geocode_path"] == "/geo/api/geocode"
    assert data["default_center"]["latitude"] == 0.3136
    serialized = response.get_data(as_text=True).lower()
    assert "api_key" not in serialized
    assert "geoapify_api_key" not in serialized
