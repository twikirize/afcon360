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
from datetime import datetime

from sqlalchemy import (
    Column, BigInteger, Integer, String, Boolean, DateTime, Date,
    ForeignKey, Text, Numeric, JSON, Index, UniqueConstraint, CheckConstraint,
    Sequence,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from sqlalchemy import Enum as SAEnum

from app.extensions import db
from app.models.base import BaseModel
from app.events.constants import (
    EventStatus,
    ALLOWED_TRANSITIONS,
    validate_transition,
)


# ============================================================================
# HELPERS
# ============================================================================

def _sa_enum(enum_cls, name: str):
    """Reduce SAEnum column-definition boilerplate."""
    return SAEnum(
        enum_cls,
        values_callable=lambda cls: [e.value for e in cls],
        name=name,
        create_constraint=True,
    )


def _deprecated(new_name: str):
    """
    Descriptor that delegates to `new_name` and emits DeprecationWarning.
    Usage (class body):
        is_active = _deprecated("is_active_flag")
    """
    @property
    def prop(self):
        warnings.warn(
            f"'{new_name.replace('_flag', '')}' is deprecated — use '{new_name}'.",
            DeprecationWarning,
            stacklevel=2,
        )
        return getattr(self, new_name)
    return prop


# ============================================================================
# ENUM CLASSES
# ============================================================================

class CreatorType(str, enum.Enum):
    """
    Who *created* the event record.  This is immutable after creation.

    INDIVIDUAL   – a human user pressed the button
    ORGANIZATION – an organisation's automated workflow created it
    SYSTEM       – the platform itself created it (e.g. anniversary events,
                   auto-generated fixtures).  current_owner_id = 0 in this case.
    """
    INDIVIDUAL   = "individual"
    ORGANIZATION = "organization"
    SYSTEM       = "system"


class OwnerType(str, enum.Enum):
    """
    Who *currently controls* the event.  Can change via EventTransferRequest.

    Example: a manager (INDIVIDUAL creator) creates an event on behalf of a
    client (INDIVIDUAL owner) — creator ≠ owner from day one.
    """
    INDIVIDUAL   = "individual"
    ORGANIZATION = "organization"
    SYSTEM       = "system"       # platform-owned event; owner_id = 0


class TransferStatus(str, enum.Enum):
    PENDING   = "pending"
    APPROVED  = "approved"
    REJECTED  = "rejected"
    CANCELLED = "cancelled"


class DiscountType(str, enum.Enum):
    PERCENTAGE = "percentage"
    FIXED      = "fixed"


# Sentinel value used when the system itself is the owner/creator (no real user).
SYSTEM_OWNER_ID: int = 0


# ============================================================================
# EVENT MODEL
# ============================================================================

class Event(BaseModel):
    __tablename__ = "events"
    __table_args__ = (
        # ── Performance indexes ────────────────────────────────────────────
        Index("idx_event_start_date",       "start_date"),
        Index("idx_event_status_featured",  "status", "featured"),
        Index("idx_event_is_deleted",       "is_deleted"),
        Index("idx_event_slug_unique",      "slug", "is_deleted", unique=True),
        Index("idx_event_category",         "category"),
        Index("idx_event_organizer_status", "organizer_id", "status"),
        Index("idx_event_status_start",     "status", "start_date"),
        Index("idx_event_creator",          "created_by_type", "created_by_id"),
        Index("idx_event_organization",     "organization_id"),
        Index("idx_event_system",           "is_system_event"),
        Index("idx_event_current_owner",    "current_owner_type", "current_owner_id"),
        # ── Constraints ────────────────────────────────────────────────────
        UniqueConstraint("slug",            name="uq_event_slug"),
        CheckConstraint("end_date >= start_date",
                        name="ck_event_end_after_start"),
        CheckConstraint("max_capacity >= 0",
                        name="ck_event_max_capacity_non_negative"),
        CheckConstraint(
            # system events must use SYSTEM_OWNER_ID (0)
            "NOT (current_owner_type = 'system' AND current_owner_id != 0)",
            name="ck_system_owner_id_zero",
        ),
    )

    # ── Identifiers ────────────────────────────────────────────────────────
    public_id  = Column(String(64),  unique=True, nullable=False,
                        default=lambda: str(uuid.uuid4()), index=True)
    event_ref  = Column(String(50),  unique=True)
    slug       = Column(String(120), nullable=False)

    # ── Core fields ────────────────────────────────────────────────────────
    name                  = Column(String(255), nullable=False)
    description           = Column(Text)
    category              = Column(String(50),  nullable=False, default="general")
    city                  = Column(String(100), nullable=False)
    country               = Column(String(100), default="Uganda")
    venue                 = Column(String(255))
    start_date            = Column(Date)
    end_date              = Column(Date)
    max_capacity          = Column(Integer,      default=0, nullable=False)
    registration_required = Column(Boolean,      default=False)
    registration_fee      = Column(Numeric(10, 2), default=0, nullable=False)
    currency              = Column(String(3),    default="USD")
    featured              = Column(Boolean,      default=False)
    website               = Column(String(500))
    contact_email         = Column(String(255))
    contact_phone         = Column(String(50))
    event_metadata        = Column(JSON,         default=dict)

    # ── Status ─────────────────────────────────────────────────────────────
    status = Column(
        _sa_enum(EventStatus, "eventstatus"),
        default=EventStatus.PENDING_APPROVAL,
        nullable=False,
    )

    # ── Organiser (the public-facing contact, may differ from creator/owner) ─
    organizer_id = Column(BigInteger, ForeignKey("users.id"), nullable=False)

    # ── Approval / rejection audit ─────────────────────────────────────────
    approved_at      = Column(DateTime, nullable=True)
    approved_by_id   = Column(BigInteger, ForeignKey("users.id"), nullable=True)
    rejected_at      = Column(DateTime, nullable=True)
    rejection_reason = Column(Text, nullable=True)

    # ── Moderation enforcement ─────────────────────────────────────────────
    suspension_reason   = Column(Text,       nullable=True)
    suspension_duration = Column(String(20), nullable=True)
    suspended_at        = Column(DateTime,   nullable=True)
    suspended_by_id     = Column(BigInteger, ForeignKey("users.id"), nullable=True)

    deactivation_reason = Column(Text,       nullable=True)
    deactivated_at      = Column(DateTime,   nullable=True)
    deactivated_by_id   = Column(BigInteger, ForeignKey("users.id"), nullable=True)

    takedown_reason   = Column(Text,       nullable=True)
    takedown_category = Column(String(50), nullable=True)
    taken_down_at     = Column(DateTime,   nullable=True)
    taken_down_by_id  = Column(BigInteger, ForeignKey("users.id"), nullable=True)

    # ── Completion (auto-set by scheduler) ────────────────────────────────
    completed_at = Column(DateTime, nullable=True)

    # ── Soft delete ────────────────────────────────────────────────────────
    # is_deleted=True + status=ARCHIVED  → organiser soft-deleted
    # is_deleted=True + status=DELETED   → admin removed
    is_deleted    = Column(Boolean,   default=False, nullable=False, index=True)
    deleted_at    = Column(DateTime,  nullable=True)
    deleted_by_id = Column(BigInteger, ForeignKey("users.id"), nullable=True)
    deletion_reason = Column(Text,    nullable=True)

    # ── Optimistic locking ─────────────────────────────────────────────────
    version = Column(Integer, default=0, nullable=False)

    # ── Submission preferences (set by organiser at submit time) ──────────
    # auto_publish_on_approval:
    #   True  → system publishes the event automatically once it is APPROVED
    #   False → organiser is notified and publishes manually
    auto_publish_on_approval = Column(Boolean, default=False, nullable=False)

    # publish_permission:
    #   'self'   → only the organiser may publish
    #   'admin'  → only an admin may publish
    #   'either' → either party may publish (default)
    publish_permission = Column(String(20), default='either', nullable=False)

    # risk_flags: list of strings populated at submission time.
    # Examples: ["new_account", "unverified_phone", "duplicate_venue"]
    # Used by admins during moderation review. Never shown to organisers.
    risk_flags = Column(JSON, default=list, nullable=False)

    # ── Standard audit trail ───────────────────────────────────────────────
    created_by_id = Column(BigInteger, ForeignKey("users.id"), nullable=True)
    updated_by_id = Column(BigInteger, ForeignKey("users.id"), nullable=True)

    # ── Creator (immutable after creation) ────────────────────────────────
    # Who pressed the "create" button.  Never changes.
    created_by_type = Column(
        _sa_enum(CreatorType, "creatortype"),
        nullable=False,
        default=CreatorType.INDIVIDUAL,
    )
    # For INDIVIDUAL → user id; for ORGANIZATION → org id; for SYSTEM → 0
    created_by_entity_id = Column(BigInteger, nullable=False, default=0)

    # ── Owner (mutable via EventTransferRequest) ───────────────────────────
    # Who currently controls the event.  Can differ from creator.
    current_owner_type = Column(
        _sa_enum(OwnerType, "ownertype"),
        nullable=False,
        default=OwnerType.INDIVIDUAL,
    )
    # For INDIVIDUAL → user id; for ORGANIZATION → org id; for SYSTEM → 0
    current_owner_id = Column(BigInteger, nullable=False, index=True)

    # ── Organisation context ───────────────────────────────────────────────
    organization_id = Column(
        BigInteger,
        ForeignKey("organisations.id", ondelete="SET NULL"),
        nullable=True, index=True,
    )
    is_system_event     = Column(Boolean,    default=False, nullable=False, index=True)
    original_creator_id = Column(
        BigInteger,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # ── Relationships ──────────────────────────────────────────────────────
    organizer      = relationship("User", foreign_keys=[organizer_id])
    approved_by    = relationship("User", foreign_keys=[approved_by_id])
    deleted_by     = relationship("User", foreign_keys=[deleted_by_id])
    created_by     = relationship("User", foreign_keys=[created_by_id])
    updated_by     = relationship("User", foreign_keys=[updated_by_id])
    suspended_by   = relationship("User", foreign_keys=[suspended_by_id])
    deactivated_by = relationship("User", foreign_keys=[deactivated_by_id])
    taken_down_by  = relationship("User", foreign_keys=[taken_down_by_id])
    registrations  = relationship("EventRegistration", back_populates="event",
                                  cascade="all, delete-orphan")
    ticket_types   = relationship("TicketType", back_populates="event",
                                  cascade="all, delete-orphan")

    # ── Constructor ────────────────────────────────────────────────────────

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._ensure_public_id()
        self._set_default_owner()

    def __repr__(self):
        return f"<Event {self.id}: {self.name!r} [{self.status.value}]>"

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
            self.current_owner_type = OwnerType.SYSTEM
            self.current_owner_id   = SYSTEM_OWNER_ID
            if self.created_by_type != CreatorType.SYSTEM:
                # An admin created a system event — creator stays INDIVIDUAL
                pass
            return

        if not self.current_owner_id and self.organizer_id:
            self.current_owner_type = OwnerType.INDIVIDUAL
            self.current_owner_id   = self.organizer_id

        if not self.created_by_entity_id and self.organizer_id:
            self.created_by_entity_id = self.organizer_id

    def generate_ref(self):
        self.event_ref = f"EVT-{self.slug.upper()[:20]}"

    # ── Status flag properties ─────────────────────────────────────────────

    @property
    def is_published_flag(self) -> bool:
        return self.status == EventStatus.PUBLISHED

    # Keep "is_active_flag" as alias for is_published_flag for back-compat
    @property
    def is_active_flag(self) -> bool:
        return self.is_published_flag

    @property
    def is_pending_flag(self) -> bool:
        return self.status == EventStatus.PENDING_APPROVAL

    @property
    def is_rejected_flag(self) -> bool:
        return self.status == EventStatus.REJECTED

    @property
    def is_draft_flag(self) -> bool:
        return self.status == EventStatus.DRAFT

    @property
    def is_cancelled_flag(self) -> bool:
        return self.status == EventStatus.CANCELLED

    @property
    def is_archived_flag(self) -> bool:
        return self.status == EventStatus.ARCHIVED

    @property
    def is_suspended_flag(self) -> bool:
        return self.status == EventStatus.SUSPENDED

    @property
    def is_paused_flag(self) -> bool:
        return self.status == EventStatus.PAUSED

    @property
    def is_approved_flag(self) -> bool:
        return self.status == EventStatus.APPROVED

    @property
    def is_completed_flag(self) -> bool:
        return self.status == EventStatus.COMPLETED

    @property
    def is_deleted_status(self) -> bool:
        return self.status == EventStatus.DELETED

    @property
    def is_terminal(self) -> bool:
        from app.events.constants import TERMINAL_STATUSES
        return self.status in TERMINAL_STATUSES

    @property
    def accepts_registrations(self) -> bool:
        from app.events.constants import REGISTRATION_OPEN_STATUSES
        return self.status in REGISTRATION_OPEN_STATUSES

    # ── Deprecated back-compat aliases ────────────────────────────────────
    is_active    = _deprecated("is_active_flag")
    is_pending   = _deprecated("is_pending_flag")
    is_rejected  = _deprecated("is_rejected_flag")
    is_draft     = _deprecated("is_draft_flag")
    is_cancelled = _deprecated("is_cancelled_flag")
    is_archived  = _deprecated("is_archived_flag")
    is_suspended = _deprecated("is_suspended_flag")
    is_paused    = _deprecated("is_paused_flag")
    is_approved  = _deprecated("is_approved_flag")

    # ── State-machine transition helpers ──────────────────────────────────

    def transition_to(self, new_status: EventStatus, actor_id: int,
                      reason: str = None,
                      ip_address: str = None,
                      user_agent: str = None) -> "EventModerationLog":
        """
        Validate and apply a status transition, returning an unsaved
        EventModerationLog entry.  The caller must flush/commit.

        Raises ValueError if the transition is not allowed.
        """
        allowed, msg = validate_transition(self.status, new_status)
        if not allowed:
            raise ValueError(msg)

        action_map = {
            EventStatus.APPROVED:         "approve",
            EventStatus.REJECTED:         "reject",
            EventStatus.PUBLISHED:        "publish",
            EventStatus.SUSPENDED:        "suspend",
            EventStatus.PAUSED:           "pause",
            EventStatus.CANCELLED:        "cancel",
            EventStatus.COMPLETED:        "complete",
            EventStatus.ARCHIVED:         "archive",
            EventStatus.DELETED:          "delete",
            EventStatus.DRAFT:            "revert_to_draft",
            EventStatus.PENDING_APPROVAL: "submit",
        }

        log = EventModerationLog(
            event_id    = self.id,
            user_id     = actor_id,
            action      = action_map.get(new_status, new_status.value),
            from_status = self.status,
            to_status   = new_status,
            reason      = reason,
            ip_address  = ip_address,
            user_agent  = user_agent,
        )

        # Side-effects per target status
        now = datetime.utcnow()
        if new_status == EventStatus.APPROVED:
            self.approved_at    = now
            self.approved_by_id = actor_id
        elif new_status == EventStatus.REJECTED:
            self.rejected_at      = now
            self.rejection_reason = reason
        elif new_status == EventStatus.SUSPENDED:
            self.suspended_at   = now
            self.suspended_by_id = actor_id
            self.suspension_reason = reason
        elif new_status == EventStatus.COMPLETED:
            self.completed_at = now
        elif new_status in (EventStatus.ARCHIVED, EventStatus.DELETED):
            self.is_deleted    = True
            self.deleted_at    = now
            self.deleted_by_id = actor_id
            self.deletion_reason = reason

        # When moving to APPROVED, record whether auto-publish is requested.
        # The service layer reads this flag after commit to decide whether
        # to immediately trigger publish_event().
        elif new_status == EventStatus.APPROVED:
            # side-effects already set approved_at / approved_by_id above
            pass  # auto_publish_on_approval is checked by the service, not here

        self.status = new_status
        return log

    def soft_delete(self, user_id: int, reason: str = None) -> "EventModerationLog":
        """
        Organiser soft-delete → ARCHIVED.
        The event is hidden from all public views but never physically removed.
        Registrations, financial records, and logs are preserved.
        """
        return self.transition_to(
            EventStatus.ARCHIVED,
            actor_id=user_id,
            reason=reason or "Organiser deleted",
        )

    def admin_remove(self, admin_id: int, reason: str) -> "EventModerationLog":
        """
        Admin hard-remove → DELETED.
        Still never physically removed — just excluded from all normal queries.
        """
        return self.transition_to(
            EventStatus.DELETED,
            actor_id=admin_id,
            reason=reason,
        )

    def restore(self):
        """Undo a soft-delete back to DRAFT for organiser revision."""
        self.is_deleted     = False
        self.deleted_at     = None
        self.deleted_by_id  = None
        self.deletion_reason = None
        self.status         = EventStatus.DRAFT

    # ── Ownership helpers ─────────────────────────────────────────────────

    def is_owned_by_user(self, user_id: int) -> bool:
        return (
            self.current_owner_type == OwnerType.INDIVIDUAL
            and self.current_owner_id == user_id
        )

    def is_owned_by_organization(self, org_id: int) -> bool:
        return (
            self.current_owner_type == OwnerType.ORGANIZATION
            and self.current_owner_id == org_id
        )

    def is_created_by_user(self, user_id: int) -> bool:
        return (
            self.created_by_type == CreatorType.INDIVIDUAL
            and self.created_by_entity_id == user_id
        )

    def is_system_owned(self) -> bool:
        return self.current_owner_type == OwnerType.SYSTEM


# ============================================================================
# TICKET TYPE MODEL
# ============================================================================

class TicketType(BaseModel):
    __tablename__ = "event_ticket_types"
    __table_args__ = (
        Index("idx_ticket_type_event_active", "event_id", "is_active"),
    )

    event_id        = Column(BigInteger, ForeignKey("events.id", ondelete="CASCADE"), nullable=False)
    name            = Column(String(100), nullable=False)
    description     = Column(Text)
    price           = Column(Numeric(10, 2), default=0)
    capacity        = Column(Integer, default=0, nullable=False)
    available_seats = Column(Integer, nullable=True)
    version         = Column(Integer, default=0, nullable=False)
    available_from  = Column(DateTime, nullable=True)
    available_until = Column(DateTime, nullable=True)
    is_active       = Column(Boolean, default=True)

    event         = relationship("Event", back_populates="ticket_types")
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
            return False        # unlimited
        if self.available_seats is None:
            self._sync_available_seats()
        return self.available_seats <= 0

    is_sold_out = _deprecated("is_sold_out_flag")

    def reserve_seat(self) -> bool:
        """Decrement available_seats.  Returns True if reservation succeeded."""
        if self.capacity == 0:
            return True         # unlimited
        if self.available_seats is None:
            self._sync_available_seats()
        if self.available_seats > 0:
            self.available_seats -= 1
            return True
        return False

    def release_seat(self, count: int = 1):
        """Return seats (e.g. on cancellation)."""
        if self.capacity == 0:
            return
        if self.available_seats is None:
            self.available_seats = 0
        self.available_seats = min(self.capacity, self.available_seats + count)
        self.version += 1


# ============================================================================
# EVENT REGISTRATION MODEL
# ============================================================================

# DB-level sequence for race-condition-free ticket numbering (PostgreSQL only)
_reg_seq = Sequence("event_registration_seq", metadata=db.Model.metadata)


class EventRegistration(BaseModel):
    __tablename__ = "event_registrations"
    __table_args__ = (
        UniqueConstraint("registration_ref", name="uq_reg_ref"),
        UniqueConstraint("ticket_number",    name="uq_ticket_number"),
        UniqueConstraint("qr_token",         name="uq_qr_token"),
        Index("idx_reg_event_user",      "event_id", "user_id"),
        Index("idx_reg_event_status",    "event_id", "status"),
        Index("idx_reg_event_payment",   "event_id", "payment_status"),
        Index("idx_reg_event_ticket",    "event_id", "ticket_type_id"),
        Index("idx_reg_user_status",     "user_id",  "status"),
        Index("idx_reg_created_event",   "created_at", "event_id"),
        Index("idx_reg_checkin",         "checked_in_at", "event_id"),
        Index("idx_reg_ticket_status",   "ticket_type_id", "status"),
        Index("idx_reg_payment_created", "payment_status", "created_at"),
        Index("idx_reg_qr_token",        "qr_token"),
        Index("idx_reg_email",           "email"),
        Index("idx_reg_phone",           "phone"),
        Index("idx_reg_created",         "created_at"),
        CheckConstraint("registration_fee >= 0", name="ck_reg_fee_non_negative"),
    )

    # Payment status constants
    PAYMENT_FREE     = "free"
    PAYMENT_PENDING  = "pending"
    PAYMENT_PAID     = "paid"
    PAYMENT_FAILED   = "failed"
    PAYMENT_REFUNDED = "refunded"
    PAYMENT_EXPIRED  = "expired"

    # Registration status constants
    STATUS_PENDING_PAYMENT = "pending_payment"
    STATUS_CONFIRMED       = "confirmed"
    STATUS_CANCELLED       = "cancelled"
    STATUS_CHECKED_IN      = "checked_in"
    STATUS_NO_SHOW         = "no_show"
    STATUS_EXPIRED         = "expired"

    # ── Columns ────────────────────────────────────────────────────────────
    # seq_number is sourced from a PG sequence — guaranteed unique, no races
    seq_number       = Column(BigInteger, _reg_seq, server_default=_reg_seq.next_value())

    registration_ref = Column(String(60),    unique=True, nullable=False, index=True)
    event_id         = Column(BigInteger,    ForeignKey("events.id", ondelete="RESTRICT"),
                              nullable=False, index=True)
    ticket_type_id   = Column(BigInteger,    ForeignKey("event_ticket_types.id", ondelete="RESTRICT"),
                              nullable=False)
    user_id          = Column(BigInteger,    ForeignKey("users.id", ondelete="SET NULL"),
                              nullable=True, index=True)
    full_name        = Column(String(255),   nullable=False)
    email            = Column(String(255),   nullable=False)
    phone            = Column(String(50))
    nationality      = Column(String(64))
    id_number        = Column(String(100))
    id_type          = Column(String(30))
    ticket_type      = Column(String(50),    default="general", nullable=False)
    ticket_number    = Column(String(50),    unique=True, nullable=False)
    qr_token         = Column(String(200),   unique=True, nullable=False, index=True)
    registration_fee = Column(Numeric(10, 2), default=0)
    payment_status   = Column(String(30),    default="free")
    wallet_txn_id    = Column(String(255),   nullable=True)
    status           = Column(String(30),    default="confirmed", nullable=False, index=True)
    checked_in_at    = Column(DateTime,      nullable=True)
    checked_in_by_id = Column(BigInteger,    ForeignKey("users.id"), nullable=True)
    discount_code_applied = Column(String(50), nullable=True)
    discount_amount  = Column(Numeric(10, 2), default=0, nullable=False)
    registered_by    = Column(String(30),    default="self")
    notes            = Column(Text,          nullable=True)

    # ── Relationships ──────────────────────────────────────────────────────
    event          = relationship("Event",      back_populates="registrations")
    ticket_type_rel = relationship("TicketType", back_populates="registrations")
    user           = relationship("User",        foreign_keys=[user_id])
    checked_in_by  = relationship("User",        foreign_keys=[checked_in_by_id])

    # ── Ref generation ─────────────────────────────────────────────────────

    def generate_refs(self, event_slug: str = None):
        """
        Generate registration_ref, ticket_number, and QR token.

        Uses the DB-backed `seq_number` (sourced from a PostgreSQL SEQUENCE)
        so this is safe under concurrent registrations with no race condition.
        The caller must ensure seq_number is populated (i.e. the row has been
        flushed) before calling this method, or pass it explicitly.
        """
        seq = self.seq_number
        if seq is None:
            raise RuntimeError(
                "seq_number is None — flush the session before calling generate_refs()."
            )

        slug = event_slug
        if not slug and self.event:
            slug = self.event.slug
        slug = (slug or "EVENT").upper().replace("-", "_")[:20]

        self.registration_ref = f"ER-{slug}-{seq:08d}"
        self.ticket_number    = f"TKT-{slug}-{seq:08d}"

        # HMAC-signed QR token — tamper-evident
        payload   = f"AFCON360:{self.registration_ref}:{seq}"
        key       = os.environ.get("QR_SECRET_KEY", "dev-secret-change-in-production").encode()
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

    def __repr__(self):
        return f"<EventRegistration {self.registration_ref}: {self.full_name!r}>"


# ============================================================================
# WAITLIST MODEL
# ============================================================================

class Waitlist(BaseModel):
    __tablename__ = "event_waitlist"
    __table_args__ = (
        UniqueConstraint("event_id", "user_id",    name="uq_waitlist_event_user"),
        Index("idx_waitlist_event_status",  "event_id", "status"),
        Index("idx_waitlist_created",       "created_at"),
        Index("idx_waitlist_position",      "event_id", "position"),
        Index("idx_waitlist_notification",  "notification_sent", "created_at"),
    )

    event_id            = Column(BigInteger, ForeignKey("events.id",             ondelete="CASCADE"), nullable=False, index=True)
    user_id             = Column(BigInteger, ForeignKey("users.id",              ondelete="CASCADE"), nullable=False, index=True)
    ticket_type_id      = Column(BigInteger, ForeignKey("event_ticket_types.id", ondelete="CASCADE"), nullable=True)
    position            = Column(Integer,    nullable=False, default=1)
    status              = Column(String(30), default="pending", nullable=False, index=True)
    email               = Column(String(255), nullable=False)
    phone               = Column(String(50),  nullable=True)
    notes               = Column(Text,        nullable=True)
    notified_at         = Column(DateTime,    nullable=True)
    converted_at        = Column(DateTime,    nullable=True)
    notification_sent   = Column(Boolean,     default=False, nullable=False)
    conversion_attempts = Column(Integer,     default=0, nullable=False)

    event       = relationship("Event",      backref="waitlist_entries")
    user        = relationship("User",       foreign_keys=[user_id])
    ticket_type = relationship("TicketType", foreign_keys=[ticket_type_id])

    def mark_notified(self):
        self.notified_at       = datetime.utcnow()
        self.notification_sent = True

    def mark_converted(self):
        self.converted_at = datetime.utcnow()
        self.status       = "converted"

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
        Index("idx_event_roles_user",  "user_id"),
        Index("idx_event_roles_role",  "role"),
    )

    event_id        = Column(BigInteger, ForeignKey("events.id",        ondelete="CASCADE"),   nullable=False)
    user_id         = Column(BigInteger, ForeignKey("users.id",         ondelete="CASCADE"),   nullable=False)
    role            = Column(String(50), nullable=False)
    organisation_id = Column(BigInteger, ForeignKey("organisations.id", ondelete="SET NULL"),  nullable=True, index=True)
    permissions     = Column(JSON,       default=list)
    assigned_by_id  = Column(BigInteger, ForeignKey("users.id"),        nullable=True)
    assigned_at     = Column(DateTime,   default=func.now())
    is_active       = Column(Boolean,    default=True)

    event        = relationship("Event",        backref="staff_roles")
    user         = relationship("User",         foreign_keys=[user_id])
    organisation = relationship("Organisation", foreign_keys=[organisation_id])
    assigned_by  = relationship("User",         foreign_keys=[assigned_by_id])

    def __repr__(self):
        return f"<EventRole event={self.event_id} user={self.user_id} role={self.role!r}>"


# ============================================================================
# DISCOUNT CODE MODEL
# ============================================================================

class DiscountCode(BaseModel):
    __tablename__ = "discount_codes"
    __table_args__ = (
        Index("idx_discount_code_event",  "event_id"),
        Index("idx_discount_code_active", "is_active", "valid_until"),
        UniqueConstraint("code",          name="uq_discount_code"),
    )

    event_id       = Column(BigInteger,     ForeignKey("events.id", ondelete="CASCADE"), nullable=False, index=True)
    code           = Column(String(50),     nullable=False, unique=True, index=True)
    discount_type  = Column(_sa_enum(DiscountType, "discounttype"), nullable=False)
    discount_value = Column(Numeric(10, 2), nullable=False)
    currency       = Column(String(3),      default="USD")
    valid_from     = Column(DateTime,       nullable=False, default=datetime.utcnow)
    valid_until    = Column(DateTime,       nullable=True)
    usage_limit    = Column(Integer,        nullable=True)
    used_count     = Column(Integer,        default=0, nullable=False)
    minimum_order  = Column(Numeric(10, 2), default=0)
    is_active      = Column(Boolean,        default=True, nullable=False)
    created_by     = Column(BigInteger,     ForeignKey("users.id"), nullable=True)

    event   = relationship("Event", backref="discount_codes")
    creator = relationship("User",  foreign_keys=[created_by])

    def is_valid(self) -> bool:
        now = datetime.utcnow()
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
        Index("idx_transfer_from_user",    "from_user_id"),
        Index("idx_transfer_to_org",       "to_organization_id"),
    )

    event_id             = Column(BigInteger, ForeignKey("events.id",        ondelete="CASCADE"),   nullable=False)
    from_user_id         = Column(BigInteger, ForeignKey("users.id",         ondelete="SET NULL"),  nullable=True)
    from_organization_id = Column(BigInteger, ForeignKey("organisations.id", ondelete="SET NULL"),  nullable=True)
    to_user_id           = Column(BigInteger, ForeignKey("users.id",         ondelete="SET NULL"),  nullable=True)
    to_organization_id   = Column(BigInteger, ForeignKey("organisations.id", ondelete="SET NULL"),  nullable=True)
    requested_by_id      = Column(BigInteger, ForeignKey("users.id"),        nullable=False)
    status               = Column(
        _sa_enum(TransferStatus, "transferstatus"),
        nullable=False,
        default=TransferStatus.PENDING,
    )
    reason         = Column(Text,     nullable=True)
    approved_by_id = Column(BigInteger, ForeignKey("users.id"), nullable=True)
    approved_at    = Column(DateTime, nullable=True)
    expires_at     = Column(DateTime, nullable=True)

    event             = relationship("Event",        foreign_keys=[event_id])
    from_user         = relationship("User",         foreign_keys=[from_user_id])
    from_organization = relationship("Organisation", foreign_keys=[from_organization_id])
    to_user           = relationship("User",         foreign_keys=[to_user_id])
    to_organization   = relationship("Organisation", foreign_keys=[to_organization_id])
    requested_by      = relationship("User",         foreign_keys=[requested_by_id])
    approved_by       = relationship("User",         foreign_keys=[approved_by_id])

    def approve(self, approver_id: int):
        self.status         = TransferStatus.APPROVED
        self.approved_by_id = approver_id
        self.approved_at    = datetime.utcnow()

    def __repr__(self):
        return f"<EventTransferRequest {self.id}: event {self.event_id} [{self.status.value}]>"


# ============================================================================
# EVENT MODERATION LOG  (append-only — never delete rows from this table)
# ============================================================================

class EventModerationLog(BaseModel):
    __tablename__ = "event_moderation_logs"
    __table_args__ = (
        Index("idx_moderation_event",  "event_id"),
        Index("idx_moderation_user",   "user_id"),
        Index("idx_moderation_action", "action"),
        Index("idx_moderation_date",   "created_at"),
    )

    event_id    = Column(BigInteger, ForeignKey("events.id", ondelete="CASCADE"), nullable=False)
    user_id     = Column(BigInteger, ForeignKey("users.id"), nullable=False)
    action      = Column(String(50), nullable=False)
    from_status = Column(_sa_enum(EventStatus, "eventstatus"), nullable=False)
    to_status   = Column(_sa_enum(EventStatus, "eventstatus"), nullable=False)
    reason      = Column(Text,        nullable=True)
    ip_address  = Column(String(64),  nullable=True)
    user_agent  = Column(String(512), nullable=True)
    extra_data  = Column(JSON,        default=dict)

    event = relationship("Event", foreign_keys=[event_id])
    user  = relationship("User",  foreign_keys=[user_id])

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

    event_id          = Column(BigInteger, ForeignKey("events.id", ondelete="CASCADE"), nullable=False)
    from_owner_type   = Column(_sa_enum(OwnerType, "ownertype"), nullable=False)
    from_owner_id     = Column(BigInteger, nullable=False)
    to_owner_type     = Column(_sa_enum(OwnerType, "ownertype"), nullable=False)
    to_owner_id       = Column(BigInteger, nullable=False)
    transferred_by_id = Column(BigInteger, ForeignKey("users.id"), nullable=False)
    transferred_at    = Column(DateTime,   default=datetime.utcnow)
    extra_data        = Column(JSON,       default=dict)

    event          = relationship("Event", foreign_keys=[event_id])
    transferred_by = relationship("User",  foreign_keys=[transferred_by_id])

    def __repr__(self):
        return (
            f"<EventTransferLog {self.id}: event {self.event_id} "
            f"{self.from_owner_type.value}:{self.from_owner_id} → "
            f"{self.to_owner_type.value}:{self.to_owner_id}>"
        )


# ============================================================================
# EVENT ASSIGNMENT MODEL
# ============================================================================

class EventAssignment(BaseModel):
    __tablename__ = "event_assignments"
    __table_args__ = (
        UniqueConstraint("event_id", "attendee_id", name="uq_event_assignment_attendee"),
        Index("idx_assignment_event_attendee", "event_id", "attendee_id"),
        Index("idx_assignment_accommodation", "accommodation_booking_id"),
        Index("idx_assignment_transport", "transport_booking_id"),
        Index("idx_assignment_meal", "meal_booking_id"),
        Index("idx_assignment_managed_by", "managed_by"),
        Index("idx_assignment_created", "created_at"),
        Index("idx_assignment_registration", "registration_id"),
    )

    event_id                  = Column(BigInteger, ForeignKey("events.id", ondelete="CASCADE"), nullable=False)
    attendee_id               = Column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    accommodation_booking_id  = Column(BigInteger, nullable=True)
    transport_booking_id      = Column(BigInteger, nullable=True)
    meal_booking_id           = Column(BigInteger, nullable=True)
    managed_by                = Column(BigInteger, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    notes                     = Column(Text, nullable=True)
    schedule_json             = Column(JSON, default=dict)
    registration_id           = Column(BigInteger, ForeignKey("event_registrations.id", ondelete="SET NULL"), nullable=True)
    status                    = Column(String(30), default="active", nullable=False)
    assigned_by_id            = Column(BigInteger, ForeignKey("users.id"), nullable=True)
    assigned_at               = Column(DateTime, default=func.now())

    event        = relationship("Event", foreign_keys=[event_id], backref="assignments")
    attendee     = relationship("User", foreign_keys=[attendee_id])
    manager      = relationship("User", foreign_keys=[managed_by])
    registration = relationship("EventRegistration", foreign_keys=[registration_id])
    assigned_by  = relationship("User", foreign_keys=[assigned_by_id])

    def __repr__(self):
        return f"<EventAssignment {self.id}: event {self.event_id}, attendee {self.attendee_id}>"
