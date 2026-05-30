"""
app/accommodation/services/payment_option_service.py
Queries PaymentMethodConfig for available payment methods in accommodation bookings.
"""
from typing import List, Dict, Optional
from app.events.payment_config import PaymentMethodConfig
import logging

logger = logging.getLogger(__name__)


class PaymentOptionService:
    """Provides available payment methods for accommodation booking checkout."""

    @staticmethod
    def get_available_methods(currency: str = "USD") -> List[Dict]:
        """
        Get all available payment methods for the given currency.
        Returns list of dicts with keys: method_id, display_name, method_type,
        provider_name, requires_phone, transaction_fee, icon.
        """
        methods = PaymentMethodConfig.get_available_methods(currency)
        result = []
        for m in methods:
            result.append({
                "id": m.id,
                "method_id": m.method_id,
                "display_name": m.display_name,
                "method_type": m.method_type,
                "provider_name": m.provider_name,
                "country_code": m.country_code,
                "requires_phone": m.requires_phone,
                "transaction_fee": float(m.transaction_fee or 0),
                "min_amount": float(m.min_amount or 0),
                "max_amount": float(m.max_amount or 0),
                "icon": PaymentOptionService._icon(m.method_type),
            })
        return result

    @staticmethod
    def get_method_by_id(method_id: str) -> Optional[PaymentMethodConfig]:
        """Get a specific payment method config by method_id string."""
        return PaymentMethodConfig.get_by_id(method_id)

    @staticmethod
    def is_method_available(method_id: str, currency: str = "USD") -> bool:
        """Check if a specific payment method is available."""
        method = PaymentMethodConfig.get_by_id(method_id)
        if not method:
            return False
        return method.is_available and method.supports_currency(currency)

    @staticmethod
    def has_any_available(currency: str = "USD") -> bool:
        """Check if any payment method is available for the given currency."""
        methods = PaymentMethodConfig.get_available_methods(currency)
        return len(methods) > 0

    @staticmethod
    def _icon(method_type: str) -> str:
        return {
            "wallet": "wallet",
            "mobile_money": "smartphone",
            "card": "credit-card",
            "bank_transfer": "building-bank",
        }.get(method_type, "cash")
