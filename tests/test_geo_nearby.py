"""AFCON360 roadmap GEO-16 Nearby / Spatial Discovery - contract tests.

Pins the domain-neutral proximity primitives that domains consume
(Accommodation radius search, Transport nearby/matching): bounding box
pre-filter math, deterministic nearest/ordering, straight-line matrix
semantics, radius guards, and truthful empty results.

Lat-first order is pinned with asymmetric points so a swap fails
loudly. Straight-line results are never road distance/ETA/fare - the
naming contract (`straight_line_*`) is asserted on the public API.
"""

import math

import pytest

from app.geo.interfaces import GeoPoint
from app.geo.services import (
    EARTH_RADIUS_M,
    NearbyService,
    bounding_box,
    straight_line_distance_m,
    straight_line_distance_matrix_m,
)
from app.utils.exceptions import ValidationError

KAMPALA = GeoPoint(0.3136, 32.5811)  # asymmetric (swap-detecting)


# --- bounding_box -------------------------------------------------------------

def test_box_contains_center_symmetrically_at_equator():
    center = GeoPoint(0.0, 30.0)
    box = bounding_box(center, 1000)
    expected_deg = math.degrees(1000 / EARTH_RADIUS_M)
    assert box["min_latitude"] == pytest.approx(-expected_deg, abs=1e-9)
    assert box["max_latitude"] == pytest.approx(expected_deg, abs=1e-9)
    # Longitude degrees scale with latitude; at the equator they match.
    assert box["min_longitude"] == pytest.approx(30.0 - expected_deg, abs=1e-9)
    assert box["max_longitude"] == pytest.approx(30.0 + expected_deg, abs=1e-9)


def test_box_latitude_first_not_swapped():
    box = bounding_box(KAMPALA, 5000)
    assert box["min_latitude"] < KAMPALA.latitude < box["max_latitude"]
    assert box["min_longitude"] < KAMPALA.longitude < box["max_longitude"]
    # Latitude span for 5 km must be ~0.045 deg, nowhere near
    # longitude-span confusion with the 32.58 absolute value.
    span = box["max_latitude"] - box["min_latitude"]
    assert span == pytest.approx(2 * math.degrees(5000 / EARTH_RADIUS_M),
                                 abs=1e-9)


def test_box_corners_are_farther_than_radius():
    """Box is a pre-filter only: corners exceed the radius, so exact
    membership still requires straight_line_distance_m."""
    box = bounding_box(KAMPALA, 2000)
    corner = GeoPoint(box["max_latitude"], box["max_longitude"])
    assert straight_line_distance_m(KAMPALA, corner) > 2000


def test_box_clamps_at_poles_and_antimeridian():
    polar = bounding_box(GeoPoint(89.999, 0.0), 100_000)
    assert polar["max_latitude"] == 90.0
    assert polar["min_latitude"] >= -90.0
    dateline = bounding_box(GeoPoint(0.0, 179.999), 100_000)
    assert dateline["max_longitude"] == 180.0
    assert dateline["min_longitude"] >= -180.0


@pytest.mark.parametrize("bad", [0, -5, 100_001, "far", None, True])
def test_box_rejects_invalid_radius(bad):
    with pytest.raises(ValidationError):
        bounding_box(KAMPALA, bad)


def test_box_accepts_max_radius_boundary():
    box = bounding_box(KAMPALA, 100_000)
    assert box["min_latitude"] < box["max_latitude"]


# --- NearbyService.nearest ----------------------------------------------------

def test_nearest_is_deterministic_closest_first():
    far = GeoPoint(1.0, 32.0)
    near = GeoPoint(0.32, 32.58)
    hits = NearbyService.nearest(KAMPALA, [far, near])
    assert len(hits) == 1
    assert hits[0].point == near
    assert hits[0].distance_m == pytest.approx(
        straight_line_distance_m(KAMPALA, near))


def test_nearest_limit_and_tie_stability():
    a = GeoPoint(0.32, 32.58)
    b = GeoPoint(0.32, 32.58)  # identical: tie keeps input order
    hits = NearbyService.nearest(KAMPALA, [a, b], limit=2)
    assert [h.public_id for h in hits] == ["0", "1"]
    assert hits[0].distance_m == hits[1].distance_m


def test_nearest_empty_is_truthful():
    assert NearbyService.nearest(KAMPALA, []) == []


@pytest.mark.parametrize("bad", [0, -1, "2", 2.5, True, None])
def test_nearest_rejects_bad_limit(bad):
    with pytest.raises(ValidationError):
        NearbyService.nearest(KAMPALA, [KAMPALA], limit=bad)


# --- NearbyService.order_by_distance ------------------------------------------

def test_ordering_boundary_inclusive_and_stable():
    p = GeoPoint(0.32, 32.58)
    dist = straight_line_distance_m(KAMPALA, p)
    hits = NearbyService.order_by_distance(KAMPALA, [p, p], dist)
    assert [h.public_id for h in hits] == ["0", "1"]  # inclusive + stable
    assert NearbyService.order_by_distance(KAMPALA, [p], dist - 1.0) == []


def test_ordering_empty_is_truthful():
    assert NearbyService.order_by_distance(KAMPALA, [], 5000) == []


# --- matrix --------------------------------------------------------------------

def test_matrix_shape_symmetry_and_diagonal():
    pts = [KAMPALA, GeoPoint(0.32, 32.58), GeoPoint(-0.1, 33.0)]
    mat = straight_line_distance_matrix_m(pts, pts)
    assert len(mat) == 3 and all(len(row) == 3 for row in mat)
    for i in range(3):
        assert mat[i][i] == pytest.approx(0.0, abs=1e-9)
        for j in range(3):
            assert mat[i][j] == pytest.approx(mat[j][i])
            assert mat[i][j] == pytest.approx(
                straight_line_distance_m(pts[i], pts[j]))


def test_matrix_rectangular_shape():
    mat = straight_line_distance_matrix_m([KAMPALA], [KAMPALA, KAMPALA])
    assert len(mat) == 1 and len(mat[0]) == 2


# --- naming contract ------------------------------------------------------------

def test_public_api_names_distance_honestly():
    import app.geo.services as svc

    assert callable(svc.straight_line_distance_m)
    assert callable(svc.straight_line_distance_matrix_m)
    assert not hasattr(svc, "distance_m")  # no bare ambiguous helper
    assert not hasattr(svc, "road_distance_m")
