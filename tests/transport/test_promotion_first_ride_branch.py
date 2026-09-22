"""S-12 behavioral proof: the first-ride branch is reachable and correct.

Before S-12 all mock promo codes were 2024-expired, so every call
returned EXPIRED_CODE and the NOT_FIRST_RIDE branch (fixed in S-10)
could never execute. With fresh 2026-12-31 dates, both branches are
exercised here with the Booking query stubbed — no database touched.
"""
from unittest.mock import MagicMock, patch

from app.transport.services.promotion_service import PromotionService


def _run_validate(prior_booking_count: int):
    """Call validate_promo_code with the prior-rides query stubbed."""
    mock_booking = MagicMock()
    mock_booking.query.filter.return_value.count.return_value = (
        prior_booking_count
    )
    with patch(
        "app.transport.services.promotion_service.Booking", mock_booking
    ):
        return PromotionService.validate_promo_code(
            promo_code="FIRSTRIDE", customer_id=4242
        )


def test_first_ride_promo_rejected_when_prior_booking_exists():
    result = _run_validate(prior_booking_count=1)
    assert result["code"] == "NOT_FIRST_RIDE", result
    assert result["valid"] is False


def test_first_ride_promo_accepted_for_new_rider():
    result = _run_validate(prior_booking_count=0)
    assert result["valid"] is True, result
    assert result["success"] is True
