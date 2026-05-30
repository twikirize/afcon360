# app/wallet/payments/visa.py
"""
Visa payment gateway integration with audit trail.

FLOW:
1. Create pending audit record
2. Call Visa Direct API
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


class VisaService:
    """
    Visa payment integration with complete audit trail.
    """

    def __init__(self):
        self.wallet_service = WalletService()

    def process_deposit(
        self,
        user_id: int,
        amount: Decimal,
        currency: str,
        card_data: Dict[str, str],
        billing_address: Dict[str, str],
        idempotency_key: Optional[str] = None
    ) -> Dict:
        """
        Process a deposit through Visa Direct API with correct ordering.

        Args:
            user_id: Internal user ID
            amount: Amount to deposit
            currency: Currency code (USD, EUR, etc.)
            card_data: Dictionary containing card information
            billing_address: Dictionary containing billing address
            idempotency_key: For duplicate prevention

        Returns:
            Dict with payment details and status
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
        provider_request_id = f"VS{uuid.uuid4().hex[:12].upper()}"

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
                payment_method="visa_direct",
                payment_provider="visa",
                ip_address=request.remote_addr if request else None,
                user_agent=request.user_agent.string if request else None,
                metadata={
                    "idempotency_key": idempotency_key,
                    "provider_request_id": provider_request_id,
                    "card_last4": card_data.get('number', '')[-4:],
                    "stage": "calling_provider"
                }
            )
        except Exception as e:
            current_app.logger.error(f"Audit create failed: {e}")

        # STEP 4: Call Visa Direct API
        provider_response = None
        provider_success = False
        provider_error = None
        provider_reference = None
        start_time = datetime.now(timezone.utc)

        try:
            # Visa Direct API endpoint
            url = f"{current_app.config['VISA_DIRECT_BASE_URL']}/payments"
            headers = {
                'Authorization': f'Bearer {current_app.config["VISA_DIRECT_API_KEY"]}',
                'Content-Type': 'application/json',
                'X-Request-ID': provider_request_id
            }

            # Prepare payment payload
            payload = {
                'merchant_id': current_app.config['VISA_DIRECT_MERCHANT_ID'],
                'transaction_id': idempotency_key or audit_transaction_id,
                'amount': {
                    'currency': currency,
                    'value': float(amount)
                },
                'payment_method': {
                    'type': 'card',
                    'card': {
                        'number': card_data.get('number', ''),
                        'expiry_month': card_data.get('expiry_month', ''),
                        'expiry_year': card_data.get('expiry_year', ''),
                        'cvv': card_data.get('cvv', ''),
                        'cardholder_name': card_data.get('cardholder_name', '')
                    }
                },
                'billing_address': billing_address,
                'customer': {
                    'id': str(user_id),
                    'email': card_data.get('email', ''),
                    'ip_address': request.remote_addr if request else ''
                },
                'return_url': current_app.config['VISA_DIRECT_RETURN_URL'],
                'webhook_url': current_app.config['VISA_DIRECT_WEBHOOK_URL'],
                '3ds_required': True,  # Require 3D Secure for amounts > 1000
                'description': f"AFCON360 wallet deposit - {audit_transaction_id}"
            }

            response = requests.post(url, json=payload, headers=headers, timeout=60)
            provider_response = response.json()
            response_time_ms = int((datetime.now(timezone.utc) - start_time).total_seconds() * 1000)

            # Check if successful
            if response.status_code == 200 and provider_response.get('status') == 'approved':
                provider_success = True
                provider_reference = provider_response.get('transaction_id')
                
                # For 3D Secure, return redirect URL
                if provider_response.get('3ds_required'):
                    return {
                        'success': True,
                        'requires_3ds': True,
                        'redirect_url': provider_response.get('3ds_url'),
                        'audit_transaction_id': audit_transaction_id,
                        'provider_reference': provider_reference,
                        'amount': float(amount),
                        'currency': currency
                    }

        except Exception as e:
            provider_error = str(e)
            current_app.logger.error(f"Visa Direct API error: {e}")

        # STEP 5: Update audit record based on provider response
        if provider_success:
            try:
                # Deposit to wallet
                deposit_result = self.wallet_service.deposit(
                    user_id=user_id,
                    amount=amount,
                    currency=currency,
                    reference=f"Visa Direct payment {provider_reference}",
                    metadata={
                        "provider": "visa_direct",
                        "provider_transaction_id": provider_reference,
                        "audit_transaction_id": audit_transaction_id,
                        "card_last4": card_data.get('number', '')[-4:],
                        "3ds_required": provider_response.get('3ds_required', False)
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
                        to_balance_before=float(balance_before),
                        payment_method="visa_direct",
                        payment_provider="visa",
                        ip_address=request.remote_addr if request else None,
                        user_agent=request.user_agent.string if request else None,
                        api_call_status=APICallStatus.SUCCESS,
                        response_time_ms=response_time_ms,
                        metadata={
                            "provider_request_id": provider_request_id,
                            "provider_reference": provider_reference,
                            "3ds_required": provider_response.get('3ds_required', False),
                            "stage": "completed"
                        }
                    )

                    return {
                        'success': True,
                        'audit_transaction_id': audit_transaction_id,
                        'provider_reference': provider_reference,
                        'amount': float(amount),
                        'currency': currency,
                        'message': 'Payment processed successfully'
                    }
                else:
                    return {
                        'success': False,
                        'error': 'Failed to deposit to wallet',
                        'audit_transaction_id': audit_transaction_id
                    }
            except Exception as e:
                current_app.logger.error(f"Wallet deposit failed: {e}")
        else:
            # STEP 6: Update audit as FAILED if anything went wrong
            try:
                AuditService.financial(
                    transaction_id=audit_transaction_id,
                    transaction_type=TransactionType.DEPOSIT,
                    amount=amount,
                    currency=currency,
                    status="failed",
                    to_user_id=user_id,
                    to_balance_before=float(balance_before),
                    payment_method="visa_direct",
                    payment_provider="visa",
                    ip_address=request.remote_addr if request else None,
                    user_agent=request.user_agent.string if request else None,
                    api_call_status=APICallStatus.FAILED,
                    metadata={
                        "provider_request_id": provider_request_id,
                        "error": provider_error,
                        "card_last4": card_data.get('number', '')[-4:],
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

    def verify_3ds_completion(self, transaction_id: str, pa_res: str, md: str) -> Dict:
        """
        Verify 3D Secure completion and finalize payment.
        """
        try:
            url = f"{current_app.config['VISA_DIRECT_BASE_URL']}/payments/3ds/verify"
            headers = {
                'Authorization': f'Bearer {current_app.config["VISA_DIRECT_API_KEY"]}',
                'Content-Type': 'application/json'
            }

            payload = {
                'transaction_id': transaction_id,
                'pa_res': pa_res,
                'md': md
            }

            response = requests.post(url, json=payload, headers=headers, timeout=30)

            if response.status_code == 200:
                result = response.json()
                
                if result.get('status') == 'completed':
                    # Get user ID from transaction
                    # This would need to be stored/retrieved from audit log
                    user_id = 1  # Placeholder - should get from audit
                    
                    # Get current balance
                    current_balance = self.wallet_service.get_balance(user_id)
                    balance_before = Decimal(current_balance.get('balance_home', '0'))

                    # Deposit to wallet
                    deposit_result = self.wallet_service.deposit(
                        user_id=user_id,
                        amount=Decimal(str(result.get('amount', '0'))),
                        currency=result.get('currency', 'USD'),
                        reference=f"Visa Direct 3DS payment {transaction_id}",
                        metadata={
                            "provider": "visa_direct",
                            "provider_transaction_id": transaction_id,
                            "3ds_verified": True,
                            "pa_res": pa_res,
                            "md": md
                        }
                    )

                    if deposit_result.get('success'):
                        # Update audit as completed
                        AuditService.financial(
                            transaction_id=transaction_id,
                            transaction_type=TransactionType.DEPOSIT,
                            amount=Decimal(str(result.get('amount', '0'))),
                            currency=result.get('currency', 'USD'),
                            status="completed",
                            to_user_id=user_id,
                            to_balance_before=float(balance_before),
                            payment_method="visa_direct",
                            payment_provider="visa",
                            api_call_status=APICallStatus.SUCCESS,
                            metadata={
                                "provider_transaction_id": transaction_id,
                                "3ds_verified": True,
                                "stage": "3ds_completed"
                            }
                        )

                        return {
                            'success': True,
                            'message': '3D Secure verification completed',
                            'transaction_id': transaction_id
                        }
                    else:
                        return {
                            'success': False,
                            'error': 'Failed to deposit after 3DS verification'
                        }
                else:
                    return {
                        'success': False,
                        'error': f"3DS verification failed: {result.get('message', 'Unknown error')}"
                    }
            else:
                return {
                    'success': False,
                    'error': f"3DS verification API error: {response.text}"
                }

        except Exception as e:
            current_app.logger.error(f"Visa 3DS verification error: {e}")
            return {
                'success': False,
                'error': str(e)
            }

    def verify_webhook(self, payload: Dict[str, Any], headers: Dict[str, str]) -> bool:
        """
        Verify Visa Direct webhook signature and process payment.
        """
        try:
            # Extract webhook signature
            signature = headers.get('X-Visa-Signature')
            if not signature:
                return False

            # Verify signature using HMAC
            expected_signature = self._generate_webhook_signature(payload)
            if not self._verify_signature(signature, expected_signature):
                return False

            # Process webhook based on event type
            event_type = payload.get('event_type')
            transaction_id = payload.get('transaction_id')
            status = payload.get('status')

            if event_type == 'payment.completed' and status == 'success':
                # Get user ID from transaction
                user_id = 1  # Placeholder - should get from audit
                
                # Get current balance
                current_balance = self.wallet_service.get_balance(user_id)
                balance_before = Decimal(current_balance.get('balance_home', '0'))

                # Deposit to wallet
                amount = Decimal(str(payload.get('amount', '0')))
                currency = payload.get('currency', 'USD')

                deposit_result = self.wallet_service.deposit(
                    user_id=user_id,
                    amount=amount,
                    currency=currency,
                    reference=f"Visa Direct webhook payment {transaction_id}",
                    metadata={
                        "provider": "visa_direct",
                        "provider_transaction_id": transaction_id,
                        "webhook_event": event_type,
                        "webhook_status": status
                    }
                )

                if deposit_result.get('success'):
                    # Update audit as completed
                    AuditService.financial(
                        transaction_id=transaction_id,
                        transaction_type=TransactionType.DEPOSIT,
                        amount=amount,
                        currency=currency,
                        status="completed",
                        to_user_id=user_id,
                        to_balance_before=float(balance_before),
                        payment_method="visa_direct",
                        payment_provider="visa",
                        api_call_status=APICallStatus.SUCCESS,
                        metadata={
                            "provider_transaction_id": transaction_id,
                            "webhook_event": event_type,
                            "webhook_status": status,
                            "stage": "webhook_processed"
                        }
                    )

                    return True

            elif event_type == 'payment.failed':
                # Update audit as failed
                AuditService.financial(
                    transaction_id=transaction_id,
                    transaction_type=TransactionType.DEPOSIT,
                    amount=Decimal(str(payload.get('amount', '0'))),
                    currency=payload.get('currency', 'USD'),
                    status="failed",
                    payment_method="visa_direct",
                    payment_provider="visa",
                    api_call_status=APICallStatus.SUCCESS,
                    metadata={
                        "provider_transaction_id": transaction_id,
                        "webhook_event": event_type,
                        "webhook_status": status,
                        "failure_reason": payload.get('failure_reason'),
                        "stage": "webhook_failed"
                    }
                )

                return True

        except Exception as e:
            current_app.logger.error(f"Visa webhook verification error: {e}")
            return False

    def _generate_webhook_signature(self, payload: Dict[str, Any]) -> str:
        """
        Generate HMAC signature for webhook verification.
        """
        import hmac
        import hashlib
        
        # Sort payload keys
        sorted_payload = sorted(payload.items())
        
        # Create string to sign
        string_to_sign = '&'.join([f"{k}={v}" for k, v in sorted_payload])
        string_to_sign += f"&key={current_app.config['VISA_DIRECT_WEBHOOK_SECRET']}"
        
        # Generate HMAC-SHA256
        return hmac.new(
            current_app.config['VISA_DIRECT_WEBHOOK_SECRET'].encode(),
            string_to_sign.encode(),
            hashlib.sha256
        ).hexdigest()

    def _verify_signature(self, received_signature: str, expected_signature: str) -> bool:
        """
        Verify webhook signature.
        """
        import hmac
        return hmac.compare_digest(received_signature, expected_signature)

    def refund_payment(self, transaction_id: str, amount: Decimal, reason: str) -> Dict:
        """
        Process a refund through Visa Direct API.
        """
        try:
            url = f"{current_app.config['VISA_DIRECT_BASE_URL']}/refunds"
            headers = {
                'Authorization': f'Bearer {current_app.config["VISA_DIRECT_API_KEY"]}',
                'Content-Type': 'application/json'
            }

            payload = {
                'original_transaction_id': transaction_id,
                'refund_amount': {
                    'currency': 'USD',  # Assuming USD for refunds
                    'value': float(amount)
                },
                'reason': reason,
                'merchant_id': current_app.config['VISA_DIRECT_MERCHANT_ID']
            }

            response = requests.post(url, json=payload, headers=headers, timeout=60)

            if response.status_code == 200:
                result = response.json()
                
                if result.get('status') == 'approved':
                    return {
                        'success': True,
                        'refund_id': result.get('refund_id'),
                        'message': 'Refund processed successfully'
                    }
                else:
                    return {
                        'success': False,
                        'error': result.get('message', 'Refund failed')
                    }
            else:
                return {
                    'success': False,
                    'error': f"Refund API error: {response.text}"
                }

        except Exception as e:
            current_app.logger.error(f"Visa refund error: {e}")
            return {
                'success': False,
                'error': str(e)
            }
