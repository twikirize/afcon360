"""AFCON360 Transport - Canonical Resolved-Location Snapshot.

Single product-layer authority that translates inbound location evidence
(device GPS, map pin, provider search, curated registry) into the ratified
13-key canonical snapshot persisted on Booking.pickup_location /
Booking.dropoff_location.

Design principles
-----------------

Coordinates are the resolution invariant.  A snapshot exists only when a
trusted pair of latitude/longitude has been validated.  Every other field
is descriptive and none of them can silently override the coordinates.

Human identity (``display_name``) and input text (``label``) are advisory.
They describe how the location was chosen or what it looks like to a
human, but they never authorize a change of position, and a provider's
display name is never copied into ``label``.

Provenance (``provenance.authority`` and ``provenance.reference``) is audit
metadata.  The reference is display/audit-only; it must never be used as a
database key, cache key, or deduplication key.  Provider raw payloads are
never copied wholesale into a snapshot.

The source/method pair is the *evidence* claim of how the location
entered AFCON360 and how it was resolved.  It is a closed vocabulary with
exactly four permitted pairs.  Direct-coordinate builders may only claim
``gps`` or ``map``: ``search`` and ``curated`` require a resolved
``GeocodeResult`` whose provider matches.

Snapshot Hardening invariants
-----------------------------

* H1 -- When both the payload and a resolved ``GeocodeResult`` carry
  coordinates, the two pairs must agree exactly.  Refusing to combine
  coordinates from one source with identity/provenance from another.
* H2 -- Direct-coordinate builders may not fabricate provider evidence.
  ``search`` and ``curated`` require a resolved ``GeocodeResult``.
  ``identity_status='verified'`` may only be produced by a
  ``curated-registry`` provider.
* H3 -- ``accuracy_m`` and ``confidence`` must be finite when supplied.
  ``NaN`` and +/-Infinity are rejected rather than persisted.

Invariants carried forward from the ratified Node 1/2 contract
--------------------------------------------------------------

* Raw-before-float coordinate safety (UI-LOC-02A).  Bool, ``NaN`` and
  infinity never reach the numeric range check by way of ``float()``
  coercion.
* Exactly 13 persisted keys -- no ``address``, no ``place_ref``, no
  ``synthetic``, no ``coordinates_resolved``, no ``identity_resolved``.
* ``label`` is required and non-null; ``display_name`` is nullable with
  empty strings normalized to ``None``.
* Unresolved typed text never becomes a ``search`` snapshot.  Explicit
  selection or resolution is required.
* Legacy read compatibility is provided by explicit helpers only; new
  writes always go through the canonical builders.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Mapping, Optional, Tuple

from app.core.validators import validate_coordinates
from app.geo.interfaces import GeocodeResult
from app.utils.exceptions import ValidationError


# ---------------------------------------------------------------------------
# Persisted shape and closed vocabularies
# ---------------------------------------------------------------------------

PERSISTED_KEYS = (
    "latitude",
    "longitude",
    "source",
    "resolution_method",
    "provenance",
    "label",
    "display_name",
    "identity_status",
    "area",
    "accuracy_m",
    "confidence",
    "observed_at",
    "resolved_at",
)

IDENTITY_NONE = "none"
IDENTITY_UNVERIFIED = "unverified"
IDENTITY_ENRICHED = "enriched"
IDENTITY_VERIFIED = "verified"

VALID_IDENTITY_STATUSES = frozenset({
    IDENTITY_NONE,
    IDENTITY_UNVERIFIED,
    IDENTITY_ENRICHED,
    IDENTITY_VERIFIED,
})

VALID_SOURCES = frozenset({"gps", "map", "search", "curated"})

VALID_RESOLUTION_METHODS = frozenset({
    "browser_geolocation",
    "map_pin",
    "forward_geocode",
    "registry_lookup",
})

SOURCE_METHOD_PAIRS = {
    "gps": "browser_geolocation",
    "map": "map_pin",
    "search": "forward_geocode",
    "curated": "registry_lookup",
}

# H2 -- sources that may be claimed from direct coordinates with no
# provider/registry evidence.  Everything else requires a resolved
# GeocodeResult whose provider matches.
DIRECT_SOURCES = frozenset({"gps", "map"})

SOURCE_DEFAULT_LABELS = {
    "gps": "Current location",
    "map": "Pinned location",
    "search": "Selected place",
    "curated": "Registry place",
}

# Exact allowlist of provider identities that justify ``curated`` (H2).
# The curated registry node has not shipped, so exactly one authority is
# trusted today.  ``verified`` is a trust statement, and trust is never
# derived from naming conventions (``registry:*``, ``*-registry``, bare
# ``registry``): those are strings anyone can supply, not credentials.
_CURATED_REGISTRY_AUTHORITIES = frozenset({"curated-registry"})

# Area keys from provider raw data, in the order the ratified Node 2
# implementation used.  Changing this order is a semantic change.
_AREA_KEYS = ("city", "locality", "district", "county", "state")


# ---------------------------------------------------------------------------
# Value types
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ProvenanceRecord:
    """Structured provenance -- a small explicit record, never raw payload."""

    authority: str
    reference: Optional[str] = None

    def to_json(self) -> Optional[Dict[str, Any]]:
        if not self.authority:
            return None
        return {"authority": self.authority, "reference": self.reference}


# ---------------------------------------------------------------------------
# Small utilities
# ---------------------------------------------------------------------------

def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _isoformat_or_none(value: Optional[datetime]) -> Optional[str]:
    if value is None:
        return None
    if value.tzinfo is None:
        raise ValueError("timestamp must be timezone-aware")
    return value.isoformat()


def _require_aware(
    value: Optional[datetime],
    field_name: str,
) -> Optional[datetime]:
    if value is None:
        return None
    if not isinstance(value, datetime):
        raise ValueError(f"{field_name} must be a datetime or None")
    if value.tzinfo is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value


# ---------------------------------------------------------------------------
# Source/method validation (syntactic + H2 semantic)
# ---------------------------------------------------------------------------

def validate_source_method(source: str, resolution_method: str) -> None:
    """Enforce the closed vocabulary and the exact source/method pairing.

    This is the *syntactic* check.  H2 (evidence justification) is
    enforced separately by the builders, where the full call context is
    available.  Raises ``ValueError``; never coerces.
    """
    if source not in VALID_SOURCES:
        raise ValueError(f"unsupported location source: {source!r}")
    if resolution_method not in VALID_RESOLUTION_METHODS:
        raise ValueError(
            f"unsupported location resolution method: {resolution_method!r}"
        )
    expected = SOURCE_METHOD_PAIRS.get(source)
    if expected != resolution_method:
        raise ValueError(
            f"invalid source/method pairing: {source!r} requires "
            f"{expected!r}, got {resolution_method!r}"
        )


def _assert_direct_source_allowed(source: str) -> None:
    """H2 -- direct-coordinate builders may only claim ``gps`` or ``map``."""
    if source not in DIRECT_SOURCES:
        raise ValueError(
            f"source {source!r} requires a resolved GeocodeResult; only "
            f"'gps' and 'map' are permitted for direct coordinates"
        )


def _provider_name(geocode_result: Any) -> Optional[str]:
    """Read the provider identity without copying any raw provider payload."""
    if geocode_result is None:
        return None
    for attr in ("provider", "authority"):
        value = getattr(geocode_result, attr, None)
        if value is not None and str(value).strip():
            return str(value).strip()
    provenance = getattr(geocode_result, "provenance", None)
    if provenance is not None:
        if isinstance(provenance, Mapping):
            authority = provenance.get("authority")
            if authority is not None and str(authority).strip():
                return str(authority).strip()
        else:
            authority = getattr(provenance, "authority", None)
            if authority is not None and str(authority).strip():
                return str(authority).strip()
    return None


def _is_curated_provider(provider: Optional[str]) -> bool:
    """Return True only for an exact curated-registry authority (H2).

    Membership is checked against :data:`_CURATED_REGISTRY_AUTHORITIES`
    after whitespace stripping and case folding.  There is no prefix,
    suffix, substring, or naming-convention matching.
    """
    if not provider:
        return False
    return provider.strip().lower() in _CURATED_REGISTRY_AUTHORITIES


def _assert_provider_source_matches(source: str, geocode_result: Any) -> None:
    """H2 -- search/curated source claims require resolved provider evidence."""
    if source in DIRECT_SOURCES:
        return

    if geocode_result is None or not bool(
        getattr(geocode_result, "resolved", False)
    ):
        raise ValueError(
            f"source {source!r} requires a resolved GeocodeResult "
            f"whose provider justifies the claim"
        )

    provider = _provider_name(geocode_result)

    if source == "curated":
        if not _is_curated_provider(provider):
            raise ValueError(
                "source 'curated' requires a curated-registry provider; "
                f"got {provider!r}"
            )
    elif source == "search":
        if not provider:
            raise ValueError(
                "source 'search' requires a provider identity on the "
                "resolved GeocodeResult"
            )


# ---------------------------------------------------------------------------
# Coordinate validation (raw-before-float; 02A safety boundary)
# ---------------------------------------------------------------------------

def _validate_raw_coordinates(latitude_raw: Any, longitude_raw: Any) -> None:
    """Validate RAW coordinate values before any ``float()`` coercion.

    Delegates to the canonical raising validator
    (``app.core.validators.validate_coordinates``) which rejects bool at
    the raw level and enforces range on the numeric pair.
    """
    validate_coordinates(latitude_raw, longitude_raw)


def _to_float_pair(
    latitude_raw: Any,
    longitude_raw: Any,
) -> Tuple[float, float]:
    """Raw-before-float conversion: validate raw, convert, re-validate."""
    _validate_raw_coordinates(latitude_raw, longitude_raw)

    try:
        latitude = float(latitude_raw)
        longitude = float(longitude_raw)
    except (TypeError, ValueError) as exc:
        raise ValidationError(
            message="coordinates must be numeric",
            field="coordinates",
        ) from exc

    if not math.isfinite(latitude) or not math.isfinite(longitude):
        raise ValidationError(
            message="coordinates must be finite",
            field="coordinates",
        )

    validate_coordinates(latitude, longitude)

    return latitude, longitude


# ---------------------------------------------------------------------------
# Field extraction
# ---------------------------------------------------------------------------

def _normalize_display_name(value: Any) -> Optional[str]:
    """Empty / whitespace-only strings normalize to ``None``."""
    if value is None:
        return None
    if isinstance(value, str):
        text = value.strip()
        return text or None
    return None


def _resolve_label(
    *,
    explicit_address: Optional[str],
    location_payload: Any,
    display_name: Optional[str],
    source: str,
) -> str:
    """Resolve the required non-null ``label``.

    Priority chain (matching the ratified Node 2 behaviour):
        explicit address text -> payload ``address``/``name``/``label``
        -> payload raw string -> provider ``display_name`` -> source
        default.

    Never returns ``None``; never returns a boolean sentinel.
    """
    if isinstance(explicit_address, str) and explicit_address.strip():
        return explicit_address.strip()

    if isinstance(location_payload, Mapping):
        for key in ("address", "name", "label"):
            value = location_payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()

    if isinstance(location_payload, str) and location_payload.strip():
        return location_payload.strip()

    if display_name:
        return display_name

    return SOURCE_DEFAULT_LABELS[source]


def _build_provenance_from_geocode_result(
    geocode_result: Any,
) -> Optional[ProvenanceRecord]:
    """Extract structured provenance without copying raw provider data.

    Only ``authority`` and (if the provider supplies one) the OSM
    reference datum are carried.  ``raw`` is never copied wholesale.
    """
    if geocode_result is None or not bool(
        getattr(geocode_result, "resolved", False)
    ):
        return None

    authority = _provider_name(geocode_result)
    if not authority or authority == "unresolved":
        return None

    reference: Optional[str] = None
    raw = getattr(geocode_result, "raw", None)
    if isinstance(raw, Mapping):
        osm_type = raw.get("osm_type")
        osm_id = raw.get("osm_id")
        if osm_type and osm_id:
            reference = f"{osm_type}/{osm_id}"

    return ProvenanceRecord(authority=authority, reference=reference)


def _infer_identity_status(
    geocode_result: Any,
    display_name: Optional[str],
) -> str:
    """Determine ``identity_status`` per the ratified Node 1 vocabulary.

    * ``verified`` is produced **only** by a curated-registry provider.
    * ``unverified`` is produced by any other resolved provider, or by a
      payload that carries a non-empty provider display name.
    * ``enriched`` is reserved for the future reverse-enrichment path; it
      is never inferred here.
    * ``none`` is the honest no-identity state for GPS / map points.
    """
    if geocode_result is not None and bool(
        getattr(geocode_result, "resolved", False)
    ):
        provider = _provider_name(geocode_result)
        if _is_curated_provider(provider):
            return IDENTITY_VERIFIED
        return IDENTITY_UNVERIFIED

    if display_name:
        return IDENTITY_UNVERIFIED

    return IDENTITY_NONE


def _extract_area_from_geocode_result(geocode_result: Any) -> Optional[str]:
    """Best available sub-national locality label, as supplied.

    No hierarchy is guaranteed; no parsing or normalization occurs.
    """
    if geocode_result is None:
        return None
    raw = getattr(geocode_result, "raw", None)
    if not isinstance(raw, Mapping):
        return None
    for key in _AREA_KEYS:
        value = raw.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _finite_float(
    value: Any,
    *,
    minimum: Optional[float] = None,
    maximum: Optional[float] = None,
    strictly_positive: bool = False,
) -> Optional[float]:
    """Return a finite float within bounds, or ``None``.

    H3 safety: rejects NaN, +/-Infinity, bool, and strings that do not
    parse to a finite number.  Never raises on invalid input -- callers
    treat ``None`` as "unknown".
    """
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    if minimum is not None and number < minimum:
        return None
    if maximum is not None and number > maximum:
        return None
    if strictly_positive and number <= 0:
        return None
    return number


def _extract_accuracy_from_geopoint(point: Any) -> Optional[float]:
    """Accuracy in metres from a GeoPoint-like value; ``None`` = unknown."""
    if point is None:
        return None
    value = getattr(point, "accuracy_m", None)
    if value is None:
        value = getattr(point, "accuracy", None)
    if value is None:
        return None
    return _finite_float(value, minimum=0.0, strictly_positive=True)


def _extract_positive_accuracy(value: Any) -> Optional[float]:
    """Accuracy from a raw provider value: strictly positive finite or None."""
    return _finite_float(value, minimum=0.0, strictly_positive=True)


def _extract_confidence_from_geocode_result(
    geocode_result: Any,
) -> Optional[float]:
    """Confidence / relevance when genuinely supplied (0..1, finite)."""
    if geocode_result is None:
        return None
    value = getattr(geocode_result, "confidence", None)
    if value is None:
        raw = getattr(geocode_result, "raw", None)
        if isinstance(raw, Mapping):
            value = raw.get("confidence")
    return _finite_float(value, minimum=0.0, maximum=1.0)


# ---------------------------------------------------------------------------
# The single canonical snapshot assembler
# ---------------------------------------------------------------------------

def _assemble_snapshot(
    *,
    latitude: float,
    longitude: float,
    source: str,
    resolution_method: str,
    provenance: Optional[Dict[str, Any]],
    label: str,
    display_name: Optional[str],
    identity_status: str,
    area: Optional[str],
    accuracy_m: Optional[float],
    confidence: Optional[float],
    observed_at: Optional[datetime],
    resolved_at: datetime,
) -> Dict[str, Any]:
    """Assemble the 13-key canonical snapshot.

    All coercion of datetimes to ISO strings happens here so the
    persisted shape is exactly what JSONB can round-trip.
    """
    if not isinstance(latitude, float) or not isinstance(longitude, float):
        raise TypeError("latitude and longitude must be float")
    if not math.isfinite(latitude) or not math.isfinite(longitude):
        raise ValueError("latitude and longitude must be finite")

    validate_source_method(source, resolution_method)

    if not isinstance(label, str) or not label.strip():
        raise ValueError("label must be a non-empty string")

    if identity_status not in VALID_IDENTITY_STATUSES:
        raise ValueError(
            f"identity_status must be one of "
            f"{sorted(VALID_IDENTITY_STATUSES)}"
        )

    if accuracy_m is not None:
        if not math.isfinite(accuracy_m) or accuracy_m <= 0:
            raise ValueError(
                "accuracy_m must be positive and finite when present"
            )

    if confidence is not None:
        if (
            not math.isfinite(confidence)
            or confidence < 0.0
            or confidence > 1.0
        ):
            raise ValueError(
                "confidence must be finite and between 0 and 1 when present"
            )

    _require_aware(observed_at, "observed_at")
    if resolved_at is None or resolved_at.tzinfo is None:
        raise ValueError("resolved_at must be timezone-aware")

    snapshot: Dict[str, Any] = {
        "latitude": latitude,
        "longitude": longitude,
        "source": source,
        "resolution_method": resolution_method,
        "provenance": provenance,
        "label": label.strip(),
        "display_name": _normalize_display_name(display_name),
        "identity_status": identity_status,
        "area": _normalize_display_name(area),
        "accuracy_m": accuracy_m,
        "confidence": confidence,
        "observed_at": _isoformat_or_none(observed_at),
        "resolved_at": resolved_at.isoformat(),
    }

    if set(snapshot.keys()) != set(PERSISTED_KEYS):
        raise AssertionError(
            "canonical location snapshot shape drifted; expected "
            f"{sorted(PERSISTED_KEYS)}, got {sorted(snapshot.keys())}"
        )

    return snapshot


# ---------------------------------------------------------------------------
# Internal: source/method inference
# ---------------------------------------------------------------------------

def _infer_source_and_method(
    location_payload: Any,
    geocode_result: Any,
) -> Tuple[str, str]:
    """Infer truthful source/method for the payload.

    * A resolved ``GeocodeResult`` determines the pair based on provider
      identity (curated registry vs everything else).
    * A mapping with coordinates but no resolved result is a direct point
      and may only claim ``gps`` or ``map``.
    * Anything else (unresolved typed text) is refused.
    """
    if geocode_result is not None and bool(
        getattr(geocode_result, "resolved", False)
    ):
        if _is_curated_provider(_provider_name(geocode_result)):
            return "curated", "registry_lookup"
        return "search", "forward_geocode"

    if isinstance(location_payload, Mapping):
        hint_source = location_payload.get("source")
        hint_method = location_payload.get("resolution_method")
        if hint_source is None and hint_method is None:
            return "map", "map_pin"
        if hint_source is None or hint_method is None:
            raise ValueError(
                "source and resolution_method must be supplied together"
            )
        source_str = str(hint_source).strip()
        method_str = str(hint_method).strip()
        validate_source_method(source_str, method_str)
        _assert_direct_source_allowed(source_str)
        return source_str, method_str

    raise ValueError(
        "unresolved typed text is not a canonical location until "
        "explicitly selected or resolved"
    )


# ---------------------------------------------------------------------------
# Public builders
# ---------------------------------------------------------------------------

def build_canonical_location_snapshot(
    *,
    location_payload: Any,
    geocode_result: Optional[GeocodeResult] = None,
    explicit_address: Optional[str] = None,
    observed_at: Optional[datetime] = None,
    source: Optional[str] = None,
    resolution_method: Optional[str] = None,
) -> Dict[str, Any]:
    """Build the single canonical resolved-location snapshot.

    This is the authority for translating inbound location evidence into
    the 13-key canonical shape persisted on ``Booking.pickup_location`` /
    ``Booking.dropoff_location``.

    Coordination:

    * Coordinates are the resolution invariant.
    * A resolved ``GeocodeResult`` may enrich identity, provenance,
      area, and quality metadata -- but never silently replace
      coordinates that disagree with the payload (H1).
    * A caller who supplies ``source``/``resolution_method`` must supply
      both, must form a ratified pair, and must be justified by evidence
      (H2).
    * Unresolved typed text is not a canonical location; it raises
      ``ValueError`` until explicit selection resolves it.
    """
    if location_payload is None:
        raise ValueError("location_payload is required")

    geocode_resolved = bool(
        geocode_result is not None
        and getattr(geocode_result, "resolved", False)
    )

    payload_mapping = (
        location_payload if isinstance(location_payload, Mapping) else None
    )

    payload_has_lat = (
        payload_mapping is not None
        and payload_mapping.get("latitude") is not None
    )
    payload_has_lng = (
        payload_mapping is not None
        and payload_mapping.get("longitude") is not None
    )

    if payload_has_lat and payload_has_lng:
        latitude, longitude = _to_float_pair(
            payload_mapping.get("latitude"),
            payload_mapping.get("longitude"),
        )
    elif payload_has_lat or payload_has_lng:
        raise ValueError(
            "location_payload must include both latitude and longitude"
        )
    elif geocode_resolved:
        latitude, longitude = _to_float_pair(
            getattr(geocode_result, "latitude", None),
            getattr(geocode_result, "longitude", None),
        )
    else:
        raise ValueError("canonical location requires resolved coordinates")

    # H1 -- when both sources carry coordinates, they must agree exactly.
    if (payload_has_lat and payload_has_lng) and geocode_resolved:
        geo_lat, geo_lng = _to_float_pair(
            getattr(geocode_result, "latitude", None),
            getattr(geocode_result, "longitude", None),
        )
        if latitude != geo_lat or longitude != geo_lng:
            raise ValueError(
                "location coordinates conflict with the resolved "
                "GeocodeResult; refusing to combine coordinate truth "
                "from one source with identity/provenance from another"
            )

    if source is None and resolution_method is None:
        final_source, final_method = _infer_source_and_method(
            location_payload, geocode_result
        )
    elif source is None or resolution_method is None:
        raise ValueError(
            "source and resolution_method must be supplied together"
        )
    else:
        final_source = str(source).strip()
        final_method = str(resolution_method).strip()
        validate_source_method(final_source, final_method)

        if geocode_resolved:
            inferred_source, inferred_method = _infer_source_and_method(
                location_payload, geocode_result
            )
            if (final_source, final_method) != (
                inferred_source,
                inferred_method,
            ):
                raise ValueError(
                    f"explicit source/method "
                    f"{(final_source, final_method)} contradicts the "
                    f"resolved GeocodeResult evidence "
                    f"{(inferred_source, inferred_method)}"
                )

    if final_source in DIRECT_SOURCES:
        _assert_direct_source_allowed(final_source)
    else:
        _assert_provider_source_matches(final_source, geocode_result)

    if geocode_resolved:
        display_name = _normalize_display_name(
            getattr(geocode_result, "display_name", None)
        )
    else:
        display_name = _normalize_display_name(
            payload_mapping.get("display_name") if payload_mapping else None
        )

    label = _resolve_label(
        explicit_address=explicit_address,
        location_payload=location_payload,
        display_name=display_name,
        source=final_source,
    )

    provenance_record = _build_provenance_from_geocode_result(geocode_result)
    provenance = (
        provenance_record.to_json() if provenance_record is not None else None
    )

    identity_status = _infer_identity_status(geocode_result, display_name)
    area = _extract_area_from_geocode_result(geocode_result)

    accuracy_m: Optional[float] = None
    confidence: Optional[float] = None
    if geocode_resolved:
        raw = getattr(geocode_result, "raw", None)
        if isinstance(raw, Mapping):
            accuracy_m = _extract_positive_accuracy(raw.get("accuracy"))
        confidence = _extract_confidence_from_geocode_result(geocode_result)

    if accuracy_m is None and payload_mapping is not None:
        accuracy_m = _extract_positive_accuracy(
            payload_mapping.get("accuracy_m")
        )
    if confidence is None and payload_mapping is not None:
        confidence = _finite_float(
            payload_mapping.get("confidence"),
            minimum=0.0,
            maximum=1.0,
        )

    observed = observed_at
    if observed is None and payload_mapping is not None:
        observed = payload_mapping.get("observed_at")
    observed = _require_aware(observed, "observed_at")

    return _assemble_snapshot(
        latitude=latitude,
        longitude=longitude,
        source=final_source,
        resolution_method=final_method,
        provenance=provenance,
        label=label,
        display_name=display_name,
        identity_status=identity_status,
        area=area,
        accuracy_m=accuracy_m,
        confidence=confidence,
        observed_at=observed,
        resolved_at=_utc_now(),
    )


def build_canonical_snapshot_from_geocode_result(
    geocode_result: GeocodeResult,
    *,
    explicit_address: Optional[str] = None,
    observed_at: Optional[datetime] = None,
    source: Optional[str] = None,
    resolution_method: Optional[str] = None,
) -> Dict[str, Any]:
    """Build a canonical snapshot from an already-resolved GeocodeResult.

    Source/method default from the provider identity
    (``curated-registry`` -> ``curated``/``registry_lookup``; anything
    else -> ``search``/``forward_geocode``).  Explicit values must be
    valid and must not contradict the provider evidence.
    """
    if geocode_result is None or not bool(
        getattr(geocode_result, "resolved", False)
    ):
        raise ValueError("a resolved GeocodeResult is required")

    provider = _provider_name(geocode_result)
    if _is_curated_provider(provider):
        inferred = ("curated", "registry_lookup")
    else:
        inferred = ("search", "forward_geocode")

    if source is None and resolution_method is None:
        final_source, final_method = inferred
    elif source is None or resolution_method is None:
        raise ValueError(
            "source and resolution_method must be supplied together"
        )
    else:
        final_source = str(source).strip()
        final_method = str(resolution_method).strip()
        validate_source_method(final_source, final_method)
        if (final_source, final_method) != inferred:
            raise ValueError(
                f"explicit source/method {(final_source, final_method)} "
                f"contradicts the GeocodeResult provider evidence "
                f"{inferred}"
            )

    _assert_provider_source_matches(final_source, geocode_result)

    latitude, longitude = _to_float_pair(
        getattr(geocode_result, "latitude", None),
        getattr(geocode_result, "longitude", None),
    )

    display_name = _normalize_display_name(
        getattr(geocode_result, "display_name", None)
    )
    label = _resolve_label(
        explicit_address=explicit_address,
        location_payload=None,
        display_name=display_name,
        source=final_source,
    )

    provenance_record = _build_provenance_from_geocode_result(geocode_result)
    provenance = (
        provenance_record.to_json() if provenance_record is not None else None
    )

    identity_status = _infer_identity_status(geocode_result, display_name)
    area = _extract_area_from_geocode_result(geocode_result)

    raw = getattr(geocode_result, "raw", None)
    accuracy_m = (
        _extract_positive_accuracy(raw.get("accuracy"))
        if isinstance(raw, Mapping)
        else None
    )
    confidence = _extract_confidence_from_geocode_result(geocode_result)

    observed = _require_aware(observed_at, "observed_at")

    return _assemble_snapshot(
        latitude=latitude,
        longitude=longitude,
        source=final_source,
        resolution_method=final_method,
        provenance=provenance,
        label=label,
        display_name=display_name,
        identity_status=identity_status,
        area=area,
        accuracy_m=accuracy_m,
        confidence=confidence,
        observed_at=observed,
        resolved_at=_utc_now(),
    )


def build_canonical_snapshot_from_coordinates(
    latitude: Any,
    longitude: Any,
    *,
    source: str = "map",
    resolution_method: str = "map_pin",
    explicit_address: Optional[str] = None,
    observed_at: Optional[datetime] = None,
    accuracy_m: Any = None,
) -> Dict[str, Any]:
    """Build a canonical snapshot from raw coordinates (GPS fix or pin).

    No provider is involved: ``provenance`` is ``None``,
    ``display_name`` is ``None``, and ``identity_status`` is ``none``.
    H2 restricts the source to ``gps`` or ``map``; search and curated
    require a resolved ``GeocodeResult``.

    Raw coordinates are validated BEFORE ``float()`` coercion (02A).
    """
    source_str = str(source).strip()
    method_str = str(resolution_method).strip()
    validate_source_method(source_str, method_str)
    _assert_direct_source_allowed(source_str)

    latitude_f, longitude_f = _to_float_pair(latitude, longitude)

    label = _resolve_label(
        explicit_address=explicit_address,
        location_payload=None,
        display_name=None,
        source=source_str,
    )

    observed = _require_aware(observed_at, "observed_at")

    return _assemble_snapshot(
        latitude=latitude_f,
        longitude=longitude_f,
        source=source_str,
        resolution_method=method_str,
        provenance=None,
        label=label,
        display_name=None,
        identity_status=IDENTITY_NONE,
        area=None,
        accuracy_m=_extract_positive_accuracy(accuracy_m),
        confidence=None,
        observed_at=observed,
        resolved_at=_utc_now(),
    )


# ---------------------------------------------------------------------------
# Read helpers
# ---------------------------------------------------------------------------

def get_display_text(snapshot: Any) -> Optional[str]:
    """Presentation text for a canonical snapshot.

    Preference order: ``display_name`` -> ``label`` -> honest
    ``identity_status``-aware fallback.  Returns ``None`` only when the
    input is neither a canonical nor a legacy shape.
    """
    if isinstance(snapshot, Mapping):
        for key in ("display_name", "label"):
            value = snapshot.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()

        identity_status = snapshot.get("identity_status")
        if identity_status == IDENTITY_NONE:
            return "Location to be confirmed"
        if identity_status == IDENTITY_UNVERIFIED:
            return "Unverified location"
        if identity_status == IDENTITY_ENRICHED:
            return "Enriched location"
        if identity_status == IDENTITY_VERIFIED:
            return "Verified location"
        return None

    if isinstance(snapshot, str) and snapshot.strip():
        return snapshot.strip()

    return None


def get_coordinates(
    snapshot: Any,
) -> Tuple[Optional[float], Optional[float]]:
    """Extract authoritative coordinates from a snapshot, or ``(None, None)``."""
    if not isinstance(snapshot, Mapping):
        return None, None
    latitude = snapshot.get("latitude")
    longitude = snapshot.get("longitude")
    if latitude is None or longitude is None:
        return None, None
    if isinstance(latitude, bool) or isinstance(longitude, bool):
        return None, None
    try:
        latitude_f = float(latitude)
        longitude_f = float(longitude)
    except (TypeError, ValueError):
        return None, None
    if not math.isfinite(latitude_f) or not math.isfinite(longitude_f):
        return None, None
    return latitude_f, longitude_f


def is_resolved_snapshot(snapshot: Any) -> bool:
    """True when readable coordinates exist."""
    latitude, longitude = get_coordinates(snapshot)
    return latitude is not None and longitude is not None


def legacy_location_text(snapshot: Any) -> Optional[str]:
    """Read path for pre-Node-2 rows (bare string or old dict shape).

    Per Node 1: legacy string-only rows remain readable as unresolved.
    New canonical snapshots are rendered via ``get_display_text()``.
    Returns ``None`` for empty/unknown input so templates can use
    ``|default``.
    """
    if snapshot is None:
        return None

    if isinstance(snapshot, str):
        return snapshot.strip() or None

    if isinstance(snapshot, Mapping):
        for key in ("address", "name", "label", "text", "location_text"):
            value = snapshot.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()

        latitude, longitude = get_coordinates(snapshot)
        if latitude is not None and longitude is not None:
            return f"{latitude:.4f}, {longitude:.4f}"

        return None

    return None


__all__ = [
    "PERSISTED_KEYS",
    "IDENTITY_NONE",
    "IDENTITY_UNVERIFIED",
    "IDENTITY_ENRICHED",
    "IDENTITY_VERIFIED",
    "VALID_IDENTITY_STATUSES",
    "VALID_SOURCES",
    "VALID_RESOLUTION_METHODS",
    "SOURCE_METHOD_PAIRS",
    "DIRECT_SOURCES",
    "SOURCE_DEFAULT_LABELS",
    "ProvenanceRecord",
    "validate_source_method",
    "build_canonical_location_snapshot",
    "build_canonical_snapshot_from_geocode_result",
    "build_canonical_snapshot_from_coordinates",
    "get_display_text",
    "get_coordinates",
    "is_resolved_snapshot",
    "legacy_location_text",
]