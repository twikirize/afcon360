from decimal import Decimal
from typing import Optional, Tuple, Dict, Any
from app.accommodation.services.payment_processors.base import PaymentProcessor


class InvoiceProcessor(PaymentProcessor):
    """Process payments via invoice (no upfront charge)."""

    def charge(
        self,
        user_id: int,
        amount: Decimal,
        currency: str,
        description: str,
        idempotency_key: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Tuple[bool, Optional[str], Optional[str]]:
        # Invoice payments are not charged upfront
        # Return success with a placeholder transaction ID
        return True, f"inv_{idempotency_key[:16]}", None

    def refund(
        self,
        transaction_id: str,
        amount: Decimal,
        reason: str,
    ) -> Tuple[bool, Optional[str]]:
        # Invoice refunds are handled separately
        return True, None
