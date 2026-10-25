"""Regression tests for AFCON360's canonical timezone primitives."""

from datetime import datetime, timezone

import pytest

from app.utils.time import (
    UTC,
    is_aware,
    parse_datetime_to_utc,
    require_aware,
    to_iso_utc,
    to_local,
    to_utc,
    utc_now,
)


def test_utc_now_is_aware_utc():
    value = utc_now()
    assert is_aware(value)
    assert value.utcoffset().total_seconds() == 0


def test_to_utc_normalizes_explicit_offset():
    value = to_utc(datetime.fromisoformat("2026-10-25T12:00:00+03:00"))
    assert value == datetime(2026, 10, 25, 9, 0, tzinfo=UTC)


def test_naive_datetime_fails_closed_without_explicit_timezone():
    with pytest.raises(ValueError, match="timezone offset"):
        parse_datetime_to_utc("2026-10-25T12:00:00")


def test_explicit_local_timezone_converts_wall_time_to_utc():
    value = parse_datetime_to_utc(
        "2026-10-25T12:00:00",
        local_timezone="Africa/Kampala",
    )
    assert value == datetime(2026, 10, 25, 9, 0, tzinfo=UTC)


def test_ambiguous_daylight_saving_wall_time_is_rejected():
    with pytest.raises(ValueError, match="ambiguous"):
        parse_datetime_to_utc(
            "2026-10-25T02:30:00",
            local_timezone="Europe/Berlin",
        )


def test_nonexistent_daylight_saving_wall_time_is_rejected():
    with pytest.raises(ValueError, match="does not exist"):
        parse_datetime_to_utc(
            "2026-03-29T02:30:00",
            local_timezone="Europe/Berlin",
        )


def test_utc_serialization_uses_z_suffix():
    assert to_iso_utc(datetime(2026, 10, 25, 9, 0, tzinfo=UTC)) == "2026-10-25T09:00:00Z"


def test_local_display_conversion_does_not_change_instant():
    utc_value = datetime(2026, 10, 25, 9, 0, tzinfo=timezone.utc)
    local_value = to_local(utc_value, "Africa/Kampala")
    assert local_value.hour == 12
    assert local_value.astimezone(UTC) == utc_value


def test_require_aware_rejects_naive_value():
    with pytest.raises(ValueError, match="timezone offset"):
        require_aware(datetime(2026, 10, 25, 9, 0))
