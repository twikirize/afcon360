#app/transport/services/payment_service.py

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
from app.transport.models import Booking, BookingStatus, PaymentStatus
from app.wallet.services.wallet_service import WalletService
from app.utils.exceptions import ValidationError, NotFoundError, ServiceUnavailableError
from app.utils.monitoring import monitor_endpoint, record_metric
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
        try:
            # Validate payment data
            sanitized_data = dict(payment_data)
            is_valid, errors = validate_payment(sanitized_data)

            if not is_valid:
                raise ValidationError(
                    message=f"Payment validation failed: {errors}"
                )

            # Get booking
            booking = db.session.get(Booking, booking_id)
            if not booking:
                raise NotFoundError(
                    message="Booking not found",
                    resource_type="booking",
                    resource_id=booking_id
                )

            # Check if booking can be paid for
            if booking.status not in [BookingStatus.COMPLETED, BookingStatus.CONFIRMED]:
                raise ValidationError(
                        message=f"Cannot process payment for booking in {booking.status} status"
                )

            # Calculate final price
            final_price = PaymentService._calculate_final_price(booking)

            # Generate payment reference
            payment_ref = PaymentService._generate_payment_reference()

            # Process payment
            payment_method = sanitized_data.get('payment_method', 'cash')

            # Validate payment method against configured methods
            PaymentService._validate_payment_method(booking, payment_method)

            wallet_txn_id = None
            if payment_method == 'wallet':
                wallet_service = WalletService()
                account = wallet_service.account_repo.get_by_user_id(booking.user_id, booking.currency)
                if not account:
                    raise ValidationError(message="No wallet account found")
                balance = wallet_service.ledger_repo.get_balance(account.id, booking.currency)
                if balance < final_price:
                    raise ValidationError(message="Insufficient wallet balance")
                client_request_id = f"TRN-PAY-{booking_id}-{int(datetime.now(timezone.utc).timestamp())}"
                result = wallet_service.withdraw(
                    account_id=str(account.id),
                    amount=final_price,
                    currency=booking.currency,
                    client_request_id=client_request_id,
                    metadata={"transport_booking_id": str(booking_id), "payment_reference": payment_ref}
                )
                if result.get("status") != "success":
                    raise ValidationError(message=result.get("error", "Wallet payment failed"))
                wallet_txn_id = result.get("transaction_id")
                payment_status = 'completed'
                payment_processed = True
            elif payment_method == 'cash':
                payment_status = 'pending'
                payment_processed = False
            else:
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
            booking.payment_status = PaymentStatus.CAPTURED if payment_processed else PaymentStatus.PENDING
            booking.payment_gateway_reference = payment_ref
            booking.payment_captured_at = datetime.now(timezone.utc) if payment_processed else None
            booking.wallet_transaction_id = wallet_txn_id or booking.wallet_transaction_id

            if payment_processed:
                booking.status = BookingStatus.CONFIRMED

            db.session.commit()

            # Create audit log
            audit_log(
                action='payment_processed',
                resource_type='booking',
                resource_id=booking_id,
                user_id=booking.user_id,
                details={
                    'amount': float(final_price),
                    'payment_method': payment_method,
                    'payment_status': payment_status,
                    'payment_reference': payment_ref,
                    'request_id': request_id
                }
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
                    'booking_status': booking.status
                }
            }

        except (ValidationError, NotFoundError) as e:
            db.session.rollback()
            record_metric('payment_processing', tags={'status': 'failed', 'error_type': type(e).__name__}, value=1)
            raise

        except SQLAlchemyError as e:
            db.session.rollback()
            current_app.logger.error(f"Database error processing payment: {e}", exc_info=True)
            record_metric('payment_processing', tags={'status': 'failed', 'error_type': 'database'}, value=1)
            raise ServiceUnavailableError(
                message="Payment service temporarily unavailable"
            )


    @staticmethod
    def _calculate_final_price(booking: Booking) -> Decimal:
        """Calculate final price for booking (canonical fare engine)."""
        from app.transport.services.fare_service import calculate_final
        return calculate_final(
            booking.base_price,
            toll_fees=booking.toll_fees,
            parking_fees=booking.parking_fees,
            promotion_discount=booking.promotion_discount,
        )




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
    def _validate_payment_method(booking: Booking, payment_method: str) -> None:
        """Validate that the payment method is allowed for this booking."""
        try:
            from app.transport.services.payment_config import (
                get_payment_config_service,
                get_user_country,
                get_user_wallet_status,
            )

            config_service = get_payment_config_service()
            country = get_user_country(booking.user_id)
            user_has_wallet = get_user_wallet_status(booking.user_id)

            allowed_methods = config_service.get_methods_for_country(
                country_code=country,
                user_has_wallet=user_has_wallet,
            )
            allowed_codes = {m.code for m in allowed_methods}

            # Cash is always allowed as fallback
            allowed_codes.add('cash')

            if payment_method not in allowed_codes:
                raise ValidationError(
                    message=f"Payment method '{payment_method}' is not available in your region. "
                            f"Available methods: {', '.join(sorted(allowed_codes))}",
                    field="payment_method",
                )
        except ValidationError:
            raise
        except Exception as exc:
            logger.warning(f"Payment method validation failed, allowing: {exc}")
            # Fail open - allow payment if validation fails
            pass

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

