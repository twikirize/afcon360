"""Canonical road measurements for Transport fare quotes.

Transport may use GEO routing only through this boundary. There is deliberately
no straight-line fallback: a fare quote cannot be issued without a resolved
road route from the configured routing provider.
"""
import logging
import math
from typing import Any, Dict

from app.core.validators import validate_coordinates
from app.geo.interfaces import GeoPoint
from app.geo.services import get_routing_service
from app.utils.exceptions import ServiceUnavailableError, ValidationError

logger = logging.getLogger(__name__)


def _read_point(location: Any, field: str) -> GeoPoint:
    if not isinstance(location, dict):
        raise ValidationError(
            "Resolved pickup and destination coordinates are required.",
            field=field,
        )
    latitude = location.get("latitude")
    longitude = location.get("longitude")
    try:
        validate_coordinates(latitude, longitude)
    except Exception as exc:
        raise ValidationError(
            "Resolved pickup and destination coordinates are required.",
            field=field,
        ) from exc
    return GeoPoint(latitude=float(latitude), longitude=float(longitude))


def _finite_nonnegative(value: Any) -> bool:
    if isinstance(value, bool) or value is None:
        return False
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return False
    return math.isfinite(number) and number >= 0


def _serialize_geometry(raw_geometry: Any):
    if not isinstance(raw_geometry, (list, tuple)) or not raw_geometry:
        return None
    points = []
    for point in raw_geometry:
        latitude = getattr(point, "latitude", None)
        longitude = getattr(point, "longitude", None)
        if (not _finite_coordinate(latitude, 90)
                or not _finite_coordinate(longitude, 180)):
            return None
        points.append({
            "latitude": float(latitude),
            "longitude": float(longitude),
        })
    return points


def _finite_coordinate(value: Any, bound: float) -> bool:
    if isinstance(value, bool) or value is None:
        return False
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return False
    return math.isfinite(number) and -bound <= number <= bound


def measure_road_route(pickup: Dict[str, Any],
                       dropoff: Dict[str, Any]) -> Dict[str, Any]:
    """Resolve one driving route and return authoritative, normalized facts.

    The returned values are server measurements. Callers must not accept
    distance or duration sent by the browser. Unresolved or malformed provider
    results raise ServiceUnavailableError and never fall back to Haversine.
    """
    origin = _read_point(pickup, "pickup")
    destination = _read_point(dropoff, "dropoff")

    try:
        result = get_routing_service().route(
            origin, destination, profile="auto"
        )
    except Exception as exc:
        logger.warning("Transport road route unresolved (%s)",
                       type(exc).__name__)
        raise ServiceUnavailableError(
            message="A driving route is temporarily unavailable. Please try again.",
            service_name="road_routing",
            code="ROUTING_UNAVAILABLE",
        ) from exc

    distance_m = getattr(result, "distance_m", None)
    duration_s = getattr(result, "duration_s", None)
    provider = getattr(result, "provider", None)
    geometry = _serialize_geometry(getattr(result, "geometry", None))
    if (not bool(getattr(result, "resolved", False))
            or not _finite_nonnegative(distance_m)
            or not _finite_nonnegative(duration_s)
            or not isinstance(provider, str)
            or not provider.strip()
            or provider.strip().lower() == "unresolved"
            or geometry is None):
        raise ServiceUnavailableError(
            message="A driving route is temporarily unavailable. Please try again.",
            service_name="road_routing",
            code="ROUTING_UNAVAILABLE",
        )

    distance_m = float(distance_m)
    duration_s = float(duration_s)
    return {
        "distance_m": distance_m,
        "distance_km": round(distance_m / 1000.0, 6),
        "duration_s": round(duration_s, 3),
        "duration_minutes": int(math.ceil(duration_s / 60.0)),
        "provider": provider.strip()[:64],
        "distance_basis": "road_network",
        "geometry": geometry,
    }
