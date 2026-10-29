# app/geo/providers/ors.py
"""
AFCON360 GEO - OpenRouteService (ORS) routing adapter.

Wire contract:
- POST {base_url}/v2/directions/{profile}/geojson
  header Authorization: {api_key}
  body {"coordinates": [[lon, lat], [lon, lat]]}
- Response FeatureCollection; features[0].properties.summary carries
  distance (meters) and duration (seconds); geometry is a LineString of
  [lon, lat] pairs.

ORS profiles are mapped explicitly (driving-car, foot-walking,
cycling-regular). ORS does not expose a public motorcycle profile, so a
motorcycle request is a truthful unresolved result rather than a silent
car route. No retries; the API key is never logged.
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
        "auto": "driving-car",
        "pedestrian": "foot-walking",
        "bicycle": "cycling-regular",
    }


@dataclass
class ORSConfig:
    base_url: str = "https://api.openrouteservice.org"
    api_key: str = ""
    timeout_s: float = 10.0
    enabled: bool = False
    profile_map: Dict[str, str] = field(default_factory=_default_profile_map)


class ORSRouter(BaseProvider, RoutingProvider):
    """OpenRouteService adapter. Live when configured; truthful miss."""

    name = "ors"
    user_agent = "AFCON360-router/1.0"

    def __init__(self, config: ORSConfig | None = None):
        self.config = config or ORSConfig()

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
        ors_profile = self.config.profile_map.get(profile)
        if not self.is_available() or not ors_profile:
            return RouteResult(distance_m=0.0, duration_s=0.0,
                               provider=self.name, resolved=False)
        url = (self.config.base_url.rstrip("/")
               + f"/v2/directions/{ors_profile}/geojson")
        payload = {
            "coordinates": [
                [origin.longitude, origin.latitude],
                [destination.longitude, destination.latitude],
            ],
        }
        try:
            response = requests.post(
                url, json=payload, timeout=self.config.timeout_s,
                headers={
                    "Authorization": self.config.api_key,
                    "User-Agent": self.user_agent,
                })
            response.raise_for_status()
            body = response.json()
            features = body.get("features")
            if not isinstance(features, list) or not features:
                raise ValueError("ORS response has no features")
            feature = features[0]
            summary = (feature.get("properties") or {}).get("summary") or {}
            distance_m = float(summary["distance"])
            duration_s = float(summary["duration"])
            coordinates = (feature.get("geometry") or {}).get("coordinates")
            geometry: List[GeoPoint] = []
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
            logger.warning("ORS route request failed: %s",
                           type(exc).__name__)
            return RouteResult(distance_m=0.0, duration_s=0.0,
                               provider=self.name, resolved=False)

    def matrix(self, origins: List[GeoPoint],
               destinations: List[GeoPoint]) -> List[List[RouteResult]]:
        return [[RouteResult(distance_m=0.0, duration_s=0.0,
                             provider=self.name, resolved=False)
                 for _ in destinations] for _ in origins]
