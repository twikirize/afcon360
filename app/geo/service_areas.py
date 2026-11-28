"""Owner-managed geographic service areas.

Service-area configuration is stored in the existing SystemConfig KV store.
No new table or migration is required. GeoJSON coordinates follow RFC 7946:
[longitude, latitude]. Invalid configured polygons never grant access.
"""
from __future__ import annotations

import json
import math
import re
from copy import deepcopy
from typing import Any

from app.models.system_config import SystemConfig
from app.utils.exceptions import ValidationError


SERVICE_AREA_CONFIG_KEY = "GEO_SERVICE_AREAS"
DEFAULT_SERVICE_AREA_CONFIG = {
    "version": 1,
    "enabled": False,
    "allow_cross_area_routes": False,
    "areas": [],
}
_ALLOWED_SERVICES = frozenset({"transport", "accommodation", "events", "tourism"})
_MAX_AREAS = 100
_MAX_RING_POINTS = 5000
_EPSILON = 1e-10


def get_service_area_config() -> dict:
    """Read authoritative service areas; malformed persisted policy fails closed.

    A missing setting means this feature has never been enabled and preserves
    the safe rollout default (off). A present but malformed setting is
    different: it must not silently disable a policy that an operator saved.
    """
    setting = SystemConfig.query.filter_by(key=SERVICE_AREA_CONFIG_KEY).first()
    if setting is None:
        return deepcopy(DEFAULT_SERVICE_AREA_CONFIG)

    try:
        raw = json.loads(setting.value) if setting.value else None
    except (TypeError, ValueError):
        raw = None
    if not isinstance(raw, dict) or setting.value_type != "json":
        return {
            "version": 1,
            "enabled": True,
            "allow_cross_area_routes": False,
            "areas": [],
        }

    areas = raw.get("areas")
    prepared_areas = []
    if isinstance(areas, list):
        for area in areas:
            if not isinstance(area, dict):
                continue
            prepared = dict(area)
            try:
                prepared["_validated_geometry"] = validate_geometry(
                    area.get("geometry")
                )
            except (TypeError, ValueError):
                # An invalid saved polygon never grants service eligibility.
                prepared["_validated_geometry"] = None
            prepared_areas.append(prepared)

    try:
        version = max(1, int(raw.get("version") or 1))
    except (TypeError, ValueError):
        version = 1
    # Only an explicit JSON boolean False disables enforcement. Any malformed
    # value is treated as enabled-with-no-trustworthy-areas (fail closed).
    enabled_value = raw.get("enabled")
    enabled = enabled_value if isinstance(enabled_value, bool) else True
    cross_area_value = raw.get("allow_cross_area_routes")
    return {
        "version": version,
        "enabled": enabled,
        "allow_cross_area_routes": cross_area_value is True,
        "areas": prepared_areas,
    }


def _number(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field} must be a numeric coordinate")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{field} must be finite")
    return number


def validate_geometry(geometry: Any) -> dict:
    """Validate a GeoJSON Polygon or MultiPolygon without external GIS deps."""
    if not isinstance(geometry, dict):
        raise ValueError("Service-area geometry must be a GeoJSON object")
    kind = geometry.get("type")
    coordinates = geometry.get("coordinates")
    if kind not in ("Polygon", "MultiPolygon") or not isinstance(coordinates, list):
        raise ValueError("Geometry must be a GeoJSON Polygon or MultiPolygon")

    polygons = [coordinates] if kind == "Polygon" else coordinates
    if not polygons:
        raise ValueError("The service-area polygon has no rings")
    total_points = 0

    for polygon_index, polygon in enumerate(polygons):
        if not isinstance(polygon, list) or not polygon:
            raise ValueError("Every polygon must contain an outer ring")
        for ring_index, ring in enumerate(polygon):
            label = f"polygon {polygon_index + 1} ring {ring_index + 1}"
            if not isinstance(ring, list) or not 4 <= len(ring) <= _MAX_RING_POINTS:
                raise ValueError(f"{label} must contain between 4 and {_MAX_RING_POINTS} points")
            total_points += len(ring)
            previous = None
            for pair in ring:
                if not isinstance(pair, (list, tuple)) or len(pair) < 2:
                    raise ValueError(f"{label} contains an invalid coordinate pair")
                lng = _number(pair[0], label + " longitude")
                lat = _number(pair[1], label + " latitude")
                if not -180 <= lng <= 180 or not -90 <= lat <= 90:
                    raise ValueError(f"{label} contains coordinates outside valid ranges")
                if previous is None:
                    first = (lng, lat)
                previous = (lng, lat)
            if previous is None or not (
                math.isclose(first[0], previous[0], abs_tol=_EPSILON)
                and math.isclose(first[1], previous[1], abs_tol=_EPSILON)
            ):
                raise ValueError(f"{label} must be closed (first and last points must match)")
    if total_points > _MAX_RING_POINTS:
        raise ValueError(f"Service-area geometry exceeds {_MAX_RING_POINTS} total points")
    # Copy only the supported GeoJSON shape; provider properties are not persisted.
    return {"type": kind, "coordinates": coordinates}


def _point_on_segment(lng: float, lat: float, a: list, b: list) -> bool:
    x1, y1 = float(a[0]), float(a[1])
    x2, y2 = float(b[0]), float(b[1])
    cross = (lng - x1) * (y2 - y1) - (lat - y1) * (x2 - x1)
    if abs(cross) > _EPSILON:
        return False
    return (
        min(x1, x2) - _EPSILON <= lng <= max(x1, x2) + _EPSILON
        and min(y1, y2) - _EPSILON <= lat <= max(y1, y2) + _EPSILON
    )


def _point_in_ring(lng: float, lat: float, ring: list) -> bool:
    inside = False
    previous = ring[-1]
    for current in ring:
        if _point_on_segment(lng, lat, previous, current):
            return True
        x1, y1 = float(previous[0]), float(previous[1])
        x2, y2 = float(current[0]), float(current[1])
        if (y1 > lat) != (y2 > lat):
            crossing_lng = x1 + (lat - y1) * (x2 - x1) / (y2 - y1)
            if lng < crossing_lng:
                inside = not inside
        previous = current
    return inside


def _point_in_validated_geometry(latitude: float, longitude: float,
                                  validated: dict) -> bool:
    polygons = (
        [validated["coordinates"]]
        if validated["type"] == "Polygon"
        else validated["coordinates"]
    )
    for polygon in polygons:
        if not _point_in_ring(longitude, latitude, polygon[0]):
            continue
        # GeoJSON interior rings are holes; their boundary is excluded too.
        if any(_point_in_ring(longitude, latitude, hole) for hole in polygon[1:]):
            continue
        return True
    return False


def point_in_geometry(latitude: float, longitude: float, geometry: dict) -> bool:
    """Return whether a point lies in a Polygon/MultiPolygon (boundary included)."""
    try:
        lat = _number(latitude, "latitude")
        lng = _number(longitude, "longitude")
        if not -90 <= lat <= 90 or not -180 <= lng <= 180:
            return False
        validated = validate_geometry(geometry)
    except (TypeError, ValueError):
        return False
    return _point_in_validated_geometry(lat, lng, validated)


def _service_matches(area: dict, service: str) -> bool:
    services = area.get("services")
    if not isinstance(services, list):
        return False
    return "*" in services or service in services


def check_service_area_point(latitude: Any, longitude: Any,
                             service: str = "transport",
                             config: dict | None = None) -> dict:
    """Assess one coordinate against active areas for a service."""
    settings = config if isinstance(config, dict) else get_service_area_config()
    if settings.get("enabled") is not True:
        return {
            "enabled": False, "supported": True,
            "reason": "geofencing_disabled", "area_id": None, "area_name": None,
            "service": service,
        }

    matching = []
    for area in settings.get("areas", []):
        if not isinstance(area, dict) or area.get("active") is not True:
            continue
        if not _service_matches(area, service):
            continue
        validated_geometry = area.get("_validated_geometry")
        if validated_geometry is None:
            try:
                validated_geometry = validate_geometry(area.get("geometry"))
            except (TypeError, ValueError):
                continue
        try:
            lat = _number(latitude, "latitude")
            lng = _number(longitude, "longitude")
        except (TypeError, ValueError):
            return {
                "enabled": True, "supported": False,
                "reason": "outside_active_area",
                "area_id": None, "area_name": None,
                "service": service,
            }
        if (-90 <= lat <= 90 and -180 <= lng <= 180
                and _point_in_validated_geometry(lat, lng, validated_geometry)):
            matching.append(area)

    if matching:
        first = matching[0]
        return {
            "enabled": True, "supported": True,
            "reason": "inside_active_area",
            "area_id": str(first.get("id") or ""),
            "area_name": str(first.get("name") or ""),
            "area_ids": [
                str(area.get("id") or "") for area in matching
                if str(area.get("id") or "")
            ],
            "area_names": [
                str(area.get("name") or "") for area in matching
            ],
            "service": service,
        }

    has_active = any(
        isinstance(area, dict) and area.get("active") is True
        and _service_matches(area, service)
        for area in settings.get("areas", [])
    )
    return {
        "enabled": True, "supported": False,
        "reason": "outside_active_area" if has_active else "no_active_service_area",
        "area_id": None, "area_name": None,
        "service": service,
    }


def assess_driver_for_pickup_area(
    driver_latitude: Any,
    driver_longitude: Any,
    pickup_latitude: Any,
    pickup_longitude: Any,
    service: str = "transport",
    config: dict | None = None,
) -> dict:
    """Require a match candidate to be in the pickup's active service area."""
    settings = config if isinstance(config, dict) else get_service_area_config()
    if settings.get("enabled") is not True:
        return {"enabled": False, "supported": True, "reason": "geofencing_disabled"}

    pickup_status = check_service_area_point(
        pickup_latitude, pickup_longitude, service, settings
    )
    if not pickup_status.get("supported"):
        return {
            "enabled": True, "supported": False,
            "reason": "pickup_outside_active_area",
        }

    driver_status = check_service_area_point(
        driver_latitude, driver_longitude, service, settings
    )
    if not driver_status.get("supported"):
        return {
            "enabled": True, "supported": False,
            "reason": "driver_outside_active_area",
        }
    pickup_area_ids = set(
        pickup_status.get("area_ids") or [pickup_status.get("area_id")]
    )
    driver_area_ids = set(
        driver_status.get("area_ids") or [driver_status.get("area_id")]
    )
    common_area_ids = pickup_area_ids.intersection(driver_area_ids)
    if not common_area_ids:
        return {
            "enabled": True, "supported": False,
            "reason": "driver_in_different_service_area",
        }
    area_id = next(
        (area_id for area_id in (pickup_status.get("area_ids") or [])
         if area_id in common_area_ids),
        pickup_status.get("area_id"),
    )
    return {
        "enabled": True, "supported": True,
        "reason": "driver_in_pickup_service_area",
        "area_id": area_id,
    }


def assess_service_area_trip(pickup: dict, dropoff: dict,
                             service: str = "transport",
                             config: dict | None = None) -> dict:
    """Require pickup and destination to be supported by one active area by default."""
    settings = config if isinstance(config, dict) else get_service_area_config()
    if settings.get("enabled") is not True:
        return {
            "enabled": False, "supported": True,
            "reason": "geofencing_disabled", "area_id": None, "area_name": None,
            "service": service,
            "pickup": check_service_area_point(
                pickup.get("latitude"), pickup.get("longitude"), service, settings),
            "dropoff": check_service_area_point(
                dropoff.get("latitude"), dropoff.get("longitude"), service, settings),
        }

    pickup_status = check_service_area_point(
        pickup.get("latitude"), pickup.get("longitude"), service, settings)
    dropoff_status = check_service_area_point(
        dropoff.get("latitude"), dropoff.get("longitude"), service, settings)

    if not pickup_status["supported"]:
        reason = pickup_status["reason"]
        field = "pickup"
    elif not dropoff_status["supported"]:
        reason = dropoff_status["reason"]
        field = "dropoff"
    else:
        pickup_area_ids = pickup_status.get("area_ids") or [
            pickup_status.get("area_id")
        ]
        dropoff_area_ids = set(
            dropoff_status.get("area_ids") or [dropoff_status.get("area_id")]
        )
        common_area_ids = [
            area_id for area_id in pickup_area_ids
            if area_id and area_id in dropoff_area_ids
        ]
        if common_area_ids:
            chosen_id = common_area_ids[0]
            chosen_name = pickup_status.get("area_name")
            for area_id, area_name in zip(
                pickup_status.get("area_ids") or [],
                pickup_status.get("area_names") or [],
            ):
                if area_id == chosen_id:
                    chosen_name = area_name
                    break
            return {
                "enabled": True, "supported": True,
                "reason": "inside_active_area", "area_id": chosen_id,
                "area_name": chosen_name, "service": service,
                "pickup": pickup_status, "dropoff": dropoff_status,
            }

        if service == "transport" and settings.get("allow_cross_area_routes") is True:
            return {
                "enabled": True, "supported": True,
                "reason": "inside_active_area", "area_id": None,
                "area_name": "Multiple supported areas", "service": service,
                "pickup": pickup_status, "dropoff": dropoff_status,
            }

        reason = "cross_area_route_not_enabled"
        field = "dropoff"

    return {
        "enabled": True, "supported": False, "reason": reason,
        "field": field, "area_id": None, "area_name": None,
        "service": service,
        "pickup": pickup_status, "dropoff": dropoff_status,
    }


def service_area_error(assessment: dict) -> str:
    """Human-readable rider-safe explanation for unsupported ride locations."""
    reason = assessment.get("reason")
    field = assessment.get("field")
    service = str(assessment.get("service") or "transport").lower()
    service_label = {
        "transport": "Ride bookings",
        "accommodation": "Accommodation bookings",
        "events": "Event services",
        "tourism": "Tourism services",
    }.get(service, "This service")
    service_noun = {
        "transport": "ride",
        "accommodation": "accommodation",
        "events": "event",
        "tourism": "tourism",
    }.get(service, "service")
    if reason == "no_active_service_area":
        return f"{service_label} are temporarily unavailable because no active service area is configured."
    if reason == "cross_area_route_not_enabled":
        return f"Pickup and destination must be within the same active {service_noun} service area."
    if field == "location":
        return (
            "This place is outside Pamoja's currently supported service areas. "
            "Choose a place inside an active service area."
        )
    endpoint = "pickup" if field == "pickup" else "destination"
    return (
        f"The {endpoint} is outside Pamoja's currently supported {service_noun} service areas. "
        "Please choose a place inside an active service area."
    )


def enforce_service_area_trip(pickup: dict, dropoff: dict,
                              service: str = "transport") -> dict:
    assessment = assess_service_area_trip(pickup, dropoff, service=service)
    if not assessment.get("supported"):
        raise ValidationError(
            message=service_area_error(assessment),
            field=assessment.get("field") or "pickup",
        )
    return assessment


def validate_service_area_config(raw: Any) -> dict:
    """Validate and normalise the complete owner-managed configuration."""
    if not isinstance(raw, dict):
        raise ValueError("Service-area configuration must be an object")
    areas = raw.get("areas", [])
    if not isinstance(areas, list) or len(areas) > _MAX_AREAS:
        raise ValueError(f"Configure no more than {_MAX_AREAS} service areas")

    cleaned = []
    seen_ids = set()
    for index, area in enumerate(areas):
        if not isinstance(area, dict):
            raise ValueError(f"Service area {index + 1} must be an object")
        name = str(area.get("name") or "").strip()
        if not name or len(name) > 80:
            raise ValueError(f"Service area {index + 1} needs a name (maximum 80 characters)")
        raw_id = str(area.get("id") or name).strip().lower()
        area_id = re.sub(r"[^a-z0-9]+", "-", raw_id).strip("-")
        if not area_id or len(area_id) > 80:
            raise ValueError(f"Service area {name} needs a valid identifier")
        if area_id in seen_ids:
            raise ValueError(f"Duplicate service-area identifier: {area_id}")
        seen_ids.add(area_id)

        country_code = str(area.get("country_code") or "").strip().upper()
        if country_code and (len(country_code) != 2 or not country_code.isalpha()):
            raise ValueError(f"{name}: country code must be two letters")
        services = area.get("services", ["transport"])
        if not isinstance(services, list):
            raise ValueError(f"{name}: services must be a list")
        services = sorted({str(item).strip().lower() for item in services})
        if not services or not set(services).issubset(_ALLOWED_SERVICES | {"*"}):
            raise ValueError(f"{name}: select at least one valid service")
        geometry = validate_geometry(area.get("geometry"))
        cleaned.append({
            "id": area_id,
            "name": name,
            "country_code": country_code,
            "active": area.get("active") is True,
            "services": services,
            "geometry": geometry,
        })

    enabled = raw.get("enabled") is True
    if enabled and not any(item["active"] for item in cleaned):
        raise ValueError(
            "Enable at least one active service area before turning on geofence enforcement."
        )

    try:
        version = max(1, int(raw.get("version") or 1))
    except (TypeError, ValueError):
        version = 1

    return {
        "version": version,
        "enabled": enabled,
        "allow_cross_area_routes": raw.get("allow_cross_area_routes") is True,
        "areas": cleaned,
    }


def save_service_area_config(raw: dict, updated_by: int | None = None) -> dict:
    """Persist the validated config in SystemConfig; no migration required."""
    current = get_service_area_config()
    validated = validate_service_area_config(raw)
    validated["version"] = max(current.get("version", 1), validated["version"]) + 1
    SystemConfig.set(
        SERVICE_AREA_CONFIG_KEY,
        validated,
        value_type="json",
        category="geo",
        description="Owner-managed service-area polygons and geofence enforcement",
        updated_by=updated_by,
    )
    return validated
