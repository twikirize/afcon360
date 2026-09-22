# app/geo/map_renderer.py
"""
AFCON360 GEO - shared map-rendering boundary (map renderer node).

What this owns (domain-neutral, no business logic):
- browser-safe public map configuration derived from GeoConfig
  (tile URL template + attribution + source label + default center/zoom)
- the documented default map center (NOT a claimed user/driver location)

What this does NOT own:
- domain records, eligibility, booking/dispatch/fare decisions
- secrets (TileProviderConfig carries none; this builder emits none)
- tile serving itself (PMTiles/Martin/external backend or the free
  OpenStreetMap default used until an operator configures one)

Renderer decision (map renderer node, CASE B): Leaflet remains the shared
browser renderer behind this boundary. MapLibre is the preferred future
target but is NOT introduced here - no MapLibre asset, style, or provider
exists in any environment, and the existing renderer satisfies the
foundation cleanly. See BACKLOG for the deferred MapLibre adoption item.

Coordinate order: latitude-first everywhere (GeoPoint). Leaflet consumes
[lat, lng], which matches GeoPoint order - no reversal at this boundary.
"""

from __future__ import annotations

from typing import Any, Dict

from app.geo.providers.tiles import TileProviderAdapter

# Documented default map center (Kampala). Rendered only ever as an
# explicitly-labelled default - never as a tracked/user/driver location.
DEFAULT_CENTER_LATITUDE = 0.3136
DEFAULT_CENTER_LONGITUDE = 32.5811
DEFAULT_ZOOM = 12

# Free-first default raster source (no keys, no credentials, no cost).
# Same OpenStreetMap source the existing domain pages already attribute.
DEFAULT_TILE_URL_TEMPLATE = (
    "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
)
DEFAULT_TILE_ATTRIBUTION = "© OpenStreetMap contributors"
DEFAULT_TILE_SOURCE_LABEL = "openstreetmap-default"
OPERATOR_TILE_SOURCE_LABEL = "operator-external"

# Keys this builder is allowed to emit. Anything else (credentials,
# server-only env, internal IDs) must never be added without review.
PUBLIC_MAP_CONFIG_KEYS = frozenset({
    "tiles_backend_available",
    "tiles_kind",
    "tile_url_template",
    "tile_attribution",
    "tile_source_label",
    "default_center",
    "default_zoom",
})


def build_public_map_config(config) -> Dict[str, Any]:
    """Derive the browser-safe map configuration from a GeoConfig.

    Pure function: no I/O, no network, no startup dependency. Emits only
    the keys in PUBLIC_MAP_CONFIG_KEYS - never secrets, never internal IDs.

    Tile resolution (free-first):
    - operator external tiles configured + available -> operator URL
    - otherwise -> OpenStreetMap default template with a truthful
      `tile_source_label` so the browser can state which source rendered.
      A configured PMTiles/Martin backend is reported via
      `tiles_backend_available` but still renders the OSM default in the
      Leaflet path (PMTiles needs the future MapLibre component).
    """
    tiles = getattr(config, "tiles", None)
    kind = str(getattr(tiles, "kind", "") or "pmtiles")
    adapter = (TileProviderAdapter(tiles)
               if tiles is not None else TileProviderAdapter())
    backend_available = bool(adapter.is_available())

    operator_url = ""
    if backend_available and kind == "external":
        # tile_url() is "" when the operator endpoint was never set, even
        # though an external backend reports enabled. An empty URL must
        # never reach the browser as an operator source - fall through to
        # the labelled OSM default instead.
        operator_url = adapter.tile_url("base")
    if operator_url:
        tile_url = operator_url
        attribution = str(
            getattr(tiles, "attribution", "") or DEFAULT_TILE_ATTRIBUTION)
        source_label = OPERATOR_TILE_SOURCE_LABEL
    else:
        tile_url = DEFAULT_TILE_URL_TEMPLATE
        attribution = DEFAULT_TILE_ATTRIBUTION
        source_label = DEFAULT_TILE_SOURCE_LABEL

    return {
        "tiles_backend_available": backend_available,
        "tiles_kind": kind,
        "tile_url_template": tile_url,
        "tile_attribution": attribution,
        "tile_source_label": source_label,
        "default_center": {
            "latitude": DEFAULT_CENTER_LATITUDE,
            "longitude": DEFAULT_CENTER_LONGITUDE,
        },
        "default_zoom": DEFAULT_ZOOM,
    }


__all__ = [
    "DEFAULT_CENTER_LATITUDE",
    "DEFAULT_CENTER_LONGITUDE",
    "DEFAULT_ZOOM",
    "DEFAULT_TILE_URL_TEMPLATE",
    "DEFAULT_TILE_ATTRIBUTION",
    "DEFAULT_TILE_SOURCE_LABEL",
    "OPERATOR_TILE_SOURCE_LABEL",
    "PUBLIC_MAP_CONFIG_KEYS",
    "build_public_map_config",
]
