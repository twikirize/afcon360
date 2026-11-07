"""Calendar boundary and DST regression tests for the platform time policy."""
from datetime import date, datetime, timezone

import pytest

from app.utils.time_policy import (
    choose_display_timezone,
    local_day_utc_bounds,
    local_month_utc_bounds,
    resolve_local_datetime,
)


def test_kampala_midnight_is_2100_utc_previous_day():
    start_utc, end_utc = local_day_utc_bounds(date(2026, 11, 7), "Africa/Kampala")
    assert start_utc == datetime(2026, 11, 6, 21, tzinfo=timezone.utc)
    assert end_utc == datetime(2026, 11, 7, 21, tzinfo=timezone.utc)


def test_month_range_uses_local_calendar_edges():
    start_utc, end_utc = local_month_utc_bounds(date(2026, 11, 7), "Africa/Kampala")
    assert start_utc == datetime(2026, 10, 31, 21, tzinfo=timezone.utc)
    assert end_utc == datetime(2026, 11, 30, 21, tzinfo=timezone.utc)


def test_dst_nonexistent_local_time_is_rejected():
    with pytest.raises(ValueError, match="does not exist"):
        resolve_local_datetime("2026-03-08T02:30", "America/New_York")


def test_dst_ambiguous_local_time_is_rejected():
    with pytest.raises(ValueError, match="ambiguous"):
        resolve_local_datetime("2026-11-01T01:30", "America/New_York")


def test_offset_bearing_time_must_match_pickup_zone():
    with pytest.raises(ValueError, match="offset does not match"):
        resolve_local_datetime("2026-11-07T14:00:00+02:00", "Africa/Kampala")


def test_explicit_offset_maps_to_utc_and_preserves_local_wall_time():
    result = resolve_local_datetime("2026-11-07T12:00:00+03:00", "Africa/Kampala")
    assert result["utc_datetime"] == datetime(2026, 11, 7, 9, tzinfo=timezone.utc)
    assert result["local_datetime"] == "2026-11-07T12:00:00"
    assert result["timezone_name"] == "Africa/Kampala"


def test_display_precedence_business_then_preference_then_browser():
    assert choose_display_timezone(
        business_timezone="Africa/Kampala",
        preferred_timezone="America/New_York",
        browser_timezone="Europe/London",
    ) == "Africa/Kampala"
    assert choose_display_timezone(
        preferred_timezone="America/New_York",
        browser_timezone="Europe/London",
    ) == "America/New_York"
    assert choose_display_timezone(browser_timezone="Europe/London") == "Europe/London"
