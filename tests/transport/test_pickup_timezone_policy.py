"""Server-side transport pickup timezone resolution regression tests."""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pytest

from app.transport.services.pickup_timezone import timezone_for_pickup_coordinates
from app.utils.time_policy import resolve_local_datetime


def test_pickup_coordinate_resolves_kampala_timezone_offline():
    assert timezone_for_pickup_coordinates(-0.0419, 32.4435) == "Africa/Kampala"


def test_new_york_pickup_coordinate_resolves_new_york_timezone_offline():
    assert timezone_for_pickup_coordinates(40.6413, -73.7781) == "America/New_York"


def test_kampala_noon_is_0900_utc_and_four_am_new_york_on_november_7_2026():
    resolved = resolve_local_datetime("2026-11-07T12:00", "Africa/Kampala")
    assert resolved["utc_datetime"] == datetime(2026, 11, 7, 9, tzinfo=timezone.utc)
    assert resolved["local_datetime"] == "2026-11-07T12:00:00"
    assert resolved["utc_offset"] == "+0300"
    assert resolved["utc_datetime"].astimezone(ZoneInfo("America/New_York")).strftime("%H:%M %Z") == "04:00 EST"


def test_pickup_in_ocean_is_rejected_instead_of_assuming_a_zone():
    with pytest.raises(ValueError, match="no resolvable land timezone"):
        timezone_for_pickup_coordinates(0.0, -30.0)
