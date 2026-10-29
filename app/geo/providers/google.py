# app/geo/providers/google.py
"""
AFCON360 GEO - Google Maps Directions routing adapter.

Wire contract (Google Directions API):
- GET {base_url}/directions/json
  params: origin=lat,lng, destination=lat,lng, mode, key
- Response status must be OK; routes[0].legs[0].distance.value is meters,
  routes[0].legs[0].duration.value is seconds, and
  routes[0].overview_polyline.points is an encoded precision-5 polyline.

The adapter is disabled by default and requires an operator-supplied API
key. Google's public Directions API has no motorcycle mode, so a
motorcycle/scooter/truck request is a truthful unresolved result rather
than a silent car route. The key is never logged or returned.

Google Maps Platform terms require displaying results on a Google map;
this adapter only produces routing data and leaves presentation to the
calling surface.
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

GOOGLE_DIRECTIONS_PATH = "/directions/json"


def _default_profile_map() -> Dict[str, str]:
    return {
        "auto": "driving",
        "driving": "driving",
        "pedestrian": "walking",
        "bicycle": "bicycling",
    }


def decode_polyline(encoded: str) -> List[GeoPoint]:
    """Decode a Google encoded polyline (precision 5) into GeoPoints."""
    if not isinstance(encoded, str) or not encoded:
        return []
    coordinates: List[GeoPoint] = []
    index = 0
    latitude = 0
    longitude = 0
    length = len(encoded)
    try:
        while index < length:
            shift = 0
            result = 0
            while True:
                byte = ord(encoded[index]) - 63
                index += 1
                result |= (byte & 0x1F) << shift
                shift += 5
                if byte < 0x20:
                    break
                if index >= length:
                    raise ValueError("truncated latitude")
            delta_latitude = ~(result >> 1) if result & 1 else result >> 1
            latitude += delta_latitude

            shift = 0
            result = 0
            while True:
                byte = ord(encoded[index]) - 63
                index += 1
                result |= (byte & 0x1F) << shift
                shift += 5
                if byte < 0x20:
                    break
                if index >= length:
                    raise ValueError("truncated longitude")
            delta_longitude = ~(result >> 1) if result & 1 else result >> 1
            longitude += delta_longitude

            lat = latitude / 1e5
            lng = longitude / 1e5
            if TransportValidators.validate_coordinates(lat, lng):
                coordinates.append(GeoPoint(latitude=lat, longitude=lng))
    except (IndexError, ValueError):
        return coordinates
    return coordinates


@dataclass
class GoogleMapsConfig:
    base_url: str = "https://maps.googleapis.com/maps/api"
    api_key: str = ""
    timeout_s: float = 10.0
    enabled: bool = False
    profile_map: Dict[str, str] = field(default_factory=_default_profile_map)


class GoogleMapsRouter(BaseProvider, RoutingProvider):
    """Google Maps Directions adapter. Truthful miss until configured."""

    name = "google"
    user_agent = "AFCON360-router/1.0"

    def __init__(self, config: GoogleMapsConfig | None = None):
        self.config = config or GoogleMapsConfig()

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
        google_mode = self.config.profile_map.get(profile)
        if not self.is_available() or not google_mode:
            return RouteResult(distance_m=0.0, duration_s=0.0,
                               provider=self.name, resolved=False)

        base_url = self.config.base_url.rstrip("/")
        if not base_url.endswith(GOOGLE_DIRECTIONS_PATH):
            base_url += GOOGLE_DIRECTIONS_PATH
        params = {
            "origin": f"{origin.latitude},{origin.longitude}",
            "destination": f"{destination.latitude},{destination.longitude}",
            "mode": google_mode,
            "alternatives": "false",
            "key": self.config.api_key,
        }
        try:
            response = requests.get(
                base_url, params=params, timeout=self.config.timeout_s,
                headers={"User-Agent": self.user_agent})
            response.raise_for_status()
            payload = response.json()
            if payload.get("status") != "OK":
                raise ValueError("Google Directions status is not OK")
            routes = payload.get("routes")
            if not isinstance(routes, list) or not routes:
                raise ValueError("Google Directions response has no routes")
            legs = routes[0].get("legs")
            if not isinstance(legs, list) or not legs:
                raise ValueError("Google Directions response has no legs")
            leg = legs[0]
            distance_m = float((leg.get("distance") or {})["value"])
            duration_s = float((leg.get("duration") or {})["value"])
            polyline = (routes[0].get("overview_polyline") or {}).get("points")
            geometry = decode_polyline(polyline)
            return RouteResult(distance_m=distance_m,
                               duration_s=duration_s,
                               geometry=geometry,
                               provider=self.name, resolved=True)
        except Exception as exc:
            logger.warning("Google Maps route request failed: %s",
                           type(exc).__name__)
            return RouteResult(distance_m=0.0, duration_s=0.0,
                               provider=self.name, resolved=False)

    def matrix(self, origins: List[GeoPoint],
               destinations: List[GeoPoint]) -> List[List[RouteResult]]:
        return [[RouteResult(distance_m=0.0, duration_s=0.0,
                             provider=self.name, resolved=False)
                 for _ in destinations] for _ in origins]
