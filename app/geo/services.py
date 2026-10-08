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
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.core.validators import validate_coordinates
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


def geoapify_needs_secondary(hits: List[GeocodeResult]) -> bool:
    """Evidence-based weak/ambiguous trigger for conditional Photon help.

    Explicit v1 policy, testable, no invented composite score:
    - exactly ONE candidate (a list lets the rider choose; zero is the
      honest no-result path), AND
    - positive weakness evidence from the provider's own signals:
      ``match_type`` present and not ``"full_match"``, OR ``confidence``
      present and below 0.5.
    Absent signals never trigger (weakness must be evidenced, not
    assumed). Thresholds are v1 pending bake-off calibration (§16).
    """
    if len(hits) != 1:
        return False
    raw = getattr(hits[0], "raw", None)
    quality = raw.get("geoapify_quality") if isinstance(raw, dict) else None
    if not isinstance(quality, dict):
        return False
    match_type = quality.get("match_type")
    if isinstance(match_type, str) and match_type != "full_match":
        return True
    confidence = quality.get("confidence")
    if (isinstance(confidence, (int, float))
            and not isinstance(confidence, bool)
            and confidence < 0.5):
        return True
    return False


def reverse_identity_presentable(result: GeocodeResult) -> bool:
    """Provider-neutral reverse-display suitability (explicit, testable).

    Decides whether a reverse result may be SHOWN as a rider-facing
    identity. Ground rules, all provider-supplied (no distance use —
    snap thresholds belong to the future quality node):
    - unresolved or blank display_name -> False (unknown stays unknown);
    - Geoapify signals present -> False when ``result_type`` is
      ``"unknown"``, when no ``formatted`` text exists, or when the
      feature is a water body (``ocean`` key); otherwise True;
    - other providers (no type/water signals, e.g. Photon) -> True iff
      display_name is non-empty. Documented limitation: a named water
      feature without those signals cannot be filtered here.
    Never invents identity; never touches coordinates or source/method.
    """
    if result is None or not bool(getattr(result, "resolved", False)):
        return False
    display = getattr(result, "display_name", "") or ""
    if not isinstance(display, str) or not display.strip():
        return False
    raw = getattr(result, "raw", None)
    quality = (raw.get("geoapify_quality")
               if isinstance(raw, dict) else None)
    if not isinstance(quality, dict):
        return True
    if quality.get("result_type") == "unknown":
        return False
    if not quality.get("formatted_present"):
        return False
    if quality.get("is_water"):
        return False
    return True


class GeocodingService:
    """
    GEO geocoding facade with provider chain: Geoapify (primary), then
    configured fallbacks (public Photon best-effort), then truthful miss.

    Policy (locked):
    A. operational failure (timeout, network, 429/5xx/any HTTP error,
       unusable shape, unavailable) -> next provider (ROLE A fallback);
    B. valid success with useful candidates -> return them verbatim
       (no ranking fusion, no merged lists, no double query);
    C. valid success with zero useful candidates -> honest no-result,
       NO automatic fallback (explicit Map / known-place recovery);
    D. valid but weak/ambiguous single candidate (geoapify_needs_secondary)
       -> conditional Photon supplement appended AFTER the Geoapify hits,
       each carrying its answering provider name (ROLE B assistance).
    Every result carries its answering provider's name, so downstream
    provenance always identifies who actually resolved the candidate.
    """

    def __init__(self, provider=None, fallbacks=None):
        self._provider = provider
        self._fallbacks = tuple(
            p for p in (fallbacks or ()) if p is not None)

    @property
    def provider_name(self) -> str:
        return "unresolved" if self._provider is None else str(
            getattr(self._provider, "name", "custom"))

    def _chain(self):
        if self._provider is not None:
            yield self._provider
        yield from self._fallbacks

    @staticmethod
    def _usable(provider) -> bool:
        available = getattr(provider, "is_available", None)
        if callable(available):
            try:
                return bool(available())
            except Exception:
                return False
        return True

    def _fallback_hits(self, query: str,
                       limit: int) -> List[GeocodeResult]:
        """ROLE A: first useful fallback answer wins, verbatim."""
        from app.geo.providers.base import ProviderFailure
        for provider in list(self._chain())[1:]:
            if not self._usable(provider):
                continue
            try:
                hits = provider.geocode(query, limit=limit)
            except ProviderFailure as exc:
                logger.warning("GEO fallback provider %s failed: %s",
                               getattr(provider, "name", "custom"), exc)
                continue
            except ValidationError:
                raise
            except Exception as exc:
                logger.warning("GEO fallback provider %s failed: %s",
                               getattr(provider, "name", "custom"),
                               type(exc).__name__)
                continue
            if hits:
                return list(hits)
        return []

    def geocode(self, query: str, limit: int = 5) -> List[GeocodeResult]:
        from app.geo.providers.base import ProviderFailure
        chain = list(self._chain())
        if not chain:
            logger.info("GEO geocode unresolved (no provider yet): %r", query)
            return []
        primary = chain[0]
        if self._usable(primary):
            try:
                hits = primary.geocode(query, limit=limit)
            except ProviderFailure as exc:
                logger.warning("GEO primary provider %s failed: %s",
                               getattr(primary, "name", "custom"), exc)
                return self._fallback_hits(query, limit)
            except ValidationError:
                raise
            except Exception as exc:
                logger.warning("GEO primary provider %s failed: %s",
                               getattr(primary, "name", "custom"),
                               type(exc).__name__)
                return self._fallback_hits(query, limit)
            if hits:
                hits = list(hits)
                if (getattr(primary, "name", "") == "geoapify"
                        and geoapify_needs_secondary(hits)):
                    extra = self._fallback_hits(query, limit)
                    if extra:
                        logger.info(
                            "GEO secondary assistance: photon supplements "
                            "weak geoapify hit for %r", query)
                        return hits + extra
                return hits
            logger.info("GEO primary provider %s honest no-result: %r",
                        getattr(primary, "name", "custom"), query)
            return []
        return self._fallback_hits(query, limit)

    def reverse(self, point: GeoPoint) -> GeocodeResult:
        for provider in self._chain():
            if not self._usable(provider):
                continue
            try:
                result = provider.reverse(point)
            except ValidationError:
                raise
            except Exception as exc:
                logger.warning("GEO reverse provider %s failed: %s",
                               getattr(provider, "name", "custom"),
                               type(exc).__name__)
                continue
            if result is not None and bool(
                    getattr(result, "resolved", False)):
                return result
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

    Provider order (locked): Geoapify first when the operator explicitly
    enabled it AND supplied an API key; public Photon as best-effort
    fallback when explicitly enabled + configured; otherwise the
    truthful-miss service. Callers check `resolved` / emptiness on every
    result, and per-result `provider` names the answering provider.
    """
    providers = []
    geoapify = getattr(config, "geoapify", None)
    if (bool(getattr(geoapify, "enabled", False))
            and str(getattr(geoapify, "api_key", "") or "")):
        from app.geo.providers.geoapify import GeoapifyGeocoder
        providers.append(GeoapifyGeocoder(geoapify))
    photon = getattr(config, "photon", None)
    enabled = bool(getattr(photon, "enabled", False))
    base_url = str(getattr(photon, "base_url", "") or "")
    if enabled and base_url:
        from app.geo.providers.photon import PhotonGeocoder
        providers.append(PhotonGeocoder(photon))
    if not providers:
        return GeocodingService()
    return GeocodingService(provider=providers[0],
                            fallbacks=providers[1:])


def geocode_result_from_candidate(candidate: Any) -> GeocodeResult:
    """Rebuild a resolved GeocodeResult from one search-result echo.

    The rider location picker receives items of the ``GET
    /geo/api/geocode`` success payload (``label`` / ``latitude`` /
    ``longitude`` / ``provider`` + optional ``osm_type`` / ``osm_id``)
    and echoes the selected one back in a hidden form field.  This
    function is the ONLY server-side path that turns that echo into
    provider evidence for a ``source="search"`` canonical snapshot (H2:
    the builder refuses a search claim without resolved provider
    identity).

    Pure: no network, no Flask context, no I/O.

    Contract:
    - ``candidate`` must be a Mapping.
    - ``provider`` must be a non-empty string and must NOT be
      ``"unresolved"`` - an unresolved claim carries no evidence and is
      refused rather than laundered into a provider identity.
    - ``latitude`` / ``longitude`` must be real numbers (bool and
      string are rejected, never coerced), finite, and within
      [-90, 90] / [-180, 180] via the canonical raising validator.
    - ``raw`` keeps ONLY the OSM provenance datum keys actually present
      (``osm_type`` / ``osm_id``); nothing else is ever copied.
    - Any violation raises ``ValidationError``.  Never fabricates
      coordinates or provider identity.
    """
    if not isinstance(candidate, Mapping):
        raise ValidationError(
            message="geocode candidate must be a mapping with "
                    "label/latitude/longitude/provider",
            field="geocode",
        )

    provider = candidate.get("provider")
    if not isinstance(provider, str) or not provider.strip():
        raise ValidationError(
            message="geocode candidate requires a non-empty provider",
            field="geocode",
        )
    provider = provider.strip()
    if provider == "unresolved":
        raise ValidationError(
            message="geocode candidate provider 'unresolved' carries no "
                    "evidence; refusing to build provider identity",
            field="geocode",
        )

    latitude_raw = candidate.get("latitude")
    longitude_raw = candidate.get("longitude")
    numbers: Dict[str, float] = {}
    for name, value in (("latitude", latitude_raw),
                        ("longitude", longitude_raw)):
        # Raw-before-float safety (UI-LOC-02A): bool and non-numeric
        # input is rejected here, never laundered by float().
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValidationError(
                message=f"geocode candidate {name} must be a number, "
                        f"got {value!r}",
                field="geocode",
            )
        try:
            number = float(value)
        except (OverflowError, ValueError) as exc:
            raise ValidationError(
                message=f"geocode candidate {name} must be finite, "
                        f"got {value!r}",
                field="geocode",
            ) from exc
        if not math.isfinite(number):
            raise ValidationError(
                message=f"geocode candidate {name} must be finite, "
                        f"got {value!r}",
                field="geocode",
            )
        numbers[name] = number

    # Canonical raising range validator (same one location_snapshot.py
    # and the booking seam use).
    validate_coordinates(numbers["latitude"], numbers["longitude"])

    label = candidate.get("label")
    raw: Dict[str, Any] = {}
    for key in ("osm_type", "osm_id"):
        value = candidate.get(key)
        if value is not None:
            raw[key] = value

    return GeocodeResult(
        latitude=numbers["latitude"],
        longitude=numbers["longitude"],
        display_name=label if isinstance(label, str) else "",
        raw=raw,
        provider=provider,
        resolved=True,
    )


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
    "geocode_result_from_candidate",
    "geoapify_needs_secondary",
    "reverse_identity_presentable",
]
