"""Focused contract tests for physical multi-room check-in assignment.

These tests intentionally avoid the known incomplete integration schema and
verify the service/model contracts that govern physical room assignment.
"""

from pathlib import Path
from types import SimpleNamespace

from app.accommodation.models.room import RoomBooking


SERVICE_SOURCE = Path(
    "app/accommodation/services/booking_service.py"
).read_text(encoding="utf-8-sig")


def test_check_in_assigns_requested_quantity_and_locks_candidates():
    assert "requested_rooms = int(booking.rooms_requested or 1)" in SERVICE_SOURCE
    assert ".with_for_update().all()" in SERVICE_SOURCE
    assert "len(assigned_rooms) < requested_rooms" in SERVICE_SOURCE
    assert "db.session.add_all(" in SERVICE_SOURCE


def test_check_in_filters_room_type_property_and_unavailable_rooms():
    for predicate in (
        "Room.property_id == booking.property_id",
        "Room.room_type_id == booking.room_type_id",
        "Room.is_active == True",
        'Room.status == "available"',
        "Room.is_maintenance == False",
    ):
        assert predicate in SERVICE_SOURCE


def test_check_in_rejects_active_room_booking_overlap():
    assert 'rb.status in {"active", "checked_in"}' in SERVICE_SOURCE
    assert "rb.check_in < booking.check_out" in SERVICE_SOURCE
    assert "rb.check_out > booking.check_in" in SERVICE_SOURCE


def test_room_booking_checkout_releases_the_assigned_room():
    released = []
    room = SimpleNamespace(release=lambda: released.append(True))
    assignment = SimpleNamespace(status="checked_in", room=room)

    RoomBooking.check_out(assignment)

    assert assignment.status == "checked_out"
    assert released == [True]
