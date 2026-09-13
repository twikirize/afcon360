"""Expiry primitive for held Transport reservations (TH-3-D3 Batch 2)."""
from __future__ import annotations

from datetime import datetime, timezone

import sqlalchemy as sa

from app.extensions import db
from app.transport.models import TransportReservation, TransportReservationLine
from app.transport.services.reservation_service import ACTIVE_LINE_STATES
from app.transport.services.reservation_state_machine import ReservationState


class TransportReservationExpiryService:
    """Expires only held reservations with an unpaid, elapsed deposit deadline."""

    @classmethod
    def expire_due_held_reservations(cls, *, limit=None, commit=True):
        now = datetime.now(timezone.utc)
        candidates = db.session.execute(
            sa.select(TransportReservation.id)
            .where(
                TransportReservation.state == ReservationState.HELD.value,
                TransportReservation.deposit_due_at.isnot(None),
                TransportReservation.deposit_due_at < now,
                TransportReservation.obligation_state == "unpaid",
                TransportReservation.is_deleted.is_(False),
            )
            .order_by(TransportReservation.deposit_due_at, TransportReservation.id)
            .limit(limit) if limit else sa.select(TransportReservation.id)
            .where(
                TransportReservation.state == ReservationState.HELD.value,
                TransportReservation.deposit_due_at.isnot(None),
                TransportReservation.deposit_due_at < now,
                TransportReservation.obligation_state == "unpaid",
                TransportReservation.is_deleted.is_(False),
            ).order_by(TransportReservation.deposit_due_at, TransportReservation.id)
        ).scalars().all()
        summary = {"examined": len(candidates), "expired": 0, "skipped": 0}
        for reservation_id in candidates:
            result = db.session.execute(
                sa.update(TransportReservation.__table__)
                .where(
                    TransportReservation.__table__.c.id == reservation_id,
                    TransportReservation.__table__.c.state == ReservationState.HELD.value,
                    TransportReservation.__table__.c.obligation_state == "unpaid",
                    TransportReservation.__table__.c.deposit_due_at < now,
                    TransportReservation.__table__.c.is_deleted.is_(False),
                )
                .values(state=ReservationState.EXPIRED.value)
            )
            if result.rowcount != 1:
                summary["skipped"] += 1
                continue
            db.session.execute(
                sa.update(TransportReservationLine.__table__)
                .where(
                    TransportReservationLine.__table__.c.reservation_id == reservation_id,
                    TransportReservationLine.__table__.c.state.in_(ACTIVE_LINE_STATES),
                ).values(state="cancelled")
            )
            summary["expired"] += 1
        if commit:
            db.session.commit()
        return summary
