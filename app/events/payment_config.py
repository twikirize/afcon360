"""
Payment method configuration re-exports from wallet module.

PaymentMethodConfig and EventPaymentPreference are owned by the wallet module.
This file re-exports them for backward compatibility with any remaining imports.
"""

from app.wallet.models.payment_method import PaymentMethodConfig, EventPaymentPreference

__all__ = ['PaymentMethodConfig', 'EventPaymentPreference']
