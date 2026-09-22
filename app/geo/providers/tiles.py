# app/geo/providers/tiles.py
"""
AFCON360 GEO - tile/map-data provider seam (slice 1).

Locked stack: PMTiles now, Martin where dynamic/vector serving is needed;
MapLibre GL JS renderer (Leaflet retained for simple pages).
This slice carries configuration + availability only - no tile serving.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.geo.interfaces import TileProvider
from app.geo.providers.base import BaseProvider


@dataclass
class TileProviderConfig:
    kind: str = "pmtiles"  # pmtiles | martin | external
    base_url: str = ""
    style_url: str = ""
    enabled: bool = True
    attribution: str = "© OpenStreetMap contributors"


class TileProviderAdapter(BaseProvider, TileProvider):
    """Tile backend handle. OSM attribution is never stripped."""

    name = "tiles"

    def __init__(self, config: TileProviderConfig | None = None):
        self.config = config or TileProviderConfig()

    def is_available(self) -> bool:
        if self.config.kind == "external":
            return self.config.enabled
        return bool(self.config.enabled and self.config.base_url)

    def tile_url(self, layer: str = "base") -> str:
        if not self.is_available():
            return ""
        base = self.config.base_url.rstrip("/")
        return f"{base}/{layer}" if base else ""
