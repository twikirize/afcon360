"""LIFECYCLE-TRUTHFULNESS — a transport booking committed CONFIRMED for
assignment purposes must NEVER be presented to the rider (or the admin
inbox) as a confirmed ride before a driver has accepted.

Scope: creation-notification copy, the rider matching page copy, and the
rider status-sync badge labels. The status MODEL is untouched
(BookingStatus.CONFIRMED, single STATUS_TRANSITIONS graph) — only wording
that overstated certainty was corrected.

Notification tests stub persistence (NotificationService.send /
_notify_admins); the rider-page test renders the real route with the
canonical rider fixtures.
"""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from app.notifications.models import NotificationType
from app.notifications.services import NotificationService
from app.transport.models import BookingStatus
from tests.test_geo_rider_tracking import (
    _rider_client,
    _seed_booking,
    _seed_owner,
)
from tests.test_transport_rider_page import _html


def _stub_booking(**overrides):
    base = {
        "user_id": 42,
        "booking_reference": "TR260922JLR0K0",
        "pickup_location": "Nakawa",
        "dropoff_location": "Garden City",
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def _capture_send():
    return patch.object(NotificationService, "send")


def test_creation_notification_never_claims_confirmation():
    booking = _stub_booking()
    with patch.object(
        NotificationService, "module_for_booking", return_value="transport"
    ), _capture_send() as mock_send, patch.object(
        NotificationService, "_notify_admins"
    ) as mock_admins:
        NotificationService.notify_transport_ride_requested(booking)

    rider_calls = [
        c for c in mock_send.call_args_list if c.kwargs.get("user_id") == 42
    ]
    assert rider_calls, "rider (user_id=42) received no ride_requested notice"
    kwargs = rider_calls[0].kwargs
    assert kwargs["notification_type"] == NotificationType.BOOKING_UPDATE
    assert "finding your driver" in kwargs["message"].lower(), kwargs["message"]
    assert "confirmed" not in kwargs["message"].lower(), kwargs["message"]

    assert mock_admins.call_count == 1
    admin_msg = mock_admins.call_args.kwargs["message"]
    assert "finding a driver" in admin_msg.lower(), admin_msg
    assert "confirmed" not in admin_msg.lower(), admin_msg
    assert mock_admins.call_args.kwargs["domain"] == "transport"


def test_driver_assigned_claims_assignment_not_confirmation():
    booking = _stub_booking()
    with _capture_send() as mock_send:
        NotificationService.send_transport_notification(
            user_id=42,
            booking=booking,
            notification_type="driver_assigned",
            channel="in_app",
        )
    message = mock_send.call_args.kwargs["message"]
    assert "assigned to your ride" in message, message
    assert "confirmed" not in message.lower(), message


def test_listener_dispatches_ride_requested_not_booking_confirmed():
    from app.notifications.signals import transport_booking_created

    booking = _stub_booking()
    with patch.object(
        NotificationService,
        "notify_transport_ride_requested",
    ) as m_ride, patch.object(
        NotificationService,
        "notify_booking_confirmed",
    ) as m_confirmed:
        transport_booking_created.send(booking=booking)
    assert m_ride.call_count >= 1, "listener did not dispatch ride_requested"
    assert m_confirmed.call_count == 0, (
        "listener still dispatches booking_confirmed for transport"
    )


def test_matching_ride_page_uses_true_wording(app, client):
    owner = _seed_owner(app, "trth")
    _, ref = _seed_booking(app, owner, BookingStatus.CONFIRMED)
    _rider_client(app, client, owner)
    resp = client.get(f"/transport/rides/{ref}")
    assert resp.status_code == 200, resp.status_code
    html = _html(resp)

    # Step trail, timeline and badge: request-stage wording only.
    assert "Finding Driver" in html          # status-flow sf-label
    assert "Request received" in html        # timeline tl-label
    assert "Finding your driver" in html     # server badge + matching card
    assert (
        "Your request is still being matched and no driver has been "
        "assigned yet. Cancelling now will not incur a fee."
    ) in html

    # The old certainty claim is gone from the cancel-dialog copy.
    assert "Your booking is confirmed but no driver has been assigned yet" not in html


def test_rider_status_sync_badge_labels_match_server():
    js = (
        Path(__file__).resolve().parents[2]
        / "static" / "js" / "modules" / "transport" / "rider_status_sync.js"
    ).read_text(encoding="utf-8")
    assert "confirmed: 'Finding your driver'" in js
    assert "no_match: 'No match found'" in js