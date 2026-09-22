"""AFCON360 GEO map-renderer node - backend contract tests.

Proves the shared map-rendering boundary:
  GeoConfig -> build_public_map_config() -> browser-safe dict
  -> /geo/ overview (server -> template -> static asset path).

Coordinate order is latitude-first everywhere (GeoPoint order); the
default center is asymmetric (0.3136 / 32.5811) so a lat/lng swap is
detectable. No secrets, no internal IDs, no domain concepts.
"""

import re
from types import SimpleNamespace

from app.geo.map_renderer import (
    DEFAULT_CENTER_LATITUDE,
    DEFAULT_CENTER_LONGITUDE,
    DEFAULT_TILE_ATTRIBUTION,
    DEFAULT_TILE_SOURCE_LABEL,
    DEFAULT_TILE_URL_TEMPLATE,
    DEFAULT_ZOOM,
    OPERATOR_TILE_SOURCE_LABEL,
    PUBLIC_MAP_CONFIG_KEYS,
    build_public_map_config,
)
from app.geo.providers.tiles import TileProviderConfig


def _config(**tiles_kwargs):
    params = {"kind": "pmtiles", "base_url": "", "style_url": "",
              "enabled": True}
    params.update(tiles_kwargs)
    return SimpleNamespace(tiles=TileProviderConfig(**params))


# --- builder: defaults (no tile backend configured) -----------------------

def test_default_config_uses_osm_fallback_with_truthful_label():
    config = build_public_map_config(_config())
    assert config["tiles_backend_available"] is False
    assert config["tile_url_template"] == DEFAULT_TILE_URL_TEMPLATE
    assert config["tile_attribution"] == DEFAULT_TILE_ATTRIBUTION
    assert config["tile_source_label"] == DEFAULT_TILE_SOURCE_LABEL
    assert config["default_center"] == {
        "latitude": DEFAULT_CENTER_LATITUDE,
        "longitude": DEFAULT_CENTER_LONGITUDE,
    }
    assert config["default_zoom"] == DEFAULT_ZOOM


def test_default_center_is_asymmetric_kampala():
    # Reversal-sensitive: latitude != longitude, so a swap is detectable.
    assert (DEFAULT_CENTER_LATITUDE, DEFAULT_CENTER_LONGITUDE) == (
        0.3136, 32.5811)
    assert DEFAULT_CENTER_LATITUDE != DEFAULT_CENTER_LONGITUDE


def test_external_tiles_configured_uses_operator_url():
    config = build_public_map_config(_config(
        kind="external",
        base_url="https://tiles.example.com",
        attribution="Example tiles",
    ))
    assert config["tiles_backend_available"] is True
    assert config["tile_url_template"] == "https://tiles.example.com/base"
    assert config["tile_attribution"] == "Example tiles"
    assert config["tile_source_label"] == OPERATOR_TILE_SOURCE_LABEL


def test_external_tiles_enabled_but_unconfigured_falls_back():
    # External backends report enabled without a URL; the browser must
    # still get the labelled OSM default, never an empty operator URL.
    config = build_public_map_config(_config(kind="external", base_url=""))
    assert config["tile_url_template"] == DEFAULT_TILE_URL_TEMPLATE
    assert config["tile_source_label"] == DEFAULT_TILE_SOURCE_LABEL


def test_pmtiles_backend_reported_but_leaflet_uses_osm_default():
    # PMTiles needs the future MapLibre component; the Leaflet path must
    # not pretend it can consume it - OSM default with truthful label.
    config = build_public_map_config(_config(
        kind="pmtiles", base_url="https://tiles.example.com/all.pmtiles"))
    assert config["tiles_backend_available"] is True
    assert config["tile_url_template"] == DEFAULT_TILE_URL_TEMPLATE
    assert config["tile_source_label"] == DEFAULT_TILE_SOURCE_LABEL


def test_public_config_emits_only_allowlisted_keys():
    config = build_public_map_config(_config())
    assert set(config.keys()) <= set(PUBLIC_MAP_CONFIG_KEYS)


def test_public_config_contains_no_secrets_or_internal_ids():
    config = build_public_map_config(_config(
        kind="external", base_url="https://tiles.example.com"))
    blob = repr(config).lower()
    for token in ("secret", "token", "password", "api_key", "apikey",
                  "private_key", "credential"):
        assert token not in blob


def test_builder_has_no_side_effects_or_startup_dependency():
    cfg = _config()
    first = build_public_map_config(cfg)
    second = build_public_map_config(cfg)
    assert first == second
    # No network at build time: unroutable backend still builds.
    offline = build_public_map_config(_config(
        kind="external", base_url="http://unroutable.invalid"))
    assert offline["tile_url_template"].startswith("http")


# --- server -> template -> static asset path --------------------------------

def test_geo_overview_renders_shared_map(app, admin_client):
    from tests.test_geo_integration import preserved_module_flags, set_geo
    with preserved_module_flags(app):
        set_geo(app, True)
        response = admin_client.get('/geo/')
        assert response.status_code == 200
        html = response.data.decode('utf-8')
        # Map container with truthful pending state.
        assert 'id="geoMap"' in html
        assert 'data-geo-map-status="pending"' in html
        # Shared GEO asset (first-party) + CSP-allowlisted Leaflet CDN.
        assert 'js/geo/geo-map.js' in html
        assert 'cdn.jsdelivr.net/npm/leaflet@1.9.4' in html
        assert 'unpkg.com' not in html
        # Browser-safe config embedded: asymmetric default center.
        assert '0.3136' in html
        assert '32.5811' in html
        assert 'tile.openstreetmap.org' in html
        assert 'openstreetmap-default' in html
        # Default marker is labelled as a default, never a tracked location.
        assert 'not a tracked location' in html
        # Inline init script carries the CSP nonce.
        assert 'nonce="' in html
        # No fabricated capability, no internal-ID links.
        assert 'not configured' in html
        assert not re.search(r'href="/[^"]*/\d+(?:[/?#]|")', html)
