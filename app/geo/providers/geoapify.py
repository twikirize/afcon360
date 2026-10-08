# app/geo/providers/geoapify.py
"""
AFCON360 GEO - Geoapify forward/reverse geocoding adapter (primary).

Locked provider order: Geoapify first, public Photon best-effort fallback,
honest unresolved on double failure.

Wire contract (Geoapify Geocoding API, ``format=geojson`` — the default and
the observed real response shape):
- Forward: GET {base_url}/v1/geocode/search
  params {text, format=geojson, limit, lang, apiKey} (+ operator bias/filter)
  -> {"type": "FeatureCollection", "features": [{"type": "Feature",
  "properties": {datasource, formatted, address_line1, address_line2,
  name, city, state, country, result_type, place_id, rank{confidence,
  match_type, ...}}, "geometry": {"type": "Point",
  "coordinates": [longitude, latitude]}, "bbox": [...]}]}.
- Reverse: GET {base_url}/v1/geocode/reverse
  params {lat, lon, format=geojson, lang, apiKey} -> same shape; first
  feature wins, empty collection is a truthful miss.

Failure classification (explicit, drives the service chain):
- timeout / network failure / ANY non-2xx (incl. 401/403/429/5xx) /
  invalid JSON / valid JSON without a list ``features`` -> raise
  ``ProviderFailure`` (operational failure -> service falls back).
- valid 200 with zero USEFUL candidates -> return [] (honest no-result ->
  service does NOT fall back).
- Network happens ONLY inside geocode()/reverse(). Import, construction,
  is_available() perform zero I/O. No retries.
- The API key travels ONLY as a server-side request parameter over the
  operator-configured base URL (https by default). It is never logged
  (exception text may contain the request URL), never returned in results,
  never stored in ``raw``.

Canonical mapping notes:
- ``display_name`` is the provider's ``formatted`` label (fallback: a
  name/city/country join); advisory only, never identity.
- ``raw`` carries ONLY ``geoapify_quality`` (confidence/match_type/
  result_type/formatted-presence/water signals for the service's explicit
  weak-result and reverse-presentability policies). The endpoint echo
  contract has no Geoapify datum pair and the canonical helper keeps
  only OSM pairs, so provenance.reference is None for Geoapify hits
  (contract-legal) and no provider payload reaches the 13-key snapshot.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import requests

from app.geo.interfaces import (GeocodeResult, GeocodingProvider, GeoPoint)
from app.geo.providers.base import BaseProvider, ProviderFailure
from app.utils.exceptions import ValidationError
from app.utils.validators import TransportValidators

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://api.geoapify.com"

# Required display credit for Geoapify-sourced data (free plan) plus the
# OSM credit Geoapify itself carries (datasource.attribution).
ATTRIBUTION_GEOAPIFY = "Powered by Geoapify | © OpenStreetMap contributors"
ATTRIBUTION_OSM = "© OpenStreetMap contributors"


@dataclass
class GeoapifyConfig:
    base_url: str = DEFAULT_BASE_URL
    api_key: str = ""
    timeout_s: float = 10.0
    enabled: bool = False  # disabled until operator configures a key
    lang: str = "en"
    bias: str = ""  # optional operator passthrough, e.g. "countrycode:ug"
    filter: str = ""  # optional operator passthrough, e.g. "countrycode:ug"


def _display_name(properties: Dict[str, Any]) -> str:
    """Provider label first, deterministic fallback join, never invented."""
    formatted = properties.get("formatted")
    if isinstance(formatted, str) and formatted.strip():
        return formatted.strip()
    parts = [properties.get("name"), properties.get("city"),
             properties.get("country")]
    return ", ".join(str(part) for part in parts if part)


def _quality(properties: Dict[str, Any]) -> Dict[str, Any]:
    """Weak-result + presentability signals, verbatim from the provider.

    Service-policy use only (weak secondary trigger, reverse display
    suitability). Never reaches the canonical snapshot: no canonical
    extractor reads the ``geoapify_quality`` key. ``distance`` is
    deliberately NOT copied: snap-distance thresholds belong to the
    future quality node, never to this adapter.
    """
    rank = properties.get("rank")
    rank = rank if isinstance(rank, dict) else {}
    confidence = rank.get("confidence")
    if confidence is None or isinstance(confidence, bool):
        confidence = None
    else:
        try:
            confidence = float(confidence)
        except (TypeError, ValueError):
            confidence = None
    match_type = rank.get("match_type")
    result_type = properties.get("result_type")
    formatted = properties.get("formatted")
    ocean = properties.get("ocean")
    return {
        "confidence": confidence,
        "match_type": match_type if isinstance(match_type, str) else None,
        "result_type": result_type if isinstance(result_type, str) else None,
        "formatted_present": bool(
            isinstance(formatted, str) and formatted.strip()),
        "is_water": bool(isinstance(ocean, str) and ocean.strip()),
    }


def _feature_to_result(feature: Any,
                       provider_name: str) -> Optional[GeocodeResult]:
    """Normalize one GeoJSON feature; None when unusable (skip, don't fake).

    GeoJSON order is [longitude, latitude] — converted to latitude-first
    at this boundary (never silently swapped).
    """
    if not isinstance(feature, dict):
        return None
    try:
        geometry = feature.get("geometry") or {}
        coordinates = geometry["coordinates"]
        lng, lat = float(coordinates[0]), float(coordinates[1])
        properties = feature.get("properties") or {}
        if not isinstance(properties, dict):
            return None
        if not TransportValidators.validate_coordinates(lat, lng):
            return None
        return GeocodeResult(
            latitude=lat,
            longitude=lng,
            display_name=_display_name(properties),
            raw={"geoapify_quality": _quality(properties)},
            provider=provider_name,
            resolved=True,
        )
    except (KeyError, TypeError, ValueError, IndexError):
        return None


class GeoapifyGeocoder(BaseProvider, GeocodingProvider):
    """Geoapify adapter. Live when configured; classified failure otherwise."""

    name = "geoapify"

    # Identifying UA so provider-side bot filtering never 403s a default
    # python-requests UA (the Photon D1 failure class, not repeated here).
    user_agent = "AFCON360-geocoder/1.0"

    def __init__(self, config: GeoapifyConfig | None = None):
        self.config = config or GeoapifyConfig()

    def is_available(self) -> bool:
        return bool(self.config.enabled and self.config.api_key)

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

    @staticmethod
    def _clamp_limit(limit: Any) -> int:
        try:
            value = int(limit)
        except (TypeError, ValueError):
            return 5
        return max(1, min(value, 5))

    def _params(self, extra: Dict[str, Any]) -> Dict[str, Any]:
        params: Dict[str, Any] = {
            "format": "geojson",
            "lang": self.config.lang or "en",
            "apiKey": self.config.api_key,
        }
        params.update(extra)
        if self.config.bias:
            params["bias"] = self.config.bias
        if self.config.filter:
            params["filter"] = self.config.filter
        return params

    def _get_features(self, path: str, params: Dict[str, Any]) -> List[Any]:
        """GET one provider call; raise ProviderFailure on operational
        failure, return the feature list (possibly empty) on valid shape."""
        url = self.config.base_url.rstrip("/") + path
        try:
            response = requests.get(url, params=params,
                                    timeout=self.config.timeout_s,
                                    headers={"User-Agent": self.user_agent})
            response.raise_for_status()
            payload = response.json()
        except Exception as exc:
            # Never log the exception text: it may embed the request URL
            # including the server-side apiKey.
            logger.warning("Geoapify request failed (%s): %s", path,
                           type(exc).__name__)
            raise ProviderFailure(f"geoapify {path} failed: "
                                  f"{type(exc).__name__}") from exc
        features = payload.get("features") if isinstance(payload,
                                                          dict) else None
        if not isinstance(features, list):
            logger.warning("Geoapify request returned unusable shape: %s",
                           path)
            raise ProviderFailure(f"geoapify {path} unusable shape")
        return features

    def geocode(self, query: str, limit: int = 5) -> List[GeocodeResult]:
        text = self._validate_query(query)
        if not self.is_available():
            return []
        features = self._get_features(
            "/v1/geocode/search",
            self._params({"text": text, "limit": self._clamp_limit(limit)}))
        hits: List[GeocodeResult] = []
        for feature in features:
            result = _feature_to_result(feature, self.name)
            if result is not None:
                hits.append(result)
        return hits

    def reverse(self, point: GeoPoint) -> GeocodeResult:
        self._validate_point(point)
        if not self.is_available():
            return GeocodeResult(provider=self.name, resolved=False)
        try:
            features = self._get_features(
                "/v1/geocode/reverse",
                self._params({"lat": point.latitude,
                              "lon": point.longitude}))
        except ProviderFailure:
            return GeocodeResult(provider=self.name, resolved=False)
        if not features:
            return GeocodeResult(provider=self.name, resolved=False)
        result = _feature_to_result(features[0], self.name)
        if result is None:
            return GeocodeResult(provider=self.name, resolved=False)
        return result
