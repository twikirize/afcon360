"""AFCON360 GEO operational contract tests (Node 4).

Pure unit tests: no DB, no Redis, no network, no Flask app required.
Proves the consumer-ready contract for nearby/nearest/bounding-box and
freshness edge cases, plus an end-to-end consumer-readiness flow through
the public GEO interface only (no domain imports).
"""

import math
from datetime import datetime, timedelta, timezone

import pytest

from app.geo.interfaces import GeoPoint
from app.geo.services import (
    EARTH_RADIUS_M,
    NearbyService,
    bounding_box,
    get_geocoding_service,
    get_location_service,
    get_routing_service,
    straight_line_distance_m,
)
from app.geo.validation import normalize_point
from app.utils.exceptions import ValidationError


KAMPALA = GeoPoint(0.3476, 32.5825)


def _due_north(center: GeoPoint, radius_m: float) -> GeoPoint:
    """Point exactly radius_m due north of center (great-circle)."""
    lat = center.latitude + math.degrees(radius_m / EARTH_RADIUS_M)
    return GeoPoint(lat, center.longitude)


# --- nearby boundary / empty / limit / duplicates -------------------------

def test_nearby_boundary_is_inclusive():
    candidate = _due_north(KAMPALA, 5_000.0)
    dist = straight_line_distance_m(KAMPALA, candidate)
    assert dist == pytest.approx(5_000.0, abs=1.0)
    hits = NearbyService.order_by_distance(KAMPALA, [candidate], 5_000.0)
    assert len(hits) == 1
    assert hits[0].distance_m == pytest.approx(5_000.0, abs=1.0)


def test_nearby_outside_radius_excluded():
    candidate = _due_north(KAMPALA, 5_001.0)
    hits = NearbyService.order_by_distance(KAMPALA, [candidate], 5_000.0)
    assert hits == []


def test_nearby_empty_candidates_returns_empty_list():
    assert NearbyService.order_by_distance(KAMPALA, [], 5_000.0) == []
    assert NearbyService.nearest(KAMPALA, [], 3) == []


def test_nearby_limit_truncates_sorted_hits():
    points = [GeoPoint(KAMPALA.latitude + d, KAMPALA.longitude)
              for d in (0.05, 0.01, 0.03, 0.02, 0.04)]
    hits = NearbyService.order_by_distance(KAMPALA, points, 100_000.0,
                                           limit=2)
    assert len(hits) == 2
    assert hits[0].distance_m <= hits[1].distance_m
    full = NearbyService.order_by_distance(KAMPALA, points, 100_000.0)
    assert [h.distance_m for h in hits] == [h.distance_m for h in full[:2]]


@pytest.mark.parametrize("bad_limit", [0, -1, True])
def test_nearby_and_nearest_reject_bad_limit(bad_limit):
    with pytest.raises(ValidationError):
        NearbyService.order_by_distance(KAMPALA, [KAMPALA], 5_000.0,
                                        limit=bad_limit)
    with pytest.raises(ValidationError):
        NearbyService.nearest(KAMPALA, [KAMPALA], limit=bad_limit)


def test_nearby_keeps_duplicates_in_stable_order():
    twin = GeoPoint(0.3480, 32.5830)
    hits = NearbyService.order_by_distance(KAMPALA, [twin, twin], 5_000.0)
    assert len(hits) == 2
    assert hits[0].public_id == "0"
    assert hits[1].public_id == "1"


# --- nearest ---------------------------------------------------------------

def test_nearest_returns_closest_first_without_radius_gate():
    near = GeoPoint(0.3480, 32.5830)
    far = GeoPoint(1.0, 33.0)  # well beyond any small radius
    hits = NearbyService.nearest(KAMPALA, [far, near])
    assert len(hits) == 1
    assert hits[0].point == near


def test_nearest_limit_orders_by_distance():
    points = [GeoPoint(KAMPALA.latitude + d, KAMPALA.longitude)
              for d in (0.05, 0.01, 0.03)]
    hits = NearbyService.nearest(KAMPALA, points, limit=2)
    assert len(hits) == 2
    assert hits[0].distance_m <= hits[1].distance_m
    assert hits[0].point == points[1]


# --- bounding box -----------------------------------------------------------

def test_bounding_box_contains_center_and_matches_radius():
    radius_m = 10_000.0
    box = bounding_box(KAMPALA, radius_m)
    assert box["min_latitude"] < KAMPALA.latitude < box["max_latitude"]
    assert box["min_longitude"] < KAMPALA.longitude < box["max_longitude"]
    expected_dlat = math.degrees(radius_m / EARTH_RADIUS_M)
    assert (box["max_latitude"] - KAMPALA.latitude) == pytest.approx(
        expected_dlat, abs=1e-9)
    # box corners are farther than radius: box is a pre-filter, exact
    # membership still requires straight_line_distance_m
    corner = GeoPoint(box["max_latitude"], box["max_longitude"])
    assert straight_line_distance_m(KAMPALA, corner) > radius_m
    # edge midpoints are (approximately) on the circle
    edge = GeoPoint(box["max_latitude"], KAMPALA.longitude)
    assert straight_line_distance_m(KAMPALA, edge) == pytest.approx(
        radius_m, rel=1e-6)


def test_bounding_box_clamps_at_poles():
    north = GeoPoint(89.99, 0.0)
    box = bounding_box(north, 100_000.0)
    assert box["max_latitude"] == pytest.approx(90.0)
    assert box["min_latitude"] >= -90.0
    assert box["min_longitude"] >= -180.0
    assert box["max_longitude"] <= 180.0


def test_bounding_box_rejects_bad_radius():
    with pytest.raises(ValidationError):
        bounding_box(KAMPALA, 0)
    with pytest.raises(ValidationError):
        bounding_box(KAMPALA, -100)


# --- freshness edge cases ----------------------------------------------------

def test_freshness_timezone_naive_treated_as_utc():
    service = get_location_service()
    now = datetime.now(timezone.utc)
    naive_recent = GeoPoint(0.3, 32.5,
                            timestamp=now.replace(tzinfo=None)
                            - timedelta(seconds=10))
    assert service.check_freshness(naive_recent)["fresh"] is True
    naive_stale = GeoPoint(0.3, 32.5,
                           timestamp=now.replace(tzinfo=None)
                           - timedelta(hours=2))
    assert service.check_freshness(naive_stale)["fresh"] is False


def test_freshness_boundary_is_inclusive():
    service = get_location_service()
    now = datetime.now(timezone.utc)
    point = GeoPoint(0.3, 32.5, timestamp=now - timedelta(seconds=300))
    verdict = service.check_freshness(point, max_age_seconds=300, now=now)
    assert verdict["fresh"] is True
    assert verdict["age_s"] == pytest.approx(300.0, abs=1.0)


# --- consumer readiness (public interface only) ------------------------------

def test_consumer_flow_validate_distance_nearby_freshness():
    """Simulates a Transport/Accommodation developer flow using only the
    documented GEO entry points: no domain imports, no internals."""
    driver = normalize_point(0.3476, 32.5825)
    pickup = normalize_point("0.3510", "32.5900")
    dist_m = straight_line_distance_m(driver, pickup)
    assert dist_m > 0

    fleet = [normalize_point(0.3600, 32.6000), driver,
             normalize_point(0.3470, 32.5820)]
    hits = NearbyService.order_by_distance(pickup, fleet, 5_000.0, limit=3)
    assert hits  # at least the driver-adjacent points fall in radius
    assert all(h.distance_m <= 5_000.0 for h in hits)

    closest = NearbyService.nearest(pickup, fleet, limit=1)
    assert closest[0].distance_m == min(h.distance_m for h in hits
                                        if h.point in fleet)

    box = bounding_box(pickup, 5_000.0)
    assert box["min_latitude"] <= pickup.latitude <= box["max_latitude"]

    live = GeoPoint(driver.latitude, driver.longitude,
                    timestamp=datetime.now(timezone.utc))
    assert get_location_service().check_freshness(live)["fresh"] is True

    route = get_routing_service().route(driver, pickup)
    assert route.resolved is False  # no road provider: truthful miss
    assert get_geocoding_service().geocode("Kampala") == []
