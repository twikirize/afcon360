# app/events/models.py
from sqlalchemy import (
    Column, BigInteger, Integer, String, Boolean, DateTime, Date,
    ForeignKey, Text, Numeric, JSON, Index, UniqueConstraint, CheckConstraint
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.extensions import db
from app.models.base import BaseModel


class Event(BaseModel):
    __tablename__ = "events"
    __table_args__ = (
        Index("idx_event_start_date", "start_date"),
        Index("idx_event_status_featured", "status", "featured"),
        Index("idx_event_is_deleted", "is_deleted"),
        Index("idx_event_slug_unique", "slug", "is_deleted", unique=True),
        # Check constraint for date validation
        CheckConstraint("end_date >= start_date", name="ck_event_end_after_start"),
        CheckConstraint("max_capacity >= 0", name="ck_event_max_capacity_non_negative"),
    )

    event_ref = Column(String(50), unique=True)
    slug = Column(String(120), nullable=False)  # Made non-unique, combined with is_deleted for uniqueness
    name = Column(String(255), nullable=False)
    description = Column(Text)
    category = Column(String(50), nullable=False)
    city = Column(String(100), nullable=False)
    country = Column(String(100), default="Uganda")
    venue = Column(String(255))
    start_date = Column(Date)
    end_date = Column(Date)
    max_capacity = Column(Integer, default=0, nullable=False)
    registration_required = Column(Boolean, default=False)
    registration_fee = Column(Numeric(10, 2), default=0, nullable=False)
    currency = Column(String(3), default="USD")
    status = Column(String(30), default="draft")  # Added "draft" as default
    featured = Column(Boolean, default=False)
    organizer_id = Column(BigInteger, ForeignKey("users.id"), nullable=False)
    website = Column(String(500))
    contact_email = Column(String(255))
    contact_phone = Column(String(50))
    event_metadata = Column(JSON, default=dict)
    approved_at = Column(DateTime, nullable=True)
    approved_by_id = Column(BigInteger, ForeignKey("users.id"), nullable=True)
    rejected_at = Column(DateTime, nullable=True)
    rejection_reason = Column(Text, nullable=True)

    # Soft delete
    is_deleted = Column(Boolean, default=False, nullable=False, index=True)
    deleted_at = Column(DateTime, nullable=True)
    deleted_by_id = Column(BigInteger, ForeignKey("users.id"), nullable=True)

    # Versioning for optimistic locking
    version = Column(Integer, default=0, nullable=False)

    # Audit trail
    created_by_id = Column(BigInteger, ForeignKey("users.id"), nullable=True)
    updated_by_id = Column(BigInteger, ForeignKey("users.id"), nullable=True)

    # Relationships
    approved_by = relationship("User", foreign_keys=[approved_by_id])
    organizer = relationship("User", foreign_keys=[organizer_id])
    deleted_by = relationship("User", foreign_keys=[deleted_by_id])
    created_by = relationship("User", foreign_keys=[created_by_id])
    updated_by = relationship("User", foreign_keys=[updated_by_id])
    registrations = relationship("EventRegistration", back_populates="event", cascade="all, delete-orphan")
    ticket_types = relationship("TicketType", back_populates="event", cascade="all, delete-orphan")

    def generate_ref(self):
        """Generate human-readable event reference from slug."""
        slug_part = self.slug.upper()[:20]
        self.event_ref = f"EVT-{slug_part}"

    def __repr__(self):
        return f"<Event {self.id}: {self.name} ({self.slug})>"

    @property
    def is_active(self):
        return self.status == "active"

    @property
    def is_pending(self):
        return self.status == "pending"

    @property
    def is_rejected(self):
        return self.status == "rejected"

    @property
    def is_draft(self):
        return self.status == "draft"

    @property
    def is_cancelled(self):
        return self.status == "cancelled"

    @property
    def is_archived(self):
        return self.status == "archived"

    def soft_delete(self, user_id):
        """Soft delete the event."""
        self.is_deleted = True
        self.deleted_at = func.now()
        self.deleted_by_id = user_id
        self.status = "archived"

    def restore(self):
        """Restore a soft-deleted event."""
        self.is_deleted = False
        self.deleted_at = None
        self.deleted_by_id = None


class TicketType(BaseModel):
    """Different ticket tiers for an event"""
    __tablename__ = "event_ticket_types"

    event_id = Column(BigInteger, ForeignKey("events.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(100), nullable=False)  # e.g., VIP, Regular, Early Bird
    description = Column(Text)
    price = Column(Numeric(10, 2), default=0)
    capacity = Column(Integer, default=0, nullable=False)  # 0 means unlimited
    available_seats = Column(Integer, nullable=True)  # Track available seats separately
    version = Column(Integer, default=0, nullable=False)  # For optimistic concurrency control
    available_from = Column(DateTime, nullable=True)
    available_until = Column(DateTime, nullable=True)
    is_active = Column(Boolean, default=True)

    # Relationships
    event = relationship("Event", back_populates="ticket_types")
    registrations = relationship("EventRegistration", back_populates="ticket_type_rel")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Initialize available_seats to capacity if not set
        if self.available_seats is None:
            self.available_seats = self.capacity

    def __repr__(self):
        return f"<TicketType {self.name} for {self.event.name}>"

    @property
    def is_sold_out(self):
        """Check if ticket type is sold out"""
        if self.capacity == 0:  # Unlimited capacity
            return False
        if self.available_seats is None:
            # Fallback to counting registrations
            from app.extensions import db
            from sqlalchemy import func
            count = db.session.query(func.count(EventRegistration.id)).filter_by(
                ticket_type_id=self.id
            ).scalar()
            return count >= self.capacity
        return self.available_seats <= 0

    def reserve_seat(self):
        """Reserve one seat (decrement available_seats)"""
        if self.capacity == 0:  # Unlimited
            return True
        if self.available_seats is None:
            # Initialize available_seats
            from app.extensions import db
            from sqlalchemy import func
            count = db.session.query(func.count(EventRegistration.id)).filter_by(
                ticket_type_id=self.id
            ).scalar()
            self.available_seats = max(0, self.capacity - count)

        if self.available_seats > 0:
            self.available_seats -= 1
            return True
        return False

    def release_seat(self, count=1):
        """Release seats back to available pool"""
        if self.capacity == 0:  # Unlimited
            return
        if self.available_seats is None:
            self.available_seats = 0
        self.available_seats = min(self.capacity, self.available_seats + count)
        # Increment version for optimistic locking
        self.version += 1


class EventRegistration(BaseModel):
    """Event Registration - Personal passport for each attendee"""
    __tablename__ = "event_registrations"
    __table_args__ = (
        UniqueConstraint("registration_ref", name="uq_reg_ref"),
        UniqueConstraint("ticket_number", name="uq_ticket_number"),
        UniqueConstraint("qr_token", name="uq_qr_token"),
        # Composite indexes for common query patterns
        Index("idx_reg_event_user", "event_id", "user_id"),
        Index("idx_reg_event_status", "event_id", "status"),
        Index("idx_reg_event_payment", "event_id", "payment_status"),
        Index("idx_reg_event_ticket", "event_id", "ticket_type_id"),
        Index("idx_reg_user_status", "user_id", "status"),
        Index("idx_reg_created_event", "created_at", "event_id"),
        Index("idx_reg_checkin", "checked_in_at", "event_id"),
        # Single column indexes
        Index("idx_reg_qr_token", "qr_token"),
        Index("idx_reg_email", "email"),
        Index("idx_reg_phone", "phone"),
        Index("idx_reg_created", "created_at"),
        # Check constraints
        CheckConstraint("registration_fee >= 0", name="ck_reg_fee_non_negative"),
    )

    # Payment status constants
    PAYMENT_STATUS_FREE = 'free'
    PAYMENT_STATUS_PENDING = 'pending'
    PAYMENT_STATUS_PAID = 'paid'
    PAYMENT_STATUS_FAILED = 'failed'
    PAYMENT_STATUS_REFUNDED = 'refunded'
    PAYMENT_STATUS_EXPIRED = 'expired'  # NEW

    # Registration status constants
    STATUS_PENDING_PAYMENT = 'pending_payment'
    STATUS_CONFIRMED = 'confirmed'
    STATUS_CANCELLED = 'cancelled'
    STATUS_CHECKED_IN = 'checked_in'
    STATUS_NO_SHOW = 'no_show'
    STATUS_EXPIRED = 'expired'  # NEW

    registration_ref = Column(String(60), unique=True, nullable=False, index=True)
    # format: ER-CRUSADE-2026-00001

    # Event link
    event_id = Column(BigInteger, ForeignKey("events.id", ondelete="RESTRICT"), nullable=False, index=True)
    event = relationship("Event", back_populates="registrations")

    # Ticket Type link
    ticket_type_id = Column(BigInteger, ForeignKey("event_ticket_types.id", ondelete="RESTRICT"), nullable=False)
    ticket_type_rel = relationship("TicketType", back_populates="registrations")

    # User link (nullable for guest registrations)
    user_id = Column(BigInteger, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    user = relationship("User", foreign_keys=[user_id])

    # Attendee snapshot (captured at registration time)
    full_name = Column(String(255), nullable=False)
    email = Column(String(255), nullable=False)
    phone = Column(String(50))
    nationality = Column(String(64))
    id_number = Column(String(100))
    id_type = Column(String(30))  # passport, national_id, voter_card

    # Ticket (Snapshot of ticket type at time of registration - denormalized for performance)
    ticket_type = Column(String(50), default="general", nullable=False)
    # types: general, vip, volunteer, media, organizer, sponsor
    ticket_number = Column(String(50), unique=True, nullable=False)
    qr_token = Column(String(100), unique=True, nullable=False, index=True)

    # Payment
    registration_fee = Column(Numeric(10, 2), default=0)
    payment_status = Column(String(30), default="free")
    # free, pending, paid, failed, refunded
    wallet_txn_id = Column(String(255), nullable=True)

    # Status
    status = Column(String(30), default="confirmed", nullable=False, index=True)
    # confirmed, cancelled, checked_in, no_show, pending_payment

    # Check-in
    checked_in_at = Column(DateTime, nullable=True)
    checked_in_by_id = Column(BigInteger, ForeignKey("users.id"), nullable=True)
    checked_in_by = relationship("User", foreign_keys=[checked_in_by_id])

    # Metadata
    registered_by = Column(String(30), default="self")
    # self, organizer, bulk_import, admin
    notes = Column(Text, nullable=True)


    def generate_refs(self, event_slug: str, sequence: int):
        """Generate registration_ref, ticket_number, and qr_token"""
        import secrets
        slug_part = event_slug.upper().replace("-", "_")[:20]
        self.registration_ref = f"ER-{slug_part}-{sequence:05d}"
        self.ticket_number = f"TKT-{slug_part}-{sequence:05d}"
        self.qr_token = secrets.token_urlsafe(32)

    @property
    def is_checked_in(self):
        return self.status == "checked_in"

    def __repr__(self):
        return f"<EventRegistration {self.registration_ref}: {self.full_name}>"


class Waitlist(BaseModel):
    """Waitlist for sold-out events"""
    __tablename__ = "event_waitlist"
    __table_args__ = (
        UniqueConstraint("event_id", "user_id", name="uq_waitlist_event_user"),
        Index("idx_waitlist_event_status", "event_id", "status"),
        Index("idx_waitlist_created", "created_at"),
        Index("idx_waitlist_position", "event_id", "position"),
    )

    event_id = Column(BigInteger, ForeignKey("events.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    ticket_type_id = Column(BigInteger, ForeignKey("event_ticket_types.id", ondelete="CASCADE"), nullable=True)

    # Waitlist position
    position = Column(Integer, nullable=False, default=1)

    # Status: pending, notified, converted, cancelled
    status = Column(String(30), default="pending", nullable=False, index=True)

    # Contact info (snapshot at time of joining waitlist)
    email = Column(String(255), nullable=False)
    phone = Column(String(50), nullable=True)

    # Metadata
    notes = Column(Text, nullable=True)
    notified_at = Column(DateTime, nullable=True)
    converted_at = Column(DateTime, nullable=True)

    # Relationships
    event = relationship("Event", backref="waitlist_entries")
    user = relationship("User", foreign_keys=[user_id])
    ticket_type = relationship("TicketType", foreign_keys=[ticket_type_id])

    def __repr__(self):
        return f"<Waitlist {self.event.slug}: {self.user_id} pos={self.position}>"


class EventRole(BaseModel):
    """Event-specific roles for staff management"""
    __tablename__ = "event_roles"
    __table_args__ = (
        UniqueConstraint("event_id", "user_id", "role", name="uq_event_user_role"),
        Index("idx_event_roles_event", "event_id"),
        Index("idx_event_roles_user", "user_id"),
        Index("idx_event_roles_role", "role"),
    )

    event_id = Column(BigInteger, ForeignKey("events.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    role = Column(String(50), nullable=False)  # organizer, co_organizer, steward, volunteer, media
    organisation_id = Column(BigInteger, ForeignKey("organisations.id", ondelete="SET NULL"), nullable=True, index=True)
    permissions = Column(JSON, default=list)  # Additional custom permissions

    # Who assigned this role
    assigned_by_id = Column(BigInteger, ForeignKey("users.id"), nullable=True)
    assigned_at = Column(DateTime, default=func.now())

    # Status
    is_active = Column(Boolean, default=True)


    # Relationships
    event = relationship("Event", backref="staff_roles")
    user = relationship("User", foreign_keys=[user_id])
    organisation = relationship("Organisation", foreign_keys=[organisation_id])
    assigned_by = relationship("User", foreign_keys=[assigned_by_id])

    def __repr__(self):
        return f"<EventRole {self.event.slug}: {self.user.email} as {self.role}>"
