# app/geo/providers/graphhopper.py
"""
AFCON360 GEO - GraphHopper routing adapter (hosted or self-hosted).

Wire contract:
- GET {base_url}/route
  params: repeated point=lat,lon, profile, points_encoded=false, key
- Response paths[0].distance is meters, paths[0].time is milliseconds,
  paths[0].points is a GeoJSON LineString ([lon, lat] pairs) when
  points_encoded=false.

GraphHopper can run hosted with an API key or self-hosted from an OSM
extract. Profiles are mapped explicitly (car/motorcycle/foot/bike); an
unmapped profile is a truthful unresolved result. No retries; the API key
is never logged.
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
    return {
        "auto": "car",
        "motorcycle": "motorcycle",
        "pedestrian": "foot",
        "bicycle": "bike",
    }


@dataclass
class GraphHopperConfig:
    base_url: str = "https://graphhopper.com/api/1"
    api_key: str = ""
    timeout_s: float = 10.0
    enabled: bool = False
    profile_map: Dict[str, str] = field(default_factory=_default_profile_map)


class GraphHopperRouter(BaseProvider, RoutingProvider):
    """GraphHopper adapter. Live when configured; truthful miss otherwise."""

    name = "graphhopper"
    user_agent = "AFCON360-router/1.0"

    def __init__(self, config: GraphHopperConfig | None = None):
        self.config = config or GraphHopperConfig()

    def is_available(self) -> bool:
        return bool(self.config.enabled and self.config.base_url
                    and self.config.api_key)

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
        gh_profile = self.config.profile_map.get(profile)
        if not self.is_available() or not gh_profile:
            return RouteResult(distance_m=0.0, duration_s=0.0,
                               provider=self.name, resolved=False)
        params = {
            "point": [
                f"{origin.latitude},{origin.longitude}",
                f"{destination.latitude},{destination.longitude}",
            ],
            "profile": gh_profile,
            "points_encoded": "false",
            "locale": "en",
            "key": self.config.api_key,
        }
        url = self.config.base_url.rstrip("/") + "/route"
        try:
            response = requests.get(
                url, params=params, timeout=self.config.timeout_s,
                headers={"User-Agent": self.user_agent})
            response.raise_for_status()
            payload = response.json()
            paths = payload.get("paths")
            if not isinstance(paths, list) or not paths:
                raise ValueError("GraphHopper response has no paths")
            path = paths[0]
            distance_m = float(path["distance"])
            duration_s = float(path["time"]) / 1000.0
            points = (path.get("points") or {}).get("coordinates")
            geometry: List[GeoPoint] = []
            if isinstance(points, list):
                for pair in points:
                    lng, lat = float(pair[0]), float(pair[1])
                    if TransportValidators.validate_coordinates(lat, lng):
                        geometry.append(
                            GeoPoint(latitude=lat, longitude=lng))
            return RouteResult(distance_m=distance_m,
                               duration_s=duration_s,
                               geometry=geometry,
                               provider=self.name, resolved=True)
        except Exception as exc:
            logger.warning("GraphHopper route request failed: %s",
                           type(exc).__name__)
            return RouteResult(distance_m=0.0, duration_s=0.0,
                               provider=self.name, resolved=False)

    def matrix(self, origins: List[GeoPoint],
               destinations: List[GeoPoint]) -> List[List[RouteResult]]:
        return [[RouteResult(distance_m=0.0, duration_s=0.0,
                             provider=self.name, resolved=False)
                 for _ in destinations] for _ in origins]
