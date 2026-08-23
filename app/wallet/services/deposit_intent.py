# app/wallet/services/deposit_intent.py
"""
Pending deposit intent store for provider-integrated deposits.

When a user initiates a deposit through a real payment provider (mobile money
push, Flutterwave checkout, etc.) the wallet is NOT credited immediately. The
provider flow is asynchronous:

    1. Form POST -> gateway.initiate_deposit()  -> provider push / redirect
    2. Provider webhook/callback -> gateway.verify() -> WalletService.deposit()

Until step 2 confirms, the deposit is "pending". We must remember which wallet
account, amount, currency and source a given provider reference belongs to so
the webhook can credit the correct ledger entry. This is that memory.

Storage is Redis (no schema migration required). Keys are namespaced and expire
so a never-confirmed intent cannot leak.
"""

import json
import time
import uuid
from typing import Optional, Dict, Any

from app.extensions import redis_client


INTENT_TTL_SECONDS = 1800  # 30 minutes
INTENT_KEY_PREFIX = "wallet:deposit_intent"


def _key(reference: str) -> str:
    return f"{INTENT_KEY_PREFIX}:{reference}"


def generate_deposit_reference(prefix: str = "DEP") -> str:
    """Generate a unique, provider-safe deposit reference."""
    return f"{prefix}-{uuid.uuid4().hex[:16].upper()}"


def save_deposit_intent(reference: str, data: Dict[str, Any],
                        ttl: int = INTENT_TTL_SECONDS) -> None:
    """Persist a pending deposit intent in Redis."""
    payload = json.dumps(data, default=str).encode("utf-8")
    redis_client.setex(_key(reference), ttl, payload)


def get_deposit_intent(reference: str) -> Optional[Dict[str, Any]]:
    """Return the pending intent for a reference, or None if absent/expired."""
    raw = redis_client.get(_key(reference))
    if not raw:
        return None
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    try:
        return json.loads(raw)
    except (ValueError, TypeError):
        return None


def consume_deposit_intent(reference: str) -> Optional[Dict[str, Any]]:
    """Atomically fetch and delete the intent (idempotency guard).

    Returns the intent if present, else None. Safe to call multiple times on
    the same reference: only the first call returns the data.
    """
    intent = get_deposit_intent(reference)
    if intent is None:
        return None
    redis_client.delete(_key(reference))
    return intent


def mark_deposit_intent_status(reference: str, status: str) -> None:
    """Update the stored status without removing the intent."""
    intent = get_deposit_intent(reference)
    if intent is None:
        return
    intent["status"] = status
    intent["completed_at"] = time.time()
    save_deposit_intent(reference, intent)
