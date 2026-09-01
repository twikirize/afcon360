"""
Agent lifecycle management (active / suspended / expelled) + fines.

This is the "manage agents" back-office layer used by owner, super-admin and
wallet-admin. It deliberately introduces NO new database table (the wallet
models are locked and migrations are owner-controlled), so agent lifecycle
state and fine history are stored in ``SystemConfig`` under the key
``agent_management``. Financial effects (fines, float recall on expulsion) go
through the existing ``AgentFloatService`` so the double-entry float ledger and
forensic audit are preserved.
"""

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional

from flask import current_app

from app.models.system_config import SystemConfig

AGENT_MANAGEMENT_KEY = "agent_management"

ACTIVE = "active"
SUSPENDED = "suspended"
EXPELLED = "expelled"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load() -> Dict[str, Any]:
    raw = SystemConfig.get(AGENT_MANAGEMENT_KEY)
    if isinstance(raw, dict):
        return raw
    return {}


def _save(data: Dict[str, Any], updated_by: Optional[int] = None) -> None:
    SystemConfig.set(
        AGENT_MANAGEMENT_KEY,
        data,
        value_type="json",
        category="agents",
        description="Agent lifecycle management state (status, suspension, expulsion, fines)",
        updated_by=updated_by,
    )


def get_agent_record(user_id: int) -> Dict[str, Any]:
    return _load().get(str(user_id), {})


def get_agent_status(user_id: int) -> str:
    rec = get_agent_record(user_id)
    return rec.get("status", ACTIVE)


def set_status(
    user_id: int,
    status: str,
    actor_id: Optional[int] = None,
    reason: str = "",
    extra: Optional[Dict[str, Any]] = None,
) -> None:
    data = _load()
    key = str(user_id)
    rec = data.get(key, {})
    if not rec:
        rec = {}

    rec["status"] = status

    if status == SUSPENDED:
        rec["suspended_at"] = _now()
        rec["suspended_by"] = actor_id
        rec["suspended_reason"] = reason
    elif status == ACTIVE:
        rec.pop("suspended_at", None)
        rec.pop("suspended_by", None)
        rec.pop("suspended_reason", None)
        rec.pop("expelled_at", None)
        rec.pop("expelled_by", None)
        rec.pop("expelled_reason", None)
    elif status == EXPELLED:
        rec["expelled_at"] = _now()
        rec["expelled_by"] = actor_id
        rec["expelled_reason"] = reason

    if extra:
        rec.update(extra)

    data[key] = rec
    _save(data, actor_id)


def _agent_display(user_id: int) -> Dict[str, Any]:
    from app.identity.models.user import User
    from app.wallet.models.agent_float import AgentFloatAccount
    from app.wallet.services.agent_float_service import AgentFloatService
    from app.profile.models import get_profile_by_user

    user = User.query.get(int(user_id))
    if not user:
        return {
            "user_id": int(user_id),
            "email": None,
            "agent_code": None,
            "country": None,
            "balances": {},
            "found": False,
        }

    profile = get_profile_by_user(int(user.id))
    country = getattr(profile, "country", None) if profile else None

    fas = AgentFloatAccount.query.filter_by(user_id=user.id).all()
    balances = {}
    for fa in fas:
        balances[fa.currency] = float(fa.balance)

    return {
        "user_id": user.id,
        "email": user.email,
        "agent_code": getattr(user, "agent_code", None),
        "country": country,
        "balances": balances,
        "found": True,
    }


def list_agents(status: Optional[str] = None) -> List[Dict[str, Any]]:
    from app.identity.models.user import User

    data = _load()
    rows = []

    for u in User.query.filter_by(is_agent=True, is_deleted=False).all():
        rec = data.get(str(u.id), {})
        st = rec.get("status", ACTIVE)

        if status and st != status:
            continue

        info = _agent_display(u.id)
        info["status"] = st
        info["suspended_at"] = rec.get("suspended_at")
        info["suspended_reason"] = rec.get("suspended_reason")
        info["expelled_at"] = rec.get("expelled_at")
        info["expelled_reason"] = rec.get("expelled_reason")
        info["fines"] = rec.get("fines", [])
        rows.append(info)

    return rows


def _audit(
    actor: Any,
    user_id: int,
    action: str,
    details: Dict[str, Any],
    risk: int = 50,
) -> Optional[int]:
    try:
        from app.audit.forensic_audit import ForensicAuditService

        return ForensicAuditService.log_attempt(
            entity_type="agent",
            entity_id=str(user_id),
            action=action,
            user_id=getattr(actor, "id", None),
            details=details,
            risk_score=risk,
        )
    except Exception:
        current_app.logger.exception("Agent management audit attempt failed")
        return None


def _audit_done(
    audit_id: Optional[int],
    status: str,
    actor: Any,
    notes: str = "",
    result: Optional[Dict[str, Any]] = None,
) -> None:
    if not audit_id:
        return
    try:
        from app.audit.forensic_audit import ForensicAuditService

        ForensicAuditService.log_completion(
            audit_id=audit_id,
            status=status,
            reviewed_by=getattr(actor, "id", None),
            review_notes=notes,
            result_details=result if result else {},
        )
    except Exception:
        current_app.logger.exception("Agent management audit completion failed")


def suspend_agent(
    actor: Any,
    user_id: int,
    reason: str,
) -> Dict[str, Any]:
    uid = int(user_id)
    if get_agent_status(uid) == EXPELLED:
        return {"success": False, "error": "Cannot suspend an expelled agent."}

    audit_id = _audit(actor, uid, "suspend", {"reason": reason})
    set_status(uid, SUSPENDED, actor_id=getattr(actor, "id", None), reason=reason)
    _audit_done(
        audit_id,
        "completed",
        actor,
        reason,
        {"new_status": SUSPENDED},
    )

    current_app.logger.info(
        f"Agent {uid} suspended by {getattr(actor, 'id', None)}: {reason}"
    )
    return {"success": True, "status": SUSPENDED}


def reactivate_agent(
    actor: Any,
    user_id: int,
    reason: str,
) -> Dict[str, Any]:
    uid = int(user_id)

    audit_id = _audit(actor, uid, "reactivate", {"reason": reason})
    set_status(uid, ACTIVE, actor_id=getattr(actor, "id", None), reason=reason)
    _audit_done(
        audit_id,
        "completed",
        actor,
        reason,
        {"new_status": ACTIVE},
    )

    return {"success": True, "status": ACTIVE}


def expel_agent(
    actor: Any,
    user_id: int,
    reason: str,
) -> Dict[str, Any]:
    from app.wallet.models.agent_float import AgentFloatAccount
    from app.wallet.services.agent_float_service import AgentFloatService

    uid = int(user_id)

    audit_id = _audit(actor, uid, "expel", {"reason": reason}, risk=85)

    recalled = {}

    try:
        fs = AgentFloatService()
        fas = AgentFloatAccount.query.filter_by(user_id=uid).all()

        for fa in fs.db.begin():
            for fa in fas:
                if fa.balance and fa.balance > 0:
                    fs.debit(
                        uid,
                        fa.currency,
                        fa.balance,
                        entry_type="recall",
                        created_by=getattr(actor, "id", None),
                        note=f"Float recalled on expulsion: {reason}",
                    )
                    recalled[fa.currency] = float(fa.balance)

        set_status(
            uid,
            EXPELLED,
            actor_id=getattr(actor, "id", None),
            reason=reason,
            extra={"recalled_float": recalled},
        )

        _audit_done(
            audit_id,
            "completed",
            actor,
            reason,
            {"new_status": EXPELLED, "recalled": recalled},
        )

        current_app.logger.info(
            f"Agent {uid} expelled by {getattr(actor, 'id', None)}: {reason}; recalled {recalled}"
        )
        return {"success": True, "status": EXPELLED, "recalled": recalled}

    except Exception:
        current_app.logger.exception("Agent float recall failed during expulsion")
        _audit_done(
            audit_id,
            "failed",
            actor,
            "float recall failed",
            {"recalled": recalled},
        )
        return {
            "success": False,
            "error": "Expulsion recorded but float recall failed; reconcile manually.",
        }


def fine_agent(
    actor: Any,
    user_id: int,
    amount: Decimal,
    currency: str,
    reason: str,
) -> Dict[str, Any]:
    from app.wallet.services.agent_float_service import AgentFloatService

    try:
        amount = Decimal(str(amount))
    except Exception:
        return {"success": False, "error": "Invalid fine amount."}

    if amount <= 0:
        return {"success": False, "error": "Fine amount must be positive."}

    currency = str(currency).upper()
    uid = int(user_id)

    fs = AgentFloatService()
    balance = fs.get_balance(uid, currency)

    if balance < amount:
        return {
            "success": False,
            "error": (
                f"Insufficient float to collect fine: have {balance:,.2f} "
                f"{currency}, need {amount:,.2f}."
            ),
        }

    audit_id = _audit(
        actor,
        uid,
        "fine",
        {"amount": str(amount), "currency": currency, "reason": reason},
        risk=70,
    )

    try:
        with fs.db.begin():
            fs.debit(
                uid,
                currency,
                amount,
                entry_type="fine",
                created_by=getattr(actor, "id", None),
                note=f"Agent fine: {reason}",
            )
    except Exception:
        current_app.logger.exception("Agent fine debit failed")
        _audit_done(
            audit_id,
            "failed",
            actor,
            str(Exception("Agent fine debit failed")),
        )
        return {"success": False, "error": "Could not apply fine."}

    data = _load()
    rec = data.get(str(uid), {})
    fines = rec.get("fines", [])

    fines.append(
        {
            "amount": str(amount),
            "currency": currency,
            "reason": reason,
            "by": getattr(actor, "id", None),
            "at": _now(),
        }
    )
    rec["fines"] = fines
    data[str(uid)] = rec
    _save(data, getattr(actor, "id", None))

    _audit_done(
        audit_id,
        "completed",
        actor,
        reason,
        {"amount": str(amount), "currency": currency},
    )

    return {"success": True, "amount": str(amount), "currency": currency}