"""AFCON360 Transport - Reservation state machines (TH-3-D3).

  A. Reservation lifecycle           (Transport-owned)
  B. Reservation-side financial      (obligation metadata only)

Neither may know about Assignment, Booking, or Execution.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional

from app.extensions import db

logger = logging.getLogger(__name__)


class ReservationState(str, Enum):
    DRAFT = "draft"
    HELD = "held"
    RESERVED = "reserved"
    MATERIALIZED = "materialized"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class ReservationObligationState(str, Enum):
    """Reservation-side financial obligation status.

    Refund outcomes (REFUNDED, PARTIALLY_REFUNDED) are intentionally absent
    here. If they become necessary, they must be admitted only when the
    underlying BookingPayment lifecycle supports them. Wallet/Payment
    remains the authoritative owner of refund state.
    """
    UNPAID = "unpaid"
    DEPOSITED = "deposited"
    PAID = "paid"


class InvalidReservationTransition(Exception): ...


class InvalidObligationTransition(Exception): ...


class TransportReservationStateMachine:

    RESERVATION_TRANSITIONS = {
        ReservationState.DRAFT: [ReservationState.HELD, ReservationState.CANCELLED],
        ReservationState.HELD: [
            ReservationState.RESERVED,
            ReservationState.CANCELLED,
            ReservationState.EXPIRED,
        ],
        ReservationState.RESERVED: [
            ReservationState.MATERIALIZED,
            ReservationState.CANCELLED,
            ReservationState.EXPIRED,
        ],
        ReservationState.MATERIALIZED: [ReservationState.COMPLETED, ReservationState.CANCELLED],
        ReservationState.COMPLETED: [],
        ReservationState.CANCELLED: [],
        ReservationState.EXPIRED: [],
    }

    # Monotonic forward-only obligation transitions.
    OBLIGATION_TRANSITIONS = {
        ReservationObligationState.UNPAID: [
            ReservationObligationState.DEPOSITED,
            ReservationObligationState.PAID,
        ],
        ReservationObligationState.DEPOSITED: [ReservationObligationState.PAID],
        ReservationObligationState.PAID: [],
    }

    TERMINAL_STATES = frozenset({
        ReservationState.COMPLETED, ReservationState.CANCELLED, ReservationState.EXPIRED,
    })

    CAPACITY_CONSUMING_STATES = frozenset({
        ReservationState.HELD, ReservationState.RESERVED, ReservationState.MATERIALIZED,
    })

    @classmethod
    def can_transition(cls, current, target) -> bool:
        try:
            cur = current if isinstance(current, ReservationState) else ReservationState(current)
            tgt = target if isinstance(target, ReservationState) else ReservationState(target)
        except (ValueError, TypeError):
            return False
        return tgt in cls.RESERVATION_TRANSITIONS.get(cur, [])

    @classmethod
    def can_transition_obligation(cls, current, target) -> bool:
        try:
            cur = current if isinstance(current, ReservationObligationState) else ReservationObligationState(current)
            tgt = target if isinstance(target, ReservationObligationState) else ReservationObligationState(target)
        except (ValueError, TypeError):
            return False
        return tgt in cls.OBLIGATION_TRANSITIONS.get(cur, [])

    @classmethod
    def is_terminal(cls, state) -> bool:
        try:
            return ReservationState(state) in cls.TERMINAL_STATES
        except (ValueError, TypeError):
            return False

    @classmethod
    def consumes_capacity(cls, state) -> bool:
        try:
            return ReservationState(state) in cls.CAPACITY_CONSUMING_STATES
        except (ValueError, TypeError):
            return False

    @classmethod
    def obligation_satisfies_reserved(cls, obligation_state, required_obligations) -> bool:
        """True if `obligation_state` is in the policy's allowed set for RESERVED."""
        try:
            cur = obligation_state if isinstance(obligation_state, ReservationObligationState) \
                else ReservationObligationState(obligation_state)
        except (ValueError, TypeError):
            return False
        allowed = {str(o).upper() for o in (required_obligations or set())}
        return cur.value.upper() in allowed

    # ------------------------------------------------------------------
    @classmethod
    def transition(cls, reservation, target_state, *, changed_by_user_id=None,
                   reason=None, trigger=None, metadata=None, commit=False):
        target_value = target_state.value if isinstance(target_state, ReservationState) else str(target_state)
        if not cls.can_transition(reservation.state, target_value):
            raise InvalidReservationTransition(
                f"Cannot transition reservation {getattr(reservation, 'id', '?')} "
                f"from '{reservation.state}' to '{target_value}'"
            )
        old = reservation.state
        reservation.state = target_value
        log = list(reservation.audit_log or [])
        log.append({
            "at": datetime.now(timezone.utc).isoformat(),
            "action": "reservation_state_changed",
            "from": old,
            "to": target_value,
            "by_user_id": changed_by_user_id,
            "reason": reason,
            "trigger": trigger,
            **(metadata or {}),
        })
        reservation.audit_log = log
        if commit:
            db.session.commit()
        logger.info("Reservation %s: %s → %s (trigger=%s)",
                    getattr(reservation, "id", "?"), old, target_value, trigger)
        return reservation

    @classmethod
    def transition_obligation(cls, reservation, target_obligation, *, changed_by_user_id=None,
                              reason=None, trigger=None, metadata=None, commit=False):
        target_value = target_obligation.value if isinstance(target_obligation, ReservationObligationState) \
            else str(target_obligation)
        if not cls.can_transition_obligation(reservation.obligation_state, target_value):
            raise InvalidObligationTransition(
                f"Cannot transition obligation for reservation "
                f"{getattr(reservation, 'id', '?')} from '{reservation.obligation_state}' to '{target_value}'"
            )
        old = reservation.obligation_state
        reservation.obligation_state = target_value
        log = list(reservation.audit_log or [])
        log.append({
            "at": datetime.now(timezone.utc).isoformat(),
            "action": "reservation_obligation_changed",
            "from": old,
            "to": target_value,
            "by_user_id": changed_by_user_id,
            "reason": reason,
            "trigger": trigger,
            **(metadata or {}),
        })
        reservation.audit_log = log
        if commit:
            db.session.commit()
        logger.info("Reservation %s obligation: %s → %s (trigger=%s)",
                    getattr(reservation, "id", "?"), old, target_value, trigger)
        return reservation