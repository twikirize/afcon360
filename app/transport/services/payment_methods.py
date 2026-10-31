"""
Transport's read-only adapter to the Wallet marketplace payment catalogue.

Transport does not own a payment-method catalogue or capability allowlist.
Methods are offered only when Wallet configuration and Wallet's implemented
marketplace collection path both support the quote currency and timing.

Wallet certifies eligibility; Transport only displays.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, List, Optional

from app.utils.exceptions import ValidationError


def get_available_transport_payment_methods(
    user_id: Optional[int] = None,
    currency_code: Optional[str] = None,
    amount: Optional[Any] = None,
    payment_timing: str = "pay_on_completion",
    service_country_code: Optional[str] = None,
    payer_country_code: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Get ALL configured payment methods with Wallet-certified eligibility status.
    
    Returns methods with status: ready, needs_setup, needs_kyc, needs_pin,
    low_balance, unavailable. Transport displays all; Wallet certifies.
    """
    if not currency_code:
        try:
            from app.transport.services.fare_service import CURRENCY_DEFAULT
            currency_code = str(CURRENCY_DEFAULT).strip().upper()
        except Exception:
            return []

    if user_id is None:
        # Anonymous user - only show cash as ready, others as needs_setup
        from app.wallet.models.payment_method import PaymentMethodConfig
        configs = PaymentMethodConfig.query.filter_by(
            is_enabled=True, is_active=True
        ).all()
        results = []
        for config in configs:
            if not config.supports_currency(currency_code):
                continue
            allowed_timings = [str(t).strip().lower() for t in (config.allowed_timings or [])]
            if payment_timing not in allowed_timings:
                continue
            results.append({
                "code": config.method_id,
                "label": config.display_name,
                "status": "ready" if config.method_id == "cash" else "needs_setup",
                "status_message": "Pay driver directly after trip" if config.method_id == "cash" else "Sign in to use this method",
                "category": config.method_type,
                "is_default": config.method_id == "cash",
                "onboarding_url": "/auth/login" if config.method_id != "cash" else None,
                "balance": None,
            })
        results.sort(key=lambda x: (not x["is_default"], x["label"].lower()))
        return results

    # Authenticated user - delegate to Wallet for certification
    from app.wallet.services.wallet_service import WalletService
    
    try:
        amount_decimal = Decimal(str(amount)) if amount is not None else Decimal("0")
    except Exception:
        amount_decimal = Decimal("0")
    
    return WalletService().get_user_payment_method_status(
        user_id=user_id,
        currency=currency_code,
        amount=amount_decimal,
        settlement_timing=payment_timing,
    )



def require_ready_transport_payment_method(
    methods: Optional[List[Dict[str, Any]]],
    method_code: str,
) -> Dict[str, Any]:
    """Fail closed unless Wallet certifies the selected marketplace method ready.

    A method can be listed for explanation/onboarding while its status is
    low_balance, needs_kyc, needs_pin, needs_setup or unavailable. Merely
    appearing in the catalogue is never authority to accept a commitment.
    """
    code = str(method_code or "").strip().lower()
    selected = next(
        (
            method for method in (methods or [])
            if str(method.get("code") or "").strip().lower() == code
        ),
        None,
    )
    if selected is None:
        raise ValidationError(
            message="The selected payment method is not available for this fare.",
            field="payment_method",
        )
    status = str(selected.get("status") or "").strip().lower()
    if status != "ready":
        message = str(
            selected.get("status_message")
            or "This payment method is not ready. Choose another available method."
        )
        raise ValidationError(message=message, field="payment_method")
    return selected


def get_transport_payment_options(
    user_id: int,
    currency: str,
    amount: Any,
    settlement_timing: str = "pay_on_completion",
) -> List[Dict[str, Any]]:
    """Explicit alias for the new certification API."""
    return get_available_transport_payment_methods(
        user_id=user_id,
        currency_code=currency,
        amount=amount,
        payment_timing=settlement_timing,
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
