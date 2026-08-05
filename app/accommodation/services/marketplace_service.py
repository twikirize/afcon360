"""
Marketplace integration service for accommodation bookings.

Integrates with the real wallet module (double-entry ledger) to handle:
- Guest payments → platform escrow
- Platform commission recording
- Host payouts after check-in
- Refunds on cancellation
"""

from decimal import Decimal
from typing import Optional, Tuple, Dict, Any
from datetime import datetime, timezone
from uuid import uuid4

from flask import current_app
from sqlalchemy.exc import OperationalError

from app.extensions import db
from app.wallet.services.wallet_service import WalletService
from app.wallet.services.commission_service import CommissionService
from app.wallet.models.ledger import AccountModel, AccountOwnerType
from app.wallet.repositories.account_repository import AccountRepository
from app.accommodation.models.booking import AccommodationBooking
from app.accommodation.models.commission import BookingCommission
import logging

logger = logging.getLogger(__name__)


class MarketplaceService:
    """
    Thin integration layer between accommodation bookings and the wallet module.
    Does NOT duplicate wallet functionality — delegates to WalletService.transfer()
    and CommissionService.record_commission().
    """

    # Default platform commission rate (overridable per booking)
    DEFAULT_COMMISSION_PCT = Decimal('10.0')

    @staticmethod
    def _get_platform_account_id(currency: str = 'USD') -> str:
        """
        Get or create the platform escrow account.
        Uses a configurable platform org ID from app config.
        """
        platform_org_id = current_app.config.get('PLATFORM_ORG_ID')
        if not platform_org_id:
            raise RuntimeError(
                "PLATFORM_ORG_ID not configured. "
                "Set it in config to the internal BIGINT ID of the platform organisation."
            )

        repo = AccountRepository(db.session)
        account = repo.get_or_create(int(platform_org_id), currency)
        if not account:
            raise RuntimeError(
                f"Platform escrow account not found for org {platform_org_id}. "
                "Please create it during system setup."
            )
        return str(account.id)

    @staticmethod
    def _get_account_for_user(user_id: int, currency: str = 'USD') -> str:
        """Get wallet account for a user. Returns error if not found."""
        repo = AccountRepository(db.session)
        account = repo.get_or_create(user_id, currency)
        if not account:
            raise RuntimeError(
                f"Wallet account not found for user {user_id}. "
                "Please create a wallet first."
            )
        return str(account.id)

    @staticmethod
    def charge_guest(
        booking: AccommodationBooking,
        total_amount: Decimal,
        currency: str,
        idempotency_key: str
    ) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Charge guest and hold funds in platform escrow.
        Uses WalletService.transfer() with platform_fee to atomically:
        - Debit guest
        - Credit platform escrow
        - Record platform commission

        Returns:
            (success, transaction_id, error_message)
        """
        try:
            guest_account_id = MarketplaceService._get_account_for_user(
                booking.booked_by_user_id, currency
            )
            platform_account_id = MarketplaceService._get_platform_account_id(currency)

            commission_pct = Decimal(str(
                current_app.config.get('PLATFORM_COMMISSION_PCT', MarketplaceService.DEFAULT_COMMISSION_PCT)
            ))
            commission_amount = (total_amount * commission_pct / Decimal('100')).quantize(Decimal('0.01'))
            host_payout = total_amount - commission_amount

            wallet = WalletService()
            result = wallet.transfer(
                from_account_id=guest_account_id,
                to_account_id=platform_account_id,
                amount=total_amount,
                currency=currency,
                client_request_id=f"booking_{booking.id}_charge_{idempotency_key}",
                note=f"Booking payment: {booking.booking_reference}",
                metadata={
                    'booking_id': str(booking.id),
                    'booking_reference': booking.booking_reference,
                    'property_id': str(booking.property_id),
                    'guest_user_id': str(booking.booked_by_user_id),
                    'host_user_id': str(booking.host_user_id),
                    'commission_pct': str(commission_pct),
                    'commission_amount': str(commission_amount),
                    'host_payout': str(host_payout),
                },
                platform_fee=commission_amount,
                fee_currency=currency,
            )

            txn_id = result.get('transaction_id')
            booking.wallet_txn_id = txn_id
            booking.paid_at = datetime.now(timezone.utc)
            booking.payment_status = 'paid'
            booking.amount_paid = total_amount

            commission = BookingCommission(
                booking_id=booking.id,
                total_amount=total_amount,
                commission_amount=commission_amount,
                host_payout=host_payout,
                platform_fee_pct=commission_pct,
                status='held',
                extra_data={
                    'booking_reference': booking.booking_reference,
                    'property_id': str(booking.property_id),
                    'guest_user_id': str(booking.booked_by_user_id),
                    'host_user_id': str(booking.host_user_id),
                    'commission_pct': str(commission_pct),
                    'commission_amount': str(commission_amount),
                    'host_payout': str(host_payout),
                }
            )
            db.session.add(commission)
            db.session.commit()

            logger.info(
                f"Payment held in escrow: {booking.booking_reference} | "
                f"Total: {total_amount} {currency} | Commission: {commission_amount} | "
                f"Host payout: {host_payout}"
            )

            return True, txn_id, None

        except Exception as e:
            db.session.rollback()
            logger.error(f"Payment failed for booking {booking.booking_reference}: {e}", exc_info=True)
            return False, None, str(e)

    @staticmethod
    def release_host_payout(booking_id: int) -> Tuple[bool, Optional[str]]:
        """
        Release payout to host after check-in.
        Transfers host_payout from platform escrow to host's wallet.

        Returns:
            (success, error_message)
        """
        try:
            booking = db.session.get(AccommodationBooking, booking_id)
            if not booking:
                return False, "Booking not found"

            commission = BookingCommission.query.filter_by(booking_id=booking_id).first()
            if not commission:
                return False, "Commission record not found"

            if commission.status != 'held':
                return False, f"Commission already {commission.status}"

            host_account_id = MarketplaceService._get_account_for_user(booking.host_user_id, booking.currency)
            platform_account_id = MarketplaceService._get_platform_account_id(booking.currency)

            wallet = WalletService()
            result = wallet.transfer(
                from_account_id=platform_account_id,
                to_account_id=host_account_id,
                amount=commission.host_payout,
                currency=booking.currency,
                client_request_id=f"booking_{booking_id}_payout_{uuid4().hex[:12]}",
                note=f"Host payout: {booking.booking_reference}",
                metadata={
                    'booking_id': str(booking_id),
                    'booking_reference': booking.booking_reference,
                    'commission_id': str(commission.id),
                },
            )

            txn_id = result.get('transaction_id')
            commission.status = 'released'
            commission.released_at = datetime.now(timezone.utc)
            commission.host_payout_transaction_id = txn_id
            db.session.commit()

            logger.info(
                f"Host payout released: {booking.booking_reference} | "
                f"Amount: {commission.host_payout} {booking.currency} | "
                f"Host: {booking.host_user_id}"
            )

            return True, None

        except Exception as e:
            db.session.rollback()
            logger.error(f"Payout failed for booking {booking_id}: {e}", exc_info=True)
            return False, str(e)

    @staticmethod
    def refund_guest(booking_id: int, refund_amount: Decimal) -> Tuple[bool, Optional[str]]:
        """
        Refund guest from platform escrow.
        Used when booking is cancelled and guest is eligible for refund.

        Returns:
            (success, error_message)
        """
        try:
            booking = db.session.get(AccommodationBooking, booking_id)
            if not booking:
                return False, "Booking not found"

            commission = BookingCommission.query.filter_by(booking_id=booking_id).first()
            if not commission:
                return False, "Commission record not found"

            if commission.status == 'refunded':
                return False, "Already refunded"

            guest_account_id = MarketplaceService._get_account_for_user(booking.booked_by_user_id, booking.currency)
            platform_account_id = MarketplaceService._get_platform_account_id(booking.currency)

            wallet = WalletService()
            result = wallet.transfer(
                from_account_id=platform_account_id,
                to_account_id=guest_account_id,
                amount=refund_amount,
                currency=booking.currency,
                client_request_id=f"booking_{booking_id}_refund_{uuid4().hex[:12]}",
                note=f"Refund: {booking.booking_reference}",
                metadata={
                    'booking_id': str(booking_id),
                    'booking_reference': booking.booking_reference,
                    'refund_amount': str(refund_amount),
                },
            )

            txn_id = result.get('transaction_id')
            commission.status = 'refunded'
            commission.refund_amount = refund_amount
            commission.refunded_at = datetime.now(timezone.utc)
            booking.refund_amount = refund_amount
            booking.refunded_at = datetime.now(timezone.utc)
            booking.payment_status = 'refunded'
            db.session.commit()

            logger.info(
                f"Refund processed: {booking.booking_reference} | "
                f"Amount: {refund_amount} {booking.currency}"
            )

            return True, None

        except Exception as e:
            db.session.rollback()
            logger.error(f"Refund failed for booking {booking_id}: {e}", exc_info=True)
            return False, str(e)

    @staticmethod
    def get_host_earnings(host_user_id: int) -> Dict[str, Any]:
        """Get earnings summary for a host."""
        released = db.session.query(
            db.func.sum(BookingCommission.host_payout)
        ).join(
            AccommodationBooking, BookingCommission.booking_id == AccommodationBooking.id
        ).filter(
            AccommodationBooking.host_user_id == host_user_id,
            BookingCommission.status == 'released'
        ).scalar() or Decimal('0')

        held = db.session.query(
            db.func.sum(BookingCommission.host_payout)
        ).join(
            AccommodationBooking, BookingCommission.booking_id == AccommodationBooking.id
        ).filter(
            AccommodationBooking.host_user_id == host_user_id,
            BookingCommission.status == 'held'
        ).scalar() or Decimal('0')

        return {
            'released': float(released),
            'held': float(held),
            'total': float(released + held),
            'currency': 'USD',
        }

    @staticmethod
    def get_host_payout_history(host_user_id: int, limit: int = 20) -> list:
        """Get recent payout history for a host."""
        return db.session.query(
            BookingCommission,
            AccommodationBooking
        ).join(
            AccommodationBooking, BookingCommission.booking_id == AccommodationBooking.id
        ).filter(
            AccommodationBooking.host_user_id == host_user_id,
            BookingCommission.status.in_(['released', 'refunded'])
        ).order_by(BookingCommission.released_at.desc()).limit(limit).all()

