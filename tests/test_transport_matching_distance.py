"""Transport matching distance — numerical regression contract (Node 5 / GEO-4).

Encodes the INTENDED numerical behavior of
MatchingService._calculate_distance (kilometres, haversine, radians-correct)
and its interaction with _rank_drivers_for_booking.

Pure dict-level tests: no DB, no Redis, no network required.

Pre-migration these contract tests FAIL on the defective degree-based
implementation (GEO-3) — the failure is the defect proof. Post-migration
(canonical GEO, metres → km bridge) they pass unchanged.
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest import mock

import pytest

from app.transport.services.matching_service import MatchingService


KAMPALA_PICKUP = {"latitude": 0.3476, "longitude": 32.5825}
ENTEBBE = {"latitude": 0.0515, "longitude": 32.4467}


def _booking(pickup):
    return SimpleNamespace(
        pickup_location=pickup,
        booking_metadata={},
        service_type=SimpleNamespace(value="ride"),
        passenger_count=1,
    )


def _driver(lat, lng, rating=4.5):
    return {
        "current_location": {"latitude": lat, "longitude": lng},
        "location_updated_at": (
            datetime.now(timezone.utc) - timedelta(seconds=10)).isoformat(),
        "vehicle_classes": ["standard"],
        "average_rating": rating,
        "acceptance_rate": 100,
        "service_types": ["ride"],
    }


# --- intended numerical contract -------------------------------------------

def test_identical_coordinates_give_zero():
    assert MatchingService._calculate_distance(
        KAMPALA_PICKUP, dict(KAMPALA_PICKUP)) == 0.0


def test_equatorial_degree_is_111km():
    dist = MatchingService._calculate_distance(
        {"latitude": 0.0, "longitude": 0.0},
        {"latitude": 0.0, "longitude": 1.0})
    assert dist == pytest.approx(111.195, abs=0.2)


def test_kampala_entebbe_corridor_km():
    """~36 km straight-line. The defective degree-based formula returns
    ~2067 km here, so this range cleanly discriminates correct behavior."""
    dist = MatchingService._calculate_distance(KAMPALA_PICKUP, ENTEBBE)
    assert dist == pytest.approx(36.2, abs=0.5)
    assert 30.0 < dist < 42.0


def test_southern_hemisphere_negative_longitude():
    # Sao Paulo -> Rio de Janeiro, known reference ~361 km.
    dist = MatchingService._calculate_distance(
        {"latitude": -23.5505, "longitude": -46.6333},
        {"latitude": -22.9068, "longitude": -43.1729})
    assert dist == pytest.approx(360.7, abs=1.0)


def test_antimeridian_crossing():
    dist = MatchingService._calculate_distance(
        {"latitude": 0.0, "longitude": 179.9},
        {"latitude": 0.0, "longitude": -179.9})
    assert dist == pytest.approx(22.2, abs=0.5)


# --- null / invalid handling (preserved across migration) -------------------

@pytest.mark.parametrize("bad_location", [
    {},
    {"latitude": 0.3},
    {"longitude": 32.5},
    {"latitude": None, "longitude": 32.5},
    {"latitude": 91.0, "longitude": 32.5},      # out of range
    {"latitude": 0.3, "longitude": 181.0},      # out of range
    {"latitude": "abc", "longitude": 32.5},     # non-numeric
])
def test_invalid_locations_return_none(bad_location):
    assert MatchingService._calculate_distance(
        bad_location, KAMPALA_PICKUP) is None
    assert MatchingService._calculate_distance(
        KAMPALA_PICKUP, bad_location) is None


# --- ranking interaction -----------------------------------------------------

def test_close_driver_outranks_far_driver_on_proximity():
    """Same ratings; ~1 km driver must beat ~12 km driver. Pre-migration
    both get +0 proximity (buggy distances exceed every band) so ranking
    degrades to a pool-order tie — this test fails until migration."""
    close = _driver(0.3566, 32.5825)   # ~1 km north of pickup
    far = _driver(0.4556, 32.5825)     # ~12 km north of pickup
    ranked = MatchingService._rank_drivers_for_booking(
        drivers=[far, close], booking=_booking(KAMPALA_PICKUP))
    assert [d["current_location"] for d in ranked] == [
        close["current_location"], far["current_location"]]
    assert ranked[0]["match_score"] > ranked[1]["match_score"]
    assert ranked[0]["estimated_arrival_time"] < ranked[1][
        "estimated_arrival_time"]


def test_stale_or_invalid_location_excluded_before_scoring():
    stale = _driver(0.3477, 32.5826)
    stale["location_updated_at"] = (
        datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    no_coords = _driver(0.3477, 32.5826)
    no_coords["current_location"] = {"latitude": None, "longitude": None}
    ranked = MatchingService._rank_drivers_for_booking(
        drivers=[stale, no_coords], booking=_booking(KAMPALA_PICKUP))
    assert ranked == []


# --- canonical-GEO wiring proof (§6 verification) ----------------------------

def test_calculate_distance_delegates_to_canonical_geo():
    """Production path must call GEO straight_line_distance_m (metres) and
    bridge to Transport's kilometre contract. Errors pre-migration."""
    with mock.patch(
            "app.transport.services.matching_service."
            "straight_line_distance_m") as geo_distance:
        geo_distance.return_value = 5_000.0
        result = MatchingService._calculate_distance(
            KAMPALA_PICKUP, ENTEBBE)
    assert geo_distance.call_count == 1
    (origin, dest), _ = geo_distance.call_args
    assert (origin.latitude, origin.longitude) == (0.3476, 32.5825)
    assert (dest.latitude, dest.longitude) == (0.0515, 32.4467)
    assert result == pytest.approx(5.0)  # metres -> km bridge
