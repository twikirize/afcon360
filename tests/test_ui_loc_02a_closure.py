"""UI-LOC-02A closure proofs (safety-closure node).

Node-owned additive tests. Proves, against the REAL server boundary:
  1. canonical validator matrix (True/False/NaN/Inf/-Inf/None/"abc" rejected;
     (0,0) + valid Kampala accepted; out-of-range rejected)
  2. create_booking rejects unresolved/invalid endpoints; valid books
  3. POST /api/transport/ride-options rejects the six classes server-side
     WITHOUT reaching fare calculation; valid still 200 straight_line_planner
  4. explicit estimate (fare/estimate) still serves planning_default while
     real booking with no coordinates is refused
"""

import math
import uuid
from datetime import datetime, timedelta, timezone

import pytest

LAT_A, LNG_A = 0.3150, 32.5820
LAT_B, LNG_B = 0.3350, 32.6000

RIDE_OPTIONS_URL = "/api/transport/ride-options"
FARE_ESTIMATE_URL = "/api/transport/fare/estimate"


def _user(app, tag="loc02a"):
    from app.extensions import db
    from app.identity.models.user import User
    with app.app_context():
        uid = uuid.uuid4().hex[:8]
        user = User(username=f"{tag}_{uid}",
                    email=f"{tag}_{uid}@test.example.com", is_active=True)
        user.set_password("TestPassword123!")
        db.session.add(user)
        db.session.commit()
        return user.id


def _payload(**over):
    data = {
        "pickup_location": "Nile Stadium, Kampala",
        "dropoff_location": "Entebbe Airport",
        "pickup_time": (datetime.now(timezone.utc)
                        + timedelta(hours=1)).isoformat(),
        "service_type": "on_demand", "passenger_count": 1,
    }
    data.update(over)
    return data


def _valid_ride_body(**over):
    body = {
        "pickup_latitude": LAT_A, "pickup_longitude": LNG_A,
        "dropoff_latitude": LAT_B, "dropoff_longitude": LNG_B,
    }
    body.update(over)
    return body


# --- Step 8: canonical validator matrix ------------------------------------

def test_canonical_validator_matrix(app):
    from app.core.validators import validate_coordinates
    from app.utils.exceptions import ValidationError
    with app.app_context():
        # Rejected: bool pair members
        for bad in (True, False):
            with pytest.raises(ValidationError):
                validate_coordinates(bad, LNG_A)
            with pytest.raises(ValidationError):
                validate_coordinates(LAT_A, bad)
        # Rejected: non-finite / missing / non-numeric / out-of-range
        for bad_lat, bad_lng in [
            (float("nan"), LNG_A), (LAT_A, float("nan")),
            (float("inf"), LNG_A), (LAT_A, float("-inf")),
            (float("-inf"), LNG_A), (LAT_A, float("inf")),
            ("nan", LNG_A), (LAT_A, "Infinity"),
            (None, LNG_A), (LAT_A, None),
            ("abc", LNG_A), (LAT_A, "abc"),
            (999.0, LNG_A), (-91.0, LNG_A),
            (LAT_A, 181.0), (LAT_A, -181.0),
        ]:
            with pytest.raises(ValidationError):
                validate_coordinates(bad_lat, bad_lng)
        # Accepted: normal valid coordinates and (0,0) (02A policy:
        # no service-area/plausibility rule authorized yet).
        assert validate_coordinates(LAT_A, LNG_A) is None
        assert validate_coordinates(0, 0) is None
        assert validate_coordinates("0.3150", "32.5820") is None


# --- Steps 3-4: booking safety + planning_default refusal ------------------

def test_booking_rejects_bool_nan_inf(app):
    from app.transport.services.booking_service import get_booking_service
    from app.utils.exceptions import ValidationError
    user_id = _user(app)
    with app.app_context():
        svc = get_booking_service()
        # bool coordinates
        with pytest.raises(ValidationError):
            svc.create_booking(user_id, _payload(
                pickup_latitude=True, pickup_longitude=LNG_A,
                dropoff_latitude=LAT_B, dropoff_longitude=LNG_B))
        # NaN / Infinity (float and string forms)
        for bad in (float("nan"), float("inf"), float("-inf"),
                    "nan", "Infinity", "-Infinity"):
            with pytest.raises(ValidationError):
                svc.create_booking(user_id, _payload(
                    pickup_latitude=bad, pickup_longitude=LNG_A,
                    dropoff_latitude=LAT_B, dropoff_longitude=LNG_B))
        # text-only and client estimate without coordinates refused
        with pytest.raises(ValidationError):
            svc.create_booking(user_id, _payload())
        with pytest.raises(ValidationError):
            svc.create_booking(user_id, _payload(estimated_distance=12))


def test_booking_valid_coordinates_still_books(app):
    from app.extensions import db
    from app.transport.models import Booking
    from app.transport.services.booking_service import get_booking_service
    user_id = _user(app)
    with app.app_context():
        result = get_booking_service().create_booking(user_id, _payload(
            pickup_latitude=LAT_A, pickup_longitude=LNG_A,
            dropoff_latitude=LAT_B, dropoff_longitude=LNG_B))
    assert result["success"] is True
    with app.app_context():
        booking = db.session.get(Booking, result["data"]["booking_id"])
        assert booking.booking_metadata["distance_basis"] == "straight_line_planner"


# --- Steps 6-7: ride_options server boundary (direct POST) ------------------

def test_ride_options_rejection_classes(app, anonymous_client):
    cases = {
        # missing endpoint pairs
        "no_pickup": {"dropoff_latitude": LAT_B, "dropoff_longitude": LNG_B},
        "no_dropoff": {"pickup_latitude": LAT_A, "pickup_longitude": LNG_A},
        # partial pairs
        "pickup_lat_only": {"pickup_latitude": LAT_A,
                            "dropoff_latitude": LAT_B,
                            "dropoff_longitude": LNG_B},
        "pickup_lng_only": {"pickup_longitude": LNG_A,
                            "dropoff_latitude": LAT_B,
                            "dropoff_longitude": LNG_B},
        "dropoff_lat_only": {"pickup_latitude": LAT_A,
                             "pickup_longitude": LNG_A,
                             "dropoff_latitude": LAT_B},
        "dropoff_lng_only": {"pickup_latitude": LAT_A,
                             "pickup_longitude": LNG_A,
                             "dropoff_longitude": LNG_B},
        # empty string
        "empty_string": _valid_ride_body(pickup_latitude=""),
        # non-numeric
        "non_numeric": _valid_ride_body(pickup_latitude="abc"),
        # bool
        "bool_true": _valid_ride_body(pickup_latitude=True),
        "bool_false": _valid_ride_body(dropoff_longitude=False),
        # non-finite
        "nan": _valid_ride_body(pickup_latitude=float("nan")),
        "inf": _valid_ride_body(pickup_latitude=float("inf")),
        "neg_inf": _valid_ride_body(dropoff_longitude=float("-inf")),
        # out of range
        "lat_high": _valid_ride_body(pickup_latitude=91.0),
        "lat_low": _valid_ride_body(pickup_latitude=-91.0),
        "lng_high": _valid_ride_body(dropoff_longitude=181.0),
        "lng_low": _valid_ride_body(dropoff_longitude=-181.0),
    }
    for name, body in cases.items():
        resp = anonymous_client.post(RIDE_OPTIONS_URL, json=body)
        assert resp.status_code == 400, name
        assert resp.get_json()["success"] is False, name


def test_ride_options_rejected_quotes_never_reach_fare(app, anonymous_client,
                                                       monkeypatch):
    import app.transport.api.ride_options_routes as ro
    calls = []

    def _boom(**kwargs):
        calls.append(kwargs)
        raise AssertionError("fare must not be reached for rejected quotes")

    monkeypatch.setattr(ro.fare_service, "calculate_estimate", _boom)
    monkeypatch.setattr(ro, "available_by_class", lambda: (_ for _ in ()).throw(
        AssertionError("availability must not be reached for rejected quotes")))
    for body in (
        {},
        {"pickup_latitude": LAT_A},
        _valid_ride_body(pickup_latitude=True),
        _valid_ride_body(pickup_latitude=float("nan")),
        _valid_ride_body(pickup_latitude=999.0),
    ):
        resp = anonymous_client.post(RIDE_OPTIONS_URL, json=body)
        assert resp.status_code == 400
    assert calls == []


def test_ride_options_valid_still_works(app, anonymous_client):
    resp = anonymous_client.post(RIDE_OPTIONS_URL, json=_valid_ride_body())
    assert resp.status_code == 200
    data = resp.get_json()["data"]
    assert data["distance_basis"] == "straight_line_planner"


# --- Steps 5/11: explicit estimate vs booking separation --------------------

def test_explicit_estimate_keeps_planning_default(app, authenticated_client):
    resp = authenticated_client.post(FARE_ESTIMATE_URL, json={
        "service_type": "on_demand", "vehicle_class": "comfort"})
    assert resp.status_code == 200
    data = resp.get_json()["data"]
    assert data["distance_basis"] == "planning_default"


def test_booking_needs_coords_while_estimate_does_not(app,
                                                      authenticated_client):
    # estimate without coordinates: allowed, labelled planning_default
    est = authenticated_client.post(FARE_ESTIMATE_URL, json={
        "service_type": "on_demand", "vehicle_class": "comfort"})
    assert est.status_code == 200
    assert est.get_json()["data"]["distance_basis"] == "planning_default"
    # real booking without coordinates: refused
    from app.transport.services.booking_service import get_booking_service
    from app.utils.exceptions import ValidationError
    user_id = _user(app, "estpax")
    with app.app_context():
        with pytest.raises(ValidationError):
            get_booking_service().create_booking(user_id, _payload())


# --- Legacy route: POST /transport/book with text-only endpoints -----------

def test_legacy_book_route_rejects_text_only_endpoints(app,
                                                      authenticated_client,
                                                      test_user):
    """UI-LOC-02A legacy-route proof (single focused test).

    The retired `book.html` form posts no lat/lng fields. With the booking
    safety closure, such a text-only submission must fail honestly at the
    route (redirect back to the book form) instead of silently pricing the
    old 5 km planning default — and must create no booking row.
    """
    from app.extensions import db
    from app.identity.individuals.individual_verification import (
        IndividualVerification,
    )
    from app.identity.models.user import User
    from app.transport.models import Booking

    with app.app_context():
        rider = db.session.merge(test_user)
        rider_id = rider.id
        rider.phone_verified = True
        rider.phone_verified_at = datetime.now(timezone.utc)
        if not rider.phone:
            rider.phone = f"+2567{uuid.uuid4().hex[:7]}"
        db.session.add(IndividualVerification(
            user_id=rider_id, status="verified",
            scope={"identity": True, "address": True,
                   "national_id": True, "biometric": True}))
        db.session.commit()
    from app.auth.kyc_compliance import calculate_kyc_tier
    with app.app_context():
        assert calculate_kyc_tier(rider_id)["tier"] >= 2
        before = Booking.query.filter_by(user_id=rider_id).count()

    # Mirrors templates/transport/book.html: text addresses, no coordinates.
    resp = authenticated_client.post("/transport/book", data={
        "service_type": "on_demand",
        "provider_type": "individual_driver",
        "passenger_count": "1",
        "luggage_count": "0",
        "currency": "USD",
        "pickup_time": (datetime.now(timezone.utc)
                        + timedelta(hours=1)).isoformat(),
        "payment_method": "cash",
        "vehicle_class": "comfort",
        "pickup_location": "Kampala Centre",
        "dropoff_location": "Nile Independence Stadium",
    }, follow_redirects=False)

    assert resp.status_code in (301, 302)
    location = resp.headers.get("Location", "")
    assert "/transport/book" in location
    assert "/transport/rides/" not in location
    with app.app_context():
        assert Booking.query.filter_by(user_id=rider_id).count() == before
