"""Regression tests for event venue-zone changes and submitted deadlines."""
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.events.services import EventService


def test_event_location_change_requires_zone_in_multi_zone_country():
    event = SimpleNamespace(
        city="New York", venue="Old Venue", country="US",
        timezone_name="America/New_York",
    )
    with pytest.raises(ValueError, match="timezone is required"):
        EventService._resolve_event_timezone_for_update(
            event, {"city": "Los Angeles", "venue": "New Venue"}
        )


def test_event_location_change_uses_new_explicit_venue_timezone():
    event = SimpleNamespace(
        city="New York", venue="Old Venue", country="US",
        timezone_name="America/New_York",
    )
    zone = EventService._resolve_event_timezone_for_update(
        event,
        {
            "city": "Los Angeles",
            "venue": "New Venue",
            "timezone_name": "America/Los_Angeles",
        },
    )
    assert zone == "America/Los_Angeles"


def test_submitted_event_deadlines_are_applied_in_new_venue_timezone():
    event = SimpleNamespace(
        registration_opens_at=None,
        registration_closes_at=None,
    )
    EventService._apply_registration_deadline_updates(
        event,
        {
            "registration_opens_at": "2026-11-07T12:00",
            "registration_closes_at": "2026-11-08T09:30",
        },
        "Africa/Kampala",
    )
    assert event.registration_opens_at == datetime(
        2026, 11, 7, 9, 0, tzinfo=timezone.utc
    )
    assert event.registration_closes_at == datetime(
        2026, 11, 8, 6, 30, tzinfo=timezone.utc
    )


def test_event_location_change_does_not_reuse_stale_same_timezone_without_confirmation():
    event = SimpleNamespace(
        city="New York", venue="Old Venue", country="US",
        timezone_name="America/New_York",
    )
    with pytest.raises(ValueError, match="timezone is required"):
        EventService._resolve_event_timezone_for_update(
            event,
            {
                "city": "Los Angeles", "venue": "New Venue",
                "timezone_name": "America/New_York",
                "timezone_name_confirmed": "false",
            },
        )


def test_event_location_change_can_reconfirm_the_same_timezone():
    event = SimpleNamespace(
        city="New York", venue="Old Venue", country="US",
        timezone_name="America/New_York",
    )
    zone = EventService._resolve_event_timezone_for_update(
        event,
        {
            "city": "Another New York City", "venue": "New Venue",
            "timezone_name": "America/New_York",
            "timezone_name_confirmed": "true",
        },
    )
    assert zone == "America/New_York"

