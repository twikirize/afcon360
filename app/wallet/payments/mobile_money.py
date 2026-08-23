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
from typing import Optional, Dict, Any
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

    def initiate_deposit(self, *, user_id: int, account_id: str, amount: Decimal,
                          currency: str, phone_number: str,
                          idempotency_key: Optional[str] = None) -> Dict:
        """Initiate an async mobile money deposit (push / STK) WITHOUT crediting.

        This is the real, trackable flow:
          1. create pending audit record
          2. send provider push request
          3. store a pending deposit intent in Redis (keyed by our reference)
          4. return 'pending' to the caller

        The wallet ledger is credited ONLY when the provider webhook confirms
        (see verify_webhook). Crediting on the initial API response would inflate
        balances for pushes the user never approves.
        """
        from flask import request
        from app.wallet.services.deposit_intent import (
            save_deposit_intent, generate_deposit_reference
        )

        audit_transaction_id = f"DEP-{uuid.uuid4().hex[:12].upper()}"
        reference = idempotency_key or generate_deposit_reference("MM")
        provider_request_id = f"MM{self.operator.upper()}-{uuid.uuid4().hex[:12].upper()}"

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
                payment_method=f"{self.operator}_mobile_money",
                payment_provider=f"{self.operator}_{self.country}",
                ip_address=request.remote_addr if request else None,
                user_agent=request.user_agent.string if request else None,
                metadata={
                    "idempotency_key": reference,
                    "provider_request_id": provider_request_id,
                    "phone_number": phone_number,
                    "operator": self.operator,
                    "country": self.country,
                    "stage": "initiating_push"
                }
            )
        except Exception as e:
            current_app.logger.error(f"Audit create failed: {e}")

        provider_reference = None
        try:
            if self.operator == 'mtn' and self.country == 'UG':
                result = self._mtn_uganda_deposit(amount, phone_number, audit_transaction_id)
            elif self.operator == 'airtel' and self.country == 'UG':
                result = self._airtel_uganda_deposit(amount, phone_number, audit_transaction_id)
            elif self.operator == 'safaricom' and self.country == 'KE':
                result = self._mpesa_deposit(amount, phone_number, audit_transaction_id)
            elif self.operator == 'mtn' and self.country == 'NG':
                result = self._mtn_nigeria_deposit(amount, phone_number, audit_transaction_id)
            elif self.operator == 'airtel' and self.country == 'NG':
                result = self._airtel_nigeria_deposit(amount, phone_number, audit_transaction_id)
            else:
                return {
                    'success': False, 'status': 'failed',
                    'error': f'Operator {self.operator} in {self.country} not supported'
                }

            if isinstance(result, dict):
                provider_reference = (
                    result.get('reference')
                    or result.get('CheckoutRequestID')
                    or result.get('provider_reference')
                )
        except Exception as e:
            current_app.logger.error(f"Mobile money push failed: {e}")
            return {
                'success': False, 'status': 'failed', 'error': str(e),
                'audit_transaction_id': audit_transaction_id
            }

        # Persist pending intent so the confirming webhook credits the right wallet.
        save_deposit_intent(reference, {
            'account_id': str(account_id),
            'user_id': int(user_id),
            'amount': str(amount),
            'currency': currency,
            'source': 'mobile_money',
            'operator': self.operator,
            'country': self.country,
            'phone_number': phone_number,
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
            'provider_reference': provider_reference,
            'audit_transaction_id': audit_transaction_id,
            'message': 'Check your phone and enter your PIN to approve the deposit.'
        }

    def _validate_webhook_signature(self, payload_raw: bytes, headers: Dict[str, str]) -> bool:
        """Validate the webhook signature using HMAC-SHA256."""
        import hmac
        import hashlib
        
        # Determine the expected header and secret based on operator
        sig_header = headers.get('X-Provider-Signature') or headers.get('X-Hub-Signature') or headers.get('X-Signature')
        secret = current_app.config.get(f"{self.operator.upper()}_{self.country.upper()}_WEBHOOK_SECRET")
        
        # If no secret is configured, fallback to IP validation or fail securely.
        # For this legal/invulnerable system, we require the secret or we fail.
        if not secret or not sig_header:
            current_app.logger.warning(f"Missing signature or secret for {self.operator}_{self.country} webhook")
            return False
            
        computed_sig = hmac.new(
            secret.encode('utf-8'),
            payload_raw,
            hashlib.sha256
        ).hexdigest()
        
        return hmac.compare_digest(computed_sig, sig_header)

    def verify_webhook(self, payload: Dict[str, Any], headers: Dict[str, str],
                      audit_transaction_id: str = None, raw_payload: bytes = b'') -> Dict:
        """
        Verify a mobile money provider webhook and credit the wallet ledger.

        The confirming webhook is resolved to the wallet account through the
        pending deposit intent stored at initiation time. Only then is the
        ledger credited (system-initiated, outside any user session) — so the
        balance can never be inflated by a push the user never approved.
        """
        from app.wallet.services.deposit_intent import (
            consume_deposit_intent, mark_deposit_intent_status
        )

        # Validate Signature
        if raw_payload and not self._validate_webhook_signature(raw_payload, headers):
            current_app.logger.error(f"Mobile money webhook signature validation failed")
            return {'success': False, 'error': 'Invalid signature'}

        try:
            status = (str(payload.get('status') or '')).lower()
            reference = (
                payload.get('reference')
                or payload.get('tx_ref')
                or payload.get('CheckoutRequestID')
                or (payload.get('data') or {}).get('tx_ref')
            )

            # Resolve the pending intent created at initiation.
            intent = consume_deposit_intent(reference) if reference else None
            if not intent:
                current_app.logger.warning(
                    f"Mobile money webhook: no pending intent for reference {reference}"
                )
                return {'success': False, 'error': 'Unknown or expired deposit reference'}

            account_id = intent['account_id']
            user_id = intent['user_id']
            # Trust the amount/currency we initiated with (defence vs tampering).
            amount = Decimal(str(intent['amount']))
            currency = intent['currency']

            if status in ('success', 'completed', 'paid', 'successful'):
                current_balance = self.wallet_service.get_balance(user_id)
                balance_before = Decimal(current_balance.get('balance_home', '0'))

                deposit_result = self.wallet_service.deposit(
                    account_id=str(account_id),
                    amount=amount,
                    currency=currency,
                    client_request_id=intent['reference'],
                    system_initiated=True,
                    payment_provider=f"{intent['operator']}_{intent['country']}",
                    payment_method=f"{intent['operator']}_mobile_money",
                    external_reference=reference or intent.get('provider_reference'),
                    metadata={
                        "source": "mobile_money",
                        "provider": f"{intent['operator']}_{intent['country']}",
                        "provider_transaction_id": reference,
                        "provider_reference": intent.get('provider_reference'),
                        "phone_number": intent.get('phone_number'),
                        "webhook_status": status,
                        "audit_transaction_id": intent.get('audit_transaction_id'),
                    }
                )

                mark_deposit_intent_status(intent['reference'], 'completed')

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
                            payment_method=f"{intent['operator']}_mobile_money",
                            payment_provider=f"{intent['operator']}_{intent['country']}",
                            api_call_status=APICallStatus.SUCCESS,
                            metadata={
                                "provider_transaction_id": reference,
                                "webhook_status": status,
                                "stage": "webhook_processed"
                            }
                        )
                    except Exception as e:
                        current_app.logger.error(f"Audit update failed: {e}")

                    return {
                        'success': True,
                        'message': 'Mobile money deposit completed',
                        'reference': reference,
                        'account_id': str(account_id),
                    }
                else:
                    return {
                        'success': False,
                        'error': 'Failed to deposit to wallet',
                        'detail': deposit_result,
                    }
            else:
                mark_deposit_intent_status(intent['reference'], 'failed')
                try:
                    AuditService.financial(
                        transaction_id=intent.get('audit_transaction_id'),
                        transaction_type=TransactionType.DEPOSIT,
                        amount=amount,
                        currency=currency,
                        status="failed",
                        payment_method=f"{intent['operator']}_mobile_money",
                        payment_provider=f"{intent['operator']}_{intent['country']}",
                        api_call_status=APICallStatus.SUCCESS,
                        metadata={
                            "provider_transaction_id": reference,
                            "webhook_status": status,
                            "stage": "webhook_failed"
                        }
                    )
                except Exception as e:
                    current_app.logger.error(f"Audit update failed: {e}")

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


def handle_mobile_money_webhook(payload: Dict[str, Any],
                                 headers: Dict[str, str], raw_payload: bytes = b'') -> Dict:
    """Module entry point for the provider webhook.

    The operator/country needed to build the service are stored on the pending
    deposit intent, so we peek at it to construct the correct gateway before
    delegating to verify_webhook (which consumes the intent and credits).
    """
    from app.wallet.services.deposit_intent import get_deposit_intent

    reference = (
        payload.get('reference')
        or payload.get('tx_ref')
        or payload.get('CheckoutRequestID')
        or (payload.get('data') or {}).get('tx_ref')
    )
    intent = get_deposit_intent(reference) if reference else None
    operator = (intent or {}).get('operator', 'mtn')
    country = (intent or {}).get('country', 'UG')
    service = MobileMoneyService(operator, country)
    return service.verify_webhook(payload, headers, raw_payload=raw_payload)
