# app/geo/validation.py
"""
AFCON360 GEO - coordinate normalization + validation (domain-neutral).

Reuses the existing project validators (single source of range truth):
    app.utils.validators.TransportValidators.validate_coordinates
    app.core.validators.validate_coordinates (raises ValidationError)

Adds GEO-level normalization: coerce str/numeric input, bounds, precision
cap, radius/freshness guards. Raises app.utils.exceptions.ValidationError
so domain callers get the same error contract they already handle.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

from app.geo.interfaces import GeoPoint
from app.utils.exceptions import ValidationError
from app.utils.validators import TransportValidators

# Precision cap: ~1 cm at equator is 7 decimals; anything beyond is noise.
MAX_COORDINATE_DECIMALS = 7
# Operational guards (tunable via config later, NOT hardcoded per domain).
MAX_SEARCH_RADIUS_M = 100_000  # 100 km
MAX_LOCATION_AGE_SECONDS = 24 * 3600  # history queries older than this warn


def normalize_coordinate(value: Any, name: str) -> float:
    """Coerce to float + range-check one axis. Raises ValidationError."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValidationError(
            f"Invalid {name}: must be numeric, got {value!r}", field=name
        )
    return number


def normalize_point(latitude: Any, longitude: Any,
                    accuracy: Any = 0.0,
                    timestamp: Optional[datetime] = None) -> GeoPoint:
    """
    Validate + normalize a (lat, lng) pair into an immutable GeoPoint.

    Raises ValidationError on out-of-range / non-numeric input (never clamps
    silently - clamping invents a location the user never reported).
    """
    lat = normalize_coordinate(latitude, "latitude")
    lng = normalize_coordinate(longitude, "longitude")
    if not TransportValidators.validate_coordinates(lat, lng):
        raise ValidationError(
            "Invalid coordinates: latitude must be within [-90, 90] and "
            "longitude within [-180, 180]",
            field="coordinates",
        )
    try:
        acc = max(0.0, float(accuracy))
    except (TypeError, ValueError):
        raise ValidationError(
            f"Invalid accuracy: must be numeric, got {accuracy!r}",
            field="accuracy",
        )
    return GeoPoint(
        latitude=round(lat, MAX_COORDINATE_DECIMALS),
        longitude=round(lng, MAX_COORDINATE_DECIMALS),
        accuracy=acc,
        timestamp=timestamp,
    )


def normalize_location_payload(payload: Dict[str, Any]) -> GeoPoint:
    """
    Normalize the shared driver-location contract:
        {latitude, longitude, accuracy?, speed?, heading?, timestamp?}

    Compatible with TrackingService.update_location input. Extra keys
    (speed/heading) are validated numerically but live on the domain record,
    not on GeoPoint. Raises ValidationError on any bad field.
    """
    if not isinstance(payload, dict):
        raise ValidationError("Location payload must be an object",
                              field="location")
    missing = [k for k in ("latitude", "longitude") if k not in payload]
    if missing:
        raise ValidationError(
            f"Location must include latitude and longitude (missing: {missing})",
            field="location",
        )
    ts = payload.get("timestamp")
    parsed_ts: Optional[datetime] = None
    if ts is not None and not isinstance(ts, datetime):
        try:
            parsed_ts = datetime.fromisoformat(str(ts))
        except ValueError:
            raise ValidationError(
                f"Invalid timestamp: {ts!r}", field="timestamp"
            )
    point = normalize_point(
        payload["latitude"], payload["longitude"],
        accuracy=payload.get("accuracy", 0.0),
        timestamp=parsed_ts if parsed_ts is not None
        else (ts if isinstance(ts, datetime) else None),
    )
    for key in ("speed", "heading"):
        if key in payload:
            try:
                value = float(payload[key])
            except (TypeError, ValueError):
                raise ValidationError(
                    f"Invalid {key}: must be numeric, got {payload[key]!r}",
                    field=key,
                )
            if value < 0:
                raise ValidationError(
                    f"Invalid {key}: must be >= 0", field=key
                )
    return point


def validate_radius_m(radius_m: Any) -> float:
    """Guard the shared nearby() radius. Raises ValidationError."""
    if isinstance(radius_m, bool):
        raise ValidationError(
            f"Invalid radius: must be numeric, got {radius_m!r}",
            field="radius",
        )
    try:
        radius = float(radius_m)
    except (TypeError, ValueError):
        raise ValidationError(
            f"Invalid radius: must be numeric, got {radius_m!r}",
            field="radius",
        )
    if radius <= 0 or radius > MAX_SEARCH_RADIUS_M:
        raise ValidationError(
            f"Invalid radius: must be within (0, {MAX_SEARCH_RADIUS_M}] meters",
            field="radius",
        )
    return radius


def is_fresh(point: GeoPoint, max_age_seconds: float,
             now: Optional[datetime] = None) -> bool:
    """Freshness check for current-state reads. Naive point = not fresh."""
    if point.timestamp is None:
        return False
    ref = now or datetime.now(timezone.utc)
    ts = point.timestamp
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return (ref - ts).total_seconds() <= max_age_seconds


def location_tuple(point: GeoPoint) -> Tuple[float, float]:
    """(lat, lng) tuple for providers that need plain pairs."""
    return (point.latitude, point.longitude)
