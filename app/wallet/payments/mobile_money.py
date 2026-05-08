# app/wallet/payments/mobile_money.py
"""
Mobile Money payment integration for African operators.

FLOW:
1. Create pending audit record
2. Call Mobile Money API
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


class MobileMoneyService:
    """
    Mobile Money payment integration for African operators.
    """

    def __init__(self, operator: str, country: str):
        self.wallet_service = WalletService()
        self.operator = operator.lower()  # mtn, airtel, safaricom, etc.
        self.country = country.upper()  # UG, KE, NG, etc.
        self.sandbox = current_app.config.get('MOBILE_MONEY_SANDBOX', True)

    def process_deposit(
        self,
        user_id: int,
        amount: Decimal,
        currency: str,
        phone_number: str,
        idempotency_key: Optional[str] = None
    ) -> Dict:
        """
        Process mobile money deposit with correct ordering.
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
        provider_request_id = f"MM{self.operator.upper()}-{uuid.uuid4().hex[:12].upper()}"

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
                payment_method=f"{self.operator}_mobile_money",
                payment_provider=f"{self.operator}_{self.country}",
                ip_address=request.remote_addr if request else None,
                user_agent=request.user_agent.string if request else None,
                metadata={
                    "idempotency_key": idempotency_key,
                    "provider_request_id": provider_request_id,
                    "phone_number": phone_number,
                    "operator": self.operator,
                    "country": self.country,
                    "stage": "calling_provider"
                }
            )
        except Exception as e:
            current_app.logger.error(f"Audit create failed: {e}")

        # STEP 4: Call Mobile Money API
        provider_response = None
        provider_success = False
        provider_error = None
        provider_reference = None
        start_time = datetime.now(timezone.utc)

        try:
            if self.operator == 'mtn' and self.country == 'UG':
                result = self._mtn_uganda_deposit(
                    amount, phone_number, audit_transaction_id
                )
            elif self.operator == 'airtel' and self.country == 'UG':
                result = self._airtel_uganda_deposit(
                    amount, phone_number, audit_transaction_id
                )
            elif self.operator == 'safaricom' and self.country == 'KE':
                result = self._mpesa_deposit(
                    amount, phone_number, audit_transaction_id
                )
            elif self.operator == 'mtn' and self.country == 'NG':
                result = self._mtn_nigeria_deposit(
                    amount, phone_number, audit_transaction_id
                )
            elif self.operator == 'airtel' and self.country == 'NG':
                result = self._airtel_nigeria_deposit(
                    amount, phone_number, audit_transaction_id
                )
            else:
                raise Exception(f"Operator {self.operator} in {self.country} not supported")

            provider_response = result
            provider_success = result.get('success', False)
            provider_reference = result.get('reference')
            response_time_ms = int((datetime.now(timezone.utc) - start_time).total_seconds() * 1000)

        except Exception as e:
            provider_error = str(e)
            current_app.logger.error(f"Mobile Money API error: {e}")

        # STEP 5: Update audit record based on provider response
        if provider_success:
            try:
                # Deposit to wallet
                deposit_result = self.wallet_service.deposit(
                    user_id=user_id,
                    amount=amount,
                    currency=currency,
                    reference=f"{self.operator} mobile money deposit - {provider_reference}",
                    metadata={
                        "provider": f"{self.operator}_{self.country}",
                        "provider_transaction_id": provider_reference,
                        "audit_transaction_id": audit_transaction_id,
                        "phone_number": phone_number,
                        "operator": self.operator,
                        "country": self.country
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
                        payment_method=f"{self.operator}_mobile_money",
                        payment_provider=f"{self.operator}_{self.country}",
                        ip_address=request.remote_addr if request else None,
                        user_agent=request.user_agent.string if request else None,
                        api_call_status=APICallStatus.SUCCESS,
                        response_time_ms=response_time_ms,
                        metadata={
                            "provider_request_id": provider_request_id,
                            "provider_reference": provider_reference,
                            "phone_number": phone_number,
                            "stage": "completed"
                        }
                    )

                    return {
                        'success': True,
                        'audit_transaction_id': audit_transaction_id,
                        'provider_reference': provider_reference,
                        'amount': float(amount),
                        'currency': currency
                    }
                else:
                    return {
                        'success': False,
                        'error': 'Failed to deposit to wallet'
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
                    payment_method=f"{self.operator}_mobile_money",
                    payment_provider=f"{self.operator}_{self.country}",
                    ip_address=request.remote_addr if request else None,
                    user_agent=request.user_agent.string if request else None,
                    api_call_status=APICallStatus.FAILED,
                    metadata={
                        "provider_request_id": provider_request_id,
                        "error": provider_error,
                        "phone_number": phone_number,
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

    def _mtn_uganda_deposit(self, amount: Decimal, phone_number: str, 
                              reference: str) -> Dict:
        """MTN Mobile Money Uganda deposit"""
        url = "https://api.mtn.co.ug/momo/api/v1/deposit"
        if self.sandbox:
            url = "https://sandbox.mtn.co.ug/momo/api/v1/deposit"

        headers = {
            'Authorization': f'Bearer {current_app.config["MTN_UG_API_KEY"]}',
            'Content-Type': 'application/json'
        }

        payload = {
            'amount': float(amount),
            'phone_number': phone_number,
            'reference': reference,
            'currency': 'UGX',
            'description': f"AFCON360 deposit - {reference}"
        }

        response = requests.post(url, headers=headers, json=payload)

        if response.status_code == 200:
            return response.json()

        raise Exception(f"MTN Mobile Money deposit failed: {response.text}")

    def _airtel_uganda_deposit(self, amount: Decimal, phone_number: str,
                                reference: str) -> Dict:
        """Airtel Money Uganda deposit"""
        url = "https://api.airtel.com/airtel-money/api/v1/deposit"
        if self.sandbox:
            url = "https://sandbox.airtel.com/airtel-money/api/v1/deposit"

        headers = {
            'Authorization': f'Bearer {current_app.config["AIRTEL_UG_API_KEY"]}',
            'Content-Type': 'application/json'
        }

        payload = {
            'amount': float(amount),
            'phone_number': phone_number,
            'reference': reference,
            'currency': 'UGX',
            'description': f"AFCON360 deposit - {reference}"
        }

        response = requests.post(url, headers=headers, json=payload)

        if response.status_code == 200:
            return response.json()

        raise Exception(f"Airtel Money deposit failed: {response.text}")

    def _mpesa_deposit(self, amount: Decimal, phone_number: str,
                       reference: str) -> Dict:
        """M-PESA Kenya deposit - Enhanced with STK Push and proper error handling"""
        url = "https://api.safaricom.co.ke/mpesa/stkpush/v1/processrequest"
        if self.sandbox:
            url = "https://sandbox.safaricom.co.ke/mpesa/stkpush/v1/processrequest"

        headers = {
            'Authorization': f'Bearer {current_app.config["MPESA_API_KEY"]}',
            'Content-Type': 'application/json'
        }

        # Generate timestamp and password
        import base64
        from datetime import datetime
        timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
        password = base64.b64encode(current_app.config['MPESA_PASSKEY'].encode()).decode()

        payload = {
            'BusinessShortCode': current_app.config['MPESA_BUSINESS_SHORT_CODE'],
            'TransactionType': 'CustomerPayBillOnline',
            'Amount': int(amount),  # M-PESA uses smallest unit
            'PhoneNumber': phone_number,
            'CallBackURL': current_app.config['MPESA_CALLBACK_URL'],
            'AccountReference': reference,
            'TransactionDesc': f"AFCON360 wallet deposit - {reference}",
            'Timestamp': timestamp,
            'Password': password
        }

        try:
            response = requests.post(url, json=payload, headers=headers, timeout=30)
            
            if response.status_code == 200:
                result = response.json()
                
                # Check if STK push was initiated successfully
                if result.get('ResponseCode') == '0':
                    return {
                        'success': True,
                        'CheckoutRequestID': result.get('CheckoutRequestID'),
                        'CustomerMessage': result.get('CustomerMessage'),
                        'MerchantRequestID': result.get('MerchantRequestID'),
                        'ResponseCode': result.get('ResponseCode'),
                        'ResponseDescription': result.get('ResponseDescription')
                    }
                else:
                    return {
                        'success': False,
                        'error': result.get('errorMessage', 'M-PESA STK push failed'),
                        'ResponseCode': result.get('ResponseCode'),
                        'ResponseDescription': result.get('ResponseDescription')
                    }
            else:
                return {
                    'success': False,
                    'error': f"M-PESA API error: {response.text}",
                    'status_code': response.status_code
                }
                
        except requests.exceptions.RequestException as e:
            current_app.logger.error(f"M-PESA API request failed: {e}")
            return {
                'success': False,
                'error': f"Network error: {str(e)}"
            }
        except Exception as e:
            current_app.logger.error(f"M-PESA deposit error: {e}")
            return {
                'success': False,
                'error': f"Processing error: {str(e)}"
            }
        if self.sandbox:
            url = "https://sandbox.safaricom.co.ke/mpesa/stkpush/v1/processrequest"

        headers = {
            'Authorization': f'Bearer {current_app.config["MPESA_API_KEY"]}',
            'Content-Type': 'application/json'
        }

        payload = {
            'BusinessShortCode': current_app.config['MPESA_BUSINESS_SHORT_CODE'],
            'TransactionType': 'CustomerPayBillOnline',
            'Amount': int(amount),  # M-PESA uses smallest unit
            'PhoneNumber': phone_number,
            'CallBackURL': current_app.config['MPESA_CALLBACK_URL'],
            'AccountReference': reference,
            'TransactionDesc': f"AFCON360 deposit - {reference}",
            'Timestamp': datetime.now().strftime('%Y%m%d%H%M%S')
        }

        response = requests.post(url, headers=headers, json=payload)

        if response.status_code == 200:
            return response.json()

        raise Exception(f"M-PESA deposit failed: {response.text}")

    def _mtn_nigeria_deposit(self, amount: Decimal, phone_number: str,
                              reference: str) -> Dict:
        """MTN Mobile Money Nigeria deposit"""
        url = "https://api.mtn.com.ng/momo/api/v1/deposit"
        if self.sandbox:
            url = "https://sandbox.mtn.com.ng/momo/api/v1/deposit"

        headers = {
            'Authorization': f'Bearer {current_app.config["MTN_NG_API_KEY"]}',
            'Content-Type': 'application/json'
        }

        payload = {
            'amount': float(amount),
            'phone_number': phone_number,
            'reference': reference,
            'currency': 'NGN',
            'description': f"AFCON360 deposit - {reference}"
        }

        response = requests.post(url, headers=headers, json=payload)

        if response.status_code == 200:
            return response.json()

        raise Exception(f"MTN Nigeria Mobile Money deposit failed: {response.text}")

    def _airtel_nigeria_deposit(self, amount: Decimal, phone_number: str,
                                reference: str) -> Dict:
        """Airtel Money Nigeria deposit"""
        url = "https://api.airtel.com.ng/airtel-money/api/v1/deposit"
        if self.sandbox:
            url = "https://sandbox.airtel.com.ng/airtel-money/api/v1/deposit"

        headers = {
            'Authorization': f'Bearer {current_app.config["AIRTEL_NG_API_KEY"]}',
            'Content-Type': 'application/json'
        }

        payload = {
            'amount': float(amount),
            'phone_number': phone_number,
            'reference': reference,
            'currency': 'NGN',
            'description': f"AFCON360 deposit - {reference}"
        }

        response = requests.post(url, headers=headers, json=payload)

        if response.status_code == 200:
            return response.json()

        raise Exception(f"Airtel Nigeria deposit failed: {response.text}")

    def verify_webhook(self, payload: Dict[str, Any], headers: Dict[str, str],
                      audit_transaction_id: str) -> Dict:
        """
        Verify mobile money webhook and process deposit.
        """
        try:
            # Extract payment details
            status = payload.get('status')
            reference = payload.get('reference')
            amount = Decimal(str(payload.get('amount', '0')))
            currency = payload.get('currency')
            phone_number = payload.get('phone_number')

            if status == 'success':
                # Get user ID from reference or metadata
                # This would need to be stored/retrieved from audit log
                user_id = 1  # Placeholder - should get from audit
                
                # Get current balance
                current_balance = self.wallet_service.get_balance(user_id)
                balance_before = Decimal(current_balance.get('balance_home', '0'))

                # Deposit to wallet
                deposit_result = self.wallet_service.deposit(
                    user_id=user_id,
                    amount=amount,
                    currency=currency,
                    reference=f"{self.operator} mobile money {reference}",
                    metadata={
                        "provider": f"{self.operator}_{self.country}",
                        "provider_transaction_id": reference,
                        "audit_transaction_id": audit_transaction_id,
                        "phone_number": phone_number,
                        "webhook_status": status
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
                        payment_method=f"{self.operator}_mobile_money",
                        payment_provider=f"{self.operator}_{self.country}",
                        api_call_status=APICallStatus.SUCCESS,
                        metadata={
                            "provider_transaction_id": reference,
                            "webhook_status": status,
                            "stage": "webhook_processed"
                        }
                    )

                    return {
                        'success': True,
                        'message': 'Mobile money deposit completed',
                        'reference': reference
                    }
                else:
                    return {
                        'success': False,
                        'error': 'Failed to deposit to wallet'
                    }
            else:
                # Update audit with webhook status
                AuditService.financial(
                    transaction_id=audit_transaction_id,
                    transaction_type=TransactionType.DEPOSIT,
                    amount=amount,
                    currency=currency,
                    status="failed",
                    payment_method=f"{self.operator}_mobile_money",
                    payment_provider=f"{self.operator}_{self.country}",
                    api_call_status=APICallStatus.SUCCESS,
                    metadata={
                        "provider_transaction_id": reference,
                        "webhook_status": status,
                        "stage": "webhook_failed"
                    }
                )

                return {
                    'success': False,
                    'error': f'Webhook status: {status}'
                }

        except Exception as e:
            current_app.logger.error(f"Mobile money webhook error: {e}")
            return {
                'success': False,
                'error': str(e)
            }
