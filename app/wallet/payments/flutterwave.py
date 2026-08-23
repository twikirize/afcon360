# app/wallet/payments/flutterwave.py - CORRECTED VERSION

import requests
import uuid
from decimal import Decimal
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from flask import current_app, request

from app.audit.comprehensive_audit import AuditService, TransactionType, APICallStatus, AuditSeverity
from app.wallet.services.wallet_service import WalletService


class FlutterwaveService:
    """
    Flutterwave payment integration with CORRECT audit ordering.

    FLOW:
    1. Create pending audit record
    2. Call Flutterwave API
    3. If success → call WalletService.deposit()
    4. Update audit record with completion
    5. If anything fails → update audit as failed
    """

    def __init__(self):
        self.wallet_service = WalletService()

    def process_deposit(self, user_id: int, amount: Decimal, currency: str,
                        payment_method: str, redirect_url: str,
                        idempotency_key: Optional[str] = None) -> Dict:
        """
        Process deposit with CORRECT ordering.
        """
        from flask import request

        # STEP 1: Get balance snapshot BEFORE anything
        try:
            current_balance = self.wallet_service.get_balance(user_id)
            balance_before = Decimal(current_balance.get('balance_home', '0'))
        except Exception as e:
            current_app.logger.error(f"Cannot get balance: {e}")
            balance_before = Decimal("0")

        # STEP 2: Create audit transaction ID
        audit_transaction_id = f"DEP-{uuid.uuid4().hex[:12].upper()}"
        provider_request_id = f"FW-{uuid.uuid4().hex[:12].upper()}"

        # STEP 3: Create PENDING audit record BEFORE calling provider
        try:
            AuditService.financial(
                transaction_id=audit_transaction_id,
                transaction_type=TransactionType.DEPOSIT,
                amount=amount,
                currency=currency,
                status="pending",
                to_user_id=user_id,
                to_balance_before=float(balance_before),
                payment_method=payment_method,
                payment_provider="flutterwave",
                ip_address=request.remote_addr if request else None,
                user_agent=request.user_agent.string if request else None,
                metadata={
                    "idempotency_key": idempotency_key,
                    "provider_request_id": provider_request_id,
                    "stage": "calling_provider"
                }
            )
        except Exception as e:
            current_app.logger.error(f"Audit create failed: {e}")

        # STEP 4: Call Flutterwave API
        provider_response = None
        provider_success = False
        provider_error = None
        provider_reference = None
        start_time = datetime.now(timezone.utc)

        try:
            url = f"{current_app.config['FLUTTERWAVE_BASE_URL']}/payments"
            payload = {
                "tx_ref": idempotency_key or audit_transaction_id,
                "amount": float(amount),
                "currency": currency,
                "payment_options": payment_method,
                "redirect_url": redirect_url,
                "customer": {"id": str(user_id)}
            }
            headers = {
                "Authorization": f"Bearer {current_app.config['FLUTTERWAVE_SECRET_KEY']}",
                "Content-Type": "application/json"
            }

            response = requests.post(url, json=payload, headers=headers)
            provider_response = response.json()
            response_time_ms = int((datetime.now(timezone.utc) - start_time).total_seconds() * 1000)

            # Check if successful
            if response.status_code in [200, 201] and provider_response.get('status') == 'success':
                provider_success = True
                provider_reference = provider_response.get('data', {}).get('reference')
            else:
                provider_error = provider_response.get('message', 'Flutterwave error')

        except Exception as e:
            provider_error = str(e)
            response_time_ms = int((datetime.now(timezone.utc) - start_time).total_seconds() * 1000)
            current_app.logger.error(f"Flutterwave API call failed: {e}")

        # STEP 5: Log API call for audit
        try:
            AuditService.api_call(
                service_name="flutterwave",
                endpoint="/payments",
                method="POST",
                request_id=provider_request_id,
                correlation_id=audit_transaction_id,
                status=APICallStatus.SUCCESS if provider_success else APICallStatus.FAILURE,
                response_status=response.status_code if 'response' in locals() else None,
                response_time_ms=response_time_ms,
                initiated_by=user_id,
                request_payload={"amount": float(amount), "currency": currency},
                response_body=provider_response,
                error_message=provider_error
            )
        except Exception as e:
            current_app.logger.error(f"API audit failed: {e}")

        # STEP 6: If provider failed, update audit and return
        if not provider_success:
            try:
                AuditService.financial(
                    transaction_id=audit_transaction_id,
                    transaction_type=TransactionType.DEPOSIT,
                    amount=amount,
                    currency=currency,
                    status="failed",
                    to_user_id=user_id,
                    payment_method=payment_method,
                    payment_provider="flutterwave",
                    metadata={"error": provider_error, "stage": "provider_failed"}
                )
            except Exception:
                pass

            return {
                "status": "failed",
                "transaction_id": audit_transaction_id,
                "error": provider_error,
                "requires_retry": True
            }

        # STEP 7: Provider succeeded - NOW update wallet balance
        try:
            deposit_result = self.wallet_service.deposit(
                user_id=user_id,
                amount=amount,
                currency=currency,
                idempotency_key=idempotency_key or audit_transaction_id,
                metadata={
                    "payment_provider": "flutterwave",
                    "payment_method": payment_method,
                    "provider_reference": provider_reference,
                    "audit_transaction_id": audit_transaction_id
                }
            )

            # STEP 8: Update audit with SUCCESS
            new_balance = self.wallet_service.get_balance(user_id)
            balance_after = Decimal(new_balance.get('balance_home', '0'))

            try:
                AuditService.financial(
                    transaction_id=audit_transaction_id,
                    transaction_type=TransactionType.DEPOSIT,
                    amount=amount,
                    currency=currency,
                    status="completed",
                    to_user_id=user_id,
                    to_balance_before=float(balance_before),
                    to_balance_after=float(balance_after),
                    payment_method=payment_method,
                    payment_provider="flutterwave",
                    external_reference=provider_reference,
                    metadata={
                        "idempotency_key": idempotency_key,
                        "provider_request_id": provider_request_id,
                        "settled_amount": deposit_result.get('settled_amount'),
                    }
                )
            except Exception as e:
                current_app.logger.error(f"Audit update failed: {e}")

            return {
                "status": "success",
                "transaction_id": deposit_result.get('transaction_id'),
                "audit_id": audit_transaction_id,
                "provider_reference": provider_reference,
                "amount": str(amount),
                "currency": currency,
                "new_balance": str(balance_after)
            }

        except Exception as e:
            # STEP 9: CRITICAL - Provider took money but wallet update failed
            current_app.logger.critical(
                f"CRITICAL: Flutterwave charged user {user_id} but deposit failed. "
                f"Transaction: {audit_transaction_id}. Provider ref: {provider_reference}. Error: {e}"
            )

            try:
                AuditService.financial(
                    transaction_id=audit_transaction_id,
                    transaction_type=TransactionType.DEPOSIT,
                    amount=amount,
                    currency=currency,
                    status="failed",
                    to_user_id=user_id,
                    payment_method=payment_method,
                    payment_provider="flutterwave",
                    external_reference=provider_reference,
                    metadata={
                        "error": str(e),
                        "stage": "wallet_update_failed",
                        "requires_manual_reconciliation": True
                    }
                )

                AuditService.security(
                    event_type="deposit_reconciliation_required",
                    severity=AuditSeverity.CRITICAL,
                    description=f"Flutterwave charged but wallet not credited",
                    user_id=user_id,
                    metadata={
                        "transaction_id": audit_transaction_id,
                        "provider_reference": provider_reference,
                        "amount": float(amount)
                    }
                )
            except Exception:
                pass

            raise

    def initiate_deposit(self, *, user_id: int, account_id: str, amount: Decimal,
                         currency: str, payment_method: str, redirect_url: str,
                         idempotency_key: Optional[str] = None) -> Dict:
        """Initiate an async Flutterwave deposit (redirect checkout) WITHOUT crediting.

        Creates a pending audit record, opens a Flutterwave checkout session, stores
        a pending deposit intent, and returns the redirect URL. The wallet ledger is
        credited only when Flutterwave confirms (see verify_and_credit), so balances
        are never inflated by abandoned checkouts.
        """
        from flask import request
        from app.wallet.services.deposit_intent import (
            save_deposit_intent, generate_deposit_reference
        )

        audit_transaction_id = f"DEP-{uuid.uuid4().hex[:12].upper()}"
        reference = idempotency_key or generate_deposit_reference("FW")
        provider_request_id = f"FW-{uuid.uuid4().hex[:12].upper()}"

        try:
            current_balance = self.wallet_service.get_balance(user_id)
            balance_before = Decimal(current_balance.get('balance_home', '0'))
        except Exception as e:
            current_app.logger.error(f"Cannot get balance: {e}")
            balance_before = Decimal("0")

        try:
            AuditService.financial(
                transaction_id=audit_transaction_id,
                transaction_type=TransactionType.DEPOSIT,
                amount=amount,
                currency=currency,
                status="pending",
                to_user_id=user_id,
                to_balance_before=float(balance_before),
                payment_method=payment_method,
                payment_provider="flutterwave",
                ip_address=request.remote_addr if request else None,
                user_agent=request.user_agent.string if request else None,
                metadata={
                    "idempotency_key": reference,
                    "provider_request_id": provider_request_id,
                    "stage": "initiating_checkout"
                }
            )
        except Exception as e:
            current_app.logger.error(f"Audit create failed: {e}")

        try:
            url = f"{current_app.config['FLUTTERWAVE_BASE_URL']}/payments"
            payload = {
                "tx_ref": reference,
                "amount": float(amount),
                "currency": currency,
                "payment_options": payment_method,
                "redirect_url": redirect_url,
                "customer": {
                    "id": str(user_id),
                    "email": (request.form.get('email') if request else None) or "",
                },
                "meta": {"source": "flutterwave", "account_id": str(account_id)}
            }
            headers = {
                "Authorization": f"Bearer {current_app.config['FLUTTERWAVE_SECRET_KEY']}",
                "Content-Type": "application/json"
            }
            response = requests.post(url, json=payload, headers=headers)
            provider_response = response.json()

            if response.status_code in [200, 201] and provider_response.get('status') == 'success':
                authorization_url = (provider_response.get('data') or {}).get('link')
                provider_reference = (provider_response.get('data') or {}).get('reference')

                save_deposit_intent(reference, {
                    'account_id': str(account_id),
                    'user_id': int(user_id),
                    'amount': str(amount),
                    'currency': currency,
                    'source': 'flutterwave',
                    'payment_method': payment_method,
                    'reference': reference,
                    'provider_request_id': provider_request_id,
                    'provider_reference': provider_reference,
                    'audit_transaction_id': audit_transaction_id,
                    'status': 'pending',
                })

                return {
                    'success': True,
                    'status': 'pending',
                    'reference': reference,
                    'authorization_url': authorization_url,
                    'provider_reference': provider_reference,
                    'audit_transaction_id': audit_transaction_id,
                    'message': 'Redirecting to Flutterwave to complete payment.'
                }
            else:
                error = provider_response.get('message', 'Flutterwave error')
                try:
                    AuditService.financial(
                        transaction_id=audit_transaction_id,
                        transaction_type=TransactionType.DEPOSIT,
                        amount=amount,
                        currency=currency,
                        status="failed",
                        to_user_id=user_id,
                        payment_method=payment_method,
                        payment_provider="flutterwave",
                        metadata={"error": error, "stage": "provider_failed"}
                    )
                except Exception:
                    pass
                return {'success': False, 'status': 'failed', 'error': error}

        except Exception as e:
            current_app.logger.error(f"Flutterwave initiate failed: {e}")
            return {
                'success': False, 'status': 'failed', 'error': str(e),
                'audit_transaction_id': audit_transaction_id
            }

    def verify_and_credit(self, reference: str) -> Dict:
        """Verify a Flutterwave transaction and credit the wallet ledger.

        Called by the Flutterwave callback/webhook. Resolves the pending deposit
        intent, verifies the transaction with Flutterwave, and credits the ledger
        (system-initiated). Idempotent: a consumed intent can only be credited once.
        """
        from app.wallet.services.deposit_intent import (
            consume_deposit_intent, mark_deposit_intent_status
        )

        try:
            intent = consume_deposit_intent(reference)
            if not intent:
                return {'success': False, 'error': 'Unknown or expired deposit reference'}

            url = (
                f"{current_app.config['FLUTTERWAVE_BASE_URL']}"
                f"/transactions/verify_by_reference?tx_ref={reference}"
            )
            headers = {
                "Authorization": f"Bearer {current_app.config['FLUTTERWAVE_SECRET_KEY']}"
            }
            response = requests.get(url, headers=headers)
            data = response.json()
            status = (data.get('data') or {}).get('status')

            if status != 'successful':
                mark_deposit_intent_status(reference, 'failed')
                return {'success': False, 'error': f'Flutterwave status: {status}'}

            user_id = intent['user_id']
            amount = Decimal(str(intent['amount']))
            currency = intent['currency']

            current_balance = self.wallet_service.get_balance(user_id)
            balance_before = Decimal(current_balance.get('balance_home', '0'))

            deposit_result = self.wallet_service.deposit(
                account_id=str(intent['account_id']),
                amount=amount,
                currency=currency,
                client_request_id=reference,
                system_initiated=True,
                payment_provider="flutterwave",
                payment_method=intent.get('payment_method', 'card'),
                external_reference=(data.get('data') or {}).get('id'),
                metadata={
                    "source": "flutterwave",
                    "provider_reference": intent.get('provider_reference'),
                    "flutterwave_status": status,
                    "audit_transaction_id": intent.get('audit_transaction_id'),
                }
            )

            mark_deposit_intent_status(reference, 'completed')

            if deposit_result.get('status') == 'success':
                try:
                    AuditService.financial(
                        transaction_id=intent.get('audit_transaction_id'),
                        transaction_type=TransactionType.DEPOSIT,
                        amount=amount,
                        currency=currency,
                        status="completed",
                        to_user_id=user_id,
                        to_balance_before=float(balance_before),
                        payment_method=intent.get('payment_method', 'card'),
                        payment_provider="flutterwave",
                        api_call_status=APICallStatus.SUCCESS,
                        metadata={"stage": "webhook_processed"}
                    )
                except Exception as e:
                    current_app.logger.error(f"Audit update failed: {e}")

                return {
                    'success': True,
                    'reference': reference,
                    'account_id': str(intent['account_id'])
                }

            return {
                'success': False,
                'error': 'Failed to deposit to wallet',
                'detail': deposit_result
            }

        except Exception as e:
            current_app.logger.error(f"Flutterwave verify error: {e}")
            return {'success': False, 'error': str(e)}
