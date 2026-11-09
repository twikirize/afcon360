"""Driver-scoped, privacy-preserving Transport demand aggregation."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict

from app.geo.activity import aggregate_cells
from app.geo.services import LOCATION_TTL_SECONDS, straight_line_distance_m
from app.geo.validation import is_fresh, normalize_point
from app.transport.services.booking_service import booking_request_points
from app.utils.exceptions import ValidationError

DRIVER_DEMAND_WINDOW_HOURS = 24
DRIVER_DEMAND_RADIUS_M = 25_000.0
DRIVER_DEMAND_MIN_CELL_REQUESTS = 3


def get_driver_demand_cells(
    profile: Any,
    *,
    now: datetime | None = None,
) -> Dict[str, Any]:
    """Return only aggregated recent demand near this driver's fresh location.

    The last published driver location is the only geographic anchor. A
    missing, invalid, stale or future-dated position returns no cells.
    Individual booking pickup points are filtered around that position before
    aggregation. The output contains cell centers and thresholded request
    counts only; it never includes booking identifiers, raw pickup points,
    fare values, driver supply or dispatch recommendations.
    """
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    else:
        current = current.astimezone(timezone.utc)

    computed_at = current.isoformat()

    def unavailable() -> Dict[str, Any]:
        return {
            "success": True,
            "state": "location_unavailable",
            "cells": [],
            "computed_at": computed_at,
        }

    if profile is None or bool(getattr(profile, "is_deleted", False)):
        return unavailable()

    location = getattr(profile, "last_location", None)
    updated_at = getattr(profile, "location_updated_at", None)
    if (
        not isinstance(location, dict)
        or not isinstance(updated_at, datetime)
    ):
        return unavailable()

    if updated_at.tzinfo is None:
        updated_at = updated_at.replace(tzinfo=timezone.utc)
    else:
        updated_at = updated_at.astimezone(timezone.utc)

    try:
        driver_point = normalize_point(
            location.get("latitude"),
            location.get("longitude"),
            timestamp=updated_at,
        )
    except (TypeError, ValueError, ValidationError):
        return unavailable()

    # A future timestamp cannot be treated as a fresh current position.
    age_seconds = (current - updated_at).total_seconds()
    if age_seconds < 0 or not is_fresh(
        driver_point, LOCATION_TTL_SECONDS, now=current
    ):
        return unavailable()

    window_start = current - timedelta(hours=DRIVER_DEMAND_WINDOW_HOURS)
    points, skipped_invalid = booking_request_points(window_start, current)

    # Filter individual points around the driver's current area BEFORE
    # aggregation, so activity in other cities cannot consume the cell cap.
    nearby_points = []
    for latitude, longitude, _tag in points:
        try:
            candidate = normalize_point(latitude, longitude)
        except (TypeError, ValueError, ValidationError):
            skipped_invalid += 1
            continue

        if straight_line_distance_m(driver_point, candidate) <= DRIVER_DEMAND_RADIUS_M:
            nearby_points.append((
                candidate.latitude,
                candidate.longitude,
                None,
            ))

    aggregated = aggregate_cells(nearby_points)
    cells = [
        {
            "center": cell["center"],
            "request_count": cell["count"],
        }
        for cell in aggregated["cells"]
        if cell["count"] >= DRIVER_DEMAND_MIN_CELL_REQUESTS
    ]

    return {
        "success": True,
        "state": "available" if cells else "no_recent_demand",
        "cells": cells,
        "window": {
            "since": window_start.isoformat(),
            "until": current.isoformat(),
        },
        "computed_at": computed_at,
        "skipped_invalid": skipped_invalid + aggregated["skipped_invalid"],
        "truncated": aggregated["truncated"],
    }


__all__ = [
    "DRIVER_DEMAND_WINDOW_HOURS",
    "DRIVER_DEMAND_RADIUS_M",
    "DRIVER_DEMAND_MIN_CELL_REQUESTS",
    "get_driver_demand_cells",
]
