# app/transport/services/availability_service.py
"""
Single source of truth for "which vehicles are actually available right now".

Availability (as specified by the product owner):

    A vehicle is available for an on-demand ride if and only if
      1. it is active and not soft-deleted;
      2. it is currently linked to an active DriverVehicleHistory row
         (i.e., a driver is assigned to it right now);
      3. that driver is online, marked available, and approved;
      4. that driver's location observation is fresh (within TTL);
      5. NEITHER the driver NOR the vehicle is engaged on another
         active booking.

Callers (RideOptionsResource, future matching surface, admin dashboards)
all read from here so "available" can never mean two different things.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import and_, exists, func, select

from app.extensions import db
from app.transport.models import (
    Booking,
    BookingStatus,
    ComplianceStatus,
    DriverProfile,
    DriverVehicleHistory,
    Vehicle,
)
from app.transport.services.assignment_service import ACTIVE_ASSIGNMENT_STATUSES
from app.transport.services.tracking_service import TrackingService

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# The engagement predicate (used in both the counting query and the ETA query)
# ---------------------------------------------------------------------------

def _driver_engaged_elsewhere():
    """Exists-subquery: driver has an active booking other than this one."""
    return exists(
        select(Booking.id)
        .where(
            Booking.assigned_driver_id == DriverProfile.id,
            Booking.status.in_(ACTIVE_ASSIGNMENT_STATUSES),
            Booking.is_deleted.is_(False),
        )
    )


def _vehicle_engaged_elsewhere():
    """Exists-subquery: vehicle has an active booking."""
    return exists(
        select(Booking.id)
        .where(
            Booking.assigned_vehicle_id == Vehicle.id,
            Booking.status.in_(ACTIVE_ASSIGNMENT_STATUSES),
            Booking.is_deleted.is_(False),
        )
    )


def _freshness_cutoff() -> datetime:
    return datetime.now(timezone.utc) - timedelta(
        seconds=TrackingService.LOCATION_TTL_SECONDS
    )


def _available_vehicle_ids() -> List[int]:
    """IDs of vehicles that pass every availability gate right now.

    Kept separate from the counting query so callers that need the actual
    vehicles (ETA calculation, dispatch seeding) reuse the exact same
    predicate — no drift between "what we count" and "what we use".
    """
    fresh = _freshness_cutoff()
    stmt = (
        select(Vehicle.id)
        .join(
            DriverVehicleHistory,
            and_(
                DriverVehicleHistory.vehicle_id == Vehicle.id,
                DriverVehicleHistory.ended_at.is_(None),
                DriverVehicleHistory.is_deleted.is_(False),
            ),
        )
        .join(DriverProfile, DriverProfile.id == DriverVehicleHistory.driver_id)
        .where(
            Vehicle.is_deleted.is_(False),
            Vehicle.status == "active",
            DriverProfile.is_deleted.is_(False),
            DriverProfile.is_online.is_(True),
            DriverProfile.is_available.is_(True),
            DriverProfile.compliance_status == ComplianceStatus.APPROVED.value,
            DriverProfile.location_updated_at.isnot(None),
            DriverProfile.location_updated_at >= fresh,
            ~_driver_engaged_elsewhere(),
            ~_vehicle_engaged_elsewhere(),
        )
    )
    return [int(r[0]) for r in db.session.execute(stmt).all()]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def available_by_class() -> List[Dict[str, Any]]:
    """Available vehicle counts, min/max capacities, per vehicle class.

    One row per class that has at least one available vehicle right now.
    Empty list means nothing is available — the caller must render an
    honest empty state, not a fallback.
    """
    fresh = _freshness_cutoff()
    stmt = (
        select(
            Vehicle.vehicle_class,
            func.count(Vehicle.id).label("available_count"),
            func.min(Vehicle.passenger_capacity).label("cap_min"),
            func.max(Vehicle.passenger_capacity).label("cap_max"),
            func.min(Vehicle.luggage_capacity).label("lug_min"),
            func.max(Vehicle.luggage_capacity).label("lug_max"),
        )
        .join(
            DriverVehicleHistory,
            and_(
                DriverVehicleHistory.vehicle_id == Vehicle.id,
                DriverVehicleHistory.ended_at.is_(None),
                DriverVehicleHistory.is_deleted.is_(False),
            ),
        )
        .join(DriverProfile, DriverProfile.id == DriverVehicleHistory.driver_id)
        .where(
            Vehicle.is_deleted.is_(False),
            Vehicle.status == "active",
            DriverProfile.is_deleted.is_(False),
            DriverProfile.is_online.is_(True),
            DriverProfile.is_available.is_(True),
            DriverProfile.compliance_status == ComplianceStatus.APPROVED.value,
            DriverProfile.location_updated_at.isnot(None),
            DriverProfile.location_updated_at >= fresh,
            ~_driver_engaged_elsewhere(),
            ~_vehicle_engaged_elsewhere(),
        )
        .group_by(Vehicle.vehicle_class)
    )
    rows = db.session.execute(stmt).all()
    return [
        {
            "vehicle_class": row.vehicle_class,
            "available_count": int(row.available_count or 0),
            "capacity": {
                "min": int(row.cap_min or 0),
                "max": int(row.cap_max or 0),
            },
            "luggage": {
                "min": int(row.lug_min or 0),
                "max": int(row.lug_max or 0),
            },
        }
        for row in rows
    ]


# Planning speed for straight-line ETA. Not a routing product.
_PLANNING_SPEED_KMH = 25.0


def nearest_eta_minutes_for_class(
    vehicle_class: str,
    pickup: Optional[Tuple[float, float]],
) -> Optional[int]:
    """Straight-line ETA to the nearest AVAILABLE vehicle of this class.

    Uses the same availability predicate as ``available_by_class`` — the
    vehicle that supplies the ETA is a vehicle the rider could actually
    ride, not just a vehicle that exists.
    """
    if pickup is None:
        return None
    try:
        from app.geo.interfaces import GeoPoint
        from app.geo.services import straight_line_distance_m
    except Exception:
        return None

    lat_p, lng_p = pickup
    if not (-90.0 <= lat_p <= 90.0 and -180.0 <= lng_p <= 180.0):
        return None

    fresh = _freshness_cutoff()
    stmt = (
        select(DriverProfile.last_location)
        .join(
            DriverVehicleHistory,
            and_(
                DriverVehicleHistory.driver_id == DriverProfile.id,
                DriverVehicleHistory.ended_at.is_(None),
                DriverVehicleHistory.is_deleted.is_(False),
            ),
        )
        .join(Vehicle, Vehicle.id == DriverVehicleHistory.vehicle_id)
        .where(
            Vehicle.is_deleted.is_(False),
            Vehicle.status == "active",
            Vehicle.vehicle_class == vehicle_class,
            DriverProfile.is_deleted.is_(False),
            DriverProfile.is_online.is_(True),
            DriverProfile.is_available.is_(True),
            DriverProfile.compliance_status == ComplianceStatus.APPROVED.value,
            DriverProfile.location_updated_at.isnot(None),
            DriverProfile.location_updated_at >= fresh,
            DriverProfile.last_location.isnot(None),
            ~_driver_engaged_elsewhere(),
            ~_vehicle_engaged_elsewhere(),
        )
    )
    origin = GeoPoint(lat_p, lng_p)
    best_km: Optional[float] = None
    for row in db.session.execute(stmt).all():
        loc = row.last_location or {}
        try:
            lat = float(loc.get("latitude"))
            lng = float(loc.get("longitude"))
        except (TypeError, ValueError):
            continue
        if not (-90.0 <= lat <= 90.0 and -180.0 <= lng <= 180.0):
            continue
        try:
            km = straight_line_distance_m(origin, GeoPoint(lat, lng)) / 1000.0
        except Exception:
            continue
        if best_km is None or km < best_km:
            best_km = km

    if best_km is None:
        return None
    return max(1, round((best_km / _PLANNING_SPEED_KMH) * 60))
