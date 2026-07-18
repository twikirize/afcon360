# app/accommodation/services/pricing_service.py
"""
Pricing Service - Calculate booking totals with fees and taxes
"""

from datetime import date
from decimal import Decimal
from typing import Dict, Optional
from app.accommodation.models.property import Property
import logging

logger = logging.getLogger(__name__)


class PricingService:
    """
    Calculates total price for accommodation bookings
    """

    # Platform fees (configurable)
    PLATFORM_SERVICE_FEE_PERCENT = Decimal('10.0')  # 10%

    @staticmethod
    def calculate_total(
            property: Property,
            check_in: date,
            check_out: date,
            num_guests: int = 1,
            room_type_id: Optional[int] = None
    ) -> Dict[str, Decimal]:
        """
        Calculate total price breakdown.

        Returns:
            {
                'nightly_rate': Decimal,
                'nights': int,
                'subtotal': Decimal,
                'cleaning_fee': Decimal,
                'service_fee': Decimal,
                'total': Decimal
            }
        """
        nights = (check_out - check_in).days

        if nights <= 0:
            raise ValueError("Check-out must be after check-in")

        # Base nightly rate and fees - check if room_type_id is provided
        if room_type_id:
            from app.accommodation.models.property import RoomType
            room_type = RoomType.query.get(room_type_id)
            if not room_type or room_type.property_id != property.id:
                raise ValueError("Room type not found or does not belong to this property")
            nightly_rate = room_type.base_price_per_night
            cleaning_fee = room_type.cleaning_fee or Decimal('0')
            service_fee_pct = room_type.service_fee_pct
        else:
            nightly_rate = property.base_price_per_night
            cleaning_fee = property.cleaning_fee or Decimal('0')
            service_fee_pct = property.service_fee_pct

        # Calculate subtotal
        subtotal = nightly_rate * nights

        # Service fee (platform commission)
        service_fee = subtotal * (service_fee_pct / Decimal('100'))

        # Total
        total = subtotal + cleaning_fee + service_fee

        return {
            'nightly_rate': nightly_rate,
            'nights': nights,
            'subtotal': subtotal,
            'cleaning_fee': cleaning_fee,
            'service_fee': service_fee,
            'total': total
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
        from app.accommodation.models.property import AccommodationCancellationPolicy

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
