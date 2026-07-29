import os
import logging
from decimal import Decimal
from typing import Optional, Tuple, Dict, Any

from app.accommodation.services.payment_processors.base import PaymentProcessor
from app.accommodation.services.marketplace_service import MarketplaceService
from app.wallet.services.wallet_service import WalletService

logger = logging.getLogger(__name__)
_ENV = os.environ.get("APP_ENV", os.environ.get("FLASK_ENV", "development"))


class MockGatewayProcessor(PaymentProcessor):
    """
    Simulates ONLY the external gateway's approve/decline decision.
    All real money movement runs through the real Financial Engine
    (WalletService -> ledger -> MarketplaceService commission split),
    identically to WalletProcessor.

    Removal when a real gateway goes live for this environment:
      1. Delete this file.
      2. Remove the import + registry entry in
         payment_processors/__init__.py and routes.py's processor_map.
      3. Disable (do not delete) the 'mock_gateway' PaymentMethodConfig row.
    Historical test transactions remain in the ledger permanently
    (Constitutional Law 2) but are tagged payment_provider='mock_gateway'
    so reconciliation/reporting can filter them out permanently.
    """

    DECLINE_CENTS = 13

    def charge(
        self,
        user_id: int,
        amount: Decimal,
        currency: str,
        description: str,
        idempotency_key: str = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Tuple[bool, Optional[str], Optional[str]]:
        if _ENV == "production":
            return False, None, "mock_gateway is disabled in production"

        if int((amount * 100) % 100) == self.DECLINE_CENTS:
            return False, None, "simulated_decline (mock gateway test amount, e.g. x.13)"

        from app.accommodation.models.booking import AccommodationBooking
        booking = AccommodationBooking.query.filter_by(
            idempotency_key=idempotency_key
        ).first()
        if not booking:
            return False, None, "Booking not found for idempotency key"

        from app.wallet.routes import get_or_create_account
        account = get_or_create_account(user_id, currency)

        wallet = WalletService()
        if account.balance < amount:
            deposit_amount = amount - account.balance + Decimal("10.00")
            wallet.deposit(
                account_id=str(account.id),
                amount=deposit_amount,
                currency=currency,
                client_request_id=f"mock_topup_{idempotency_key}",
                metadata={"test_mode": True},
                payment_provider="mock_gateway",
            )

        return MarketplaceService.charge_guest(
            booking=booking,
            total_amount=amount,
            currency=currency,
            idempotency_key=idempotency_key,
        )

    def refund(
        self,
        transaction_id: str,
        amount: Decimal,
        reason: str = None,
    ) -> Tuple[bool, Optional[str]]:
        from app.accommodation.models.commission import BookingCommission
        commission = BookingCommission.query.filter_by(
            host_payout_transaction_id=transaction_id
        ).first()
        if not commission:
            return False, "Commission record not found for transaction"
        return MarketplaceService.refund_guest(commission.booking_id, amount)