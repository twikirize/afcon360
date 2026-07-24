# app/accommodation/services/payment_processors/base.py

from abc import ABC, abstractmethod
from decimal import Decimal
from typing import Tuple, Optional, Dict


class PaymentProcessor(ABC):
    """Base class for payment processors."""

    @abstractmethod
    def charge(
        self,
        user_id: int,
        amount: Decimal,
        currency: str,
        description: str,
        idempotency_key: str = None,
        metadata: Dict = None
    ) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Process a payment.

        Returns:
            (success, transaction_id, error_message)
        """
        pass

    @abstractmethod
    def refund(
        self,
        transaction_id: str,
        amount: Decimal,
        reason: str = None
    ) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Process a refund.

        Returns:
            (success, refund_id, error_message)
        """
        pass