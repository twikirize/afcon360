"""UI-14-D1 — state-preserving Edit trip path out of Review.

Gap being closed: the Review stage (state `c`) offered only Confirm;
a rider spotting an error had to use browser-back (full state loss) or
submit wrong. The fix adds one `type="button"` Edit trip control that
returns to the editable stage via the existing goTo('a') navigation
without clearing anything; continuing forward re-runs the existing
options/fare recalculation flow.

Pure-file assertions — no DB, no browser. The round-trip behavior
(values intact, no submit, forward flow functional) is proven by
tests/browser/ui14_d1_edit_trip.spec.js (untracked browser specs
directory, per repository convention).
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "templates" / "transport" / "new_home.html"


def _template() -> str:
    return TEMPLATE.read_text(encoding="utf-8")


def test_review_declares_edit_trip_button():
    import re
    text = _template()
    match = re.search(
        r'<button\b[^>]*id="btnEditTrip"[^>]*>', text)
    assert match, "Edit trip control missing from the Review stage"
    tag = match.group(0)
    # type="button" inside #boltForm: the control can never submit.
    assert 'type="button"' in tag
    assert 'aria-label="Edit trip details"' in tag


def test_edit_trip_returns_via_existing_navigation():
    text = _template()
    start = text.index("var btnEditTrip = document.getElementById('btnEditTrip');")
    block = text[start:start + 400]
    assert "btnEditTrip.addEventListener('click', function(){" in block
    assert "goTo('a');" in block
    # No clearing, no reconstruction, no submit on this path.
    assert "preventDefault" not in block
    assert "pickup_geocode" not in block
    assert "dropoff_geocode" not in block


def test_edit_trip_has_dedicated_visible_style():
    text = _template()
    assert "#btnEditTrip{" in text
    assert "#btnEditTrip:focus-visible" in text
    assert "min-height:52px" in text


# --- vehicle preference across Edit-trip reload (D1 follow-up) -----------------

def test_selection_records_preferred_class():
    text = _template()
    assert "preferredClass: null," in text
    assert "state.preferredClass = el.dataset.class;" in text


def test_reload_restores_preferred_class_from_fresh_options():
    text = _template()
    start = text.index("function renderOptions(opts, currency){")
    block = text[start:text.index("function selectOption(", start)]
    # Preferred match wins; fare/details still come from the fresh node
    # via selectOption (never restored from stale state).
    assert "state.preferredClass" in block
    assert "'.bolt-veh[data-class=\"' + state.preferredClass" in block.replace(
        "\n", " ")
    assert "if (!target) target = first;" in block
    assert "if (target) target.click();" in block
    # Absent/unavailable preference falls back to existing first-option path.
    assert "var first = optionsBox.querySelector('.bolt-veh');" in block
