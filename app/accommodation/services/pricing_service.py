# app/accommodation/services/pricing_service.py
"""
Pricing Service - Calculate booking totals with fees, taxes, and discounts.
"""

from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, Optional
from app.accommodation.models.property import Property
import logging

logger = logging.getLogger(__name__)


class PricingService:
    """
    Calculates transparent accommodation booking price breakdowns.
    """

    @staticmethod
    def _money(value) -> Decimal:
        """Normalize values to two-decimal Decimal money amounts."""
        return Decimal(str(value or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    @staticmethod
    def _percentage(value) -> Decimal:
        """Normalize percentage values as Decimal."""
        return Decimal(str(value or 0))

    @staticmethod
    def calculate_total(
            property: Property,
            check_in: date,
            check_out: date,
            num_guests: int = 1,
            room_type_id: Optional[int] = None,
            num_rooms: int = 1,
            promo_discount: Decimal = Decimal("0"),
            loyalty_discount: Decimal = Decimal("0"),
            wallet_credit: Decimal = Decimal("0"),
            tax_rate_pct: Optional[Decimal] = None,
    ) -> Dict[str, Decimal]:
        """
        Calculate a production-grade price breakdown.

        Includes base price, cleaning fee, service fee, taxes, optional discounts,
        and the final total. Discount values are absolute money amounts and are
        capped so the final total never drops below zero.
        """
        nights = (check_out - check_in).days
        rooms = max(1, int(num_rooms or 1))

        if nights <= 0:
            raise ValueError("Check-out must be after check-in")

        if room_type_id:
            from app.accommodation.models.room import RoomType
            room_type = RoomType.query.get(room_type_id)
            if not room_type or room_type.property_id != property.id:
                raise ValueError("Room type not found or does not belong to this property")
            nightly_rate = PricingService._money(room_type.base_price_per_night)
            cleaning_fee = PricingService._money(room_type.cleaning_fee) * rooms
            service_fee_pct = PricingService._percentage(room_type.service_fee_pct)
        else:
            nightly_rate = PricingService._money(property.base_price_per_night)
            cleaning_fee = PricingService._money(property.cleaning_fee) * rooms
            service_fee_pct = PricingService._percentage(property.service_fee_pct)

        subtotal = PricingService._money(nightly_rate * nights * rooms)
        service_fee = PricingService._money(subtotal * (service_fee_pct / Decimal("100")))

        if tax_rate_pct is None:
            tax_rate_pct = PricingService._percentage(getattr(property, "tax_rate_pct", 0))
        else:
            tax_rate_pct = PricingService._percentage(tax_rate_pct)

        taxable_amount = subtotal + cleaning_fee + service_fee
        taxes = PricingService._money(taxable_amount * (tax_rate_pct / Decimal("100")))

        gross_total = PricingService._money(taxable_amount + taxes)
        discounts = {
            "promo_discount": PricingService._money(promo_discount),
            "loyalty_discount": PricingService._money(loyalty_discount),
            "wallet_credit": PricingService._money(wallet_credit),
        }
        total_discount = PricingService._money(sum(discounts.values(), Decimal("0")))
        discount_applied = min(total_discount, gross_total)
        total = PricingService._money(gross_total - discount_applied)

        return {
            "nightly_rate": nightly_rate,
            "nights": nights,
            "num_rooms": rooms,
            "subtotal": subtotal,
            "cleaning_fee": cleaning_fee,
            "service_fee": service_fee,
            "service_fee_pct": service_fee_pct,
            "tax_rate_pct": tax_rate_pct,
            "taxes": taxes,
            "discounts": discounts,
            "discount_total": discount_applied,
            "gross_total": gross_total,
            "total": total,
        }

    @staticmethod
    def calculate_refund(
            booking,
            cancellation_date: date
    ) -> Dict[str, Decimal]:
        """
        Calculate refund amount based on cancellation policy.

        Returns:
            {
                'refund_amount': Decimal,
                'policy': str,
                'explanation': str
            }
        """
        days_until_checkin = (booking.check_in - cancellation_date).days
        policy = booking.accommodation_property.cancellation_policy

        if policy == "flexible":
            if days_until_checkin >= 1:
                return {
                    'refund_amount': booking.total_amount,
                    'policy': 'flexible',
                    'explanation': 'Full refund (cancelled at least 24h before check-in)'
                }
            else:
                return {
                    'refund_amount': Decimal('0'),
                    'policy': 'flexible',
                    'explanation': 'No refund (cancelled within 24h of check-in)'
                }

        elif policy == "moderate":
            if days_until_checkin >= 5:
                return {
                    'refund_amount': booking.total_amount,
                    'policy': 'moderate',
                    'explanation': 'Full refund (cancelled at least 5 days before check-in)'
                }
            elif days_until_checkin >= 1:
                refund = booking.total_amount * Decimal('0.5')
                return {
                    'refund_amount': refund,
                    'policy': 'moderate',
                    'explanation': '50% refund (cancelled 1-4 days before check-in)'
                }
            else:
                return {
                    'refund_amount': Decimal('0'),
                    'policy': 'moderate',
                    'explanation': 'No refund (cancelled within 24h of check-in)'
                }

        elif policy == "strict":
            if days_until_checkin >= 7:
                refund = booking.total_amount * Decimal('0.5')
                return {
                    'refund_amount': refund,
                    'policy': 'strict',
                    'explanation': '50% refund (cancelled at least 7 days before check-in)'
                }
            else:
                return {
                    'refund_amount': Decimal('0'),
                    'policy': 'strict',
                    'explanation': 'No refund (cancelled within 7 days of check-in)'
                }

        else:  # SUPER_STRICT
            return {
                'refund_amount': Decimal('0'),
                'policy': 'super_strict',
                'explanation': 'Non-refundable booking'
            }
