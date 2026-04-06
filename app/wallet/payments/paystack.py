# app/wallet/payments/paystack.py - CORRECTED VERSION

"""
Paystack Payment Integration with CORRECT audit ordering.

FLOW:
1. Create pending audit record
2. Call Paystack API
3. If success → call WalletService.deposit()
4. Update audit record with completion
5. If anything fails → update audit as failed
"""

import requests
import uuid
from decimal import Decimal
from datetime import datetime
from typing import Optional, Dict
from flask import current_app, request

from app.audit.comprehensive_audit import AuditService, TransactionType, APICallStatus, AuditSeverity
from app.wallet.services.wallet_service import WalletService


class PaystackService:
    """
    Paystack payment integration with complete audit trail.
    """
    
    def __init__(self):
        self.wallet_service = WalletService()
    
    def process_deposit(
        self, 
        user_id: int, 
        amount: Decimal, 
        currency: str, 
        email: str,
        idempotency_key: Optional[str] = None,
        metadata: Optional[Dict] = None
    ) -> Dict:
        """
        Process a deposit through Paystack with CORRECT ordering.
        
        Args:
            user_id: Internal user ID
            amount: Amount to deposit (will be converted to smallest unit)
            currency: Currency code (NGN, GHS, USD, etc.)
            email: User's email for Paystack
            idempotency_key: For duplicate prevention
            metadata: Additional transaction metadata
        
        Returns:
            Dict with transaction result including authorization URL
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
        provider_request_id = f"PS-{uuid.uuid4().hex[:12].upper()}"
        
        # Convert amount to smallest unit (Paystack requirement)
        # e.g., 100 NGN = 10000 kobo, 1 USD = 100 cents
        smallest_unit_multiplier = {
            "NGN": 100,  # Kobo
            "GHS": 100,  # Pesewas
            "USD": 100,  # Cents
            "KES": 100,  # Cents
            "ZAR": 100,  # Cents
        }
        multiplier = smallest_unit_multiplier.get(currency, 100)
        amount_in_smallest_unit = int(float(amount) * multiplier)
        
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
                payment_method="card_transfer",
                payment_provider="paystack",
                ip_address=request.remote_addr if request else None,
                user_agent=request.user_agent.string if request else None,
                metadata={
                    "idempotency_key": idempotency_key,
                    "provider_request_id": provider_request_id,
                    "stage": "calling_provider",
                    "client_metadata": metadata or {},
                }
            )
        except Exception as e:
            current_app.logger.error(f"Failed to create pending audit: {e}")
        
        # STEP 4: Call Paystack API
        provider_response = None
        provider_success = False
        provider_error = None
        provider_reference = None
        authorization_url = None
        access_code = None
        start_time = datetime.utcnow()
        
        try:
            url = f"{current_app.config['PAYSTACK_BASE_URL']}/transaction/initialize"
            
            payload = {
                "email": email,
                "amount": amount_in_smallest_unit,
                "currency": currency,
                "reference": idempotency_key or audit_transaction_id,
                "metadata": {
                    "user_id": user_id,
                    "transaction_id": audit_transaction_id,
                    "client_metadata": metadata or {}
                }
            }
            
            headers = {
                "Authorization": f"Bearer {current_app.config['PAYSTACK_SECRET_KEY']}",
                "Content-Type": "application/json"
            }
            
            response = requests.post(url, json=payload, headers=headers)
            provider_response = response.json()
            response_time_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)
            
            # Check if successful
            if response.status_code == 200 and provider_response.get('status'):
                provider_success = True
                provider_reference = provider_response.get('data', {}).get('reference')
                authorization_url = provider_response.get('data', {}).get('authorization_url')
                access_code = provider_response.get('data', {}).get('access_code')
            else:
                provider_error = provider_response.get('message', 'Paystack error')
                
        except Exception as e:
            provider_error = str(e)
            response_time_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)
            current_app.logger.error(f"Paystack API call failed: {e}")
        
        # STEP 5: Log API call for audit
        try:
            AuditService.api_call(
                service_name="paystack",
                endpoint="/transaction/initialize",
                method="POST",
                request_id=provider_request_id,
                correlation_id=audit_transaction_id,
                status=APICallStatus.SUCCESS if provider_success else APICallStatus.FAILURE,
                response_status=response.status_code if 'response' in locals() else None,
                response_time_ms=response_time_ms,
                initiated_by=user_id,
                request_payload={
                    "email": email,
                    "amount": amount_in_smallest_unit,
                    "currency": currency,
                },
                response_body=provider_response,
                error_message=provider_error
            )
        except Exception as e:
            current_app.logger.error(f"Failed to log API audit: {e}")
        
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
                    payment_method="card_transfer",
                    payment_provider="paystack",
                    ip_address=request.remote_addr if request else None,
                    metadata={
                        "error": provider_error,
                        "stage": "provider_failed",
                        "provider_request_id": provider_request_id
                    }
                )
            except Exception as e:
                current_app.logger.error(f"Failed to log failure audit: {e}")
            
            return {
                "status": "failed",
                "transaction_id": audit_transaction_id,
                "error": provider_error,
                "requires_retry": True
            }
        
        # STEP 7: For Paystack, we don't update balance immediately
        # Balance is updated via webhook after payment confirmation
        # So we just return the authorization URL
        
        try:
            AuditService.financial(
                transaction_id=audit_transaction_id,
                transaction_type=TransactionType.DEPOSIT,
                amount=amount,
                currency=currency,
                status="pending_payment",
                to_user_id=user_id,
                to_balance_before=float(balance_before),
                payment_method="card_transfer",
                payment_provider="paystack",
                external_reference=provider_reference,
                ip_address=request.remote_addr if request else None,
                metadata={
                    "idempotency_key": idempotency_key,
                    "provider_request_id": provider_request_id,
                    "stage": "awaiting_payment",
                    "access_code": access_code,
                    "client_metadata": metadata or {},
                }
            )
        except Exception as e:
            current_app.logger.error(f"Failed to update audit: {e}")
        
        return {
            "status": "pending",
            "transaction_id": audit_transaction_id,
            "provider_reference": provider_reference,
            "authorization_url": authorization_url,
            "access_code": access_code,
            "amount": str(amount),
            "currency": currency,
            "message": "Redirect user to authorization_url to complete payment"
        }
    
    def verify_payment(self, reference: str) -> Dict:
        """
        Verify a Paystack transaction after webhook or redirect.
        
        This should be called when Paystack redirects back or via webhook.
        """
        from flask import request
        
        # STEP 1: Get existing transaction from audit
        # Find the pending transaction by reference
        
        # STEP 2: Call Paystack to verify
        start_time = datetime.utcnow()
        
        try:
            url = f"{current_app.config['PAYSTACK_BASE_URL']}/transaction/verify/{reference}"
            headers = {"Authorization": f"Bearer {current_app.config['PAYSTACK_SECRET_KEY']}"}
            
            response = requests.get(url, headers=headers)
            verification_response = response.json()
            response_time_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)
            
            # Log verification API call
            AuditService.api_call(
                service_name="paystack",
                endpoint=f"/transaction/verify/{reference}",
                method="GET",
                request_id=f"VER-{uuid.uuid4().hex[:12].upper()}",
                correlation_id=reference,
                status=APICallStatus.SUCCESS if response.status_code == 200 else APICallStatus.FAILURE,
                response_status=response.status_code,
                response_time_ms=response_time_ms,
                response_body=verification_response
            )
            
            # Check if payment was successful
            if (verification_response.get('status') and 
                verification_response.get('data', {}).get('status') == 'success'):
                
                # Extract payment details
                payment_data = verification_response.get('data', {})
                amount_in_smallest_unit = payment_data.get('amount', 0)
                currency = payment_data.get('currency', 'NGN')
                amount = Decimal(str(amount_in_smallest_unit / 100))  # Convert from smallest unit
                
                # Get user_id from metadata
                user_id = payment_data.get('metadata', {}).get('user_id')
                
                if not user_id:
                    raise ValueError("Cannot determine user from payment metadata")
                
                # STEP 3: Update wallet balance (NOW the money is confirmed)
                deposit_result = self.wallet_service.deposit(
                    user_id=user_id,
                    amount=amount,
                    currency=currency,
                    idempotency_key=reference,
                    metadata={
                        "payment_provider": "paystack",
                        "payment_method": "card",
                        "provider_reference": reference,
                        "verification_response": payment_data
                    }
                )
                
                # STEP 4: Update audit record
                try:
                    # Get balance after deposit
                    new_balance = self.wallet_service.get_balance(user_id)
                    balance_after = Decimal(new_balance.get('balance_home', '0'))
                    
                    # Find and update the original pending audit
                    # For now, create a completion record
                    AuditService.financial(
                        transaction_id=reference,
                        transaction_type=TransactionType.DEPOSIT,
                        amount=amount,
                        currency=currency,
                        status="completed",
                        to_user_id=user_id,
                        to_balance_after=float(balance_after),
                        payment_method="card",
                        payment_provider="paystack",
                        external_reference=reference,
                        metadata={
                            "stage": "payment_confirmed",
                            "verification_time_ms": response_time_ms
                        }
                    )
                except Exception as e:
                    current_app.logger.error(f"Failed to update audit: {e}")
                
                return {
                    "status": "success",
                    "transaction_id": deposit_result.get('transaction_id'),
                    "amount": str(amount),
                    "currency": currency,
                    "provider_reference": reference
                }
            else:
                # Payment failed or pending
                return {
                    "status": "failed",
                    "message": verification_response.get('message', 'Payment verification failed'),
                    "provider_reference": reference
                }
                
        except Exception as e:
            current_app.logger.error(f"Paystack verification failed: {e}")
            return {
                "status": "error",
                "message": str(e),
                "provider_reference": reference
            }
    
    def handle_webhook(self, payload: Dict, signature: str) -> Dict:
        """
        Handle Paystack webhook for asynchronous payment confirmation.
        
        This is the recommended way to receive payment confirmations.
        """
        from flask import request
        
        # Verify webhook signature
        expected_signature = self._calculate_webhook_signature(
            request.get_data(), 
            current_app.config.get('PAYSTACK_SECRET_KEY')
        )
        
        if not self._verify_signature(signature, expected_signature):
            current_app.logger.warning("Invalid Paystack webhook signature")
            return {"status": "error", "message": "Invalid signature"}, 401
        
        event = payload.get('event')
        
        # Handle successful charge event
        if event == 'charge.success':
            data = payload.get('data', {})
            reference = data.get('reference')
            amount_in_smallest_unit = data.get('amount', 0)
            currency = data.get('currency', 'NGN')
            amount = Decimal(str(amount_in_smallest_unit / 100))
            
            # Get user from metadata
            user_id = data.get('metadata', {}).get('user_id')
            
            if not user_id:
                current_app.logger.error(f"Webhook missing user_id for reference: {reference}")
                return {"status": "error", "message": "Missing user_id"}, 400
            
            # Update wallet balance
            try:
                deposit_result = self.wallet_service.deposit(
                    user_id=user_id,
                    amount=amount,
                    currency=currency,
                    idempotency_key=reference,
                    metadata={
                        "payment_provider": "paystack",
                        "payment_method": "card",
                        "provider_reference": reference,
                        "webhook_payload": data
                    }
                )
                
                # Log successful webhook processing
                AuditService.security(
                    event_type="paystack_webhook_processed",
                    severity=AuditSeverity.INFO,
                    description=f"Paystack webhook processed for deposit {reference}",
                    user_id=user_id,
                    metadata={
                        "reference": reference,
                        "amount": float(amount),
                        "currency": currency,
                        "transaction_id": deposit_result.get('transaction_id')
                    }
                )
                
                return {"status": "success"}
                
            except Exception as e:
                current_app.logger.error(f"Webhook deposit failed: {e}")
                return {"status": "error", "message": str(e)}, 500
        
        # Handle other events
        current_app.logger.info(f"Unhandled Paystack webhook event: {event}")
        return {"status": "ignored"}
    
    def _calculate_webhook_signature(self, payload: bytes, secret: str) -> str:
        """Calculate expected webhook signature."""
        import hmac
        import hashlib
        return hmac.new(secret.encode(), payload, hashlib.sha512).hexdigest()
    
    def _verify_signature(self, received: str, expected: str) -> bool:
        """Securely verify webhook signature."""
        import hmac
        return hmac.compare_digest(received, expected)