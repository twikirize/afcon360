"""
Owner-configurable agent operating terms.

These are the "set and contracted terms" the platform owner defines for the
agent network: which currencies agents may handle, and the per-transaction /
daily limits and commission rates for cash-in and cash-out.

Stored in ``SystemConfig`` (JSON) under the key ``agent_terms`` so no schema
migration is required. Everything here is read-only on the DB config table.
"""

from decimal import Decimal
from typing import Any, Dict, List, Optional

from app.models.system_config import SystemConfig

AGENT_TERMS_KEY = "agent_terms"

DEFAULT_TERMS: Dict[str, Any] = {
    "accepted_currencies": ["UGX", "KES", "TZS", "RWF", "USD", "EUR"],
    "cashin": {
        "per_txn_limit": 5000000,
        "daily_limit": 20000000,
        "commission_rate": 1.0,
    },
    "cashout": {
        "per_txn_limit": 5000000,
        "daily_limit": 20000000,
        "commission_rate": 1.0,
    },
}


def _as_float(value: Any, default: float) -> float:
    try:
        if value is None or value == "":
            return float(default)
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def get_agent_terms() -> Dict[str, Any]:
    raw = SystemConfig.get(AGENT_TERMS_KEY)
    if not isinstance(raw, dict):
        raw = {}

    currencies = raw.get("accepted_currencies")
    if not currencies:
        currencies = DEFAULT_TERMS["accepted_currencies"]
    currencies = [str(c).upper() for c in currencies]

    cashin = DEFAULT_TERMS["cashin"].copy()
    cashin.update(raw.get("cashin", {}))

    cashout = DEFAULT_TERMS["cashout"].copy()
    cashout.update(raw.get("cashout", {}))

    return {
        "accepted_currencies": currencies,
        "cashin": cashin,
        "cashout": cashout,
    }


def save_agent_terms(
    data: Dict[str, Any], updated_by: Optional[int] = None
) -> Dict[str, Any]:
    cashin = data.get("cashin", {})
    if not cashin:
        cashin = {}

    cashout = data.get("cashout", {})
    if not cashout:
        cashout = {}

    currencies = data.get("accepted_currencies")
    if not currencies:
        currencies = DEFAULT_TERMS["accepted_currencies"]
    currencies = [str(c).upper() for c in currencies]

    terms = {
        "accepted_currencies": currencies,
        "cashin": {
            "per_txn_limit": _as_float(cashin.get("per_txn_limit"), DEFAULT_TERMS["cashin"]["per_txn_limit"]),
            "daily_limit": _as_float(cashin.get("daily_limit"), DEFAULT_TERMS["cashin"]["daily_limit"]),
            "commission_rate": _as_float(cashin.get("commission_rate"), DEFAULT_TERMS["cashin"]["commission_rate"]),
        },
        "cashout": {
            "per_txn_limit": _as_float(cashout.get("per_txn_limit"), DEFAULT_TERMS["cashout"]["per_txn_limit"]),
            "daily_limit": _as_float(cashout.get("daily_limit"), DEFAULT_TERMS["cashout"]["daily_limit"]),
            "commission_rate": _as_float(cashout.get("commission_rate"), DEFAULT_TERMS["cashout"]["commission_rate"]),
        },
    }

    SystemConfig.set(
        AGENT_TERMS_KEY,
        terms,
        value_type="json",
        category="agents",
        description="Agent operating terms: accepted currencies and contracted cash-in/cash-out limits and commission",
        updated_by=updated_by,
    )

    return terms


def agents_enabled() -> bool:
    try:
        from app.wallet.models.config import WalletSystemConfig

        return bool(WalletSystemConfig.get_config().agents_enabled)
    except Exception:
        return False


def is_currency_accepted(currency: str) -> bool:
    if not currency:
        return False
    return currency.upper() in get_agent_terms()["accepted_currencies"]


def get_direction_terms(direction: str) -> Dict[str, Any]:
    terms = get_agent_terms()
    return terms.get(direction, terms["cashin"])


def get_agent_country(agent_user: Any) -> Optional[str]:
    from app.profile.models import get_profile_by_user

    try:
        profile = get_profile_by_user(int(agent_user.id))
        if profile:
            return getattr(profile, "country", None)
    except Exception:
        pass
    return None


def check_agent_limits(
    agent_user_id: int,
    currency: str,
    amount: Decimal,
    direction: str,
) -> tuple[bool, Optional[str], Optional[Decimal]]:
    from datetime import datetime, timezone
    from app.wallet.models.agent_float import AgentFloatLedger

    if direction not in ("cashin", "cashout"):
        direction = "cashin"

    dt = get_direction_terms(direction)

    per_txn = Decimal(str(dt.get("per_txn_limit", 0)))
    daily = Decimal(str(dt.get("daily_limit", 0)))
    amount = Decimal(str(amount))

    if per_txn > 0 and amount > per_txn:
        return (
            False,
            f"Amount exceeds the agent {direction} per-transaction limit of {per_txn:,.0f} {currency}.",
            Decimal("0"),
        )

    today = datetime.now(timezone.utc).date()
    start = datetime(today.year, today.month, today.day, tzinfo=timezone.utc)

    entries = (
        AgentFloatLedger.query.filter(
            AgentFloatLedger.agent_user_id == int(agent_user_id),
            AgentFloatLedger.currency == str(currency),
            AgentFloatLedger.entry_type == direction,
            AgentFloatLedger.created_at >= start,
        )
        .all()
    )

    daily_used = sum((abs(e.amount) for e in entries), Decimal("0"))

    if daily > 0 and (daily_used + amount) > daily:
        return (
            False,
            (
                f"Amount would exceed the agent {direction} daily limit of "
                f"{daily:,.0f} {currency} (already used {daily_used:,.0f} today)."
            ),
            daily_used,
        )

    return True, None, daily_used


def assert_agent_can_operate(
    agent_user: Any,
    currency: str,
    amount: Decimal,
    direction: str,
) -> Dict[str, Any]:
    from app.wallet.services.agent_onboarding_service import is_agency_available_for_country
    from app.wallet.services.agent_management_service import get_agent_status, SUSPENDED, EXPELLED

    if not getattr(agent_user, "is_agent", False):
        return {"ok": False, "error": "Only authorized agents can perform this action."}

    if not agents_enabled():
        return {"ok": False, "error": "The agent service is currently disabled."}

    st = get_agent_status(agent_user.id)
    if st == SUSPENDED:
        return {"ok": False, "error": "This agent is suspended and cannot process transactions."}
    if st == EXPELLED:
        return {"ok": False, "error": "This agent has been expelled and can no longer operate."}

    country = get_agent_country(agent_user)
    if country and not is_agency_available_for_country(country):
        return {
            "ok": False,
            "error": f"Agent services are not available in {country}.",
        }

    if not is_currency_accepted(currency):
        accepted = ", ".join(get_agent_terms()["accepted_currencies"])
        return {
            "ok": False,
            "error": f"Currency {currency} is not accepted for agent transactions. Accepted currencies: {accepted}.",
        }

    ok, err, _ = check_agent_limits(agent_user.id, currency, amount, direction)
    if not ok:
        return {"ok": False, "error": err}

    return {"ok": True, "error": None}