"""
Transport's read-only adapter to the Wallet marketplace payment catalogue.

Transport does not own a payment-method catalogue or capability allowlist.
Methods are offered only when Wallet configuration and Wallet's implemented
marketplace collection path both support the quote currency and timing.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional


def get_available_transport_payment_methods(
    user_id: Optional[int] = None,
    currency_code: Optional[str] = None,
    amount: Optional[Any] = None,
    payment_timing: str = "pay_on_completion",
    service_country_code: Optional[str] = None,
    payer_country_code: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Delegate method eligibility to Wallet; never invent a fallback method."""
    if not currency_code:
        # Pre-quote pages use the fare engine's server-side display denomination.
        # The signed fare quote and Wallet invoice still bind the actual amount
        # and currency before dispatch; the browser does not choose the currency.
        try:
            from app.transport.services.fare_service import CURRENCY_DEFAULT
            currency_code = str(CURRENCY_DEFAULT).strip().upper()
        except Exception:
            return []
    from app.wallet.services.marketplace_invoice_service import MarketplaceInvoiceService

    return MarketplaceInvoiceService.list_available_methods(
        payer_user_id=user_id,
        currency=currency_code,
        amount=amount,
        settlement_timing=payment_timing,
        service_country_code=service_country_code,
        payer_country_code=payer_country_code,
    )


def get_available_payment_methods(
    user_id: Optional[int] = None,
    wallet_currency_code: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Compatibility wrapper; Wallet remains the only source of truth."""
    return get_available_transport_payment_methods(
        user_id,
        currency_code=wallet_currency_code,
        payment_timing="pay_on_completion",
    )
