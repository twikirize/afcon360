"""AFCON360 Transport - Reservation policy evaluator (TH-3-D3).

Evaluates reservation requests against the frozen payment model:

  METHOD  = { CASH, WALLET, MOBILE_MONEY, CARD, BANK_TRANSFER }
  TIMING  = { NOW, DEPOSIT, END_OF_TRIP, INVOICE }

Commercial policy (negotiated / organisation-specific / provider-specific)
is separate from both and referenced via `commercial_policy_ref`.

Does not move money. Does not own payment state.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional

from app.transport.services.settings_service import SettingsService

logger = logging.getLogger(__name__)

# Frozen canonical payment methods. INVOICE and NEGOTIATED are NOT methods.
CANONICAL_PAYMENT_METHODS = frozenset({
    "CASH", "WALLET", "MOBILE_MONEY", "CARD", "BANK_TRANSFER",
})

# Frozen canonical payment timings.
CANONICAL_PAYMENT_TIMINGS = frozenset({
    "NOW", "DEPOSIT", "END_OF_TRIP", "INVOICE",
})

# Reservation modes.
RESERVATION_MODES = frozenset({"specific", "capacity"})

# Timing → obligation required before RESERVED is reachable.
# END_OF_TRIP and INVOICE permit UNPAID.
# DEPOSIT requires DEPOSITED or PAID.
# NOW requires PAID.
_REQUIRED_OBLIGATION_FOR_RESERVED = {
    "NOW":         frozenset({"PAID"}),
    "DEPOSIT":     frozenset({"DEPOSITED", "PAID"}),
    "END_OF_TRIP": frozenset({"UNPAID", "DEPOSITED", "PAID"}),
    "INVOICE":     frozenset({"UNPAID", "DEPOSITED", "PAID"}),
}


@dataclass
class PolicyDecision:
    allowed: bool
    reason: str = ""
    requires_deposit: bool = False
    deposit_amount: Optional[Decimal] = None
    deposit_currency: Optional[str] = None
    deposit_due_at: Optional[datetime] = None
    required_obligation_for_reserved: frozenset = field(default_factory=frozenset)
    commercial_policy_ref: Optional[str] = None
    missing_requirements: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


class TransportReservationPolicyEvaluator:
    """Policy evaluator for reservation creation."""

    DEFAULT_DEPOSIT_LEAD_HOURS = 72
    DEFAULT_DEPOSIT_PERCENT = Decimal("20.00")
    DEFAULT_DEPOSIT_CURRENCY = "USD"

    @classmethod
    def evaluate(
        cls,
        *,
        actor,
        offering_code: str,
        provider_type: str,
        provider_id: int,
        quantity: int,
        window_start: datetime,
        window_end: datetime,
        payment_method: Optional[str] = None,
        payment_timing: Optional[str] = None,
        commercial_policy_ref: Optional[str] = None,
        on_behalf_of_organisation_id: Optional[int] = None,
        authority_evidence: Optional[dict] = None,
        estimated_value: Optional[Decimal] = None,
        **_,
    ) -> PolicyDecision:
        missing: List[str] = []

        # 1. Window sanity
        if not isinstance(window_start, datetime) or not isinstance(window_end, datetime):
            return PolicyDecision(allowed=False, reason="window_start and window_end must be datetimes")
        if window_start.tzinfo is None or window_end.tzinfo is None:
            return PolicyDecision(allowed=False, reason="window_start and window_end must be tz-aware")
        if window_end <= window_start:
            return PolicyDecision(allowed=False, reason="window_end must be strictly after window_start")

        # 2. Quantity
        if not isinstance(quantity, int) or quantity <= 0:
            return PolicyDecision(allowed=False, reason="quantity must be a positive integer")

        # 3. Actor
        if actor is None or not getattr(actor, "is_authenticated", False):
            return PolicyDecision(allowed=False, reason="Authentication required")

        # 4. Payment timing (required)
        timing_upper = (payment_timing or "").strip().upper()
        if not timing_upper:
            return PolicyDecision(allowed=False, reason="payment_timing is required")
        if timing_upper not in CANONICAL_PAYMENT_TIMINGS:
            return PolicyDecision(
                allowed=False,
                reason=(
                    f"Unsupported payment_timing '{timing_upper}'. "
                    f"Canonical: {sorted(CANONICAL_PAYMENT_TIMINGS)}."
                ),
            )

        # 5. Payment method (policy-controlled)
        method_upper = (payment_method or "").strip().upper() or None
        if timing_upper == "NOW" and method_upper is None:
            return PolicyDecision(allowed=False, reason="payment_method is required for timing=NOW")
        if method_upper is not None:
            if method_upper not in CANONICAL_PAYMENT_METHODS:
                return PolicyDecision(
                    allowed=False,
                    reason=(
                        f"Unsupported payment_method '{method_upper}'. "
                        f"Canonical: {sorted(CANONICAL_PAYMENT_METHODS)}."
                    ),
                )
            # Capability gate: is this method enabled in this deployment?
            enabled_methods = SettingsService.get_setting(
                "transport.reservation.enabled_payment_methods",
                sorted(CANONICAL_PAYMENT_METHODS),
            )
            if isinstance(enabled_methods, str):
                enabled_methods = [enabled_methods]
            enabled_upper = {str(m).strip().upper() for m in (enabled_methods or [])}
            if method_upper not in enabled_upper:
                return PolicyDecision(
                    allowed=False,
                    reason=f"Payment method '{method_upper}' is not enabled for this deployment",
                )

        # 6. Authority
        if on_behalf_of_organisation_id is not None:
            ok, auth_reason = cls._validate_authority(
                actor, on_behalf_of_organisation_id, authority_evidence or {}
            )
            if not ok:
                return PolicyDecision(allowed=False, reason=auth_reason)

        # 7. Deposit computation
        requires_deposit, deposit_amount, deposit_currency, deposit_due_at = cls._compute_deposit(
            payment_timing=timing_upper,
            estimated_value=estimated_value,
            window_start=window_start,
        )

        # 8. Obligation gate for RESERVED
        required_obligation = _REQUIRED_OBLIGATION_FOR_RESERVED[timing_upper]

        # 9. Commercial policy is a reference, not a timing value.
        resolved_policy_ref = commercial_policy_ref or SettingsService.get_setting(
            f"transport.reservation.commercial_policy.{offering_code}",
            None,
        )

        return PolicyDecision(
            allowed=True,
            reason="Reservation policy satisfied",
            requires_deposit=requires_deposit,
            deposit_amount=deposit_amount,
            deposit_currency=deposit_currency,
            deposit_due_at=deposit_due_at,
            required_obligation_for_reserved=required_obligation,
            commercial_policy_ref=resolved_policy_ref,
            missing_requirements=missing,
            metadata={
                "payment_method": method_upper,
                "payment_timing": timing_upper,
                "offering_code": offering_code,
                "provider_type": provider_type,
                "provider_id": provider_id,
                "quantity": quantity,
            },
        )

    # ------------------------------------------------------------------
    @classmethod
    def _validate_authority(cls, actor, org_id: int, evidence: Dict[str, Any]):
        try:
            from app.identity.models.organisation import Organisation
        except Exception:
            return False, "Organisation model unavailable"

        org = Organisation.query.filter_by(id=org_id).first()
        if org is None:
            return False, "Organisation not found"

        actor_id = getattr(actor, "id", None)
        if actor_id is None:
            return False, "Cannot determine actor identity"

        for attr in ("owner_user_id", "created_by_user_id"):
            if getattr(org, attr, None) == actor_id:
                return True, ""

        for m in (getattr(org, "members", None) or []):
            if getattr(m, "user_id", None) == actor_id and getattr(m, "is_active", True):
                return True, ""

        try:
            for m in (getattr(actor, "organisation_memberships", None) or []):
                if getattr(m, "organisation_id", None) == org_id and getattr(m, "is_active", True):
                    return True, ""
        except Exception:
            pass

        return False, "Actor is not authorised for this organisation"

    # ------------------------------------------------------------------
    @classmethod
    def _compute_deposit(cls, *, payment_timing: str, estimated_value: Optional[Decimal], window_start: datetime):
        if payment_timing != "DEPOSIT":
            return False, None, None, None

        try:
            lead_hours = int(SettingsService.get_setting(
                "transport.reservation.deposit_lead_hours", cls.DEFAULT_DEPOSIT_LEAD_HOURS
            ))
        except (TypeError, ValueError):
            lead_hours = cls.DEFAULT_DEPOSIT_LEAD_HOURS

        try:
            deposit_percent = Decimal(str(SettingsService.get_setting(
                "transport.reservation.deposit_percent", str(cls.DEFAULT_DEPOSIT_PERCENT)
            )))

        except (InvalidOperation, TypeError, ValueError):
            deposit_percent = cls.DEFAULT_DEPOSIT_PERCENT

        currency = SettingsService.get_setting(
            "transport.reservation.deposit_currency", cls.DEFAULT_DEPOSIT_CURRENCY
        ) or cls.DEFAULT_DEPOSIT_CURRENCY

        deposit_amount = None
        if estimated_value is not None:
            try:
                deposit_amount = (Decimal(str(estimated_value)) * deposit_percent) / Decimal("100")
            except (InvalidOperation, TypeError, ValueError):
                deposit_amount = None

        return True, deposit_amount, str(currency), window_start - timedelta(hours=lead_hours)


def get_reservation_policy_evaluator():
    return TransportReservationPolicyEvaluator