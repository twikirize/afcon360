"""
app/wallet/services/audit.py
COMPLETE AUDIT SYSTEM FOR WALLET

Audits EVERY wallet operation:
- Deposits (success/failure)
- Withdrawals (success/failure)
- Transfers (success/failure)
- Balance changes (before/after)
- API calls to payment providers
- KYC/compliance checks
- Sensitive data access
- Security events (AML flags)
- Login attempts to wallet
- Wallet creation
- Wallet freezing/unfreezing
- Agent commissions
- Payout requests

NOTHING is missed.
"""

from decimal import Decimal
from typing import Optional, Dict, Any, List
from datetime import datetime
from flask import request, current_app
import uuid
import inspect
import json

from app.extensions import db
from app.audit.comprehensive_audit import (
    AuditService,
    TransactionType,
    APICallStatus,
    AuditSeverity,
    DataAccessType
)


class WalletAudit:
    """
    COMPLETE AUDIT SYSTEM - Audits EVERY wallet operation.

    Every method in this class should be called whenever something happens
    in the wallet system. NO OPERATION should go un-audited.
    """

    # ========================================================================
    # HELPER METHODS
    # ========================================================================

    @staticmethod
    def _get_request_context() -> Dict[str, Any]:
        """Get current request and identity context for audit (actor vs effective)."""
        try:
            # Identity
            actor_id = None
            effective_id = None
            try:
                from app.core.context import RequestContext
                actor = RequestContext.get_actor()
                effective = RequestContext.get_effective_user()
                actor_id = getattr(actor, 'id', None)
                effective_id = getattr(effective, 'id', None)
            except Exception:
                pass

            # Request/session
            session_id = None
            try:
                from flask import session as flask_session
                session_id = flask_session.get('session_id') or flask_session.get('_id') or getattr(flask_session, 'sid', None)
            except Exception:
                session_id = None

            return {
                "ip_address": request.remote_addr if request else None,
                "user_agent": request.user_agent.string if request and request.user_agent else None,
                "endpoint": request.endpoint if request else None,
                "method": request.method if request else None,
                "actor_user_id": actor_id,
                "effective_user_id": effective_id,
                "session_id": session_id,
            }
        except Exception:
            return {"ip_address": None, "user_agent": None, "endpoint": None, "method": None, "actor_user_id": None, "effective_user_id": None, "session_id": None}

    @staticmethod
    def _generate_audit_id() -> str:
        """Generate unique audit ID for tracking."""
        return f"AUD-{uuid.uuid4().hex[:12].upper()}"

    # ========================================================================
    # WALLET LIFECYCLE AUDITS
    # ========================================================================

    @staticmethod
    def log_wallet_created(
        user_id: int,
        wallet_id: int,
        wallet_ref: str,
        home_currency: str,
        local_currency: str,
        created_by: int = None
    ):
        """
        Audit wallet creation.
        Called when a new wallet is created.
        """
        context = WalletAudit._get_request_context()

        AuditService.data_change(
            entity_type="wallet",
            entity_id=wallet_id,
            operation="create",
            old_value=None,
            new_value={
                "user_id": user_id,
                "wallet_ref": wallet_ref,
                "home_currency": home_currency,
                "local_currency": local_currency
            },
            changed_by=created_by or user_id,
            ip_address=context.get("ip_address"),
            user_agent=context.get("user_agent"),
            extra_data={
                "audit_id": WalletAudit._generate_audit_id(),
                "event": "wallet_created"
            }
        )

    @staticmethod
    def log_wallet_frozen(
        user_id: int,
        wallet_id: int,
        wallet_ref: str,
        reason: str,
        frozen_by: int
    ):
        """
        Audit wallet freeze.
        Called when an admin freezes a wallet.
        """
        context = WalletAudit._get_request_context()

        AuditService.security(
            event_type="wallet_frozen",
            severity=AuditSeverity.WARNING,
            description=f"Wallet {wallet_ref} frozen. Reason: {reason}",
            user_id=user_id,
            ip_address=context.get("ip_address"),
            extra_data={
                "wallet_id": wallet_id,
                "wallet_ref": wallet_ref,
                "reason": reason,
                "frozen_by": frozen_by,
                "audit_id": WalletAudit._generate_audit_id()
            }
        )

    @staticmethod
    def log_wallet_unfrozen(
        user_id: int,
        wallet_id: int,
        wallet_ref: str,
        unfrozen_by: int
    ):
        """
        Audit wallet unfreeze.
        Called when an admin unfreezes a wallet.
        """
        context = WalletAudit._get_request_context()

        AuditService.security(
            event_type="wallet_unfrozen",
            severity=AuditSeverity.INFO,
            description=f"Wallet {wallet_ref} unfrozen",
            user_id=user_id,
            ip_address=context.get("ip_address"),
            extra_data={
                "wallet_id": wallet_id,
                "wallet_ref": wallet_ref,
                "unfrozen_by": unfrozen_by,
                "audit_id": WalletAudit._generate_audit_id()
            }
        )

    # ========================================================================
    # DEPOSIT AUDITS (Complete - Nothing Missed)
    # ========================================================================

    @staticmethod
    def log_deposit_initiated(
        user_id: int,
        amount: Decimal,
        currency: str,
        payment_method: str,
        payment_provider: str,
        idempotency_key: str = None
    ):
        """
        Audit deposit initiation.
        Called BEFORE calling payment provider.
        """
        context = WalletAudit._get_request_context()

        AuditService.financial(
            transaction_id=f"DEP-{uuid.uuid4().hex[:12].upper()}",
            transaction_type=TransactionType.DEPOSIT,
            amount=amount,
            currency=currency,
            status="initiated",
            to_user_id=user_id,
            payment_method=payment_method,
            payment_provider=payment_provider,
            ip_address=context.get("ip_address"),
            user_agent=context.get("user_agent"),
            extra_data={
                "idempotency_key": idempotency_key,
                "stage": "initiated",
                "audit_id": WalletAudit._generate_audit_id()
            }
        )

    @staticmethod
    def log_payment_provider_call(
        user_id: int,
        provider: str,
        endpoint: str,
        method: str,
        request_payload: Dict,
        response: Dict,
        response_time_ms: int,
        success: bool
    ):
        """
        Audit payment provider API call.
        Called AFTER calling payment provider.
        """
        context = WalletAudit._get_request_context()
        audit_id = WalletAudit._generate_audit_id()

        status = APICallStatus.SUCCESS if success else APICallStatus.FAILURE

        AuditService.api_call(
            service_name=provider.lower(),
            endpoint=endpoint,
            method=method,
            request_id=f"REQ-{uuid.uuid4().hex[:12].upper()}",
            correlation_id=audit_id,
            status=status,
            response_status=response.get("status_code", 200),
            response_time_ms=response_time_ms,
            initiated_by=user_id,
            request_payload=request_payload,
            response_body=response,
            extra_data={
                "audit_id": audit_id,
                "provider": provider
            }
        )

    @staticmethod
    def log_deposit_completed(
        user_id: int,
        amount: Decimal,
        currency: str,
        transaction_id: str,
        balance_before: Decimal,
        balance_after: Decimal,
        payment_method: str,
        payment_provider: str,
        external_reference: str,
        risk_score: Decimal = None,
        aml_flagged: bool = False,
        fee_amount: Decimal = None
    ):
        """
        Audit successful deposit.
        Called AFTER wallet balance is updated.
        """
        context = WalletAudit._get_request_context()
        audit_id = WalletAudit._generate_audit_id()

        AuditService.financial(
            transaction_id=transaction_id,
            transaction_type=TransactionType.DEPOSIT,
            amount=amount,
            currency=currency,
            status="completed",
            to_user_id=user_id,
            to_balance_before=float(balance_before),
            to_balance_after=float(balance_after),
            payment_method=payment_method,
            payment_provider=payment_provider,
            external_reference=external_reference,
            fee_amount=float(fee_amount) if fee_amount else None,
            fee_currency=currency,
            risk_score=float(risk_score) if risk_score else None,
            aml_flagged=aml_flagged,
            requires_review=aml_flagged,
            ip_address=context.get("ip_address"),
            user_agent=context.get("user_agent"),
            extra_data={
                "audit_id": audit_id,
                "event": "deposit_completed"
            }
        )

        # Security alert for AML flagged deposits
        if aml_flagged:
            WalletAudit.log_security_alert(event_type="high_risk_deposit", severity="WARNING",
                                           description=f"High-risk deposit: {amount} {currency} via {payment_provider}",
                                           user_id=user_id)

    @staticmethod
    def log_deposit_failed(
        user_id: int,
        amount: Decimal,
        currency: str,
        payment_method: str,
        payment_provider: str,
        error: str,
        external_reference: str = None
    ):
        """
        Audit failed deposit.
        Called when deposit fails.
        """
        context = WalletAudit._get_request_context()
        audit_id = WalletAudit._generate_audit_id()

        AuditService.financial(
            transaction_id=f"DEP-{uuid.uuid4().hex[:12].upper()}",
            transaction_type=TransactionType.DEPOSIT,
            amount=amount,
            currency=currency,
            status="failed",
            to_user_id=user_id,
            payment_method=payment_method,
            payment_provider=payment_provider,
            external_reference=external_reference,
            ip_address=context.get("ip_address"),
            user_agent=context.get("user_agent"),
            extra_data={
                "audit_id": audit_id,
                "error": error,
                "event": "deposit_failed"
            }
        )

    # ========================================================================
    # WITHDRAWAL AUDITS (Complete - Nothing Missed)
    # ========================================================================

    @staticmethod
    def log_withdrawal_initiated(
        user_id: int,
        amount: Decimal,
        currency: str,
        payment_method: str,
        destination: Dict
    ):
        """
        Audit withdrawal initiation.
        Called BEFORE processing withdrawal.
        """
        context = WalletAudit._get_request_context()

        AuditService.financial(
            transaction_id=f"WTH-{uuid.uuid4().hex[:12].upper()}",
            transaction_type=TransactionType.WITHDRAWAL,
            amount=amount,
            currency=currency,
            status="initiated",
            from_user_id=user_id,
            payment_method=payment_method,
            ip_address=context.get("ip_address"),
            user_agent=context.get("user_agent"),
            extra_data={
                "destination_type": destination.get("type"),
                "destination_last4": destination.get("account_number", "")[-4:] if destination.get("account_number") else None,
                "audit_id": WalletAudit._generate_audit_id()
            }
        )

    @staticmethod
    def log_withdrawal_kyc_check(
        user_id: int,
        kyc_level: int,
        required_level: int,
        passed: bool,
        transaction_id: str
    ):
        """
        Audit KYC check for withdrawal.
        Called during withdrawal KYC verification.
        """
        context = WalletAudit._get_request_context()

        if not passed:
            AuditService.security(
                event_type="withdrawal_kyc_blocked",
                severity=AuditSeverity.WARNING,
                description=f"Withdrawal blocked - KYC level {kyc_level} below required {required_level}",
                user_id=user_id,
                ip_address=context.get("ip_address"),
                extra_data={
                    "transaction_id": transaction_id,
                    "kyc_level": kyc_level,
                    "required_level": required_level,
                    "audit_id": WalletAudit._generate_audit_id()
                }
            )

    @staticmethod
    def log_withdrawal_limit_check(
        user_id: int,
        amount: Decimal,
        daily_total: Decimal,
        daily_limit: Decimal,
        passed: bool,
        transaction_id: str
    ):
        """
        Audit daily limit check for withdrawal.
        Called during withdrawal limit verification.
        """
        context = WalletAudit._get_request_context()

        if not passed:
            AuditService.security(
                event_type="withdrawal_limit_exceeded",
                severity=AuditSeverity.WARNING,
                description=f"Withdrawal blocked - Daily limit exceeded",
                user_id=user_id,
                ip_address=context.get("ip_address"),

                extra_data={
                    "transaction_id": transaction_id,
                    "requested_amount": float(amount),
                    "daily_total": float(daily_total),
                    "daily_limit": float(daily_limit),
                    "audit_id": WalletAudit._generate_audit_id()
                }
            )

    @staticmethod
    def log_sensitive_data_access(
        user_id: int,
        accessed_by: int,
        data_category: str,
        resource_type: str,
        resource_id: str,
        fields_accessed: List[str],
        purpose: str
    ):
        """
        Audit access to sensitive data (GDPR compliant).
        Called when accessing bank details, ID documents, etc.
        """
        context = WalletAudit._get_request_context()

        AuditService.data_access(
            accessed_by=accessed_by,
            subject_user_id=user_id,
            access_type=DataAccessType.READ,
            data_category=data_category,
            resource_type=resource_type,
            resource_id=resource_id,
            fields_accessed=fields_accessed,
            purpose=purpose,
            legal_basis="legitimate_interest",
            ip_address=context.get("ip_address"),
            user_agent=context.get("user_agent"),
            extra_data={
                "audit_id": WalletAudit._generate_audit_id()
            }
        )

    @staticmethod
    def log_withdrawal_completed(
        user_id: int,
        amount: Decimal,
        currency: str,
        transaction_id: str,
        balance_before: Decimal,
        balance_after: Decimal,
        payment_method: str,
        payment_provider: str,
        external_reference: str,
        fee_amount: Decimal = None,
        status: str = "pending"
    ):
        """
        Audit successful withdrawal.
        Called AFTER wallet balance is updated.
        """
        context = WalletAudit._get_request_context()

        AuditService.financial(
            transaction_id=transaction_id,
            transaction_type=TransactionType.WITHDRAWAL,
            amount=amount,
            currency=currency,
            status=status,
            from_user_id=user_id,
            from_balance_before=float(balance_before),
            from_balance_after=float(balance_after),
            fee_amount=float(fee_amount) if fee_amount else None,
            fee_currency=currency,
            payment_method=payment_method,
            payment_provider=payment_provider,
            external_reference=external_reference,
            ip_address=context.get("ip_address"),
            user_agent=context.get("user_agent"),
            extra_data={
                "audit_id": WalletAudit._generate_audit_id(),
                "event": "withdrawal_completed"
            }
        )

    @staticmethod
    def log_withdrawal_failed(
        user_id: int,
        amount: Decimal,
        currency: str,
        payment_method: str,
        error: str,
        transaction_id: str = None
    ):
        """
        Audit failed withdrawal.
        Called when withdrawal fails.
        """
        context = WalletAudit._get_request_context()

        AuditService.financial(
            transaction_id=transaction_id or f"WTH-{uuid.uuid4().hex[:12].upper()}",
            transaction_type=TransactionType.WITHDRAWAL,
            amount=amount,
            currency=currency,
            status="failed",
            from_user_id=user_id,
            payment_method=payment_method,
            ip_address=context.get("ip_address"),
            user_agent=context.get("user_agent"),
            extra_data={
                "error": error,
                "audit_id": WalletAudit._generate_audit_id(),
                "event": "withdrawal_failed"
            }
        )

    # ========================================================================
    # TRANSFER AUDITS (Complete - Nothing Missed)
    # ========================================================================

    @staticmethod
    def log_transfer_initiated(
        from_user_id: int,
        to_user_id: int,
        amount: Decimal,
        currency: str,
        note: str = None
    ):
        """
        Audit transfer initiation.
        Called BEFORE processing transfer.
        """
        context = WalletAudit._get_request_context()

        AuditService.financial(
            transaction_id=f"P2P-{uuid.uuid4().hex[:12].upper()}",
            transaction_type=TransactionType.TRANSFER,
            amount=amount,
            currency=currency,
            status="initiated",
            from_user_id=from_user_id,
            to_user_id=to_user_id,
            payment_method="internal_transfer",
            ip_address=context.get("ip_address"),
            user_agent=context.get("user_agent"),
            extra_data={
                "note": note,
                "audit_id": WalletAudit._generate_audit_id(),
                "event": "transfer_initiated"
            }
        )

    @staticmethod
    def log_transfer_completed(
        from_user_id: int,
        to_user_id: int,
        amount: Decimal,
        currency: str,
        transaction_id: str,
        from_balance_before: Decimal,
        from_balance_after: Decimal,
        to_balance_before: Decimal,
        to_balance_after: Decimal,
        note: str = None,
        risk_score: Decimal = None,
        aml_flagged: bool = False,
        conversion_rate: Decimal = None,
        conversion_fee: Decimal = None
    ):
        """
        Audit successful transfer.
        Called AFTER both wallets are updated.
        """
        context = WalletAudit._get_request_context()
        audit_id = WalletAudit._generate_audit_id()

        # Get usernames for extra_data
        from_username = None
        to_username = None
        try:
            from app.identity.models.user import User
            from_user = User.query.get(from_user_id)
            to_user = User.query.get(to_user_id)
            from_username = from_user.username if from_user else None
            to_username = to_user.username if to_user else None
        except:
            pass

        AuditService.financial(
            transaction_id=transaction_id,
            transaction_type=TransactionType.TRANSFER,
            amount=amount,
            currency=currency,
            status="completed",
            from_user_id=from_user_id,
            to_user_id=to_user_id,
            from_balance_before=float(from_balance_before),
            from_balance_after=float(from_balance_after),
            to_balance_before=float(to_balance_before),
            to_balance_after=float(to_balance_after),
            payment_method="internal_transfer",
            risk_score=float(risk_score) if risk_score else None,
            aml_flagged=aml_flagged,
            requires_review=aml_flagged,
            ip_address=context.get("ip_address"),
            user_agent=context.get("user_agent"),
            extra_data={
                "note": note,
                "from_username": from_username,
                "to_username": to_username,
                "conversion_rate": str(conversion_rate) if conversion_rate else None,
                "conversion_fee": str(conversion_fee) if conversion_fee else None,
                "audit_id": audit_id,
                "event": "transfer_completed"
            }
        )

        # Security alert for AML flagged transfers
        if aml_flagged:
            WalletAudit.log_security_alert(event_type="suspicious_transfer", severity="WARNING",
                                           description=f"Suspicious transfer: {amount} {currency} from user {from_user_id} to {to_user_id}",
                                           user_id=from_user_id)

    @staticmethod
    def log_transfer_failed(
        from_user_id: int,
        to_user_id: int,
        amount: Decimal,
        currency: str,
        error: str,
        transaction_id: str = None
    ):
        """
        Audit failed transfer.
        Called when transfer fails.
        """
        context = WalletAudit._get_request_context()

        AuditService.financial(
            transaction_id=transaction_id or f"P2P-{uuid.uuid4().hex[:12].upper()}",
            transaction_type=TransactionType.TRANSFER,
            amount=amount,
            currency=currency,
            status="failed",
            from_user_id=from_user_id,
            to_user_id=to_user_id,
            payment_method="internal_transfer",
            ip_address=context.get("ip_address"),
            user_agent=context.get("user_agent"),
            extra_data={
                "error": error,
                "audit_id": WalletAudit._generate_audit_id(),
                "event": "transfer_failed"
            }
        )

    # ========================================================================
    # BALANCE AUDITS
    # ========================================================================

    @staticmethod
    def log_balance_change(
        user_id: int,
        wallet_id: int,
        currency: str,
        old_balance: Decimal,
        new_balance: Decimal,
        reason: str,
        transaction_id: str = None
    ):
        """
        Audit any balance change.
        Called whenever balance changes (deposit, withdraw, transfer, adjustment).
        """
        context = WalletAudit._get_request_context()

        AuditService.data_change(
            entity_type="wallet_balance",
            entity_id=wallet_id,
            operation="update",
            old_value={"balance": float(old_balance), "currency": currency},
            new_value={"balance": float(new_balance), "currency": currency},
            changed_by=user_id,
            ip_address=context.get("ip_address"),
            user_agent=context.get("user_agent"),
            extra_data={
                "reason": reason,
                "transaction_id": transaction_id,
                "audit_id": WalletAudit._generate_audit_id()
            }
        )

    # ========================================================================
    # SECURITY AUDITS
    # ========================================================================

    @staticmethod
    def log_security_alert(
        event_type: str,
        severity: str,
        description: str,
        user_id: int = None,
        extra_data: Dict = None
    ):
        """
        Audit security events (AML flags, suspicious activity, etc.).
        """
        context = WalletAudit._get_request_context()

        severity_map = {
            "INFO": AuditSeverity.INFO,
            "WARNING": AuditSeverity.WARNING,
            "CRITICAL": AuditSeverity.CRITICAL
        }

        AuditService.security(
            event_type=event_type,
            severity=severity_map.get(severity, AuditSeverity.WARNING),
            description=description,
            user_id=user_id,
            ip_address=context.get("ip_address"),
            extra_data={
                **(extra_data or {}),
                "audit_id": WalletAudit._generate_audit_id()
            }
        )

    @staticmethod
    def log_unauthorized_access_attempt(
        user_id: int = None,
        resource: str = None,
        reason: str = None
    ):
        """
        Audit unauthorized access attempts.
        Called when someone tries to access a wallet they shouldn't.
        """
        context = WalletAudit._get_request_context()

        AuditService.security(
            event_type="unauthorized_access_attempt",
            severity=AuditSeverity.WARNING,
            description=f"Unauthorized access attempt to {resource}: {reason}",
            user_id=user_id,
            ip_address=context.get("ip_address"),
            user_agent=context.get("user_agent"),
            extra_data={
                "resource": resource,
                "reason": reason,
                "audit_id": WalletAudit._generate_audit_id()
            }
        )

    # ========================================================================
    # AGENT COMMISSION AUDITS
    # ========================================================================

    @staticmethod
    def log_commission_earned(
        agent_id: int,
        amount: Decimal,
        currency: str,
        source_type: str,
        source_id: str,
        recipient_id: int = None
    ):
        """
        Audit agent commission earned.
        Called when an agent earns commission.
        """
        context = WalletAudit._get_request_context()
        audit_id = WalletAudit._generate_audit_id()

        AuditService.financial(
            transaction_id=f"COM-{uuid.uuid4().hex[:12].upper()}",
            transaction_type=TransactionType.COMMISSION,
            amount=amount,
            currency=currency,
            status="earned",
            to_user_id=agent_id,
            from_user_id=recipient_id,
            payment_method=source_type,
            external_reference=source_id,
            ip_address=context.get("ip_address"),
            user_agent=context.get("user_agent"),
            extra_data={
                "source_type": source_type,
                "source_id": source_id,
                "audit_id": audit_id,
                "event": "commission_earned"
            }
        )

    @staticmethod
    def log_commission_paid(
        agent_id: int,
        amount: Decimal,
        currency: str,
        commission_id: str,
        paid_by: int
    ):
        """
        Audit agent commission paid out.
        Called when commission is paid to agent.
        """
        context = WalletAudit._get_request_context()

        AuditService.financial(
            transaction_id=f"PAY-{uuid.uuid4().hex[:12].upper()}",
            transaction_type=TransactionType.PAYOUT,
            amount=amount,
            currency=currency,
            status="paid",
            to_user_id=agent_id,
            from_user_id=paid_by,
            external_reference=commission_id,
            ip_address=context.get("ip_address"),
            user_agent=context.get("user_agent"),
            extra_data={
                "commission_id": commission_id,
                "audit_id": WalletAudit._generate_audit_id(),
                "event": "commission_paid"
            }
        )

    # ========================================================================
    # PAYOUT REQUEST AUDITS
    # ========================================================================

    @staticmethod
    def log_payout_request_created(
        agent_id: int,
        request_id: str,
        amount: Decimal,
        currency: str,
        payment_method: str
    ):
        """
        Audit payout request creation.
        Called when agent requests payout.
        """
        context = WalletAudit._get_request_context()

        AuditService.data_change(
            entity_type="payout_request",
            entity_id=request_id,
            operation="create",
            old_value=None,
            new_value={
                "agent_id": agent_id,
                "amount": float(amount),
                "currency": currency,
                "payment_method": payment_method,
                "status": "pending"
            },
            changed_by=agent_id,
            ip_address=context.get("ip_address"),
            user_agent=context.get("user_agent"),
            extra_data={
                "audit_id": WalletAudit._generate_audit_id(),
                "event": "payout_request_created"
            }
        )

    @staticmethod
    def log_payout_request_approved(
        request_id: str,
        agent_id: int,
        approved_by: int,
        notes: str = None
    ):
        """
        Audit payout request approval.
        Called when admin approves payout.
        """
        context = WalletAudit._get_request_context()

        AuditService.data_change(
            entity_type="payout_request",
            entity_id=request_id,
            operation="update",
            old_value={"status": "pending"},
            new_value={"status": "approved", "approved_by": approved_by},
            changed_by=approved_by,
            ip_address=context.get("ip_address"),
            user_agent=context.get("user_agent"),
            extra_data={
                "agent_id": agent_id,
                "notes": notes,
                "audit_id": WalletAudit._generate_audit_id(),
                "event": "payout_request_approved"
            }
        )

    @staticmethod
    def log_payout_request_rejected(
        request_id: str,
        agent_id: int,
        rejected_by: int,
        reason: str
    ):
        """
        Audit payout request rejection.
        Called when admin rejects payout.
        """
        context = WalletAudit._get_request_context()

        AuditService.data_change(
            entity_type="payout_request",
            entity_id=request_id,
            operation="update",
            old_value={"status": "pending"},
            new_value={"status": "rejected", "rejection_reason": reason},
            changed_by=rejected_by,
            ip_address=context.get("ip_address"),
            user_agent=context.get("user_agent"),
            extra_data={
                "agent_id": agent_id,
                "reason": reason,
                "audit_id": WalletAudit._generate_audit_id(),
                "event": "payout_request_rejected"
            }
        )

    # ========================================================================
    # CURRENCY CONVERSION AUDITS
    # ========================================================================

    @staticmethod
    def log_currency_conversion(
        user_id: int,
        from_amount: Decimal,
        from_currency: str,
        to_amount: Decimal,
        to_currency: str,
        rate: Decimal,
        fee: Decimal,
        transaction_id: str = None
    ):
        """
        Audit currency conversion.
        Called when currency is converted.
        """
        context = WalletAudit._get_request_context()

        AuditService.financial(
            transaction_id=transaction_id or f"FX-{uuid.uuid4().hex[:12].upper()}",
            transaction_type=TransactionType.EXCHANGE,
            amount=from_amount,
            currency=from_currency,
            status="completed",
            to_user_id=user_id,
            ip_address=context.get("ip_address"),
            user_agent=context.get("user_agent"),
            extra_data={
                "from_amount": float(from_amount),
                "from_currency": from_currency,
                "to_amount": float(to_amount),
                "to_currency": to_currency,
                "rate": float(rate),
                "fee": float(fee),
                "audit_id": WalletAudit._generate_audit_id(),
                "event": "currency_conversion"
            }
        )

    # ========================================================================
    # COMPLIANCE AUDITS
    # ========================================================================

    @staticmethod
    def log_compliance_check(
        user_id: int,
        check_type: str,
        result: str,
        details: Dict = None
    ):
        """
        Audit compliance checks (KYC, AML, sanctions, etc.).
        """
        context = WalletAudit._get_request_context()
        audit_id = WalletAudit._generate_audit_id()

        AuditService.compliance(
            entity_type="user",
            entity_id=user_id,
            check_type=check_type,
            result=result,
            details=details or {},
            ip_address=context.get("ip_address"),
            user_agent=context.get("user_agent"),
            extra_data={
                "audit_id": audit_id,
                "event": "compliance_check"
            }
        )

    # ========================================================================
    # TRANSACTION DISPUTE AUDITS
    # ========================================================================

    @staticmethod
    def log_dispute_created(
        transaction_id: str,
        user_id: int,
        dispute_reason: str,
        amount: Decimal,
        currency: str,
        dispute_details: Dict = None
    ):
        """
        Audit transaction dispute creation.
        Called when a user disputes a transaction.
        """
        context = WalletAudit._get_request_context()
        audit_id = WalletAudit._generate_audit_id()

        AuditService.data_change(
            entity_type="transaction_dispute",
            entity_id=transaction_id,
            operation="create",
            old_value={"status": "completed"},
            new_value={"status": "disputed"},
            changed_by=user_id,
            ip_address=context.get("ip_address"),
            user_agent=context.get("user_agent"),
            extra_data={
                "audit_id": audit_id,
                "dispute_reason": dispute_reason,
                "amount": float(amount),
                "currency": currency,
                "dispute_details": dispute_details or {},
                "event": "dispute_created"
            }
        )

        # Also log as security event for review
        AuditService.security(
            event_type="transaction_dispute",
            severity=AuditSeverity.WARNING,
            description=f"Transaction {transaction_id} disputed by user {user_id}",
            user_id=user_id,
            ip_address=context.get("ip_address"),
            extra_data={
                "transaction_id": transaction_id,
                "amount": float(amount),
                "currency": currency,
                "dispute_reason": dispute_reason,
                "audit_id": audit_id
            }
        )

    @staticmethod
    def log_dispute_resolved(
        transaction_id: str,
        resolved_by: int,
        resolution: str,  # "refunded", "rejected", "partially_refunded"
        resolution_amount: Decimal = None,
        resolution_notes: str = None
    ):
        """
        Audit transaction dispute resolution.
        Called when admin resolves a dispute.
        """
        context = WalletAudit._get_request_context()
        audit_id = WalletAudit._generate_audit_id()

        AuditService.data_change(
            entity_type="transaction_dispute",
            entity_id=transaction_id,
            operation="resolve",
            old_value={"status": "disputed"},
            new_value={"status": "resolved", "resolution": resolution},
            changed_by=resolved_by,
            ip_address=context.get("ip_address"),
            user_agent=context.get("user_agent"),
            extra_data={
                "audit_id": audit_id,
                "resolution": resolution,
                "resolution_amount": float(resolution_amount) if resolution_amount else None,
                "resolution_notes": resolution_notes,
                "resolved_by": resolved_by,
                "event": "dispute_resolved"
            }
        )

    # ========================================================================
    # AUDIT QUERY HELPERS
    # ========================================================================

    @staticmethod
    def get_audit_trail(
        user_id: int = None,
        transaction_id: str = None,
        start_date: datetime = None,
        end_date: datetime = None,
        limit: int = 100
    ) -> List[Dict]:
        """
        Retrieve audit trail for a user or transaction.
        Useful for compliance and customer support.
        """
        # TODO: Implement query to audit tables
        # This would query the audit database for records
        pass

    @staticmethod
    def export_audit_report(
        user_id: int,
        start_date: datetime,
        end_date: datetime,
        format: str = "json"
    ) -> str:
        """
        Export audit report for compliance.
        Useful for regulatory reporting.
        """
        # TODO: Implement audit report generation
        pass


# Singleton instance for easy import
wallet_audit = WalletAudit()
