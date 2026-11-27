"""Transport route-preview API.

This is an informational, non-persistent preview for the rider's existing
pre-commitment journey. GEO remains the only owner of routing providers and
route calculation. Fare quotes and bookings retain their existing distance
basis and lifecycle.
"""

import logging
import math

from flask import request
from flask_login import current_user
from flask_restful import Resource

from app.core.validators import validate_coordinates
from app.extensions import limiter
from app.geo.interfaces import GeoPoint
from app.geo.services import get_routing_service
from app.utils.exceptions import ValidationError

logger = logging.getLogger(__name__)


def _rate_limit_key():
    """Use the same per-user / per-IP key shape as the rider estimate API."""
    if current_user.is_authenticated:
        return f"user:{current_user.id}"
    return f"ip:{request.remote_addr}"


def _read_point(data, prefix):
    """Validate raw coordinate values before converting them to floats."""
    latitude_key = f"{prefix}_latitude"
    longitude_key = f"{prefix}_longitude"
    latitude = data.get(latitude_key)
    longitude = data.get(longitude_key)

    if latitude is None or latitude == "":
        raise ValidationError(
            f"Missing coordinate: {latitude_key}", field=latitude_key
        )
    if longitude is None or longitude == "":
        raise ValidationError(
            f"Missing coordinate: {longitude_key}", field=longitude_key
        )

    try:
        validate_coordinates(latitude, longitude)
    except ValidationError as exc:
        raise ValidationError(
            f"Invalid coordinates for {prefix}", field=prefix
        ) from exc

    # Conversion occurs only after the canonical validator has accepted the
    # original values, so bool/NaN/Inf and out-of-range values cannot be
    # laundered by float().
    return GeoPoint(
        latitude=float(latitude),
        longitude=float(longitude),
    )


def _finite_nonnegative(value):
    if isinstance(value, bool) or value is None:
        return False
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return False
    return math.isfinite(number) and number >= 0


def _unresolved_payload(provider="unresolved"):
    return {
        "resolved": False,
        "distance_m": None,
        "duration_s": None,
        "provider": provider if isinstance(provider, str) and provider else "unresolved",
        "profile": "auto",
        "geometry": [],
    }


def _serialize_route(result):
    """Serialize a valid provider-independent RouteResult; fail closed."""
    if not bool(getattr(result, "resolved", False)):
        return _unresolved_payload(getattr(result, "provider", "unresolved"))

    distance_m = getattr(result, "distance_m", None)
    duration_s = getattr(result, "duration_s", None)
    geometry = getattr(result, "geometry", None)
    provider = getattr(result, "provider", "unresolved")

    if (not _finite_nonnegative(distance_m)
            or not _finite_nonnegative(duration_s)
            or not isinstance(geometry, (list, tuple))
            or not geometry):
        return _unresolved_payload(provider)

    points = []
    for point in geometry:
        latitude = getattr(point, "latitude", None)
        longitude = getattr(point, "longitude", None)
        if not (_finite_nonnegative(abs(latitude)) if isinstance(latitude, (int, float)) else False):
            return _unresolved_payload(provider)
        if not (_finite_nonnegative(abs(longitude)) if isinstance(longitude, (int, float)) else False):
            return _unresolved_payload(provider)
        if float(latitude) > 90 or float(longitude) > 180:
            return _unresolved_payload(provider)
        # The provider contract supplies latitude-first points. Preserve that
        # order in the API response consumed by Leaflet.
        points.append({
            "latitude": float(latitude),
            "longitude": float(longitude),
        })

    return {
        "resolved": True,
        "distance_m": float(distance_m),
        "duration_s": float(duration_s),
        "provider": provider if isinstance(provider, str) and provider else "unknown",
        "profile": "auto",
        "geometry": points,
    }


class RoutePreviewResource(Resource):
    """POST /api/transport/route-preview — planned driving route only."""

    method_decorators = [
        limiter.limit("30 per minute", key_func=_rate_limit_key),
    ]

    def post(self):
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return {
                "success": False,
                "error": "A JSON object with pickup and destination coordinates is required.",
                "code": "INVALID_ROUTE_INPUT",
            }, 400

        try:
            origin = _read_point(data, "pickup")
            destination = _read_point(data, "dropoff")
        except ValidationError as exc:
            return {
                "success": False,
                "error": exc.message,
                "field": exc.field,
                "code": "INVALID_ROUTE_INPUT",
            }, 400

        try:
            service = get_routing_service()
            result = service.route(origin, destination, profile="auto")
            route_data = _serialize_route(result)
        except Exception as exc:
            # Do not log provider exception text: it may include a URL.
            logger.warning(
                "Transport route preview unresolved (%s)",
                type(exc).__name__,
            )
            route_data = _unresolved_payload()

        return {"success": True, "data": route_data}, 200
