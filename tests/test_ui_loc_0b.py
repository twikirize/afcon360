"""UI-LOC-0B focused source tests (no browser, no provider).

Proves the 0B safety-UX wiring in templates/transport/new_home.html:
- GPS sequence/token exists and stale callbacks are ignored
- map targeting uses resolved coordinates, not text
- pickup-affecting actions bump the GPS sequence; destination-only do not
- chip selection invents no coordinates
- disabled reason + indicators are wired through validateA()
"""
import re
from pathlib import Path

TEMPLATE = Path(__file__).resolve().parent.parent / "templates" / "transport" / "new_home.html"


def _src():
    return TEMPLATE.read_text(encoding="utf-8")


def test_0b_indicators_present():
    src = _src()
    assert 'id="gpsStatus"' in src
    assert 'id="mapTargetIndicator"' in src
    assert 'id="continueDisabledReason"' in src
    assert 'aria-live="polite"' in src


def test_0b_gps_sequence_and_stale_guard():
    src = _src()
    assert "var gpsSeq = 0" in src
    assert "function bumpGpsSeq()" in src
    # token captured per request and checked on both callbacks
    assert "var mySeq = bumpGpsSeq();" in src
    assert src.count("if (mySeq !== gpsSeq) return;") >= 2


def test_0b_gps_failure_preserves_previous():
    src = _src()
    # previous resolved state captured before request
    assert "var hadResolved = isPickupResolved();" in src
    assert "previous pickup" in src.lower() or "previous pickup kept" in src.lower()


def test_0b_map_targeting_uses_resolved_coords():
    src = _src()
    # new resolved-state targeting must read hidden coordinate fields
    assert "document.getElementById('pickup_latitude').value" in src
    # old text-occupancy rule must be gone from the click handler
    click_block = src[src.find("Tap-to-place") : src.find("Tap-to-place") + 2000]
    assert "inputPickup.value.trim()" not in click_block
    assert "pickupResolved" in click_block or "pickup_latitude" in click_block


def test_0b_pickup_actions_bump_dest_only_do_not():
    src = _src()
    # pickup input invalidates (resets GPS UI + bumps sequence)
    assert "inputPickup.addEventListener('input'" in src
    pickup_block = src[src.find("inputPickup.addEventListener('input'") : src.find("inputPickup.addEventListener('input'") + 300]
    assert "invalidateGpsRequest()" in pickup_block
    # swap invalidates (pickup changes)
    assert "btnSwap" in src and "invalidateGpsRequest()" in src
    # helper resets button + status and bumps sequence
    assert "function invalidateGpsRequest()" in src
    assert "bi-crosshair" in src[src.find("function invalidateGpsRequest()") : src.find("function invalidateGpsRequest()") + 400]
    # chip handler must not bump (destination-only) and must not place pins
    chip_start = src.find("querySelectorAll('.bolt-chip')")
    chip_block = src[chip_start : chip_start + 600]
    assert "bumpGpsSeq()" not in chip_block
    assert "placePin" not in chip_block
    assert "data-lat" not in chip_block and "data-lng" not in chip_block


def test_0b_chip_honest_no_coords():
    src = _src()
    # chips carry text only in markup
    assert 'class="bolt-chip"' in src or "bolt-chip" in src
    assert "data-dest=" in src
    # no hardcoded chip coordinates in template
    assert "data-lat" not in src
    assert "data-lng" not in src


def test_0b_validate_single_sync_point():
    src = _src()
    va_start = src.find("function validateA(){")
    va_block = src[va_start : va_start + 1200]
    assert "updateMapTarget();" in va_block
    assert "updateContinueReason();" in va_block
    # safety gate preserved
    assert "btnContinue.disabled = !state.dest || !state.pickup || !coordsPresent;" in va_block


def test_0b_csp_nonce_preserved():
    src = _src()
    assert '<script nonce="{{ csp_nonce }}">' in src
    assert 'src="https://cdn.jsdelivr.net/npm/leaflet@1.9.4/dist/leaflet.js"' in src
    assert "onclick=" not in src
    assert "onsubmit=" not in src or "addEventListener('submit'" in src
