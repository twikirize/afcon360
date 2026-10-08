"""UI-11 copy regression: success flash must not imply driver acceptance.

Ratified finding (UI-11 trace, adversarial review): the booking state
machine is correct - ``confirmed`` = booking accepted / matching active /
no driver yet. The only rider-facing defect was the finality-sounding
success flash produced by ``book_transport``. This pins, through the real
``POST /transport/book`` route and its redirect render, that:

  1. the successful booking flow still produces the booking reference;
  2. the rider-facing flash uses the corrected wording;
  3. the old finality-sounding wording is absent from the success message.

Presentation-only: no state, transition, timeline, or MATCH-01 contract
assertions are made or changed here.
"""
from datetime import datetime, timedelta, timezone

from app.extensions import db
from tests.test_transport_booking_route_path import (
    _FakeRedis,
    _bolt_form,
    _new_pickup_time,
    _promote_user_to_tier3,
)

OLD_WORDING = "Booking confirmed! Reference"
NEW_WORDING = "Ride request received! We’re finding your driver. Reference:"


def test_success_flash_uses_ride_request_wording(
    app, authenticated_client, test_user, monkeypatch
):
    fake = _FakeRedis()
    monkeypatch.setattr(
        "app.transport.services.offer_service.redis_client", fake
    )

    with app.app_context():
        rider = db.session.merge(test_user)  # reattach expired fixture row
        _promote_user_to_tier3(app, rider.id)

    # 1) Booking flow succeeds and produces the booking reference.
    resp = authenticated_client.post(
        "/transport/book",
        data=_bolt_form(_new_pickup_time()),
        follow_redirects=False,
    )
    assert resp.status_code in (301, 302), resp.status_code
    location = resp.headers.get("Location", "")
    assert "/transport/rides/" in location, location
    ref = location.rstrip("/").rsplit("/", 1)[1]
    assert ref, "redirect carried no booking reference"

    # The flash renders on the redirect target (base.html messages block).
    page = authenticated_client.get(location)
    assert page.status_code == 200, page.status_code
    html = page.get_data(as_text=True)

    # 2) New wording, with the booking reference preserved exactly.
    assert f"{NEW_WORDING} {ref}" in html, (
        "corrected success flash with exact reference not rendered"
    )
    # 3) Old finality-sounding wording absent from the success message.
    assert OLD_WORDING not in html, (
        "old finality-sounding flash wording still rendered"
    )
