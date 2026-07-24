from decimal import Decimal
from typing import Optional, Tuple, Dict, Any
from app.accommodation.services.payment_processors.base import PaymentProcessor


class MobileMoneyProcessor(PaymentProcessor):
    """Process payments via mobile money (M-Pesa, Airtel Money, etc.)."""

    def charge(
        self,
        user_id: int,
        amount: Decimal,
        currency: str,
        description: str,
        idempotency_key: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Tuple[bool, Optional[str], Optional[str]]:
        # TODO: Integrate with mobile money API
        # For now, return a placeholder success
        return True, f"mm_{idempotency_key[:16]}", None

    def refund(
        self,
        transaction_id: str,
        amount: Decimal,
        reason: str,
    ) -> Tuple[bool, Optional[str]]:
        # TODO: Integrate with mobile money API
        return True, None
