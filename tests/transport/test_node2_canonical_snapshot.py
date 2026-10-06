"""Node 2 - Canonical Location Snapshot tests (correction pass).

Verifies the canonical location snapshot against the RATIFIED Node 1
contract (docs/transport/nodes/NODE-1-canonical-location-contract.md):

- 02A safety: raw coordinates validated before float() conversion
  (bool/NaN/Inf rejected, never laundered);
- identity_status vocabulary exactly none | unverified | enriched |
  verified (no `synthetic`);
- no top-level `place_ref` (provenance.reference is the sole reference);
- closed source set + enforced source/method pairings, no coercion;
- GPS stays GPS; unresolved typed text never becomes search;
- label required and non-null; display_name nullable ("" -> None);
- identity_status=none reachable for GPS/map points without identity;
- no presentation-only `address` key in new canonical snapshots.
"""
from datetime import datetime, timezone

import pytest

from app.geo.interfaces import GeocodeResult
from app.transport.services.location_snapshot import (
    build_canonical_location_snapshot,
    build_canonical_snapshot_from_coordinates,
    build_canonical_snapshot_from_geocode_result,
    get_display_text,
    get_coordinates,
    is_resolved_snapshot,
    legacy_location_text,
    validate_source_method,
    IDENTITY_NONE,
    IDENTITY_UNVERIFIED,
    IDENTITY_ENRICHED,
    IDENTITY_VERIFIED,
    VALID_IDENTITY_STATUSES,
)


def _search_result(**over):
    base = {
        "latitude": 0.3150,
        "longitude": 32.5820,
        "display_name": "Nile Stadium, Kampala",
        "raw": {"osm_type": "N", "osm_id": "9626381835", "city": "Kampala"},
        "provider": "photon",
        "resolved": True,
    }
    base.update(over)
    return GeocodeResult(**base)


# --- coordinates path: map pin with explicit address -----------------------

def test_build_snapshot_from_coordinates():
    """Snapshot from raw coordinates (map pin) with explicit address."""
    snap = build_canonical_snapshot_from_coordinates(
        0.3150, 32.5820,
        explicit_address="Nile Stadium",
        accuracy_m=10.0,
    )
    assert snap["latitude"] == pytest.approx(0.3150)
    assert snap["longitude"] == pytest.approx(32.5820)
    assert snap["source"] == "map"
    assert snap["resolution_method"] == "map_pin"
    assert snap["provenance"] is None
    assert snap["label"] == "Nile Stadium"
    # Explicit address is label only: no provider identity exists.
    assert snap["display_name"] is None
    assert snap["identity_status"] == IDENTITY_NONE
    assert snap["accuracy_m"] == 10.0
    assert snap["confidence"] is None
    assert snap["area"] is None
    assert "place_ref" not in snap
    assert "address" not in snap
    assert "resolved_at" in snap
    assert snap["observed_at"] is None


def test_build_snapshot_from_coordinates_no_address():
    """Snapshot from coordinates only: label defaults honestly, no identity."""
    snap = build_canonical_snapshot_from_coordinates(0.3150, 32.5820)
    # label is required and non-null: honest input-path default.
    assert isinstance(snap["label"], str) and snap["label"]
    assert snap["display_name"] is None
    assert snap["identity_status"] == IDENTITY_NONE


def test_gps_stays_gps():
    """GPS-originated locations keep source=gps / browser_geolocation."""
    snap = build_canonical_snapshot_from_coordinates(
        0.3150, 32.5820,
        source="gps",
        resolution_method="browser_geolocation",
    )
    assert snap["source"] == "gps"
    assert snap["resolution_method"] == "browser_geolocation"
    assert snap["identity_status"] == IDENTITY_NONE
    assert snap["display_name"] is None
    assert snap["provenance"] is None
    assert isinstance(snap["label"], str) and snap["label"]


def test_map_stays_map():
    """Map pins are never reclassified as GPS or search."""
    snap = build_canonical_snapshot_from_coordinates(
        0.3150, 32.5820,
        source="map",
        resolution_method="map_pin",
    )
    assert snap["source"] == "map"
    assert snap["resolution_method"] == "map_pin"


# --- 02A safety: raw-before-float ------------------------------------------

def test_coordinates_reject_bool_nan_inf():
    """bool/NaN/Inf raw values are rejected before float() conversion."""
    from app.utils.exceptions import ValidationError
    for bad_lat, bad_lng in [
        (True, 32.5820), (0.3150, False),
        (float("nan"), 32.5820), (0.3150, float("nan")),
        (float("inf"), 32.5820), (0.3150, float("-inf")),
        ("nan", 32.5820), (0.3150, "Infinity"),
        (None, 32.5820), (0.3150, None),
        ("abc", 32.5820), (999.0, 32.5820),
    ]:
        with pytest.raises((ValidationError, ValueError, TypeError)):
            build_canonical_snapshot_from_coordinates(bad_lat, bad_lng)


def test_dict_payload_rejects_bool_coordinates():
    """Dict payloads with bool coordinates are rejected, not laundered."""
    from app.utils.exceptions import ValidationError
    with pytest.raises((ValidationError, ValueError)):
        build_canonical_location_snapshot(
            location_payload={"latitude": True, "longitude": 32.5820},
        )


# --- source/method pairing + closed vocab ----------------------------------

@pytest.mark.parametrize("source,method", [
    ("gps", "browser_geolocation"),
    ("map", "map_pin"),
    ("search", "forward_geocode"),
    ("curated", "registry_lookup"),
])
def test_valid_source_method_pairs_accepted(source, method):
    validate_source_method(source, method)


@pytest.mark.parametrize("source,method", [
    ("gps", "map_pin"),
    ("map", "forward_geocode"),
    ("search", "map_pin"),
    ("curated", "browser_geolocation"),
    ("map", "browser_geolocation"),
    ("gps", "forward_geocode"),
])
def test_invalid_source_method_pairs_rejected(source, method):
    with pytest.raises(ValueError):
        validate_source_method(source, method)
    with pytest.raises(ValueError):
        build_canonical_snapshot_from_coordinates(
            0.3150, 32.5820, source=source, resolution_method=method
        )


@pytest.mark.parametrize("bad_source", ["manual", "typing", "auto", "", "GPS"])
def test_closed_source_set_rejects(bad_source):
    with pytest.raises(ValueError):
        validate_source_method(bad_source, "map_pin")
    with pytest.raises(ValueError):
        build_canonical_snapshot_from_coordinates(
            0.3150, 32.5820, source=bad_source, resolution_method="map_pin"
        )


def test_invalid_pairing_in_payload_hint_rejected():
    """An invalid source hint inside the payload is rejected, not coerced."""
    with pytest.raises(ValueError):
        build_canonical_location_snapshot(
            location_payload={
                "latitude": 0.3150,
                "longitude": 32.5820,
                "source": "gps",
                "resolution_method": "map_pin",
            },
        )


def test_payload_gps_hint_honored():
    """An explicit valid GPS hint in the payload stays GPS."""
    snap = build_canonical_location_snapshot(
        location_payload={
            "latitude": 0.3150,
            "longitude": 32.5820,
            "source": "gps",
            "resolution_method": "browser_geolocation",
        },
    )
    assert snap["source"] == "gps"
    assert snap["resolution_method"] == "browser_geolocation"
    assert snap["identity_status"] == IDENTITY_NONE
    assert snap["display_name"] is None


# --- unresolved typed text is never search ----------------------------------

def test_unresolved_typed_text_has_no_snapshot():
    """Typed text without explicit selection is not search/forward_geocode."""
    with pytest.raises(ValueError):
        build_canonical_location_snapshot(
            location_payload="Nile Stadium, Kampala",
        )
    with pytest.raises(ValueError):
        build_canonical_location_snapshot(
            location_payload="Nile Stadium, Kampala",
            explicit_address="Nile Stadium, Kampala",
        )


def test_unresolved_geocode_result_has_no_snapshot():
    with pytest.raises(ValueError):
        build_canonical_location_snapshot(
            location_payload="Nile Stadium, Kampala",
            geocode_result=GeocodeResult(resolved=False),
        )


# --- search / curated paths -------------------------------------------------

def test_search_selected_identity():
    """Explicitly selected search candidate: unverified + provenance."""
    snap = build_canonical_location_snapshot(
        location_payload={"latitude": 0.3150, "longitude": 32.5820},
        geocode_result=_search_result(),
        explicit_address="Nile Stadium",
    )
    assert snap["source"] == "search"
    assert snap["resolution_method"] == "forward_geocode"
    assert snap["identity_status"] == IDENTITY_UNVERIFIED
    assert snap["display_name"] == "Nile Stadium, Kampala"
    assert snap["label"] == "Nile Stadium"
    assert snap["provenance"] == {
        "authority": "photon", "reference": "N/9626381835"
    }
    assert snap["area"] == "Kampala"
    assert "place_ref" not in snap
    assert "address" not in snap


def test_search_label_falls_back_to_display_name():
    """Without explicit text, the selected search text is the label."""
    snap = build_canonical_snapshot_from_geocode_result(_search_result())
    assert snap["source"] == "search"
    assert snap["label"] == "Nile Stadium, Kampala"
    assert snap["display_name"] == "Nile Stadium, Kampala"


def test_search_cannot_be_claimed_as_gps():
    """A resolved provider result cannot be relabeled gps/map."""
    with pytest.raises(ValueError):
        build_canonical_location_snapshot(
            location_payload={"latitude": 0.3150, "longitude": 32.5820},
            geocode_result=_search_result(),
            source="gps",
            resolution_method="browser_geolocation",
        )


def test_curated_registry_identity_verified():
    result = _search_result(
        provider="curated-registry",
        raw={"city": "Kampala"},
        display_name="Nile Stadium (Verified)",
    )
    snap = build_canonical_snapshot_from_geocode_result(result)
    assert snap["source"] == "curated"
    assert snap["resolution_method"] == "registry_lookup"
    assert snap["identity_status"] == IDENTITY_VERIFIED
    assert snap["provenance"]["authority"] == "curated-registry"


def test_provenance_never_fabricated():
    """GPS/map snapshots carry provenance=None; provider raw is not copied."""
    snap = build_canonical_snapshot_from_coordinates(0.3150, 32.5820)
    assert snap["provenance"] is None
    result = _search_result(provider="photon", raw={})
    snap = build_canonical_snapshot_from_geocode_result(result)
    assert snap["provenance"] == {"authority": "photon", "reference": None}
    assert "osm_type" not in str(snap)


def test_display_name_empty_string_normalizes_to_none():
    result = _search_result(display_name="   ")
    snap = build_canonical_snapshot_from_geocode_result(result)
    assert snap["display_name"] is None


def test_unresolved_geocode_result_rejected():
    with pytest.raises(ValueError):
        build_canonical_snapshot_from_geocode_result(
            GeocodeResult(resolved=False)
        )


# --- label is required and non-null -----------------------------------------

def test_label_never_none():
    """Every builder emits a non-null string label."""
    snaps = [
        build_canonical_snapshot_from_coordinates(0.3150, 32.5820),
        build_canonical_snapshot_from_coordinates(
            0.3150, 32.5820, source="gps",
            resolution_method="browser_geolocation"),
        build_canonical_location_snapshot(
            location_payload={"latitude": 0.3150, "longitude": 32.5820}),
        build_canonical_snapshot_from_geocode_result(_search_result()),
    ]
    for snap in snaps:
        assert isinstance(snap["label"], str) and snap["label"].strip()


# --- display text ------------------------------------------------------------

def test_display_text_with_display_name():
    """get_display_text returns display_name when available."""
    snap = {
        "display_name": "Kampala Serena",
        "identity_status": IDENTITY_UNVERIFIED,
        "label": "Kampala Serena",
        "latitude": 0.3476,
        "longitude": 32.5825,
    }
    assert get_display_text(snap) == "Kampala Serena"


def test_display_text_label_fallback():
    """Without display_name, the input-associated label is shown."""
    snap = {
        "display_name": None,
        "identity_status": IDENTITY_NONE,
        "label": "Pinned location",
        "latitude": 0.3150,
        "longitude": 32.5820,
    }
    assert get_display_text(snap) == "Pinned location"


def test_display_text_none_identity():
    """None identity without label shows honest fallback."""
    snap = {
        "display_name": None,
        "identity_status": IDENTITY_NONE,
        "label": None,
        "latitude": 0.3150,
        "longitude": 32.5820,
    }
    assert get_display_text(snap) == "Location to be confirmed"


def test_display_text_unverified():
    """Unverified identity shows honest fallback."""
    snap = {
        "display_name": None,
        "identity_status": IDENTITY_UNVERIFIED,
        "label": None,
        "latitude": 0.3150,
        "longitude": 32.5820,
    }
    assert get_display_text(snap) == "Unverified location"


def test_display_text_enriched():
    """Enriched identity shows honest fallback."""
    snap = {
        "display_name": None,
        "identity_status": IDENTITY_ENRICHED,
        "label": None,
        "latitude": 0.3150,
        "longitude": 32.5820,
    }
    assert get_display_text(snap) == "Enriched location"


def test_display_text_verified():
    """Verified identity shows honest fallback."""
    snap = {
        "display_name": None,
        "identity_status": IDENTITY_VERIFIED,
        "label": None,
        "latitude": 0.3150,
        "longitude": 32.5820,
    }
    assert get_display_text(snap) == "Verified location"


def test_get_coordinates():
    """Extract authoritative coordinates from snapshot."""
    snap = {"latitude": 0.3150, "longitude": 32.5820}
    lat, lng = get_coordinates(snap)
    assert lat == pytest.approx(0.3150)
    assert lng == pytest.approx(32.5820)

    # Missing coords
    snap = {"latitude": None, "longitude": 32.5820}
    lat, lng = get_coordinates(snap)
    assert lat is None
    assert lng is None

    # Bool coordinates are never coordinates
    snap = {"latitude": True, "longitude": 32.5820}
    assert get_coordinates(snap) == (None, None)


def test_is_resolved_snapshot():
    """Detect canonical resolved snapshot vs legacy."""
    assert is_resolved_snapshot({"latitude": 0.3150, "longitude": 32.5820}) is True
    assert is_resolved_snapshot({"address": "Kampala"}) is False
    assert is_resolved_snapshot("Kampala") is False
    assert is_resolved_snapshot(None) is False
    assert is_resolved_snapshot({}) is False


def test_legacy_location_text():
    """Legacy compatibility for old string/dict rows."""
    assert legacy_location_text("Kampala") == "Kampala"
    assert legacy_location_text({"address": "Nile Stadium"}) == "Nile Stadium"
    assert legacy_location_text({"name": "Venue"}) == "Venue"
    assert legacy_location_text({"label": "Pin"}) == "Pin"
    assert legacy_location_text({"latitude": 0.3150, "longitude": 32.5820}) == "0.3150, 32.5820"
    assert legacy_location_text(None) is None
    assert legacy_location_text("") is None


def test_full_canonical_snapshot_roundtrip():
    """Verify all Node 1 contract fields are present in snapshot."""
    snap = build_canonical_snapshot_from_coordinates(
        0.3150, 32.5820,
        explicit_address="Nile Stadium",
        observed_at=datetime.now(timezone.utc),
        accuracy_m=15.0,
    )

    # Geographic truth
    assert "latitude" in snap
    assert "longitude" in snap

    # Input path
    assert "source" in snap
    assert "resolution_method" in snap

    # Provenance
    assert "provenance" in snap

    # Human identity
    assert "label" in snap
    assert "display_name" in snap
    assert "identity_status" in snap
    assert "area" in snap

    # Quality
    assert "accuracy_m" in snap
    assert "confidence" in snap

    # Time
    assert "observed_at" in snap
    assert "resolved_at" in snap

    # Forbidden keys: no duplicate reference, no presentation address,
    # no resolution booleans, no fifth identity state.
    for forbidden in ("place_ref", "address", "coordinates_resolved",
                      "identity_resolved", "synthetic"):
        assert forbidden not in snap
        assert forbidden not in str(snap.values())

    # All values are correct types
    assert isinstance(snap["latitude"], float)
    assert isinstance(snap["longitude"], float)
    assert isinstance(snap["source"], str)
    assert isinstance(snap["resolution_method"], str)
    assert snap["provenance"] is None or isinstance(snap["provenance"], dict)
    assert isinstance(snap["label"], str)
    assert snap["display_name"] is None or isinstance(snap["display_name"], str)
    assert snap["identity_status"] in VALID_IDENTITY_STATUSES
    assert snap["area"] is None or isinstance(snap["area"], str)
    assert snap["accuracy_m"] is None or isinstance(snap["accuracy_m"], float)
    assert snap["confidence"] is None or isinstance(snap["confidence"], float)
    assert snap["observed_at"] is None or isinstance(snap["observed_at"], str)
    assert isinstance(snap["resolved_at"], str)


def test_identity_status_vocabulary():
    """Verify Node 1 identity status vocabulary is exact."""
    assert VALID_IDENTITY_STATUSES == {
        IDENTITY_NONE,
        IDENTITY_UNVERIFIED,
        IDENTITY_ENRICHED,
        IDENTITY_VERIFIED,
    }
    # No "unresolved", "synthetic", "coordinates_resolved", "identity_resolved"
    assert "unresolved" not in VALID_IDENTITY_STATUSES
    assert "synthetic" not in VALID_IDENTITY_STATUSES
    assert "coordinates_resolved" not in VALID_IDENTITY_STATUSES
    assert "identity_resolved" not in VALID_IDENTITY_STATUSES


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
