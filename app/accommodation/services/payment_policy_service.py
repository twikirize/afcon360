# app/accommodation/services/payment_policy_service.py

"""
Payment Policy Service - Manages property booking policies and payment options
"""

from decimal import Decimal
from typing import Dict, List, Optional
from app.accommodation.models.booking_policy import PropertyBookingPolicy
from app.accommodation.models.property_payment_method import PropertyPaymentMethod
from app.accommodation.models.platform_override import PlatformBookingPolicyOverride
from app.wallet import PaymentMethodConfig
from app.extensions import db
import logging

logger = logging.getLogger(__name__)


class PaymentPolicyService:
    """
    Service for managing booking policies and payment options.
    """

    @staticmethod
    def get_policy(property_id: int) -> Optional[PropertyBookingPolicy]:
        """Get the booking policy for a property."""
        return PropertyBookingPolicy.query.filter_by(property_id=property_id).first()

    @staticmethod
    def get_or_create_policy(property_id: int) -> PropertyBookingPolicy:
        """Get or create a default booking policy for a property."""
        policy = PaymentPolicyService.get_policy(property_id)
        if not policy:
            policy = PropertyBookingPolicy(property_id=property_id)
            db.session.add(policy)
            db.session.commit()
        return policy

    @staticmethod
    def get_allowed_options(
        property_id: int,
        booking_amount: Decimal,
        guest_type: str = "normal"
    ) -> Dict:
        """
        Get allowed payment options for a property.
        """
        policy = PaymentPolicyService.get_or_create_policy(property_id)

        # Get enabled payment methods for this property
        enabled_methods = PropertyPaymentMethod.query.filter_by(
            property_id=property_id,
            enabled=True
        ).all()

        method_ids = [pm.wallet_method_id for pm in enabled_methods]
        payment_methods = PaymentMethodConfig.query.filter(
            PaymentMethodConfig.id.in_(method_ids),
            PaymentMethodConfig.is_enabled.is_(True),
            PaymentMethodConfig.is_active.is_(True),
        ).all() if method_ids else []

        from app.accommodation.models.property import Property
        property_obj = db.session.get(Property, property_id)
        property_currency = (getattr(property_obj, 'currency', None) or 'USD').upper()
        policy_timings = {
            'pay_now': policy.allow_pay_now,
            'pay_on_arrival': policy.allow_pay_on_arrival,
            'deposit': policy.allow_deposit_payment,
            'invoice': True,
        }

        # Build options
        options = {
            'payment_methods': [],
            'allowed_methods': [m.method_id for m in payment_methods],
            'timing': {
                'pay_now': policy.allow_pay_now,
                'pay_on_arrival': policy.allow_pay_on_arrival,
                'deposit': policy.allow_deposit_payment,
                'deposit_percentage': float(policy.deposit_percentage) if policy.deposit_percentage else 0,
            },
            'allowed_timings': [key for key, enabled in policy_timings.items() if enabled],
            'cancellation': {
                'policy': policy.cancellation_policy,
                'free_cancel_hours': policy.free_cancel_hours,
            },
            'guest_requirements': {
                'require_identity': policy.require_guest_identity,
                'require_phone': policy.require_guest_phone,
                'require_email': policy.require_guest_email,
                'minimum_age': policy.minimum_age,
            }
        }

        for method in payment_methods:
            linked = next((pm for pm in enabled_methods if pm.wallet_method_id == method.id), None)
            currency = (getattr(linked, 'preferred_currency', None) or property_currency).upper()
            supported = method.supported_currencies or []
            if supported and currency not in {str(item).upper() for item in supported}:
                currency = property_currency
            method_timings = [timing for timing in (method.allowed_timings or []) if policy_timings.get(timing, False)]
            options['payment_methods'].append({
                'id': method.id,
                'method_id': method.method_id,
                'display_name': method.display_name,
                'method_type': method.method_type,
                'currency': currency,
                'allowed_timings': method_timings,
                'transaction_fee': float(method.transaction_fee or 0),
                'min_amount': float(method.min_amount or 0),
                'max_amount': float(method.max_amount or 0),
                'icon': PaymentPolicyService._get_icon(method.method_type),
            })

        options['allowed_methods'] = [m['method_id'] for m in options['payment_methods']]

        # Enforce platform-wide booking policy overrides
        platform_override = PlatformBookingPolicyOverride.query.first()
        if platform_override:
            if platform_override.afcon_pay_on_arrival_disabled and 'pay_on_arrival' in options['allowed_timings']:
                options['allowed_timings'] = [t for t in options['allowed_timings'] if t != 'pay_on_arrival']
                options['timing']['pay_on_arrival'] = False

            if platform_override.minimum_deposit_percentage and options['timing']['deposit']:
                min_deposit = float(platform_override.minimum_deposit_percentage)
                current_deposit = options['timing'].get('deposit_percentage', 0)
                if current_deposit < min_deposit:
                    options['timing']['deposit_percentage'] = min_deposit

            if platform_override.require_vip_verification:
                options['guest_requirements']['require_vip_verification'] = True

            if platform_override.maximum_pay_on_arrival_days is not None:
                options['timing']['maximum_pay_on_arrival_days'] = platform_override.maximum_pay_on_arrival_days

            if platform_override.afcon_restrictions_active:
                options['timing']['afcon_restrictions_active'] = True

        return options

    @staticmethod
    def _get_icon(method_type: str) -> str:
        """Get icon for payment method type."""
        icons = {
            'wallet': 'wallet',
            'mobile_money': 'smartphone',
            'card': 'credit-card',
            'bank_transfer': 'building-bank',
            'invoice': 'file-invoice',
            'cash': 'cash',
        }
        return icons.get(method_type, 'cash')