"""UI-01 — rider pickup typed-search: form wiring (template + module bytes).

Defect being closed: the rider could only resolve a pickup by GPS fix or map
pin.  A typed place name carried no coordinates, and no provider result ever
reached the booking payload, so a search-selected pickup could not claim
source='search' truthfully (H2: that claim requires a resolved GeocodeResult
whose provider justifies it).

Correction (this node, UI side):
  * `pickup_geocode` / `dropoff_geocode` hidden fields echo the SELECTED
    provider result verbatim (JSON.stringify) so the server can rehydrate a
    GeocodeResult;
  * an external, nonce'd module (`pickup-search.js`) renders the shared
    `/geo/api/geocode` contract into an accessible listbox under the pickup
    field and writes label/coords/source/evidence on selection;
  * the swap handler carries evidence across sides (mirrors how
    `__mapSwapSides` already carries `pkSrc/dfSrc`);
  * a one-line inline bridge (`window.__boltValidateA`) lets the module
    re-run validation after a selection when the map is unavailable.

Pure-file assertions — no DB, no browser.  Mirrors the template-byte
pattern established by tests/transport/test_node3_source_provenance.py.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "templates" / "transport" / "new_home.html"
SEARCH_JS = ROOT / "static" / "js" / "modules" / "transport" / "pickup-search.js"


def _template() -> str:
    return TEMPLATE.read_text(encoding="utf-8")


def _search_js() -> str:
    return SEARCH_JS.read_text(encoding="utf-8")


# --- hidden evidence contract -------------------------------------------------

def test_form_declares_both_geocode_evidence_fields():
    text = _template()
    assert 'id="pickup_geocode"' in text
    assert 'name="pickup_geocode"' in text
    assert 'id="dropoff_geocode"' in text
    assert 'name="dropoff_geocode"' in text


def test_geocode_fields_sit_with_the_backend_contract_fields():
    """The evidence echo must ride along the booking POST, i.e. live inside
    the form, next to the other hidden-backend-contract inputs."""
    text = _template()
    form_start = text.index('<form method="POST"')
    form_end = text.index("</form>", form_start)
    form_html = text[form_start:form_end]
    assert 'name="pickup_geocode"' in form_html
    assert 'name="dropoff_geocode"' in form_html
    assert 'name="pickup_source"' in form_html


# --- module include (CSP) -----------------------------------------------------

def test_form_includes_pickup_search_module_with_nonce():
    text = _template()
    expected = (
        '<script nonce="{{ csp_nonce }}" '
        'src="{{ url_for(\'static\', '
        'filename=\'js/modules/transport/pickup-search.js\') }}"></script>'
    )
    assert expected in text
    # and it is loaded from the same include site as geo-map.js
    # (anchor on filename='...' — a prose comment also names the file)
    assert text.index("filename='js/geo/geo-map.js'") < text.index(
        "filename='js/modules/transport/pickup-search.js'"
    )


# --- listbox ------------------------------------------------------------------

def test_form_declares_pickup_results_listbox():
    text = _template()
    match = re.search(r"<div\b[^>]*id=\"pickupResults\"[^>]*>", text)
    assert match, "pickup results container missing from the template"
    assert 'role="listbox"' in match.group(0)
    assert 'aria-label="Pickup search results"' in match.group(0)
    # the list starts hidden; the module opens it after a response
    assert 'id="pickupResults"' in text and "hidden></div>" in text


# --- swap wiring (evidence travels with its side) -----------------------------

def test_swap_handler_swaps_geocode_evidence_fields():
    text = _template()
    swap_start = text.index("btnSwap.addEventListener")
    swap_block = text[swap_start:text.index("});", swap_start)]
    assert "getElementById('pickup_geocode')" in swap_block
    assert "getElementById('dropoff_geocode')" in swap_block
    assert (
        "var swapGeo = pg.value; pg.value = dg.value; dg.value = swapGeo;"
        in swap_block
    )
    # provenance swap (D3) must still be wired alongside it
    assert "__mapSwapSides" in swap_block


# --- inline bridge ------------------------------------------------------------

def test_inline_bridge_exposes_validate_a_for_the_module():
    text = _template()
    assert "window.__boltValidateA = validateA;" in text


# --- the module consumes the shared endpoint contract -------------------------

def test_module_calls_the_shared_geocode_endpoint():
    js = _search_js()
    assert "'/geo/api/geocode'" in js
    assert "encodeURIComponent" in js
    assert "'Accept': 'application/json'" in js
    assert "credentials: 'same-origin'" in js


def test_module_writes_the_selection_into_the_contract_fields():
    js = _search_js()
    # verbatim evidence echo
    assert "geoField.value = JSON.stringify(result)" in js
    # coords + provenance, selection only ever 'search'
    assert "srcField.value = 'search'" in js
    assert "latField.value = String(lat)" in js
    assert "lngField.value = String(lng)" in js
    # map pin carries the search provenance (mirrors the GPS handler)
    assert "__mapPinPickup(lat, lng, result.label, 'search')" in js
    assert "__boltValidateA" in js


def test_module_clears_evidence_on_manual_keystroke():
    js = _search_js()
    input_handler = re.search(
        r"input\.addEventListener\('input', function \(\) \{(?P<body>.*?)\}\);",
        js,
        re.S,
    )
    assert input_handler, "module has no input listener"
    body = input_handler.group("body")
    assert "geoField.value = ''" in body
    assert "scheduleSearch()" in body


def test_module_guards_against_stale_responses():
    js = _search_js()
    assert "searchSeq += 1" in js
    assert "mySeq !== searchSeq" in js
    assert "abort" in js


def test_module_degraded_states_are_truthful():
    js = _search_js()
    # empty results -> non-interactive "No matches" row, never coordinates
    assert "'No matches'" in js
    assert "aria-disabled" in js
    # network failure -> transient hint, prior pickup untouched
    assert "'Search unavailable'" in js
    # a malformed result is refused, not coerced
    assert "validResult" in js
