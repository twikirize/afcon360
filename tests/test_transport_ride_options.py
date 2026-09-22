"""Transport ride options (hailing node) - contract tests.

Pins the anonymous ride-options endpoint: it composes real fleet
availability grouped by class with the canonical fare engine, honours
currency validation, reports the straight-line distance basis and
planning ETA, and leaks no internal IDs. Excludes vehicles and drivers
that are deleted, unavailable, or inactive — per the sanctioned
``availability_service`` predicate (online + approved + fresh driver
linked to the vehicle by an active history row, not engaged elsewhere).
The booking action itself remains behind transport.book_transport
(auth + KYC), so no booking is created here.
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
    resp = anonymous_client.post("/api/transport/ride-options", json={})
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["success"] is True
    data = payload["data"]
    assert data["service_type"] == "on_demand"
    assert data["currency"] == "USD"
    assert data["distance_basis"] == "planning_default"
    assert data["note"]
    if data["options"]:
        assert set(data["options"][0]) >= {
            "vehicle_class", "display_name", "available_count",
            "capacity", "luggage", "fare_total", "fare_breakdown",
            "fare_version", "currency", "eta_minutes",
        }


def test_ride_options_rejects_unknown_currency(app, anonymous_client):
    resp = anonymous_client.post("/api/transport/ride-options",
                                 json={"currency": "GIL"})
    assert resp.status_code == 400


def test_ride_options_prices_available_classes_via_engine(
        app, anonymous_client, db_session):
    loc = {"latitude": 0.32, "longitude": 32.585}
    keep = set()
    d1 = _seed_driver(db_session, vehicle_class="comfort",
                      driver_location=loc, keep_online=keep)
    _seed_vehicle(db_session, d1, vehicle_class="comfort",
                  current_location=loc)
    d2 = _seed_driver(db_session, vehicle_class="comfort",
                      driver_location=loc, keep_online=keep)
    _seed_vehicle(db_session, d2, vehicle_class="comfort",
                  current_location=loc)
    d3 = _seed_driver(db_session, vehicle_class="economy",
                      driver_location=loc, keep_online=keep)
    _seed_vehicle(db_session, d3, vehicle_class="economy",
                  current_location=loc)

    iso = _OnlineFleetIsolation(keep)
    try:
        resp = anonymous_client.post(
            "/api/transport/ride-options",
            json={"service_type": "on_demand", "currency": "USD",
                  "estimated_distance_km": 5})
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["distance_basis"] == "planning_default"
        comfort = next(o for o in data["options"]
                       if o["vehicle_class"] == "comfort")
        economy = next(o for o in data["options"]
                       if o["vehicle_class"] == "economy")
        assert comfort["available_count"] == 2
        assert economy["available_count"] == 1
        expected = calculate_estimate(service_type="on_demand",
                                      vehicle_class="comfort", distance_km=5)
        assert Decimal(str(comfort["fare_total"])) == expected["total"]
        assert comfort["fare_version"] == FARE_VERSION
        # Cheapest first.
        totals = [Decimal(str(o["fare_total"])) for o in data["options"]]
        assert totals == sorted(totals)
        blob = __import__("json").dumps(data)
        assert "driver_id" not in blob and '"id":' not in blob
    finally:
        iso.restore()


def test_ride_options_excludes_unavailable_and_inactive(
        app, anonymous_client, db_session):
    loc = {"latitude": 0.32, "longitude": 32.585}
    keep = set()
    # Driver unavailable -> vehicle must not be offered.
    d1 = _seed_driver(db_session, vehicle_class="luxury",
                      is_available=False, driver_location=loc,
                      keep_online=keep)
    _seed_vehicle(db_session, d1, vehicle_class="luxury",
                  current_location=loc)
    # Vehicle inactive -> driver matchable but vehicle not offered.
    d2 = _seed_driver(db_session, vehicle_class="luxury",
                      driver_location=loc, keep_online=keep)
    _seed_vehicle(db_session, d2, vehicle_class="luxury", status="maintenance",
                  current_location=loc)

    iso = _OnlineFleetIsolation(keep)
    try:
        resp = anonymous_client.post("/api/transport/ride-options", json={})
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert all(o["vehicle_class"] != "luxury" for o in data["options"])
    finally:
        iso.restore()


def test_ride_options_straight_line_distance_and_eta(
        app, anonymous_client, db_session):
    from app.geo.interfaces import GeoPoint
    from app.geo.services import straight_line_distance_m

    loc = {"latitude": 0.32, "longitude": 32.59}
    keep = set()
    d1 = _seed_driver(db_session, vehicle_class="comfort",
                      driver_location=loc, keep_online=keep)
    _seed_vehicle(db_session, d1, vehicle_class="comfort",
                  current_location=loc)

    iso = _OnlineFleetIsolation(keep)
    try:
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
        assert isinstance(comfort["eta_minutes"], int)
        assert comfort["eta_minutes"] >= 1
        assert comfort["eta_basis"] == "straight_line_planner"
    finally:
        iso.restore()