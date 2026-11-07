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
    def _refund_policy_signing_key() -> bytes:
        """Use an application-held secret, never a digest stored beside the policy."""
        key = (
            current_app.config.get("REFUND_POLICY_SIGNING_KEY")
            or current_app.config.get("SECRET_KEY")
        )
        if not key:
            raise RuntimeError("Refund policy signing key is not configured")
        return key if isinstance(key, bytes) else str(key).encode("utf-8")

    @staticmethod
    def _refund_policy_booking_context(booking) -> Dict[str, str]:
        return {
            "booking_id": str(booking.id),
            "booking_reference": str(booking.booking_reference),
            "property_id": str(booking.property_id),
            "booked_by_user_id": str(booking.booked_by_user_id),
            "host_user_id": str(booking.host_user_id),
            "currency": str(booking.currency or "").upper(),
        }

    @staticmethod
    def sign_cancellation_policy_rules(booking, rules: dict) -> str:
        """HMAC-sign immutable rules and bind them to this booking."""
        import hashlib
        import hmac
        import json

        unsigned_rules = {
            key: value for key, value in rules.items()
            if key not in {"hmac_sha256", "sha256"}
        }
        payload = json.dumps(
            {
                "booking": MarketplaceService._refund_policy_booking_context(booking),
                "rules": unsigned_rules,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hmac.new(
            MarketplaceService._refund_policy_signing_key(),
            payload,
            hashlib.sha256,
        ).hexdigest()

    @staticmethod
    def verify_cancellation_policy_rules(booking, rules: dict) -> bool:
        import hmac

        recorded = str((rules or {}).get("hmac_sha256") or "")
        if not recorded:
            return False
        try:
            expected = MarketplaceService.sign_cancellation_policy_rules(booking, rules)
        except Exception:
            return False
        return hmac.compare_digest(recorded, expected)

    @staticmethod
    def sign_cancellation_outcome(booking, outcome: dict) -> str:
        """Bind the calculated refund/fine to the signed booking-time rules."""
        import hashlib
        import hmac
        import json

        rules = (booking.policy_snapshot or {}).get("cancellation_policy_rules", {})
        payload = json.dumps(
            {
                "booking": MarketplaceService._refund_policy_booking_context(booking),
                "policy_rules_signature": (rules or {}).get("hmac_sha256"),
                "outcome": outcome,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hmac.new(
            MarketplaceService._refund_policy_signing_key(),
            payload,
            hashlib.sha256,
        ).hexdigest()

    @staticmethod
    def verify_cancellation_outcome(booking) -> bool:
        import hmac

        snapshot = booking.policy_snapshot if isinstance(booking.policy_snapshot, dict) else {}
        outcome = snapshot.get("cancellation_outcome")
        recorded = str(snapshot.get("cancellation_outcome_hmac") or "")
        if not isinstance(outcome, dict) or not recorded:
            return False
        try:
            expected = MarketplaceService.sign_cancellation_outcome(booking, outcome)
        except Exception:
            return False
        return hmac.compare_digest(recorded, expected)

    @staticmethod
    def sign_refund_workflow(booking, workflow: dict) -> str:
        """Authenticate every workflow state and decision stored in booking JSON."""
        import hashlib
        import hmac
        import json

        snapshot = booking.policy_snapshot if isinstance(booking.policy_snapshot, dict) else {}
        unsigned_workflow = {
            key: value for key, value in (workflow or {}).items()
            if key != "hmac_sha256"
        }
        payload = json.dumps(
            {
                "booking": MarketplaceService._refund_policy_booking_context(booking),
                "policy_rules_signature": (
                    snapshot.get("cancellation_policy_rules") or {}
                ).get("hmac_sha256"),
                "cancellation_outcome_signature": snapshot.get("cancellation_outcome_hmac"),
                "workflow": unsigned_workflow,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hmac.new(
            MarketplaceService._refund_policy_signing_key(),
            payload,
            hashlib.sha256,
        ).hexdigest()

    @staticmethod
    def verify_refund_workflow(booking, workflow: dict) -> bool:
        import hmac

        recorded = str((workflow or {}).get("hmac_sha256") or "")
        if not recorded:
            return False
        try:
            expected = MarketplaceService.sign_refund_workflow(booking, workflow)
        except Exception:
            return False
        return hmac.compare_digest(recorded, expected)

    @staticmethod
    def _store_refund_workflow(booking, snapshot: dict, workflow: dict) -> dict:
        signed = {
            key: value for key, value in (workflow or {}).items()
            if key != "hmac_sha256"
        }
        # The signer binds to the currently persisted policy and cancellation
        # signatures, so install the new snapshot context before signing.
        snapshot["refund_workflow"] = signed
        booking.policy_snapshot = snapshot
        signed["hmac_sha256"] = MarketplaceService.sign_refund_workflow(
            booking, signed
        )
        snapshot["refund_workflow"] = signed
        booking.policy_snapshot = snapshot
        return signed

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
    def _refund_workflow(booking):
        snapshot = dict(booking.policy_snapshot or {})
        workflow = dict(snapshot.get("refund_workflow") or {})
        return snapshot, workflow

    @staticmethod
    def _save_refund_workflow(booking, workflow):
        snapshot = dict(booking.policy_snapshot or {})
        return MarketplaceService._store_refund_workflow(
            booking, snapshot, workflow
        )

    @staticmethod
    def _record_refund_history(booking, actor_user_id, trigger, metadata):
        """Append one booking-history event and one canonical audit record."""
        from app.accommodation.models.booking import BookingStatusHistory
        from app.audit.models import AuditLog

        details = dict(metadata or {})
        db.session.add(
            BookingStatusHistory(
                booking_id=booking.id,
                from_status=booking.status,
                to_status=booking.status,
                changed_by=actor_user_id,
                trigger=trigger,
                change_metadata=details,
            )
        )
        # The canonical audit writer does not commit: the audit event and
        # business decision are committed atomically by the calling service.
        AuditLog.log(
            user_id=actor_user_id,
            action="accommodation_refund." + str(trigger),
            resource_type="accommodation_refund",
            resource_id=str(booking.booking_reference),
            meta={
                "booking_id": booking.id,
                "booking_reference": booking.booking_reference,
                "booking_status": booking.status,
                **details,
            },
            db_session=db.session,
        )

    @staticmethod
    def _refund_screening_flags(booking, refund_amount, commission):
        """Return machine-detected risks that prevent automatic settlement."""
        from app.wallet.models.transaction import TransactionModel

        flags = []
        amount = Decimal(str(refund_amount)).quantize(Decimal("0.01"))
        payment_method = str(booking.payment_method or "").lower()
        snapshot = booking.policy_snapshot if isinstance(booking.policy_snapshot, dict) else {}
        rules = snapshot.get("cancellation_policy_rules") or {}

        if rules.get("snapshot_version") != 2:
            flags.append("booking_time_policy_snapshot_incomplete")
        elif not MarketplaceService.verify_cancellation_policy_rules(booking, rules):
            flags.append("booking_time_policy_snapshot_integrity_failed")

        if not MarketplaceService.verify_cancellation_outcome(booking):
            flags.append("cancellation_outcome_integrity_failed")
        if payment_method not in {"wallet", "mock_gateway"}:
            flags.append("payment_not_held_in_platform_wallet")
        if not booking.wallet_txn_id:
            flags.append("original_platform_transaction_missing")
        if str(booking.payment_status or "").lower() not in {"paid", "partially_paid"}:
            flags.append("booking_payment_not_confirmed")
        paid_amount = Decimal(str(booking.amount_paid or 0))
        if amount > paid_amount:
            flags.append("refund_exceeds_confirmed_payment")
        if commission is None:
            flags.append("escrow_commission_record_missing")
        else:
            if commission.status != "held":
                flags.append("escrow_not_held_for_automatic_refund")
            if amount > Decimal(str(commission.total_amount or 0)):
                flags.append("refund_exceeds_escrow_amount")
        if booking.refunded_at or Decimal(str(booking.refund_amount or 0)) > 0:
            flags.append("previous_refund_recorded")

        # Verify that the referenced original transaction is a completed
        # platform ledger payment by the booking's payer for this booking.
        if booking.wallet_txn_id:
            try:
                from uuid import UUID
                original_transaction_id = UUID(str(booking.wallet_txn_id))
                original = TransactionModel.query.filter_by(
                    id=original_transaction_id
                ).first()
            except (ValueError, TypeError, AttributeError):
                original = None
            except Exception:
                # A failed read is not permission to refund. The missing
                # transaction is converted into a review flag below.
                original = None
            original_status = getattr(getattr(original, "status", None), "value", getattr(original, "status", None))
            original_metadata = dict(getattr(original, "tx_metadata", None) or {}) if original else {}
            if (
                original is None
                or str(original_status).lower() != "completed"
                or original.user_id != booking.booked_by_user_id
                or Decimal(str(original.amount or 0)) < amount
                or str(original.currency or "").upper() != str(booking.currency or "").upper()
                or str(original_metadata.get("booking_id")) != str(booking.id)
            ):
                flags.append("original_payment_cannot_be_reconciled")

        return list(dict.fromkeys(flags))

    @staticmethod
    def _execute_escrow_refund(
        booking,
        commission,
        refund_amount: Decimal,
        *,
        authorization_source: str,
        authorized_by_user_id: int,
        approval_reason: str,
        approved_by_user_id: Optional[int] = None,
    ) -> Tuple[bool, Optional[str]]:
        """Move an approved refund through the real wallet ledger exactly once."""
        from app.wallet.models.transaction import TransactionModel
        from app.wallet.repositories.transaction_repository import TransactionRepository
        from app.accommodation.state_machine.booking_states import BookingStateMachine
        from app.accommodation.models.booking import AccommodationBookingStatus, AccommodationPaymentStatus

        amount = Decimal(str(refund_amount)).quantize(Decimal("0.01"))
        if amount <= 0:
            return False, "Refund amount must be greater than zero"
        if commission is None or commission.status != "held":
            return False, "Platform escrow is not held; human recovery review is required"
        if amount > Decimal(str(booking.amount_paid or 0)):
            return False, "Refund exceeds the amount actually paid"
        if amount > Decimal(str(commission.total_amount or 0)):
            return False, "Refund exceeds the amount held in escrow"

        if commission.status == "refunded":
            return False, "Already refunded"

        refund_key = "booking_" + str(booking.id) + "_refund"
        wallet = WalletService()
        result = wallet.transfer(
            from_account_id=MarketplaceService._get_platform_account_id(booking.currency),
            to_account_id=MarketplaceService._get_account_for_user(
                booking.booked_by_user_id, booking.currency
            ),
            amount=amount,
            currency=booking.currency,
            client_request_id=refund_key,
            note="Accommodation refund: " + str(booking.booking_reference),
            metadata={
                "booking_id": str(booking.id),
                "booking_reference": booking.booking_reference,
                "refund_amount": str(amount),
                "authorization_source": authorization_source,
                "authorized_by_user_id": authorized_by_user_id,
                "approved_by_user_id": approved_by_user_id,
                "approval_reason": approval_reason,
                "approved_at": datetime.now(timezone.utc).isoformat(),
            },
            # The accommodation policy engine or platform reviewer has
            # authorized this specific escrow movement. It is not a guest
            # wallet transfer and never requests the guest's PIN.
            system_initiated=True,
        )

        existing = TransactionRepository(db.session).get_by_client_request_id(refund_key)
        if existing is None:
            existing = TransactionModel.query.filter_by(client_request_id=refund_key).first()
        if existing is None:
            return False, "Wallet did not return a durable refund transaction"
        if Decimal(str(existing.amount)) != amount:
            return False, "An earlier refund exists for a different amount; human reconciliation is required"

        transaction_metadata = dict(existing.tx_metadata or {})
        if result.get("already_processed"):
            # A retry may finish the business record only when the durable
            # wallet transaction carries an approval record.
            if not transaction_metadata.get("authorization_source"):
                return False, "Existing refund transaction has no authorization evidence"
            refund_authorization = {
                "authorization_source": transaction_metadata.get("authorization_source"),
                "authorized_by_user_id": transaction_metadata.get("authorized_by_user_id"),
                "approved_by_user_id": transaction_metadata.get("approved_by_user_id"),
                "approval_reason": transaction_metadata.get("approval_reason"),
                "approved_at": transaction_metadata.get("approved_at"),
            }
        else:
            refund_authorization = {
                "authorization_source": authorization_source,
                "authorized_by_user_id": authorized_by_user_id,
                "approved_by_user_id": approved_by_user_id,
                "approval_reason": approval_reason,
                "approved_at": transaction_metadata.get("approved_at")
                or datetime.now(timezone.utc).isoformat(),
            }

        now = datetime.now(timezone.utc)
        commission_is_fully_refunded = amount >= Decimal(str(commission.total_amount or 0))
        booking_is_fully_refunded = amount >= Decimal(str(booking.amount_paid or 0))
        commission.status = "refunded" if commission_is_fully_refunded else "partially_refunded"
        commission.refund_amount = amount
        commission.refunded_at = now
        extra_data = dict(commission.extra_data or {})
        extra_data["refund_authorization"] = refund_authorization
        commission.extra_data = extra_data

        booking.refund_amount = amount
        booking.refunded_at = now
        booking.payment_status = (
            AccommodationPaymentStatus.REFUNDED.value
            if booking_is_fully_refunded
            else AccommodationPaymentStatus.PARTIAL_REFUND.value
        )
        if booking.status == AccommodationBookingStatus.CANCELLED.value and booking_is_fully_refunded:
            BookingStateMachine.transition(
                booking,
                AccommodationBookingStatus.REFUNDED,
                changed_by_user_id=approved_by_user_id or authorized_by_user_id,
                reason="Refund executed under recorded authorization",
                trigger="refund_processed",
            )

        snapshot, workflow = MarketplaceService._refund_workflow(booking)
        workflow.update({
            "state": "refunded" if booking_is_fully_refunded else "partially_refunded",
            "actual_amount": str(amount),
            "remaining_paid_amount": str(
                max(Decimal("0.00"), Decimal(str(booking.amount_paid or 0)) - amount)
            ),
            "remaining_escrow_amount": str(
                max(Decimal("0.00"), Decimal(str(commission.total_amount or 0)) - amount)
            ),
            "transaction_id": str(existing.id),
            "completed_at": now.isoformat(),
            "authorization": refund_authorization,
        })
        MarketplaceService._store_refund_workflow(booking, snapshot, workflow)
        booking.policy_snapshot = snapshot
        MarketplaceService._record_refund_history(
            booking,
            approved_by_user_id or authorized_by_user_id,
            "refund_ledger_settled",
            {
                "amount": str(amount),
                "currency": booking.currency,
                "transaction_id": str(existing.id),
                "authorization": refund_authorization,
                "full_refund": booking_is_fully_refunded,
            },
        )
        db.session.commit()
        return True, None

    @staticmethod
    def refund_guest(
        booking_id: int,
        refund_amount: Decimal,
    ) -> Tuple[bool, Optional[str]]:
        """
        Process a guest-authorized, booking-policy refund automatically when
        the booking-time policy and platform escrow reconcile. Any ambiguity
        or explicit exception request is placed in the platform human-review
        queue; a host is never asked to approve an ordinary guest cancellation.
        """
        from flask import current_app
        from sqlalchemy import select
        from app.accommodation.models.booking import AccommodationBookingStatus

        try:
            booking = db.session.execute(
                select(AccommodationBooking)
                .where(AccommodationBooking.id == booking_id)
                .with_for_update()
            ).scalar_one_or_none()
            if booking is None:
                return False, "Booking not found"

            actor = current_user
            if not actor or not actor.is_authenticated:
                return False, "An authenticated booking cancellation is required"
            if (
                booking.cancelled_by_user_id != actor.id
                or booking.status not in {
                    AccommodationBookingStatus.CANCELLED.value,
                    AccommodationBookingStatus.REFUNDED.value,
                }
            ):
                return False, "Only the authenticated cancellation actor can start this policy refund"

            amount = Decimal(str(refund_amount)).quantize(Decimal("0.01"))
            outcome = (booking.policy_snapshot or {}).get("cancellation_outcome", {})
            policy_amount = Decimal(str(outcome.get("refund") or "0")).quantize(Decimal("0.01"))
            if amount <= 0 or amount != policy_amount:
                return False, "Refund amount does not match the recorded booking-time cancellation calculation"

            snapshot, workflow = MarketplaceService._refund_workflow(booking)
            if not MarketplaceService.verify_refund_workflow(booking, workflow):
                # Do not trust a database-stored workflow state or requester
                # identity unless it is signed by the application secret.
                workflow.update({
                    "state": "pending_human_review",
                    "risk_flags": list(dict.fromkeys(
                        list(workflow.get("risk_flags") or [])
                        + ["refund_workflow_integrity_failed"]
                    )),
                    "review_reason": "The stored refund workflow failed its signature check",
                    "integrity_review_queued_at": datetime.now(timezone.utc).isoformat(),
                })
                MarketplaceService._store_refund_workflow(booking, snapshot, workflow)
                MarketplaceService._record_refund_history(
                    booking,
                    actor.id,
                    "refund_workflow_integrity_review_queued",
                    {
                        "risk_flag": "refund_workflow_integrity_failed",
                        "proposed_amount": workflow.get("proposed_amount"),
                    },
                )
                db.session.commit()
                return True, "Refund workflow integrity could not be verified; the case was sent for human review"
            if workflow.get("state") in {"refunded", "partially_refunded"}:
                return False, "Already refunded"
            if workflow.get("state") in {
                "pending_human_review",
                "approved_external_execution_pending",
                "approved_recovery_required",
                "rejected",
            }:
                return True, "Refund is awaiting platform human review or external settlement"

            commission = (
                BookingCommission.query.filter_by(booking_id=booking_id)
                .with_for_update()
                .first()
            )
            flags = MarketplaceService._refund_screening_flags(
                booking, amount, commission
            )
            if workflow.get("risk_flags"):
                flags.extend(workflow["risk_flags"])
            flags = list(dict.fromkeys(flags))
            if flags:
                workflow.update({
                    "state": "pending_human_review",
                    "proposed_amount": str(amount),
                    "currency": booking.currency or "USD",
                    "risk_flags": flags,
                    "review_submitted_at": datetime.now(timezone.utc).isoformat(),
                    "review_reason": "Machine screening could not safely authorize automatic refund",
                })
                MarketplaceService._store_refund_workflow(booking, snapshot, workflow)
                booking.policy_snapshot = snapshot
                MarketplaceService._record_refund_history(
                    booking,
                    actor.id,
                    "refund_review_queued",
                    {
                        "proposed_amount": str(amount),
                        "currency": booking.currency,
                        "risk_flags": flags,
                        "request_source": workflow.get("request_source"),
                    },
                )
                db.session.commit()
                return True, "Refund submitted to the platform human-approval queue"

            reason = (
                booking.cancellation_reason
                or "Authenticated guest cancellation under frozen booking policy"
            )
            return MarketplaceService._execute_escrow_refund(
                booking,
                commission,
                amount,
                authorization_source="booking_time_policy",
                authorized_by_user_id=actor.id,
                approval_reason=reason,
            )
        except Exception as exc:
            db.session.rollback()
            current_app.logger.exception(
                "Automatic accommodation refund failed for booking %s", booking_id
            )
            try:
                booking = db.session.get(AccommodationBooking, booking_id)
                if booking:
                    snapshot, workflow = MarketplaceService._refund_workflow(booking)
                    workflow.update({
                        "state": "pending_human_review",
                        "last_error": str(exc)[:500],
                        "failed_at": datetime.now(timezone.utc).isoformat(),
                        "risk_flags": list(dict.fromkeys(
                            list(workflow.get("risk_flags") or []) + ["automatic_refund_execution_failed"]
                        )),
                    })
                    MarketplaceService._store_refund_workflow(booking, snapshot, workflow)
                    booking.policy_snapshot = snapshot
                    db.session.commit()
            except Exception:
                db.session.rollback()
            return False, "Refund execution failed; the payment remains unrefunded"

    @staticmethod
    def submit_refund_review(
        booking_id: int,
        refund_amount: Decimal,
        reason: str,
        *,
        requested_by_user_id: int,
        request_source: str = "host_manual_refund",
    ) -> Tuple[bool, Optional[str]]:
        """Submit a provider/manual exception for independent platform review."""
        from sqlalchemy import select
        from app.accommodation.services.identity_service import AccommodationIdentityService
        from app.identity.models.user import User
        from flask_login import current_user

        try:
            booking = db.session.execute(
                select(AccommodationBooking)
                .where(AccommodationBooking.id == booking_id)
                .with_for_update()
            ).scalar_one_or_none()
            if not booking:
                return False, "Booking not found"
            actor = db.session.get(User, requested_by_user_id)
            if (
                not current_user
                or not current_user.is_authenticated
                or current_user.id != requested_by_user_id
            ):
                return False, "The refund requester must be the authenticated property manager"
            prop = booking.accommodation_property
            if not actor or not AccommodationIdentityService.can_manage_property(
                actor,
                property_owner_user_id=prop.owner_user_id if prop else None,
                property_owner_org_id=prop.owner_org_id if prop else None,
            ):
                return False, "Only an authorised property manager can submit this request"
            reason = str(reason or "").strip()
            if len(reason) < 5:
                return False, "A review reason of at least five characters is required"
            amount = Decimal(str(refund_amount)).quantize(Decimal("0.01"))
            if amount < 0 or amount > Decimal(str(booking.amount_paid or 0)):
                return False, "Requested refund must not exceed the confirmed amount paid"
            snapshot, workflow = MarketplaceService._refund_workflow(booking)
            workflow_signature_valid = MarketplaceService.verify_refund_workflow(
                booking, workflow
            )
            if workflow.get("state") in {
                "pending_human_review",
                "approved_external_execution_pending",
                "approved_recovery_required",
                "refunded",
                "partially_refunded",
            } and workflow_signature_valid:
                return False, "A refund review or settlement is already active for this booking"
            if not workflow_signature_valid:
                workflow["risk_flags"] = list(dict.fromkeys(
                    list(workflow.get("risk_flags") or [])
                    + ["refund_workflow_integrity_failed"]
                ))
                workflow["integrity_review_reason"] = (
                    "Previous refund workflow signature was invalid; provider request resubmitted for review"
                )
            workflow.update({
                "state": "pending_human_review",
                "proposed_amount": str(amount),
                "currency": booking.currency or "USD",
                "request_source": request_source,
                "requested_by_user_id": requested_by_user_id,
                "request_reason": reason,
                "submitted_at": datetime.now(timezone.utc).isoformat(),
                "risk_flags": list(dict.fromkeys(
                    list(workflow.get("risk_flags") or []) + ["provider_or_manual_exception"]
                )),
            })
            MarketplaceService._store_refund_workflow(booking, snapshot, workflow)
            booking.policy_snapshot = snapshot
            MarketplaceService._record_refund_history(
                booking,
                requested_by_user_id,
                "refund_review_submitted",
                {
                    "proposed_amount": str(amount),
                    "currency": booking.currency,
                    "request_source": request_source,
                    "reason": reason,
                    "risk_flags": workflow["risk_flags"],
                },
            )
            db.session.commit()
            return True, None
        except Exception as exc:
            db.session.rollback()
            logger.exception("Could not submit accommodation refund review for %s", booking_id)
            return False, str(exc)

    @staticmethod
    def refund_guest_approved(
        booking_id: int,
        refund_amount: Decimal,
        approval_reason: Optional[str] = None,
        *,
        integrity_exception_acknowledged: bool = False,
    ) -> Tuple[bool, Optional[str]]:
        """Execute a queued refund only after an independent platform admin approves it."""
        from flask_login import current_user
        from app.auth.helpers import has_global_role
        from sqlalchemy import select

        try:
            actor = current_user
            if not actor or not actor.is_authenticated or not has_global_role(
                actor, "admin", "super_admin", "owner", "accommodation_admin"
            ):
                return False, "Platform administrator approval is required"
            reason = str(approval_reason or "").strip()
            if len(reason) < 5:
                return False, "An approval reason of at least five characters is required"

            booking = db.session.execute(
                select(AccommodationBooking)
                .where(AccommodationBooking.id == booking_id)
                .with_for_update()
            ).scalar_one_or_none()
            if not booking:
                return False, "Booking not found"

            snapshot, workflow = MarketplaceService._refund_workflow(booking)
            if not MarketplaceService.verify_refund_workflow(booking, workflow):
                return False, "Refund workflow signature failed; do not approve until the case is safely resubmitted and reviewed"
            if booking.refunded_at or Decimal(str(booking.refund_amount or 0)) > 0:
                return False, "A refund has already been executed for this booking"
            if workflow.get("state") in {"refunded", "partially_refunded"}:
                return False, "Already refunded"
            if workflow.get("state") != "pending_human_review":
                return False, "This refund is not awaiting human review"
            prohibited_actors = {
                booking.cancelled_by_user_id,
                booking.booked_by_user_id,
                booking.guest_user_id,
                booking.host_user_id,
                workflow.get("requested_by_user_id"),
            }
            if actor.id in prohibited_actors:
                return False, "The cancellation actor, guest, requester or host cannot approve this refund"

            amount = Decimal(str(refund_amount)).quantize(Decimal("0.01"))
            if amount <= 0:
                return False, "Approved refund amount must be greater than zero"
            if amount > Decimal(str(booking.amount_paid or 0)):
                return False, "Approved refund cannot exceed the amount actually collected"
            if amount > Decimal(str(booking.total_amount or 0)):
                return False, "Approved refund cannot exceed the booking total"

            payment_method = str(booking.payment_method or "").lower()
            commission = (
                BookingCommission.query.filter_by(booking_id=booking_id)
                .with_for_update()
                .first()
            )
            if amount > Decimal(str(booking.amount_paid or 0)):
                return False, "Approved refund cannot exceed the amount actually collected"
            if payment_method in {"wallet", "mock_gateway"}:
                screening_flags = MarketplaceService._refund_screening_flags(
                    booking, amount, commission
                )
                integrity_flags = {
                    "booking_time_policy_snapshot_incomplete",
                    "booking_time_policy_snapshot_integrity_failed",
                    "cancellation_outcome_integrity_failed",
                }
                discovered_integrity_flags = integrity_flags.intersection(screening_flags)
                if discovered_integrity_flags and not integrity_exception_acknowledged:
                    workflow.update({
                        "risk_flags": list(dict.fromkeys(
                            list(workflow.get("risk_flags") or [])
                            + sorted(discovered_integrity_flags)
                        )),
                        "integrity_review_required": True,
                        "integrity_reviewed_at": datetime.now(timezone.utc).isoformat(),
                    })
                    MarketplaceService._store_refund_workflow(
                        booking, snapshot, workflow
                    )
                    booking.policy_snapshot = snapshot
                    MarketplaceService._record_refund_history(
                        booking,
                        actor.id,
                        "refund_policy_integrity_rechecked",
                        {
                            "integrity_flags": sorted(discovered_integrity_flags),
                            "approval_blocked": True,
                        },
                    )
                    db.session.commit()
                    return False, (
                        "The booking policy evidence failed its integrity check. "
                        "Review the warning and explicitly acknowledge the exception before approval."
                    )
                if discovered_integrity_flags:
                    workflow.update({
                        "integrity_exception_acknowledged_by_user_id": actor.id,
                        "integrity_exception_acknowledged_at": datetime.now(timezone.utc).isoformat(),
                        "integrity_exception_reason": reason,
                        "risk_flags": list(dict.fromkeys(
                            list(workflow.get("risk_flags") or [])
                            + sorted(discovered_integrity_flags)
                        )),
                    })
                    MarketplaceService._store_refund_workflow(
                        booking, snapshot, workflow
                    )
                    booking.policy_snapshot = snapshot
                    MarketplaceService._record_refund_history(
                        booking,
                        actor.id,
                        "refund_policy_integrity_exception_acknowledged",
                        {
                            "integrity_flags": sorted(discovered_integrity_flags),
                            "approval_reason": reason,
                        },
                    )

                hard_flags = {
                    "original_platform_transaction_missing",
                    "original_payment_cannot_be_reconciled",
                    "booking_payment_not_confirmed",
                    "refund_exceeds_confirmed_payment",
                    "escrow_commission_record_missing",
                    "refund_exceeds_escrow_amount",
                    "previous_refund_recorded",
                }
                flags = set(MarketplaceService._refund_screening_flags(
                    booking, amount, commission
                ))
                if flags.intersection(hard_flags):
                    return False, "The original payment or escrow cannot be reconciled; keep this request in review"
            if payment_method not in {"wallet", "mock_gateway"}:
                workflow.update({
                    "state": "approved_external_execution_pending",
                    "approved_amount": str(amount),
                    "approved_by_user_id": actor.id,
                    "approval_reason": reason,
                    "approved_at": datetime.now(timezone.utc).isoformat(),
                    "execution_owner": "original_payment_provider_or_property",
                    "execution_note": "Do not mark refunded until the original payment channel supplies an execution reference.",
                })
                MarketplaceService._store_refund_workflow(booking, snapshot, workflow)
                booking.policy_snapshot = snapshot
                MarketplaceService._record_refund_history(
                    booking,
                    actor.id,
                    "refund_review_approved_external",
                    {
                        "approved_amount": str(amount),
                        "currency": booking.currency,
                        "approval_reason": reason,
                        "execution_owner": workflow["execution_owner"],
                    },
                )
                db.session.commit()
                return True, "Approved. Refund remains pending execution by the original payment provider or property"

            if commission is None or commission.status != "held":
                workflow.update({
                    "state": "approved_recovery_required",
                    "approved_amount": str(amount),
                    "approved_by_user_id": actor.id,
                    "approval_reason": reason,
                    "approved_at": datetime.now(timezone.utc).isoformat(),
                    "execution_note": "Escrow has already been released or cannot be reconciled. Financial recovery is required before payment.",
                })
                MarketplaceService._store_refund_workflow(booking, snapshot, workflow)
                booking.policy_snapshot = snapshot
                MarketplaceService._record_refund_history(
                    booking,
                    actor.id,
                    "refund_review_approved_recovery_required",
                    {
                        "approved_amount": str(amount),
                        "currency": booking.currency,
                        "approval_reason": reason,
                        "commission_status": commission.status if commission else None,
                    },
                )
                db.session.commit()
                return True, "Approved, but escrow recovery is required before the refund can be executed"

            return MarketplaceService._execute_escrow_refund(
                booking,
                commission,
                amount,
                authorization_source="platform_human_review",
                authorized_by_user_id=actor.id,
                approved_by_user_id=actor.id,
                approval_reason=reason,
            )
        except Exception as exc:
            db.session.rollback()
            logger.exception("Human-approved accommodation refund failed for %s", booking_id)
            return False, "Could not execute approved refund: " + str(exc)

    @staticmethod
    def reject_refund_review(
        booking_id: int,
        reason: str,
        *,
        reviewer_user_id: int,
    ) -> Tuple[bool, Optional[str]]:
        """Record a human rejection without changing the original payment."""
        from app.auth.helpers import has_global_role
        from app.identity.models.user import User
        from flask_login import current_user
        from sqlalchemy import select

        try:
            actor = db.session.get(User, reviewer_user_id)
            if (
                not current_user
                or not current_user.is_authenticated
                or current_user.id != reviewer_user_id
            ):
                return False, "The refund reviewer must be the authenticated platform administrator"
            if not actor or not has_global_role(
                actor, "admin", "super_admin", "owner", "accommodation_admin"
            ):
                return False, "Platform administrator review is required"
            reason = str(reason or "").strip()
            if len(reason) < 5:
                return False, "A rejection reason of at least five characters is required"
            booking = db.session.execute(
                select(AccommodationBooking)
                .where(AccommodationBooking.id == booking_id)
                .with_for_update()
            ).scalar_one_or_none()
            if not booking:
                return False, "Booking not found"
            snapshot, workflow = MarketplaceService._refund_workflow(booking)
            if not MarketplaceService.verify_refund_workflow(booking, workflow):
                return False, "Refund workflow signature failed; do not reject until the case is safely resubmitted and reviewed"
            if workflow.get("state") != "pending_human_review":
                return False, "This refund is not awaiting human review"
            if reviewer_user_id in {
                booking.cancelled_by_user_id,
                booking.booked_by_user_id,
                booking.guest_user_id,
                booking.host_user_id,
                workflow.get("requested_by_user_id"),
            }:
                return False, "The cancellation actor, guest, requester or host cannot reject this review as the platform reviewer"
            workflow.update({
                "state": "rejected",
                "rejected_by_user_id": reviewer_user_id,
                "rejection_reason": reason,
                "rejected_at": datetime.now(timezone.utc).isoformat(),
            })
            MarketplaceService._store_refund_workflow(booking, snapshot, workflow)
            booking.policy_snapshot = snapshot
            MarketplaceService._record_refund_history(
                booking,
                reviewer_user_id,
                "refund_review_rejected",
                {
                    "rejection_reason": reason,
                    "requested_by_user_id": workflow.get("requested_by_user_id"),
                    "proposed_amount": workflow.get("proposed_amount"),
                },
            )
            db.session.commit()
            return True, None
        except Exception as exc:
            db.session.rollback()
            logger.exception("Could not reject accommodation refund for %s", booking_id)
            return False, str(exc)

    @staticmethod
    def record_external_refund_execution(
        booking_id: int,
        amount: Decimal,
        provider_reference: str,
        *,
        verification_note: str,
        reviewer_user_id: int,
    ) -> Tuple[bool, Optional[str]]:
        """Record verified completion by the original payment channel."""
        from app.auth.helpers import has_global_role
        from app.identity.models.user import User
        from flask_login import current_user
        from app.accommodation.models.booking import AccommodationBookingStatus, AccommodationPaymentStatus
        from app.accommodation.state_machine.booking_states import BookingStateMachine

        try:
            actor = db.session.get(User, reviewer_user_id)
            if (
                not current_user
                or not current_user.is_authenticated
                or current_user.id != reviewer_user_id
            ):
                return False, "The execution verifier must be the authenticated platform administrator"
            if not actor or not has_global_role(
                actor, "admin", "super_admin", "owner", "accommodation_admin"
            ):
                return False, "Platform administrator authorization is required"
            reference = str(provider_reference or "").strip()
            verification_note = str(verification_note or "").strip()
            if not reference:
                return False, "Original provider refund reference is required"
            if len(verification_note) < 10:
                return False, "Record what you independently checked in the original provider's system"
            from sqlalchemy import select
            booking = db.session.execute(
                select(AccommodationBooking)
                .where(AccommodationBooking.id == booking_id)
                .with_for_update()
            ).scalar_one_or_none()
            if not booking:
                return False, "Booking not found"
            snapshot, workflow = MarketplaceService._refund_workflow(booking)
            if not MarketplaceService.verify_refund_workflow(booking, workflow):
                return False, "The external refund approval record failed its signature check"
            if workflow.get("state") != "approved_external_execution_pending":
                return False, "This refund is not awaiting external payment execution"
            if not workflow.get("approved_by_user_id") or not workflow.get("approval_reason"):
                return False, "The human approval record is incomplete"
            if reviewer_user_id in {
                workflow.get("approved_by_user_id"),
                workflow.get("requested_by_user_id"),
                booking.cancelled_by_user_id,
                booking.booked_by_user_id,
                booking.guest_user_id,
                booking.host_user_id,
            }:
                return False, "A different platform administrator must verify external execution"
            amount = Decimal(str(amount)).quantize(Decimal("0.01"))
            if amount <= 0 or amount > Decimal(str(booking.amount_paid or 0)):
                return False, "Verified provider refund must be positive and no greater than the amount collected"
            if amount != Decimal(str(workflow.get("approved_amount") or "0")):
                return False, "Recorded provider execution amount does not match the approved amount"
            from app.accommodation.models.booking import BookingStatusHistory
            existing_external_records = BookingStatusHistory.query.filter_by(
                trigger="external_refund_verified"
            ).all()
            if any(
                str((row.change_metadata or {}).get("external_provider_reference")) == reference
                for row in existing_external_records
            ):
                return False, "This provider refund reference has already been recorded"
            full_refund = amount >= Decimal(str(booking.amount_paid or 0))
            booking.refund_amount = amount
            booking.refunded_at = datetime.now(timezone.utc)
            booking.payment_status = (
                AccommodationPaymentStatus.REFUNDED.value
                if full_refund else AccommodationPaymentStatus.PARTIAL_REFUND.value
            )
            if (
                booking.status == AccommodationBookingStatus.CANCELLED.value
                and full_refund
            ):
                BookingStateMachine.transition(
                    booking,
                    AccommodationBookingStatus.REFUNDED,
                    changed_by_user_id=reviewer_user_id,
                    reason="Original payment provider refund verified",
                    trigger="external_refund_verified",
                )
            workflow.update({
                "state": "refunded" if full_refund else "partially_refunded",
                "actual_amount": str(amount),
                "external_provider_reference": reference,
                "execution_verification_note": verification_note,
                "execution_verification_method": "independent_manual_provider_reconciliation",
                "execution_verified_by_user_id": reviewer_user_id,
                "execution_verified_at": datetime.now(timezone.utc).isoformat(),
            })
            MarketplaceService._store_refund_workflow(booking, snapshot, workflow)
            booking.policy_snapshot = snapshot
            MarketplaceService._record_refund_history(
                booking,
                reviewer_user_id,
                "external_refund_verified",
                {
                    "approved_by_user_id": workflow.get("approved_by_user_id"),
                    "verified_by_user_id": reviewer_user_id,
                    "amount": str(amount),
                    "currency": booking.currency,
                    "external_provider_reference": reference,
                    "verification_note": verification_note,
                    "verification_method": "independent_manual_provider_reconciliation",
                    "full_refund": full_refund,
                },
            )
            db.session.commit()
            return True, None
        except Exception as exc:
            db.session.rollback()
            logger.exception("Could not record external refund execution for %s", booking_id)
            return False, str(exc)

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

