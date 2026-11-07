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



def test_country_timezone_default_is_only_used_for_single_zone_countries():
    from app.utils.location_timezone import resolve_location_timezone, timezone_for_country

    assert timezone_for_country("UG") == "Africa/Kampala"
    assert resolve_location_timezone(country="Uganda") == "Africa/Kampala"
    assert timezone_for_country("US") is None
    with pytest.raises(ValueError, match="timezone is required for this location"):
        resolve_location_timezone(country="US")
    assert resolve_location_timezone(
        explicit_timezone="America/New_York", country="US"
    ) == "America/New_York"


def test_event_default_registration_close_is_venue_local_midnight():
    from types import SimpleNamespace
    from app.events.services import EventService

    event = SimpleNamespace(
        start_date=date(2026, 11, 7),
        business_timezone=lambda: "Africa/Kampala",
    )
    close_at = EventService._registration_close_at(event)
    assert close_at == datetime(2026, 11, 6, 21, tzinfo=timezone.utc)


def test_event_registration_deadline_is_interpreted_in_venue_timezone():
    from app.events.services import EventService

    close_at = EventService._parse_datetime(
        "2026-11-07T12:00", "Africa/Kampala"
    )
    assert close_at == datetime(2026, 11, 7, 9, tzinfo=timezone.utc)

def test_event_expiration_uses_the_venue_calendar_day():
    from types import SimpleNamespace
    from app.events.services import EventService

    event = SimpleNamespace(
        end_date=date(2026, 11, 7),
        local_today=lambda: date(2026, 11, 7),
    )
    assert EventService.is_event_expired(event) is False
    event.local_today = lambda: date(2026, 11, 8)
    assert EventService.is_event_expired(event) is True


def test_event_availability_fails_closed_when_venue_timezone_is_unresolved(monkeypatch):
    from types import SimpleNamespace
    from app.events.services import EventService
    from app.events.constants import RegistrationAvailability

    class FakeColumn:
        @staticmethod
        def in_(values):
            return tuple(values)

    class FakeQuery:
        def filter(self, *args, **kwargs):
            return self

        @staticmethod
        def count():
            return 0

    class FakeRegistration:
        event_id = object()
        status = FakeColumn()
        query = FakeQuery()

    monkeypatch.setattr(
        EventService,
        "_get_registration_class",
        staticmethod(lambda: FakeRegistration),
    )
    event = SimpleNamespace(
        id=1,
        start_date=date(2026, 11, 7),
        end_date=date(2026, 11, 8),
        business_timezone=lambda: (_ for _ in ()).throw(
            ValueError("venue timezone is not configured")
        ),
        registration_opens_at=None,
        registration_closes_at=None,
        status="published",
        registration_required=True,
        max_capacity=0,
        ticket_types=[],
        currency="USD",
    )

    result = EventService._availability_snapshot(
        event, datetime(2026, 11, 7, 12, tzinfo=timezone.utc)
    )

    assert result["state"] == RegistrationAvailability.CLOSED.value
    assert result["reason"] == "timezone_unconfigured"

