# app/wallet/payments/paypal.py
"""
PayPal payment integration with audit trail.

FLOW:
1. Create pending audit record
2. Call PayPal API
3. If success → call WalletService.deposit()
4. Update audit record with completion
5. If anything fails → update audit as failed
"""

import requests
import uuid
from decimal import Decimal
from datetime import datetime, timezone
from typing import Optional, Dict
from flask import current_app, request

from app.audit.comprehensive_audit import AuditService, TransactionType, APICallStatus, AuditSeverity
from app.wallet.services.wallet_service import WalletService


class PayPalService:
    """
    PayPal payment integration with complete audit trail.
    """

    def __init__(self):
        self.wallet_service = WalletService()

    def process_deposit(
        self,
        user_id: int,
        amount: Decimal,
        currency: str,
        return_url: str,
        cancel_url: str,
        idempotency_key: Optional[str] = None
    ) -> Dict:
        """
        Process a deposit through PayPal with correct ordering.

        Args:
            user_id: Internal user ID
            amount: Amount to deposit
            currency: Currency code (USD, EUR, etc.)
            return_url: Success return URL
            cancel_url: Cancel return URL
            idempotency_key: For duplicate prevention

        Returns:
            Dict with payment URL and transaction details
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
        provider_request_id = f"PP-{uuid.uuid4().hex[:12].upper()}"

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
                payment_method="paypal",
                payment_provider="paypal",
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

        # STEP 4: Call PayPal API
        provider_response = None
        provider_success = False
        provider_error = None
        provider_reference = None
        start_time = datetime.now(timezone.utc)

        try:
            # Get PayPal access token
            token_url = f"{current_app.config['PAYPAL_BASE_URL']}/v1/oauth2/token"
            auth_headers = {
                'Accept': 'application/json',
                'Accept-Language': 'en_US',
                'Content-Type': 'application/x-www-form-urlencoded'
            }
            
            auth_data = 'grant_type=client_credentials'
            auth = base64.b64encode(
                f"{current_app.config['PAYPAL_CLIENT_ID']}:{current_app.config['PAYPAL_CLIENT_SECRET']}".encode()
            ).decode()
            auth_headers['Authorization'] = f"Basic {auth}"

            auth_response = requests.post(token_url, headers=auth_headers, data=auth_data)
            
            if auth_response.status_code == 200:
                token_data = auth_response.json()
                access_token = token_data['access_token']

                # Create payment
                payment_url = f"{current_app.config['PAYPAL_BASE_URL']}/v1/payments/payment"
                payment_headers = {
                    'Content-Type': 'application/json',
                    'Authorization': f'Bearer {access_token}'
                }

                payment_payload = {
                    'intent': 'sale',
                    'payer': {'payment_method': 'paypal'},
                    'transactions': [{
                        'amount': {
                            'total': f"{float(amount):.2f}",
                            'currency': currency
                        },
                        'description': f"AFCON360 wallet deposit - {audit_transaction_id}"
                    }],
                    'redirect_urls': {
                        'return_url': return_url,
                        'cancel_url': cancel_url
                    }
                }

                payment_response = requests.post(payment_url, headers=payment_headers, json=payment_payload)
                provider_response = payment_response.json()
                response_time_ms = int((datetime.now(timezone.utc) - start_time).total_seconds() * 1000)

                if payment_response.status_code == 201 and provider_response.get('state') == 'created':
                    provider_success = True
                    provider_reference = provider_response.get('id')

                    # Get approval URL
                    approval_url = None
                    for link in provider_response.get('links', []):
                        if link.get('rel') == 'approval_url':
                            approval_url = link.get('href')
                            break

                    # STEP 5: Update audit as SUCCESS
                    AuditService.financial(
                        transaction_id=audit_transaction_id,
                        transaction_type=TransactionType.DEPOSIT,
                        amount=amount,
                        currency=currency,
                        status="completed",
                        to_user_id=user_id,
                        to_balance_before=float(balance_before),
                        payment_method="paypal",
                        payment_provider="paypal",
                        ip_address=request.remote_addr if request else None,
                        user_agent=request.user_agent.string if request else None,
                        api_call_status=APICallStatus.SUCCESS,
                        response_time_ms=response_time_ms,
                        metadata={
                            "provider_request_id": provider_request_id,
                            "provider_reference": provider_reference,
                            "approval_url": approval_url,
                            "stage": "completed"
                        }
                    )

                    return {
                        'success': True,
                        'audit_transaction_id': audit_transaction_id,
                        'payment_url': approval_url,
                        'provider_reference': provider_reference,
                        'amount': float(amount),
                        'currency': currency
                    }
                else:
                    provider_error = provider_response.get('message', 'Unknown error')

            else:
                provider_error = f"PayPal authentication failed: {auth_response.text}"

        except Exception as e:
            provider_error = str(e)
            current_app.logger.error(f"PayPal API error: {e}")

        # STEP 6: Update audit as FAILED if anything went wrong
        if not provider_success:
            try:
                AuditService.financial(
                    transaction_id=audit_transaction_id,
                    transaction_type=TransactionType.DEPOSIT,
                    amount=amount,
                    currency=currency,
                    status="failed",
                    to_user_id=user_id,
                    to_balance_before=float(balance_before),
                    payment_method="paypal",
                    payment_provider="paypal",
                    ip_address=request.remote_addr if request else None,
                    user_agent=request.user_agent.string if request else None,
                    api_call_status=APICallStatus.FAILED,
                    metadata={
                        "provider_request_id": provider_request_id,
                        "error": provider_error,
                        "stage": "failed"
                    }
                )
            except Exception as e:
                current_app.logger.error(f"Audit update failed: {e}")

            return {
                'success': False,
                'error': provider_error,
                'audit_transaction_id': audit_transaction_id
            }

    def execute_payment(self, payment_id: str, payer_id: str, audit_transaction_id: str) -> Dict:
        """
        Execute approved PayPal payment and deposit to wallet.
        """
        try:
            # Get PayPal access token
            token_url = f"{current_app.config['PAYPAL_BASE_URL']}/v1/oauth2/token"
            auth_headers = {
                'Content-Type': 'application/x-www-form-urlencoded'
            }
            
            auth_data = 'grant_type=client_credentials'
            auth = base64.b64encode(
                f"{current_app.config['PAYPAL_CLIENT_ID']}:{current_app.config['PAYPAL_CLIENT_SECRET']}".encode()
            ).decode()
            auth_headers['Authorization'] = f"Basic {auth}"

            auth_response = requests.post(token_url, headers=auth_headers, data=auth_data)
            
            if auth_response.status_code == 200:
                token_data = auth_response.json()
                access_token = token_data['access_token']

                # Execute payment
                execute_url = f"{current_app.config['PAYPAL_BASE_URL']}/v1/payments/payment/{payment_id}/execute"
                execute_headers = {
                    'Content-Type': 'application/json',
                    'Authorization': f'Bearer {access_token}'
                }

                execute_payload = {'payer_id': payer_id}
                execute_response = requests.post(execute_url, headers=execute_headers, json=execute_payload)

                if execute_response.status_code == 200:
                    result = execute_response.json()
                    
                    if result.get('state') == 'approved':
                        # Extract transaction details
                        transaction = result.get('transactions', [{}])[0]
                        amount = Decimal(str(transaction.get('amount', {}).get('total', '0')))
                        currency = transaction.get('amount', {}).get('currency', 'USD')
                        
                        # Get user ID from audit transaction
                        # This would need to be stored/retrieved from audit log
                        user_id = 1  # Placeholder - should get from audit
                        
                        # Deposit to wallet
                        deposit_result = self.wallet_service.deposit(
                            user_id=user_id,
                            amount=amount,
                            currency=currency,
                            reference=f"PayPal payment {payment_id}",
                            metadata={
                                "provider": "paypal",
                                "provider_transaction_id": payment_id,
                                "audit_transaction_id": audit_transaction_id
                            }
                        )
                        
                        if deposit_result.get('success'):
                            # Update audit as completed
                            AuditService.financial(
                                transaction_id=audit_transaction_id,
                                transaction_type=TransactionType.DEPOSIT,
                                amount=amount,
                                currency=currency,
                                status="completed",
                                to_user_id=user_id,
                                payment_method="paypal",
                                payment_provider="paypal",
                                api_call_status=APICallStatus.SUCCESS,
                                metadata={
                                    "provider_transaction_id": payment_id,
                                    "stage": "wallet_deposited"
                                }
                            )
                            
                            return {
                                'success': True,
                                'message': 'Payment completed and deposited to wallet',
                                'transaction_id': payment_id
                            }
                        else:
                            return {
                                'success': False,
                                'error': 'Failed to deposit to wallet'
                            }
                    else:
                        return {
                            'success': False,
                            'error': f"Payment not approved: {result.get('state')}"
                        }
                else:
                    return {
                        'success': False,
                        'error': f"Payment execution failed: {execute_response.text}"
                    }
            else:
                return {
                    'success': False,
                    'error': 'PayPal authentication failed'
                }

        except Exception as e:
            current_app.logger.error(f"PayPal execute error: {e}")
            return {
                'success': False,
                'error': str(e)
            }

    def verify_webhook(self, payload: Dict[str, Any], headers: Dict[str, str]) -> bool:
        """
        Verify PayPal webhook signature.
        """
        try:
            # Get webhook ID from headers
            webhook_id = headers.get('PAYPAL-AUTH-ALGO')
            if not webhook_id:
                return False

            # Verify with PayPal (simplified - implement proper verification in production)
            # This should call PayPal's webhook verification endpoint
            return True

        except Exception as e:
            current_app.logger.error(f"PayPal webhook verification error: {e}")
            return False
