# app/geo/providers/geoapify_routing.py
"""
AFCON360 GEO - Geoapify routing adapter.

Wire contract (Geoapify Routing API):
- GET {base_url}/v1/routing
  params {waypoints: "lat,lon|lat,lon", mode, apiKey}
- Response GeoJSON FeatureCollection; first feature properties carry
  distance (meters) and time (seconds); geometry.coordinates is a
  LineString of [longitude, latitude] pairs.

Mode mapping is explicit: auto -> drive, motorcycle -> motorcycle,
pedestrian -> walk, bicycle -> bicycle, scooter -> scooter, truck -> truck.
Geoapify's motorcycle mode is accepted by the hosted API; whether its
Uganda data actually differs from drive is a benchmark question, not an
adapter assumption.

Failure behavior matches the other routing adapters: disabled, missing
key, timeout, HTTP error, or malformed payload returns an unresolved
RouteResult. The API key is never logged. No retries.
"""

from __future__ import annotations

import logging
from typing import Dict, List

import requests

from app.geo.interfaces import GeoPoint, RouteResult, RoutingProvider
from app.geo.providers.base import BaseProvider
from app.geo.providers.geoapify import GeoapifyConfig
from app.utils.exceptions import ValidationError
from app.utils.validators import TransportValidators

logger = logging.getLogger(__name__)

_MODE_MAP: Dict[str, str] = {
    "auto": "drive",
    "driving": "drive",
    "motorcycle": "motorcycle",
    "pedestrian": "walk",
    "walking": "walk",
    "bicycle": "bicycle",
    "cycling": "bicycle",
    "scooter": "scooter",
    "truck": "truck",
}


class GeoapifyRouter(BaseProvider, RoutingProvider):
    """Geoapify routing adapter. Live when enabled with a key."""

    name = "geoapify"
    user_agent = "AFCON360-router/1.0"

    def __init__(self, config: GeoapifyConfig | None = None):
        self.config = config or GeoapifyConfig()

    def is_available(self) -> bool:
        return bool(self.config.enabled and self.config.api_key
                    and self.config.base_url)

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
        mode = _MODE_MAP.get(profile)
        if not self.is_available() or not mode:
            return RouteResult(distance_m=0.0, duration_s=0.0,
                               provider=self.name, resolved=False)
        params = {
            "waypoints": (f"{origin.latitude},{origin.longitude}|"
                          f"{destination.latitude},{destination.longitude}"),
            "mode": mode,
            "apiKey": self.config.api_key,
        }
        url = self.config.base_url.rstrip("/") + "/v1/routing"
        try:
            response = requests.get(
                url, params=params, timeout=self.config.timeout_s,
                headers={"User-Agent": self.user_agent})
            response.raise_for_status()
            payload = response.json()
            features = payload.get("features")
            if not isinstance(features, list) or not features:
                raise ValueError("Geoapify response has no features")
            feature = features[0]
            properties = feature.get("properties") or {}
            distance_m = float(properties["distance"])
            duration_s = float(properties["time"])
            geometry_data = feature.get("geometry") or {}
            coordinates = geometry_data.get("coordinates")
            lines = []
            if geometry_data.get("type") == "MultiLineString":
                if isinstance(coordinates, list):
                    lines = [line for line in coordinates
                             if isinstance(line, list)]
            elif isinstance(coordinates, list):
                lines = [coordinates]
            geometry: List[GeoPoint] = []
            for line in lines:
                for pair in line:
                    lng, lat = float(pair[0]), float(pair[1])
                    if TransportValidators.validate_coordinates(lat, lng):
                        geometry.append(
                            GeoPoint(latitude=lat, longitude=lng))
            return RouteResult(distance_m=distance_m,
                               duration_s=duration_s,
                               geometry=geometry,
                               provider=self.name, resolved=True)
        except Exception as exc:
            logger.warning("Geoapify route request failed: %s",
                           type(exc).__name__)
            return RouteResult(distance_m=0.0, duration_s=0.0,
                               provider=self.name, resolved=False)

    def matrix(self, origins: List[GeoPoint],
               destinations: List[GeoPoint]) -> List[List[RouteResult]]:
        return [[RouteResult(distance_m=0.0, duration_s=0.0,
                             provider=self.name, resolved=False)
                 for _ in destinations] for _ in origins]
