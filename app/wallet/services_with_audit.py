#later while in wallet modification ensure you first audit the initial set up for modification,
# app/wallet/services_with_audit.py
"""
Example: How to integrate comprehensive audit logging into wallet services

This shows proper audit logging for:
- Deposits (from external payment providers)
- Withdrawals (to bank accounts, mobile money)
- Peer-to-peer transfers
- Currency exchanges
- Refunds
"""

from decimal import Decimal
from datetime import datetime
from typing import Optional
import uuid

from app.extensions import db
from app.audit.comprehensive_audit import (
    AuditService,
    TransactionType,
    APICallStatus,
    AuditSeverity,
    DataAccessType
)
from app.identity.models.user import User
from flask import request


# ============================================================================
# EXAMPLE 1: Wallet Deposit with External Payment Provider
# ============================================================================

def process_deposit(
        user_id: int,
        amount: Decimal,
        currency: str,
        payment_method: str,  # "mobile_money", "bank_transfer", "card"
        payment_provider: str,  # "MTN", "Airtel", "Flutterwave"
        external_reference: str  # Provider's transaction ID
) -> dict:
    """
    Process a deposit from external payment provider.

    Audit requirements:
    1. Log API call to payment provider
    2. Log financial transaction
    3. Log balance changes
    4. Flag suspicious patterns (AML)
    """

    transaction_id = f"DEP-{uuid.uuid4().hex[:12].upper()}"
    request_id = f"REQ-{uuid.uuid4().hex[:12].upper()}"

    try:
        # 1. Call payment provider API to verify payment
        api_response = verify_payment_with_provider(
            payment_provider,
            external_reference
        )

        # 2. Log the API call (CRITICAL for reconciliation)
        AuditService.api_call(
            service_name=payment_provider.lower(),
            endpoint=f"/api/verify/{external_reference}",
            method="GET",
            request_id=request_id,
            correlation_id=transaction_id,
            status=APICallStatus.SUCCESS if api_response['status'] == 'success' else APICallStatus.FAILURE,
            response_status=200,
            response_time_ms=api_response.get('response_time_ms'),
            initiated_by=user_id,
            request_payload={"reference": external_reference},
            response_body=api_response
        )

        if api_response['status'] != 'success':
            raise ValueError("Payment verification failed")

        # 3. Get user's wallet and current balance
        user = User.query.get(user_id)
        wallet = get_or_create_wallet(user, currency)
        balance_before = wallet.balance

        # 4. Credit wallet
        wallet.balance += amount
        balance_after = wallet.balance

        # 5. Calculate risk score (simple example)
        risk_score = calculate_deposit_risk(user, amount, payment_method)
        aml_flagged = risk_score > 70  # Flag high-risk transactions

        # 6. Log financial transaction (IMMUTABLE RECORD)
        AuditService.financial(
            transaction_id=transaction_id,
            transaction_type=TransactionType.DEPOSIT,
            amount=amount,
            currency=currency,
            status="completed",
            to_user_id=user_id,
            to_balance_before=balance_before,
            to_balance_after=balance_after,
            payment_method=payment_method,
            payment_provider=payment_provider,
            external_reference=external_reference,
            risk_score=risk_score,
            aml_flagged=aml_flagged,
            requires_review=aml_flagged,
            ip_address=request.remote_addr if request else None,
            user_agent=request.user_agent.string if request else None,
            metadata={
                "api_request_id": request_id,
                "verification_response": api_response
            }
        )

        # 7. If flagged, create security alert
        if aml_flagged:
            AuditService.security(
                event_type="high_risk_deposit",
                severity=AuditSeverity.WARNING,
                description=f"High-risk deposit: {amount} {currency} via {payment_provider}",
                user_id=user_id,
                ip_address=request.remote_addr if request else None,
                metadata={
                    "transaction_id": transaction_id,
                    "risk_score": float(risk_score),
                    "amount": float(amount),
                    "currency": currency
                }
            )

        db.session.commit()

        return {
            "success": True,
            "transaction_id": transaction_id,
            "new_balance": float(balance_after),
            "requires_review": aml_flagged
        }

    except Exception as e:
        db.session.rollback()

        # Log failed transaction
        AuditService.financial(
            transaction_id=transaction_id,
            transaction_type=TransactionType.DEPOSIT,
            amount=amount,
            currency=currency,
            status="failed",
            to_user_id=user_id,
            payment_method=payment_method,
            payment_provider=payment_provider,
            external_reference=external_reference,
            metadata={
                "error": str(e),
                "api_request_id": request_id
            }
        )

        raise


# ============================================================================
# EXAMPLE 2: Withdrawal to Bank Account (with KYC check)
# ============================================================================

def process_withdrawal(
        user_id: int,
        amount: Decimal,
        currency: str,
        bank_account: dict,  # {account_number, bank_name, account_name}
        payment_provider: str = "flutterwave"
) -> dict:
    """
    Process withdrawal to user's bank account.

    Audit requirements:
    1. Log KYC check (compliance)
    2. Log transaction limit check
    3. Log API call to payment provider
    4. Log financial transaction
    5. Log sensitive data access (bank details)
    """

    transaction_id = f"WTH-{uuid.uuid4().hex[:12].upper()}"

    user = User.query.get(user_id)
    wallet = get_or_create_wallet(user, currency)

    # 1. Check KYC level (COMPLIANCE REQUIREMENT)
    from app.compliance.logger import ComplianceLogger

    if user.kyc_level < 2:
        ComplianceLogger.log_decision(
            entity_id=user_id,
            entity_type="individual",
            operation="wallet_withdrawal",
            decision="blocked",
            requirement_key="kyc_level_2_required",
            compliance_level=user.kyc_level,
            risk_tier="high",
            context={
                "transaction_id": transaction_id,
                "requested_amount": float(amount),
                "currency": currency
            }
        )
        raise ValueError("KYC Level 2 required for withdrawals")

    # 2. Check daily limit
    daily_total = get_daily_withdrawal_total(user_id, currency)
    daily_limit = get_withdrawal_limit(user.kyc_level, currency)

    if daily_total + amount > daily_limit:
        ComplianceLogger.log_decision(
            entity_id=user_id,
            entity_type="individual",
            operation="wallet_withdrawal",
            decision="blocked",
            requirement_key="daily_withdrawal_limit",
            compliance_level=user.kyc_level,
            context={
                "transaction_id": transaction_id,
                "requested_amount": float(amount),
                "daily_total": float(daily_total),
                "daily_limit": float(daily_limit),
                "currency": currency
            }
        )
        raise ValueError(f"Daily withdrawal limit exceeded ({daily_limit} {currency})")

    # 3. Log access to sensitive bank details (GDPR)
    AuditService.data_access(
        accessed_by=user_id,
        subject_user_id=user_id,
        access_type=DataAccessType.READ,
        data_category="bank_account_details",
        resource_type="bank_account",
        resource_id=bank_account.get('id'),
        fields_accessed=["account_number", "bank_name", "account_name"],
        purpose="withdrawal_processing",
        legal_basis="contract"  # Processing for contract performance
    )

    # 4. Check sufficient balance
    if wallet.balance < amount:
        raise ValueError("Insufficient balance")

    balance_before = wallet.balance

    try:
        # 5. Call payment provider API
        request_id = f"REQ-{uuid.uuid4().hex[:12].upper()}"

        api_response = initiate_bank_transfer(
            payment_provider=payment_provider,
            amount=amount,
            currency=currency,
            bank_account=bank_account,
            reference=transaction_id
        )

        # 6. Log API call
        AuditService.api_call(
            service_name=payment_provider,
            endpoint="/api/transfers/bank",
            method="POST",
            request_id=request_id,
            correlation_id=transaction_id,
            status=APICallStatus.SUCCESS if api_response['status'] == 'success' else APICallStatus.FAILURE,
            response_status=200,
            response_time_ms=api_response.get('response_time_ms'),
            initiated_by=user_id,
            request_payload={
                "amount": float(amount),
                "currency": currency,
                "bank_name": bank_account['bank_name'],
                # DO NOT log full account number (PCI/PII)
                "account_number_last4": bank_account['account_number'][-4:]
            },
            response_body=api_response
        )

        # 7. Debit wallet
        wallet.balance -= amount
        balance_after = wallet.balance

        # 8. Log financial transaction
        fee_amount = calculate_withdrawal_fee(amount)

        AuditService.financial(
            transaction_id=transaction_id,
            transaction_type=TransactionType.WITHDRAWAL,
            amount=amount,
            currency=currency,
            status="pending",  # Will be updated when confirmed
            from_user_id=user_id,
            from_balance_before=balance_before,
            from_balance_after=balance_after,
            fee_amount=fee_amount,
            fee_currency=currency,
            payment_method="bank_transfer",
            payment_provider=payment_provider,
            external_reference=api_response.get('provider_reference'),
            ip_address=request.remote_addr if request else None,
            user_agent=request.user_agent.string if request else None,
            metadata={
                "api_request_id": request_id,
                "bank_name": bank_account['bank_name'],
                "account_name": bank_account['account_name']
            }
        )

        # 9. Log compliance approval
        ComplianceLogger.log_decision(
            entity_id=user_id,
            entity_type="individual",
            operation="wallet_withdrawal",
            decision="allowed",
            compliance_level=user.kyc_level,
            context={
                "transaction_id": transaction_id,
                "amount": float(amount),
                "currency": currency,
                "new_daily_total": float(daily_total + amount)
            }
        )

        db.session.commit()

        return {
            "success": True,
            "transaction_id": transaction_id,
            "status": "pending",
            "provider_reference": api_response.get('provider_reference'),
            "estimated_arrival": "1-3 business days"
        }

    except Exception as e:
        db.session.rollback()

        # Log failed transaction
        AuditService.financial(
            transaction_id=transaction_id,
            transaction_type=TransactionType.WITHDRAWAL,
            amount=amount,
            currency=currency,
            status="failed",
            from_user_id=user_id,
            payment_method="bank_transfer",
            payment_provider=payment_provider,
            metadata={
                "error": str(e)
            }
        )

        raise


# ============================================================================
# EXAMPLE 3: Peer-to-Peer Transfer
# ============================================================================

def process_p2p_transfer(
        from_user_id: int,
        to_user_id: int,
        amount: Decimal,
        currency: str,
        note: Optional[str] = None
) -> dict:
    """
    Transfer money between two users.

    Audit requirements:
    1. Log both sender and receiver balance changes
    2. Check for suspicious patterns
    3. Immutable audit trail
    """

    transaction_id = f"P2P-{uuid.uuid4().hex[:12].upper()}"

    from_user = User.query.get(from_user_id)
    to_user = User.query.get(to_user_id)

    from_wallet = get_or_create_wallet(from_user, currency)
    to_wallet = get_or_create_wallet(to_user, currency)

    if from_wallet.balance < amount:
        raise ValueError("Insufficient balance")

    from_balance_before = from_wallet.balance
    to_balance_before = to_wallet.balance

    # Execute transfer
    from_wallet.balance -= amount
    to_wallet.balance += amount

    from_balance_after = from_wallet.balance
    to_balance_after = to_wallet.balance

    # Calculate risk
    risk_score = calculate_p2p_risk(from_user, to_user, amount)
    aml_flagged = risk_score > 80

    # Log complete financial transaction
    AuditService.financial(
        transaction_id=transaction_id,
        transaction_type=TransactionType.TRANSFER,
        amount=amount,
        currency=currency,
        status="completed",
        from_user_id=from_user_id,
        to_user_id=to_user_id,
        from_balance_before=from_balance_before,
        from_balance_after=from_balance_after,
        to_balance_before=to_balance_before,
        to_balance_after=to_balance_after,
        payment_method="internal_transfer",
        risk_score=risk_score,
        aml_flagged=aml_flagged,
        requires_review=aml_flagged,
        ip_address=request.remote_addr if request else None,
        user_agent=request.user_agent.string if request else None,
        metadata={
            "note": note,
            "from_username": from_user.username,
            "to_username": to_user.username
        }
    )

    if aml_flagged:
        AuditService.security(
            event_type="suspicious_p2p_transfer",
            severity=AuditSeverity.WARNING,
            description=f"Suspicious P2P transfer: {amount} {currency}",
            user_id=from_user_id,
            metadata={
                "transaction_id": transaction_id,
                "to_user_id": to_user_id,
                "risk_score": float(risk_score)
            }
        )

    db.session.commit()

    return {
        "success": True,
        "transaction_id": transaction_id,
        "new_balance": float(from_balance_after)
    }


# ============================================================================
# Helper Functions (Placeholders)
# ============================================================================

def verify_payment_with_provider(provider: str, reference: str) -> dict:
    """Placeholder: Call payment provider API"""
    return {"status": "success", "response_time_ms": 150}


def initiate_bank_transfer(payment_provider: str, amount: Decimal, currency: str,
                           bank_account: dict, reference: str) -> dict:
    """Placeholder: Initiate bank transfer via provider"""
    return {
        "status": "success",
        "provider_reference": f"PROV-{uuid.uuid4().hex[:8].upper()}",
        "response_time_ms": 320
    }


def get_or_create_wallet(user, currency: str):
    """Placeholder: Get user's wallet for currency"""
    pass


def calculate_deposit_risk(user, amount: Decimal, payment_method: str) -> Decimal:
    """
    Calculate risk score for deposit.

    Factors:
    - First-time user
    - Large amount
    - New payment method
    - Unusual time/location
    """
    return Decimal("35.5")  # Placeholder


def calculate_p2p_risk(from_user, to_user, amount: Decimal) -> Decimal:
    """Calculate risk for P2P transfer"""
    return Decimal("25.0")  # Placeholder


def get_daily_withdrawal_total(user_id: int, currency: str) -> Decimal:
    """Get total withdrawals today"""
    return Decimal("0")  # Placeholder


def get_withdrawal_limit(kyc_level: int, currency: str) -> Decimal:
    """Get daily withdrawal limit based on KYC level"""
    limits = {
        0: Decimal("100"),
        1: Decimal("500"),
        2: Decimal("5000"),
        3: Decimal("50000")
    }
    return limits.get(kyc_level, Decimal("0"))


def calculate_withdrawal_fee(amount: Decimal) -> Decimal:
    """Calculate withdrawal fee"""
    return amount * Decimal("0.02")  # 2% fee
