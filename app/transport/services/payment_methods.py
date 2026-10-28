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