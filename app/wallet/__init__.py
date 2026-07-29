"""
Wallet module initialization.
Exports the wallet blueprint and helper functions.
"""
from .routes import wallet_bp, get_or_create_account
from .models.payment_method import PaymentMethodConfig, EventPaymentPreference

__all__ = [
    'wallet_bp',
    'get_or_create_account',
    'PaymentMethodConfig',
    'EventPaymentPreference',
]