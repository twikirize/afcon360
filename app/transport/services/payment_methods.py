# app/transport/services/payment_methods.py
"""
Payment methods a rider can actually choose today.

Source of truth, in priority order:

  1. The wallet service, if it exposes a method-list surface.
     (The wallet owns a user's saved payment instruments.)
  2. Otherwise, the methods the transport payment service can actually
     process. Today that is ``cash`` and ``wallet`` —
     ``PaymentService.process_payment()`` routes those through real code
     and everything else through ``_process_online_payment()``, which
     currently raises NotImplementedError. Advertising an unimplemented
     method to riders is a lie, so we don't.

When the wallet service gains a real list surface, add the method name
below and this helper will start using it with no template change.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


_WALLET_LIST_METHODS = (
    "get_payment_methods",
    "list_payment_methods",
    "get_available_payment_methods",
    "available_payment_methods",
)


def get_available_payment_methods(user_id: Optional[int] = None) -> List[Dict[str, Any]]:
    """Return the payment methods the rider may choose from.

    Each entry: {"code": str, "label": str, "default": bool}.
    """
    if user_id is not None:
        try:
            from app.wallet.services.wallet_service import WalletService
            ws = WalletService()
            for name in _WALLET_LIST_METHODS:
                fn = getattr(ws, name, None)
                if not callable(fn):
                    continue
                try:
                    raw = fn(user_id=user_id)
                except TypeError:
                    raw = fn(user_id)
                normalised = _normalise(raw)
                if normalised:
                    return normalised
        except Exception as exc:
            logger.debug("wallet payment-method lookup unavailable: %s", exc)

    # Fallback: what PaymentService.process_payment() actually executes.
    return [
        {"code": "cash",   "label": "Cash",   "default": True},
        {"code": "wallet", "label": "Wallet", "default": False},
    ]


def _normalise(raw: Any) -> List[Dict[str, Any]]:
    if not raw:
        return []
    out: List[Dict[str, Any]] = []
    try:
        iterator = raw.items() if isinstance(raw, dict) else raw
        for i, item in enumerate(iterator):
            if isinstance(item, tuple) and len(item) == 2:
                code, label = item
                out.append({
                    "code": str(code).lower(),
                    "label": str(label),
                    "default": i == 0,
                })
            elif isinstance(item, dict):
                code = item.get("code") or item.get("method") or item.get("id")
                if not code:
                    continue
                out.append({
                    "code": str(code).lower(),
                    "label": str(item.get("label") or item.get("name") or code),
                    "default": bool(item.get("default", i == 0)),
                })
            elif isinstance(item, str):
                out.append({
                    "code": item.lower(),
                    "label": item.replace("_", " ").title(),
                    "default": i == 0,
                })
    except Exception as exc:
        logger.debug("wallet payment-method normalisation failed: %s", exc)
        return []
    return out
