"""AFCON360 Transport - Reservation service (TH-3-D3).

Frozen boundaries:
    Reservation ≠ Booking ≠ Assignment ≠ Payment ≠ Execution

Concurrency:
  - specific-resource lines: Postgres GiST exclusion constraint on
    (vehicle_id, tstzrange)
  - capacity accounting: `SELECT ... FOR UPDATE` on all overlapping supply
    rows in deterministic order

Idempotency:
  - caller supplies `idempotency_key`; DB unique constraint on
    (reserving_user_id, idempotency_key) guarantees convergence.
"""
from __future__ import annotations

import logging
import secrets
import string
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

import sqlalchemy as sa
from sqlalchemy import func

from app.extensions import db
from app.transport.models import (
    TransportReservation, TransportReservationLine,
    ProviderOfferingSupply, Vehicle, TransportOffering,
)
from app.transport.services.reservation_state_machine import (
    TransportReservationStateMachine as SM,
    ReservationState, ReservationObligationState,
    InvalidReservationTransition,
)
from app.transport.services.reservation_policy_evaluator import (
    TransportReservationPolicyEvaluator, PolicyDecision, RESERVATION_MODES,
)
from app.transport.services.offering_registry import TransportOfferingRegistry
from app.utils.audit import audit_log
from app.utils.exceptions import ValidationError, NotFoundError, ConflictError, PermissionError

logger = logging.getLogger(__name__)

ACTIVE_LINE_STATES = ("held", "reserved", "materialized")
VEHICLE_PROVIDER_TYPE_ORG = "organisation"
VEHICLE_PROVIDER_TYPE_DRIVER = "driver"


class ReservationConflictError(ConflictError): ...
class SupplyCoverageError(ConflictError): ...


class TransportReservationService:

    # ==================================================================
    # Create
    # ==================================================================
    @classmethod
    def create_reservation(
        cls,
        *,
        actor,
        offering_code: str,
        provider_type: str,
        provider_id: int,
        window_start: datetime,
        window_end: datetime,
        required_quantity: int,
        mode: str,
        idempotency_key: str,
        payment_method: Optional[str] = None,
        payment_timing: Optional[str] = None,
        commercial_policy_ref: Optional[str] = None,
        on_behalf_of_organisation_id: Optional[int] = None,
        authority_evidence: Optional[Dict[str, Any]] = None,
        event_id: Optional[int] = None,
        context_source: Optional[str] = None,
        context_ref: Optional[str] = None,
        specific_vehicle_ids: Optional[List[int]] = None,
        estimated_value: Optional[Decimal] = None,
        commit: bool = True,
    ) -> TransportReservation:
        # -- 1. Basic validation
        if not isinstance(window_start, datetime) or not isinstance(window_end, datetime):
            raise ValidationError("window_start and window_end must be datetimes")
        if window_start.tzinfo is None or window_end.tzinfo is None:
            raise ValidationError("window_start and window_end must be timezone-aware")
        if window_end <= window_start:
            raise ValidationError("window_end must be strictly after window_start")
        if not isinstance(required_quantity, int) or required_quantity <= 0:
            raise ValidationError("required_quantity must be a positive integer")
        if mode not in RESERVATION_MODES:
            raise ValidationError(f"mode must be one of {sorted(RESERVATION_MODES)}")
        if actor is None or not getattr(actor, "is_authenticated", False):
            raise PermissionError("Authentication required")
        if not idempotency_key or not isinstance(idempotency_key, str):
            raise ValidationError("idempotency_key is required")

        # -- 2. Offering
        offering = TransportOfferingRegistry.get(offering_code)
        if not offering:
            raise NotFoundError(f"Unknown or inactive offering '{offering_code}'",
                                resource_type="offering", resource_id=offering_code)

        # -- 3. Specific mode requires exact vehicle list
        if mode == "specific":
            if not specific_vehicle_ids or len(specific_vehicle_ids) != required_quantity:
                raise ValidationError(
                    "specific mode requires exactly `required_quantity` vehicle ids"
                )

        # -- 4. Idempotency lookup (before policy — so a retry that only differs
        #      in non-material fields still converges)
        existing = cls._lookup_idempotent(
            reserving_user_id=actor.id,
            idempotency_key=idempotency_key,
        )
        if existing is not None:
            return existing

        # -- 5. Policy evaluation
        decision: PolicyDecision = TransportReservationPolicyEvaluator.evaluate(
            actor=actor,
            offering_code=offering_code,
            provider_type=provider_type,
            provider_id=provider_id,
            quantity=required_quantity,
            window_start=window_start,
            window_end=window_end,
            payment_method=payment_method,
            payment_timing=payment_timing,
            commercial_policy_ref=commercial_policy_ref,
            on_behalf_of_organisation_id=on_behalf_of_organisation_id,
            authority_evidence=authority_evidence,
            estimated_value=estimated_value,
        )
        if not decision.allowed:
            raise PermissionError(decision.reason or "Reservation policy denied")

        # -- 6. Specific-mode vehicle ownership + eligibility proof
        if mode == "specific":
            cls._prove_vehicle_ownership(
                vehicle_ids=specific_vehicle_ids,
                provider_type=provider_type,
                provider_id=provider_id,
                offering=offering,
            )

        # -- 7. Supply coverage + capacity check (locked)
        cls._check_supply_coverage(
            provider_type=provider_type,
            provider_id=provider_id,
            offering_code=offering_code,
            window_start=window_start,
            window_end=window_end,
            quantity=required_quantity,
            mode=mode,
        )

        # -- 8. Persist header in DRAFT
        reservation = TransportReservation(
            reservation_reference=cls._generate_reference(),
            idempotency_key=idempotency_key,
            reserving_user_id=actor.id,
            on_behalf_of_organisation_id=on_behalf_of_organisation_id,
            authority_evidence=authority_evidence or {},
            event_id=event_id,
            offering_code=offering_code,
            provider_type=provider_type,
            provider_id=provider_id,
            window_start=window_start,
            window_end=window_end,
            required_quantity=required_quantity,
            mode=mode,
            state=ReservationState.DRAFT.value,
            obligation_state=ReservationObligationState.UNPAID.value,
            payment_method=(payment_method or "").strip().upper() or None,
            payment_timing=(payment_timing or "").strip().upper() or None,
            commercial_policy_ref=decision.commercial_policy_ref,
            deposit_required=bool(decision.requires_deposit),
            deposit_amount=decision.deposit_amount,
            deposit_currency=decision.deposit_currency,
            deposit_due_at=decision.deposit_due_at,
            context_source=context_source,
            context_ref=context_ref,
            policy_snapshot={
                "payment_method": payment_method,
                "payment_timing": payment_timing,
                "required_obligation_for_reserved": sorted(decision.required_obligation_for_reserved),
                "commercial_policy_ref": decision.commercial_policy_ref,
                "requires_deposit": decision.requires_deposit,
                "deposit_amount": str(decision.deposit_amount) if decision.deposit_amount else None,
                "deposit_due_at": decision.deposit_due_at.isoformat() if decision.deposit_due_at else None,
            },
            reservation_metadata={"created_from": "reservation_service", "schema_version": 1},
            audit_log=[],
        )
        try:
            db.session.add(reservation)
            db.session.flush()
        except sa.exc.IntegrityError as exc:
            db.session.rollback()
            # Concurrent create with same idempotency key — return the winner.
            winner = cls._lookup_idempotent(actor.id, idempotency_key)
            if winner is not None:
                return winner
            raise ConflictError("Concurrent reservation creation") from exc

        # -- 9. Materialise lines under lock
        try:
            cls._consume_capacity_locked(
                reservation=reservation,
                specific_vehicle_ids=specific_vehicle_ids,
                required_obligation_for_reserved=decision.required_obligation_for_reserved,
            )
        except Exception:
            db.session.rollback()
            raise

        audit_log(
            action="transport_reservation_created",
            resource_type="transport_reservation",
            resource_id=reservation.id,
            user_id=actor.id,
            details={
                "reservation_reference": reservation.reservation_reference,
                "offering_code": offering_code,
                "provider_type": provider_type,
                "provider_id": provider_id,
                "quantity": required_quantity,
                "mode": mode,
            },
            db_session=db.session,
        )

        if commit:
            db.session.commit()
            db.session.expire_all()
            return db.session.get(TransportReservation, reservation.id)
        return reservation

    # ==================================================================
    # Idempotency
    # ==================================================================
    @classmethod
    def _lookup_idempotent(cls, *, reserving_user_id: int, idempotency_key: str):
        return TransportReservation.query.filter_by(
            reserving_user_id=reserving_user_id,
            idempotency_key=idempotency_key,
            is_deleted=False,
        ).first()

    # ==================================================================
    # Vehicle ownership proof
    # ==================================================================
    @classmethod
    def _prove_vehicle_ownership(cls, *, vehicle_ids, provider_type, provider_id, offering):
        rows = Vehicle.query.filter(
            Vehicle.id.in_(vehicle_ids),
            Vehicle.is_deleted.is_(False),
        ).all()
        by_id = {v.id: v for v in rows}

        for vid in vehicle_ids:
            v = by_id.get(int(vid))
            if v is None:
                raise NotFoundError(f"Vehicle {vid} not found",
                                    resource_type="vehicle", resource_id=vid)

            # Provider ownership: match Vehicle.owner_type/owner_id
            expected_owner_type = (
                "organisation" if provider_type == VEHICLE_PROVIDER_TYPE_ORG else "driver"
            )
            if v.owner_type != expected_owner_type or int(v.owner_id) != int(provider_id):
                raise PermissionError(
                    f"Vehicle {vid} is not owned by the indicated provider"
                )

            # Active status
            if (v.status or "").lower() != "active":
                raise ValidationError(f"Vehicle {vid} is not in active status")

            # Offering eligibility: vehicle_class must be compatible with
            # the offering's declared compatibility set (stored on offering
            # metadata if present), or fall back to permissive mode.
            compat = (getattr(offering, "offering_metadata", None) or {}).get(
                "compatible_vehicle_classes"
            )
            if compat:
                vc = getattr(v.vehicle_class, "value", None) or getattr(v, "vehicle_class", None)
                if vc and vc not in compat:
                    raise ValidationError(
                        f"Vehicle {vid} (class={vc}) is not eligible for offering '{offering.code}'"
                    )

    # ==================================================================
    # Supply coverage + capacity
    # ==================================================================
    @classmethod
    def _check_supply_coverage(cls, *, provider_type, provider_id, offering_code,
                               window_start, window_end, quantity, mode):
        """Verify continuous supply coverage and sufficient capacity.

        Two invariants:
          A. Every instant of [window_start, window_end) is covered by at
             least one declared supply slice (no gaps).
          B. For each covered slice, committed units + requested ≤ slice total.
        """
        supplies = cls._lock_overlapping_supply_rows(
            provider_type=provider_type,
            provider_id=provider_id,
            offering_code=offering_code,
            window_start=window_start,
            window_end=window_end,
        )

        if not supplies:
            if mode == "capacity":
                raise SupplyCoverageError(
                    "Provider has not declared supply for this offering."
                )
            # Specific mode does not require declared supply, but does require
            # no other reservation to have claimed the slot (enforced by the
            # exclusion constraint on the line).
            return

        # A. Continuous coverage
        cls._assert_continuous_coverage(
            supplies=supplies,
            window_start=window_start,
            window_end=window_end,
        )

        # B. Capacity per slice
        for s in supplies:
            slice_start = max(s.window_start, window_start)
            slice_end = min(s.window_end, window_end)
            if slice_end <= slice_start:
                continue
            committed = cls._count_committed_in_slice(
                provider_type=provider_type,
                provider_id=provider_id,
                offering_code=offering_code,
                slice_start=slice_start,
                slice_end=slice_end,
            )
            available = int(s.total_units) - int(committed)
            if available < quantity:
                raise ReservationConflictError(
                    f"Insufficient supply for "
                    f"[{slice_start.isoformat()} .. {slice_end.isoformat()}]: "
                    f"requested {quantity}, available {available}"
                )

    @classmethod
    def _lock_overlapping_supply_rows(cls, *, provider_type, provider_id, offering_code,
                                      window_start, window_end):
        return db.session.execute(
            sa.select(ProviderOfferingSupply.__table__)
            .where(
                ProviderOfferingSupply.__table__.c.provider_type == provider_type,
                ProviderOfferingSupply.__table__.c.provider_id == provider_id,
                ProviderOfferingSupply.__table__.c.offering_code == offering_code,
                ProviderOfferingSupply.__table__.c.is_deleted.is_(False),
                ProviderOfferingSupply.__table__.c.window_start < window_end,
                ProviderOfferingSupply.__table__.c.window_end > window_start,
            )
            .order_by(
                ProviderOfferingSupply.__table__.c.window_start.asc(),
                ProviderOfferingSupply.__table__.c.id.asc(),
            )
            .with_for_update()
        ).all()

    @classmethod
    def _assert_continuous_coverage(cls, *, supplies, window_start, window_end):
        """Reject if any instant in [window_start, window_end) is uncovered."""
        sorted_slices: List[Tuple[datetime, datetime]] = sorted(
            ((s.window_start, s.window_end) for s in supplies),
            key=lambda t: t[0],
        )
        cursor = window_start
        for s_start, s_end in sorted_slices:
            if s_end <= cursor:
                continue
            if s_start > cursor:
                raise SupplyCoverageError(
                    f"Supply coverage gap between "
                    f"{cursor.isoformat()} and {s_start.isoformat()}"
                )
            cursor = max(cursor, s_end)
            if cursor >= window_end:
                return
        if cursor < window_end:
            raise SupplyCoverageError(
                f"Supply coverage ends at {cursor.isoformat()} "
                f"before requested window end {window_end.isoformat()}"
            )

    @classmethod
    def _count_committed_in_slice(cls, *, provider_type, provider_id, offering_code,
                                  slice_start, slice_end, exclude_reservation_id=None):
        q = (
            db.session.query(func.count(TransportReservationLine.id))
            .join(TransportReservation,
                  TransportReservationLine.reservation_id == TransportReservation.id)
            .filter(
                TransportReservation.provider_type == provider_type,
                TransportReservation.provider_id == provider_id,
                TransportReservation.offering_code == offering_code,
                TransportReservation.is_deleted.is_(False),
                TransportReservationLine.is_deleted.is_(False),
                TransportReservationLine.state.in_(ACTIVE_LINE_STATES),
                TransportReservationLine.window_start < slice_end,
                TransportReservationLine.window_end > slice_start,
            )
        )
        if exclude_reservation_id is not None:
            q = q.filter(TransportReservation.id != exclude_reservation_id)
        return int(q.scalar() or 0)

    # ==================================================================
    # Capacity consumption + line materialisation + state gating
    # ==================================================================
    @classmethod
    def _consume_capacity_locked(cls, *, reservation, specific_vehicle_ids,
                                 required_obligation_for_reserved):
        # Lines
        cls._materialise_lines(reservation=reservation,
                               specific_vehicle_ids=specific_vehicle_ids)
        # DRAFT → HELD (capacity is secured; reservation exists but is not
        # yet usable until the obligation gate is satisfied).
        SM.transition(reservation, ReservationState.HELD,
                      changed_by_user_id=reservation.reserving_user_id,
                      trigger="capacity_secured")

        # HELD → RESERVED only if the current obligation state already
        # satisfies the policy requirement for RESERVED.
        if SM.obligation_satisfies_reserved(
            reservation.obligation_state, required_obligation_for_reserved
        ):
            SM.transition(reservation, ReservationState.RESERVED,
                          changed_by_user_id=reservation.reserving_user_id,
                          trigger="obligation_satisfied")
        # Otherwise stay in HELD. The reservation is valid and capacity is
        # held; it will transition to RESERVED only after the obligation is
        # satisfied (see `apply_obligation_event`).

    @classmethod
    def _materialise_lines(cls, *, reservation, specific_vehicle_ids):
        if reservation.mode == "specific":
            for vid in specific_vehicle_ids or []:
                db.session.add(TransportReservationLine(
                    reservation_id=reservation.id,
                    offering_code=reservation.offering_code,
                    vehicle_id=int(vid),
                    window_start=reservation.window_start,
                    window_end=reservation.window_end,
                    state="held",
                    line_metadata={"mode": "specific"},
                ))
        else:
            for _ in range(reservation.required_quantity):
                db.session.add(TransportReservationLine(
                    reservation_id=reservation.id,
                    offering_code=reservation.offering_code,
                    vehicle_id=None,
                    window_start=reservation.window_start,
                    window_end=reservation.window_end,
                    state="held",
                    line_metadata={"mode": "capacity"},
                ))
        db.session.flush()

    # ==================================================================
    # Obligation transition (called by Wallet/Payment callback)
    # ==================================================================
    @classmethod
    def apply_obligation_event(
        cls,
        *,
        reservation_id: int,
        target_obligation: ReservationObligationState,
        wallet_transaction_reference: Optional[str] = None,
        commit: bool = True,
    ) -> TransportReservation:
        """Advance obligation state; promote HELD → RESERVED if policy allows.

        This is the ONLY entry point where a payment-side signal drives a
        reservation-side transition. The reservation state machine never
        inspects payment state directly.
        """
        row = db.session.get(TransportReservation, reservation_id)
        if row is None or row.is_deleted:
            raise NotFoundError("Reservation not found",
                                resource_type="transport_reservation",
                                resource_id=reservation_id)

        SM.transition_obligation(
            row, target_obligation,
            trigger="wallet_obligation_event",
        )
        if wallet_transaction_reference:
            row.wallet_transaction_reference = wallet_transaction_reference

        # Promote HELD → RESERVED if the policy's required obligations are now met.
        if row.state == ReservationState.HELD.value:
            required = set(
                (row.policy_snapshot or {}).get("required_obligation_for_reserved", [])
            )
            if SM.obligation_satisfies_reserved(row.obligation_state, required):
                SM.transition(row, ReservationState.RESERVED,
                              trigger="obligation_satisfied")

        if commit:
            db.session.commit()
            db.session.expire_all()
            return db.session.get(TransportReservation, row.id)
        return row

    # ==================================================================
    # Cancel
    # ==================================================================
    @classmethod
    def cancel_reservation(cls, *, reservation_id: int, actor, reason: Optional[str] = None,
                           commit: bool = True) -> TransportReservation:
        row = db.session.get(TransportReservation, reservation_id)
        if row is None or row.is_deleted:
            raise NotFoundError("Reservation not found",
                                resource_type="transport_reservation",
                                resource_id=reservation_id)

        is_admin = False
        try:
            is_admin = bool(getattr(actor, "has_global_role", lambda *_: False)(
                "admin", "super_admin", "owner"
            ))
        except Exception:
            is_admin = False

        if row.reserving_user_id != getattr(actor, "id", None) and not is_admin:
            raise PermissionError("Not authorised to cancel this reservation")

        if SM.is_terminal(row.state):
            return row

        result = db.session.execute(
            sa.update(TransportReservation.__table__)
            .where(
                TransportReservation.__table__.c.id == row.id,
                TransportReservation.__table__.c.state.in_([
                    ReservationState.HELD.value,
                    ReservationState.RESERVED.value,
                    ReservationState.MATERIALIZED.value,
                ]),
                TransportReservation.__table__.c.is_deleted.is_(False),
            )
            .values(state=ReservationState.CANCELLED.value)
            .execution_options(synchronize_session=False)
        )
        if result.rowcount != 1:
            db.session.rollback()
            raise ConflictError("Reservation is not in a cancellable state")

        db.session.execute(
            sa.update(TransportReservationLine.__table__)
            .where(
                TransportReservationLine.__table__.c.reservation_id == row.id,
                TransportReservationLine.__table__.c.state.in_(ACTIVE_LINE_STATES),
            )
            .values(state="cancelled")
            .execution_options(synchronize_session=False)
        )

        audit_log(
            action="transport_reservation_cancelled",
            resource_type="transport_reservation",
            resource_id=row.id,
            user_id=getattr(actor, "id", None),
            details={"reason": reason},
            db_session=db.session,
        )

        if commit:
            db.session.commit()
            db.session.expire_all()
            return db.session.get(TransportReservation, row.id)
        return row

    @classmethod
    def register_supply(
        cls,
        *,
        provider_type: str,
        provider_id: int,
        offering_code: str,
        window_start: datetime,
        window_end: datetime,
        total_units: int,
        commit: bool = True,
    ) -> ProviderOfferingSupply:
        if window_end <= window_start:
            raise ValidationError("window_end must be > window_start")
        if total_units <= 0:
            raise ValidationError("total_units must be > 0")

        # Reject overlap with any existing supply declaration for the same pool.
        existing_overlap = db.session.execute(
            sa.select(ProviderOfferingSupply.__table__.c.id)
            .where(
                ProviderOfferingSupply.__table__.c.provider_type == provider_type,
                ProviderOfferingSupply.__table__.c.provider_id == provider_id,
                ProviderOfferingSupply.__table__.c.offering_code == offering_code,
                ProviderOfferingSupply.__table__.c.is_deleted.is_(False),
                ProviderOfferingSupply.__table__.c.window_start < window_end,
                ProviderOfferingSupply.__table__.c.window_end > window_start,
            )
            .limit(1)
        ).first()
        if existing_overlap:
            raise ConflictError(
                "Overlapping supply declaration exists for this provider/offering"
            )

        row = ProviderOfferingSupply(
            provider_type=provider_type,
            provider_id=provider_id,
            offering_code=offering_code,
            window_start=window_start,
            window_end=window_end,
            total_units=total_units,
        )
        db.session.add(row)
        if commit:
            db.session.commit()
        else:
            db.session.flush()
        return row

    @classmethod
    def _generate_reference(cls) -> str:
        date_prefix = datetime.now(timezone.utc).strftime("%y%m%d")
        random_part = "".join(
            secrets.choice(string.ascii_uppercase + string.digits) for _ in range(8)
        )
        return f"RSV{date_prefix}{random_part}"


def get_reservation_service():
    return TransportReservationService