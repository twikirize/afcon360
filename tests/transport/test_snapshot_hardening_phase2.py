"""Snapshot Hardening (Phase 2) — H1 / H2 / H3 proofs under the adopted Base B.

Evidence produced for the panel's CLEAN BASE ADOPTION order. These are the
invariants the corrected ``app/transport/services/location_snapshot.py``
must hold once the Base-A persistence/label compensations were removed:

* H1 — when the payload and a resolved ``GeocodeResult`` both carry
  coordinates, they must be *exactly* equal. Any disagreement, including
  sub-micro drift, is rejected. No tolerance is invented here or anywhere.
* H2 — direct-coordinate construction may claim only ``gps`` / ``map``.
  A ``search`` / ``curated`` claim with no resolved provider evidence is
  rejected, and a resolved provider result yields ``search`` +
  ``unverified`` (or ``curated`` + ``verified`` for a curated registry).
* H3 — ``accuracy_m`` / ``confidence`` are finite when supplied; nothing
  non-finite is ever persisted.
* Persistence — the builder's output is JSONB-safe as returned: ISO-8601
  *strings* for ``observed_at`` / ``resolved_at``, 13 keys, no datetime
  objects. No caller-side normalization exists any more.
"""

import json
import math
from datetime import datetime, timezone

import pytest

from app.geo.interfaces import GeocodeResult
from app.transport.services.location_snapshot import (
    IDENTITY_UNVERIFIED,
    IDENTITY_VERIFIED,
    build_canonical_location_snapshot,
    build_canonical_snapshot_from_coordinates,
    build_canonical_snapshot_from_geocode_result,
)

CANONICAL_KEYS = {
    "latitude", "longitude", "source", "resolution_method", "provenance",
    "label", "display_name", "identity_status", "area", "accuracy_m",
    "confidence", "observed_at", "resolved_at",
}


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


# --- H1: exact agreement only -------------------------------------------------

def test_h1_exact_coordinate_agreement_accepted():
    snap = build_canonical_location_snapshot(
        location_payload={"latitude": 0.3150, "longitude": 32.5820},
        geocode_result=_search_result(latitude=0.3150, longitude=32.5820),
        explicit_address="Nile Stadium",
    )
    assert snap["latitude"] == 0.3150
    assert snap["longitude"] == 32.5820


def test_h1_conflicting_coordinates_rejected():
    with pytest.raises(ValueError) as exc:
        build_canonical_location_snapshot(
            location_payload={"latitude": 0.3150, "longitude": 32.5820},
            geocode_result=_search_result(latitude=0.3151, longitude=32.5820),
        )
    assert "conflict" in str(exc.value)


def test_h1_no_tolerance_for_sub_micro_drift():
    """A disagreement at the 1e-9 level is still a disagreement."""
    with pytest.raises(ValueError):
        build_canonical_location_snapshot(
            location_payload={"latitude": 0.3150, "longitude": 32.5820},
            geocode_result=_search_result(latitude=0.315000001,
                                          longitude=32.5820),
        )


def test_h1_disagreement_never_returns_partial_snapshot():
    """The rejected combination leaks no coordinates or identity."""
    try:
        build_canonical_location_snapshot(
            location_payload={"latitude": 0.3150, "longitude": 32.5820},
            geocode_result=_search_result(latitude=1.0, longitude=2.0),
        )
    except ValueError as exc:
        assert "conflict" in str(exc)
        return
    raise AssertionError("mismatched coordinates were accepted")


# --- H2: evidence-justified source claims ------------------------------------

def test_h2_direct_gps_claim_accepted():
    snap = build_canonical_snapshot_from_coordinates(
        0.3150, 32.5820, source="gps",
        resolution_method="browser_geolocation",
    )
    assert snap["source"] == "gps"
    assert snap["resolution_method"] == "browser_geolocation"


def test_h2_direct_map_claim_accepted():
    snap = build_canonical_snapshot_from_coordinates(
        0.3150, 32.5820, source="map", resolution_method="map_pin",
    )
    assert snap["source"] == "map"
    assert snap["resolution_method"] == "map_pin"


def test_h2_direct_search_claim_rejected_without_evidence():
    with pytest.raises(ValueError) as exc:
        build_canonical_location_snapshot(
            location_payload={
                "latitude": 0.3150, "longitude": 32.5820,
                "source": "search", "resolution_method": "forward_geocode",
            },
        )
    assert "requires a resolved GeocodeResult" in str(exc.value)


def test_h2_direct_curated_claim_rejected_without_evidence():
    with pytest.raises(ValueError) as exc:
        build_canonical_location_snapshot(
            location_payload={
                "latitude": 0.3150, "longitude": 32.5820,
                "source": "curated", "resolution_method": "registry_lookup",
            },
        )
    assert "requires a resolved GeocodeResult" in str(exc.value)


def test_h2_resolved_search_yields_unverified_identity():
    snap = build_canonical_location_snapshot(
        location_payload={"latitude": 0.3150, "longitude": 32.5820},
        geocode_result=_search_result(),
        explicit_address="Nile Stadium",
    )
    assert snap["source"] == "search"
    assert snap["resolution_method"] == "forward_geocode"
    assert snap["identity_status"] == IDENTITY_UNVERIFIED


def test_h2_curated_registry_yields_verified_identity():
    snap = build_canonical_location_snapshot(
        location_payload={"latitude": 0.3150, "longitude": 32.5820},
        geocode_result=_search_result(provider="curated-registry"),
        explicit_address="Nile Stadium",
    )
    assert snap["source"] == "curated"
    assert snap["resolution_method"] == "registry_lookup"
    assert snap["identity_status"] == IDENTITY_VERIFIED


def test_h2_curated_claim_needs_a_curated_provider():
    with pytest.raises(ValueError):
        build_canonical_location_snapshot(
            location_payload={"latitude": 0.3150, "longitude": 32.5820},
            geocode_result=_search_result(provider="photon"),
            source="curated",
            resolution_method="registry_lookup",
        )


# --- H2: exact curated-registry trust boundary -------------------------------
#
# ``verified`` is a trust statement, so the trusted authority set is an
# exact allowlist.  The curated registry node has not shipped, which
# leaves exactly one authority: ``curated-registry``.  Naming
# conventions such as ``registry:*``, ``*-registry`` or bare
# ``registry`` are strings anyone can supply and confer no trust.

_CURATED_AUTHORITY = "curated-registry"
_HEURISTIC_AUTHORITIES = ("evil-registry", "registry:anything", "registry")
_COORDS = {"latitude": 0.3150, "longitude": 32.5820}


def test_h2_curated_allowlist_membership_is_exact():
    """The trust rule itself: exact match after strip/lower, nothing else."""
    from app.transport.services.location_snapshot import (
        _is_curated_provider,
    )
    assert _is_curated_provider("evil-registry") is False
    assert _is_curated_provider("registry:anything") is False
    assert _is_curated_provider("registry") is False
    assert _is_curated_provider("Curated-Registry") is True
    assert _is_curated_provider("curated-registry") is True


def test_h2_curated_allowlist_rejects_whitespace_and_empty():
    from app.transport.services.location_snapshot import (
        _is_curated_provider,
    )
    assert _is_curated_provider("") is False
    assert _is_curated_provider(None) is False
    assert _is_curated_provider("  curated-registry  ") is True
    assert _is_curated_provider("curated-registry ") is True


@pytest.mark.parametrize("authority", _HEURISTIC_AUTHORITIES)
def test_h2_heuristic_authority_never_yields_verified_identity(authority):
    """evil-registry / registry:anything / registry -> unverified search."""
    snap = build_canonical_snapshot_from_geocode_result(
        _search_result(provider=authority),
    )
    assert snap["identity_status"] == IDENTITY_UNVERIFIED
    assert snap["source"] == "search"
    assert snap["resolution_method"] == "forward_geocode"


@pytest.mark.parametrize("authority", _HEURISTIC_AUTHORITIES)
def test_h2_heuristic_authority_cannot_justify_curated_claim(authority):
    """An explicit curated claim against a heuristic authority is refused.

    Two legitimate refusals exist and either is acceptable evidence: the
    explicit pair contradicts the inferred provider evidence, or the
    provider fails the exact curated-registry allowlist.  What must never
    happen is a ``verified`` curated snapshot.
    """
    with pytest.raises(ValueError) as exc:
        build_canonical_location_snapshot(
            location_payload=dict(_COORDS),
            geocode_result=_search_result(provider=authority),
            source="curated",
            resolution_method="registry_lookup",
        )
    message = str(exc.value)
    assert ("contradicts" in message
            or "curated-registry provider" in message), message


@pytest.mark.parametrize("authority", ["Curated-Registry", "curated-registry"])
def test_h2_exact_authority_yields_verified_identity(authority):
    """Case normalization: the exact authority is trusted in any case."""
    snap = build_canonical_snapshot_from_geocode_result(
        _search_result(provider=authority),
    )
    assert snap["identity_status"] == IDENTITY_VERIFIED
    assert snap["source"] == "curated"
    assert snap["resolution_method"] == "registry_lookup"
    assert snap["provenance"]["authority"] == authority


def test_h2_both_builders_inherit_the_exact_allowlist():
    """The corrected trust rule reaches every public builder."""
    for authority in _HEURISTIC_AUTHORITIES:
        via_location = build_canonical_location_snapshot(
            location_payload=dict(_COORDS),
            geocode_result=_search_result(provider=authority),
        )
        via_geocode = build_canonical_snapshot_from_geocode_result(
            _search_result(provider=authority),
        )
        for snap in (via_location, via_geocode):
            assert snap["identity_status"] == IDENTITY_UNVERIFIED, authority
            assert snap["source"] == "search", authority

        with pytest.raises(ValueError):
            build_canonical_location_snapshot(
                location_payload=dict(_COORDS),
                geocode_result=_search_result(provider=authority),
                source="curated",
                resolution_method="registry_lookup",
            )

    for authority in (_CURATED_AUTHORITY, "Curated-Registry"):
        via_location = build_canonical_location_snapshot(
            location_payload=dict(_COORDS),
            geocode_result=_search_result(provider=authority),
        )
        via_geocode = build_canonical_snapshot_from_geocode_result(
            _search_result(provider=authority),
        )
        for snap in (via_location, via_geocode):
            assert snap["identity_status"] == IDENTITY_VERIFIED, authority
            assert snap["source"] == "curated", authority
            assert snap["resolution_method"] == "registry_lookup", authority


# --- H3: finite quality metadata only ----------------------------------------

def test_h3_non_finite_accuracy_is_not_persisted():
    snap = build_canonical_snapshot_from_coordinates(
        0.3150, 32.5820, accuracy_m=float("inf"),
    )
    assert snap["accuracy_m"] is None
    assert not isinstance(snap["accuracy_m"], float) or math.isfinite(
        snap["accuracy_m"]
    )


def test_h3_non_finite_accuracy_in_payload_is_not_persisted():
    snap = build_canonical_location_snapshot(
        location_payload={
            "latitude": 0.3150, "longitude": 32.5820,
            "accuracy": float("nan"),
        },
    )
    assert snap["accuracy_m"] is None or math.isfinite(snap["accuracy_m"])


def test_h3_non_finite_confidence_is_not_persisted():
    for bad in (float("nan"), float("inf"), -float("inf")):
        snap = build_canonical_location_snapshot(
            location_payload={
                "latitude": 0.3150, "longitude": 32.5820,
                "confidence": bad,
            },
        )
        confidence = snap["confidence"]
        assert confidence is None or math.isfinite(confidence), bad


def test_h3_out_of_range_confidence_not_persisted():
    """Contract §11: unknown/invalid confidence is None, never a bad value."""
    snap = build_canonical_location_snapshot(
        location_payload={
            "latitude": 0.3150, "longitude": 32.5820, "confidence": 1.5,
        },
    )
    assert snap["confidence"] is None or (
        math.isfinite(snap["confidence"])
        and 0.0 <= snap["confidence"] <= 1.0
    )


def test_h3_negative_accuracy_not_persisted():
    """Contract §11: unknown/invalid accuracy is None, never a bad value."""
    snap = build_canonical_snapshot_from_coordinates(
        0.3150, 32.5820, accuracy_m=-1.0,
    )
    assert snap["accuracy_m"] is None or (
        math.isfinite(snap["accuracy_m"]) and snap["accuracy_m"] > 0
    )


# --- Persistence: JSONB-safe as returned -------------------------------------

def test_persistence_builder_output_is_json_serializable():
    observed = datetime(2026, 10, 7, 9, 30, tzinfo=timezone.utc)
    snap = build_canonical_location_snapshot(
        location_payload={"latitude": 0.3150, "longitude": 32.5820},
        observed_at=observed,
        source="gps",
        resolution_method="browser_geolocation",
    )
    assert set(snap) == CANONICAL_KEYS

    for key in ("observed_at", "resolved_at"):
        assert isinstance(snap[key], str), (key, type(snap[key]))
        datetime.fromisoformat(snap[key])

    text = json.dumps(snap)          # must not raise
    restored = json.loads(text)
    assert restored == snap


def test_persistence_coordinates_stay_float_after_roundtrip():
    snap = build_canonical_snapshot_from_coordinates(0.3150, 32.5820)
    restored = json.loads(json.dumps(snap))
    assert restored["latitude"] == pytest.approx(0.3150)
    assert restored["longitude"] == pytest.approx(32.5820)
    assert isinstance(restored["label"], str) and restored["label"]
