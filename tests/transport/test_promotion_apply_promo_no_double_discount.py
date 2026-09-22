"""S-11 behavioral proof: apply_promo_code must not touch final_price directly.

The discount is recorded in booking.promotion_discount and the fare
engine recomputes final_price from components on the next call.
Decrementing final_price inside apply_promo_code as well would apply
the discount twice.

This test bypasses validate_promo_code (all mock promo codes are
2024-expired per S-12) so it exercises the accumulation path in
isolation. No database is touched: the session is stubbed.
"""
from decimal import Decimal
from unittest.mock import patch

from app.transport.models import Booking, ServiceType
from app.transport.services.promotion_service import PromotionService


def _fixture_booking() -> Booking:
    booking = Booking()
    booking.user_id = 1
    booking.service_type = ServiceType.ON_DEMAND
    booking.promotion_discount = Decimal("0.00")
    booking.final_price = Decimal("100.00")
    booking.base_price = Decimal("100.00")
    booking.booking_metadata = {}
    return booking


def test_apply_promo_accumulates_discount_without_touching_final_price():
    booking = _fixture_booking()

    fake_validation = {
        "valid": True,
        "success": True,
        "message": "ok",
        "data": {
            "discount_amount": 10.0,
            "discount_type": "fixed",
            "discount_value": 10.0,
        },
    }

    with patch.object(
        PromotionService,
        "validate_promo_code",
        staticmethod(lambda **kw: fake_validation),
    ):
        with patch(
            "app.transport.services.promotion_service.db"
        ) as mock_db:
            mock_db.session.get.return_value = booking
            result = PromotionService.apply_promo_code(
                booking_id=1, promo_code="TEST10"
            )

    assert result["success"] is True
    assert booking.promotion_discount == Decimal("10.00"), (
        f"discount not accumulated: {booking.promotion_discount}"
    )
    assert booking.final_price == Decimal("100.00"), (
        f"final_price directly modified: {booking.final_price}"
    )
    assert "TEST10" in (booking.booking_metadata or {}).get("promo_codes", [])
