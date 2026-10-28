"""Transport fare quote endpoint contract tests.

Pins the anonymous pre-confirmation endpoint: it validates resolved
coordinates, returns a short-lived signed fare quote for every supported
vehicle class using the canonical fare engine, and exposes no driver,
vehicle, availability-count, or ETA data. Most importantly, quote
requests must not create a Booking, RideRequest, SearchCycle or offer.
Driver lookup/matching is a separate post-confirmation step.
"""

import uuid
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from app.transport.models import (
    ComplianceStatus,
    DriverProfile,
    DriverVehicleHistory,
    Vehicle,
    VehicleClass,
    VerificationTier,
)
from app.transport.services.fare_service import FARE_VERSION, calculate_estimate


def _seed_driver(db_session, *, vehicle_class="comfort",
                 is_available=True, driver_location=None, keep_online=None):
    """Create a unique user + fully-eligible DriverProfile.

    ``keep_online`` marks drivers that must stay online when the test
    isolates the fleet (see ``_isolate_online_fleet``). Returns driver_id.
    """
    from app.identity.models.user import User

    uid = uuid.uuid4().hex[:8]
    user = User(username=f"ro_{uid}", email=f"ro_{uid}@test.example.com",
                is_active=True)
    user.set_password("TestPassword123!")
    db_session.add(user)
    db_session.flush()

    dp = DriverProfile(
        user_id=user.id,
        driver_code=f"RO-{uuid.uuid4().hex[:6].upper()}",
        verification_tier=VerificationTier.PLATFORM_VERIFIED,
        compliance_status=ComplianceStatus.APPROVED,
        is_active=True, is_online=True, is_available=is_available,
        max_passenger_capacity=4, vehicle_classes=[vehicle_class],
    )
    db_session.add(dp)
    db_session.flush()

    if keep_online is not None:
        keep_online.add(dp.id)
    if driver_location is not None:
        from app.transport.services.tracking_service import TrackingService
        TrackingService.update_location("driver", dp.id, driver_location)
    return dp.id


def _seed_vehicle(db_session, driver_id, *, vehicle_class="comfort",
                  status="active", current_location=None):
    v = Vehicle(
        owner_type="driver",
        owner_id=driver_id,
        license_plate=f"UG{uuid.uuid4().hex[:8].upper()}",
        make="Test",
        model="Model",
        year=2023,
        vehicle_type="Sedan",
        vehicle_class=vehicle_class,
        passenger_capacity=4,
        luggage_capacity=2,
        is_available=True,
        status=status,
        current_location=current_location,
    )
    db_session.add(v)
    db_session.flush()

    history = DriverVehicleHistory(
        driver_id=driver_id,
        vehicle_id=v.id,
        assignment_reason="test_ride_options",
        started_at=datetime.now(timezone.utc),
        ended_at=None,
    )
    db_session.add(history)
    db_session.flush()
    return v.id


class _OnlineFleetIsolation:
    """Deterministic fleet control for the shared test DB.

    Ride options count vehicles of online, approved, fresh drivers. Other
    suites leave such drivers behind, so a raw count can be polluted.
    Snapshot current online statuses, take everyone except ``keep_ids``
    offline, and restore afterwards — even on assertion failure.
    """

    def __init__(self, keep_ids):
        from app.extensions import db
        self._snapshot = [
            (d.id, d.is_online)
            for d in DriverProfile.query.filter(DriverProfile.is_online.is_(True)).all()
        ]
        keep = list(keep_ids or [])
        if keep:
            (DriverProfile.query.filter(
                DriverProfile.is_online.is_(True),
                DriverProfile.id.notin_(keep)).update(
                {DriverProfile.is_online: False}))
        else:
            (DriverProfile.query.filter(
                DriverProfile.is_online.is_(True)).update(
                {DriverProfile.is_online: False}))
        db.session.commit()

    def restore(self):
        from app.extensions import db
        for did, online in self._snapshot:
            d = db.session.get(DriverProfile, did)
            if d is not None and d.is_online is not online:
                d.is_online = online
        db.session.commit()


def test_ride_options_empty_body_returns_labeled_defaults(app, anonymous_client):
    # Now requires coordinates; provide a minimal valid coordinate set
    body = {
        "pickup_latitude": 0.3136,
        "pickup_longitude": 32.5811,
        "dropoff_latitude": 0.32,
        "dropoff_longitude": 32.59,
    }
    resp = anonymous_client.post("/api/transport/ride-options", json=body)
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["success"] is True
    data = payload["data"]
    assert data["service_type"] == "on_demand"
    assert data["currency"] == "USD"
    assert data["distance_basis"] == "straight_line_planner"
    assert data["note"]
    assert "does not query driver" in data["note"]
    assert data["options"], "a valid route should return fare quotes even with no drivers"
    assert {o["vehicle_class"] for o in data["options"]} == {
        str(vc.value) for vc in VehicleClass
    }
    required = {
        "vehicle_class", "display_name", "fare_total", "fare_breakdown",
        "fare_version", "currency", "quote_token",
    }
    for option in data["options"]:
        assert set(option) >= required
        assert not ({"available_count", "capacity", "luggage",
                     "eta_minutes", "eta_basis"} & set(option))
        assert option["fare_total"] > 0
        assert option["quote_token"]


def test_fare_quote_never_creates_request_search_or_booking(
        app, anonymous_client):
    from app.transport.models import Booking, OfferAttempt, RideRequest, SearchCycle

    def counts():
        with app.app_context():
            return (
                Booking.query.count(),
                RideRequest.query.count(),
                SearchCycle.query.count(),
                OfferAttempt.query.count(),
            )

    before = counts()
    response = anonymous_client.post(
        "/api/transport/ride-options",
        json={
            "service_type": "on_demand",
            "currency": "USD",
            "pickup_latitude": 0.3136,
            "pickup_longitude": 32.5811,
            "dropoff_latitude": 0.32,
            "dropoff_longitude": 32.59,
        },
    )
    assert response.status_code == 200, response.get_data(as_text=True)
    after = counts()
    assert after == before, "pricing alone must not persist a ride or start a search"


def test_ride_options_rejects_unknown_currency(app, anonymous_client):
    resp = anonymous_client.post("/api/transport/ride-options",
                                 json={"currency": "GIL"})
    assert resp.status_code == 400


def test_ride_options_prices_every_class_without_driver_lookup(
        app, anonymous_client, db_session, monkeypatch):
    # Any call to live supply is a bug: fare review must not start matching
    # or inspect availability before the rider agrees to the price.
    from app.transport.services import availability_service
    from app.transport.api import ride_options_routes

    def forbidden_supply_lookup(*args, **kwargs):
        pytest.fail("pre-confirmation fare quote queried live driver/vehicle supply")

    monkeypatch.setattr(
        availability_service, "available_by_class",
        forbidden_supply_lookup,
    )
    # Patch the endpoint namespace too so a future direct import of the
    # availability function cannot bypass this guard.
    monkeypatch.setattr(
        ride_options_routes, "available_by_class",
        forbidden_supply_lookup, raising=False,
    )
    monkeypatch.setattr(
        ride_options_routes, "nearest_eta_minutes_for_class",
        forbidden_supply_lookup, raising=False,
    )
    body = {"service_type": "on_demand", "currency": "USD",
            "pickup_latitude": 0.3136, "pickup_longitude": 32.5811,
            "dropoff_latitude": 0.32, "dropoff_longitude": 32.59}
    resp = anonymous_client.post("/api/transport/ride-options", json=body)
    assert resp.status_code == 200, resp.get_data(as_text=True)
    data = resp.get_json()["data"]
    assert data["distance_basis"] == "straight_line_planner"
    from app.geo.interfaces import GeoPoint
    from app.geo.services import straight_line_distance_m
    from app.transport.services.fare_quote_service import load_fare_quote, money_amount

    expected_km = straight_line_distance_m(
        GeoPoint(0.3136, 32.5811), GeoPoint(0.32, 32.59)
    ) / 1000.0
    assert data["distance_km"] == pytest.approx(expected_km)
    assert {o["vehicle_class"] for o in data["options"]} == {
        str(vc.value) for vc in VehicleClass
    }
    comfort = next(o for o in data["options"] if o["vehicle_class"] == "comfort")
    with app.app_context():
        quote = load_fare_quote(comfort["quote_token"])
    assert quote["vehicle_class"] == "comfort"
    assert quote["distance_km"] == round(expected_km, 6)
    assert quote["amount"] == format(Decimal(str(comfort["fare_total"])), ".2f")
    assert Decimal(str(comfort["fare_total"])) == money_amount(comfort["fare_total"])
    assert comfort["fare_version"] == FARE_VERSION
    assert "available_count" not in comfort and "eta_minutes" not in comfort
    totals = [Decimal(str(o["fare_total"])) for o in data["options"]]
    assert totals == sorted(totals)
    blob = __import__("json").dumps(data)
    assert "driver_id" not in blob and '"id":' not in blob


def test_ride_options_missing_pickup_coords(app, anonymous_client):
    body = {
        "dropoff_latitude": 0.32,
        "dropoff_longitude": 32.59,
    }
    resp = anonymous_client.post("/api/transport/ride-options", json=body)
    assert resp.status_code == 400
    payload = resp.get_json()
    assert payload["success"] is False
    assert "Missing coordinate" in payload["error"]


def test_ride_options_missing_dropoff_coords(app, anonymous_client):
    body = {
        "pickup_latitude": 0.3136,
        "pickup_longitude": 32.5811,
    }
    resp = anonymous_client.post("/api/transport/ride-options", json=body)
    assert resp.status_code == 400
    payload = resp.get_json()
    assert payload["success"] is False
    assert "Missing coordinate" in payload["error"]


def test_ride_options_partial_pickup_coords(app, anonymous_client):
    body = {
        "pickup_latitude": 0.3136,
        "dropoff_latitude": 0.32,
        "dropoff_longitude": 32.59,
    }
    resp = anonymous_client.post("/api/transport/ride-options", json=body)
    assert resp.status_code == 400
    payload = resp.get_json()
    assert payload["success"] is False
    assert "Missing coordinate" in payload["error"]


def test_ride_options_invalid_non_numeric(app, anonymous_client):
    body = {
        "pickup_latitude": "abc",
        "pickup_longitude": 32.5811,
        "dropoff_latitude": 0.32,
        "dropoff_longitude": 32.59,
    }
    resp = anonymous_client.post("/api/transport/ride-options", json=body)
    assert resp.status_code == 400
    payload = resp.get_json()
    assert payload["success"] is False
    assert "Invalid coordinate" in payload["error"]


def test_ride_options_out_of_range_latitude(app, anonymous_client):
    body = {
        "pickup_latitude": 999.0,
        "pickup_longitude": 32.5811,
        "dropoff_latitude": 0.32,
        "dropoff_longitude": 32.59,
    }
    resp = anonymous_client.post("/api/transport/ride-options", json=body)
    assert resp.status_code == 400
    payload = resp.get_json()
    assert payload["success"] is False
    assert "Invalid latitude" in payload["error"]


def test_ride_options_invalid_longitude(app, anonymous_client):
    body = {
        "pickup_latitude": 0.3136,
        "pickup_longitude": 200.0,
        "dropoff_latitude": 0.32,
        "dropoff_longitude": 32.59,
    }
    resp = anonymous_client.post("/api/transport/ride-options", json=body)
    assert resp.status_code == 400
    payload = resp.get_json()
    assert payload["success"] is False
    assert "Invalid longitude" in payload["error"]


def test_ride_options_valid_coordinates(app, anonymous_client):
    body = {
        "pickup_latitude": 0.3136,
        "pickup_longitude": 32.5811,
        "dropoff_latitude": 0.32,
        "dropoff_longitude": 32.59,
    }
    resp = anonymous_client.post("/api/transport/ride-options", json=body)
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["success"] is True
    data = payload["data"]
    assert data["distance_basis"] == "straight_line_planner"
    assert data["distance_km"] is not None
    assert isinstance(data["options"], list)



def test_fare_quote_does_not_depend_on_vehicle_availability(
        app, anonymous_client, monkeypatch):
    from app.transport.services import availability_service
    monkeypatch.setattr(
        availability_service, "available_by_class",
        lambda: pytest.fail("pre-confirmation fare quote queried live supply"),
    )
    body = {"pickup_latitude": 0.3136, "pickup_longitude": 32.5811,
            "dropoff_latitude": 0.32, "dropoff_longitude": 32.59}
    resp = anonymous_client.post("/api/transport/ride-options", json=body)
    assert resp.status_code == 200, resp.get_data(as_text=True)
    data = resp.get_json()["data"]
    assert "luxury" in {o["vehicle_class"] for o in data["options"]}
    assert all("available_count" not in o for o in data["options"])


def test_ride_options_distance_has_no_preconfirmation_eta(
        app, anonymous_client):
    from app.geo.interfaces import GeoPoint
    from app.geo.services import straight_line_distance_m
    body = {"service_type": "on_demand",
            "pickup_latitude": 0.3136, "pickup_longitude": 32.5811,
            "dropoff_latitude": 0.32, "dropoff_longitude": 32.59}
    resp = anonymous_client.post("/api/transport/ride-options", json=body)
    assert resp.status_code == 200
    data = resp.get_json()["data"]
    assert data["distance_basis"] == "straight_line_planner"
    expected_km = straight_line_distance_m(
        GeoPoint(0.3136, 32.5811), GeoPoint(0.32, 32.59)) / 1000.0
    assert data["distance_km"] == pytest.approx(expected_km)
    comfort = next(o for o in data["options"]
                   if o["vehicle_class"] == "comfort")
    assert comfort["quote_token"]
    assert "eta_minutes" not in comfort and "eta_basis" not in comfort

