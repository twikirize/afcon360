"""
Payment methods a rider can actually choose today.

Source of truth, in priority order:

  1. TransportSetting configuration (country-aware, admin-managed)
  2. Fallback to hardcoded defaults

Cash is always available as the default fallback.
Digital methods are configured by super admin/owner and filtered by user's country.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Methods with real end-of-trip settlement behaviour implemented in transport.
# Other methods may remain configured in admin settings, but must not be shown
# as selectable until their transport initiation + verified callback workflow
# is integrated. This is a capability gate, not a replacement for configuration.
TRANSPORT_END_OF_TRIP_METHODS = frozenset({"cash", "wallet"})


def get_available_transport_payment_methods(
    user_id: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Return configured methods that transport can actually settle at trip end.

    Admin configuration remains the source of truth for enabled methods. This
    extra capability gate prevents advertising card/mobile-money/bank methods
    when the transport settlement adapter cannot yet verify and record them.
    """
    configured = get_available_payment_methods(user_id)
    result = [
        method for method in configured
        if str(method.get("code") or "").strip().lower()
        in TRANSPORT_END_OF_TRIP_METHODS
    ]

    # get_available_payment_methods has a legacy fallback that includes Wallet
    # even if configuration lookup failed. Don't advertise it unless the user
    # actually has a wallet account available.
    if user_id is None:
        return [method for method in result
                if str(method.get("code") or "").strip().lower() == "cash"]

    try:
        from app.transport.services.payment_config import get_user_wallet_status
        wallet_available = bool(get_user_wallet_status(user_id))
    except Exception:
        logger.warning(
            "Wallet availability could not be verified for rider %s",
            user_id,
            exc_info=True,
        )
        wallet_available = False

    if not wallet_available:
        result = [
            method for method in result
            if str(method.get("code") or "").strip().lower() != "wallet"
        ]
    return result


def get_available_payment_methods(user_id: Optional[int] = None) -> List[Dict[str, Any]]:
    """Return the payment methods the rider may choose from.

    Each entry: {"code": str, "label": str, "default": bool, "category": str, "gateway": str}.

    Filters by user's country and wallet status.
    """
    try:
        from app.transport.services.payment_config import (
            get_payment_config_service,
            get_user_country,
            get_user_wallet_status,
        )

        config_service = get_payment_config_service()

        country = None
        user_has_wallet = False

        if user_id is not None:
            country = get_user_country(user_id)
            user_has_wallet = get_user_wallet_status(user_id)

        methods = config_service.get_methods_for_country(
            country_code=country,
            user_has_wallet=user_has_wallet,
        )

        # Convert to expected format
        result = []
        for m in methods:
            result.append({
                "code": m.code,
                "label": m.label,
                "default": m.default,
                "category": m.category,
                "gateway": m.gateway,
                "description": m.description,
                "metadata": m.metadata,
            })

        # Ensure cash is always present as fallback
        if not any(m["code"] == "cash" for m in result):
            result.insert(0, {
                "code": "cash",
                "label": "Cash",
                "default": True,
                "category": "offline",
                "gateway": None,
                "description": "Pay driver directly in cash",
                "metadata": {"sort_order": 0}
            })

        return result

    except Exception as exc:
        logger.debug("Payment config service unavailable, using fallback: %s", exc)

    # Fallback: what PaymentService.process_payment() actually executes
    return [
        {"code": "cash", "label": "Cash", "default": True, "category": "offline", "gateway": None},
        {"code": "wallet", "label": "Wallet", "default": False, "category": "digital", "gateway": "internal"},
    ]