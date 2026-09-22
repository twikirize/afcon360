"""AFCON360 GEO foundation tests (slice 1: boundary + validation + math).

Pure unit tests: no DB, no Redis, no network, no Flask app required.
Covers mandate §50 (coordinates) + no-radians-regression guard.
"""

import math
from datetime import datetime, timedelta, timezone

import pytest

from app.geo import geo_bp, init_geo_module
from app.geo.services import (
    NearbyService,
    eta_from_duration,
    get_geocoding_service,
    get_location_service,
    get_routing_service,
    straight_line_distance_m,
)
from app.geo.validation import (
    MAX_SEARCH_RADIUS_M,
    normalize_location_payload,
    normalize_point,
    validate_radius_m,
)
from app.geo.interfaces import GeoPoint
from app.utils.exceptions import ValidationError


# --- boundary ----------------------------------------------------------

def test_geo_blueprint_identity():
    assert geo_bp.name == "geo"
    assert geo_bp.url_prefix == "/geo"


def test_geo_singletons_stable():
    assert get_location_service() is get_location_service()
    assert get_routing_service() is get_routing_service()
    assert get_geocoding_service() is get_geocoding_service()


# --- coordinates (mandate §50) -----------------------------------------

@pytest.mark.parametrize("lat,lng", [
    (0.3476, 32.5825),    # Kampala
    (-90, -180),          # boundary
    (90, 180),            # boundary
    ("0.3476", "32.5825"),  # numeric strings coerce
    (0, 0),
])
def test_valid_coordinates_pass(lat, lng):
    point = normalize_point(lat, lng)
    assert -90 <= point.latitude <= 90
    assert -180 <= point.longitude <= 180


@pytest.mark.parametrize("lat,lng", [
    (91, 0), (0, 181), (-91, 0), (0, -181),
    ("abc", 0), (0, None), (float("nan"), 0),
])
def test_invalid_coordinates_raise(lat, lng):
    with pytest.raises(ValidationError):
        normalize_point(lat, lng)


def test_location_payload_contract_matches_tracking_service():
    payload = {"latitude": 0.3476, "longitude": 32.5825,
               "accuracy": 5.0, "speed": 3.1, "heading": 90.0}
    point = normalize_location_payload(payload)
    assert point.latitude == pytest.approx(0.3476)
    assert point.accuracy == pytest.approx(5.0)


def test_location_payload_missing_fields_raise():
    with pytest.raises(ValidationError):
        normalize_location_payload({"latitude": 0.0})
    with pytest.raises(ValidationError):
        normalize_location_payload({"latitude": 0.0, "longitude": 0.0,
                                    "speed": -1.0})


def test_radius_guard():
    assert validate_radius_m(5000) == 5000.0
    with pytest.raises(ValidationError):
        validate_radius_m(0)
    with pytest.raises(ValidationError):
        validate_radius_m(MAX_SEARCH_RADIUS_M + 1)


# --- distance: known values + radians regression ------------------------

def test_equatorial_degree_is_111km():
    dist = straight_line_distance_m(GeoPoint(0.0, 0.0), GeoPoint(0.0, 1.0))
    assert dist == pytest.approx(111_195, abs=200)


def test_kampala_entebbe_corridor():
    kampala = GeoPoint(0.3476, 32.5825)
    entebbe = GeoPoint(0.0515, 32.4467)
    dist = straight_line_distance_m(kampala, entebbe)
    assert 30_000 < dist < 42_000  # ~36 km straight-line


def test_no_radians_regression_against_naive_degrees():
    """The Transport matching defect passed degrees into trig functions.
    A naive (degree-based) implementation diverges wildly; GEO must not."""
    a = GeoPoint(0.3476, 32.5825)
    b = GeoPoint(0.0515, 32.4467)
    correct = straight_line_distance_m(a, b)
    # naive: same formula without radians() -> different magnitude
    d_lat, d_lng = (b.latitude - a.latitude), (b.longitude - a.longitude)
    naive = 2 * 6_371_000.0 * math.asin(math.sqrt(
        math.sin(d_lat / 2) ** 2
        + math.cos(a.latitude) * math.cos(b.latitude)
        * math.sin(d_lng / 2) ** 2))
    assert abs(naive - correct) > 1_000_000  # proves test can catch the bug
    assert correct < 100_000


# --- routing/geocoding honesty ------------------------------------------

def test_routing_without_provider_is_truthful_miss():
    service = get_routing_service()
    result = service.route(GeoPoint(0.3, 32.5), GeoPoint(0.0, 32.4))
    assert result.resolved is False
    assert result.provider == "haversine-fallback"
    assert result.distance_m > 0  # labelled straight-line, not road


def test_geocoding_without_provider_is_truthful_miss():
    service = get_geocoding_service()
    assert service.geocode("Nambole, Kampala") == []
    assert service.reverse(GeoPoint(0.3, 32.5)).resolved is False


# --- nearby ordering -----------------------------------------------------

def test_nearby_orders_by_distance_within_radius():
    center = GeoPoint(0.3476, 32.5825)
    near = GeoPoint(0.3480, 32.5830)
    far = GeoPoint(0.4000, 32.6000)
    hits = NearbyService.order_by_distance(center, [far, near], 5000)
    assert [h.point for h in hits] == [near]


# --- freshness + ETA ------------------------------------------------------

def test_freshness_and_eta():
    service = get_location_service()
    fresh_point = GeoPoint(0.3, 32.5,
                           timestamp=datetime.now(timezone.utc))
    assert service.check_freshness(fresh_point)["fresh"] is True
    stale_point = GeoPoint(0.3, 32.5, timestamp=datetime.now(timezone.utc)
                           - timedelta(hours=1))
    assert service.check_freshness(stale_point)["fresh"] is False
    assert service.check_freshness(GeoPoint(0.3, 32.5))["fresh"] is False

    now = datetime.now(timezone.utc)
    assert eta_from_duration(600, now=now) == now + timedelta(seconds=600)
    with pytest.raises(ValidationError):
        eta_from_duration(-5)
