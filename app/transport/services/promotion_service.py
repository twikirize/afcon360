#app/transport/services/promotion_service.py
"""
AFCON360 Transport Module - Promotion Service
Handles discounts, promo codes, and special offers
"""

from datetime import datetime, timezone
from decimal import Decimal
from typing import Dict, List, Optional, Any, Tuple
import uuid
from flask import current_app
from sqlalchemy.exc import SQLAlchemyError

from app.extensions import db
from app.transport.models import Booking
from app.utils.exceptions import ValidationError, NotFoundError
from app.utils.monitoring import monitor_endpoint, record_metric
from app.utils.security import sanitize_input


class PromotionService:
    """Service for managing promotions and discounts"""

    @staticmethod
    @monitor_endpoint("validate_promo_code")
    def validate_promo_code(promo_code: str,
                            customer_id: Optional[int] = None,
                            booking_data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Validate a promo code

        Args:
            promo_code: Promo code to validate
            customer_id: ID of customer (for user-specific codes)
            booking_data: Booking details (for eligibility checks)

        Returns:
            Validation result
        """
        try:
            # Clean promo code
            clean_code = promo_code.strip().upper()

            # In production, query from database
            # For now, use mock promo codes
            valid_codes = {
                'WELCOME10': {
                    'discount_type': 'percentage',
                    'discount_value': 10,
                    'min_amount': Decimal('20.00'),
                    'max_discount': Decimal('10.00'),
                    'valid_until': datetime(2024, 12, 31, tzinfo=timezone.utc),
                    'usage_limit': 1,
                    'user_specific': False,
                    'service_types': ['on_demand', 'airport_transfer']
                },
                'AFCON25': {
                    'discount_type': 'percentage',
                    'discount_value': 25,
                    'min_amount': Decimal('50.00'),
                    'max_discount': Decimal('25.00'),
                    'valid_until': datetime(2024, 7, 31, tzinfo=timezone.utc),
                    'usage_limit': 3,
                    'user_specific': False,
                    'service_types': ['stadium_shuttle', 'hotel_transfer']
                },
                'FIRSTRIDE': {
                    'discount_type': 'fixed',
                    'discount_value': Decimal('15.00'),
                    'min_amount': Decimal('25.00'),
                    'max_discount': Decimal('15.00'),
                    'valid_until': datetime(2024, 12, 31, tzinfo=timezone.utc),
                    'usage_limit': 1,
                    'user_specific': True,
                    'first_ride_only': True
                }
            }

            # Check if code exists
            if clean_code not in valid_codes:
                return {
                    'success': False,
                    'valid': False,
                    'message': 'Invalid promo code',
                    'code': 'INVALID_CODE'
                }

            promo_details = valid_codes[clean_code]

            # Check expiry
            if datetime.now(timezone.utc) > promo_details['valid_until']:
                return {
                    'success': False,
                    'valid': False,
                    'message': 'Promo code has expired',
                    'code': 'EXPIRED_CODE'
                }

            # Check if user-specific and first ride
            if promo_details.get('first_ride_only') and customer_id:
                # Check if user has taken a ride before
                has_previous_rides = Booking.query.filter_by(
                    customer_id=customer_id,
                    status__in=['completed', 'paid']
                ).count() > 0

                if has_previous_rides:
                    return {
                        'success': False,
                        'valid': False,
                        'message': 'Promo code only valid for first ride',
                        'code': 'NOT_FIRST_RIDE'
                    }

            # Check service type eligibility
            if booking_data and 'service_types' in promo_details:
                service_type = booking_data.get('service_type')
                if service_type not in promo_details['service_types']:
                    return {
                        'success': False,
                        'valid': False,
                        'message': f'Promo code not valid for {service_type} service',
                        'code': 'INVALID_SERVICE_TYPE'
                    }

            # Check minimum amount
            if booking_data and 'estimated_price' in booking_data:
                estimated_price = Decimal(str(booking_data['estimated_price']))
                if estimated_price < promo_details['min_amount']:
                    return {
                        'success': False,
                        'valid': False,
                        'message': f'Minimum booking amount of ${promo_details["min_amount"]} required',
                        'code': 'MIN_AMOUNT_NOT_MET'
                    }

            # Calculate discount amount
            discount_amount = PromotionService._calculate_discount(
                promo_details=promo_details,
                booking_amount=Decimal(str(booking_data.get('estimated_price', 0))) if booking_data else Decimal('0.00')
            )

            return {
                'success': True,
                'valid': True,
                'message': 'Promo code is valid',
                'data': {
                    'promo_code': clean_code,
                    'discount_amount': float(discount_amount),
                    'discount_type': promo_details['discount_type'],
                    'discount_value': float(promo_details['discount_value']),
                    'max_discount': float(promo_details.get('max_discount', discount_amount)),
                    'min_amount': float(promo_details['min_amount']),
                    'valid_until': promo_details['valid_until'].isoformat(),
                    'terms': PromotionService._get_promo_terms(promo_details)
                }
            }

        except Exception as e:
            current_app.logger.error(f"Error validating promo code: {e}", exc_info=True)
            return {
                'success': False,
                'valid': False,
                'message': f"Error validating promo code: {str(e)}",
                'code': 'VALIDATION_ERROR'
            }

    @staticmethod
    def _calculate_discount(promo_details: Dict[str, Any],
                            booking_amount: Decimal) -> Decimal:
        """Calculate discount amount"""
        discount_type = promo_details['discount_type']
        discount_value = promo_details['discount_value']

        if discount_type == 'percentage':
            # Percentage discount
            discount = booking_amount * (Decimal(str(discount_value)) / Decimal('100'))
            max_discount = promo_details.get('max_discount')
            if max_discount:
                discount = min(discount, Decimal(str(max_discount)))
        else:
            # Fixed amount discount
            discount = Decimal(str(discount_value))

        # Ensure discount doesn't exceed booking amount
        return min(discount, booking_amount)

    @staticmethod
    def _get_promo_terms(promo_details: Dict[str, Any]) -> List[str]:
        """Get terms and conditions for promo code"""
        terms = []

        if promo_details['discount_type'] == 'percentage':
            terms.append(f"{promo_details['discount_value']}% discount")
        else:
            terms.append(f"${promo_details['discount_value']} off")

        if promo_details['min_amount'] > Decimal('0.00'):
            terms.append(f"Minimum purchase: ${promo_details['min_amount']}")

        if promo_details.get('max_discount'):
            terms.append(f"Maximum discount: ${promo_details['max_discount']}")

        if promo_details.get('valid_until'):
            valid_until = promo_details['valid_until'].strftime('%b %d, %Y')
            terms.append(f"Valid until: {valid_until}")

        if promo_details.get('usage_limit'):
            terms.append(f"Usage limit: {promo_details['usage_limit']} per user")

        if promo_details.get('service_types'):
            services = ', '.join(promo_details['service_types'])
            terms.append(f"Valid for: {services} services")

        if promo_details.get('first_ride_only'):
            terms.append("Valid for first ride only")

        return terms

    @staticmethod
    @monitor_endpoint("apply_promo_code")
    def apply_promo_code(booking_id: int, promo_code: str) -> Dict[str, Any]:
        """Apply promo code to a booking"""
        try:
            booking = Booking.query.get(booking_id)
            if not booking:
                raise NotFoundError(
                    message="Booking not found",
                    resource_type="booking",
                    resource_id=booking_id
                )

            # Check if promo code already applied
            if booking.promo_code:
                raise ValidationError(
                    message="Promo code already applied to this booking",
                    code="PROMO_ALREADY_APPLIED"
                )

            # Validate promo code
            validation_result = PromotionService.validate_promo_code(
                promo_code=promo_code,
                customer_id=booking.customer_id,
                booking_data={
                    'service_type': booking.service_type.value,
                    'estimated_price': float(booking.estimated_price) if booking.estimated_price else 0.0
                }
            )

            if not validation_result['valid']:
                raise ValidationError(
                    message=validation_result['message'],
                    code=validation_result.get('code', 'INVALID_PROMO')
                )

            # Calculate discount
            discount_amount = Decimal(str(validation_result['data']['discount_amount']))

            # Update booking
            booking.promo_code = promo_code
            booking.discount_amount = discount_amount

            # Recalculate final price if already set
            if booking.final_price:
                booking.final_price = booking.final_price - discount_amount
            elif booking.estimated_price:
                booking.final_price = booking.estimated_price - discount_amount

            db.session.commit()

            # Record metrics
            record_metric(
                'promo_code_applied',
                tags={
                    'promo_code': promo_code,
                    'discount_type': validation_result['data']['discount_type']
                },
                value=1
            )

            return {
                'success': True,
                'message': 'Promo code applied successfully',
                'data': {
                    'booking_id': booking_id,
                    'promo_code': promo_code,
                    'discount_amount': float(discount_amount),
                    'new_price': float(booking.final_price) if booking.final_price else float(
                        booking.estimated_price - discount_amount) if booking.estimated_price else 0.0
                }
            }

        except (NotFoundError, ValidationError) as e:
            db.session.rollback()
            raise
        except SQLAlchemyError as e:
            db.session.rollback()
            current_app.logger.error(f"Database error applying promo code: {e}", exc_info=True)
            raise
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error applying promo code: {e}", exc_info=True)
            raise

    @staticmethod
    @monitor_endpoint("create_promo_code")
    def create_promo_code(promo_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new promo code (admin function)"""
        try:
            # Validate promo data
            required_fields = ['code', 'discount_type', 'discount_value']
            if not all(field in promo_data for field in required_fields):
                raise ValidationError(
                    message="Missing required fields",
                    details={'required_fields': required_fields},
                    code="MISSING_FIELDS"
                )

            # Generate unique code if not provided
            promo_code = promo_data.get('code', '').strip().upper()
            if not promo_code:
                promo_code = PromotionService._generate_promo_code()

            # Create promo code record
            # In production, save to database
            # For now, return success

            return {
                'success': True,
                'message': 'Promo code created successfully',
                'data': {
                    'promo_code': promo_code,
                    'discount_type': promo_data['discount_type'],
                    'discount_value': promo_data['discount_value'],
                    'valid_until': promo_data.get('valid_until'),
                    'usage_limit': promo_data.get('usage_limit'),
                    'min_amount': promo_data.get('min_amount', 0)
                }
            }

        except ValidationError:
            raise
        except Exception as e:
            current_app.logger.error(f"Error creating promo code: {e}", exc_info=True)
            return {
                'success': False,
                'message': f"Error creating promo code: {str(e)}",
                'data': {}
            }

    @staticmethod
    def _generate_promo_code() -> str:
        """Generate a unique promo code"""
        import random
        import string

        # Format: AFCON + 6 random characters
        prefix = "AFCON"
        random_chars = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
        return f"{prefix}{random_chars}"

# ------------------------
# Singleton getter (module-level)
# ------------------------
from threading import Lock

_promotion_service_instance = None
_promotion_service_lock = Lock()

def get_promotion_service():
    """Singleton getter for PromotionService"""
    global _promotion_service_instance
    if _promotion_service_instance is None:
        with _promotion_service_lock:
            if _promotion_service_instance is None:
                _promotion_service_instance = PromotionService()
    return _promotion_service_instance
