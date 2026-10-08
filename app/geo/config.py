# app/geo/config.py
"""
AFCON360 GEO - configuration surface (slice 1).

Free-first + paid-safety rules:
- Self-hosted OSS adapters are the default path (no keys needed).
- Paid/external adapters are DISABLED by default and require an explicit
  operator endpoint (+ server-side credential, never shipped to browsers).
- Reads existing AFCON360 mechanisms only: Flask app config / env vars /
  the SystemConfig-TransportSetting KV pattern. Creates NO new settings
  model and NO new settings table.

Env vars (all optional):
    GEO_VALHALLA_URL / GEO_VALHALLA_ENABLED
    GEO_PHOTON_URL / GEO_PHOTON_ENABLED
    GEOAPIFY_BASE_URL / GEOAPIFY_API_KEY / GEOAPIFY_ENABLED /
    GEOAPIFY_TIMEOUT_S / GEOAPIFY_LANG / GEOAPIFY_BIAS / GEOAPIFY_FILTER
    GEO_TILES_KIND (pmtiles|martin|external) / GEO_TILES_URL / GEO_TILES_STYLE_URL
    GEO_LOCATION_TTL_SECONDS (default 300, mirrors Transport tracking)

Secret rule: GEOAPIFY_API_KEY is server-side only. It is read here and
handed to the Geoapify adapter; it is never logged, never rendered, and
never returned in any API payload (see health/config surfaces, which
report only enabled/configured booleans).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from app.geo.providers.geoapify import GeoapifyConfig
from app.geo.providers.photon import PhotonConfig
from app.geo.providers.tiles import TileProviderConfig
from app.geo.providers.valhalla import ValhallaConfig


def _env_flag(name: str, default: bool = False) -> bool:
    return os.getenv(name, "true" if default else "false").lower() in (
        "1", "true", "yes")


@dataclass(frozen=True)
class GeoConfig:
    valhalla: ValhallaConfig
    photon: PhotonConfig
    # Defaulted (not required) so existing constructions without a
    # Geoapify section keep working: absent means disabled/unconfigured.
    geoapify: GeoapifyConfig = field(default_factory=GeoapifyConfig)
    tiles: TileProviderConfig = field(default_factory=TileProviderConfig)
    location_ttl_seconds: int = 300


def load_geo_config(app=None) -> GeoConfig:
    """Build GeoConfig from Flask config (preferred) with env fallback."""
    source = None
    if app is not None and hasattr(app, "config"):
        source = app.config.get("GEO", {})

    def get(key: str, env: str, default: str = "") -> str:
        if isinstance(source, dict) and key in source:
            return str(source[key])
        return os.getenv(env, default)

    def flag(key: str, env: str, default: bool = False) -> bool:
        if isinstance(source, dict) and key in source:
            value = source[key]
            if isinstance(value, bool):
                return value
            return str(value).lower() in ("1", "true", "yes")
        return _env_flag(env, default)

    ttl_raw = get("location_ttl_seconds", "GEO_LOCATION_TTL_SECONDS", "300")
    try:
        ttl = max(30, int(ttl_raw))
    except (TypeError, ValueError):
        ttl = 300

    timeout_raw = get("geoapify_timeout_s", "GEOAPIFY_TIMEOUT_S", "10.0")
    try:
        geoapify_timeout = float(timeout_raw)
        if not (geoapify_timeout > 0):
            raise ValueError("timeout must be positive")
    except (TypeError, ValueError):
        geoapify_timeout = 10.0

    return GeoConfig(
        valhalla=ValhallaConfig(
            base_url=get("valhalla_url", "GEO_VALHALLA_URL"),
            enabled=flag("valhalla_enabled", "GEO_VALHALLA_ENABLED", False),
        ),
        photon=PhotonConfig(
            base_url=get("photon_url", "GEO_PHOTON_URL"),
            enabled=flag("photon_enabled", "GEO_PHOTON_ENABLED", False),
        ),
        geoapify=GeoapifyConfig(
            base_url=(get("geoapify_url", "GEOAPIFY_BASE_URL",
                          "https://api.geoapify.com")
                      or "https://api.geoapify.com"),
            api_key=get("geoapify_api_key", "GEOAPIFY_API_KEY"),
            timeout_s=geoapify_timeout,
            enabled=flag("geoapify_enabled", "GEOAPIFY_ENABLED", False),
            lang=get("geoapify_lang", "GEOAPIFY_LANG", "en") or "en",
            bias=get("geoapify_bias", "GEOAPIFY_BIAS"),
            filter=get("geoapify_filter", "GEOAPIFY_FILTER"),
        ),
        tiles=TileProviderConfig(
            kind=get("tiles_kind", "GEO_TILES_KIND", "pmtiles") or "pmtiles",
            base_url=get("tiles_url", "GEO_TILES_URL"),
            style_url=get("tiles_style_url", "GEO_TILES_STYLE_URL"),
            enabled=True,
        ),
        location_ttl_seconds=ttl,
    )
