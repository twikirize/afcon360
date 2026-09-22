"""Transport tracking distance/freshness — regression contract (GEO-5).

Encodes the INTENDED contracts of TrackingService._calculate_distance
(kilometres, haversine, radians-correct) and the 300 s freshness boundary
shared with canonical GEO.

Pure tests: no DB, no Redis, no network. _calculate_distance is exercised
directly — it is the real production computation used by track_booking
(ETA) and get_nearby_drivers (filter/sort).
"""

from datetime import datetime, timedelta, timezone
from unittest import mock

import pytest

from app.geo.services import LOCATION_TTL_SECONDS as GEO_TTL
from app.geo.validation import is_fresh
from app.geo.interfaces import GeoPoint
from app.transport.services.tracking_service import TrackingService


KAMPALA = {"latitude": 0.3476, "longitude": 32.5825}
ENTEBBE = {"latitude": 0.0515, "longitude": 32.4467}


# --- intended numerical contract -------------------------------------------

def test_identical_coordinates_give_zero():
    assert TrackingService._calculate_distance(
        KAMPALA, dict(KAMPALA)) == 0.0


def test_equatorial_degree_is_km_not_metres():
    """111.195 km proves the kilometre contract (GEO speaks metres)."""
    dist = TrackingService._calculate_distance(
        {"latitude": 0.0, "longitude": 0.0},
        {"latitude": 0.0, "longitude": 1.0})
    assert dist == pytest.approx(111.195, abs=0.2)


def test_kampala_entebbe_corridor_km():
    """~36.2 km. A degree-based (radians-missing) implementation returns
    ~2067 here, so this range cleanly discriminates correct behavior."""
    dist = TrackingService._calculate_distance(KAMPALA, ENTEBBE)
    assert dist == pytest.approx(36.2, abs=0.5)
    assert 30.0 < dist < 42.0


def test_southern_hemisphere_negative_longitude():
    # Sao Paulo -> Rio de Janeiro, known reference ~360.7 km.
    dist = TrackingService._calculate_distance(
        {"latitude": -23.5505, "longitude": -46.6333},
        {"latitude": -22.9068, "longitude": -43.1729})
    assert dist == pytest.approx(360.7, abs=1.0)


def test_antimeridian_crossing():
    dist = TrackingService._calculate_distance(
        {"latitude": 0.0, "longitude": 179.9},
        {"latitude": 0.0, "longitude": -179.9})
    assert dist == pytest.approx(22.2, abs=0.5)


@pytest.mark.parametrize("bad_location", [
    {},
    {"latitude": 0.3},
    {"longitude": 32.5},
    {"latitude": None, "longitude": 32.5},
    {"latitude": 91.0, "longitude": 32.5},
    {"latitude": 0.3, "longitude": 181.0},
    {"latitude": "abc", "longitude": 32.5},
])
def test_invalid_locations_return_none(bad_location):
    assert TrackingService._calculate_distance(
        bad_location, KAMPALA) is None
    assert TrackingService._calculate_distance(
        KAMPALA, bad_location) is None


# --- freshness contract (threshold + boundary semantics) ---------------------

def test_freshness_threshold_matches_geo_canonical():
    """Transport's 300 s boundary and GEO's LOCATION_TTL_SECONDS must stay
    aligned — the consolidation assumes one shared freshness horizon."""
    assert TrackingService.LOCATION_TTL_SECONDS == 300
    assert TrackingService.LOCATION_TTL_SECONDS == GEO_TTL


def test_freshness_boundary_semantics_agree_with_geo():
    """Production rule (`updated_at < now - 300s → stale`) and GEO is_fresh
    agree: exactly-at-boundary counts as fresh on both sides."""
    now = datetime.now(timezone.utc)
    at_boundary = GeoPoint(0.3, 32.5, timestamp=now - timedelta(seconds=300))
    assert is_fresh(at_boundary, 300, now=now) is True
    just_stale = GeoPoint(0.3, 32.5, timestamp=now - timedelta(seconds=301))
    assert is_fresh(just_stale, 300, now=now) is False
    # Mirror of the production rule (`updated_at < cutoff → stale`):
    # exactly-at-boundary is fresh on both sides.
    cutoff = now - timedelta(seconds=300)
    assert not ((now - timedelta(seconds=300)) < cutoff)
    assert (now - timedelta(seconds=301)) < cutoff


# --- canonical-GEO wiring proof (post-migration) ------------------------------

def test_calculate_distance_delegates_to_canonical_geo():
    """Production path must call GEO straight_line_distance_m (metres) and
    bridge to Transport's kilometre contract. Errors pre-migration."""
    with mock.patch(
            "app.transport.services.tracking_service."
            "straight_line_distance_m") as geo_distance:
        geo_distance.return_value = 36_220.0
        result = TrackingService._calculate_distance(KAMPALA, ENTEBBE)
    assert geo_distance.call_count == 1
    (origin, dest), _ = geo_distance.call_args
    assert (origin.latitude, origin.longitude) == (0.3476, 32.5825)
    assert (dest.latitude, dest.longitude) == (0.0515, 32.4467)
    assert result == pytest.approx(36.22)  # metres -> km bridge
