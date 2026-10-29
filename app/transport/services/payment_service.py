#app/transport/services/payment_service.py

"""
AFCON360 Transport Module - Payment Service
Handles payment processing and transactions
"""

from datetime import datetime, timezone
from decimal import Decimal
from typing import Dict, List, Optional, Any
import logging
from flask import current_app
from sqlalchemy.exc import SQLAlchemyError

from app.extensions import db
from app.transport.models import Booking, BookingPayment, BookingStatus, PaymentStatus
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

            # Settlement is an end-of-trip event, never a booking-confirmation
            # event. Do not debit or capture while the ride is merely requested,
            # assigned, en route, or in progress.
            if booking.status != BookingStatus.COMPLETED:
                raise ValidationError(
                    message="Payment can be settled only after the trip is completed"
                )

            # A retry of a captured payment is a read-only success; never debit
            # the same trip twice. Repair a missing payment-index row for a
            # legacy booking without executing the money movement again.
            if booking.payment_status == PaymentStatus.CAPTURED:
                captured_amount = Decimal(str(
                    booking.final_price or booking.total_amount or 0
                ))
                payment_record = PaymentService._get_or_create_payment_record(
                    booking, captured_amount, str(booking.payment_method or ""),
                    booking.payment_captured_at or datetime.now(timezone.utc),
                )
                payment_record.payment_status = PaymentStatus.CAPTURED
                payment_record.captured_at = (
                    booking.payment_captured_at or payment_record.captured_at
                    or datetime.now(timezone.utc)
                )
                payment_record.wallet_txn_id = (
                    booking.wallet_transaction_id or payment_record.wallet_txn_id
                )
                db.session.commit()
                return {
                    "success": True,
                    "message": "Payment is already settled",
                    "data": {
                        "booking_reference": booking.booking_reference,
                        "amount": float(captured_amount),
                        "payment_method": booking.payment_method,
                        "payment_status": "captured",
                        "payment_reference": payment_record.payment_reference,
                        "booking_status": str(getattr(booking.status, "value", booking.status)),
                        "idempotent_replay": True,
                    },
                }

            # The method is selected and stored when the rider commits the
            # request. A payment call cannot silently switch it at trip end.
            stored_method = str(booking.payment_method or "").strip().lower()
            requested_method = str(
                sanitized_data.get("payment_method") or stored_method
            ).strip().lower()
            if not stored_method:
                raise ValidationError(message="This trip has no recorded payment method")
            if requested_method != stored_method:
                raise ValidationError(
                    message="Payment method must match the method selected when the ride was requested",
                    field="payment_method",
                )
            payment_method = stored_method
            # The previously confirmed Wallet invoice is the payment contract.\n
            final_price = PaymentService._calculate_final_price(booking)
            now = datetime.now(timezone.utc)
            payment_record = PaymentService._get_or_create_payment_record(
                booking, final_price, payment_method, now
            )
            # Keep one stable transport payment reference for the life of this
            # booking. Provider retries must not invent a new payment identity.
            payment_ref = payment_record.payment_reference

            # Reuse the invoice created at ride confirmation. Legacy bookings
            # without one receive an idempotent Wallet invoice here before any
            # settlement attempt.
            try:
                invoice = PaymentService._ensure_wallet_invoice_for_booking(
                    booking, payment_record, final_price, payment_method
                )
            except Exception as exc:
                from app.wallet.services.marketplace_invoice_service import MarketplaceInvoiceError
                if isinstance(exc, MarketplaceInvoiceError):
                    raise ValidationError(message=exc.message, field="payment_method") from exc
                raise

            wallet_txn_id = None
            payment_processed = False
            if payment_method == "cash":
                try:
                    settlement = MarketplaceInvoiceService.settle_after_completion(
                        invoice_id=invoice.id,
                        payer_user_id=booking.user_id,
                        service_code="transport",
                        service_reference=booking.booking_reference,
                        amount=final_price,
                        currency=str(getattr(booking.currency, "value", booking.currency)),
                        request_id=request_id,
                    )
                except MarketplaceInvoiceError as exc:
                    raise ValidationError(message=exc.message, field="payment_method") from exc

                # A driver's cash receipt is still required. The invoice is due,
                # not paid, and no transport code asserts receipt of cash.
                payment_record.amount = final_price
                payment_record.currency = booking.currency
                payment_record.wallet_invoice_id = invoice.id
                payment_record.payment_method = payment_method
                payment_record.payment_status = PaymentStatus.PENDING
                payment_record.captured_at = None
                booking.final_price = final_price
                booking.payment_status = PaymentStatus.PENDING
                booking.payment_gateway_reference = None
                booking.payment_captured_at = None
                booking_meta = dict(booking.booking_metadata or {})
                booking_meta["wallet_invoice_id"] = str(invoice.id)
                booking_meta["wallet_invoice_status"] = settlement["status"]
                booking.booking_metadata = booking_meta
                db.session.add(booking)
                db.session.commit()
                return {
                    "success": True,
                    "message": "Trip completed; cash receipt is still awaiting confirmation",
                    "data": {
                        "booking_reference": booking.booking_reference,
                        "amount": float(final_price),
                        "currency": str(getattr(booking.currency, "value", booking.currency)),
                        "payment_method": payment_method,
                        "payment_status": "pending",
                        "payment_reference": payment_record.payment_reference,
                        "wallet_invoice_id": str(invoice.id),
                        "booking_status": str(getattr(booking.status, "value", booking.status)),
                        "requires_cash_receipt_confirmation": True,
                    },
                }
            elif payment_method == "wallet":
                try:
                    settlement = MarketplaceInvoiceService.settle_after_completion(
                        invoice_id=invoice.id,
                        payer_user_id=booking.user_id,
                        service_code="transport",
                        service_reference=booking.booking_reference,
                        amount=final_price,
                        currency=str(getattr(booking.currency, "value", booking.currency)),
                        request_id=request_id,
                    )
                except MarketplaceInvoiceError as exc:
                    if exc.code == "insufficient_funds":
                        raise ValidationError(message=exc.message, field="payment_method") from exc
                    raise ServiceUnavailableError(message=exc.message) from exc

                if settlement.get("status") != "paid" or not settlement.get("transaction_id"):
                    raise ServiceUnavailableError(
                        message="Wallet has not confirmed completed settlement; this trip remains unpaid."
                    )
                wallet_txn_id = settlement["transaction_id"]
                payment_status = "captured"
                payment_processed = True

                # Wallet's atomic transaction is committed independently. Re-lock
                # Transport rows and only refresh its status cache afterwards.
                locked_booking = Booking.query.filter_by(
                    id=booking_id, is_deleted=False
                ).with_for_update().first()
                if locked_booking is None:
                    raise NotFoundError(
                        "Booking not found",
                        resource_type="booking",
                        resource_id=booking_id,
                    )
                booking = locked_booking
                if booking.payment_status == PaymentStatus.CAPTURED:
                    captured_amount = Decimal(str(
                        booking.final_price or booking.total_amount or final_price
                    ))
                    payment_record = PaymentService._get_or_create_payment_record(
                        booking,
                        captured_amount,
                        payment_method,
                        booking.payment_captured_at or now,
                        payment_reference=booking.payment_gateway_reference,
                    )
                    payment_record.payment_status = PaymentStatus.CAPTURED
                    payment_record.wallet_invoice_id = invoice.id
                    payment_record.wallet_txn_id = booking.wallet_transaction_id or wallet_txn_id
                    payment_record.captured_at = (
                        booking.payment_captured_at or payment_record.captured_at or now
                    )
                    db.session.commit()
                    return {
                        "success": True,
                        "message": "Payment is already settled",
                        "data": {
                            "booking_reference": booking.booking_reference,
                            "amount": float(captured_amount),
                            "payment_method": booking.payment_method,
                            "payment_status": "captured",
                            "payment_reference": payment_record.payment_reference,
                            "wallet_invoice_id": str(invoice.id),
                            "wallet_txn_id": str(payment_record.wallet_txn_id),
                            "booking_status": str(getattr(booking.status, "value", booking.status)),
                            "idempotent_replay": True,
                        },
                    }

                payment_record = PaymentService._get_or_create_payment_record(
                    booking, final_price, payment_method, now,
                    payment_reference=payment_ref,
                )
                payment_record.wallet_invoice_id = invoice.id
                payment_ref = payment_record.payment_reference
                booking_meta = dict(booking.booking_metadata or {})
                booking_meta["wallet_invoice_id"] = str(invoice.id)
                booking_meta["wallet_invoice_status"] = "paid"
                booking.booking_metadata = booking_meta
            else:
                # MarketplaceInvoiceService rejects methods without a real
                # Wallet-owned collection and verification implementation.
                raise ServiceUnavailableError(
                    message="Wallet has not enabled this payment method for marketplace settlement."
                )

            booking.final_price = final_price
            booking.payment_status = (
                PaymentStatus.CAPTURED if payment_processed else PaymentStatus.PENDING
            )
            booking.payment_gateway_reference = payment_ref if payment_processed else None
            booking.payment_captured_at = now if payment_processed else None
            booking.wallet_transaction_id = wallet_txn_id or booking.wallet_transaction_id

            payment_record.amount = final_price
            payment_record.payment_method = payment_method
            payment_record.payment_status = (
                PaymentStatus.CAPTURED if payment_processed else PaymentStatus.PENDING
            )
            payment_record.captured_at = now if payment_processed else None
            if wallet_txn_id:
                payment_record.wallet_txn_id = str(wallet_txn_id)
                payment_record.payment_gateway = "internal_wallet"
                payment_record.gateway_transaction_id = str(wallet_txn_id)
            payment_record.payment_method_details = {
                **(payment_record.payment_method_details or {}),
                "timing": "pay_on_completion",
                "settlement_request_id": request_id,
            }
            # Audit the ledger change in the same database transaction as
            # the booking/payment-index update. This preserves a durable admin
            # trail for captured wallet payments and any pending provider result.
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
                },
                db_session=db.session,
            )

            # Do not rewrite Booking.status when payment succeeds. The trip
            # stays completed; the booking summary, payment ledger and audit row
            # commit together. Wallet retries reuse the stable booking key.
            db.session.commit()

            # Observability must not turn a committed payment into a reported
            # failure. The financial state and audit record are authoritative.
            try:
                record_metric(
                    'payment_processed',
                    tags={
                        'payment_method': payment_method,
                        'payment_status': payment_status,
                        'amount_range': PaymentService._get_amount_range(final_price)
                    },
                    value=1
                )
            except Exception:
                current_app.logger.warning(
                    "Payment metrics emission failed for booking %s",
                    booking_id,
                    exc_info=True,
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

        except (ValidationError, NotFoundError, ServiceUnavailableError) as e:
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
    def _ensure_wallet_invoice_for_booking(
        booking: Booking,
        payment_record: BookingPayment,
        amount: Decimal,
        payment_method: str,
    ):
        """Resolve/create the Wallet invoice and persist only its transport reference."""
        from app.wallet.services.marketplace_invoice_service import (
            MarketplaceInvoiceService,
        )

        metadata = dict(booking.booking_metadata or {})
        raw_invoice_id = payment_record.wallet_invoice_id or metadata.get("wallet_invoice_id")
        key = "transport-booking:%s" % booking.booking_reference
        if raw_invoice_id:
            invoice = MarketplaceInvoiceService.get_invoice(raw_invoice_id)
            key = invoice.idempotency_key

        invoice = MarketplaceInvoiceService.create_invoice(
            idempotency_key=key,
            service_code="transport",
            service_reference=booking.booking_reference,
            payer_user_id=booking.user_id,
            amount=amount,
            currency=str(getattr(booking.currency, "value", booking.currency)),
            payment_method=payment_method,
            settlement_timing="pay_on_completion",
            metadata={
                "booking_reference": booking.booking_reference,
                "booking_id": str(booking.id),
            },
            commit=True,
        )
        payment_record.wallet_invoice_id = invoice.id
        payment_details = dict(payment_record.payment_method_details or {})
        payment_details["wallet_invoice_id"] = str(invoice.id)
        payment_record.payment_method_details = payment_details
        metadata["wallet_invoice_id"] = str(invoice.id)
        metadata["wallet_invoice_status"] = invoice.status
        booking.booking_metadata = metadata
        db.session.add(payment_record)
        db.session.add(booking)
        return invoice

    @staticmethod
    def _get_or_create_payment_record(
        booking: Booking,
        amount: Decimal,
        payment_method: str,
        now: Optional[datetime] = None,
        payment_reference: Optional[str] = None,
    ) -> BookingPayment:
        """Return the authoritative payment row for a booking, creating once."""
        timestamp = now or datetime.now(timezone.utc)
        record = (
            BookingPayment.query.filter_by(booking_id=booking.id)
            .order_by(BookingPayment.created_at.desc(), BookingPayment.id.desc())
            .with_for_update()
            .first()
        )
        if record is not None:
            return record
        record = BookingPayment(
            booking_id=booking.id,
            payment_reference=payment_reference or "",
            amount=amount,
            currency=booking.currency,
            payment_method=payment_method,
            payment_method_details={"timing": "pay_on_completion"},
            payment_status=PaymentStatus.PENDING,
            initiated_at=timestamp,
        )
        if not payment_reference:
            record.generate_payment_reference()
        db.session.add(record)
        db.session.flush()
        return record

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

        # No transport card/mobile-money capture is implemented in this
        # service yet. Fail closed rather than fabricating a successful payment.
        raise ServiceUnavailableError(
            message=(
                "The selected payment provider is not yet integrated for "
                "transport settlement. The trip remains completed and unpaid."
            )
        )

    @staticmethod
    def _generate_payment_reference(booking: Optional[Booking] = None) -> str:
        """Stable payment reference scoped to one trip."""
        if booking is not None and booking.booking_reference:
            return ("TRP-" + str(booking.booking_reference))[:100]
        raise ValidationError("A booking reference is required for a payment reference")

    @staticmethod
    def _validate_payment_method(booking: Booking, payment_method: str) -> None:
        """Compatibility adapter to Wallet's market-collection eligibility."""
        from app.wallet.services.marketplace_invoice_service import (
            MarketplaceInvoiceService,
        )
        methods = MarketplaceInvoiceService.list_available_methods(
            payer_user_id=booking.user_id,
            currency=str(getattr(booking.currency, "value", booking.currency)),
            amount=getattr(booking, "final_price", None) or getattr(booking, "total_amount", None),
            settlement_timing="pay_on_completion",
        )
        allowed_codes = {
            str(method.get("code") or "").strip().lower() for method in methods
        }
        if str(payment_method or "").strip().lower() not in allowed_codes:
            raise ValidationError(
                message="This payment method is not available for Wallet marketplace settlement.",
                field="payment_method",
            )

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

