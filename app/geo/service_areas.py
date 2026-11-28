"""GEO-owned service-area policy and Polygon/MultiPolygon evaluation.

Authoritative persistence uses the GEO service-area tables. Until the
operator-generated Alembic migration is applied, the existing SystemConfig
JSON setting remains a temporary compatibility path so this branch can be
reviewed without hand-written migrations. Once the tables exist, all writes
go to relational GEO records and the singleton policy row.
"""
from __future__ import annotations

import json
import math
import re
from copy import deepcopy
from typing import Any

from sqlalchemy.exc import SQLAlchemyError

from app.extensions import db
from app.geo.models import GeoServiceArea, GeoServiceAreaPolicy
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
_MAX_TOTAL_CONFIG_POINTS = 25000
_EPSILON = 1e-10


def _prepare_area_record(area: dict) -> dict:
    """Convert a persisted area to the shared service-policy dictionary."""
    prepared = {
        "id": str(area.get("id") or area.get("slug") or ""),
        "name": str(area.get("name") or ""),
        "country_code": str(area.get("country_code") or ""),
        "active": area.get("active") is True,
        "services": area.get("services") if isinstance(area.get("services"), list) else [],
        "geometry": area.get("geometry"),
    }
    prepared["_geometry_invalid"] = False
    try:
        if prepared["active"]:
            prepared["_validated_geometry"] = validate_geometry(prepared["geometry"])
        else:
            prepared["_validated_geometry"] = None
    except (TypeError, ValueError):
        prepared["_validated_geometry"] = None
        prepared["_geometry_invalid"] = True
    return prepared


def _read_legacy_service_area_config() -> dict:
    """Read the pre-migration JSON setting without treating corruption as off."""
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
    prepared = [
        _prepare_area_record(area)
        for area in areas
        if isinstance(area, dict)
    ] if isinstance(areas, list) else []
    try:
        version = max(1, int(raw.get("version") or 1))
    except (TypeError, ValueError):
        version = 1
    enabled = raw.get("enabled")
    return {
        "version": version,
        "enabled": enabled if isinstance(enabled, bool) else True,
        "allow_cross_area_routes": raw.get("allow_cross_area_routes") is True,
        "areas": prepared,
    }


def _is_missing_geofence_table(error: Exception) -> bool:
    message = str(error).lower()
    table_named = (
        "geo_service_areas" in message
        or "geo_service_area_policies" in message
    )
    missing = (
        "does not exist" in message
        or "no such table" in message
        or "undefinedtable" in message
    )
    return table_named and missing


def get_service_area_config() -> dict:
    """Read current DB policy; safely fall back before the migration is applied."""
    try:
        policy = GeoServiceAreaPolicy.query.filter_by(
            policy_key="default", is_deleted=False
        ).first()
        records = (
            GeoServiceArea.query
            .filter_by(is_deleted=False)
            .order_by(GeoServiceArea.name.asc(), GeoServiceArea.slug.asc())
            .all()
        )
    except SQLAlchemyError as exc:
        db.session.rollback()
        if _is_missing_geofence_table(exc):
            return _read_legacy_service_area_config()
        raise

    # One-time transition behavior: when models exist but no owner has saved
    # through the new page yet, retain any pre-migration SystemConfig values.
    if policy is None and not records:
        return _read_legacy_service_area_config()

    areas = [
        _prepare_area_record({
            "id": record.slug,
            "name": record.name,
            "country_code": record.country_code,
            "active": record.active,
            "services": record.services,
            "geometry": record.geometry,
        })
        for record in records
    ]
    return {
        "version": max(1, int(policy.policy_version or 1)) if policy else 1,
        "enabled": bool(policy.enforcement_enabled) if policy else False,
        "allow_cross_area_routes": bool(policy.allow_cross_area_routes) if policy else False,
        "areas": areas,
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
            unique_vertices = {
                (float(pair[0]), float(pair[1])) for pair in ring[:-1]
            }
            if len(unique_vertices) < 3:
                raise ValueError(f"{label} must contain at least three distinct vertices")
            signed_area_twice = sum(
                float(ring[index][0]) * float(ring[index + 1][1])
                - float(ring[index + 1][0]) * float(ring[index][1])
                for index in range(len(ring) - 1)
            )
            if abs(signed_area_twice) <= _EPSILON:
                raise ValueError(f"{label} must enclose a non-zero area")
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
        if area.get("_geometry_invalid") is True:
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
    total_config_points = 0
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
        polygons = (
            [geometry["coordinates"]]
            if geometry["type"] == "Polygon"
            else geometry["coordinates"]
        )
        total_config_points += sum(
            len(ring)
            for polygon in polygons
            for ring in polygon
        )
        if total_config_points > _MAX_TOTAL_CONFIG_POINTS:
            raise ValueError(
                "Combined service-area boundaries exceed "
                f"{_MAX_TOTAL_CONFIG_POINTS} coordinate points"
            )
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
    """Persist service-area records and their singleton enforcement policy."""
    current = get_service_area_config()
    validated = validate_service_area_config(raw)
    validated["version"] = max(
        current.get("version", 1), validated["version"]
    ) + 1

    try:
        policy = GeoServiceAreaPolicy.query.filter_by(
            policy_key="default", is_deleted=False
        ).first()
        if policy is None:
            policy = GeoServiceAreaPolicy(
                policy_key="default",
                enforcement_enabled=validated["enabled"],
                allow_cross_area_routes=validated["allow_cross_area_routes"],
                policy_version=validated["version"],
                updated_by=updated_by,
            )
            db.session.add(policy)
        else:
            policy.enforcement_enabled = validated["enabled"]
            policy.allow_cross_area_routes = validated["allow_cross_area_routes"]
            policy.policy_version = validated["version"]
            policy.updated_by = updated_by

        existing_records = GeoServiceArea.query.filter(
            GeoServiceArea.is_deleted.is_(False)
        ).all()
        existing_by_slug = {record.slug: record for record in existing_records}
        retained_slugs = set()

        for area in validated["areas"]:
            slug = area["id"]
            record = existing_by_slug.get(slug)
            if record is None:
                # Restore a soft-deleted slug rather than create a duplicate.
                record = GeoServiceArea.query.filter_by(slug=slug).first()
            if record is None:
                record = GeoServiceArea(
                    slug=slug,
                    name=area["name"],
                    country_code=area["country_code"] or None,
                    active=area["active"],
                    services=area["services"],
                    geometry=area["geometry"],
                    created_by=updated_by,
                    updated_by=updated_by,
                )
                db.session.add(record)
            else:
                record.is_deleted = False
                record.deleted_at = None
                record.name = area["name"]
                record.country_code = area["country_code"] or None
                record.active = area["active"]
                record.services = area["services"]
                record.geometry = area["geometry"]
                record.updated_by = updated_by
            retained_slugs.add(slug)

        # Preserve historic configuration but prevent omitted records from
        # remaining eligible. No raw DELETE is performed.
        for record in existing_records:
            if record.slug not in retained_slugs:
                record.active = False
                record.is_deleted = True
                record.deleted_at = db.func.now()
                record.updated_by = updated_by

        db.session.commit()
        return validated
    except SQLAlchemyError as exc:
        db.session.rollback()
        if not _is_missing_geofence_table(exc):
            raise

        # Temporary compatibility only: until the owner runs the generated
        # migration, preserve the previous JSON storage contract. This path
        # automatically stops being used once both GEO tables exist.
        SystemConfig.set(
            SERVICE_AREA_CONFIG_KEY,
            validated,
            value_type="json",
            category="geo",
            description="Legacy transition for owner-managed service areas",
            updated_by=updated_by,
        )
        return validated
