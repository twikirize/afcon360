# app/geo/sql.py
"""
AFCON360 GEO - database-side canonical spatial expressions (SQLAlchemy).

Why this module exists: some consumers filter database-side (WHERE radius),
where calling Python straight_line_distance_m() per row would destroy query
scalability. This module owns the canonical SQL form of the great-circle
contract so domains never hand-roll trigonometric SQL again.

Contract:
- Spherical law of cosines, identical great-circle semantics to
  straight_line_distance_m() (haversine). The two formulas agree to ~1e-9
  relative at kilometre scales; acos degrades only at sub-metre scales,
  irrelevant for radius filtering.
- Output is KILOMETRES (named *_km_expr). GEO's canonical unit remains
  metres in Python; the km view exists because Accommodation's search
  contract (radius_km, distance <= radius_km) is kilometre-based.
  The unit is in the name so no caller can mistake it.
- Inputs are (latitude, longitude) floats in degrees, validated by the
  caller (Accommodation parses params the same way it always has).
- Usage is filter-only: `q.filter(expr <= radius_km)`. GEO never decides
  business filtering, ordering, or result shape.
"""

from __future__ import annotations

from sqlalchemy import func
from sqlalchemy.sql.elements import BinaryExpression

# Kilometre view of the canonical earth radius (cf. EARTH_RADIUS_M).
# Integer literal so rendered SQL is byte-identical to the legacy inline
# expression this builder replaces (`6371 * acos(...)`; Postgres coerces
# integer * double precision to double precision either way).
EARTH_RADIUS_KM = 6371


def straight_line_distance_km_expr(lat_col, lng_col,
                                   latitude: float,
                                   longitude: float) -> BinaryExpression:
    """Great-circle distance from (latitude, longitude) to row columns.

    Returns a SQLAlchemy expression evaluating to kilometres. `lat_col`
    / `lng_col` are column expressions (e.g. Property.latitude /
    Property.longitude); `latitude` / `longitude` are degree floats.
    `func.least(1.0, ...)` clamps floating-point overshoot so acos never
    receives an out-of-domain argument on identical points.
    """
    return (
        EARTH_RADIUS_KM * func.acos(
            func.least(1.0,
                       func.cos(func.radians(latitude)) *
                       func.cos(func.radians(lat_col)) *
                       func.cos(func.radians(lng_col) -
                                func.radians(longitude)) +
                       func.sin(func.radians(latitude)) *
                       func.sin(func.radians(lat_col)))
        )
    )


__all__ = ["EARTH_RADIUS_KM", "straight_line_distance_km_expr"]
