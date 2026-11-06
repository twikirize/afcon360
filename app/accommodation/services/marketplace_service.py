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

from flask import current_app
from flask_login import current_user
from sqlalchemy.exc import OperationalError

from app.extensions import db
from app.wallet.services.wallet_service import WalletService
from app.wallet.services.commission_service import CommissionService
from app.wallet.models.ledger import AccountModel, AccountOwnerType
from app.wallet.repositories.account_repository import AccountRepository
from app.wallet.repositories.transaction_repository import TransactionRepository
from app.accommodation.models.booking import AccommodationBooking, AccommodationBookingStatus
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
        Release escrow only after the authenticated property manager who
        confirmed check-in is verified again at the financial boundary.
        Wallet executes the transfer; the human check-in actor authorizes it.
        """
        try:
            booking = db.session.get(AccommodationBooking, booking_id)
            if not booking:
                return False, "Booking not found"

            actor = current_user
            if not actor or not actor.is_authenticated:
                return False, "An authenticated host approval is required"

            from app.accommodation.services.identity_service import AccommodationIdentityService
            prop = booking.accommodation_property
            if not AccommodationIdentityService.can_manage_property(
                actor,
                property_owner_user_id=prop.owner_user_id if prop else None,
                property_owner_org_id=prop.owner_org_id if prop else None,
            ):
                return False, "You are not authorised to approve this host payout"

            if not (
                booking.is_checked_in
                and booking.status == AccommodationBookingStatus.CHECKED_IN.value
                and booking.checked_in_by == actor.id
            ):
                return False, "A host must confirm this booking's check-in before payout"

            commission = BookingCommission.query.filter_by(booking_id=booking_id).first()
            if not commission:
                return False, "Commission record not found"

            if commission.status != 'held':
                return False, f"Commission already {commission.status}"

            approval_at = datetime.now(timezone.utc)
            host_account_id = MarketplaceService._get_account_for_user(booking.host_user_id, booking.currency)
            platform_account_id = MarketplaceService._get_platform_account_id(booking.currency)

            wallet = WalletService()
            result = wallet.transfer(
                from_account_id=platform_account_id,
                to_account_id=host_account_id,
                amount=commission.host_payout,
                currency=booking.currency,
                client_request_id=f"booking_{booking_id}_payout",
                note=f"Host payout: {booking.booking_reference}",
                metadata={
                    'booking_id': str(booking_id),
                    'booking_reference': booking.booking_reference,
                    'commission_id': str(commission.id),
                    'approved_by_user_id': actor.id,
                    'approval_source': 'host_check_in',
                    'approval_reason': 'Host confirmed guest check-in',
                    'approved_at': approval_at.isoformat(),
                },
                # System executes the escrow movement after the human approval
                # above; the platform escrow account does not enter a user PIN.
                system_initiated=True,
            )

            txn_id = result.get('transaction_id')
            commission.status = 'released'
            commission.released_at = approval_at
            commission.released_by = actor.id
            commission.host_payout_transaction_id = txn_id
            db.session.commit()

            logger.info(
                f"Host payout released: {booking.booking_reference} | "
                f"Amount: {commission.host_payout} {booking.currency} | "
                f"Approver: {actor.id}"
            )

            return True, None

        except Exception as e:
            db.session.rollback()
            logger.error(f"Payout failed for booking {booking_id}: {e}", exc_info=True)
            return False, str(e)

    @staticmethod
    def refund_guest(
        booking_id: int,
        refund_amount: Decimal,
        approval_reason: Optional[str] = None,
    ) -> Tuple[bool, Optional[str]]:
        """
        Execute a wallet refund only after an authenticated human approval.

        A property manager can explicitly approve a manual refund. A human who
        cancelled the booking can approve only the exact refund amount persisted
        by the cancellation-policy calculation. The guest never supplies a
        platform escrow PIN; the approved system workflow performs the transfer.
        """
        try:
            booking = db.session.get(AccommodationBooking, booking_id)
            if not booking:
                return False, "Booking not found"

            actor = current_user
            if not actor or not actor.is_authenticated:
                return False, "An authenticated human refund approval is required"

            reason = str(approval_reason or "").strip()
            if not reason:
                return False, "A human approval reason is required"

            try:
                refund_amount = Decimal(str(refund_amount)).quantize(Decimal("0.01"))
            except Exception:
                return False, "Invalid refund amount"
            if refund_amount <= 0:
                return False, "Refund amount must be greater than zero"
            if refund_amount > Decimal(str(booking.total_amount or 0)):
                return False, "Refund amount cannot exceed the booking total"

            from app.accommodation.services.identity_service import AccommodationIdentityService
            prop = booking.accommodation_property
            is_property_manager = AccommodationIdentityService.can_manage_property(
                actor,
                property_owner_user_id=prop.owner_user_id if prop else None,
                property_owner_org_id=prop.owner_org_id if prop else None,
            )
            outcome = (booking.policy_snapshot or {}).get("cancellation_outcome", {})
            cancellation_approved_by_actor = (
                booking.cancelled_by_user_id == actor.id
                and actor.id in {
                    booking.booking_owner_id or booking.booked_by_user_id,
                    booking.booked_by_user_id,
                    booking.host_user_id,
                }
                and booking.status in {
                    AccommodationBookingStatus.CANCELLED.value,
                    AccommodationBookingStatus.REFUNDED.value,
                }
            )

            if not (is_property_manager or cancellation_approved_by_actor):
                return False, "You are not authorised to approve this booking refund"

            if cancellation_approved_by_actor:
                policy_refund = outcome.get("refund")
                if policy_refund is None or Decimal(str(policy_refund)) != refund_amount:
                    return False, "Refund amount does not match the human-approved cancellation policy"

            commission = BookingCommission.query.filter_by(booking_id=booking_id).first()
            if not commission:
                return False, "Commission record not found"

            if commission.status == 'refunded':
                return False, "Already refunded"
            if refund_amount > Decimal(str(commission.total_amount or 0)):
                return False, "Refund amount exceeds the amount held for this booking"

            approval_at = datetime.now(timezone.utc)
            approval_source = (
                "booking_cancellation"
                if cancellation_approved_by_actor
                else "host_manual_refund"
            )
            guest_account_id = MarketplaceService._get_account_for_user(booking.booked_by_user_id, booking.currency)
            platform_account_id = MarketplaceService._get_platform_account_id(booking.currency)

            wallet = WalletService()
            result = wallet.transfer(
                from_account_id=platform_account_id,
                to_account_id=guest_account_id,
                amount=refund_amount,
                currency=booking.currency,
                client_request_id=f"booking_{booking_id}_refund",
                note=f"Refund: {booking.booking_reference}",
                metadata={
                    'booking_id': str(booking_id),
                    'booking_reference': booking.booking_reference,
                    'refund_amount': str(refund_amount),
                    'approved_by_user_id': actor.id,
                    'approval_source': approval_source,
                    'approval_reason': reason,
                    'approved_at': approval_at.isoformat(),
                },
                # The authenticated human approval above authorizes execution;
                # the system moves escrow funds without a wallet-owner PIN.
                system_initiated=True,
            )

            if result.get('already_processed'):
                # Converge to the previously committed transfer and preserve its
                # original human approver in the commission audit metadata.
                existing = TransactionRepository(db.session).get_by_client_request_id(
                    f"booking_{booking_id}_refund"
                )
                recorded_amount = existing.amount if existing else refund_amount
                transaction_metadata = (
                    getattr(existing, "tx_metadata", None) if existing else None
                ) or {}
                refund_approval = {
                    "approved_by_user_id": transaction_metadata.get("approved_by_user_id"),
                    "approval_source": transaction_metadata.get("approval_source"),
                    "approval_reason": transaction_metadata.get("approval_reason"),
                    "approved_at": transaction_metadata.get("approved_at"),
                }
            else:
                recorded_amount = refund_amount
                refund_approval = {
                    "approved_by_user_id": actor.id,
                    "approval_source": approval_source,
                    "approval_reason": reason,
                    "approved_at": approval_at.isoformat(),
                }

            commission.status = 'refunded'
            commission.refund_amount = recorded_amount
            commission.refunded_at = datetime.now(timezone.utc)
            extra_data = dict(commission.extra_data or {})
            extra_data["refund_approval"] = refund_approval
            commission.extra_data = extra_data
            booking.refund_amount = recorded_amount
            booking.refunded_at = datetime.now(timezone.utc)
            booking.payment_status = 'refunded'
            db.session.commit()

            logger.info(
                f"Refund processed: {booking.booking_reference} | "
                f"Amount: {recorded_amount} {booking.currency} | "
                f"Approver: {refund_approval.get('approved_by_user_id')}"
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

