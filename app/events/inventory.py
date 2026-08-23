# app/events/inventory.py
"""
Atomic ticket-inventory reservation primitives for high-concurrency onsales.

This module is the ONLY place that mutates ``TicketType.available_seats``.
Every former read-modify-write decrement path (services.py, payment_service.py)
must route through these functions so inventory can never be oversold or leaked.

Reservation lifecycle (mirrors Accommodation RoomHold + AvailabilityService):

    reserved -> confirmed | released | expired | cancelled

Public high-volume path is reserve-then-pay:

    1. reserve_capacity()      : atomically decrement inventory + create a
                                 TicketHold with a short TTL (default 10 min)
    2. client pays via Wallet  : idempotent WalletService.withdraw(client_request_id)
    3. confirm_reservation()   : mark the hold confirmed, create EventRegistration
    4. on TTL expiry / cancel  : release_capacity() returns inventory to the pool

Legacy inline paths (register_for_event_optimistic, EventPaymentService) use
decrement_capacity() / increment_capacity() which perform the same atomic
decrement/increment without creating a hold. They share the same lock ordering
and event-level cap logic via _atomic_decrement().

Invariants preserved:
  * Wallet remains the sole owner of money; this module only stores wallet_txn_id.
  * Internal BigInteger FKs are used; reservation_token/public_id are the only
    external identifiers.
  * No new PostgreSQL ENUM types (status is a validated String + CHECK constraint).
"""

import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from flask import current_app
from app.utils.db_retry import retry_on_deadlock
from sqlalchemy import func, update
from sqlalchemy import (
    Column,
    BigInteger,
    Integer,
    String,
    Text,
    DateTime,
    Index,
    UniqueConstraint,
    CheckConstraint,
    ForeignKey,
)
from sqlalchemy.orm import relationship

from app.extensions import db
from app.models.base import BaseModel
from app.utils.db_retry import retry_on_deadlock


HOLD_TTL_MINUTES_DEFAULT = 10


class ReservationInventoryError(Exception):
    """Raised when inventory cannot satisfy a reservation request."""


class ReservationStatus:
    """TicketHold lifecycle states (stored as String, validated by CHECK)."""

    RESERVED = "reserved"
    CONFIRMED = "confirmed"
    RELEASED = "released"
    EXPIRED = "expired"
    CANCELLED = "cancelled"

    VALID = frozenset({RESERVED, CONFIRMED, RELEASED, EXPIRED, CANCELLED})
    TERMINAL = frozenset({CONFIRMED, RELEASED, EXPIRED, CANCELLED})


class TicketHold(BaseModel):
    __tablename__ = "event_ticket_holds"
    __table_args__ = (
        Index("idx_ticket_hold_event_status", "event_id", "status"),
        Index("idx_ticket_hold_ticket_status", "ticket_type_id", "status"),
        Index("idx_ticket_hold_user", "user_id"),
        Index("idx_ticket_hold_expires", "status", "expires_at"),
        UniqueConstraint("reservation_token", name="uq_ticket_hold_token"),
        UniqueConstraint("public_id", name="uq_ticket_hold_public_id"),
        CheckConstraint(
            "status IN ('reserved','confirmed','released','expired','cancelled')",
            name="ck_ticket_hold_status",
        ),
        CheckConstraint("hold_minutes > 0", name="ck_ticket_hold_minutes_positive"),
        CheckConstraint("quantity > 0", name="ck_ticket_hold_quantity_positive"),
    )

    public_id = Column(
        String(64), unique=True, nullable=False,
        default=lambda: str(uuid.uuid4()), index=True,
    )
    reservation_token = Column(String(64), unique=True, nullable=False)
    event_id = Column(
        BigInteger, ForeignKey("events.id", ondelete="RESTRICT"),
        nullable=False, index=True,
    )
    ticket_type_id = Column(
        BigInteger, ForeignKey("event_ticket_types.id", ondelete="RESTRICT"),
        nullable=False, index=True,
    )
    user_id = Column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True, index=True,
    )
    quantity = Column(Integer, nullable=False, default=1)
    status = Column(String(20), nullable=False, default=ReservationStatus.RESERVED)
    idempotency_key = Column(String(255), nullable=True, index=True)
    wallet_txn_id = Column(String(255), nullable=True)
    payment_status = Column(String(30), nullable=True)
    hold_minutes = Column(Integer, nullable=False, default=HOLD_TTL_MINUTES_DEFAULT)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    released_at = Column(DateTime(timezone=True), nullable=True)
    release_reason = Column(Text, nullable=True)
    converted_registration_id = Column(BigInteger, nullable=True)

    event = relationship("Event", foreign_keys=[event_id])
    ticket_type = relationship("TicketType", foreign_keys=[ticket_type_id])
    user = relationship("User", foreign_keys=[user_id])

    @property
    def is_expired_flag(self) -> bool:
        if self.status != ReservationStatus.RESERVED:
            return False
        expires_at = self.expires_at
        if expires_at and expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        return expires_at <= datetime.now(timezone.utc)

    def mark_confirmed(self, wallet_txn_id: Optional[str] = None,
                       registration_id: Optional[int] = None) -> None:
        self.status = ReservationStatus.CONFIRMED
        if wallet_txn_id is not None:
            self.wallet_txn_id = wallet_txn_id
        if registration_id is not None:
            self.converted_registration_id = registration_id
        self.release_reason = "Converted to registration"

    def mark_released(self, reason: Optional[str] = None) -> None:
        self.status = ReservationStatus.RELEASED
        self.released_at = datetime.now(timezone.utc)
        self.release_reason = reason

    def mark_expired(self) -> None:
        self.status = ReservationStatus.EXPIRED
        self.released_at = datetime.now(timezone.utc)
        self.release_reason = "Hold expired"

    def mark_cancelled(self, reason: Optional[str] = None) -> None:
        self.status = ReservationStatus.CANCELLED
        self.released_at = datetime.now(timezone.utc)
        self.release_reason = reason


def _load_models():
    from app.events.models import Event, TicketType

    return Event, TicketType


def _event_consumed_seats(event_id: int) -> int:
    """Sum of sold seats across all limited ticket types for an event.

    Must be evaluated while the event row is locked (see _atomic_decrement).
    """
    _, TicketType = _load_models()
    consumed = db.session.query(
        func.coalesce(
            func.sum(
                TicketType.capacity
                - func.coalesce(TicketType.available_seats, TicketType.capacity)
            ),
            0,
        )
    ).filter(
        TicketType.event_id == event_id,
        TicketType.capacity > 0,
    ).scalar()
    return int(consumed or 0)


def _atomic_decrement(event_id: int, ticket_type_id: int, quantity: int) -> None:
    """Atomically reserve `quantity` seats, honouring both tier and event caps.

    Correctness rests on a single atomic conditional UPDATE:

        UPDATE event_ticket_types
           SET available_seats = available_seats - :q
         WHERE id = :id AND available_seats >= :q AND is_active

    This is the ONLY gate that decides whether a seat exists. PostgreSQL
    serialises these UPDATEs on the tier row, so there is no window in which
    two buyers can both observe and consume the same seat.

    Crucially we do NOT ``SELECT ... FOR UPDATE`` the tier row before updating
    it: under READ COMMITTED that pattern establishes a snapshot and then
    collides with concurrently-committed updates, producing
    "could not serialize access due to concurrent update" (SQLSTATE 40001)
    thrashing. The conditional UPDATE reads the latest committed value and
    applies atomically, so it never raises a serialization anomaly.

    The event-level derived cap (when configured) is enforced under an Event
    row lock so concurrent decrementors serialize that decision. Callers must
    let this run inside their own transaction (no commit here).
    """
    if quantity < 1:
        raise ValueError("quantity must be >= 1")

    Event, TicketType = _load_models()

    # Verify the event exists and decide whether an event-level cap applies.
    event = db.session.query(Event).filter_by(id=event_id).first()
    if event is None:
        raise ReservationInventoryError("Event not found")

    if event.max_capacity and event.max_capacity > 0:
        # Lock the event row so the derived-cap check + decrement are serialised
        # against other decrementors for this event.
        event = (
            db.session.query(Event)
            .with_for_update()
            .filter_by(id=event_id)
            .first()
        )
        consumed = _event_consumed_seats(event_id)
        if consumed + quantity > event.max_capacity:
            raise ReservationInventoryError("Event has reached full capacity")

    # Atomic conditional decrement of the tier. No prior snapshot read of the
    # hot row, so READ COMMITTED cannot raise a serialization anomaly here.
    result = db.session.execute(
        update(TicketType)
        .where(
            TicketType.id == ticket_type_id,
            TicketType.event_id == event_id,
            TicketType.is_active.is_(True),
            TicketType.available_seats >= quantity,
        )
        .values(available_seats=TicketType.available_seats - quantity)
    )

    if result.rowcount == 0:
        # The conditional UPDATE touched no rows. Distingurish "sold out" from
        # "missing/inactive/unlimited" so callers get a precise error.
        tt = (
            db.session.query(TicketType)
            .filter_by(id=ticket_type_id, event_id=event_id)
            .first()
        )
        if tt is None:
            raise ReservationInventoryError("Ticket type not found")
        if not tt.is_active:
            raise ReservationInventoryError("Ticket type is not available for sale")
        # Unlimited tier (capacity == 0): nothing to decrement, succeed silently.
        if not tt.capacity or tt.capacity == 0:
            return
        available = (
            tt.available_seats if tt.available_seats is not None else tt.capacity
        )
        if available < quantity:
            raise ReservationInventoryError(
                f"Only {available} ticket(s) available for '{tt.name}'"
            )
        raise ReservationInventoryError("Ticket inventory unavailable")

@retry_on_deadlock(max_retries=5)
def decrement_capacity(ticket_type_id: int, quantity: int = 1,
                       event_id: Optional[int] = None) -> None:
    """Atomic inventory decrement without creating a hold (legacy/fallback path)."""
    if quantity < 1:
        raise ValueError("quantity must be >= 1")
    Event, TicketType = _load_models()
    if event_id is None:
        tt = db.session.query(TicketType).filter_by(id=ticket_type_id).first()
        if tt is None:
            raise ReservationInventoryError("Ticket type not found")
        event_id = tt.event_id
    _atomic_decrement(event_id, ticket_type_id, quantity)
    db.session.flush()


@retry_on_deadlock(max_retries=5)
def increment_capacity(ticket_type_id: int, quantity: int = 1) -> int:
    """Atomically return `quantity` seats to the pool (release / cancel / refund)."""
    from sqlalchemy import func as sqlfunc

    if quantity < 1:
        return 0
    _, TicketType = _load_models()
    updated = (
        db.session.query(TicketType)
        .filter(TicketType.id == ticket_type_id, TicketType.capacity > 0)
        .update(
            {
                TicketType.available_seats: sqlfunc.least(
                    TicketType.capacity,
                    sqlfunc.coalesce(TicketType.available_seats, TicketType.capacity)
                    + quantity,
                )
            },
            synchronize_session=False,
        )
    )
    return updated


@retry_on_deadlock(max_retries=10, base_delay=0.05, max_delay=1.0)
def reserve_capacity(event_id: int, ticket_type_id: int, quantity: int = 1, *,
                     user_id: Optional[int] = None, hold_minutes: Optional[int] = None,
                     idempotency_key: Optional[str] = None, commit: bool = True) -> "TicketHold":
    """Reserve seats and create a short-lived TicketHold.

    The inventory is decremented immediately so the seat cannot be sold twice
    during the payment window. The whole reserve + commit runs inside the
    deadlock/serialisation retry, so a transient PostgreSQL 40001
    (serialization failure) or 40P01 (deadlock) raised at COMMIT time is
    retried as a single unit. Without this, a buyer who should have won could
    be wrongly rejected (or 500'd) under a hot onsale, because the row-lock
    dance and the commit are one inseparable transaction.

    By default the transaction is committed here. Pass ``commit=False`` to
    defer the commit and compose the hold with other work in the caller's own
    transaction (the caller then owns committing and retrying that commit).

    Raises ReservationInventoryError on insufficient inventory — a business
    rejection that is never retried.
    """
    if quantity < 1:
        raise ValueError("quantity must be >= 1")

    hold_minutes = int(
        hold_minutes
        or current_app.config.get("TICKET_HOLD_MINUTES", HOLD_TTL_MINUTES_DEFAULT)
    )

    _atomic_decrement(event_id, ticket_type_id, quantity)

    expires_at = datetime.now(timezone.utc) + timedelta(minutes=hold_minutes)
    hold = TicketHold(
        event_id=event_id,
        ticket_type_id=ticket_type_id,
        user_id=user_id,
        quantity=quantity,
        status=ReservationStatus.RESERVED,
        public_id=str(uuid.uuid4()),
        reservation_token=secrets.token_hex(16),
        idempotency_key=idempotency_key,
        hold_minutes=hold_minutes,
        expires_at=expires_at,
    )
    db.session.add(hold)
    db.session.flush()
    if commit:
        db.session.commit()
    return hold


def release_capacity(ticket_type_id: int, quantity: int = 1) -> int:
    """Return inventory to the pool (public alias of the increment primitive)."""
    return increment_capacity(ticket_type_id, quantity)


@retry_on_deadlock(max_retries=5)
def release_hold(hold: "TicketHold", reason: Optional[str] = "released") -> bool:
    """Release a reserved hold and return its seats to the pool."""
    if hold is None or hold.status != ReservationStatus.RESERVED:
        return False
    release_capacity(hold.ticket_type_id, hold.quantity)
    hold.mark_released(reason)
    db.session.flush()
    return True


@retry_on_deadlock(max_retries=5)
def confirm_reservation(hold: "TicketHold", wallet_txn_id: Optional[str] = None,
                        registration_id: Optional[int] = None) -> "TicketHold":
    """Mark a reserved hold as confirmed (payment succeeded, registration created).

    Idempotent: confirming an already-confirmed hold is a no-op. Inventory was
    already decremented at reserve time, so nothing else changes here.
    """
    if hold is None:
        raise ReservationInventoryError("Hold not found")
    if hold.status == ReservationStatus.CONFIRMED:
        return hold
    if hold.status in (ReservationStatus.RELEASED, ReservationStatus.EXPIRED,
                       ReservationStatus.CANCELLED):
        raise ReservationInventoryError(f"Hold is {hold.status} and cannot be confirmed")
    hold.mark_confirmed(wallet_txn_id=wallet_txn_id, registration_id=registration_id)
    db.session.flush()
    return hold
