"""Regression tests for the accommodation date-range invariant."""

from datetime import date, timedelta

from app.accommodation.services.availability_service import AvailabilityService


def test_empty_stay_range_is_not_available():
    check_in = date(2026, 9, 1)

    available, blocked_dates, error = AvailabilityService.is_range_available(
        property_id=1,
        check_in=check_in,
        check_out=check_in,
    )

    assert available is False
    assert blocked_dates == []
    assert error == "Check-out must be after check-in"


def test_availability_cascade_rejects_reverse_range_before_database_lookup():
    check_in = date(2026, 9, 2)

    result = AvailabilityService.get_availability_cascade(
        property_id=999999,
        check_in=check_in,
        check_out=check_in - timedelta(days=1),
    )

    assert result["error"] == "Check-out must be after check-in"