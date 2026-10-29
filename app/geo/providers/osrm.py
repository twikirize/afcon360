# app/geo/providers/osrm.py
"""
AFCON360 GEO - OSRM routing adapter.

Wire contract (OSRM HTTP API):
- GET {base_url}/route/v1/{profile}/{lon},{lat};{lon},{lat}
  ?overview=full&geometries=geojson&alternatives=false&steps=false
- Response {"code": "Ok", "routes": [{"distance": meters, "duration":
  seconds, "geometry": {"coordinates": [[lon, lat], ...]}}]}.
- Coordinates are longitude-first on the wire; converted to latitude-first
  GeoPoints at this boundary.

Profile mapping is explicit because OSRM's URL profile must match the
server's configured profile. The public demo only serves ``driving``;
motorcycle and foot require a self-hosted OSRM profile and an operator
mapping. An unmapped request profile is a truthful unresolved result, not
a silent car route.

Failure behavior matches Valhalla: disabled, timeout, HTTP error, or
malformed payload returns RouteResult(resolved=False, provider="osrm").
No retries. Import, construction, and is_available() perform no I/O.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List

import requests

from app.geo.interfaces import GeoPoint, RouteResult, RoutingProvider
from app.geo.providers.base import BaseProvider
from app.utils.exceptions import ValidationError
from app.utils.validators import TransportValidators

logger = logging.getLogger(__name__)


def _default_profile_map() -> Dict[str, str]:
    return {"auto": "driving", "driving": "driving"}


@dataclass
class OSRMConfig:
    base_url: str = ""
    timeout_s: float = 10.0
    enabled: bool = False
    profile_map: Dict[str, str] = field(default_factory=_default_profile_map)


class OSRMRouter(BaseProvider, RoutingProvider):
    """OSRM adapter. Live when configured; truthful miss otherwise."""

    name = "osrm"
    user_agent = "AFCON360-router/1.0"

    def __init__(self, config: OSRMConfig | None = None):
        self.config = config or OSRMConfig()

    def is_available(self) -> bool:
        return bool(self.config.enabled and self.config.base_url)

    @staticmethod
    def _validate_point(point: GeoPoint, name: str) -> None:
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
        osrm_profile = self.config.profile_map.get(profile)
        if not self.is_available() or not osrm_profile:
            return RouteResult(distance_m=0.0, duration_s=0.0,
                               provider=self.name, resolved=False)
        coordinates = (
            f"{origin.longitude},{origin.latitude};"
            f"{destination.longitude},{destination.latitude}"
        )
        url = (self.config.base_url.rstrip("/")
               + f"/route/v1/{osrm_profile}/{coordinates}")
        params = {
            "overview": "full",
            "geometries": "geojson",
            "alternatives": "false",
            "steps": "false",
        }
        try:
            response = requests.get(
                url, params=params, timeout=self.config.timeout_s,
                headers={"User-Agent": self.user_agent})
            response.raise_for_status()
            payload = response.json()
            if payload.get("code") != "Ok":
                raise ValueError("OSRM code is not Ok")
            routes = payload.get("routes")
            if not isinstance(routes, list) or not routes:
                raise ValueError("OSRM response has no routes")
            route = routes[0]
            distance_m = float(route["distance"])
            duration_s = float(route["duration"])
            geometry: List[GeoPoint] = []
            coordinates = (route.get("geometry") or {}).get("coordinates")
            if isinstance(coordinates, list):
                for pair in coordinates:
                    lng, lat = float(pair[0]), float(pair[1])
                    if TransportValidators.validate_coordinates(lat, lng):
                        geometry.append(
                            GeoPoint(latitude=lat, longitude=lng))
            return RouteResult(distance_m=distance_m,
                               duration_s=duration_s,
                               geometry=geometry,
                               provider=self.name, resolved=True)
        except Exception as exc:
            logger.warning("OSRM route request failed: %s",
                           type(exc).__name__)
            return RouteResult(distance_m=0.0, duration_s=0.0,
                               provider=self.name, resolved=False)

    def matrix(self, origins: List[GeoPoint],
               destinations: List[GeoPoint]) -> List[List[RouteResult]]:
        return [[RouteResult(distance_m=0.0, duration_s=0.0,
                             provider=self.name, resolved=False)
                 for _ in destinations] for _ in origins]
