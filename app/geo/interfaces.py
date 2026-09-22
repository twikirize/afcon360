# app/geo/interfaces.py
"""
AFCON360 GEO - stable domain-facing contracts.

Domain modules depend on THESE contracts, never on a provider SDK or
provider-specific response object. Providers implement these interfaces
behind app/geo/providers/.

Design: dataclasses for values, ABCs for provider seams. Pure Python -
no Flask/Django, no network, no DB at import time.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Value objects (domain-neutral)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class GeoPoint:
    """Validated geographic point. Use app.geo.validation.normalize_point()."""
    latitude: float
    longitude: float
    accuracy: float = 0.0
    timestamp: Optional[datetime] = None


@dataclass(frozen=True)
class RouteResult:
    """Provider-independent route answer. Distances in meters, duration sec."""
    distance_m: float
    duration_s: float
    geometry: List[GeoPoint] = field(default_factory=list)
    # Straight-line fallback MUST be labelled: provider="haversine-fallback".
    provider: str = "unresolved"
    resolved: bool = False


@dataclass(frozen=True)
class GeocodeResult:
    """Provider-independent geocode answer. Unresolved = truthful miss."""
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    display_name: str = ""
    raw: Dict[str, Any] = field(default_factory=dict)
    provider: str = "unresolved"
    resolved: bool = False


@dataclass(frozen=True)
class NearbyItem:
    """One proximity hit: public ref + distance. GEO never returns the
    domain record itself - the owning domain resolves public_id → record."""
    public_id: str = ""
    distance_m: float = 0.0
    point: Optional[GeoPoint] = None


# ---------------------------------------------------------------------------
# Provider seams (adapters implement these)
# ---------------------------------------------------------------------------

class RoutingProvider(ABC):
    """Road routing seam: Valhalla now, OSRM later, paid later."""

    @abstractmethod
    def route(self, origin: GeoPoint, destination: GeoPoint,
              profile: str = "auto") -> RouteResult:
        """Return road route or unresolved RouteResult (never fake)."""

    @abstractmethod
    def matrix(self, origins: List[GeoPoint],
               destinations: List[GeoPoint]) -> List[List[RouteResult]]:
        """Multi-point distance/duration capability (dispatch planning)."""


class GeocodingProvider(ABC):
    """Geocoding seam: Photon now, others later."""

    @abstractmethod
    def geocode(self, query: str, limit: int = 5) -> List[GeocodeResult]:
        """Forward geocode or [] when unavailable (truthful miss)."""

    @abstractmethod
    def reverse(self, point: GeoPoint) -> GeocodeResult:
        """Reverse geocode or unresolved result (never fake coords)."""


class TileProvider(ABC):
    """Map/tile infrastructure seam: PMTiles now, Martin dynamic later."""

    @abstractmethod
    def tile_url(self, layer: str = "base") -> str:
        """Public tile/style URL for the requested layer."""

    @abstractmethod
    def is_available(self) -> bool:
        """False when the tile backend is unreachable/disabled."""
