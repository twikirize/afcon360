# app/geo/activity.py
"""
AFCON360 GEO - domain-neutral demand/activity aggregation (roadmap GEO-17).

Answers geographic questions only (where is activity concentrated?
where are request signals concentrated?) over caller-supplied or
GEO-owned point streams. Business meaning stays with the owning
domain: GEO never decides which driver gets a trip, what a fare is,
whether surge applies, or which property/event ranks first.

Representation: fixed decimal grid cells (CELL_DECIMALS). A fixed
constant — not caller-supplied precision — so grouping is bounded and
deterministic. 2 decimals ≈ 1.1 km × 1.1 km at the equator.

Time windows are REQUIRED (since/until); there is no implicit default
window. Responses always echo the resolved window plus computed_at so
historical aggregates can never be mistaken for live state.

Zero new writes: activity derives from GEO-15 observations, demand
aggregates caller-supplied authoritative points (e.g. Transport
booking requests). No H3, no PostGIS, no ML — unevidenced at this
scale.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple

from app.geo.models import LocationObservation
from app.geo.realtime import ENTITY_TYPES
from app.utils.exceptions import ValidationError

CELL_DECIMALS = 2
MAX_CELLS = 200
# Query-safety cap (not retention semantics): bounds full-table scans.
MAX_WINDOW_DAYS = 31


def cell_key_for(latitude: Any, longitude: Any,
                 decimals: int = CELL_DECIMALS) -> str:
    """Deterministic grid-cell key for a coordinate pair (lat-first)."""
    try:
        lat = float(latitude)
        lng = float(longitude)
    except (TypeError, ValueError):
        raise ValidationError(
            f"Invalid cell coordinate: ({latitude!r}, {longitude!r})")
    if not (-90.0 <= lat <= 90.0 and -180.0 <= lng <= 180.0):
        raise ValidationError(
            f"Cell coordinate out of range: ({lat!r}, {lng!r})")
    parts = []
    for value in (lat, lng):
        text = f"{value:.{decimals}f}"
        if text == f"-0.{'0' * decimals}":
            text = f"0.{'0' * decimals}"
        parts.append(text)
    return ",".join(parts)


def cell_center(cell_key: str) -> Dict[str, float]:
    """Rounded center of a cell key (representation center, not a claim
    that activity sat exactly here)."""
    try:
        lat_s, lng_s = cell_key.split(",")
        return {"latitude": float(lat_s), "longitude": float(lng_s)}
    except (ValueError, AttributeError):
        raise ValidationError(f"Invalid cell key: {cell_key!r}") from None


def _valid_point(latitude: Any, longitude: Any) -> Optional[Tuple[float, float]]:
    try:
        lat = float(latitude)
        lng = float(longitude)
    except (TypeError, ValueError):
        return None
    if not (-90.0 <= lat <= 90.0 and -180.0 <= lng <= 180.0):
        return None
    if lat != lat or lng != lng:  # NaN guard (comparisons pass for NaN)
        return None
    return lat, lng


def aggregate_cells(points: Iterable[Tuple[Any, Any, Any]]) -> Dict[str, Any]:
    """Bin (latitude, longitude, tag) points into grid cells.

    tag groups within a cell (distinct count) or None to count only.
    Invalid coordinates are SKIPPED and counted (never raise, never
    fabricate). Deterministic order: count desc, cell_key asc. Capped
    at MAX_CELLS with an explicit truncated flag.
    """
    bins: Dict[str, Dict[str, Any]] = {}
    skipped_invalid = 0
    for latitude, longitude, tag in points:
        coords = _valid_point(latitude, longitude)
        if coords is None:
            skipped_invalid += 1
            continue
        key = cell_key_for(*coords)
        cell = bins.get(key)
        if cell is None:
            cell = {"key": key, "count": 0, "tags": set()}
            bins[key] = cell
        cell["count"] += 1
        if tag is not None:
            cell["tags"].add(tag)
    ranked = sorted(bins.values(),
                    key=lambda c: (-c["count"], c["key"]))
    truncated = len(ranked) > MAX_CELLS
    cells = [{
        "cell_key": cell["key"],
        "center": cell_center(cell["key"]),
        "count": cell["count"],
        "distinct": len(cell["tags"]),
    } for cell in ranked[:MAX_CELLS]]
    return {"cells": cells, "skipped_invalid": skipped_invalid,
            "truncated": truncated}


def parse_window(since: Any, until: Any) -> Tuple[datetime, datetime]:
    if since is None or until is None:
        raise ValueError("since and until are required (ISO-8601)")
    try:
        start = (since if isinstance(since, datetime)
                 else datetime.fromisoformat(str(since).strip()))
        end = (until if isinstance(until, datetime)
               else datetime.fromisoformat(str(until).strip()))
    except (ValueError, AttributeError):
        raise ValueError("since/until must be ISO-8601 datetimes") from None
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    if end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)
    if start > end:
        raise ValueError("since must not be after until")
    if (end - start).days > MAX_WINDOW_DAYS:
        raise ValueError(
            f"window exceeds {MAX_WINDOW_DAYS} days (query-safety cap)")
    return start, end


def _validate_bbox(bbox: Any) -> Optional[Dict[str, float]]:
    if bbox is None:
        return None
    if not isinstance(bbox, dict):
        raise ValueError("bbox must be an object")
    try:
        bounds = {k: float(bbox[k]) for k in (
            "min_latitude", "max_latitude", "min_longitude", "max_longitude")}
    except (KeyError, TypeError, ValueError):
        raise ValueError("bbox needs numeric min/max latitude/longitude") from None
    if not (-90.0 <= bounds["min_latitude"] <= bounds["max_latitude"] <= 90.0):
        raise ValueError("invalid latitude bounds")
    if not (-180.0 <= bounds["min_longitude"] <= bounds["max_longitude"] <= 180.0):
        raise ValueError("invalid longitude bounds")
    return bounds


def get_activity(entity_type: Optional[str] = None, *,
                 since: Any = None, until: Any = None,
                 bbox: Any = None) -> Dict[str, Any]:
    """Observation concentration over GEO-15 history (read-only).

    Counts observations (activity) and distinct public refs
    (active observed entities — NOT availability, which Transport
    owns) per grid cell. since/until required; no implicit window.
    """
    if entity_type is not None and entity_type not in ENTITY_TYPES:
        raise ValueError(f"Unsupported entity_type: {entity_type!r}")
    start, end = parse_window(since, until)
    bounds = _validate_bbox(bbox)

    query = LocationObservation.query.filter(
        LocationObservation.observed_at >= start,
        LocationObservation.observed_at <= end,
        LocationObservation.is_deleted == False,  # noqa: E712
    )
    if entity_type is not None:
        query = query.filter(
            LocationObservation.entity_type == entity_type)
    if bounds is not None:
        query = query.filter(
            LocationObservation.latitude >= bounds["min_latitude"],
            LocationObservation.latitude <= bounds["max_latitude"],
            LocationObservation.longitude >= bounds["min_longitude"],
            LocationObservation.longitude <= bounds["max_longitude"],
        )
    points = [(row.latitude, row.longitude, row.public_ref)
              for row in query.all()]
    agg = aggregate_cells(points)
    cells = [{
        "cell_key": cell["cell_key"],
        "center": cell["center"],
        "observation_count": cell["count"],
        "entity_count": cell["distinct"],
    } for cell in agg["cells"]]
    return {
        "cells": cells,
        "window": {"since": start.isoformat(), "until": end.isoformat()},
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "skipped_invalid": agg["skipped_invalid"],
        "truncated": agg["truncated"],
    }


__all__ = [
    "CELL_DECIMALS",
    "MAX_CELLS",
    "MAX_WINDOW_DAYS",
    "cell_key_for",
    "cell_center",
    "aggregate_cells",
    "get_activity",
    "parse_window",
]
