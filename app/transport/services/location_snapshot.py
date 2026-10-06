"""
AFCON360 Transport - Canonical Location Snapshot (Node 2).

Builds the ratified Node 1 canonical location snapshot for storage at
booking acceptance time. The snapshot preserves the complete semantic
information available at that moment, per the Node 1 contract
(docs/transport/nodes/NODE-1-canonical-location-contract.md).

This module is the single authority for translating inbound location data
(GeoPoint, GeocodeResult, raw JSONB) into the canonical JSONB structure
stored on Booking.pickup_location and Booking.dropoff_location.

Node 1 invariants enforced here:
- raw lat/lng are validated BEFORE float() conversion (02A coordinate
  safety: bool/NaN/Inf must never launder into coordinates);
- identity_status vocabulary is exactly none | unverified | enriched |
  verified (no `synthetic`);
- the sole external reference field is provenance.reference (no
  top-level `place_ref`);
- source/method must form one of the ratified pairs
  (gps->browser_geolocation, map->map_pin, search->forward_geocode,
  curated->registry_lookup);
- source vocabulary is closed (gps | map | search | curated);
- label is required and non-null; display_name is nullable with empty
  strings normalized to None;
- unresolved typed text never becomes a search snapshot;
- no presentation-only `address` key is written into new snapshots
  (legacy rows remain readable via legacy_location_text()).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from app.core.validators import validate_coordinates
from app.geo.interfaces import GeocodeResult, GeoPoint
from app.utils.exceptions import ValidationError


@dataclass(frozen=True)
class ProvenanceRecord:
    """Structured provenance per Node 1 contract (not a DB model)."""
    authority: str
    reference: Optional[str] = None

    def to_json(self) -> Optional[Dict[str, Any]]:
        if self.authority is None:
            return None
        return {"authority": self.authority, "reference": self.reference}


# Identity status vocabulary per Node 1 contract - exactly these four.
# There is no `synthetic` state (removed at Node 1 ratification).
IDENTITY_NONE = "none"
IDENTITY_UNVERIFIED = "unverified"
IDENTITY_ENRICHED = "enriched"
IDENTITY_VERIFIED = "verified"

VALID_IDENTITY_STATUSES = frozenset([
    IDENTITY_NONE,
    IDENTITY_UNVERIFIED,
    IDENTITY_ENRICHED,
    IDENTITY_VERIFIED,
])

# Closed source vocabulary per Node 1. No `manual`, no `typing`,
# no fifth source.
VALID_SOURCES = frozenset(["gps", "map", "search", "curated"])

# Closed resolution-method vocabulary per Node 1.
VALID_RESOLUTION_METHODS = frozenset([
    "browser_geolocation",
    "map_pin",
    "forward_geocode",
    "registry_lookup",
])

# Required source/method pairings per Node 1. Invalid combinations
# (e.g. gps + map_pin) are rejected, never silently coerced.
SOURCE_METHOD_PAIRS = {
    "gps": "browser_geolocation",
    "map": "map_pin",
    "search": "forward_geocode",
    "curated": "registry_lookup",
}

# Honest input-associated default labels per source (Node 1 lists
# "Current location" and "Pinned ..." as label examples). These describe
# the input path, never geographic identity, and are used only when no
# rider/provider text exists so that `label` stays required and non-null.
SOURCE_DEFAULT_LABELS = {
    "gps": "Current location",
    "map": "Pinned location",
    "search": "Selected place",
    "curated": "Registry place",
}


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def validate_source_method(source: str, resolution_method: str) -> None:
    """Enforce the closed source set and the required source/method pairing.

    Raises ValueError on unknown source, unknown method, or an invalid
    combination. Never coerces.
    """
    if source not in VALID_SOURCES:
        raise ValueError(
            f"Invalid source {source!r}: must be one of {sorted(VALID_SOURCES)}"
        )
    if resolution_method not in VALID_RESOLUTION_METHODS:
        raise ValueError(
            f"Invalid resolution_method {resolution_method!r}: must be one of "
            f"{sorted(VALID_RESOLUTION_METHODS)}"
        )
    expected = SOURCE_METHOD_PAIRS[source]
    if resolution_method != expected:
        raise ValueError(
            f"Invalid source/method pairing: source={source!r} requires "
            f"resolution_method={expected!r}, got {resolution_method!r}"
        )


def _validate_raw_coordinates(latitude_raw: Any, longitude_raw: Any) -> None:
    """Validate RAW coordinate values before float() conversion.

    This is the 02A safety boundary: bool/NaN/Inf/non-numeric values are
    rejected here, on the raw input, so float() can never launder them
    into apparently-valid coordinates (float(True) == 1.0).
    Raises ValidationError when invalid.
    """
    validate_coordinates(latitude_raw, longitude_raw)


def _to_float_pair(latitude_raw: Any, longitude_raw: Any) -> tuple[float, float]:
    """Raw-before-float conversion: validate raw, convert, re-validate."""
    _validate_raw_coordinates(latitude_raw, longitude_raw)
    try:
        latitude = float(latitude_raw)
        longitude = float(longitude_raw)
    except (TypeError, ValueError) as exc:
        raise ValidationError(
            "Invalid coordinates: must be numeric",
            field="coordinates",
        ) from exc
    # Post-conversion range validation on the canonical floats.
    validate_coordinates(latitude, longitude)
    return latitude, longitude


def _normalize_display_name(value: Any) -> Optional[str]:
    """Normalize display_name: real identity string, else None.

    Empty/blank strings normalize to None. Never fabricated from
    coordinates or from `label`.
    """
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _resolve_label(
    *,
    explicit_address: Optional[str],
    location_payload: Any,
    display_name: Optional[str],
    source: str,
) -> str:
    """Resolve the required non-null `label`.

    Priority: explicit rider/system text, then payload text keys, then
    the provider identity (the selected search text IS the label), then
    the honest source-derived default. Never None; never a boolean
    sentinel.
    """
    if isinstance(explicit_address, str) and explicit_address.strip():
        return explicit_address.strip()
    if isinstance(location_payload, dict):
        for key in ("address", "name", "label"):
            val = location_payload.get(key)
            if isinstance(val, str) and val.strip():
                return val.strip()
    if isinstance(location_payload, str) and location_payload.strip():
        return location_payload.strip()
    if display_name:
        return display_name
    return SOURCE_DEFAULT_LABELS[source]


def _build_provenance_from_geocode_result(result: GeocodeResult) -> Optional[ProvenanceRecord]:
    """Extract provenance from a resolved GeocodeResult.

    Authority is the actually-observed provider identity; nothing is
    fabricated (an unresolved/missing provider yields None, never the
    string "unresolved"). The provider `raw` payload is never copied
    wholesale - only the OSM type/id reference datum is carried.
    """
    if not result.resolved:
        return None
    authority = result.provider
    if not authority or authority == "unresolved":
        return None
    # Reference from raw provider data (e.g. Photon OSM type/id).
    reference = None
    if isinstance(result.raw, dict):
        osm_type = result.raw.get("osm_type")
        osm_id = result.raw.get("osm_id")
        if osm_type and osm_id:
            reference = f"{osm_type}/{osm_id}"
    return ProvenanceRecord(authority=authority, reference=reference)


def _infer_source_and_method(
    location_payload: Any,
    geocode_result: Optional[GeocodeResult] = None
) -> tuple[str, str]:
    """
    Infer source and resolution_method from the inbound evidence.
    Per Node 1: source and resolution_method must form a coherent pair.

    A resolved GeocodeResult determines the pair (curated registry vs
    provider search). A dict carrying coordinates without a resolved
    result is a directly-supplied point: an explicit source hint in the
    payload is honored (and validated); otherwise map/map_pin (a placed
    pin is the only direct-coordinate path wired today).

    Unresolved typed text (str payload, no resolved result) raises
    ValueError: it is NOT a search snapshot until explicit selection
    resolves it (Node 1 + Node 6 boundary). Never defaults to search.
    """
    if geocode_result is not None and geocode_result.resolved:
        if geocode_result.provider == "curated-registry":
            return "curated", "registry_lookup"
        return "search", "forward_geocode"

    if isinstance(location_payload, dict):
        has_coords = (
            location_payload.get("latitude") is not None
            and location_payload.get("longitude") is not None
        )
        if has_coords:
            hint_source = location_payload.get("source")
            hint_method = location_payload.get("resolution_method")
            if hint_source is not None or hint_method is not None:
                if not isinstance(hint_source, str) or not isinstance(hint_method, str):
                    raise ValueError(
                        "Invalid source hint: source/resolution_method must be strings"
                    )
                validate_source_method(hint_source, hint_method)
                return hint_source, hint_method
            return "map", "map_pin"

    # No coordinates and no resolved result: no canonical snapshot exists.
    raise ValueError(
        "Cannot infer source/resolution_method: unresolved typed text is "
        "not a resolved location until explicitly selected"
    )


def _infer_identity_status(
    geocode_result: Optional[GeocodeResult],
    display_name: Optional[str],
) -> str:
    """
    Determine identity_status per Node 1 contract vocabulary.

    - none: no human identity attached (GPS/map point, typed label only)
    - unverified: provider/search identity exists but is not curated
    - enriched: reverse enrichment added identity (set only by an
      enrichment path that supplies it; never inferred here)
    - verified: identity from the verified curated registry
    """
    if geocode_result is not None and geocode_result.resolved:
        if geocode_result.provider == "curated-registry":
            return IDENTITY_VERIFIED
        # Forward geocode result from provider (Photon, etc.)
        # This is unverified - provider supplied but not curated
        return IDENTITY_UNVERIFIED
    # Coordinates and/or rider-typed label alone carry no verified human
    # identity. `display_name` here can only be provider-derived (it is
    # never copied from `label`), so its absence means `none`.
    if display_name:
        return IDENTITY_UNVERIFIED
    return IDENTITY_NONE


def _extract_area_from_geocode_result(result: GeocodeResult) -> Optional[str]:
    """Extract best available area label from provider result (Node 1)."""
    if not isinstance(result.raw, dict):
        return None
    # Photon returns city, locality, district, county, state
    # Node 1: area is "best available sub-national locality label as supplied"
    # No hierarchy guaranteed, no parsing, no normalization
    for key in ("city", "locality", "district", "county", "state"):
        val = result.raw.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return None


def _extract_accuracy_from_geopoint(point: Optional[GeoPoint]) -> Optional[float]:
    """Extract accuracy_m from GeoPoint (None = unknown, never 0.0)."""
    if point is None:
        return None
    acc = getattr(point, "accuracy", None)
    if isinstance(acc, bool) or acc is None or acc == 0.0:
        return None
    try:
        acc_f = float(acc)
    except (TypeError, ValueError):
        return None
    if acc_f <= 0:
        return None
    return acc_f


def _extract_confidence_from_geocode_result(result: Optional[GeocodeResult]) -> Optional[float]:
    """Extract confidence from GeocodeResult if genuinely supplied (0..1)."""
    if result is None:
        return None
    # Photon doesn't supply confidence today
    if isinstance(result.raw, dict):
        conf = result.raw.get("confidence")
        if isinstance(conf, bool):
            return None
        if isinstance(conf, (int, float)) and 0.0 <= conf <= 1.0:
            return float(conf)
    return None


def _extract_positive_accuracy(value: Any) -> Optional[float]:
    """Accuracy from a raw provider value: positive finite float or None."""
    if isinstance(value, bool) or value is None:
        return None
    try:
        acc = float(value)
    except (TypeError, ValueError):
        return None
    if not (acc > 0):
        return None
    return acc


def build_canonical_location_snapshot(
    *,
    location_payload: Any,
    geocode_result: Optional[GeocodeResult] = None,
    explicit_address: Optional[str] = None,
    observed_at: Optional[datetime] = None,
    source: Optional[str] = None,
    resolution_method: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Build the canonical location snapshot per Node 1 contract.

    This is the single function that creates the JSONB structure stored
    on Booking.pickup_location / dropoff_location at acceptance time.

    Args:
        location_payload: The raw inbound payload (dict with lat/lng, or string)
        geocode_result: Optional GeocodeResult from forward/reverse geocoding
        explicit_address: Explicit address text from booking form
            (pickup_address/dropoff_address). Becomes `label` only - never
            `display_name`, never identity.
        observed_at: When the underlying observation occurred (GPS fix, pin event)
        source: Optional explicit source (gps | map | search | curated).
            When omitted it is inferred from the evidence. When supplied
            it must form a valid pairing with resolution_method and must
            not contradict a resolved GeocodeResult.
        resolution_method: Optional explicit method (browser_geolocation |
            map_pin | forward_geocode | registry_lookup). Same rules.

    Returns:
        Dict with all Node 1 canonical fields, suitable for JSONB storage.
        Never contains `place_ref`, `address`, `synthetic`, or
        coordinates_resolved/identity_resolved keys.

    Raises:
        ValueError: when no canonical snapshot can be built (missing
            coordinates, unresolved typed text, invalid source pairing).
        ValidationError: when raw coordinates fail the 02A safety check.
    """
    resolved_at = _now_utc()

    inferred_source, inferred_method = _infer_source_and_method(
        location_payload, geocode_result
    )
    if source is None and resolution_method is None:
        source, resolution_method = inferred_source, inferred_method
    else:
        if source is None or resolution_method is None:
            raise ValueError(
                "source and resolution_method must be supplied together"
            )
        validate_source_method(source, resolution_method)
        if geocode_result is not None and geocode_result.resolved:
            # A resolved provider result cannot be claimed as a GPS fix
            # or a map pin: the provenance path must stay truthful.
            if (source, resolution_method) != (inferred_source, inferred_method):
                raise ValueError(
                    f"Explicit source/method {(source, resolution_method)} "
                    f"contradicts the resolved GeocodeResult "
                    f"{(inferred_source, inferred_method)}"
                )

    # Extract coordinates: raw validated BEFORE float conversion (02A).
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    if isinstance(location_payload, dict) and (
        location_payload.get("latitude") is not None
        or location_payload.get("longitude") is not None
    ):
        if (location_payload.get("latitude") is None
                or location_payload.get("longitude") is None):
            raise ValueError("Cannot build canonical snapshot without coordinates")
        latitude, longitude = _to_float_pair(
            location_payload.get("latitude"), location_payload.get("longitude")
        )
    elif geocode_result is not None and geocode_result.resolved:
        if geocode_result.latitude is None or geocode_result.longitude is None:
            raise ValueError("Cannot build canonical snapshot without coordinates")
        latitude, longitude = _to_float_pair(
            geocode_result.latitude, geocode_result.longitude
        )
    else:
        raise ValueError("Cannot build canonical snapshot without coordinates")

    # Provenance: observed provider identity only, else None.
    provenance = None
    if geocode_result is not None and geocode_result.resolved:
        prov_record = _build_provenance_from_geocode_result(geocode_result)
        if prov_record:
            provenance = prov_record.to_json()

    # Human identity: display_name comes ONLY from a resolved provider
    # result (never copied from label/coordinates). Empty normalizes
    # to None.
    display_name: Optional[str] = None
    if geocode_result is not None and geocode_result.resolved:
        display_name = _normalize_display_name(geocode_result.display_name)

    # Label is required and non-null (may be an input-associated default).
    label = _resolve_label(
        explicit_address=explicit_address,
        location_payload=location_payload,
        display_name=display_name,
        source=source,
    )

    # identity_status per evidence.
    identity_status = _infer_identity_status(geocode_result, display_name)

    # area
    area = None
    if geocode_result is not None and geocode_result.resolved:
        area = _extract_area_from_geocode_result(geocode_result)

    # quality (nullable; never fabricated)
    accuracy_m = None
    confidence = None
    if geocode_result is not None and geocode_result.resolved:
        if isinstance(geocode_result.raw, dict):
            accuracy_m = _extract_positive_accuracy(
                geocode_result.raw.get("accuracy")
            )
        confidence = _extract_confidence_from_geocode_result(geocode_result)

    return {
        # Geographic truth (authoritative)
        "latitude": latitude,
        "longitude": longitude,
        # Input path (authoritative routing)
        "source": source,
        "resolution_method": resolution_method,
        # Provenance (authoritative record, nullable, structured)
        "provenance": provenance,
        # Human identity (advisory)
        "label": label,
        "display_name": display_name,
        "identity_status": identity_status,
        "area": area,
        # Quality (both nullable; never fabricated)
        "accuracy_m": accuracy_m,
        "confidence": confidence,
        # Time (distinct fields)
        "observed_at": observed_at.isoformat() if observed_at else None,
        "resolved_at": resolved_at.isoformat(),
    }


def build_canonical_snapshot_from_geocode_result(
    geocode_result: GeocodeResult,
    *,
    explicit_address: Optional[str] = None,
    observed_at: Optional[datetime] = None,
    source: Optional[str] = None,
    resolution_method: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Build canonical snapshot directly from a resolved GeocodeResult.

    Used when the booking flow has already performed geocoding and has
    a GeocodeResult with all provider data. Source/method default from
    the provider (curated-registry -> curated/registry_lookup, anything
    else -> search/forward_geocode); explicit values must be valid and
    must not contradict the provider evidence.
    """
    if not geocode_result.resolved:
        raise ValueError("GeocodeResult must be resolved")

    if geocode_result.provider == "curated-registry":
        inferred = ("curated", "registry_lookup")
    else:
        inferred = ("search", "forward_geocode")
    if source is None and resolution_method is None:
        source, resolution_method = inferred
    else:
        if source is None or resolution_method is None:
            raise ValueError(
                "source and resolution_method must be supplied together"
            )
        validate_source_method(source, resolution_method)
        if (source, resolution_method) != inferred:
            raise ValueError(
                f"Explicit source/method {(source, resolution_method)} "
                f"contradicts the GeocodeResult provider evidence {inferred}"
            )

    provenance_record = _build_provenance_from_geocode_result(geocode_result)
    provenance = provenance_record.to_json() if provenance_record else None

    display_name = _normalize_display_name(geocode_result.display_name)
    label = _resolve_label(
        explicit_address=explicit_address,
        location_payload=None,
        display_name=display_name,
        source=source,
    )

    # For forward geocode, identity is unverified (provider result, not curated)
    identity_status = IDENTITY_VERIFIED if geocode_result.provider == "curated-registry" else IDENTITY_UNVERIFIED

    area = _extract_area_from_geocode_result(geocode_result)
    accuracy_m = None
    if isinstance(geocode_result.raw, dict):
        accuracy_m = _extract_positive_accuracy(geocode_result.raw.get("accuracy"))
    confidence = _extract_confidence_from_geocode_result(geocode_result)

    if geocode_result.latitude is None or geocode_result.longitude is None:
        raise ValueError("GeocodeResult must carry coordinates")
    latitude, longitude = _to_float_pair(
        geocode_result.latitude, geocode_result.longitude
    )

    resolved_at = _now_utc()

    return {
        "latitude": latitude,
        "longitude": longitude,
        "source": source,
        "resolution_method": resolution_method,
        "provenance": provenance,
        "label": label,
        "display_name": display_name,
        "identity_status": identity_status,
        "area": area,
        "accuracy_m": accuracy_m,
        "confidence": confidence,
        "observed_at": observed_at.isoformat() if observed_at else None,
        "resolved_at": resolved_at.isoformat(),
    }


def build_canonical_snapshot_from_coordinates(
    latitude: float,
    longitude: float,
    *,
    source: str = "map",
    resolution_method: str = "map_pin",
    explicit_address: Optional[str] = None,
    observed_at: Optional[datetime] = None,
    accuracy_m: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Build canonical snapshot from raw coordinates (GPS fix or map pin).

    No provider involved, so provenance is None and there is no human
    identity: display_name is None and identity_status is `none`, even
    when a rider-typed label exists (the label is input text, not
    identity). Raw coordinates are validated BEFORE float conversion
    (02A safety boundary).
    """
    validate_source_method(source, resolution_method)
    latitude_f, longitude_f = _to_float_pair(latitude, longitude)

    label = _resolve_label(
        explicit_address=explicit_address,
        location_payload=None,
        display_name=None,
        source=source,
    )

    resolved_at = _now_utc()

    return {
        "latitude": latitude_f,
        "longitude": longitude_f,
        "source": source,
        "resolution_method": resolution_method,
        "provenance": None,
        "label": label,
        "display_name": None,
        "identity_status": IDENTITY_NONE,
        "area": None,
        "accuracy_m": _extract_positive_accuracy(accuracy_m),
        "confidence": None,
        "observed_at": observed_at.isoformat() if observed_at else None,
        "resolved_at": resolved_at.isoformat(),
    }


def get_display_text(snapshot: Dict[str, Any]) -> Optional[str]:
    """
    Get presentation text for a canonical location snapshot.

    Per Node 1: display_name is advisory and nullable.
    - Show display_name when available;
    - otherwise show the input-associated label when one exists;
    - otherwise render an honest fallback based on identity_status.
    Presentation fallbacks are never canonical display_name.
    """
    display_name = snapshot.get("display_name")
    if isinstance(display_name, str) and display_name.strip():
        return display_name.strip()

    label = snapshot.get("label")
    if isinstance(label, str) and label.strip():
        return label.strip()

    # Honest fallback based on identity_status
    identity_status = snapshot.get("identity_status")

    if identity_status == IDENTITY_NONE:
        return "Location to be confirmed"

    if identity_status == IDENTITY_UNVERIFIED:
        return "Unverified location"

    if identity_status == IDENTITY_ENRICHED:
        return "Enriched location"

    if identity_status == IDENTITY_VERIFIED:
        return "Verified location"

    return "Location to be confirmed"


def get_coordinates(snapshot: Dict[str, Any]) -> tuple[Optional[float], Optional[float]]:
    """Extract authoritative coordinates from snapshot."""
    lat = snapshot.get("latitude")
    lng = snapshot.get("longitude")
    if lat is not None and lng is not None:
        if isinstance(lat, bool) or isinstance(lng, bool):
            return None, None
        try:
            return float(lat), float(lng)
        except (TypeError, ValueError):
            return None, None
    return None, None


def is_resolved_snapshot(snapshot: Any) -> bool:
    """Check if a stored value is a canonical resolved snapshot (has coordinates)."""
    if not isinstance(snapshot, dict):
        return False
    return snapshot.get("latitude") is not None and snapshot.get("longitude") is not None


def legacy_location_text(snapshot: Any) -> Optional[str]:
    """
    Legacy compatibility: extract text from old string-only or partial dict rows.

    Per Node 1: legacy string-only rows remain readable as unresolved.
    This is the READ path for pre-Node-2 rows only; new canonical snapshots
    are rendered via get_display_text().
    """
    if snapshot is None:
        return None
    if isinstance(snapshot, str):
        return snapshot.strip() if snapshot.strip() else None
    if isinstance(snapshot, dict):
        # Old dict shape: address/name/label
        for key in ("address", "name", "label"):
            val = snapshot.get(key)
            if isinstance(val, str) and val.strip():
                return val.strip()
        # Coordinates fallback
        lat = snapshot.get("latitude")
        lng = snapshot.get("longitude")
        if lat is not None and lng is not None:
            if isinstance(lat, bool) or isinstance(lng, bool):
                return None
            try:
                return f"{float(lat):.4f}, {float(lng):.4f}"
            except (TypeError, ValueError):
                return None
    return None


__all__ = [
    "ProvenanceRecord",
    "IDENTITY_NONE",
    "IDENTITY_UNVERIFIED",
    "IDENTITY_ENRICHED",
    "IDENTITY_VERIFIED",
    "VALID_IDENTITY_STATUSES",
    "VALID_SOURCES",
    "VALID_RESOLUTION_METHODS",
    "SOURCE_METHOD_PAIRS",
    "validate_source_method",
    "build_canonical_location_snapshot",
    "build_canonical_snapshot_from_geocode_result",
    "build_canonical_snapshot_from_coordinates",
    "get_display_text",
    "get_coordinates",
    "is_resolved_snapshot",
    "legacy_location_text",
]
