#app/transport/sevices/payment_service.py

"""
AFCON360 Transport Module - Payment Service
Handles payment processing and transactions
"""

from datetime import datetime, timezone
from decimal import Decimal
from typing import Dict, List, Optional, Any
import uuid
from flask import current_app
from sqlalchemy.exc import SQLAlchemyError

from app.extensions import db
from app.transport.models import Booking, BookingStatus
from app.utils.exceptions import ValidationError, NotFoundError, ServiceUnavailableError
from app.utils.monitoring import monitor_endpoint, record_metric, start_span
from app.utils.security import sanitize_input
from app.utils.validators import validate_payment
from app.utils.audit import audit_log


class PaymentService:
    """Service for handling transport payments"""

    @staticmethod
    @monitor_endpoint("process_payment")
    def process_payment(booking_id: int, payment_data: Dict[str, Any],
                        request_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Process payment for a booking

        Args:
            booking_id: ID of booking to pay for
            payment_data: Payment details
            request_id: Unique request ID

        Returns:
            Payment processing result
        """
        span = start_span("process_payment")

        try:
            # Validate payment data
            sanitized_data = sanitize_input(payment_data)
            validation_result = validate_payment(sanitized_data)

            if not validation_result['valid']:
                raise ValidationError(
                    message="Payment validation failed",
                    details=validation_result['errors'],
                    code="VALIDATION_FAILED"
                )

            # Get booking
            booking = Booking.query.get(booking_id)
            if not booking:
                raise NotFoundError(
                    message="Booking not found",
                    resource_type="booking",
                    resource_id=booking_id
                )

            # Check if booking can be paid for
            if booking.status not in [BookingStatus.COMPLETED, BookingStatus.CONFIRMED]:
                raise ValidationError(
                    message=f"Cannot process payment for booking in {booking.status.value} status",
                    code="INVALID_BOOKING_STATUS"
                )

            # Calculate final price
            final_price = PaymentService._calculate_final_price(booking)

            # Generate payment reference
            payment_ref = PaymentService._generate_payment_reference()

            # Process payment (simplified - integrate with actual payment gateway)
            payment_method = sanitized_data.get('payment_method', 'cash')

            if payment_method == 'cash':
                # Cash payment - mark as pending
                payment_status = 'pending'
                payment_processed = False
            else:
                # Card/online payment - check if enabled
                if not current_app.config.get('PAYMENT_PROCESSING_ENABLED', False):
                    raise ValidationError(
                        message="Online payment processing is disabled",
                        code="PAYMENT_DISABLED"
                    )

                payment_status = 'processing'
                payment_processed = PaymentService._process_online_payment(
                    amount=final_price,
                    payment_data=sanitized_data
                )

                if payment_processed:
                    payment_status = 'completed'
                else:
                    payment_status = 'failed'

            # Update booking with payment info
            booking.final_price = final_price
            booking.payment_method = payment_method
            booking.payment_status = payment_status
            booking.payment_reference = payment_ref
            booking.payment_processed_at = datetime.now(timezone.utc) if payment_processed else None

            if payment_status == 'completed':
                booking.status = BookingStatus.PAID
                booking.paid_at = datetime.now(timezone.utc)

            db.session.commit()

            # Create audit log
            audit_log(
                action='payment_processed',
                entity_type='booking',
                entity_id=booking_id,
                user_id=booking.customer_id,
                details={
                    'amount': float(final_price),
                    'payment_method': payment_method,
                    'payment_status': payment_status,
                    'payment_reference': payment_ref
                },
                request_id=request_id
            )

            # Record metrics
            record_metric(
                'payment_processed',
                tags={
                    'payment_method': payment_method,
                    'payment_status': payment_status,
                    'amount_range': PaymentService._get_amount_range(final_price)
                },
                value=1
            )

            return {
                'success': True,
                'message': 'Payment processed successfully',
                'data': {
                    'booking_id': booking_id,
                    'amount': float(final_price),
                    'payment_method': payment_method,
                    'payment_status': payment_status,
                    'payment_reference': payment_ref,
                    'booking_status': booking.status.value
                }
            }

        except (ValidationError, NotFoundError) as e:
            db.session.rollback()
            span.set_status("ERROR", str(e))
            record_metric('payment_processing', tags={'status': 'failed', 'error_type': type(e).__name__}, value=1)
            raise

        except SQLAlchemyError as e:
            db.session.rollback()
            current_app.logger.error(f"Database error processing payment: {e}", exc_info=True)
            span.set_status("ERROR", f"Database error: {str(e)}")
            record_metric('payment_processing', tags={'status': 'failed', 'error_type': 'database'}, value=1)
            raise ServiceUnavailableError(
                message="Payment service temporarily unavailable",
                code="SERVICE_UNAVAILABLE"
            )

        finally:
            span.end()

    @staticmethod
    @monitor_endpoint("calculate_fare")
    def calculate_fare(booking_data: Dict[str, Any]) -> Dict[str, Any]:
        """Calculate estimated fare for a booking"""
        try:
            # Calculate base fare
            estimated_price = PaymentService._calculate_estimated_fare(booking_data)

            # Add any applicable charges
            surge_multiplier = PaymentService._get_surge_multiplier(booking_data)
            final_price = estimated_price * surge_multiplier

            # Apply discounts if any
            discount = PaymentService._calculate_discount(booking_data)
            discounted_price = final_price - discount

            return {
                'success': True,
                'data': {
                    'estimated_price': float(estimated_price),
                    'surge_multiplier': float(surge_multiplier),
                    'discount': float(discount),
                    'final_price': float(discounted_price),
                    'currency': 'USD',
                    'breakdown': {
                        'base_fare': float(estimated_price * Decimal('0.6')),
                        'distance_charge': float(estimated_price * Decimal('0.3')),
                        'service_fee': float(estimated_price * Decimal('0.1'))
                    }
                }
            }

        except Exception as e:
            current_app.logger.error(f"Error calculating fare: {e}", exc_info=True)
            return {
                'success': False,
                'message': f"Error calculating fare: {str(e)}",
                'data': {}
            }

    @staticmethod
    def _calculate_final_price(booking: Booking) -> Decimal:
        """Calculate final price for booking"""
        base_price = booking.estimated_price or Decimal('0.00')

        # Add any additional charges
        additional_charges = Decimal('0.00')

        # Add waiting time charges if applicable
        if booking.waiting_time_minutes and booking.waiting_time_minutes > 5:
            waiting_charge = Decimal(str((booking.waiting_time_minutes - 5) * 0.5))
            additional_charges += waiting_charge

        # Add tolls/road charges
        if booking.additional_charges:
            additional_charges += booking.additional_charges

        # Apply discount if any
        discount = booking.discount_amount or Decimal('0.00')

        final_price = base_price + additional_charges - discount

        # Ensure minimum price
        min_price = Decimal('5.00')
        return max(final_price, min_price)

    @staticmethod
    def _calculate_estimated_fare(booking_data: Dict[str, Any]) -> Decimal:
        """Calculate estimated fare from booking data"""
        # Similar to BookingService._calculate_estimated_price
        base_prices = {
            'on_demand': 10.00,
            'airport_transfer': 25.00,
            'stadium_shuttle': 15.00,
            'hotel_transfer': 20.00,
            'city_tour': 30.00
        }

        service_type = booking_data.get('service_type', 'on_demand')
        base_price = Decimal(str(base_prices.get(service_type, 10.00)))

        distance = booking_data.get('estimated_distance', 5)
        distance_rate = Decimal('2.50')
        distance_cost = Decimal(str(distance)) * distance_rate

        vehicle_class = booking_data.get('vehicle_class', 'comfort')
        class_multipliers = {
            'economy': 1.0,
            'comfort': 1.2,
            'premium': 1.5,
            'van': 1.8,
            'luxury': 2.0
        }
        multiplier = Decimal(str(class_multipliers.get(vehicle_class, 1.0)))

        return (base_price + distance_cost) * multiplier

    @staticmethod
    def _get_surge_multiplier(booking_data: Dict[str, Any]) -> Decimal:
        """Get surge pricing multiplier"""
        from datetime import datetime
        hour = datetime.now().hour

        if (7 <= hour <= 9) or (17 <= hour <= 19):
            return Decimal('1.3')

        return Decimal('1.0')

    @staticmethod
    def _calculate_discount(booking_data: Dict[str, Any]) -> Decimal:
        """Calculate applicable discount"""
        # Check for promo codes
        promo_code = booking_data.get('promo_code')
        if promo_code:
            # Validate promo code
            return Decimal('5.00')  # Example discount

        return Decimal('0.00')

    @staticmethod
    def _process_online_payment(amount: Decimal, payment_data: Dict[str, Any]) -> bool:
        """Process online payment with production safety checks"""
        # Check if payment processing is enabled
        if not current_app.config.get('PAYMENT_PROCESSING_ENABLED', False):
            raise RuntimeError("Payment processing is disabled in production. Configure PAYMENT_PROCESSING_ENABLED and integrate with a real payment gateway.")

        # In production, this should integrate with Stripe, PayPal, etc.
        # For now, we'll raise an error to prevent accidental use of mock payments
        raise NotImplementedError(
            "Online payment processing not implemented. "
            "Integrate with a real payment gateway for production use. "
            "Set PAYMENT_PROCESSING_ENABLED=true only after integration."
        )

    @staticmethod
    def _generate_payment_reference() -> str:
        """Generate unique payment reference"""
        import random
        import string
        prefix = "PAY"
        timestamp = datetime.now().strftime("%Y%m%d")
        random_chars = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
        return f"{prefix}{timestamp}{random_chars}"

    @staticmethod
    def _get_amount_range(amount: Decimal) -> str:
        """Categorize amount for metrics"""
        amount_float = float(amount)
        if amount_float < 10:
            return '0-10'
        elif amount_float < 25:
            return '10-25'
        elif amount_float < 50:
            return '25-50'
        elif amount_float < 100:
            return '50-100'
        else:
            return '100+'

# ------------------------
# Singleton getter (module-level)
# ------------------------
from threading import Lock

_payment_service_instance = None
_payment_service_lock = Lock()

def get_payment_service():
    """Singleton getter for PaymentService"""
    global _payment_service_instance
    if _payment_service_instance is None:
        with _payment_service_lock:
            if _payment_service_instance is None:
                _payment_service_instance = PaymentService()
    return _payment_service_instance
