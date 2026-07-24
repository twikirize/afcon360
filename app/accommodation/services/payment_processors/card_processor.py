from decimal import Decimal
from typing import Optional, Tuple, Dict, Any
from app.accommodation.services.payment_processors.base import PaymentProcessor


class CardProcessor(PaymentProcessor):
    """Process payments via credit/debit card (Stripe, etc.)."""

    def charge(
        self,
        user_id: int,
        amount: Decimal,
        currency: str,
        description: str,
        idempotency_key: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Tuple[bool, Optional[str], Optional[str]]:
        # TODO: Integrate with card payment gateway
        # For now, return a placeholder success
        return True, f"card_{idempotency_key[:16]}", None

    def refund(
        self,
        transaction_id: str,
        amount: Decimal,
        reason: str,
    ) -> Tuple[bool, Optional[str]]:
        # TODO: Integrate with card payment gateway
        return True, None
