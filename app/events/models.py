# app/events/models.py
"""
Event data models.

Design principles
─────────────────
1.  PostgreSQL is the source of truth.  Nothing is ever physically deleted.
2.  creator  ≠  owner.  The person/system that created the record is immutable;
    ownership can transfer via EventTransferRequest.
3.  Every status transition is recorded in EventModerationLog (append-only).
4.  Financial and registration records outlive the event itself.
5.  Soft-delete hierarchy:
      organiser action  →  ARCHIVED  (is_deleted=True, still queried by admins)
      admin removal     →  DELETED   (is_deleted=True, excluded from all normal queries)
"""

import uuid
import enum
import warnings
import hmac
import hashlib
import os
from datetime import datetime, timezone

from sqlalchemy import (
    Column, BigInteger, Integer, String, Boolean, DateTime, Date,
    ForeignKey, Text, Numeric, JSON, Index, UniqueConstraint, CheckConstraint,
    Sequence,
)
from sqlalchemy.orm import relationship, backref
from sqlalchemy.sql import func

from app.extensions import db
from app.models.base import BaseModel
from app.utils.id_kinds import IDKind
from app.events.constants import (
    EventStatus,
    ALLOWED_TRANSITIONS,
    validate_transition,
    BookingType,
)


# ============================================================================
# HELPERS
# ============================================================================

def _deprecated(new_name: str):
    """
    Descriptor that delegates to `new_name` and emits DeprecationWarning.
    Usage (class body):
        is_active = _deprecated("is_active_flag")
    """

    @property
    def prop(self):
        warnings.warn(
            f"'{new_name.replace('_flag', '')}' is deprecated - use '{new_name}'.",
            DeprecationWarning,
            stacklevel=2,
        )
        return getattr(self, new_name)

    return prop


def _owner_type_value(value):
    """Return the string value from either a string enum or a plain string."""
    return getattr(value, "value", value)


# ============================================================================
# ENUM CLASSES
# ============================================================================

class CreatorType(str, enum.Enum):
    """
    Who *created* the event record.  This is immutable after creation.

    INDIVIDUAL   - a human user pressed the button
    ORGANIZATION - an organisation's automated workflow created it
    SYSTEM       - the platform itself created it (e.g. anniversary events,
                   auto-generated fixtures).  current_owner_id = 0 in this case.
    """
    INDIVIDUAL = "individual"
    ORGANIZATION = "organization"
    SYSTEM = "system"


class OwnerType(str, enum.Enum):
    """
    Who *currently controls* the event.  Can change via EventTransferRequest.

    Example: a manager (INDIVIDUAL creator) creates an event on behalf of a
    client (INDIVIDUAL owner) - creator ≠ owner from day one.
    """
    INDIVIDUAL = "individual"
    ORGANIZATION = "organization"
    SYSTEM = "system"  # platform-owned event; owner_id = 0


class TransferStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


class DiscountType(str, enum.Enum):
    PERCENTAGE = "percentage"
    FIXED = "fixed"


# Sentinel value used when the system itself is the owner/creator (no real user).
SYSTEM_OWNER_ID: int = 0


# ============================================================================
# EVENT MODEL
# ============================================================================

class Event(BaseModel):
    __tablename__ = "events"
    __table_args__ = (
        # ── Performance indexes ────────────────────────────────────────────
        Index("idx_event_start_date", "start_date"),
        Index("idx_event_status_featured", "status", "featured"),
        Index("idx_event_slug_unique", "slug", unique=True),
        Index("idx_event_category", "category"),
        Index("idx_event_organizer_status", "organizer_id", "status"),
        Index("idx_event_status_start", "status", "start_date"),
        Index("idx_event_creator", "created_by_type", "created_by_id"),
        Index("idx_event_organization", "organization_id"),
        Index("idx_event_system", "is_system_event"),
        Index("idx_event_current_owner", "current_owner_type", "current_owner_id"),
        # ── Constraints ────────────────────────────────────────────────────
        UniqueConstraint("slug", name="uq_event_slug"),
        CheckConstraint("end_date >= start_date",
                        name="ck_event_end_after_start"),
        CheckConstraint(
            "registration_opens_at IS NULL OR registration_closes_at IS NULL "
            "OR registration_closes_at > registration_opens_at",
            name="ck_event_registration_window_order",
        ),
        CheckConstraint("max_capacity >= 0",
                        name="ck_event_max_capacity_non_negative"),
        CheckConstraint(
            # system events must use SYSTEM_OWNER_ID (0)
            "NOT (current_owner_type = 'system' AND current_owner_id != 0)",
            name="ck_system_owner_id_zero",
        ),
    )

    # ── Identifiers ────────────────────────────────────────────────────────
    public_id = Column(String(64), unique=True, nullable=False,
                       default=lambda: str(uuid.uuid4()), index=True)
    event_ref = Column(String(50), unique=True)
    slug = Column(String(120), nullable=False)

    # ── Core fields ────────────────────────────────────────────────────────
    name = Column(String(255), nullable=False)
    description = Column(Text, default='', server_default='')
    category = Column(String(50), nullable=False, default="general")
    city = Column(String(100), nullable=False)
    country = Column(String(100), default="Uganda")
    venue = Column(String(255))
    start_date = Column(Date)
    end_date = Column(Date)
    max_capacity = Column(Integer, default=0, nullable=False)
    registration_required = Column(Boolean, default=False)
    registration_fee = Column(Numeric(10, 2), default=0, nullable=False)
    registration_opens_at = Column(DateTime(timezone=True), nullable=True)
    registration_closes_at = Column(DateTime(timezone=True), nullable=True)
    currency = Column(String(3), default="USD")
    featured = Column(Boolean, default=False)
    website = Column(String(500))
    contact_email = Column(String(255))
    contact_phone = Column(String(50))
    event_metadata = Column(JSON, default=dict)

    # ── Status ─────────────────────────────────────────────────────────────
    status = Column(
        String(30),
        default=EventStatus.PENDING_APPROVAL.value,
        nullable=False,
        index=True
    )

    # ── Organiser (the public-facing contact, may differ from creator/owner) ─
    organizer_id = Column(BigInteger, ForeignKey("users.id"), nullable=False)

    # ── Approval / rejection audit ─────────────────────────────────────────
    approved_at = Column(DateTime(timezone=True), nullable=True)
    approved_by_id = Column(BigInteger, ForeignKey("users.id"), nullable=True)
    rejected_at = Column(DateTime(timezone=True), nullable=True)
    rejection_reason = Column(Text, nullable=True)

    # Internal moderation notes (separate from rejection_reason which goes to organiser)
    moderation_notes = Column(Text, nullable=True)

    # ── Moderation enforcement ─────────────────────────────────────────────
    suspension_reason = Column(Text, nullable=True)
    suspension_duration = Column(String(20), nullable=True)
    suspended_at = Column(DateTime(timezone=True), nullable=True)
    suspended_by_id = Column(BigInteger, ForeignKey("users.id"), nullable=True)

    deactivation_reason = Column(Text, nullable=True)
    deactivated_at = Column(DateTime(timezone=True), nullable=True)
    deactivated_by_id = Column(BigInteger, ForeignKey("users.id"), nullable=True)

    takedown_reason = Column(Text, nullable=True)
    takedown_category = Column(String(50), nullable=True)
    taken_down_at = Column(DateTime(timezone=True), nullable=True)
    taken_down_by_id = Column(BigInteger, ForeignKey("users.id"), nullable=True)

    # ── Completion (auto-set by scheduler) ────────────────────────────────
    completed_at = Column(DateTime(timezone=True), nullable=True)
    published_at = Column(DateTime(timezone=True), nullable=True)
    published_by_id = Column(BigInteger, ForeignKey("users.id"), nullable=True)

    # ── Soft delete ────────────────────────────────────────────────────────
    # is_deleted=True + status=ARCHIVED  → organiser soft-deleted
    # is_deleted=True + status=DELETED   → admin removed
    deleted_by_id = Column(BigInteger, ForeignKey("users.id"), nullable=True)
    deletion_reason = Column(Text, nullable=True)

    # ── Optimistic locking ─────────────────────────────────────────────────
    version = Column(Integer, default=0, nullable=False)

    # ── Submission preferences (set by organiser at submit time) ──────────
    auto_publish_on_approval = Column(Boolean, default=False, nullable=False)
    publish_permission = Column(String(20), default='either', nullable=False)

    # risk_flags: list of strings populated at submission time.
    risk_flags = Column(JSON, default=list, nullable=False)

    # ── Standard audit trail ───────────────────────────────────────────────
    created_by_id = Column(BigInteger, ForeignKey("users.id"), nullable=True)
    updated_by_id = Column(BigInteger, ForeignKey("users.id"), nullable=True)

    # ── Creator (immutable after creation) ────────────────────────────────
    created_by_type = Column(
        String(20),
        nullable=False,
        default=CreatorType.INDIVIDUAL.value,
    )
    created_by_entity_id = Column(BigInteger, nullable=False, default=0)

    # ── Owner (mutable via EventTransferRequest) ───────────────────────────
    current_owner_type = Column(
        String(20),
        nullable=False,
        default=OwnerType.INDIVIDUAL.value,
    )
    current_owner_id = Column(BigInteger, nullable=False)

    # ── Organisation context ───────────────────────────────────────────────
    organization_id = Column(
        BigInteger,
        ForeignKey("organisations.id", ondelete="SET NULL"),
        nullable=True, index=True,
    )
    is_system_event = Column(Boolean, default=False, nullable=False, )
    original_creator_id = Column(
        BigInteger,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # ── Relationships ──────────────────────────────────────────────────────
    organizer = relationship("User", foreign_keys=[organizer_id])
    approved_by = relationship("User", foreign_keys=[approved_by_id])
    deleted_by = relationship("User", foreign_keys=[deleted_by_id])
    created_by = relationship("User", foreign_keys=[created_by_id])
    updated_by = relationship("User", foreign_keys=[updated_by_id])
    suspended_by = relationship("User", foreign_keys=[suspended_by_id])
    deactivated_by = relationship("User", foreign_keys=[deactivated_by_id])
    taken_down_by = relationship("User", foreign_keys=[taken_down_by_id])
    registrations = relationship("EventRegistration", back_populates="event",
                                 cascade="all, delete-orphan")
    ticket_types = relationship("TicketType", back_populates="event",
                                cascade="all, delete-orphan")

    # ── Constructor ────────────────────────────────────────────────────────

    def __init__(self, **kwargs):
        if 'organizer_id' in kwargs and kwargs.get('current_owner_id') is None:
            import logging
            import warnings
            warnings.warn(
                'Event constructor organizer_id parameter is DEPRECATED (Phase 4 Step 5)',
                DeprecationWarning,
                stacklevel=2,
            )
            logging.getLogger(__name__).warning(
                'LEGACY CONSTRUCTOR FALLBACK: Event initialized with organizer_id. Phase 4 Deprecation.'
            )
        super().__init__(**kwargs)
        self._ensure_public_id()
        self._set_default_owner()

    def __repr__(self):
        return f"<Event {self.id}: {self.name!r} [{self.status}]>"

    # ── Internal helpers ───────────────────────────────────────────────────

    def _ensure_public_id(self):
        if not self.public_id:
            self.public_id = str(uuid.uuid4())

    def _set_default_owner(self):
        """
        If no owner was explicitly provided, derive sensible defaults.
        For system events the owner is always SYSTEM / id=0.
        For individual events the owner defaults to the organiser.
        """
        if self.is_system_event:
            self.current_owner_type = OwnerType.SYSTEM.value
            self.current_owner_id = SYSTEM_OWNER_ID
            return

        if not self.current_owner_id and self.organizer_id:
            self.current_owner_type = OwnerType.INDIVIDUAL.value
            self.current_owner_id = self.organizer_id

        if not self.created_by_entity_id and self.organizer_id:
            self.created_by_entity_id = self.organizer_id

    def generate_ref(self):
        self.event_ref = f"EVT-{self.slug.upper()[:20]}"

    # ── Status flag properties ─────────────────────────────────────────────

    @property
    def is_draft(self) -> bool:
        return self.status == EventStatus.DRAFT.value

    @property
    def is_pending(self) -> bool:
        return self.status == EventStatus.PENDING_APPROVAL.value

    @property
    def is_approved(self) -> bool:
        return self.status == EventStatus.APPROVED.value

    @property
    def is_rejected(self) -> bool:
        return self.status == EventStatus.REJECTED.value

    @property
    def is_published(self) -> bool:
        return self.status == EventStatus.PUBLISHED.value

    @property
    def is_suspended(self) -> bool:
        return self.status == EventStatus.SUSPENDED.value

    @property
    def is_paused(self) -> bool:
        return self.status == EventStatus.PAUSED.value

    @property
    def is_cancelled(self) -> bool:
        return self.status == EventStatus.CANCELLED.value

    @property
    def is_completed(self) -> bool:
        return self.status == EventStatus.COMPLETED.value

    @property
    def is_archived(self) -> bool:
        return self.status == EventStatus.ARCHIVED.value

    @property
    def is_deleted_flag(self) -> bool:
        return self.status == EventStatus.DELETED.value

    @property
    def is_terminal(self) -> bool:
        """Check if event is in a terminal state"""
        return self.status in EventStatus.get_terminal_statuses()

    @property
    def accepts_registrations(self) -> bool:
        """Check if event accepts new registrations"""
        return EventStatus.can_register(self.status)

    @property
    def needs_moderation(self) -> bool:
        """Check if event needs moderator review"""
        return EventStatus.needs_moderation(self.status)

    # ── State-machine transition helpers ──────────────────────────────────

    def transition_to(self, new_status: str, actor_id: int,
                      reason: str = None,
                      ip_address: str = None,
                      user_agent: str = None) -> "EventModerationLog":
        """
        Validate and apply a status transition.
        Returns the moderation log entry (not yet committed).
        """
        allowed, msg = validate_transition(self.status, new_status)
        if not allowed:
            raise ValueError(msg)

        # Create log entry
        log = EventModerationLog(
            event_id=self.id,
            user_id=actor_id,
            action=f"{self.status}_to_{new_status}",
            from_status=self.status,
            to_status=new_status,
            reason=reason,
            ip_address=ip_address,
            user_agent=user_agent,
        )

        # Update timestamps based on target status
        now = datetime.now(timezone.utc)
        if new_status == EventStatus.APPROVED.value:
            self.approved_at = now
            self.approved_by_id = actor_id
        elif new_status == EventStatus.REJECTED.value:
            self.rejected_at = now
            self.rejection_reason = reason
        elif new_status == EventStatus.SUSPENDED.value:
            self.suspended_at = now
            self.suspended_by_id = actor_id
            self.suspension_reason = reason
        elif new_status == EventStatus.PUBLISHED.value:
            self.published_at = now
            self.published_by_id = actor_id
        elif new_status == EventStatus.COMPLETED.value:
            self.completed_at = now
        elif new_status in (EventStatus.ARCHIVED.value, EventStatus.DELETED.value):
            self.deleted_at = now
            self.deleted_by_id = actor_id
            self.deletion_reason = reason
            self.is_deleted = True

        self.status = new_status
        return log

    def soft_delete(self, user_id: int, reason: str = None) -> "EventModerationLog":
        """
        Organiser soft-delete → ARCHIVED.
        The event is hidden from all public views but never physically removed.
        Registrations, financial records, and logs are preserved.
        """
        return self.transition_to(
            EventStatus.ARCHIVED.value,
            actor_id=user_id,
            reason=reason or "Organiser deleted",
        )

    def admin_remove(self, admin_id: int, reason: str) -> "EventModerationLog":
        """
        Admin hard-remove → DELETED.
        Still never physically removed - just excluded from all normal queries.
        """
        return self.transition_to(
            EventStatus.DELETED.value,
            actor_id=admin_id,
            reason=reason,
        )

    def restore(self):
        """Undo a soft-delete back to DRAFT for organiser revision."""
        self.deleted_at = None
        self.deleted_by_id = None
        self.deletion_reason = None
        self.is_deleted = False
        self.status = EventStatus.DRAFT.value

    # ── Ownership helpers ─────────────────────────────────────────────────

    def is_owned_by_user(self, user_id: int) -> bool:
        return (
                _owner_type_value(self.current_owner_type) == OwnerType.INDIVIDUAL.value
                and self.current_owner_id == user_id
        )

    def is_owned_by_organization(self, org_id: int) -> bool:
        return (
                _owner_type_value(self.current_owner_type) == OwnerType.ORGANIZATION.value
                and self.current_owner_id == org_id
        )

    def is_created_by_user(self, user_id: int) -> bool:
        return (
                _owner_type_value(self.created_by_type) == CreatorType.INDIVIDUAL.value
                and self.created_by_entity_id == user_id
        )

    def is_system_owned(self) -> bool:
        return _owner_type_value(self.current_owner_type) == OwnerType.SYSTEM.value


# ============================================================================
# TICKET TYPE MODEL
# ============================================================================

class TicketType(BaseModel):
    __tablename__ = "event_ticket_types"
    __table_args__ = (
        Index("idx_ticket_type_event_active", "event_id", "is_active"),
    )

    event_id = Column(BigInteger, ForeignKey("events.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(100), nullable=False)
    description = Column(Text)
    price = Column(Numeric(10, 2), default=0)
    capacity = Column(Integer, default=0, nullable=False)
    available_seats = Column(Integer, nullable=True)
    version = Column(Integer, default=0, nullable=False)
    available_from = Column(DateTime(timezone=True), nullable=True)
    available_until = Column(DateTime(timezone=True), nullable=True)
    is_active = Column(Boolean, default=True)

    event = relationship("Event", back_populates="ticket_types")
    registrations = relationship("EventRegistration", back_populates="ticket_type_rel")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if self.available_seats is None:
            self.available_seats = self.capacity

    def __repr__(self):
        return f"<TicketType {self.name!r} event_id={self.event_id}>"

    # ── Seat management ────────────────────────────────────────────────────

    def _sync_available_seats(self):
        """Re-compute available_seats from DB (use when cache is stale)."""
        from sqlalchemy import func as sqlfunc
        count = (
            db.session.query(sqlfunc.count(EventRegistration.id))
            .filter(
                EventRegistration.ticket_type_id == self.id,
                EventRegistration.status.notin_(["cancelled", "expired"]),
            )
            .scalar()
        )
        self.available_seats = max(0, self.capacity - count)

    @property
    def is_sold_out_flag(self) -> bool:
        if self.capacity == 0:
            return False  # unlimited
        if self.available_seats is None:
            self._sync_available_seats()
        return self.available_seats <= 0

    is_sold_out = _deprecated("is_sold_out_flag")

    def reserve_seat(self) -> bool:
        """Deprecated: use app.events.inventory.decrement_capacity.

        Retained only for backward compatibility. Now delegates to the atomic
        inventory primitive so it is no longer a non-atomic read-modify-write.
        """
        import warnings
        warnings.warn(
            "TicketType.reserve_seat is deprecated; use events.inventory.decrement_capacity",
            DeprecationWarning,
            stacklevel=2,
        )
        if self.capacity == 0:
            return True  # unlimited
        from app.events.inventory import decrement_capacity

        try:
            decrement_capacity(self.id, 1, event_id=self.event_id)
            return True
        except Exception:
            return False

    def release_seat(self, count: int = 1):
        """Deprecated: use app.events.inventory.increment_capacity."""
        import warnings
        warnings.warn(
            "TicketType.release_seat is deprecated; use events.inventory.increment_capacity",
            DeprecationWarning,
            stacklevel=2,
        )
        if self.capacity == 0 or count < 1:
            return
        from app.events.inventory import increment_capacity

        increment_capacity(self.id, count)


# ============================================================================
# EVENT REGISTRATION MODEL
# ============================================================================

# DB-level sequence for race-condition-free ticket numbering (PostgreSQL only)
_reg_seq = Sequence("event_registration_seq", metadata=db.Model.metadata)


class EventRegistration(BaseModel):
    __tablename__ = "event_registrations"
    __table_args__ = (
        UniqueConstraint("registration_ref", name="uq_reg_ref"),
        UniqueConstraint("ticket_number", name="uq_ticket_number"),
        UniqueConstraint("qr_token", name="uq_qr_token"),
        UniqueConstraint("event_id", "user_id", name="uq_reg_event_user"),
        UniqueConstraint("event_id", "email", name="uq_reg_event_email"),
        Index("idx_reg_event_user", "event_id", "user_id"),
        Index("idx_reg_event_status", "event_id", "status"),
        Index("idx_reg_event_payment", "event_id", "payment_status"),
        Index("idx_reg_event_ticket", "event_id", "ticket_type_id"),
        Index("idx_reg_user_status", "user_id", "status"),
        Index("idx_reg_created_event", "created_at", "event_id"),
        Index("idx_reg_checkin", "checked_in_at", "event_id"),
        Index("idx_reg_ticket_status", "ticket_type_id", "status"),
        Index("idx_reg_payment_created", "payment_status", "created_at"),
        Index("idx_reg_qr_token", "qr_token"),
        Index("idx_reg_email", "email"),
        Index("idx_reg_phone", "phone"),
        Index("idx_reg_created", "created_at"),
        CheckConstraint("registration_fee >= 0", name="ck_reg_fee_non_negative"),
    )

    """
    Event Registration with full database-backed ID hierarchy:

    ID STRUCTURE (all database-backed):
    ──────────────────────────────────
    Event
      ├─ event.id (BigInteger PK)
      ├─ event.public_id (UUID string, unique)
      └─ event.slug (human-readable unique string)

    TicketType
      ├─ ticket_type.id (BigInteger PK) ← FK'd by registrations
      ├─ ticket_type.event_id (FK → events.id)
      ├─ ticket_type.name (e.g. "VIP", "General", "Free Entry")
      └─ ticket_type.price (Decimal - 0 for free tiers)

    EventRegistration (this table)
      ├─ registration.id (BigInteger PK)
      ├─ registration.seq_number (PostgreSQL SEQUENCE - globally unique)
      ├─ registration.registration_ref (human-readable e.g. "ER-AFCON2024-00001234")
      ├─ registration.ticket_number (e.g. "TKT-AFCON2024-00001234")
      ├─ registration.event_id (FK → events.id)
      ├─ registration.ticket_type_id (FK → event_ticket_types.id) ← ALWAYS SET
      ├─ registration.id_type (String - registration-specific ID type: passport/national_id/etc)
      └─ registration.id_number (String - registration-specific ID number)

    KEY DESIGN:
    ───────────
    1. ticket_type_id is NEVER NULL - every event has ≥1 TicketType
       - Free events: one "Free Entry" ticket type (price=0, capacity=0/unlimited)
       - Paid events: one or more paid ticket tiers

    2. All IDs are database-backed for referential integrity

    3. id_type in registration is a STRING (not a foreign key):
       - Stores values like "passport", "national_id", "driver_license"
       - Allows flexibility for future ID types without schema migration
       - Registration can collect ID info independently of event ID requirements
    """

    PAYMENT_FREE = "free"
    PAYMENT_PENDING = "pending"
    PAYMENT_PAID = "paid"
    PAYMENT_FAILED = "failed"
    PAYMENT_REFUNDED = "refunded"
    PAYMENT_EXPIRED = "expired"

    STATUS_PENDING_PAYMENT = "pending_payment"
    STATUS_CONFIRMED = "confirmed"
    STATUS_CANCELLED = "cancelled"
    STATUS_CHECKED_IN = "checked_in"
    STATUS_NO_SHOW = "no_show"
    STATUS_EXPIRED = "expired"

    # ── Columns ────────────────────────────────────────────────────────────
    seq_number = Column(BigInteger, _reg_seq, server_default=_reg_seq.next_value())

    registration_ref = Column(String(60), unique=True, nullable=False, index=True)
    event_id = Column(BigInteger, ForeignKey("events.id", ondelete="RESTRICT"),
                      nullable=False, index=True)
    ticket_type_id = Column(BigInteger, ForeignKey("event_ticket_types.id", ondelete="RESTRICT"),
                            nullable=False)
    user_id = Column(BigInteger, ForeignKey("users.id", ondelete="SET NULL"),
                     nullable=True, index=True)
    guest_id = Column(BigInteger, ForeignKey("event_guests.id", ondelete="SET NULL"),
                      nullable=True, index=True)
    full_name = Column(String(255), nullable=False)
    email = Column(String(255), nullable=False)
    phone = Column(String(50))
    nationality = Column(String(64))
    id_number = Column(String(100))
    id_type = Column(String(30))
    ticket_type = Column(String(50), default="general", nullable=False)
    ticket_number = Column(String(50), unique=True, nullable=False)
    qr_token = Column(String(200), unique=True, nullable=False, index=True)
    registration_fee = Column(Numeric(10, 2), default=0)
    payment_status = Column(String(30), default="free")
    wallet_txn_id = Column(String(255), nullable=True)
    status = Column(String(30), default="confirmed", nullable=False, index=True)
    checked_in_at = Column(DateTime(timezone=True), nullable=True)
    checked_in_by_id = Column(BigInteger, ForeignKey("users.id"), nullable=True)
    discount_code_applied = Column(String(50), nullable=True)
    discount_amount = Column(Numeric(10, 2), default=0, nullable=False)
    registered_by = Column(String(30), default="self")
    notes = Column(Text, nullable=True)

    booked_by_user_id = Column(BigInteger, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    booking_type = Column(String(30), default=BookingType.SELF.value, nullable=False, index=True)
    group_booking_id = Column(String(100), nullable=True, index=True)
    group_label = Column(String(150), nullable=True, index=True)
    attendee_user_id = Column(BigInteger, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    """
    REDUNDANT FIELD: Currently always equals user_id for third_party/group bookings,
    NULL for self bookings. Reserved for future "transfer ticket" feature where
    a registration can be reassigned to a different attendee without changing
    the original user_id (which remains for audit trail).

    Do not use this field for current business logic - use user_id and booking_type.
    """
    group_index = Column(Integer, nullable=True)

    # ── Relationships ──────────────────────────────────────────────────────
    event = relationship("Event", back_populates="registrations")
    ticket_type_rel = relationship("TicketType", back_populates="registrations")
    user = relationship("User", foreign_keys=[user_id])
    guest = relationship("EventGuest", foreign_keys=[guest_id])
    checked_in_by = relationship("User", foreign_keys=[checked_in_by_id])
    booked_by = relationship("User", foreign_keys=[booked_by_user_id], backref="booked_registrations")
    attendee_user = relationship("User", foreign_keys=[attendee_user_id], backref="attending_registrations")

    # ── Ref generation ─────────────────────────────────────────────────────

    def generate_refs(self, event_slug: str = None, sequence: int = None):
        """
        Generate registration_ref, ticket_number, and QR token.

        Prefers self.seq_number (PostgreSQL SEQUENCE, populated after flush).
        Falls back to the manually passed sequence argument for callers that
        compute it before flushing - safe inside a REPEATABLE READ transaction.
        """
        seq = self.seq_number if self.seq_number is not None else sequence
        if seq is None:
            raise RuntimeError(
                "generate_refs requires either a flushed seq_number or "
                "an explicit sequence argument."
            )

        slug = event_slug
        if not slug and self.event:
            slug = self.event.slug
        slug = (slug or "EVENT").upper().replace("-", "_")[:20]

        self.registration_ref = f"ER-{slug}-{seq:08d}"
        self.ticket_number = f"TKT-{slug}-{seq:08d}"

        payload = f"AFCON360:{self.registration_ref}:{seq}"
        key = os.environ.get("QR_SECRET_KEY", "dev-secret-change-in-production").encode()
        signature = hmac.new(key, payload.encode(), digestmod=hashlib.sha256).hexdigest()[:24]
        self.qr_token = f"{payload}:{signature}"

    # ── Status flags ───────────────────────────────────────────────────────

    @property
    def is_checked_in_flag(self) -> bool:
        return self.status == self.STATUS_CHECKED_IN

    @property
    def is_confirmed_flag(self) -> bool:
        return self.status == self.STATUS_CONFIRMED

    @property
    def is_cancelled_flag(self) -> bool:
        return self.status == self.STATUS_CANCELLED

    is_checked_in = _deprecated("is_checked_in_flag")

    @property
    def registered_by_display(self) -> str:
        """Deprecated - use booking_type instead. Maintained for backward compatibility."""
        import warnings
        warnings.warn(
            "registered_by is deprecated, use booking_type",
            DeprecationWarning,
            stacklevel=2
        )
        return self.booking_type

    def __repr__(self):
        return f"<EventRegistration {self.registration_ref}: {self.full_name!r}>"


# ============================================================================
# WAITLIST MODEL
# ============================================================================

class Waitlist(BaseModel):
    __tablename__ = "event_waitlist"
    __table_args__ = (
        UniqueConstraint("event_id", "user_id", name="uq_waitlist_event_user"),
        Index("idx_waitlist_event_status", "event_id", "status"),
        Index("idx_waitlist_created", "created_at"),
        Index("idx_waitlist_position", "event_id", "position"),
        Index("idx_waitlist_notification", "notification_sent", "created_at"),
    )

    event_id = Column(BigInteger, ForeignKey("events.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    ticket_type_id = Column(BigInteger, ForeignKey("event_ticket_types.id", ondelete="CASCADE"), nullable=True)
    position = Column(Integer, nullable=False, default=1)
    status = Column(String(30), default="pending", nullable=False, index=True)
    email = Column(String(255), nullable=False)
    phone = Column(String(50), nullable=True)
    notes = Column(Text, nullable=True)
    notified_at = Column(DateTime(timezone=True), nullable=True)
    converted_at = Column(DateTime(timezone=True), nullable=True)
    notification_sent = Column(Boolean, default=False, nullable=False)
    conversion_attempts = Column(Integer, default=0, nullable=False)

    event = relationship("Event", backref="waitlist_entries")
    user = relationship("User", foreign_keys=[user_id])
    ticket_type = relationship("TicketType", foreign_keys=[ticket_type_id])

    def mark_notified(self):
        self.notified_at = datetime.now(timezone.utc)
        self.notification_sent = True

    def mark_converted(self):
        self.converted_at = datetime.now(timezone.utc)
        self.status = "converted"

    def __repr__(self):
        return f"<Waitlist event={self.event_id} user={self.user_id} pos={self.position}>"


# ============================================================================
# EVENT ROLE MODEL
# ============================================================================

class EventRole(BaseModel):
    __tablename__ = "event_roles"
    __table_args__ = (
        UniqueConstraint("event_id", "user_id", "role", name="uq_event_user_role"),
        Index("idx_event_roles_event", "event_id"),
        Index("idx_event_roles_user", "user_id"),
        Index("idx_event_roles_role", "role"),
    )

    event_id = Column(BigInteger, ForeignKey("events.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    role = Column(String(50), nullable=False)
    title = Column(String(120), nullable=True)
    organisation_id = Column(BigInteger, ForeignKey("organisations.id", ondelete="SET NULL"), nullable=True, index=True)
    permissions = Column(JSON, default=list)
    assigned_by_id = Column(BigInteger, ForeignKey("users.id"), nullable=True)
    assigned_at = Column(DateTime(timezone=True), default=func.now())
    is_active = Column(Boolean, default=True)

    event = relationship("Event", backref="staff_roles")
    user = relationship("User", foreign_keys=[user_id])
    organisation = relationship("Organisation", foreign_keys=[organisation_id])
    assigned_by = relationship("User", foreign_keys=[assigned_by_id])

    def __repr__(self):
        return f"<EventRole event={self.event_id} user={self.user_id} role={self.role!r}>"


# ============================================================================
# DISCOUNT CODE MODEL
# ============================================================================

class DiscountCode(BaseModel):
    __tablename__ = "discount_codes"
    __table_args__ = (
        Index("idx_discount_code_event", "event_id"),
        Index("idx_discount_code_active", "is_active", "valid_until"),
        UniqueConstraint("code", name="uq_discount_code"),
    )

    event_id = Column(BigInteger, ForeignKey("events.id", ondelete="CASCADE"), nullable=False, index=True)
    code = Column(String(50), nullable=False, unique=True, index=True)
    discount_type = Column(String(20), nullable=False)
    discount_value = Column(Numeric(10, 2), nullable=False)
    currency = Column(String(3), default="USD")
    valid_from = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    valid_until = Column(DateTime(timezone=True), nullable=True)
    usage_limit = Column(Integer, nullable=True)
    used_count = Column(Integer, default=0, nullable=False)
    minimum_order = Column(Numeric(10, 2), default=0)
    is_active = Column(Boolean, default=True, nullable=False)
    created_by = Column(BigInteger, ForeignKey("users.id"), nullable=True)

    event = relationship("Event", backref="discount_codes")
    creator = relationship("User", foreign_keys=[created_by])

    def is_valid(self) -> bool:
        now = datetime.now(timezone.utc)
        return (
                self.is_active
                and now >= self.valid_from
                and (self.valid_until is None or now <= self.valid_until)
                and (self.usage_limit is None or self.used_count < self.usage_limit)
        )

    def calculate_discount(self, amount: float) -> float:
        if self.discount_type == DiscountType.PERCENTAGE:
            return float(amount) * (float(self.discount_value) / 100)
        return min(float(self.discount_value), float(amount))


# ============================================================================
# EVENT TRANSFER REQUEST MODEL
# ============================================================================

class EventTransferRequest(BaseModel):
    __tablename__ = "event_transfer_requests"
    __table_args__ = (
        Index("idx_transfer_event_status", "event_id", "status"),
        Index("idx_transfer_from_user", "from_user_id"),
        Index("idx_transfer_to_org", "to_organization_id"),
    )

    event_id = Column(BigInteger, ForeignKey("events.id", ondelete="CASCADE"), nullable=False)
    from_user_id = Column(BigInteger, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    from_organization_id = Column(BigInteger, ForeignKey("organisations.id", ondelete="SET NULL"), nullable=True)
    to_user_id = Column(BigInteger, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    to_organization_id = Column(BigInteger, ForeignKey("organisations.id", ondelete="SET NULL"), nullable=True)
    requested_by_id = Column(BigInteger, ForeignKey("users.id"), nullable=False)
    status = Column(
        String(20),
        nullable=False,
        default=TransferStatus.PENDING.value,
    )
    reason = Column(Text, nullable=True)
    approved_by_id = Column(BigInteger, ForeignKey("users.id"), nullable=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)

    event = relationship("Event", foreign_keys=[event_id])
    from_user = relationship("User", foreign_keys=[from_user_id])
    from_organization = relationship("Organisation", foreign_keys=[from_organization_id])
    to_user = relationship("User", foreign_keys=[to_user_id])
    to_organization = relationship("Organisation", foreign_keys=[to_organization_id])
    requested_by = relationship("User", foreign_keys=[requested_by_id])
    approved_by = relationship("User", foreign_keys=[approved_by_id])

    def approve(self, approver_id: int):
        self.status = TransferStatus.APPROVED.value
        self.approved_by_id = approver_id
        self.approved_at = datetime.now(timezone.utc)

    def __repr__(self):
        return f"<EventTransferRequest {self.id}: event {self.event_id} [{self.status}]>"


# ============================================================================
# EVENT MODERATION LOG  (append-only - never delete rows from this table)
# ============================================================================

class EventModerationLog(BaseModel):
    __tablename__ = "event_moderation_logs"
    __table_args__ = (
        Index("idx_moderation_event", "event_id"),
        Index("idx_moderation_user", "user_id"),
        Index("idx_moderation_action", "action"),
        Index("idx_moderation_date", "created_at"),
    )

    event_id = Column(BigInteger, ForeignKey("events.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(BigInteger, ForeignKey("users.id"), nullable=False)
    action = Column(String(50), nullable=False)
    from_status = Column(String(30), nullable=False)
    to_status = Column(String(30), nullable=False)
    reason = Column(Text, nullable=True)
    ip_address = Column(String(64), nullable=True)
    user_agent = Column(String(512), nullable=True)
    extra_data = Column(JSON, default=dict)

    event = relationship("Event", foreign_keys=[event_id])
    user = relationship("User", foreign_keys=[user_id])

    def __repr__(self):
        return (
            f"<EventModerationLog {self.id}: "
            f"event {self.event_id} {self.action} by user {self.user_id}>"
        )


# ============================================================================
# EVENT TRANSFER LOG  (append-only ownership audit trail)
# ============================================================================

class EventTransferLog(BaseModel):
    __tablename__ = "event_transfer_logs"

    event_id = Column(BigInteger, ForeignKey("events.id", ondelete="CASCADE"), nullable=False)
    from_owner_type = Column(String(20), nullable=False)
    from_owner_id = Column(BigInteger, nullable=False)
    to_owner_type = Column(String(20), nullable=False)
    to_owner_id = Column(BigInteger, nullable=False)
    transferred_by_id = Column(BigInteger, ForeignKey("users.id"), nullable=False)
    transferred_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    extra_data = Column(JSON, default=dict)

    event = relationship("Event", foreign_keys=[event_id])
    transferred_by = relationship("User", foreign_keys=[transferred_by_id])

    def __repr__(self):
        return (
            f"<EventTransferLog {self.id}: event {self.event_id} "
            f"{_owner_type_value(self.from_owner_type)}:{self.from_owner_id} → "
            f"{_owner_type_value(self.to_owner_type)}:{self.to_owner_id}>"
        )


# ============================================================================
# EVENT HOST REGISTRATION MODEL
# ============================================================================

class EventHostRegistration(BaseModel):
    """Tracks community host registration for specific events"""
    __tablename__ = "event_host_registrations"

    event_id = Column(BigInteger, ForeignKey("events.id", ondelete="CASCADE"), nullable=False)
    property_id = Column(BigInteger, ForeignKey("accommodation_properties.id", ondelete="CASCADE"), nullable=False)
    host_user_id = Column(BigInteger, ForeignKey("users.id", use_alter=True, name="fk_event_host_reg_user"), nullable=False)

    status = Column(String(30), default="pending", nullable=False)

    price_per_night = Column(Numeric(10, 2), nullable=True)
    currency = Column(String(3), default="USD")
    is_free = Column(Boolean, default=False)

    max_guests = Column(Integer, nullable=True)
    special_instructions = Column(Text, nullable=True)

    registered_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    approved_at = Column(DateTime(timezone=True), nullable=True)
    approved_by_id = Column(BigInteger, ForeignKey("users.id"), nullable=True)
    rejected_at = Column(DateTime(timezone=True), nullable=True)
    rejection_reason = Column(Text, nullable=True)

    event = relationship("Event", foreign_keys=[event_id], backref="host_registrations")
    property = relationship("Property", foreign_keys=[property_id], back_populates="event_host_registrations")
    host_user = relationship("User", foreign_keys=[host_user_id])
    approved_by = relationship("User", foreign_keys=[approved_by_id])

    __table_args__ = (
        UniqueConstraint("event_id", "property_id", name="uq_event_property_host"),
        Index("idx_host_registration_event", "event_id", "status"),
        Index("idx_host_registration_host", "host_user_id"),
        Index("idx_host_registration_status", "status"),
    )


# ============================================================================
# EVENT ASSIGNMENT MODEL
# ============================================================================

class EventGuest(BaseModel):
    """Stable event guest identity independent of an AFCON360 account."""

    __tablename__ = "event_guests"
    __table_args__ = (
        UniqueConstraint("guest_ref", name="uq_event_guest_ref"),
        Index("idx_event_guest_email", "email"),
        Index("idx_event_guest_user", "user_id"),
    )

    guest_ref = Column(String(80), unique=True, nullable=False, index=True,
                       default=lambda: f"EG-{uuid.uuid4().hex}")
    user_id = Column(BigInteger, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    full_name = Column(String(255), nullable=False)
    email = Column(String(255), nullable=False)
    phone = Column(String(50), nullable=True)
    nationality = Column(String(64), nullable=True)
    qr_token = Column(String(200), nullable=True)
    notification_eligible = Column(Boolean, nullable=False, default=True)

    user = relationship("User", foreign_keys=[user_id])

    def __repr__(self):
        return f"<EventGuest {self.guest_ref}>"

class EventAssignment(BaseModel):
    __tablename__ = "event_assignments"
    __table_args__ = (
        UniqueConstraint("event_id", "guest_id", name="uq_event_assignment_guest"),
        Index("idx_assignment_event_attendee", "event_id", "attendee_id"),
        Index("idx_assignment_accommodation", "accommodation_booking_id"),
        Index("idx_assignment_transport", "transport_booking_id"),
        Index("idx_assignment_meal", "meal_booking_id"),
        Index("idx_assignment_managed_by", "managed_by"),
        Index("idx_assignment_created", "created_at"),
        Index("idx_assignment_registration", "registration_id"),
        Index("idx_assignment_community_host", "community_host_id"),
    )

    event_id = Column(BigInteger, ForeignKey("events.id", ondelete="CASCADE"), nullable=False)
    guest_id = Column(BigInteger, ForeignKey("event_guests.id", ondelete="CASCADE"), nullable=True)
    attendee_id = Column(
        BigInteger,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    accommodation_booking_id = Column(BigInteger, nullable=True, info={"id_kind": IDKind.CROSS_MODULE_REF})
    transport_booking_id = Column(BigInteger, nullable=True, info={"id_kind": IDKind.CROSS_MODULE_REF})
    meal_booking_id = Column(BigInteger, nullable=True, info={"id_kind": IDKind.CROSS_MODULE_REF})
    community_host_id = Column(BigInteger, nullable=True, info={"id_kind": IDKind.CROSS_MODULE_REF})
    managed_by = Column(BigInteger, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    notes = Column(Text, nullable=True)
    schedule_json = Column(JSON, default=dict)
    acc_link_token_hash = Column(String(64), nullable=True, unique=True, index=True)
    acc_link_expires_at = Column(DateTime(timezone=True), nullable=True)
    registration_id = Column(BigInteger, ForeignKey("event_registrations.id", ondelete="SET NULL"), nullable=True)
    status = Column(String(30), default="active", nullable=False)
    assigned_by_id = Column(BigInteger, ForeignKey("users.id"), nullable=True)
    assigned_at = Column(DateTime(timezone=True), default=func.now())

    event = relationship("Event", foreign_keys=[event_id], backref="assignments")
    attendee = relationship("User", foreign_keys=[attendee_id])
    guest = relationship("EventGuest", foreign_keys=[guest_id])
    manager = relationship("User", foreign_keys=[managed_by])
    registration = relationship("EventRegistration", foreign_keys=[registration_id])
    assigned_by = relationship("User", foreign_keys=[assigned_by_id])

    def __repr__(self):
        return f"<EventAssignment {self.id}: event {self.event_id}, attendee {self.attendee_id}>"


# ============================================================================
# EVENT GROUP / DELEGATION MODEL
# ============================================================================

class EventGroup(BaseModel):
    """A delegation or group of guests scoped to a single event.

    Groups let organisers coordinate a subset of attendees (e.g. a national
    delegation or a VIP party) without granting those attendees any organiser
    authority.  Membership is recorded in EventGroupMember.
    """

    __tablename__ = "event_groups"
    __table_args__ = (
        UniqueConstraint("event_id", "name", name="uq_event_group_name"),
        Index("idx_event_group_event", "event_id"),
    )

    public_id = Column(String(64), unique=True, nullable=False,
                       default=lambda: str(uuid.uuid4()), index=True)
    event_id = Column(BigInteger, ForeignKey("events.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(150), nullable=False)
    description = Column(Text, nullable=True)
    group_type = Column(String(30), default="delegation", nullable=False)
    created_by_id = Column(BigInteger, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    event = relationship("Event", foreign_keys=[event_id], backref="groups")
    created_by = relationship("User", foreign_keys=[created_by_id])

    def __repr__(self):
        return f"<EventGroup {self.public_id}: {self.name}>"


class EventGroupMember(BaseModel):
    """A guest/attendee that belongs to an EventGroup."""

    __tablename__ = "event_group_members"
    __table_args__ = (
        UniqueConstraint("group_id", "registration_id", name="uq_group_registration"),
        Index("idx_group_member_group", "group_id"),
        Index("idx_group_member_registration", "registration_id"),
        Index("idx_group_member_guest", "guest_id"),
    )

    group_id = Column(BigInteger, ForeignKey("event_groups.id", ondelete="CASCADE"), nullable=False)
    registration_id = Column(BigInteger, ForeignKey("event_registrations.id", ondelete="CASCADE"), nullable=True)
    guest_id = Column(BigInteger, ForeignKey("event_guests.id", ondelete="SET NULL"), nullable=True)
    is_vip = Column(Boolean, default=False, nullable=False)
    added_by_id = Column(BigInteger, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    group = relationship("EventGroup", foreign_keys=[group_id], backref="members")
    registration = relationship("EventRegistration", foreign_keys=[registration_id])
    guest = relationship("EventGuest", foreign_keys=[guest_id])
    added_by = relationship("User", foreign_keys=[added_by_id])

    def __repr__(self):
        return f"<EventGroupMember {self.id}: group {self.group_id}>"


# ============================================================================
# ORGANIZER MESSAGE MODEL
# ============================================================================

class OrganizerMessage(BaseModel):
    """
    Messages sent from users to event organizers.
    Stored for audit trail and read/unread tracking in organizer dashboard.
    """
    __tablename__ = 'organizer_messages'
    __table_args__ = (
        Index('idx_organizer_message_event', 'event_id'),
        Index('idx_organizer_message_user', 'user_id'),
        Index('idx_organizer_message_status', 'status'),
    )

    public_id = Column(String(64), unique=True, nullable=False,
                       default=lambda: str(uuid.uuid4()), index=True)

    event_id = Column(BigInteger, ForeignKey('events.id'), nullable=False)
    user_id = Column(BigInteger, ForeignKey('users.id'), nullable=False)
    message = Column(Text, nullable=False)
    status = Column(String(20), default='unread', nullable=False)

    event = relationship('Event', backref='organizer_messages')
    user = relationship('User', backref='sent_organizer_messages')

    def __repr__(self):
        return f'<OrganizerMessage {self.id}: event {self.event_id}, user {self.user_id}>'


# ============================================================================
# ORGANIZER PROFILE
# ============================================================================

class OrganizerProfile(BaseModel):
    """
    Lightweight profile created when an attendee is approved to "Become an
    Organizer".

    Design notes
    ------------
    * This is intentionally separate from event ownership (Event.current_owner_*)
      and EventRole. It records that a user has been granted organizer
      capability and snapshots the eligibility evidence at approval time.
    * Attendee data is NEVER moved or copied: the user keeps the same account,
      so all existing registrations/attendance remain intact (continuity).
    * Status uses a String (no PostgreSQL ENUM, per project policy).
    """
    __tablename__ = 'organizer_profiles'
    __table_args__ = (
        UniqueConstraint('user_id', 'public_id', name='uq_organizer_profile_user_pub'),
        Index('idx_organizer_profile_user', 'user_id'),
    )

    public_id = Column(
        String(64), unique=True, nullable=False,
        default=lambda: str(uuid.uuid4()), index=True,
    )

    user_id = Column(
        BigInteger, ForeignKey('users.id', ondelete='CASCADE'),
        nullable=False,
    )

    # ── Eligibility snapshot (captured at approval) ──────────────────────────
    account_verified = Column(Boolean, default=False, nullable=False)
    kyc_tier = Column(Integer, nullable=True)
    attended_events_count = Column(Integer, default=0, nullable=False)
    total_registrations = Column(Integer, default=0, nullable=False)

    # ── Lifecycle ────────────────────────────────────────────────────────────
    # approved | pending_review | rejected | suspended
    status = Column(String(30), default='approved', nullable=False, index=True)
    eligibility_passed = Column(Boolean, default=True, nullable=False)

    # ── Onboarding / continuity ──────────────────────────────────────────────
    onboarding_completed = Column(Boolean, default=False, nullable=False)
    organization_name = Column(String(255), nullable=True)
    bio = Column(Text, nullable=True)

    approved_at = Column(DateTime(timezone=True), nullable=True)
    revoked_at = Column(DateTime(timezone=True), nullable=True)

    user = relationship(
        'User', foreign_keys=[user_id], backref='organizer_profile',
    )

    def __repr__(self):
        return f'<OrganizerProfile {self.public_id}: user {self.user_id} ({self.status})>'