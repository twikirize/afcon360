"""
Payment Gateway Integration Layer
Supports Flutterwave, Paystack, MTN Mobile Money, Visa, MasterCard
"""

from abc import ABC, abstractmethod
from enum import Enum
from typing import Optional, Dict, Any, Callable
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import hmac
import json
import requests
from flask import current_app

from app.extensions import db, redis_client
from app.wallet.exceptions import PaymentError, InsufficientFundsError
from app.wallet.models.transaction import TransactionModel, TransactionStatus, TransactionType
from app.wallet.services.wallet_service import WalletService


class PaymentProvider(Enum):
    FLUTTERWAVE = "flutterwave"
    PAYSTACK = "paystack"
    MTN_MOMO = "mtn_momo"
    AIRTEL_MONEY = "airtel_money"
    VISA = "visa"
    MASTERCARD = "mastercard"
    UNIONPAY = "unionpay"
    BANK_TRANSFER = "bank_transfer"


class PaymentMethod(Enum):
    CARD = "card"
    BANK_TRANSFER = "bank_transfer"
    MOBILE_MONEY = "mobile_money"
    USSD = "ussd"
    QR_CODE = "qr_code"


@dataclass
class PaymentRequest:
    amount: float
    currency: str
    user_id: int
    provider: PaymentProvider
    method: PaymentMethod
    email: str
    phone: Optional[str] = None
    card_number: Optional[str] = None
    cvv: Optional[str] = None
    expiry_month: Optional[str] = None
    expiry_year: Optional[str] = None
    bank_code: Optional[str] = None
    account_number: Optional[str] = None
    mobile_money_provider: Optional[str] = None
    callback_url: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


@dataclass
class PaymentResponse:
    success: bool
    transaction_id: Optional[str]
    provider_reference: Optional[str]
    status: str
    message: str
    authorization_url: Optional[str] = None
    requires_3ds: bool = False
    error_code: Optional[str] = None


@dataclass
class PayoutRequest:
    amount: float
    currency: str
    user_id: int
    recipient_name: str
    recipient_account: str
    recipient_bank_code: Optional[str] = None
    recipient_phone: Optional[str] = None
    provider: PaymentProvider = PaymentProvider.FLUTTERWAVE
    reason: Optional[str] = None
    reference: Optional[str] = None


@dataclass
class PayoutResponse:
    success: bool
    payout_id: Optional[str]
    provider_reference: Optional[str]
    status: str
    message: str
    error_code: Optional[str] = None


class BasePaymentGateway(ABC):
    """Abstract base class for payment gateways"""
    
    def __init__(self, provider: PaymentProvider):
        self.provider = provider
        self.config = current_app.config.get(f'{provider.value.upper()}_CONFIG', {})
        self.is_sandbox = current_app.config.get('PAYMENT_SANDBOX', True)
    
    @abstractmethod
    def initiate_payment(self, request: PaymentRequest) -> PaymentResponse:
        """Initiate a payment transaction"""
        pass
    
    @abstractmethod
    def verify_payment(self, transaction_ref: str) -> PaymentResponse:
        """Verify a payment status"""
        pass
    
    @abstractmethod
    def initiate_payout(self, request: PayoutRequest) -> PayoutResponse:
        """Initiate a payout/transfer"""
        pass
    
    @abstractmethod
    def verify_payout(self, payout_ref: str) -> PayoutResponse:
        """Verify a payout status"""
        pass
    
    @abstractmethod
    def handle_webhook(self, payload: Dict[str, Any], signature: str) -> bool:
        """Handle incoming webhook from provider"""
        pass
    
    def _generate_reference(self, prefix: str = "TXN") -> str:
        """Generate unique transaction reference"""
        timestamp = datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')
        random_hash = hashlib.md5(str(datetime.now(timezone.utc)).encode()).hexdigest()[:6]
        return f"{prefix}_{timestamp}_{random_hash}"
    
    def _get_cache_key(self, key: str) -> str:
        return f"payment:{self.provider.value}:{key}"
    
    def _cache_transaction(self, ref: str, data: Dict, ttl: int = 3600):
        """Cache transaction data in Redis"""
        key = self._get_cache_key(ref)
        redis_client.setex(key, ttl, json.dumps(data))
    
    def _get_cached_transaction(self, ref: str) -> Optional[Dict]:
        """Get cached transaction data"""
        key = self._get_cache_key(ref)
        data = redis_client.get(key)
        return json.loads(data) if data else None


class FlutterwaveGateway(BasePaymentGateway):
    """Flutterwave payment integration for Africa"""
    
    def __init__(self):
        super().__init__(PaymentProvider.FLUTTERWAVE)
        self.secret_key = self.config.get('SECRET_KEY') or current_app.config.get('FLUTTERWAVE_SECRET_KEY')
        self.public_key = self.config.get('PUBLIC_KEY') or current_app.config.get('FLUTTERWAVE_PUBLIC_KEY')
        self.encryption_key = self.config.get('ENCRYPTION_KEY') or current_app.config.get('FLUTTERWAVE_ENCRYPTION_KEY')
        self.base_url = "https://api.flutterwave.com/v3" if not self.is_sandbox else "https://api.flutterwave.com/v3"
        
        if not self.secret_key:
            raise PaymentError("Flutterwave secret key not configured")
    
    def initiate_payment(self, request: PaymentRequest) -> PaymentResponse:
        """Initiate Flutterwave payment"""
        reference = self._generate_reference("FW")
        
        payload = {
            "tx_ref": reference,
            "amount": str(request.amount),
            "currency": request.currency,
            "redirect_url": request.callback_url or current_app.config.get('FLUTTERWAVE_CALLBACK_URL'),
            "customer": {
                "email": request.email,
                "phonenumber": request.phone or "",
                "name": f"User {request.user_id}"
            },
            "customizations": {
                "title": "AFCON360 Payment",
                "description": "Wallet deposit",
                "logo": current_app.config.get('APP_LOGO_URL', "")
            },
            "meta": {
                "user_id": request.user_id,
                "provider": "flutterwave",
                **(request.metadata or {})
            }
        }
        
        if request.method == PaymentMethod.CARD and request.card_number:
            payload["payment_type"] = "card"
            payload["card_number"] = request.card_number
            payload["cvv"] = request.cvv
            payload["expiry_month"] = request.expiry_month
            payload["expiry_year"] = request.expiry_year
        elif request.method == PaymentMethod.MOBILE_MONEY:
            payload["payment_type"] = "mobilemoney"
            if request.mobile_money_provider:
                payload["network"] = request.mobile_money_provider
        elif request.method == PaymentMethod.USSD:
            payload["payment_type"] = "ussd"
        elif request.method == PaymentMethod.BANK_TRANSFER:
            payload["payment_type"] = "bank_transfer"
            if request.bank_code and request.account_number:
                payload["bank_transfer"] = {
                    "bank_code": request.bank_code,
                    "account_number": request.account_number
                }
        
        try:
            headers = {
                "Authorization": f"Bearer {self.secret_key}",
                "Content-Type": "application/json"
            }
            
            response = requests.post(
                f"{self.base_url}/payments",
                json=payload,
                headers=headers,
                timeout=30
            )
            response.raise_for_status()
            data = response.json()
            
            if data.get("status") == "success":
                result = data.get("data", {})
                
                self._cache_transaction(reference, {
                    "user_id": request.user_id,
                    "amount": request.amount,
                    "currency": request.currency,
                    "provider": "flutterwave",
                    "status": "pending"
                })
                
                return PaymentResponse(
                    success=True,
                    transaction_id=reference,
                    provider_reference=result.get("id"),
                    status="pending",
                    message="Payment initiated",
                    authorization_url=result.get("link"),
                    requires_3ds=result.get("meta", {}).get("authorization", {}).get("mode") == "redirect"
                )
            else:
                return PaymentResponse(
                    success=False,
                    transaction_id=None,
                    provider_reference=None,
                    status="failed",
                    message=data.get("message", "Payment initiation failed"),
                    error_code=data.get("code")
                )
                
        except requests.RequestException as e:
            current_app.logger.error(f"Flutterwave payment error: {str(e)}")
            return PaymentResponse(
                success=False,
                transaction_id=None,
                provider_reference=None,
                status="error",
                message=f"Payment service error: {str(e)}"
            )
    
    def verify_payment(self, transaction_ref: str) -> PaymentResponse:
        """Verify Flutterwave transaction"""
        try:
            headers = {
                "Authorization": f"Bearer {self.secret_key}"
            }
            
            response = requests.get(
                f"{self.base_url}/transactions/{transaction_ref}/verify",
                headers=headers,
                timeout=30
            )
            response.raise_for_status()
            data = response.json()
            
            if data.get("status") == "success":
                result = data.get("data", {})
                tx_status = result.get("status", "").lower()
                
                status_map = {
                    "successful": "completed",
                    "pending": "pending",
                    "failed": "failed",
                    "cancelled": "cancelled"
                }
                
                return PaymentResponse(
                    success=tx_status == "successful",
                    transaction_id=transaction_ref,
                    provider_reference=str(result.get("id")),
                    status=status_map.get(tx_status, "unknown"),
                    message=result.get("processor_response", "")
                )
            else:
                return PaymentResponse(
                    success=False,
                    transaction_id=transaction_ref,
                    provider_reference=None,
                    status="failed",
                    message=data.get("message", "Verification failed")
                )
                
        except requests.RequestException as e:
            current_app.logger.error(f"Flutterwave verification error: {str(e)}")
            return PaymentResponse(
                success=False,
                transaction_id=transaction_ref,
                provider_reference=None,
                status="error",
                message=f"Verification error: {str(e)}"
            )
    
    def initiate_payout(self, request: PayoutRequest) -> PayoutResponse:
        """Initiate Flutterwave transfer/payout"""
        reference = request.reference or self._generate_reference("FW-PAYOUT")
        
        payload = {
            "account_bank": request.recipient_bank_code,
            "account_number": request.recipient_account,
            "amount": request.amount,
            "narration": request.reason or "Wallet withdrawal",
            "currency": request.currency,
            "reference": reference,
            "callback_url": current_app.config.get('FLUTTERWAVE_TRANSFER_CALLBACK'),
            "meta": {
                "user_id": request.user_id,
                "sender": "AFCON360"
            }
        }
        
        if request.recipient_phone and not request.recipient_bank_code:
            payload = {
                "amount": request.amount,
                "currency": request.currency,
                "reference": reference,
                "beneficiary_name": request.recipient_name,
                "meta": {
                    "user_id": request.user_id,
                    "sender": "AFCON360",
                    "mobile_number": request.recipient_phone
                }
            }
        
        try:
            headers = {
                "Authorization": f"Bearer {self.secret_key}",
                "Content-Type": "application/json"
            }
            
            response = requests.post(
                f"{self.base_url}/transfers",
                json=payload,
                headers=headers,
                timeout=30
            )
            response.raise_for_status()
            data = response.json()
            
            if data.get("status") == "success":
                result = data.get("data", {})
                return PayoutResponse(
                    success=True,
                    payout_id=reference,
                    provider_reference=str(result.get("id")),
                    status="pending",
                    message="Transfer initiated"
                )
            else:
                return PayoutResponse(
                    success=False,
                    payout_id=reference,
                    provider_reference=None,
                    status="failed",
                    message=data.get("message", "Transfer failed"),
                    error_code=data.get("code")
                )
                
        except requests.RequestException as e:
            current_app.logger.error(f"Flutterwave payout error: {str(e)}")
            return PayoutResponse(
                success=False,
                payout_id=reference,
                provider_reference=None,
                status="error",
                message=f"Transfer service error: {str(e)}"
            )
    
    def verify_payout(self, payout_ref: str) -> PayoutResponse:
        """Verify Flutterwave transfer status"""
        try:
            headers = {
                "Authorization": f"Bearer {self.secret_key}"
            }
            
            response = requests.get(
                f"{self.base_url}/transfers/{payout_ref}",
                headers=headers,
                timeout=30
            )
            response.raise_for_status()
            data = response.json()
            
            if data.get("status") == "success":
                result = data.get("data", {})
                status = result.get("status", "").lower()
                
                return PayoutResponse(
                    success=status == "successful",
                    payout_id=payout_ref,
                    provider_reference=str(result.get("id")),
                    status=status,
                    message=result.get("complete_message", "")
                )
            else:
                return PayoutResponse(
                    success=False,
                    payout_id=payout_ref,
                    provider_reference=None,
                    status="failed",
                    message=data.get("message", "Verification failed")
                )
                
        except requests.RequestException as e:
            return PayoutResponse(
                success=False,
                payout_id=payout_ref,
                provider_reference=None,
                status="error",
                message=f"Verification error: {str(e)}"
            )
    
    def handle_webhook(self, payload: Dict[str, Any], signature: str) -> bool:
        """Handle Flutterwave webhook"""
        expected_hash = hmac.new(
            self.secret_key.encode(),
            json.dumps(payload, separators=(',', ':')).encode(),
            hashlib.sha256
        ).hexdigest()
        
        if not hmac.compare_digest(expected_hash, signature):
            current_app.logger.warning("Invalid Flutterwave webhook signature")
            return False
        
        event_type = payload.get("event")
        data = payload.get("data", {})
        
        if event_type == "charge.completed":
            tx_ref = data.get("txRef")
            status = data.get("status")
            amount = data.get("amount")
            currency = data.get("currency")
            
            cached = self._get_cached_transaction(tx_ref)
            if cached and status == "successful":
                self._process_successful_deposit(cached.get("user_id"), amount, currency, tx_ref)
        
        elif event_type == "transfer.completed":
            transfer_ref = data.get("reference")
            status = data.get("status")
            if status == "successful":
                self._mark_payout_completed(transfer_ref)
        
        return True
    
    def _process_successful_deposit(self, user_id: int, amount: float, currency: str, reference: str):
        """Process a successful deposit webhook"""
        try:
            wallet_service = WalletService()
            wallet_service.deposit(
                user_id=user_id,
                amount=amount,
                currency=currency,
                client_request_id=reference,
                metadata={"source": "flutterwave", "reference": reference}
            )
        except Exception as e:
            current_app.logger.error(f"Failed to process deposit {reference}: {str(e)}")
    
    def _mark_payout_completed(self, reference: str):
        current_app.logger.info(f"Payout completed: {reference}")


class PaystackGateway(BasePaymentGateway):
    """Paystack payment integration for Nigeria/Ghana"""
    
    def __init__(self):
        super().__init__(PaymentProvider.PAYSTACK)
        self.secret_key = self.config.get('SECRET_KEY') or current_app.config.get('PAYSTACK_SECRET_KEY')
        self.public_key = self.config.get('PUBLIC_KEY') or current_app.config.get('PAYSTACK_PUBLIC_KEY')
        self.base_url = "https://api.paystack.co"
        
        if not self.secret_key:
            raise PaymentError("Paystack secret key not configured")
    
    def initiate_payment(self, request: PaymentRequest) -> PaymentResponse:
        """Initiate Paystack payment"""
        reference = self._generate_reference("PS")
        
        payload = {
            "email": request.email,
            "amount": int(request.amount * 100),
            "currency": request.currency,
            "reference": reference,
            "callback_url": request.callback_url or current_app.config.get('PAYSTACK_CALLBACK_URL'),
            "metadata": {
                "user_id": request.user_id,
                "cancel_action": current_app.config.get('PAYMENT_CANCEL_URL'),
                **(request.metadata or {})
            }
        }
        
        if request.method == PaymentMethod.CARD:
            payload["channels"] = ["card"]
        elif request.method == PaymentMethod.BANK_TRANSFER:
            payload["channels"] = ["bank_transfer"]
        elif request.method == PaymentMethod.USSD:
            payload["channels"] = ["ussd"]
        elif request.method == PaymentMethod.QR_CODE:
            payload["channels"] = ["qr"]
        
        try:
            headers = {
                "Authorization": f"Bearer {self.secret_key}",
                "Content-Type": "application/json"
            }
            
            response = requests.post(
                f"{self.base_url}/transaction/initialize",
                json=payload,
                headers=headers,
                timeout=30
            )
            response.raise_for_status()
            data = response.json()
            
            if data.get("status"):
                result = data.get("data", {})
                
                self._cache_transaction(reference, {
                    "user_id": request.user_id,
                    "amount": request.amount,
                    "currency": request.currency,
                    "provider": "paystack",
                    "status": "pending"
                })
                
                return PaymentResponse(
                    success=True,
                    transaction_id=reference,
                    provider_reference=result.get("reference"),
                    status="pending",
                    message="Payment initialized",
                    authorization_url=result.get("authorization_url")
                )
            else:
                return PaymentResponse(
                    success=False,
                    transaction_id=None,
                    provider_reference=None,
                    status="failed",
                    message=data.get("message", "Payment initiation failed")
                )
                
        except requests.RequestException as e:
            current_app.logger.error(f"Paystack payment error: {str(e)}")
            return PaymentResponse(
                success=False,
                transaction_id=None,
                provider_reference=None,
                status="error",
                message=f"Payment service error: {str(e)}"
            )
    
    def verify_payment(self, transaction_ref: str) -> PaymentResponse:
        """Verify Paystack transaction"""
        try:
            headers = {
                "Authorization": f"Bearer {self.secret_key}"
            }
            
            response = requests.get(
                f"{self.base_url}/transaction/verify/{transaction_ref}",
                headers=headers,
                timeout=30
            )
            response.raise_for_status()
            data = response.json()
            
            if data.get("status"):
                result = data.get("data", {})
                status = result.get("status", "").lower()
                
                return PaymentResponse(
                    success=status == "success",
                    transaction_id=transaction_ref,
                    provider_reference=result.get("reference"),
                    status=status,
                    message=result.get("gateway_response", "")
                )
            else:
                return PaymentResponse(
                    success=False,
                    transaction_id=transaction_ref,
                    provider_reference=None,
                    status="failed",
                    message=data.get("message", "Verification failed")
                )
                
        except requests.RequestException as e:
            return PaymentResponse(
                success=False,
                transaction_id=transaction_ref,
                provider_reference=None,
                status="error",
                message=f"Verification error: {str(e)}"
            )
    
    def initiate_payout(self, request: PayoutRequest) -> PayoutResponse:
        """Initiate Paystack transfer"""
        reference = request.reference or self._generate_reference("PS-PAYOUT")
        
        recipient_payload = {
            "type": "nuban",
            "name": request.recipient_name,
            "account_number": request.recipient_account,
            "bank_code": request.recipient_bank_code,
            "currency": request.currency
        }
        
        try:
            headers = {
                "Authorization": f"Bearer {self.secret_key}",
                "Content-Type": "application/json"
            }
            
            recipient_response = requests.post(
                f"{self.base_url}/transferrecipient",
                json=recipient_payload,
                headers=headers,
                timeout=30
            )
            recipient_response.raise_for_status()
            recipient_data = recipient_response.json()
            
            if not recipient_data.get("status"):
                return PayoutResponse(
                    success=False,
                    payout_id=reference,
                    provider_reference=None,
                    status="failed",
                    message="Failed to create transfer recipient"
                )
            
            recipient_code = recipient_data["data"]["recipient_code"]
            
            transfer_payload = {
                "source": "balance",
                "reason": request.reason or "Wallet withdrawal",
                "amount": int(request.amount * 100),
                "recipient": recipient_code,
                "reference": reference
            }
            
            transfer_response = requests.post(
                f"{self.base_url}/transfer",
                json=transfer_payload,
                headers=headers,
                timeout=30
            )
            transfer_response.raise_for_status()
            transfer_data = transfer_response.json()
            
            if transfer_data.get("status"):
                result = transfer_data.get("data", {})
                return PayoutResponse(
                    success=True,
                    payout_id=reference,
                    provider_reference=str(result.get("id")),
                    status="pending",
                    message="Transfer initiated"
                )
            else:
                return PayoutResponse(
                    success=False,
                    payout_id=reference,
                    provider_reference=None,
                    status="failed",
                    message=transfer_data.get("message", "Transfer failed")
                )
                
        except requests.RequestException as e:
            return PayoutResponse(
                success=False,
                payout_id=reference,
                provider_reference=None,
                status="error",
                message=f"Transfer error: {str(e)}"
            )
    
    def verify_payout(self, payout_ref: str) -> PayoutResponse:
        """Verify Paystack transfer"""
        try:
            headers = {
                "Authorization": f"Bearer {self.secret_key}"
            }
            
            response = requests.get(
                f"{self.base_url}/transfer/{payout_ref}",
                headers=headers,
                timeout=30
            )
            response.raise_for_status()
            data = response.json()
            
            if data.get("status"):
                result = data.get("data", {})
                status = result.get("status", "").lower()
                
                return PayoutResponse(
                    success=status == "success",
                    payout_id=payout_ref,
                    provider_reference=str(result.get("id")),
                    status=status,
                    message=result.get("complete_message", "")
                )
            else:
                return PayoutResponse(
                    success=False,
                    payout_id=payout_ref,
                    provider_reference=None,
                    status="failed",
                    message=data.get("message", "Verification failed")
                )
                
        except requests.RequestException as e:
            return PayoutResponse(
                success=False,
                payout_id=payout_ref,
                provider_reference=None,
                status="error",
                message=f"Verification error: {str(e)}"
            )
    
    def handle_webhook(self, payload: Dict[str, Any], signature: str) -> bool:
        """Handle Paystack webhook"""
        hash = hmac.new(
            self.secret_key.encode(),
            json.dumps(payload, separators=(',', ':')).encode(),
            hashlib.sha512
        ).hexdigest()
        
        if not hmac.compare_digest(hash, signature):
            current_app.logger.warning("Invalid Paystack webhook signature")
            return False
        
        event = payload.get("event")
        data = payload.get("data", {})
        
        if event == "charge.success":
            reference = data.get("reference")
            amount = data.get("amount", 0) / 100
            currency = data.get("currency", "NGN")
            
            cached = self._get_cached_transaction(reference)
            if cached:
                self._process_successful_deposit(
                    cached.get("user_id"),
                    amount,
                    currency,
                    reference
                )
        
        elif event == "transfer.success":
            reference = data.get("reference")
            self._mark_payout_completed(reference)
        
        elif event == "transfer.failed":
            reference = data.get("reference")
            reason = data.get("complete_message", "Transfer failed")
            self._mark_payout_failed(reference, reason)
        
        return True
    
    def _process_successful_deposit(self, user_id: int, amount: float, currency: str, reference: str):
        try:
            wallet_service = WalletService()
            wallet_service.deposit(
                user_id=user_id,
                amount=amount,
                currency=currency,
                client_request_id=reference,
                metadata={"source": "paystack", "reference": reference}
            )
        except Exception as e:
            current_app.logger.error(f"Failed to process Paystack deposit: {str(e)}")
    
    def _mark_payout_completed(self, reference: str):
        current_app.logger.info(f"Paystack payout completed: {reference}")
    
    def _mark_payout_failed(self, reference: str, reason: str):
        current_app.logger.error(f"Paystack payout failed: {reference}, reason: {reason}")


class PaymentGatewayFactory:
    """Factory for creating payment gateway instances"""
    
    _gateways = {
        PaymentProvider.FLUTTERWAVE: FlutterwaveGateway,
        PaymentProvider.PAYSTACK: PaystackGateway
    }
    
    @classmethod
    def get_gateway(cls, provider: PaymentProvider) -> BasePaymentGateway:
        """Get payment gateway instance"""
        gateway_class = cls._gateways.get(provider)
        if not gateway_class:
            raise PaymentError(f"Unsupported payment provider: {provider}")
        return gateway_class()
    
    @classmethod
    def register_gateway(cls, provider: PaymentProvider, gateway_class: type):
        """Register a new payment gateway"""
        cls._gateways[provider] = gateway_class
    
    @classmethod
    def get_available_providers(cls, country_code: str = None) -> list:
        """Get available providers for a country"""
        providers = list(cls._gateways.keys())
        
        country_providers = {
            "NG": [PaymentProvider.FLUTTERWAVE, PaymentProvider.PAYSTACK],
            "GH": [PaymentProvider.FLUTTERWAVE, PaymentProvider.PAYSTACK],
            "KE": [PaymentProvider.FLUTTERWAVE, PaymentProvider.MTN_MOMO],
            "UG": [PaymentProvider.FLUTTERWAVE, PaymentProvider.MTN_MOMO, PaymentProvider.AIRTEL_MONEY],
            "ZA": [PaymentProvider.FLUTTERWAVE],
        }
        
        if country_code and country_code in country_providers:
            return country_providers[country_code]
        
        return providers


class PaymentOrchestrator:
    """Orchestrates payments across multiple gateways"""
    
    def __init__(self):
        self.factory = PaymentGatewayFactory()
    
    def initiate_deposit(self, request: PaymentRequest) -> PaymentResponse:
        """Initiate a deposit through appropriate gateway"""
        gateway = self.factory.get_gateway(request.provider)
        return gateway.initiate_payment(request)
    
    def verify_deposit(self, provider: PaymentProvider, reference: str) -> PaymentResponse:
        """Verify a deposit"""
        gateway = self.factory.get_gateway(provider)
        return gateway.verify_payment(reference)
    
    def initiate_withdrawal(self, request: PayoutRequest) -> PayoutResponse:
        """Initiate a withdrawal/payout"""
        gateway = self.factory.get_gateway(request.provider)
        return gateway.initiate_payout(request)
    
    def verify_withdrawal(self, provider: PaymentProvider, reference: str) -> PayoutResponse:
        """Verify a withdrawal"""
        gateway = self.factory.get_gateway(provider)
        return gateway.verify_payout(reference)
    
    def handle_webhook(self, provider: PaymentProvider, payload: Dict, signature: str) -> bool:
        """Handle webhook from any provider"""
        gateway = self.factory.get_gateway(provider)
        return gateway.handle_webhook(payload, signature)
    
    def get_providers_for_country(self, country_code: str) -> list:
        """Get recommended providers for a country"""
        return self.factory.get_available_providers(country_code)


# Singleton instance
payment_orchestrator = None

def get_payment_orchestrator() -> PaymentOrchestrator:
    """Get payment orchestrator singleton"""
    global payment_orchestrator
    if payment_orchestrator is None:
        payment_orchestrator = PaymentOrchestrator()
    return payment_orchestrator


# Convenience functions for common operations

def deposit_with_card(user_id: int, amount: float, currency: str, 
                      card_details: Dict, email: str, provider: PaymentProvider = PaymentProvider.FLUTTERWAVE) -> PaymentResponse:
    """Deposit using card payment"""
    request = PaymentRequest(
        amount=amount,
        currency=currency,
        user_id=user_id,
        provider=provider,
        method=PaymentMethod.CARD,
        email=email,
        card_number=card_details.get("number"),
        cvv=card_details.get("cvv"),
        expiry_month=card_details.get("expiry_month"),
        expiry_year=card_details.get("expiry_year")
    )
    
    orchestrator = get_payment_orchestrator()
    return orchestrator.initiate_deposit(request)


def deposit_with_mobile_money(user_id: int, amount: float, currency: str,
                               phone: str, email: str, provider: PaymentProvider = PaymentProvider.FLUTTERWAVE,
                               network: str = None) -> PaymentResponse:
    """Deposit using mobile money"""
    request = PaymentRequest(
        amount=amount,
        currency=currency,
        user_id=user_id,
        provider=provider,
        method=PaymentMethod.MOBILE_MONEY,
        email=email,
        phone=phone,
        mobile_money_provider=network
    )
    
    orchestrator = get_payment_orchestrator()
    return orchestrator.initiate_deposit(request)


def deposit_with_bank_transfer(user_id: int, amount: float, currency: str,
                                email: str, bank_code: str = None, 
                                account_number: str = None,
                                provider: PaymentProvider = PaymentProvider.PAYSTACK) -> PaymentResponse:
    """Deposit using bank transfer"""
    request = PaymentRequest(
        amount=amount,
        currency=currency,
        user_id=user_id,
        provider=provider,
        method=PaymentMethod.BANK_TRANSFER,
        email=email,
        bank_code=bank_code,
        account_number=account_number
    )
    
    orchestrator = get_payment_orchestrator()
    return orchestrator.initiate_deposit(request)


def withdraw_to_bank(user_id: int, amount: float, currency: str,
                     recipient_name: str, account_number: str, bank_code: str,
                     reason: str = None, provider: PaymentProvider = PaymentProvider.FLUTTERWAVE) -> PayoutResponse:
    """Withdraw to bank account"""
    request = PayoutRequest(
        amount=amount,
        currency=currency,
        user_id=user_id,
        recipient_name=recipient_name,
        recipient_account=account_number,
        recipient_bank_code=bank_code,
        provider=provider,
        reason=reason
    )
    
    orchestrator = get_payment_orchestrator()
    return orchestrator.initiate_withdrawal(request)


def withdraw_to_mobile_money(user_id: int, amount: float, currency: str,
                              recipient_name: str, phone_number: str,
                              reason: str = None, provider: PaymentProvider = PaymentProvider.FLUTTERWAVE) -> PayoutResponse:
    """Withdraw to mobile money"""
    request = PayoutRequest(
        amount=amount,
        currency=currency,
        user_id=user_id,
        recipient_name=recipient_name,
        recipient_account=phone_number,
        recipient_phone=phone_number,
        provider=provider,
        reason=reason
    )
    
    orchestrator = get_payment_orchestrator()
    return orchestrator.initiate_withdrawal(request)


def verify_payment(provider: PaymentProvider, reference: str) -> PaymentResponse:
    """Verify payment status"""
    orchestrator = get_payment_orchestrator()
    return orchestrator.verify_deposit(provider, reference)


def verify_payout(provider: PaymentProvider, reference: str) -> PayoutResponse:
    """Verify payout status"""
    orchestrator = get_payment_orchestrator()
    return orchestrator.verify_withdrawal(provider, reference)


def handle_provider_webhook(provider: PaymentProvider, payload: Dict, signature: str) -> bool:
    """Handle webhook from payment provider"""
    orchestrator = get_payment_orchestrator()
    return orchestrator.handle_webhook(provider, payload, signature)


def get_recommended_providers(country_code: str) -> list:
    """Get recommended payment providers for a country"""
    orchestrator = get_payment_orchestrator()
    return orchestrator.get_providers_for_country(country_code)


def is_provider_available(provider: PaymentProvider) -> bool:
    """Check if a payment provider is configured and available"""
    try:
        gateway = PaymentGatewayFactory.get_gateway(provider)
        return gateway.secret_key is not None
    except:
        return False


def get_provider_status() -> Dict[str, bool]:
    """Get status of all payment providers"""
    return {
        provider.value: is_provider_available(provider)
        for provider in PaymentProvider
    }


__all__ = [
    'PaymentProvider', 'PaymentMethod', 'PaymentRequest', 'PaymentResponse',
    'PayoutRequest', 'PayoutResponse', 'BasePaymentGateway',
    'FlutterwaveGateway', 'PaystackGateway', 'PaymentGatewayFactory',
    'PaymentOrchestrator', 'get_payment_orchestrator',
    'deposit_with_card', 'deposit_with_mobile_money', 'deposit_with_bank_transfer',
    'withdraw_to_bank', 'withdraw_to_mobile_money',
    'verify_payment', 'verify_payout',
    'handle_provider_webhook',
    'get_recommended_providers', 'is_provider_available', 'get_provider_status'
]
