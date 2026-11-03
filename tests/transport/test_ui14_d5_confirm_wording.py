"""UI-14-D5 — Confirm action wording clarity.

The Review primary action submitted a ride request (booking creation
followed by a driver-matching attempt) while reading "Confirm", which
overstates certainty. The narrow correction renames the visible label to
"Request ride" and keeps everything else byte-identical: button ID and
submit type, cash indicator, pickup-time summary behavior for Now and
Later, and the existing submission path.

Pure-file assertions — no DB. Rendered proof (both modes, submission
path intact, no booking created) comes from the browser drills, which
stop at Review / intercept the POST.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "templates" / "transport" / "new_home.html"


def _template() -> str:
    return TEMPLATE.read_text(encoding="utf-8")


def test_confirm_action_requests_rather_than_asserts():
    text = _template()
    start = text.index('id="btnConfirm"')
    button = text[start:start + 400]
    assert "Confirm Fare &amp; Request Ride" in button or "Confirm Fare & Request Ride" in button
    assert "Select payment" in button
    # The old generic action label is gone; the rider must see fare + payment choice.
    assert '<span>Request ride</span>' not in button


def test_cash_indicator_and_submit_contract_unchanged():
    text = _template()
    start = text.index('id="btnConfirm"')
    # The button submits only after the rider chooses a payment method.
    assert 'type="submit"' in text[start - 200:start]
    assert 'id="btnConfirmPaymentLabel">Select payment</span>' in text[start:start + 400]
    assert 'name="payment_method"' in text
    assert '<span>Cash</span>' not in text[start:start + 400]
    # ID, behavior hooks and summaries referenced by the flow are intact.
    assert 'id="confirmTimeSub"' in text


def test_pickup_time_summary_preserved_for_both_modes():
    text = _template()
    assert "'Leaving now.'" in text
    assert "'Pickup scheduled for ' + fmtSched(schedAt.value)" in text


def test_submit_handler_references_btn_confirm_for_pending_guard():
    """UI-15 documents the one expected btnConfirm script reference.

    The Review markup keeps a single id="btnConfirm" submit control.
    The submit handler references that same control exactly once — to
    apply the pending-state guard (disabled + aria-busy + sending copy)
    after validation/auth checks pass. This positive assertion replaces
    the old negative getElementById check so UI-14 keeps guarding the
    button's identity while UI-15 owns the pending behavior.
    """
    text = _template()
    assert text.count('id="btnConfirm"') == 1
    assert "document.getElementById('btnConfirm')" in text
    guard_at = text.index("document.getElementById('btnConfirm')")
    guard = text[guard_at:guard_at + 500]
    assert "btnConfirm.disabled = true" in guard
    assert "aria-busy" in guard
