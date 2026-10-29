"""Pin the rider-facing fare label after the amount has been accepted."""

from pathlib import Path


def test_request_tracker_labels_the_accepted_amount_as_confirmed():
    template = Path("templates/transport/rides/request_show.html").read_text(
        encoding="utf-8"
    )
    assert '<div class="request-label">Confirmed fare</div>' in template
    assert (
        "Your locations, vehicle preference and confirmed fare have been saved."
        in template
    )
    assert '<div class="request-label">Fare estimate</div>' not in template
