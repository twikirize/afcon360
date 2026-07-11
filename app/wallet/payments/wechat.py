# app/wallet/payments/wechat.py
"""
WeChat Pay payment integration with audit trail.

FLOW:
1. Create pending audit record
2. Call WeChat Pay API
3. If success → call WalletService.deposit()
4. Update audit record with completion
5. If anything fails → update audit as failed
"""

import requests
import uuid
import qrcode
import io
import base64
from decimal import Decimal
from datetime import datetime, timezone
from typing import Optional, Dict
from flask import current_app, request

from app.audit.comprehensive_audit import AuditService, TransactionType, APICallStatus, AuditSeverity
from app.wallet.services.wallet_service import WalletService


class WeChatPayService:
    """
    WeChat Pay integration with complete audit trail.
    """

    def __init__(self):
        self.wallet_service = WalletService()

    def process_deposit(
        self,
        user_id: int,
        amount: Decimal,
        currency: str,
        description: str,
        idempotency_key: Optional[str] = None
    ) -> Dict:
        """
        Process a deposit through WeChat Pay with correct ordering.

        Args:
            user_id: Internal user ID
            amount: Amount to deposit
            currency: Currency code (CNY, USD, etc.)
            description: Payment description
            idempotency_key: For duplicate prevention

        Returns:
            Dict with QR code and transaction details
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
        provider_request_id = f"WC{uuid.uuid4().hex[:12].upper()}"

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
                payment_method="wechat_pay",
                payment_provider="wechat",
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

        # STEP 4: Call WeChat Pay API
        provider_response = None
        provider_success = False
        provider_error = None
        provider_reference = None
        start_time = datetime.now(timezone.utc)

        try:
            # Generate WeChat Pay QR code
            result = self._generate_wechat_qr(
                amount=amount,
                description=description,
                transaction_id=idempotency_key or audit_transaction_id,
                user_id=user_id
            )
            
            provider_response = result
            provider_success = result.get('success', False)
            provider_reference = result.get('prepay_id')
            response_time_ms = int((datetime.now(timezone.utc) - start_time).total_seconds() * 1000)

        except Exception as e:
            provider_error = str(e)
            current_app.logger.error(f"WeChat Pay API error: {e}")

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
                    payment_method="wechat_pay",
                    payment_provider="wechat",
                    ip_address=request.remote_addr if request else None,
                    user_agent=request.user_agent.string if request else None,
                    api_call_status=APICallStatus.SUCCESS,
                    response_time_ms=response_time_ms,
                    metadata={
                        "provider_request_id": provider_request_id,
                        "provider_reference": provider_reference,
                        "qr_code": result.get('qr_code'),
                        "stage": "awaiting_payment"
                    }
                )
            except Exception as e:
                current_app.logger.error(f"Audit update failed: {e}")

            return {
                'success': True,
                'audit_transaction_id': audit_transaction_id,
                'qr_code': result.get('qr_code'),
                'qr_data': result.get('qr_data'),
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
                    payment_method="wechat_pay",
                    payment_provider="wechat",
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

    def _generate_wechat_qr(self, amount: Decimal, description: str,
                             transaction_id: str, user_id: int) -> Dict:
        """
        Generate WeChat Pay QR code for payment.
        """
        try:
            # WeChat Pay unified order API
            url = f"{current_app.config['WECHAT_PAY_BASE_URL']}/pay/unifiedorder"
            
            # Prepare order data
            order_data = {
                'appid': current_app.config['WECHAT_PAY_APP_ID'],
                'mch_id': current_app.config['WECHAT_PAY_MCH_ID'],
                'nonce_str': str(uuid.uuid4()).replace('-', ''),
                'body': description,
                'out_trade_no': transaction_id,
                'total_fee': int(amount * 100),  # Convert to fen
                'spbill_create_ip': request.remote_addr if request else '127.0.0.1',
                'notify_url': current_app.config['WECHAT_PAY_NOTIFY_URL'],
                'trade_type': 'NATIVE',  # Native payment
                'product_id': str(user_id),  # User ID as product ID
            }

            # Generate signature
            sign = self._generate_wechat_signature(order_data)
            order_data['sign'] = sign

            # Make API request
            response = requests.post(url, json=order_data, timeout=30)
            
            if response.status_code == 200:
                result = response.json()
                
                if result.get('return_code') == 'SUCCESS':
                    prepay_id = result.get('prepay_id')
                    code_url = result.get('code_url')
                    
                    # Generate QR code from code URL
                    qr_code = self._generate_qr_image(code_url)
                    
                    return {
                        'success': True,
                        'prepay_id': prepay_id,
                        'code_url': code_url,
                        'qr_code': qr_code,
                        'qr_data': code_url
                    }
                else:
                    return {
                        'success': False,
                        'error': result.get('return_msg', 'Unknown error')
                    }
            else:
                return {
                    'success': False,
                    'error': f'WeChat Pay API error: {response.text}'
                }

        except Exception as e:
            current_app.logger.error(f"WeChat Pay QR generation error: {e}")
            return {
                'success': False,
                'error': str(e)
            }

    def verify_payment(self, notification_data: Dict[str, Any], audit_transaction_id: str) -> Dict:
        """
        Verify WeChat Pay payment notification and deposit to wallet.
        """
        try:
            # Extract payment details
            out_trade_no = notification_data.get('out_trade_no')
            transaction_id = notification_data.get('transaction_id')
            result_code = notification_data.get('result_code')
            total_fee = Decimal(str(notification_data.get('total_fee', '0'))) / 100  # Convert from fen
            time_end = notification_data.get('time_end')
            
            # Get user ID from transaction ID (would need to be stored/retrieved from audit log)
            user_id = 1  # Placeholder - should get from audit
            
            # Verify signature
            if not self._verify_wechat_signature(notification_data):
                return {
                    'success': False,
                    'error': 'Invalid signature'
                }

            if result_code == 'SUCCESS':
                # Get current balance
                current_balance = self.wallet_service.get_balance(user_id)
                balance_before = Decimal(current_balance.get('balance_home', '0'))

                # Deposit to wallet
                deposit_result = self.wallet_service.deposit(
                    user_id=user_id,
                    amount=total_fee,
                    currency='CNY',
                    reference=f"WeChat Pay payment {transaction_id}",
                    metadata={
                        "provider": "wechat",
                        "provider_transaction_id": transaction_id,
                        "audit_transaction_id": audit_transaction_id,
                        "result_code": result_code,
                        "time_end": time_end
                    }
                )

                if deposit_result.get('success'):
                    # Update audit as completed
                    AuditService.financial(
                        transaction_id=audit_transaction_id,
                        transaction_type=TransactionType.DEPOSIT,
                        amount=total_fee,
                        currency='CNY',
                        status="completed",
                        to_user_id=user_id,
                        to_balance_before=float(balance_before),
                        payment_method="wechat_pay",
                        payment_provider="wechat",
                        api_call_status=APICallStatus.SUCCESS,
                        metadata={
                            "provider_transaction_id": transaction_id,
                            "result_code": result_code,
                            "time_end": time_end,
                            "stage": "wallet_deposited"
                        }
                    )

                    return {
                        'success': True,
                        'message': 'WeChat Pay payment completed and deposited to wallet',
                        'transaction_id': transaction_id
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
                    amount=total_fee,
                    currency='CNY',
                    status="failed",
                    payment_method="wechat_pay",
                    payment_provider="wechat",
                    api_call_status=APICallStatus.SUCCESS,
                    metadata={
                        "provider_transaction_id": transaction_id,
                        "result_code": result_code,
                        "time_end": time_end,
                        "stage": "payment_not_successful"
                    }
                )

                return {
                    'success': False,
                    'error': f'Payment not successful: {result_code}'
                }

        except Exception as e:
            current_app.logger.error(f"WeChat Pay verification error: {e}")
            return {
                'success': False,
                'error': str(e)
            }

    def _generate_wechat_signature(self, params: Dict[str, Any]) -> str:
        """
        Generate WeChat Pay signature.
        """
        # Sort parameters
        sorted_params = sorted(params.items())
        
        # Create string to sign
        string_to_sign = '&'.join([f"{k}={v}" for k, v in sorted_params if k != 'sign'])
        
        # Add API key (in production, this would be the actual API key)
        string_to_sign += f"&key={current_app.config['WECHAT_PAY_API_KEY']}"
        
        # Generate MD5 hash
        import hashlib
        return hashlib.md5(string_to_sign.encode('utf-8')).hexdigest().upper()

    def _verify_wechat_signature(self, params: Dict[str, Any]) -> bool:
        """
        Verify WeChat Pay signature.
        """
        sign = params.pop('sign', None)
        if not sign:
            return False

        # Reconstruct parameters for verification
        sorted_params = sorted(params.items())
        string_to_sign = '&'.join([f"{k}={v}" for k, v in sorted_params])
        string_to_sign += f"&key={current_app.config['WECHAT_PAY_API_KEY']}"

        # Verify MD5 hash
        import hashlib
        expected_sign = hashlib.md5(string_to_sign.encode('utf-8')).hexdigest().upper()
        return expected_sign == sign

    def _generate_qr_image(self, data: str) -> str:
        """
        Generate QR code image as base64 string.
        """
        try:
            # Create QR code
            qr = qrcode.QRCode(
                version=1,
                error_correction=qrcode.constants.ERROR_CORRECT_L,
                box_size=10,
                border=4,
            )
            qr.add_data(data)
            qr.make(fit=True)

            # Convert to image
            img = qr.make_image(fill_color="black", back_color="white")
            
            # Convert to base64
            buffer = io.BytesIO()
            img.save(buffer, format='PNG')
            img_str = base64.b64encode(buffer.getvalue()).decode()
            
            return f"data:image/png;base64,{img_str}"

        except Exception as e:
            current_app.logger.error(f"QR code generation error: {e}")
            return ""

    def query_order_status(self, out_trade_no: str) -> Dict:
        """
        Query WeChat Pay order status.
        """
        try:
            url = f"{current_app.config['WECHAT_PAY_BASE_URL']}/pay/orderquery"
            
            # Prepare query data
            query_data = {
                'appid': current_app.config['WECHAT_PAY_APP_ID'],
                'mch_id': current_app.config['WECHAT_PAY_MCH_ID'],
                'out_trade_no': out_trade_no,
                'nonce_str': str(uuid.uuid4()).replace('-', ''),
            }

            # Generate signature
            sign = self._generate_wechat_signature(query_data)
            query_data['sign'] = sign

            # Make API request
            response = requests.post(url, json=query_data, timeout=30)
            
            if response.status_code == 200:
                result = response.json()
                
                if result.get('return_code') == 'SUCCESS':
                    return {
                        'success': True,
                        'trade_state': result.get('trade_state'),
                        'transaction_id': result.get('transaction_id'),
                        'total_fee': result.get('total_fee'),
                        'time_end': result.get('time_end')
                    }
                else:
                    return {
                        'success': False,
                        'error': result.get('return_msg', 'Unknown error')
                    }
            else:
                return {
                    'success': False,
                    'error': f'WeChat Pay API error: {response.text}'
                }

        except Exception as e:
            current_app.logger.error(f"WeChat Pay order query error: {e}")
            return {
                'success': False,
                'error': str(e)
            }

    def close_order(self, out_trade_no: str) -> Dict:
        """
        Close WeChat Pay order.
        """
        try:
            url = f"{current_app.config['WECHAT_PAY_BASE_URL']}/pay/closeorder"
            
            # Prepare close order data
            close_data = {
                'appid': current_app.config['WECHAT_PAY_APP_ID'],
                'mch_id': current_app.config['WECHAT_PAY_MCH_ID'],
                'out_trade_no': out_trade_no,
                'nonce_str': str(uuid.uuid4()).replace('-', ''),
                'operator_id': 'SYSTEM',  # System operator
            }

            # Generate signature
            sign = self._generate_wechat_signature(close_data)
            close_data['sign'] = sign

            # Make API request
            response = requests.post(url, json=close_data, timeout=30)
            
            if response.status_code == 200:
                result = response.json()
                
                if result.get('return_code') == 'SUCCESS':
                    return {
                        'success': True,
                        'result_code': result.get('result_code'),
                        'result_msg': result.get('result_msg')
                    }
                else:
                    return {
                        'success': False,
                        'error': result.get('return_msg', 'Unknown error')
                    }
            else:
                return {
                    'success': False,
                    'error': f'WeChat Pay API error: {response.text}'
                }

        except Exception as e:
            current_app.logger.error(f"WeChat Pay order close error: {e}")
            return {
                'success': False,
                'error': str(e)
            }
