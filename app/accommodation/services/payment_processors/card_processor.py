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
        raise NotImplementedError(
            "CardProcessor is not yet implemented. "
            "Use 'wallet', 'mobile_money', 'mock_gateway', or 'invoice' as payment method."
        )

    def refund(
        self,
        transaction_id: str,
        amount: Decimal,
        reason: str,
    ) -> Tuple[bool, Optional[str]]:
        raise NotImplementedError("CardProcessor is not yet implemented.")
