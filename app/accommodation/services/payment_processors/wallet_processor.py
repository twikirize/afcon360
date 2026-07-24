from decimal import Decimal
from typing import Optional, Tuple, Dict, Any
from app.accommodation.services.payment_processors.base import PaymentProcessor
from app.accommodation.services.marketplace_service import MarketplaceService


class WalletProcessor(PaymentProcessor):
    """Process payments via the internal wallet system."""

    def charge(
        self,
        user_id: int,
        amount: Decimal,
        currency: str,
        description: str,
        idempotency_key: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Charge guest wallet via MarketplaceService.
        Looks up the booking by idempotency_key and delegates to
        MarketplaceService.charge_guest() which uses WalletService.transfer()
        with platform_fee for commission.
        """
        from app.accommodation.models.booking import AccommodationBooking

        booking = AccommodationBooking.query.filter_by(
            idempotency_key=idempotency_key
        ).first()
        if not booking:
            return False, None, "Booking not found for idempotency key"

        success, txn_id, error = MarketplaceService.charge_guest(
            booking=booking,
            total_amount=amount,
            currency=currency,
            idempotency_key=idempotency_key,
        )
        return success, txn_id, error

    def refund(
        self,
        transaction_id: str,
        amount: Decimal,
        reason: str,
    ) -> Tuple[bool, Optional[str]]:
        """
        Refund via MarketplaceService.
        Transfers from platform escrow back to guest.
        """
        from app.accommodation.models.commission import BookingCommission
        commission = BookingCommission.query.filter_by(
            host_payout_transaction_id=transaction_id
        ).first()
        if not commission:
            return False, "Commission record not found for transaction"

        success, error = MarketplaceService.refund_guest(commission.booking_id, amount)
        return success, error
