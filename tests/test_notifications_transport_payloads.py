"""NOTIF-TRANSPORT behavioral proof: transport payloads use public refs,
route to the rider, and scope admin broadcast (BL-04, BL-05, BL-13, BL-15).

All persistence is stubbed (NotificationService.send / _notify_admins) —
no database is touched. Stubs carry the transport Booking shape
(user_id, booking_reference, string-or-dict locations, internal id).
"""
from types import SimpleNamespace
from unittest.mock import patch

from app.notifications.services import NotificationService


def _stub_booking(**overrides):
    base = {
        "user_id": 42,
        "id": 999,
        "booking_reference": "TR260922JLR0K0",
        "pickup_location": "Nakawa",
        "dropoff_location": "Garden City",
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def _capture_send():
    return patch.object(NotificationService, "send", autospec=True)


def test_1_driver_assigned_payload_uses_booking_reference():
    booking = _stub_booking()
    with _capture_send() as mock_send:
        NotificationService.send_transport_notification(
            user_id=42,
            booking=booking,
            notification_type="driver_assigned",
            channel="in_app",
        )
    assert mock_send.call_count == 1
    kwargs = mock_send.call_args.kwargs
    assert kwargs["data"]["booking_id"] == "TR260922JLR0K0"
    assert kwargs["link"].endswith("/TR260922JLR0K0")
    # FS-2: rider deep link must resolve to the ref-keyed rider page,
    # never the admin internal-id route (which 404s on a reference).
    assert kwargs["link"] == "/transport/rides/TR260922JLR0K0"
    assert "Nakawa" in kwargs["message"]
    assert "{" not in kwargs["message"], kwargs["message"]
    assert "booking_code" not in kwargs["data"]
    assert "scheduled_time" not in kwargs["data"]

    # Dict-shape location resolves via the text property, not repr().
    dict_booking = _stub_booking(
        pickup_location={"address": "Nakawa, Kampala"},
        pickup_location_text="Nakawa, Kampala",
    )
    with _capture_send() as mock_send2:
        NotificationService.send_transport_notification(
            user_id=42,
            booking=dict_booking,
            notification_type="driver_assigned",
            channel="in_app",
        )
    message = mock_send2.call_args.kwargs["message"]
    assert "Nakawa, Kampala" in message
    assert "{'address'" not in message


def test_2_booking_confirmed_routes_to_rider():
    booking = _stub_booking()
    with patch.object(
        NotificationService, "module_for_booking", return_value="transport"
    ), _capture_send() as mock_send, patch.object(
        NotificationService, "_notify_admins", autospec=True
    ):
        NotificationService.notify_booking_confirmed(booking)
    rider_calls = [
        c for c in mock_send.call_args_list if c.kwargs.get("user_id") == 42
    ]
    assert rider_calls, "rider (user_id=42) received no notification"


def test_3_admin_broadcast_is_scoped_to_transport_domain():
    booking = _stub_booking()
    with patch.object(
        NotificationService, "module_for_booking", return_value="transport"
    ), _capture_send(), patch.object(
        NotificationService, "_notify_admins", autospec=True
    ) as mock_admins:
        NotificationService.notify_booking_confirmed(booking)
    assert mock_admins.call_count == 1
    assert mock_admins.call_args.kwargs.get("domain") == "transport"

    roles = NotificationService._resolve_recipient_roles(domain="transport")
    assert roles == ["admin", "owner", "super_admin", "transport_admin"], roles


def test_4_no_internal_id_in_transport_payloads():
    booking = _stub_booking()
    with patch.object(
        NotificationService, "module_for_booking", return_value="transport"
    ), _capture_send() as mock_send, patch.object(
        NotificationService, "_notify_admins", autospec=True
    ) as mock_admins:
        NotificationService.send_transport_notification(
            user_id=42,
            booking=booking,
            notification_type="driver_assigned",
            channel="in_app",
        )
        NotificationService.notify_booking_confirmed(booking)
    blobs = []
    for call in mock_send.call_args_list:
        blobs.append(str(call.kwargs.get("data")))
        blobs.append(str(call.kwargs.get("link")))
        blobs.append(str(call.kwargs.get("message")))
    for call in mock_admins.call_args_list:
        blobs.append(str(call.kwargs.get("data")))
        blobs.append(str(call.kwargs.get("message")))
    for blob in blobs:
        assert "999" not in blob, blob
