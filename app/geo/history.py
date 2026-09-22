# app/geo/history.py
"""
AFCON360 GEO - location observation history retrieval (roadmap GEO-15).

Domain-neutral read boundary over ``LocationObservation`` rows. Returns
chronological observations for one entity's public reference; never
exposes internal IDs.

Authorization lives with the caller (the HTTP view enforces it):
this module only validates scope/shape parameters.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.geo.models import LocationObservation
from app.geo.realtime import ENTITY_TYPES

DEFAULT_LIMIT = 100
MAX_LIMIT = 500


def _parse_bound(value: Any, name: str) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        bound = value
    elif isinstance(value, str) and value.strip():
        try:
            bound = datetime.fromisoformat(value.strip())
        except ValueError:
            raise ValueError(f"Invalid {name}: not ISO-8601") from None
    else:
        raise ValueError(f"Invalid {name}: must be ISO-8601 string")
    if bound.tzinfo is None:
        bound = bound.replace(tzinfo=timezone.utc)
    return bound


def get_observations(entity_type: str, public_ref: str, *,
                     since: Any = None, until: Any = None,
                     limit: Any = DEFAULT_LIMIT) -> List[Dict[str, Any]]:
    """Chronological observations for one entity (oldest first).

    Raises ValueError on invalid scope/shape so the caller maps it to
    400; unknown-but-wellformed references simply yield [] (the view
    404s unresolvable references before calling).
    """
    if entity_type not in ENTITY_TYPES:
        raise ValueError(f"Unsupported entity_type: {entity_type!r}")
    if not isinstance(public_ref, str) or not public_ref.strip():
        raise ValueError("public_ref must be a non-empty string")
    ref = public_ref.strip()
    if len(ref) > 64:
        raise ValueError("public_ref too long")
    try:
        count = int(limit)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        raise ValueError("Invalid limit: must be an integer") from None
    count = max(1, min(MAX_LIMIT, count))
    since_dt = _parse_bound(since, "since")
    until_dt = _parse_bound(until, "until")

    from app.extensions import db

    query = LocationObservation.query.filter(
        LocationObservation.entity_type == entity_type,
        LocationObservation.public_ref == ref,
        LocationObservation.is_deleted == False,  # noqa: E712
    )
    if since_dt is not None:
        query = query.filter(LocationObservation.observed_at >= since_dt)
    if until_dt is not None:
        query = query.filter(LocationObservation.observed_at <= until_dt)
    rows = (query.order_by(LocationObservation.observed_at.asc(),
                           LocationObservation.id.asc())
            .limit(count).all())
    return [
        {
            "public_id": row.public_id,
            "entity_type": row.entity_type,
            "public_ref": row.public_ref,
            "latitude": row.latitude,
            "longitude": row.longitude,
            "accuracy": row.accuracy,
            "observed_at": row.observed_at.isoformat(),
            "recorded_at": row.recorded_at.isoformat(),
            "source": row.source,
        }
        for row in rows
    ]


__all__ = ["DEFAULT_LIMIT", "MAX_LIMIT", "get_observations"]
