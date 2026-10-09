"""UI-14-F1 — Later-without-time can never silently become an immediate ride.

Defect being closed: selecting Later with an empty/invalid datetime-local
left every gate open — validateA() and the submit guard ignored schedule
state, Review rendered "Scheduled for later today", and
finalizePickupTime() silently substituted the current time at submit.

Correction (this node, template inline flow only):
  * isScheduleValid(): Now always valid; Later requires a non-empty,
    parseable datetime-local value (mirrors the server pickup_time
    contract: valid ISO-8601, no new lead-time/timezone policy).
  * validateA() gates Find a Ride on schedule validity, with an
    accessible explanatory message.
  * setSchedule() + schedAt input/change revalidate both gates at once.
  * selectOption() enables Review only with a committable schedule.
  * renderConfirm() never implies a schedule without a valid time.
  * The submit handler revalidates (recovery: back to the form) and
    finalizePickupTime() reports success instead of substituting now.

Pure-file assertions — no DB, no browser. Mirrors the template-byte
pattern established by tests/transport/test_node3_source_provenance.py.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "templates" / "transport" / "new_home.html"


def _template() -> str:
    return TEMPLATE.read_text(encoding="utf-8")


def test_schedule_validity_helper_exists():
    text = _template()
    assert "function isScheduleValid(){" in text
    assert "if (state.schedule !== 'later') return true;" in text
    assert "if (!v) return false;" in text
    assert "return !isNaN(new Date(v).getTime());" in text


def test_find_a_ride_gate_requires_valid_schedule():
    text = _template()
    assert ("btnContinue.disabled = !state.dest || !state.pickup "
            "|| !coordsPresent || !isScheduleValid();") in text


def test_disabled_reason_explains_missing_schedule():
    text = _template()
    assert ("else if (!isScheduleValid()) msg = "
            "'Select a scheduled time to continue.';") in text


def test_schedule_and_time_changes_revalidate_both_gates():
    text = _template()
    assert "function syncReviewGate(){" in text
    assert "btnReview.disabled = !isScheduleValid();" in text
    # mode switch revalidates immediately (previously it validated nothing)
    set_schedule = text[text.index("function setSchedule(mode){"):
                         text.index("schedNowBtn.addEventListener")]
    assert "validateA();" in set_schedule
    assert "syncReviewGate();" in set_schedule
    # time edits revalidate immediately
    assert ("schedAt.addEventListener('input', function(){ "
            "validateA(); syncReviewGate(); });") in text
    assert ("schedAt.addEventListener('change', function(){ "
            "validateA(); syncReviewGate(); });") in text


def test_review_button_requires_committable_schedule():
    text = _template()
    assert "btnReview.disabled = false;" not in text
    assert "btnReview.disabled = !isScheduleValid();" in text


def test_review_never_implies_schedule_without_valid_time():
    text = _template()
    assert "later today" not in text
    assert ("? (isScheduleValid() ? 'Scheduled for ' + fmtSched(schedAt.value)"
            " : 'Select a scheduled time.')" in text)


def test_finalize_reports_instead_of_substituting_now():
    text = _template()
    start = text.index("function finalizePickupTime(){")
    end = text.index("function ", start + len("function finalizePickupTime(){"))
    body = text[start:end]
    assert "if (!schedAt.value) return false;" in body
    assert "if (isNaN(d.getTime())) return false;" in body
    assert "setPickupTimeNow();" in body
    assert "return true;" in body


def test_submit_guard_revalidates_schedule_with_recovery():
    text = _template()
    start = text.index("form.addEventListener('submit', function(e){")
    block = text[start:start + 1500]
    assert ("if (!state.dest || !state.pickup || !state.selectedClass "
            "|| !isScheduleValid()) {") in block
    assert "if (!finalizePickupTime()) { e.preventDefault(); return goTo('a'); }" in block


def test_now_path_unchanged():
    """Now keeps the exact pre-existing current-time behavior."""
    text = _template()
    assert "state.schedule = mode;" in text
    assert re.search(
        r"function finalizePickupTime\(\)\{.*?setPickupTimeNow\(\);",
        text, re.S) is not None
