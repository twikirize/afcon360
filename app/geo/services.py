# app/geo/services.py
"""
AFCON360 GEO - domain-neutral foundation services (slice 1).

What lives here NOW (pure Python, no network, no DB, no Redis):
- canonical straight-line distance (haversine, radians-correct)
- duration → ETA conversion (explicit; NO distance×k heuristics here)
- location freshness boundary helper (shares TrackingService 300 s default)

What lives here LATER (behind interfaces, separate nodes):
- road routing (Valhalla adapter), geocoding (Photon adapter),
  Redis current-state + Postgres history, SSE delivery.

Function naming rule: straight-line results are ALWAYS named
`straight_line_*` so no caller can mistake them for road distance.
"""

from __future__ import annotations

import logging
import math
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.geo.interfaces import (GeocodeResult, GeoPoint, NearbyItem,
                                RouteResult)
from app.geo.validation import (is_fresh, normalize_location_payload,
                                normalize_point, validate_radius_m)
from app.utils.exceptions import ValidationError

logger = logging.getLogger(__name__)

# Canonical earth radius (meters) - single source for straight-line math.
EARTH_RADIUS_M = 6_371_000.0
# Freshness boundary shared with Transport TrackingService (300 s).
LOCATION_TTL_SECONDS = 300


# ---------------------------------------------------------------------------
# Straight-line distance (explicitly NOT road distance)
# ---------------------------------------------------------------------------

def straight_line_distance_m(origin: GeoPoint,
                             destination: GeoPoint) -> float:
    """
    Haversine great-circle distance in meters. Radians conversion is applied
    to ALL angular inputs (regression guard for the known Transport matching
    defect where degrees were passed to trig functions directly).
    """
    lat1 = math.radians(origin.latitude)
    lat2 = math.radians(destination.latitude)
    d_lat = math.radians(destination.latitude - origin.latitude)
    d_lng = math.radians(destination.longitude - origin.longitude)
    a = (math.sin(d_lat / 2) ** 2
         + math.cos(lat1) * math.cos(lat2) * math.sin(d_lng / 2) ** 2)
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(a))


def straight_line_distance_matrix_m(
        origins: List[GeoPoint],
        destinations: List[GeoPoint]) -> List[List[float]]:
    """Straight-line matrix (planning fallback; road matrix comes later)."""
    return [[straight_line_distance_m(o, d) for d in destinations]
            for o in origins]


# ---------------------------------------------------------------------------
# ETA (duration-based only - heuristics live in domains, never here)
# ---------------------------------------------------------------------------

def eta_from_duration(duration_s: float,
                      now: Optional[datetime] = None) -> datetime:
    """
    ETA = now + provider duration. `duration_s` must come from a routing
    engine (later) or an explicitly-labelled estimate - NEVER distance×k.
    """
    if duration_s < 0:
        raise ValidationError("Invalid duration: must be >= 0",
                              field="duration_s")
    ref = now or datetime.now(timezone.utc)
    from datetime import timedelta
    return ref + timedelta(seconds=duration_s)


# ---------------------------------------------------------------------------
# Location service (validation + freshness; storage arrives later)
# ---------------------------------------------------------------------------

class LocationService:
    """Shared location entry point. Storage backends attach in later nodes."""

    def normalize_update(self, payload: Dict[str, Any]) -> GeoPoint:
        """Validate + normalize an inbound location payload."""
        return normalize_location_payload(payload)

    def check_freshness(self, point: GeoPoint,
                        max_age_seconds: float = LOCATION_TTL_SECONDS,
                        now: Optional[datetime] = None) -> Dict[str, Any]:
        """Freshness verdict for a current-state point."""
        fresh = is_fresh(point, max_age_seconds, now=now)
        age_s: Optional[float] = None
        if point.timestamp is not None:
            ref = now or datetime.now(timezone.utc)
            ts = point.timestamp
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            age_s = (ref - ts).total_seconds()
        return {"fresh": fresh, "age_s": age_s,
                "max_age_s": max_age_seconds}


class RoutingService:
    """
    GEO routing facade. Until the Valhalla adapter node lands, every call
    returns a TRUTHFUL unresolved result: straight-line distance labelled
    provider="haversine-fallback", duration unknown (None). Domains MUST
    treat resolved=False as "no road data yet", never as road distance.
    """

    def __init__(self, provider=None):
        self._provider = provider

    @property
    def provider_name(self) -> str:
        return "unresolved" if self._provider is None else str(
            getattr(self._provider, "name", "custom"))

    def route(self, origin: GeoPoint, destination: GeoPoint,
              profile: str = "auto") -> RouteResult:
        if self._provider is not None:
            return self._provider.route(origin, destination, profile=profile)
        return RouteResult(
            distance_m=straight_line_distance_m(origin, destination),
            duration_s=0.0,
            geometry=[origin, destination],
            provider="haversine-fallback",
            resolved=False,
        )

    def matrix(self, origins: List[GeoPoint],
               destinations: List[GeoPoint]) -> List[List[RouteResult]]:
        if self._provider is not None:
            return self._provider.matrix(origins, destinations)
        table = straight_line_distance_matrix_m(origins, destinations)
        return [[RouteResult(distance_m=d, duration_s=0.0,
                             provider="haversine-fallback", resolved=False)
                 for d in row] for row in table]


class GeocodingService:
    """
    GEO geocoding facade. Until the Photon adapter node lands, returns
    truthful misses (never fake coordinates).
    """

    def __init__(self, provider=None):
        self._provider = provider

    @property
    def provider_name(self) -> str:
        return "unresolved" if self._provider is None else str(
            getattr(self._provider, "name", "custom"))

    def geocode(self, query: str, limit: int = 5) -> List[GeocodeResult]:
        if self._provider is not None:
            return self._provider.geocode(query, limit=limit)
        logger.info("GEO geocode unresolved (no provider yet): %r", query)
        return []

    def reverse(self, point: GeoPoint) -> GeocodeResult:
        if self._provider is not None:
            return self._provider.reverse(point)
        return GeocodeResult(provider="unresolved", resolved=False)


class NearbyService:
    """
    Shared proximity guard + ordering helper. Spatial query backend
    (PostGIS) attaches in a later node; this slice owns validation and
    distance ordering over caller-supplied candidates so domains stop
    re-implementing radius math immediately.

    Contract:
    - center/candidates are GeoPoint (latitude-first order).
    - radius_m is meters, guarded by validate_radius_m (> 0, <= 100 km).
    - boundary is inclusive: dist <= radius.
    - empty candidates -> [] (never None, never an error).
    - duplicates are kept (no dedupe: record identity belongs to the
      owning domain, GEO only sees coordinates).
    - results sort ascending by distance_m; ties keep input order
      (Python sort is stable).
    """

    @staticmethod
    def order_by_distance(center: GeoPoint,
                          candidates: List[GeoPoint],
                          radius_m: float,
                          limit: Optional[int] = None) -> List[NearbyItem]:
        radius = validate_radius_m(radius_m)
        if limit is not None:
            if (isinstance(limit, bool) or not isinstance(limit, int)
                    or limit <= 0):
                raise ValidationError(
                    f"Invalid limit: must be a positive integer, "
                    f"got {limit!r}",
                    field="limit",
                )
        hits: List[NearbyItem] = []
        for index, point in enumerate(candidates):
            dist = straight_line_distance_m(center, point)
            if dist <= radius:
                hits.append(NearbyItem(public_id=str(index),
                                       distance_m=dist, point=point))
        hits.sort(key=lambda h: h.distance_m)
        return hits[:limit] if limit is not None else hits

    @staticmethod
    def nearest(center: GeoPoint,
                candidates: List[GeoPoint],
                limit: int = 1) -> List[NearbyItem]:
        """Closest `limit` candidates with no radius gate.

        Use order_by_distance when a radius applies. Empty candidates
        -> []. Raises ValidationError on a non-positive limit.
        """
        if (isinstance(limit, bool) or not isinstance(limit, int)
                or limit <= 0):
            raise ValidationError(
                f"Invalid limit: must be a positive integer, "
                f"got {limit!r}",
                field="limit",
            )
        ranked = sorted(
            (NearbyItem(
                public_id=str(index),
                distance_m=straight_line_distance_m(center, point),
                point=point,
            ) for index, point in enumerate(candidates)),
            key=lambda h: h.distance_m,
        )
        return ranked[:limit]


def bounding_box(center: GeoPoint,
                 radius_m: float) -> Dict[str, float]:
    """Minimal lat/lng box containing the radius_m circle around center.

    Returns {min_latitude, max_latitude, min_longitude, max_longitude}
    in degrees, clamped to [-90, 90] / [-180, 180].

    Intended as a pre-filter for caller-side queries (SQL BETWEEN /
    candidate shortlist). Exact membership still requires
    straight_line_distance_m: box corners are farther than radius.
    """
    radius = validate_radius_m(radius_m)
    angular = radius / EARTH_RADIUS_M  # central angle, radians
    d_lat_deg = math.degrees(angular)
    cos_lat = math.cos(math.radians(center.latitude))
    if abs(cos_lat) < 1e-12:
        d_lng_deg = 180.0
    else:
        ratio = math.sin(angular) / abs(cos_lat)
        d_lng_deg = 180.0 if ratio >= 1.0 else math.degrees(
            math.asin(ratio))
    return {
        "min_latitude": max(-90.0, center.latitude - d_lat_deg),
        "max_latitude": min(90.0, center.latitude + d_lat_deg),
        "min_longitude": max(-180.0, center.longitude - d_lng_deg),
        "max_longitude": min(180.0, center.longitude + d_lng_deg),
    }


# ---------------------------------------------------------------------------
# Deep-lazy singletons (transport/__init__.py pattern)
# ---------------------------------------------------------------------------

_location_service: Optional[LocationService] = None
_routing_service: Optional[RoutingService] = None
_geocoding_service: Optional[GeocodingService] = None


def get_location_service() -> LocationService:
    global _location_service
    if _location_service is None:
        _location_service = LocationService()
    return _location_service


def get_routing_service() -> RoutingService:
    global _routing_service
    if _routing_service is None:
        _routing_service = RoutingService()
    return _routing_service


def get_geocoding_service() -> GeocodingService:
    global _geocoding_service
    if _geocoding_service is None:
        _geocoding_service = GeocodingService()
    return _geocoding_service


def build_routing_service(config) -> RoutingService:
    """Wire a RoutingService from a GeoConfig (no I/O at build time).

    Returns a Valhalla-backed service only when the operator explicitly
    enabled + configured the endpoint; otherwise the truthful-fallback
    service. Callers check `.resolved` on every result.
    """
    valhalla = getattr(config, "valhalla", None)
    enabled = bool(getattr(valhalla, "enabled", False))
    base_url = str(getattr(valhalla, "base_url", "") or "")
    if enabled and base_url:
        from app.geo.providers.valhalla import ValhallaRouter
        return RoutingService(provider=ValhallaRouter(valhalla))
    return RoutingService()


def build_geocoding_service(config) -> GeocodingService:
    """Wire a GeocodingService from a GeoConfig (no I/O at build time).

    Returns a Photon-backed service only when the operator explicitly
    enabled + configured the endpoint; otherwise the truthful-miss
    service. Callers check `resolved` / emptiness on every result.
    """
    photon = getattr(config, "photon", None)
    enabled = bool(getattr(photon, "enabled", False))
    base_url = str(getattr(photon, "base_url", "") or "")
    if enabled and base_url:
        from app.geo.providers.photon import PhotonGeocoder
        return GeocodingService(provider=PhotonGeocoder(photon))
    return GeocodingService()


__all__ = [
    "EARTH_RADIUS_M",
    "LOCATION_TTL_SECONDS",
    "LocationService",
    "RoutingService",
    "GeocodingService",
    "NearbyService",
    "bounding_box",
    "straight_line_distance_m",
    "straight_line_distance_matrix_m",
    "eta_from_duration",
    "get_location_service",
    "get_routing_service",
    "get_geocoding_service",
    "build_geocoding_service",
    "build_routing_service",
]
