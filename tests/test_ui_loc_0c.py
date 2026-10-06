"""UI-LOC-0C focused source tests (no browser, no provider).

Proves map operational hardening without changing 0B/02A behavior:
- Leaflet/map-init failures produce a truthful unavailable state + retry
- tile failures are degraded (not unavailable) and rider-safe
- rider page surfaces map unavailability instead of map targeting
- 0B GPS/targeting/Continue guards remain intact
"""
from pathlib import Path

GEO_MAP = Path(__file__).resolve().parent.parent / "static" / "js" / "geo" / "geo-map.js"
TEMPLATE = Path(__file__).resolve().parent.parent / "templates" / "transport" / "new_home.html"


def _geo():
    return GEO_MAP.read_text(encoding="utf-8")


def _tpl():
    return TEMPLATE.read_text(encoding="utf-8")


def test_0c_geo_map_init_failure_truthful_with_retry():
    src = _geo()
    assert "Map library failed to load" in src
    assert "Map could not be started" in src
    assert "geo-map-retry" in src
    assert "Try again" in src


def test_0c_tile_failure_degraded_not_unavailable():
    src = _geo()
    # tileerror listener attached to TileLayer before addTo(map)
    assert "tileLayer.on('tileerror'" in src
    # strict locality: the degraded rendering lives inside renderTileDegraded()
    body_start = src.find("function renderTileDegraded(")
    assert body_start != -1
    body_end = src.find("\n  function ", body_start + 1)
    body = src[body_start : body_end if body_end != -1 else len(src)]
    assert "data-geo-map-tiles" in body
    assert "degraded" in body
    assert "Map tiles are failing to load" in body
    # degraded path must not mark the container unavailable
    assert "unavailable" not in body


def test_0c_rider_page_surfaces_map_unavailable():
    src = _tpl()
    assert "window.__boltMapAvailable = false" in src
    assert "window.__boltMapAvailable = true" in src
    assert "Map unavailable" in src


def test_0c_0b_contracts_intact():
    src = _tpl()
    # 0B GPS + targeting + Continue gate untouched
    assert "function invalidateGpsRequest()" in src
    assert "if (mySeq !== gpsSeq) return;" in src
    assert "btnContinue.disabled = !state.dest || !state.pickup || !coordsPresent;" in src
    assert "updateMapTarget();" in src and "updateContinueReason();" in src
    # 02A guards untouched
    assert "if (!pickupLat || !pickupLng || !dropoffLat || !dropoffLng) {" in src


def test_0c_csp_nonce_preserved():
    src = _tpl()
    assert '<script nonce="{{ csp_nonce }}">' in src
    assert "onclick=" not in src
