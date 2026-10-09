"""UI-14-D3 — quoted ride-option values survive attribute embedding.

Defect being closed: esc() serialized via textContent->innerHTML, which
leaves double quotes intact. Interpolated into the double-quoted
data-breakdown attribute, the JSON truncated at its first quote (observed
live: a lone "{"), JSON.parse threw, state.fareBreakdown became null and
Review fell back to a Total-only row.

Correction: one escaper safe for both text content and double-quoted
attributes (& < > " ', ampersand first). Entities render as literal
characters in text and decode losslessly in attributes.

Pure-file assertions — no DB, no browser. The end-to-end path
(option -> selection -> Review rows, incl. a quote/apostrophe display
name) is proven by tests/browser/ui14_d3_quoted_options.spec.js.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "templates" / "transport" / "new_home.html"


def _template() -> str:
    return TEMPLATE.read_text(encoding="utf-8")


def _esc_body() -> str:
    text = _template()
    start = text.index("function esc(t){")
    end = text.index("}", text.index("replace(/'/g, '&#39;');", start))
    return text[start:end]


def test_escaper_encodes_all_five_delimiters_ampersand_first():
    body = _esc_body()
    for entity in ("&amp;", "&lt;", "&gt;", "&quot;", "&#39;"):
        assert entity in body, f"esc() must emit {entity}"
    # Replacement order matters: ampersand MUST be escaped before the
    # entities introduced below are written, or they double-encode.
    assert body.index("&amp;") < body.index("&lt;")
    assert body.index("&amp;") < body.index("&quot;")


def test_escaper_no_longer_relies_on_innerHTML():
    body = _esc_body()
    assert "innerHTML" not in body
    assert "textContent" not in body


def test_breakdown_attribute_still_flows_through_esc():
    text = _template()
    assert ("'data-breakdown=\"' + "
            "esc(JSON.stringify(o.fare_breakdown || {})) + '\" '") in text


def test_selection_still_parses_breakdown_and_branches_review():
    text = _template()
    assert "state.fareBreakdown = JSON.parse(el.dataset.breakdown" in text
    assert re.search(
        r"if \(b\) \{.*?fareRow\('Base fare'",
        text, re.S) is not None
