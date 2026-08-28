"""
Payment State Machine - Manages payment lifecycle independently from booking.

Payment State Flow:
UNPAID → PENDING → PARTIALLY_PAID → PAID
                    ↘
                     FAILED
                     
PAID → REFUND_PENDING → REFUNDED
         ↘
        PARTIAL_REFUND

The payment state machine NEVER controls booking lifecycle.
It only describes what has actually happened financially.
"""

from enum import Enum
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional
from app.extensions import db
from app.accommodation.models.booking_payment import AccommodationBookingPayment
import logging

logger = logging.getLogger(__name__)


class PaymentState(str, Enum):
    """Payment lifecycle states - stored as string in DB"""
    UNPAID = "unpaid"
    PENDING = "pending"
    PROCESSING = "processing"
    PARTIALLY_PAID = "partially_paid"
    PAID = "paid"
    FAILED = "failed"
    REFUND_PENDING = "refund_pending"
    REFUNDED = "refunded"
    PARTIAL_REFUND = "partial_refund"
    CANCELLED = "cancelled"


class InvalidPaymentTransition(Exception):
    """Raised when a payment state transition is invalid"""
    pass


class PaymentStateMachine:
    """
    Manages payment state transitions with validation and history logging.
    
    This state machine is INDEPENDENT from the booking state machine.
    It only tracks financial reality, not booking approval or confirmation.
    """

    # Valid payment state transitions
    VALID_TRANSITIONS = {
        PaymentState.UNPAID: [
            PaymentState.PENDING,
            PaymentState.PARTIALLY_PAID,
            PaymentState.PAID,
            PaymentState.CANCELLED,
        ],
        PaymentState.PENDING: [
            PaymentState.PROCESSING,
            PaymentState.PARTIALLY_PAID,
            PaymentState.PAID,
            PaymentState.FAILED,
            PaymentState.CANCELLED,
            PaymentState.UNPAID,  # Payment cancelled before processing
        ],
        PaymentState.PROCESSING: [
            PaymentState.PARTIALLY_PAID,
            PaymentState.PAID,
            PaymentState.FAILED,
            PaymentState.CANCELLED,
        ],
        PaymentState.PARTIALLY_PAID: [
            PaymentState.PENDING,
            PaymentState.PAID,
            PaymentState.FAILED,
            PaymentState.REFUND_PENDING,
            PaymentState.CANCELLED,
        ],
        PaymentState.PAID: [
            PaymentState.REFUND_PENDING,
            PaymentState.PARTIAL_REFUND,
            PaymentState.REFUNDED,
        ],
        PaymentState.FAILED: [
            PaymentState.UNPAID,
            PaymentState.PENDING,
            PaymentState.CANCELLED,
        ],
        PaymentState.REFUND_PENDING: [
            PaymentState.REFUNDED,
            PaymentState.PARTIAL_REFUND,
            PaymentState.PAID,  # Refund cancelled
        ],
        PaymentState.REFUNDED: [],
        PaymentState.PARTIAL_REFUND: [
            PaymentState.REFUND_PENDING,
            PaymentState.REFUNDED,
        ],
        PaymentState.CANCELLED: [],
    }

    @classmethod
    def can_transition(
        cls,
        current_state: PaymentState,
        new_state: PaymentState,
        booking=None,
        amount: Optional[Decimal] = None,
    ) -> bool:
        """
        Check if payment can transition to new_state.
        
        Args:
            current_state: Current payment state
            new_state: Target payment state
            booking: Optional booking for policy-aware transitions
            amount: Optional payment amount for partial payment validation
            
        Returns:
            True if transition is valid
        """
        if new_state not in cls.VALID_TRANSITIONS.get(current_state, []):
            return False

        # Additional validation for specific transitions
        if new_state == PaymentState.PARTIALLY_PAID:
            # Must have a positive amount
            if amount is not None and amount <= 0:
                return False
            # Cannot exceed total amount (would need booking context)
            # This is validated at the service layer

        if new_state == PaymentState.PAID and current_state == PaymentState.PARTIALLY_PAID:
            # Full payment completing a partial payment
            # Amount validation happens at service layer
            pass

        if new_state in (PaymentState.REFUNDED, PaymentState.PARTIAL_REFUND):
            # Refunds require a prior PAID or PARTIALLY_PAID state
            # This is validated by the transition table above
            pass

        return True

    @classmethod
    def get_next_states(cls, current_state: PaymentState) -> list:
        """Return all valid next states from current_state"""
        return cls.VALID_TRANSITIONS.get(current_state, [])

    @classmethod
    def is_terminal(cls, state: PaymentState) -> bool:
        """Return True if state has no further transitions"""
        return len(cls.VALID_TRANSITIONS.get(state, [])) == 0

    @classmethod
    def is_success_state(cls, state: PaymentState) -> bool:
        """Return True if state represents successful payment completion"""
        return state in (PaymentState.PAID, PaymentState.PARTIALLY_PAID)

    @classmethod
    def is_failure_state(cls, state: PaymentState) -> bool:
        """Return True if state represents payment failure"""
        return state in (PaymentState.FAILED, PaymentState.CANCELLED)

    @classmethod
    def transition(
        cls,
        payment_event: AccommodationBookingPayment,
        new_state: PaymentState,
        changed_by_user_id: Optional[int] = None,
        reason: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        trigger: Optional[str] = None,
        metadata: Optional[dict] = None,
        amount: Optional[Decimal] = None,
    ):
        """
        Transition payment event to new_state with validation and history record.
        
        Args:
            payment_event: The AccommodationBookingPayment instance
            new_state: Target PaymentState enum
            changed_by_user_id: User performing the transition (None = system)
            reason: Optional reason string
            ip_address: Request IP for audit trail
            user_agent: Request user-agent for audit trail
            trigger: What triggered this transition
            metadata: Additional context as dict
            amount: Payment amount for this transition (for partial payments)
            
        Returns:
            The updated payment_event instance
            
        Raises:
            InvalidPaymentTransition: If the transition is not allowed
        """
        from app.accommodation.models.booking import BookingStatusHistory
        
        current_state = PaymentState(payment_event.payment_status)
        
        # Validate transition
        if not cls.can_transition(current_state, new_state, amount=amount):
            raise InvalidPaymentTransition(
                f"Cannot transition payment for booking {payment_event.booking_id} "
                f"from '{current_state.value}' to '{new_state.value}'"
            )

        old_state_string = payment_event.payment_status
        new_state_string = new_state.value

        # Record transition in history (extend BookingStatusHistory or create PaymentStatusHistory)
        # For now, we log to the existing booking status history with payment trigger
        # TODO: Create separate PaymentStatusHistory table in Phase 3
        if payment_event.booking_id is not None:
            history = BookingStatusHistory(
                booking_id=payment_event.booking_id,
                from_status=f"payment:{old_state_string}",
                to_status=f"payment:{new_state_string}",
                changed_by=changed_by_user_id,
                trigger=trigger or f"payment_{new_state_string}",
                change_metadata={
                    **(metadata or {}),
                    "reason": reason,
                    "ip_address": ip_address,
                    "user_agent": user_agent,
                    "payment_reference": payment_event.payment_reference,
                    "amount": str(amount) if amount else None,
                },
            )
            db.session.add(history)

        # Apply the transition
        payment_event.payment_status = new_state_string
        payment_event.updated_at = datetime.now(timezone.utc)
        
        if amount is not None:
            # Update amount_paid on the booking (will be synced by service)
            pass

        logger.info(
            f"Payment transition: booking={payment_event.booking_id} "
            f"ref={payment_event.payment_reference} | "
            f"{old_state_string} → {new_state_string} | "
            f"By: {changed_by_user_id or 'system'} | "
            f"Trigger: {trigger or 'none'} | "
            f"Reason: {reason or 'none'}"
        )

        return payment_event

    @classmethod
    def initiate_payment(
        cls,
        booking,
        amount: Decimal,
        payment_method: str,
        payment_gateway: Optional[str] = None,
        initiated_by_user_id: Optional[int] = None,
        idempotency_key: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> AccommodationBookingPayment:
        """
        Create a new payment event in PENDING state.
        
        This is the entry point for all payment flows.
        """
        payment_event = AccommodationBookingPayment(
            booking_id=booking.id,
            wallet_txn_id=None,
            payment_reference=AccommodationBookingPayment.generate_payment_reference(),
            payment_status=PaymentState.PENDING.value,
            payment_method=payment_method,
            payment_gateway=payment_gateway,
            idempotency_key=idempotency_key,
        )
        db.session.add(payment_event)
        db.session.flush()
        
        # Transition to PENDING with initiation metadata
        cls.transition(
            payment_event,
            PaymentState.PENDING,
            changed_by_user_id=initiated_by_user_id,
            reason="Payment initiated",
            trigger="payment_initiated",
            metadata={
                **(metadata or {}),
                "amount": str(amount),
                "payment_method": payment_method,
                "payment_gateway": payment_gateway,
            },
            amount=amount,
        )
        
        return payment_event

    @classmethod
    def mark_processing(
        cls,
        payment_event: AccommodationBookingPayment,
        gateway_transaction_id: Optional[str] = None,
        wallet_txn_id: Optional[str] = None,
    ):
        """Mark payment as being processed by gateway"""
        cls.transition(
            payment_event,
            PaymentState.PROCESSING,
            trigger="gateway_processing",
            metadata={
                "gateway_transaction_id": gateway_transaction_id,
                "wallet_txn_id": wallet_txn_id,
            },
        )
        if gateway_transaction_id:
            payment_event.gateway_transaction_id = gateway_transaction_id
        if wallet_txn_id:
            payment_event.wallet_txn_id = wallet_txn_id

    @classmethod
    def mark_paid(
        cls,
        payment_event: AccommodationBookingPayment,
        amount: Decimal,
        wallet_txn_id: Optional[str] = None,
        gateway_transaction_id: Optional[str] = None,
        changed_by_user_id: Optional[int] = None,
    ):
        """Mark payment as fully paid"""
        # Determine if this completes a partial payment or is a full payment
        current_state = PaymentState(payment_event.payment_status)
        new_state = PaymentState.PAID
        
        cls.transition(
            payment_event,
            new_state,
            changed_by_user_id=changed_by_user_id,
            reason="Payment completed",
            trigger="payment_completed",
            metadata={
                "amount": str(amount),
                "wallet_txn_id": wallet_txn_id,
                "gateway_transaction_id": gateway_transaction_id,
            },
            amount=amount,
        )
        payment_event.wallet_txn_id = wallet_txn_id
        if gateway_transaction_id:
            payment_event.gateway_transaction_id = gateway_transaction_id

    @classmethod
    def mark_partially_paid(
        cls,
        payment_event: AccommodationBookingPayment,
        amount: Decimal,
        wallet_txn_id: Optional[str] = None,
        gateway_transaction_id: Optional[str] = None,
        changed_by_user_id: Optional[int] = None,
    ):
        """Mark payment as partially paid"""
        cls.transition(
            payment_event,
            PaymentState.PARTIALLY_PAID,
            changed_by_user_id=changed_by_user_id,
            reason="Partial payment received",
            trigger="partial_payment",
            metadata={
                "amount": str(amount),
                "wallet_txn_id": wallet_txn_id,
                "gateway_transaction_id": gateway_transaction_id,
            },
            amount=amount,
        )
        payment_event.wallet_txn_id = wallet_txn_id
        if gateway_transaction_id:
            payment_event.gateway_transaction_id = gateway_transaction_id

    @classmethod
    def mark_failed(
        cls,
        payment_event: AccommodationBookingPayment,
        failure_reason: str,
        changed_by_user_id: Optional[int] = None,
    ):
        """Mark payment as failed"""
        cls.transition(
            payment_event,
            PaymentState.FAILED,
            changed_by_user_id=changed_by_user_id,
            reason=f"Payment failed: {failure_reason}",
            trigger="payment_failed",
            metadata={"failure_reason": failure_reason},
        )
        payment_event.failure_reason = failure_reason
        payment_event.retry_count = (payment_event.retry_count or 0) + 1

    @classmethod
    def initiate_refund(
        cls,
        payment_event: AccommodationBookingPayment,
        amount: Decimal,
        reason: str,
        changed_by_user_id: Optional[int] = None,
    ):
        """Initiate a refund (full or partial)"""
        current_state = PaymentState(payment_event.payment_status)
        new_state = PaymentState.REFUND_PENDING if amount >= Decimal(str(payment_event.booking.total_amount or 0)) else PaymentState.PARTIAL_REFUND
        
        cls.transition(
            payment_event,
            new_state,
            changed_by_user_id=changed_by_user_id,
            reason=f"Refund initiated: {reason}",
            trigger="refund_initiated",
            metadata={
                "refund_amount": str(amount),
                "refund_reason": reason,
            },
            amount=amount,
        )

    @classmethod
    def mark_refunded(
        cls,
        payment_event: AccommodationBookingPayment,
        amount: Decimal,
        wallet_txn_id: Optional[str] = None,
        changed_by_user_id: Optional[int] = None,
    ):
        """Mark refund as completed"""
        current_state = PaymentState(payment_event.payment_status)
        new_state = PaymentState.REFUNDED if current_state == PaymentState.REFUND_PENDING else PaymentState.PARTIAL_REFUND
        
        cls.transition(
            payment_event,
            new_state,
            changed_by_user_id=changed_by_user_id,
            reason="Refund completed",
            trigger="refund_completed",
            metadata={
                "refund_amount": str(amount),
                "wallet_txn_id": wallet_txn_id,
            },
            amount=amount,
        )
        if wallet_txn_id:
            payment_event.wallet_txn_id = wallet_txn_id