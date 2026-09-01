"""
Pending withdrawal intent store for agent-assisted cash-out.

Mirrors ``deposit_intent.py``. When a user wants to withdraw cash through an
agent, the wallet is NOT debited immediately. The user generates a reference
code, hands it (plus receives physical cash) to the agent, and the agent
confirms the code in the Agent Portal. Only on authorized agent confirmation is
the user's wallet debited.

Storage is Redis (no schema migration required). Keys are namespaced and expire
so a never-confirmed intent cannot leak.
"""

import json
import uuid
from typing import Dict, Any, Optional

from app.extensions import redis_client

INTENT_TTL_SECONDS = 1800
INTENT_KEY_PREFIX = "wallet:withdrawal_intent"


def _key(reference: str) -> str:
    return f"{INTENT_KEY_PREFIX}:{reference}"


def generate_withdrawal_reference(prefix: str = "WDR") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:16].upper()}"


def save_withdrawal_intent(
    reference: str,
    data: Dict[str, Any],
    ttl: int = INTENT_TTL_SECONDS,
) -> None:
    payload = json.dumps(data, default=str).encode("utf-8")
    redis_client.setex(_key(reference), ttl, payload)


def get_withdrawal_intent(reference: str) -> Optional[Dict[str, Any]]:
    raw = redis_client.get(_key(reference))
    if not raw:
        return None
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    try:
        return json.loads(raw)
    except (ValueError, TypeError):
        return None


def consume_withdrawal_intent(reference: str) -> Optional[Dict[str, Any]]:
    intent = get_withdrawal_intent(reference)
    if intent is None:
        return None
    redis_client.delete(_key(reference))
    return intent