# app/accommodation/services/payment_policy_service.py

"""
Payment Policy Service - Manages property booking policies and payment options
"""

from decimal import Decimal
from typing import Dict, List, Optional
from app.accommodation.models.booking_policy import PropertyBookingPolicy
from app.accommodation.models.property_payment_method import PropertyPaymentMethod
from app.events.payment_config import PaymentMethodConfig
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

        # Get enabled payment methods
        enabled_methods = PropertyPaymentMethod.query.filter_by(
            property_id=property_id,
            enabled=True
        ).all()

        method_ids = [pm.wallet_method_id for pm in enabled_methods]
        payment_methods = PaymentMethodConfig.query.filter(
            PaymentMethodConfig.id.in_(method_ids) if method_ids else False,
            PaymentMethodConfig.is_available == True
        ).all()

        # Build options
        options = {
            'payment_methods': [
                {
                    'id': m.id,
                    'method_id': m.method_id,
                    'display_name': m.display_name,
                    'method_type': m.method_type,
                    'icon': PaymentPolicyService._get_icon(m.method_type),
                }
                for m in payment_methods
            ],
            'allowed_methods': [m.method_id for m in payment_methods],
            'timing': {
                'pay_now': policy.allow_pay_now,
                'pay_on_arrival': policy.allow_pay_on_arrival,
                'deposit': policy.allow_deposit_payment,
                'deposit_percentage': float(policy.deposit_percentage) if policy.deposit_percentage else 0,
            },
            'allowed_timings': [
                key for key, enabled in {
                    'pay_now': policy.allow_pay_now,
                    'pay_on_arrival': policy.allow_pay_on_arrival,
                    'deposit': policy.allow_deposit_payment,
                }.items() if enabled
            ],
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
        }
        return icons.get(method_type, 'cash')