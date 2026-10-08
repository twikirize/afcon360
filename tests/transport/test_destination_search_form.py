"""Rider discovery — destination typed search: form wiring (template bytes).

Defect being closed: the destination input carried text only. Coordinates
reached the booking payload solely via map pin, so a typed place name could
never resolve and Find Ride stayed disabled for riders who do not use the
map. The pickup search (UI-01) proved the contract; destination mirrors it:

  * `dropoff_geocode` hidden field echoes the SELECTED provider result
    verbatim (JSON.stringify) so the server rehydrates a GeocodeResult;
  * an external, nonce'd module (`dropoff-search.js`) renders the shared
    `/geo/api/geocode` contract into an accessible listbox under the
    destination field and writes label/coords/source/evidence on selection;
  * `window.__mapPinDropoff` mirrors `window.__mapPinPickup` so a search
    selection keeps the map truthful with 'search' provenance;
  * the pickup module gained the same minimum-query-length guard the
    server already enforces (len<2 = honest no-result, zero provider I/O).

Pure-file assertions — no DB, no browser. Mirrors the template-byte
pattern established by tests/transport/test_node3_source_provenance.py.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "templates" / "transport" / "new_home.html"
DEST_JS = ROOT / "static" / "js" / "modules" / "transport" / "dropoff-search.js"
PICKUP_JS = ROOT / "static" / "js" / "modules" / "transport" / "pickup-search.js"


def _template() -> str:
    return TEMPLATE.read_text(encoding="utf-8")


def _dest_js() -> str:
    return DEST_JS.read_text(encoding="utf-8")


def _pickup_js() -> str:
    return PICKUP_JS.read_text(encoding="utf-8")


# --- destination listbox markup ------------------------------------------------

def test_form_declares_destination_results_listbox():
    text = _template()
    match = re.search(r"<div\b[^>]*id=\"dropoffResults\"[^>]*>", text)
    assert match, "destination results container missing from the template"
    assert 'role="listbox"' in match.group(0)
    assert 'aria-label="Destination search results"' in match.group(0)


def test_form_declares_destination_search_note():
    text = _template()
    match = re.search(r"<div\b[^>]*id=\"dropoffSearchNote\"[^>]*>", text)
    assert match, "destination search note missing from the template"
    assert 'role="status"' in match.group(0)
    assert 'aria-live="polite"' in match.group(0)


def test_destination_search_markup_lives_inside_the_form():
    text = _template()
    form_start = text.index('<form method="POST"')
    form_end = text.index("</form>", form_start)
    form_html = text[form_start:form_end]
    assert 'id="dropoffSearch"' in form_html
    assert 'id="dropoffResults"' in form_html
    assert 'id="dropoffSearchNote"' in form_html


# --- module include (CSP) ------------------------------------------------------

def test_form_includes_dropoff_search_module_with_nonce():
    text = _template()
    expected = (
        '<script nonce="{{ csp_nonce }}" '
        'src="{{ url_for(\'static\', '
        'filename=\'js/modules/transport/dropoff-search.js\') }}"></script>'
    )
    assert expected in text


# --- map hook ------------------------------------------------------------------

def test_inline_map_exposes_dropoff_pin_hook():
    text = _template()
    assert "window.__mapPinDropoff = function(lat, lng, label, src){" in text


# --- the module consumes the shared endpoint contract --------------------------

def test_dest_module_calls_the_shared_geocode_endpoint():
    js = _dest_js()
    assert "'/geo/api/geocode'" in js
    assert "encodeURIComponent" in js
    assert "'Accept': 'application/json'" in js
    assert "credentials: 'same-origin'" in js
    # no parallel provider architecture, no direct provider calls,
    # no client-side API keys: the browser only ever calls OUR endpoint
    assert "api.geoapify.com" not in js
    assert "api_key" not in js
    assert "GEOAPIFY" not in js


def test_dest_module_enforces_minimum_query_length():
    js = _dest_js()
    assert "text.length < 2" in js


def test_dest_module_debounces_and_cancels_stale_requests():
    js = _dest_js()
    assert "DEBOUNCE_MS = 300" in js
    assert "searchSeq += 1" in js
    assert "mySeq !== searchSeq" in js
    assert "abort" in js


def test_dest_module_writes_the_selection_into_the_contract_fields():
    js = _dest_js()
    assert "geoField.value = JSON.stringify(result)" in js
    assert "srcField.value = 'search'" in js
    assert "latField.value = String(lat)" in js
    assert "lngField.value = String(lng)" in js
    assert "__mapPinDropoff(lat, lng, result.label, 'search')" in js
    assert "__boltValidateA" in js


def test_dest_module_clears_evidence_on_manual_keystroke():
    js = _dest_js()
    input_handler = re.search(
        r"input\.addEventListener\('input', function \(\) \{(?P<body>.*?)\}\);",
        js,
        re.S,
    )
    assert input_handler, "module has no input listener"
    body = input_handler.group("body")
    assert "geoField.value = ''" in body
    assert "scheduleSearch()" in body


def test_dest_module_degraded_states_are_truthful():
    js = _dest_js()
    assert "'No matches'" in js
    assert "aria-disabled" in js
    assert "'Search unavailable'" in js
    assert "validResult" in js


def test_dest_module_unavailable_state_keeps_wrapper_rendered():
    """Regression guard for the UI-01 Test C defect class: the failure
    note must be visible, so the collapsed list must not hide its
    own container."""
    js = _dest_js()
    start = js.index("function showUnavailable()")
    end = js.index("}", js.index("setNote('Search unavailable');", start))
    body = js[start:end]
    assert "wrap.classList.add('is-open')" in body
    assert "aria-expanded', 'false'" in body


# --- pickup scheduling parity (§§7-8: min length on both sides) -----------------

def test_pickup_module_enforces_the_same_minimum_query_length():
    """The server answers len<2 as an honest no-result without provider
    I/O; the pickup client must not send such queries either."""
    js = _pickup_js()
    assert "MIN_QUERY_LEN = 2" in js
    assert "text.length < MIN_QUERY_LEN" in js
