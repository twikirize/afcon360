"""
AFCON360 Transport - Payment Method Configuration Service

Country-aware payment method configuration managed by super admin/owner via TransportSetting.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Set
from dataclasses import dataclass, field
from functools import lru_cache

from flask import current_app

from app.extensions import db
from app.transport.models import TransportSetting

logger = logging.getLogger(__name__)

# Default payment method definitions with country restrictions
DEFAULT_PAYMENT_METHODS = [
    {
        "code": "cash",
        "label": "Cash",
        "description": "Pay driver directly in cash",
        "category": "offline",
        "enabled": True,
        "default": True,
        "countries": [],  # Empty = all countries
        "requires_wallet": False,
        "gateway": None,
        "metadata": {"sort_order": 0}
    },
    {
        "code": "wallet",
        "label": "AFCON360 Wallet",
        "description": "Pay from your wallet balance",
        "category": "digital",
        "enabled": True,
        "default": False,
        "countries": [],
        "requires_wallet": True,
        "gateway": "internal",
        "metadata": {"sort_order": 1}
    },
    {
        "code": "mtn_momo",
        "label": "MTN Mobile Money",
        "description": "Pay with MTN MoMo",
        "category": "mobile_money",
        "enabled": True,
        "default": False,
        "countries": ["UG"],  # Uganda only
        "requires_wallet": False,
        "gateway": "mtn_momo",
        "metadata": {"sort_order": 2, "currency": "UGX"}
    },
    {
        "code": "airtel_money",
        "label": "Airtel Money",
        "description": "Pay with Airtel Money",
        "category": "mobile_money",
        "enabled": True,
        "default": False,
        "countries": ["UG", "RW", "TZ", "KE"],  # East Africa
        "requires_wallet": False,
        "gateway": "airtel_money",
        "metadata": {"sort_order": 3, "currency": "UGX"}
    },
    {
        "code": "flutterwave",
        "label": "Card (Flutterwave)",
        "description": "Pay with Visa/Mastercard via Flutterwave",
        "category": "card",
        "enabled": True,
        "default": False,
        "countries": ["NG", "GH", "KE", "UG", "TZ", "RW", "ZA"],  # Africa
        "requires_wallet": False,
        "gateway": "flutterwave",
        "metadata": {"sort_order": 4, "currencies": ["NGN", "GHS", "KES", "UGX", "TZS", "RWF", "ZAR", "USD"]}
    },
    {
        "code": "paystack",
        "label": "Card (Paystack)",
        "description": "Pay with Visa/Mastercard via Paystack",
        "category": "card",
        "enabled": True,
        "default": False,
        "countries": ["NG", "GH", "ZA"],  # Nigeria, Ghana, South Africa
        "requires_wallet": False,
        "gateway": "paystack",
        "metadata": {"sort_order": 5, "currencies": ["NGN", "GHS", "ZAR", "USD"]}
    },
    {
        "code": "paypal",
        "label": "PayPal",
        "description": "Pay with PayPal",
        "category": "digital_wallet",
        "enabled": True,
        "default": False,
        "countries": [],  # Global
        "requires_wallet": False,
        "gateway": "paypal",
        "metadata": {"sort_order": 6, "currencies": ["USD", "EUR", "GBP"]}
    },
    {
        "code": "bank_transfer",
        "label": "Bank Transfer",
        "description": "Direct bank transfer",
        "category": "bank",
        "enabled": True,
        "default": False,
        "countries": [],
        "requires_wallet": False,
        "gateway": "bank_transfer",
        "metadata": {"sort_order": 7}
    },
]

SETTING_KEY = "payment.methods"
SETTING_CATEGORY = "payments"
SETTING_PERMISSION = "transport.settings"


@dataclass
class PaymentMethodConfig:
    """Configuration for a single payment method"""
    code: str
    label: str
    description: str
    category: str
    enabled: bool
    default: bool
    countries: List[str] = field(default_factory=list)
    requires_wallet: bool = False
    gateway: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def is_available_for_country(self, country_code: Optional[str]) -> bool:
        """Check if method is available for a country"""
        if not self.enabled:
            return False
        if not country_code:
            return True
        if not self.countries:
            return True
        return country_code.upper() in [c.upper() for c in self.countries]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "code": self.code,
            "label": self.label,
            "description": self.description,
            "category": self.category,
            "enabled": self.enabled,
            "default": self.default,
            "countries": self.countries,
            "requires_wallet": self.requires_wallet,
            "gateway": self.gateway,
            "metadata": self.metadata,
        }


class PaymentConfigService:
    """Service for managing payment method configuration"""

    def __init__(self):
        self._cache: Optional[List[PaymentMethodConfig]] = None

    def _load_from_db(self) -> List[PaymentMethodConfig]:
        """Load configuration from TransportSetting"""
        try:
            setting = TransportSetting.query.filter_by(
                key=SETTING_KEY, is_deleted=False
            ).first()

            if setting and isinstance(setting.value, dict):
                methods_data = setting.value.get("methods", [])
                if methods_data:
                    return [PaymentMethodConfig(**m) for m in methods_data]
        except Exception as e:
            logger.warning(f"Failed to load payment config from DB: {e}")

        # Fallback to defaults
        return [PaymentMethodConfig(**m) for m in DEFAULT_PAYMENT_METHODS]

    def get_all_methods(self, force_reload: bool = False) -> List[PaymentMethodConfig]:
        """Get all configured payment methods"""
        if self._cache is None or force_reload:
            self._cache = self._load_from_db()
        return self._cache

    def get_enabled_methods(self, force_reload: bool = False) -> List[PaymentMethodConfig]:
        """Get only enabled payment methods"""
        return [m for m in self.get_all_methods(force_reload) if m.enabled]

    def get_methods_for_country(
        self,
        country_code: Optional[str],
        user_has_wallet: bool = False,
        force_reload: bool = False
    ) -> List[PaymentMethodConfig]:
        """Get payment methods available for a specific country and user"""
        methods = self.get_enabled_methods(force_reload)

        available = []
        for method in methods:
            if not method.is_available_for_country(country_code):
                continue
            if method.requires_wallet and not user_has_wallet:
                continue
            available.append(method)

        # Sort by metadata.sort_order
        available.sort(key=lambda m: m.metadata.get("sort_order", 999))
        return available

    def get_default_method(
        self,
        country_code: Optional[str] = None,
        user_has_wallet: bool = False
    ) -> Optional[PaymentMethodConfig]:
        """Get the default payment method for a country/user"""
        methods = self.get_methods_for_country(country_code, user_has_wallet)
        for method in methods:
            if method.default:
                return method
        return methods[0] if methods else None

    def update_configuration(
        self,
        methods: List[Dict[str, Any]],
        actor_user_id: int
    ) -> Dict[str, Any]:
        """Update payment method configuration (super admin/owner only)"""
        # Validate each method
        validated_methods = []
        for m in methods:
            try:
                config = PaymentMethodConfig(**m)
                validated_methods.append(config.to_dict())
            except Exception as e:
                raise ValueError(f"Invalid payment method config: {e}")

        # Get or create setting
        setting = TransportSetting.query.filter_by(
            key=SETTING_KEY, is_deleted=False
        ).first()

        value = {
            "version": 1,
            "methods": validated_methods,
            "updated_by": actor_user_id,
        }

        if setting is None:
            setting = TransportSetting(
                key=SETTING_KEY,
                value=value,
                name="Payment Methods Configuration",
                description="Country-aware payment method configuration for transport bookings",
                category=SETTING_CATEGORY,
                data_type="json",
                default_value={"methods": [m.to_dict() for m in DEFAULT_PAYMENT_METHODS]},
                is_public=False,
                is_advanced=True,
                requires_permission=SETTING_PERMISSION,
            )
            db.session.add(setting)
        else:
            from app.transport.models import update_setting
            update_setting(SETTING_KEY, value, modified_by=actor_user_id)

        db.session.commit()

        # Invalidate cache
        self._cache = None

        return {"success": True, "methods": validated_methods}

    def seed_defaults(self, actor_user_id: int) -> Dict[str, Any]:
        """Seed default configuration"""
        return self.update_configuration(
            [m.to_dict() for m in DEFAULT_PAYMENT_METHODS],
            actor_user_id
        )


# Singleton instance
_payment_config_service: Optional[PaymentConfigService] = None


def get_payment_config_service() -> PaymentConfigService:
    global _payment_config_service
    if _payment_config_service is None:
        _payment_config_service = PaymentConfigService()
    return _payment_config_service


# Country detection helpers
def get_user_country(user_id: int) -> Optional[str]:
    """
    Get user's country for payment method filtering.
    Priority: 1) User's registered country, 2) Current location country, 3) App default
    """
    try:
        from app.identity.models.user import User
        user = db.session.get(User, user_id)
        if not user:
            return None

        # Check user profile for country
        if hasattr(user, 'profile') and user.profile:
            country = getattr(user.profile, 'country', None)
            if country:
                return country.upper()

        # Check organisation membership for country
        from app.identity.models.organisation_member import OrganisationMember
        from app.identity.models.organisation import Organisation
        membership = OrganisationMember.query.filter_by(
            user_id=user_id, is_deleted=False
        ).first()
        if membership:
            org = db.session.get(Organisation, membership.organisation_id)
            if org and org.country:
                return org.country.upper()

    except Exception as e:
        logger.debug(f"Could not determine user country: {e}")

    # Fallback to app default
    return current_app.config.get("DEFAULT_COUNTRY", "UG")


def get_user_wallet_status(
    user_id: int,
    currency_code: Optional[str] = None,
) -> bool:
    """Check whether the user has a wallet account in the requested currency.

    The legacy default remains UGX for callers that predate currency-aware
    transport quotes. Transport passes its canonical fare currency explicitly,
    so a UGX wallet cannot be advertised for a USD-denominated trip (and vice
    versa) unless an actual matching account exists.
    """
    try:
        from app.wallet.models.ledger import AccountModel
        from app.utils.enums import Currency

        wallet_currency = (
            Currency(str(currency_code).strip().upper())
            if currency_code else Currency.UGX
        )
        account = AccountModel.query.filter_by(
            user_id=user_id,
            currency=wallet_currency,
            is_deleted=False,
        ).first()
        return account is not None
    except (ValueError, TypeError):
        return False
    except Exception:
        logger.exception(
            "Could not verify wallet availability for user %s / currency %s",
            user_id,
            currency_code or "UGX",
        )
        return False
