# app/geo/tile_proxy.py
"""AFCON360 GEO - server-side raster tile proxy (map availability node).

Why this exists: OpenStreetMap blocks requests that arrive straight from an
app or an embedded WebView ("418 Access blocked - App is not following the
tile usage policy"). A mobile client cannot send the required identifying
User-Agent, so the raster tiles must be fetched by our own server, which can
identify itself, cache aggressively, and answer 502 when the upstream is
unavailable instead of painting grey "418" squares inside the map.

Rules kept here:
- The upstream is server-only configuration (``GEO_TILES_UPSTREAM_URL``, or an
  operator ``GEO_TILES_URL`` when ``GEO_TILES_KIND=external``). No key or
  upstream URL is ever emitted to a client payload.
- Aggressive caching (Redis, 7 days) keeps the upstream traffic to one request
  per tile per week per deployment.
- Every failure is truthful: 404 for an impossible tile index, 502 when the
  upstream refused or timed out. Callers render a map-unavailable fallback
  rather than a broken grid.
- OSM attribution is never stripped: the tile response carries
  ``X-Pamoja-Tile-Attribution`` and the map renderer still displays it.
"""

from __future__ import annotations

import hashlib
import logging
from typing import Optional, Tuple

import requests
from flask import Response, current_app

from app.geo.config import load_geo_config

logger = logging.getLogger(__name__)

# Same ceiling the Leaflet layer uses on the client.
MAX_ZOOM = 19
MIN_ZOOM = 0

TILE_CACHE_TTL_SECONDS = 7 * 24 * 3600
TILE_UPSTREAM_TIMEOUT_S = 6.0
# A real 256px PNG is a few kilobytes; anything far larger is not a tile.
MAX_TILE_BYTES = 512 * 1024
CACHE_KEY_PREFIX = "geo:tile:v1"

# Free-first default. Only our server ever calls it, with this User-Agent.
DEFAULT_UPSTREAM_TEMPLATE = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
TILE_USER_AGENT = "Pamoja/1.0 (map tiles; +https://www.pamoja.space)"


def resolve_upstream_template(config=None) -> str:
    """Operator-configured raster upstream, else the free OSM default."""
    if config is None:
        config = load_geo_config(current_app)
    tiles = getattr(config, "tiles", None)
    upstream = str(getattr(tiles, "upstream_url", "") or "").strip()
    if upstream:
        return upstream
    kind = str(getattr(tiles, "kind", "") or "")
    base_url = str(getattr(tiles, "base_url", "") or "").strip().rstrip("/")
    if kind == "external" and base_url:
        return base_url + "/{z}/{x}/{y}.png"
    return DEFAULT_UPSTREAM_TEMPLATE


def tile_attribution(config=None) -> str:
    if config is None:
        config = load_geo_config(current_app)
    attribution = str(getattr(getattr(config, "tiles", None), "attribution", "") or "").strip()
    return attribution or "© OpenStreetMap contributors"


def tile_indices_valid(z: int, x: int, y: int) -> bool:
    """Reject indices that cannot exist, before any network call."""
    if not (MIN_ZOOM <= z <= MAX_ZOOM):
        return False
    limit = (1 << z) - 1
    return 0 <= x <= limit and 0 <= y <= limit


def _cache_key(url: str) -> str:
    digest = hashlib.sha1(url.encode("utf-8")).hexdigest()
    return CACHE_KEY_PREFIX + ":" + digest


def _redis():
    try:
        from app.extensions import redis_client
        return redis_client
    except Exception:
        return None


def _cache_get(key: str) -> Optional[bytes]:
    client = _redis()
    if client is None:
        return None
    try:
        cached = client.get(key)
    except Exception:
        return None
    return cached if isinstance(cached, (bytes, bytearray)) and cached else None


def _cache_set(key: str, body: bytes) -> None:
    client = _redis()
    if client is None:
        return
    try:
        client.setex(key, TILE_CACHE_TTL_SECONDS, body)
    except Exception:
        pass


def fetch_tile(z: int, x: int, y: int, config=None) -> Tuple[Optional[bytes], str]:
    """Return ``(tile_bytes, source)``; ``(None, reason)`` on honest failure.

    ``source`` is ``"cache"``, ``"upstream"`` or the failure reason. No
    exception leaves this function: the map must degrade, not 500.
    """
    if config is None:
        config = load_geo_config(current_app)
    if not tile_indices_valid(z, x, y):
        return None, "invalid_index"

    url = resolve_upstream_template(config).format(z=z, x=x, y=y)
    key = _cache_key(url)
    cached = _cache_get(key)
    if cached is not None:
        return cached, "cache"

    try:
        response = requests.get(
            url,
            timeout=TILE_UPSTREAM_TIMEOUT_S,
            headers={
                "User-Agent": TILE_USER_AGENT,
                "Accept": "image/png,image/*;q=0.8",
                "Referer": "https://www.pamoja.space/",
            },
        )
        response.raise_for_status()
        content_type = response.headers.get("Content-Type", "")
        body = response.content or b""
        if not content_type.startswith("image/"):
            logger.warning("Tile upstream answered non-image content for %s", url)
            return None, "upstream_not_image"
        if not body or len(body) > MAX_TILE_BYTES:
            logger.warning("Tile upstream answered an unusable body for %s", url)
            return None, "upstream_bad_body"
    except Exception as exc:
        # One log line per upstream failure; the caller answers 502.
        logger.warning("Tile upstream failed for %s: %s", url, exc)
        return None, "upstream_unavailable"

    _cache_set(key, body)
    return body, "upstream"


def tile_response(z: int, x: int, y: int, config=None) -> Response:
    """Flask response for one tile. 200 with the image, or 404 / 502."""
    body, source = fetch_tile(z, x, y, config)
    if body is None:
        status = 404 if source == "invalid_index" else 502
        response = Response(b"", status=status, mimetype="text/plain")
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Pamoja-Tile-Status"] = source
        return response

    response = Response(body, status=200, mimetype="image/png")
    response.headers["Cache-Control"] = (
        "public, max-age=" + str(TILE_CACHE_TTL_SECONDS) + ", immutable"
    )
    response.headers["X-Pamoja-Tile-Source"] = source
    response.headers["X-Pamoja-Tile-Attribution"] = tile_attribution(config)
    return response


__all__ = [
    "MAX_ZOOM",
    "MIN_ZOOM",
    "TILE_CACHE_TTL_SECONDS",
    "TILE_USER_AGENT",
    "DEFAULT_UPSTREAM_TEMPLATE",
    "resolve_upstream_template",
    "tile_attribution",
    "tile_indices_valid",
    "fetch_tile",
    "tile_response",
]
