"""Focused tests for room-aware accommodation availability."""

from datetime import date
from types import SimpleNamespace

from app.accommodation.models.room import RoomType
from app.accommodation.services.availability_service import AvailabilityService
from app.accommodation.services.host_service import HostService


class _RoomTypeQuery:
    def __init__(self, room_types):
        self._room_types = room_types

    def filter_by(self, **kwargs):
        return self

    def all(self):
        return self._room_types


def _availability(monkeypatch, available_units, guests, requested_rooms=1):
    room_type = SimpleNamespace(
        id=10,
        name="Standard",
        max_guests=2,
        total_units=10,
        base_price_per_night=100,
        currency="USD",
        is_active=True,
    )
    monkeypatch.setattr(RoomType, "query", _RoomTypeQuery([room_type]))
    monkeypatch.setattr(
        HostService,
        "available_units",
        staticmethod(lambda *args, **kwargs: available_units),
    )

    return AvailabilityService.get_room_type_availability(
        property_id=1,
        check_in=date(2026, 9, 1),
        check_out=date(2026, 9, 2),
        num_guests=guests,
        num_rooms=requested_rooms,
    )["room_types"][0]


def test_group_of_100_is_rejected_when_only_ten_rooms_are_available(monkeypatch):
    result = _availability(monkeypatch, available_units=10, guests=100)

    assert result["rooms_needed"] == 50
    assert result["can_accommodate_guests"] is False
    assert result["is_available"] is False
    assert result["status"] == "limited"


def test_one_booking_does_not_hide_the_other_nine_rooms(monkeypatch):
    result = _availability(monkeypatch, available_units=9, guests=2)

    assert result["rooms_needed"] == 1
    assert result["available_units"] == 9
    assert result["is_available"] is True
    assert result["status"] == "available"