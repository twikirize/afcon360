# app/geo/providers/valhalla.py
"""
AFCON360 GEO - Valhalla routing adapter.

Locked stack: Valhalla is the primary routing engine (OSRM optional later).

Behavior:
- Configured + enabled + reachable Valhalla → normalized road RouteResult
  (resolved=True, provider="valhalla").
- Anything else (disabled, unconfigured, timeout, HTTP error, malformed
  response) → truthful unresolved RouteResult (resolved=False). Domains
  MUST treat resolved=False as "no road data", never as road distance.
- Network happens ONLY inside route()/matrix(). Import, construction,
  is_available(), and health checks perform zero I/O.
- No retries: provider failures must not produce runaway request loops.

Valhalla wire details assumed (documented public /route contract):
- POST {base_url}/route, JSON {"locations": [{"lat", "lon"} x2],
  "costing": profile}. Note: Valhalla uses lat-first "lat"/"lon" keys,
  matching AFCON360's latitude-first convention — no axis swap.
- Response trip.summary.length is KILOMETRES, trip.summary.time is
  SECONDS. Leg shapes are precision-6 encoded polylines ([lng,lat] pairs
  after decoding — converted back to latitude-first GeoPoints here).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import List, Tuple

import requests

from app.geo.interfaces import GeoPoint, RouteResult, RoutingProvider
from app.geo.providers.base import BaseProvider
from app.utils.exceptions import ValidationError
from app.utils.validators import TransportValidators

logger = logging.getLogger(__name__)


@dataclass
class ValhallaConfig:
    base_url: str = ""
    timeout_s: float = 10.0
    enabled: bool = False  # disabled until operator configures endpoint


def _decode_polyline(shape: str, precision: int = 6) -> List[Tuple[float, float]]:
    """Decode an encoded polyline to [(latitude, longitude), ...].

    Precision 6 is Valhalla's shape default. Raises ValueError on
    truncated input so callers can map it to an unresolved result.
    """
    factor = 10 ** precision
    points: List[Tuple[float, float]] = []
    index = 0
    lat = 0
    lng = 0
    size = len(shape)
    while index < size:
        for axis in ("lat", "lng"):
            shift = 0
            value = 0
            while True:
                if index >= size:
                    raise ValueError("Truncated polyline shape")
                byte = ord(shape[index]) - 63
                index += 1
                value |= (byte & 0x1F) << shift
                shift += 5
                if byte < 0x20:
                    break
            delta = ~(value >> 1) if (value & 1) else (value >> 1)
            if axis == "lat":
                lat += delta
            else:
                lng += delta
        points.append((lat / factor, lng / factor))
    return points


class ValhallaRouter(BaseProvider, RoutingProvider):
    """Valhalla adapter. Live when configured; truthful miss otherwise."""

    name = "valhalla"

    def __init__(self, config: ValhallaConfig | None = None):
        self.config = config or ValhallaConfig()

    def is_available(self) -> bool:
        return bool(self.config.enabled and self.config.base_url)

    @staticmethod
    def _validate_point(point: GeoPoint, name: str) -> None:
        """Reject out-of-range/non-numeric coordinates before any I/O."""
        try:
            valid = TransportValidators.validate_coordinates(
                point.latitude, point.longitude)
        except Exception:
            valid = False
        if not valid:
            raise ValidationError(
                f"Invalid {name}: latitude must be within [-90, 90] and "
                f"longitude within [-180, 180], got "
                f"({point.latitude!r}, {point.longitude!r})",
                field=name,
            )

    def route(self, origin: GeoPoint, destination: GeoPoint,
              profile: str = "auto") -> RouteResult:
        self._validate_point(origin, "origin")
        self._validate_point(destination, "destination")
        if not self.is_available():
            return RouteResult(distance_m=0.0, duration_s=0.0,
                               provider=self.name, resolved=False)
        payload = {
            "locations": [
                {"lat": origin.latitude, "lon": origin.longitude},
                {"lat": destination.latitude, "lon": destination.longitude},
            ],
            "costing": profile,
        }
        try:
            url = self.config.base_url.rstrip("/") + "/route"
            response = requests.post(url, json=payload,
                                     timeout=self.config.timeout_s)
            response.raise_for_status()
            trip = response.json()["trip"]
            summary = trip["summary"]
            distance_m = float(summary["length"]) * 1000.0
            duration_s = float(summary["time"])
            geometry: List[GeoPoint] = []
            for leg in trip.get("legs", []):
                shape = leg.get("shape")
                if shape:
                    geometry.extend(
                        GeoPoint(latitude=lat, longitude=lng)
                        for lat, lng in _decode_polyline(shape))
            return RouteResult(distance_m=distance_m,
                               duration_s=duration_s,
                               geometry=geometry,
                               provider=self.name, resolved=True)
        except Exception as e:
            logger.warning("Valhalla route request failed: %s", e)
            return RouteResult(distance_m=0.0, duration_s=0.0,
                               provider=self.name, resolved=False)

    def matrix(self, origins: List[GeoPoint],
               destinations: List[GeoPoint]) -> List[List[RouteResult]]:
        # DEFERRED: sources_to_targets has no current product requirement.
        # Interface-only until a matrix consumer is authorized.
        return [[RouteResult(distance_m=0.0, duration_s=0.0,
                             provider=self.name, resolved=False)
                 for _ in destinations] for _ in origins]
