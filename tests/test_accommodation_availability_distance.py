"""Accommodation availability distance — regression contract (Node 6B / GEO-7).

Encodes the INTENDED contract of
AvailabilityService._nearby_distance_km (kilometres, haversine,
radians-correct, 1-decimal rounding) as used by find_nearby_alternatives
Tier-2 fallback suggestions ("{distance}km away").

Pure tests: no DB, no Redis, no network. The helper is exercised
directly — it is the real production calculation path, extracted
verbatim so the contract is pinned before the GEO migration.
"""

from unittest import mock

import pytest

from app.accommodation.services.availability_service import (
    AvailabilityService,
)


# --- intended numerical contract -------------------------------------------

def test_identical_coordinates_give_zero():
    assert AvailabilityService._nearby_distance_km(
        0.3476, 32.5825, 0.3476, 32.5825) == 0.0


def test_equatorial_degree_km_rounded():
    assert AvailabilityService._nearby_distance_km(
        0.0, 0.0, 0.0, 1.0) == pytest.approx(111.2, abs=0.05)


def test_kampala_entebbe_corridor_km():
    """~36.2 km. A degree-based (radians-missing) implementation returns
    ~2067 here, so this range cleanly discriminates correct behavior."""
    dist = AvailabilityService._nearby_distance_km(
        0.3476, 32.5825, 0.0515, 32.4467)
    assert dist == pytest.approx(36.2, abs=0.05)
    assert 30.0 < dist < 42.0


def test_southern_hemisphere_negative_longitude():
    # Sao Paulo -> Rio de Janeiro, known reference ~360.7 km.
    assert AvailabilityService._nearby_distance_km(
        -23.5505, -46.6333, -22.9068, -43.1729) == pytest.approx(
            360.7, abs=0.05)


def test_antimeridian_crossing():
    assert AvailabilityService._nearby_distance_km(
        0.0, 179.9, 0.0, -179.9) == pytest.approx(22.2, abs=0.05)


def test_result_is_rounded_to_one_decimal():
    # 1° at the equator carries a 2nd decimal (111.19...); the contract
    # rounds for display ("{distance}km away").
    dist = AvailabilityService._nearby_distance_km(0.0, 0.0, 0.0, 1.0)
    assert dist == round(dist, 1)


def test_radians_defect_sensitivity():
    """Guards the Transport-class defect: degrees passed straight into
    trig functions inflate Kampala–Entebbe ~57x. The contract must stay
    two orders of magnitude below the defective value."""
    dist = AvailabilityService._nearby_distance_km(
        0.3476, 32.5825, 0.0515, 32.4467)
    assert dist < 100.0


# --- canonical-GEO wiring proof (post-migration) ----------------------------

def test_nearby_distance_delegates_to_canonical_geo():
    """Production helper must call GEO straight_line_distance_m (metres)
    and bridge to the kilometre/1-decimal result contract. Errors until
    the helper body is migrated to canonical GEO."""
    with mock.patch(
            "app.accommodation.services.availability_service."
            "straight_line_distance_m") as geo_distance:
        geo_distance.return_value = 36_220.0
        result = AvailabilityService._nearby_distance_km(
            0.3476, 32.5825, 0.0515, 32.4467)
    assert geo_distance.call_count == 1
    (origin, dest), _ = geo_distance.call_args
    assert (origin.latitude, origin.longitude) == (0.3476, 32.5825)
    assert (dest.latitude, dest.longitude) == (0.0515, 32.4467)
    assert result == pytest.approx(36.2)  # metres -> km, 1-decimal bridge
