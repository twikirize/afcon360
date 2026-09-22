# app/geo/providers/photon.py
"""
AFCON360 GEO - Photon geocoding adapter.

Locked stack: Photon (self-hosted Uganda/Africa extract) is primary;
public Nominatim MUST NOT become the production dependency.

Behavior:
- Configured + enabled + reachable Photon → normalized GeocodeResult
  hits (resolved=True, provider="photon").
- Anything else (disabled, unconfigured, timeout, HTTP error, malformed
  response) → truthful miss ([] / unresolved). Never fake coordinates.
- Network happens ONLY inside geocode()/reverse(). Import,
  construction, is_available() perform zero I/O.
- No retries: provider failures must not produce runaway request loops.

Photon wire details assumed (documented public search API):
- Forward: GET {base_url}/api?q=<query>&limit=<n> → GeoJSON
  FeatureCollection. Feature geometry.coordinates are GeoJSON-ordered
  [longitude, latitude] — converted back to latitude-first GeoPoint
  order at this boundary (never silently swapped).
- Reverse: GET {base_url}/reverse?lat=<lat>&lon=<lon> → FeatureCollection;
  first feature wins, empty collection is a truthful miss.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import requests

from app.geo.interfaces import (GeocodeResult, GeocodingProvider, GeoPoint)
from app.geo.providers.base import BaseProvider
from app.utils.exceptions import ValidationError
from app.utils.validators import TransportValidators

logger = logging.getLogger(__name__)


@dataclass
class PhotonConfig:
    base_url: str = ""
    timeout_s: float = 10.0
    enabled: bool = False  # disabled until operator configures endpoint


def _display_name(properties: Dict[str, Any]) -> str:
    """Deterministic human label from Photon properties (never invented)."""
    parts = [properties.get("name"), properties.get("city"),
             properties.get("country")]
    return ", ".join(str(part) for part in parts if part)


def _feature_to_result(feature: Dict[str, Any],
                       provider_name: str) -> Optional[GeocodeResult]:
    """Normalize one GeoJSON feature; None when unusable (skip, don't fake)."""
    try:
        coordinates = feature["geometry"]["coordinates"]
        lng, lat = float(coordinates[0]), float(coordinates[1])
        properties = feature.get("properties") or {}
        if not TransportValidators.validate_coordinates(lat, lng):
            return None
        return GeocodeResult(
            latitude=lat,
            longitude=lng,
            display_name=_display_name(properties),
            raw=dict(properties),
            provider=provider_name,
            resolved=True,
        )
    except (KeyError, TypeError, ValueError, IndexError):
        return None


class PhotonGeocoder(BaseProvider, GeocodingProvider):
    """Photon adapter. Live when configured; truthful miss otherwise."""

    name = "photon"

    def __init__(self, config: PhotonConfig | None = None):
        self.config = config or PhotonConfig()

    def is_available(self) -> bool:
        return bool(self.config.enabled and self.config.base_url)

    @staticmethod
    def _validate_query(query: Any) -> str:
        if not isinstance(query, str) or not query.strip():
            raise ValidationError(
                f"Invalid query: must be a non-empty string, got {query!r}",
                field="query",
            )
        return query.strip()

    @staticmethod
    def _validate_point(point: GeoPoint) -> None:
        """Reject out-of-range/non-numeric coordinates before any I/O."""
        try:
            valid = TransportValidators.validate_coordinates(
                point.latitude, point.longitude)
        except Exception:
            valid = False
        if not valid:
            raise ValidationError(
                "Invalid point: latitude must be within [-90, 90] and "
                "longitude within [-180, 180], got "
                f"({point.latitude!r}, {point.longitude!r})",
                field="point",
            )

    def geocode(self, query: str, limit: int = 5) -> List[GeocodeResult]:
        text = self._validate_query(query)
        if not self.is_available():
            return []
        try:
            url = self.config.base_url.rstrip("/") + "/api"
            response = requests.get(url, params={"q": text, "limit": limit},
                                    timeout=self.config.timeout_s)
            response.raise_for_status()
            features = response.json().get("features") or []
            hits: List[GeocodeResult] = []
            for feature in features:
                result = _feature_to_result(feature, self.name)
                if result is not None:
                    hits.append(result)
            return hits
        except Exception as e:
            logger.warning("Photon geocode request failed: %s", e)
            return []

    def reverse(self, point: GeoPoint) -> GeocodeResult:
        self._validate_point(point)
        if not self.is_available():
            return GeocodeResult(provider=self.name, resolved=False)
        try:
            url = self.config.base_url.rstrip("/") + "/reverse"
            response = requests.get(
                url,
                params={"lat": point.latitude, "lon": point.longitude},
                timeout=self.config.timeout_s)
            response.raise_for_status()
            features = response.json().get("features") or []
            if not features:
                return GeocodeResult(provider=self.name, resolved=False)
            result = _feature_to_result(features[0], self.name)
            if result is None:
                return GeocodeResult(provider=self.name, resolved=False)
            return result
        except Exception as e:
            logger.warning("Photon reverse request failed: %s", e)
            return GeocodeResult(provider=self.name, resolved=False)
