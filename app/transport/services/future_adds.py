"""
from typing import Dict, Any
from flask import current_app
import uuid
#import random
from datetime import datetime

# ==========================================================
# BASE GATEWAY INTERFACE
# ==========================================================

class PaymentGateway:
    ""Base interface for all payment providers""

    def initiate_payment(self, amount: float, payload: Dict[str, Any]) -> Dict[str, Any]:
        raise NotImplementedError

    def verify_payment(self, reference: str) -> Dict[str, Any]:
        raise NotImplementedError

    def refund(self, reference: str, amount: float) -> Dict[str, Any]:
        raise NotImplementedError


# ==========================================================
# MOBILE MONEY ADAPTERS
# ==========================================================

class MpesaGateway(PaymentGateway):
    ""Safaricom M-Pesa STK Push""

    def initiate_payment(self, amount, payload):
        phone = payload.get("phone")
        return {
            "success": True,
            "provider": "mpesa",
            "reference": f"mpesa_{uuid.uuid4().hex[:10]}",
            "status": "pending",
            "message": f"STK Push sent to {phone} (mock)"
        }

    def verify_payment(self, reference):
        return {"success": True, "status": "completed"}

    def refund(self, reference, amount):
        return {"success": True}


class MTNMoMoGateway(PaymentGateway):
    ""MTN Mobile Money""

    def initiate_payment(self, amount, payload):
        return {
            "success": True,
            "provider": "mtn_momo",
            "reference": f"mtn_{uuid.uuid4().hex[:10]}",
            "status": "pending",
            "message": "MTN MoMo request sent (mock)"
        }

    def verify_payment(self, reference):
        return {"success": True, "status": "completed"}

    def refund(self, reference, amount):
        return {"success": True}


class AirtelMoneyGateway(PaymentGateway):
    ""Airtel Money Integration""

    def initiate_payment(self, amount, payload):
        return {
            "success": True,
            "provider": "airtel_money",
            "reference": f"airtel_{uuid.uuid4().hex[:10]}",
            "status": "pending"
        }

    def verify_payment(self, reference):
        return {"success": True, "status": "completed"}

    def refund(self, reference, amount):
        return {"success": True}


class FlutterwaveGateway(PaymentGateway):
    ""Pan-African Payment Gateway""

    def initiate_payment(self, amount, payload):
        return {
            "success": True,
            "provider": "flutterwave",
            "reference": f"flw_{uuid.uuid4().hex[:10]}",
            "status": "pending"
        }

    def verify_payment(self, reference):
        return {"success": True, "status": "completed"}

    def refund(self, reference, amount):
        return {"success": True}


class StripeGateway(PaymentGateway):
    ""Card Payments""

    def initiate_payment(self, amount, payload):
        return {
            "success": True,
            "provider": "stripe",
            "reference": f"stripe_{uuid.uuid4().hex[:10]}",
            "status": "completed"
        }

    def verify_payment(self, reference):
        return {"success": True, "status": "completed"}

    def refund(self, reference, amount):
        return {"success": True}


# ==========================================================
# PAYMENT FACTORY
# ==========================================================

class PaymentGatewayFactory:

    @staticmethod
    def get_gateway(provider: str) -> PaymentGateway:
        gateways = {
            "mpesa": MpesaGateway(),
            "mtn_momo": MTNMoMoGateway(),
            "airtel_money": AirtelMoneyGateway(),
            "flutterwave": FlutterwaveGateway(),
            "stripe": StripeGateway(),
        }

        if provider not in gateways:
            raise ValueError(f"Unsupported payment provider: {provider}")

        return gateways[provider]


# ==========================================================
# SMS PROVIDERS
# ==========================================================

class SMSService:

    @staticmethod
    def send_sms(to_number: str, message: str):
        # ⚠ FUTURE TODO:
        # Implement Twilio / Africa's Talking integration
        # Add retry mechanism

        current_app.logger.info(f"SMS to {to_number}: {message}")

        return {"success": True, "message": "SMS sent (mock)"}


# ==========================================================
# MAP SERVICES
# ==========================================================

class MapsService:

    @staticmethod
    def get_directions(origin: Dict, destination: Dict):
        # ⚠ FUTURE TODO:
        # Integrate Google Maps / Mapbox
        return {
            "success": True,
            "distance_km": random.randint(1, 20),
            "duration_minutes": random.randint(5, 40),
            "provider": "mock"
        }


# ==========================================================
# MAIN EXTERNAL PLATFORMS SERVICE
# ==========================================================

class ExternalPlatformsService:
    ""
    Orchestrator for all external integrations
    ""

    @staticmethod
    def process_payment(amount: float, payload: Dict[str, Any], provider: str):
        gateway = PaymentGatewayFactory.get_gateway(provider)
        return gateway.initiate_payment(amount, payload)

    @staticmethod
    def verify_payment(reference: str, provider: str):
        gateway = PaymentGatewayFactory.get_gateway(provider)
        return gateway.verify_payment(reference)

    @staticmethod
    def refund_payment(reference: str, amount: float, provider: str):
        gateway = PaymentGatewayFactory.get_gateway(provider)
        return gateway.refund(reference, amount)

    @staticmethod
    def send_sms(to_number: str, message: str):
        return SMSService.send_sms(to_number, message)

    @staticmethod
    def get_directions(origin: Dict, destination: Dict):
        return MapsService.get_directions(origin, destination)


# ==========================================================
# SINGLETON ACCESSOR
# ==========================================================

_external_platforms_instance = None

def get_external_platforms():
    ""Singleton accessor to avoid import errors""
    global _external_platforms_instance
    if _external_platforms_instance is None:
        _external_platforms_instance = ExternalPlatformsService()
    return _external_platforms_instance
"""