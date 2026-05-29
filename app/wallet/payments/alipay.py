# app/wallet/payments/alipay.py
"""
Alipay payment integration with audit trail.

FLOW:
1. Create pending audit record
2. Call Alipay API
3. If success → call WalletService.deposit()
4. Update audit record with completion
5. If anything fails → update audit as failed
"""

import requests
import uuid
import hashlib
from decimal import Decimal
from datetime import datetime, timezone
from typing import Optional, Dict
from flask import current_app, request
from urllib.parse import urlencode

from app.audit.comprehensive_audit import AuditService, TransactionType, APICallStatus, AuditSeverity
from app.wallet.services.wallet_service import WalletService


class AlipayService:
    """
    Alipay payment integration with complete audit trail.
    """

    def __init__(self):
        self.wallet_service = WalletService()

    def process_deposit(
        self,
        user_id: int,
        amount: Decimal,
        currency: str,
        return_url: str,
        notify_url: str,
        idempotency_key: Optional[str] = None
    ) -> Dict:
        """
        Process a deposit through Alipay with correct ordering.

        Args:
            user_id: Internal user ID
            amount: Amount to deposit
            currency: Currency code (CNY, USD, etc.)
            return_url: Success return URL
            notify_url: Webhook notification URL
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
        provider_request_id = f"ALI{uuid.uuid4().hex[:12].upper()}"

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
                payment_method="alipay",
                payment_provider="alipay",
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

        # STEP 4: Call Alipay API
        provider_response = None
        provider_success = False
        provider_error = None
        provider_reference = None
        start_time = datetime.now(timezone.utc)

        try:
            # Build Alipay parameters
            import time
            
            params = {
                'app_id': current_app.config['ALIPAY_APP_ID'],
                'method': 'alipay.trade.page.pay',
                'format': 'json',
                'charset': 'utf-8',
                'sign_type': 'RSA2',
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'version': '1.0',
                'notify_url': notify_url,
                'return_url': return_url,
                'biz_content': json.dumps({
                    'out_trade_no': idempotency_key or audit_transaction_id,
                    'product_code': 'FAST_INSTANT_TRADE_PAY',
                    'total_amount': f"{float(amount):.2f}",
                    'subject': f"AFCON360 wallet deposit - {audit_transaction_id}",
                    'currency': currency,
                    'passback_params': {
                        'audit_transaction_id': audit_transaction_id,
                        'user_id': str(user_id)
                    }
                })
            }

            # Generate signature
            sign = self._generate_sign(params)
            params['sign'] = sign

            # Create payment URL
            base_url = current_app.config['ALIPAY_GATEWAY_URL']
            if current_app.config.get('ALIPAY_SANDBOX', True):
                base_url = 'https://openapi.alipaydev.com/gateway.do'
            else:
                base_url = 'https://openapi.alipay.com/gateway.do'

            payment_url = f"{base_url}?{urlencode(params)}"
            
            provider_response = {'payment_url': payment_url}
            provider_success = True
            provider_reference = idempotency_key or audit_transaction_id
            response_time_ms = int((datetime.now(timezone.utc) - start_time).total_seconds() * 1000)

        except Exception as e:
            provider_error = str(e)
            current_app.logger.error(f"Alipay API error: {e}")

        # STEP 5: Update audit record based on provider response
        if provider_success:
            try:
                AuditService.financial(
                    transaction_id=audit_transaction_id,
                    transaction_type=TransactionType.DEPOSIT,
                    amount=amount,
                    currency=currency,
                    status="pending_payment",
                    to_user_id=user_id,
                    to_balance_before=float(balance_before),
                    payment_method="alipay",
                    payment_provider="alipay",
                    ip_address=request.remote_addr if request else None,
                    user_agent=request.user_agent.string if request else None,
                    api_call_status=APICallStatus.SUCCESS,
                    response_time_ms=response_time_ms,
                    metadata={
                        "provider_request_id": provider_request_id,
                        "provider_reference": provider_reference,
                        "payment_url": payment_url,
                        "stage": "awaiting_payment"
                    }
                )
            except Exception as e:
                current_app.logger.error(f"Audit update failed: {e}")

            return {
                'success': True,
                'audit_transaction_id': audit_transaction_id,
                'payment_url': payment_url,
                'provider_reference': provider_reference,
                'amount': float(amount),
                'currency': currency
            }
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
                    payment_method="alipay",
                    payment_provider="alipay",
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

    def verify_payment(self, params: Dict[str, Any], audit_transaction_id: str) -> Dict:
        """
        Verify Alipay payment notification and deposit to wallet.
        """
        try:
            # Extract payment details
            out_trade_no = params.get('out_trade_no')
            trade_status = params.get('trade_status')
            total_amount = Decimal(params.get('total_amount', '0'))
            currency = params.get('currency', 'CNY')
            
            # Get user ID from passback params
            passback_params = json.loads(params.get('passback_params', '{}'))
            user_id = int(passback_params.get('user_id', '0'))

            # Verify signature
            if not self._verify_signature(params):
                return {
                    'success': False,
                    'error': 'Invalid signature'
                }

            if trade_status == 'TRADE_SUCCESS':
                # Get current balance
                current_balance = self.wallet_service.get_balance(user_id)
                balance_before = Decimal(current_balance.get('balance_home', '0'))

                # Deposit to wallet
                deposit_result = self.wallet_service.deposit(
                    user_id=user_id,
                    amount=total_amount,
                    currency=currency,
                    reference=f"Alipay payment {out_trade_no}",
                    metadata={
                        "provider": "alipay",
                        "provider_transaction_id": out_trade_no,
                        "audit_transaction_id": audit_transaction_id,
                        "trade_status": trade_status
                    }
                )

                if deposit_result.get('success'):
                    # Update audit as completed
                    AuditService.financial(
                        transaction_id=audit_transaction_id,
                        transaction_type=TransactionType.DEPOSIT,
                        amount=total_amount,
                        currency=currency,
                        status="completed",
                        to_user_id=user_id,
                        to_balance_before=float(balance_before),
                        payment_method="alipay",
                        payment_provider="alipay",
                        api_call_status=APICallStatus.SUCCESS,
                        metadata={
                            "provider_transaction_id": out_trade_no,
                            "trade_status": trade_status,
                            "stage": "wallet_deposited"
                        }
                    )

                    return {
                        'success': True,
                        'message': 'Payment verified and deposited to wallet',
                        'transaction_id': out_trade_no
                    }
                else:
                    return {
                        'success': False,
                        'error': 'Failed to deposit to wallet'
                    }
            else:
                # Update audit with payment status
                AuditService.financial(
                    transaction_id=audit_transaction_id,
                    transaction_type=TransactionType.DEPOSIT,
                    amount=total_amount,
                    currency=currency,
                    status="failed",
                    payment_method="alipay",
                    payment_provider="alipay",
                    api_call_status=APICallStatus.SUCCESS,
                    metadata={
                        "provider_transaction_id": out_trade_no,
                        "trade_status": trade_status,
                        "stage": "payment_not_successful"
                    }
                )

                return {
                    'success': False,
                    'error': f'Payment not successful: {trade_status}'
                }

        except Exception as e:
            current_app.logger.error(f"Alipay verification error: {e}")
            return {
                'success': False,
                'error': str(e)
            }

    def _generate_sign(self, params: Dict[str, Any]) -> str:
        """
        Generate RSA signature for Alipay.
        """
        # This is simplified - in production, use proper RSA2 signing
        sorted_params = sorted(params.items())
        sign_string = '&'.join([f"{k}={v}" for k, v in sorted_params if v and k != 'sign'])
        
        # For now, use MD5 (should be RSA2 in production)
        return hashlib.md5(sign_string.encode('utf-8')).hexdigest()

    def _verify_signature(self, params: Dict[str, Any]) -> bool:
        """
        Verify Alipay signature.
        """
        sign = params.pop('sign', None)
        if not sign:
            return False

        # Reconstruct parameters for verification
        sorted_params = sorted(params.items())
        sign_string = '&'.join([f"{k}={v}" for k, v in sorted_params if v])

        # Simplified verification - use proper RSA verification in production
        expected_sign = hashlib.md5(sign_string.encode('utf-8')).hexdigest()
        return expected_sign == sign
