# app/events/models.py
from sqlalchemy import (
    Column, BigInteger, Integer, String, Boolean, DateTime, Date,
    ForeignKey, Text, Numeric, JSON, Index, UniqueConstraint
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.extensions import db


class Event(db.Model):
    __tablename__ = "events"

    id = Column(BigInteger, primary_key=True)
    event_ref = Column(String(50), unique=True)
    slug = Column(String(120), unique=True, nullable=False)
    name = Column(String(255), nullable=False)
    description = Column(Text)
    category = Column(String(50), nullable=False)
    city = Column(String(100), nullable=False)
    country = Column(String(100), default="Uganda")
    venue = Column(String(255))
    start_date = Column(Date)
    end_date = Column(Date)
    max_capacity = Column(Integer)
    registration_required = Column(Boolean, default=False)
    registration_fee = Column(Numeric(10, 2), default=0)
    currency = Column(String(3), default="USD")
    status = Column(String(30), default="pending")
    featured = Column(Boolean, default=False)
    organizer_id = Column(BigInteger, ForeignKey("users.id"), nullable=False)
    website = Column(String(500))
    contact_email = Column(String(255))
    contact_phone = Column(String(50))
    event_metadata = Column(JSON, default=dict)
    created_at = Column(DateTime, default=func.now())
    approved_at = Column(DateTime, nullable=True)
    approved_by_id = Column(BigInteger, ForeignKey("users.id"), nullable=True)
    rejected_at = Column(DateTime, nullable=True)
    rejection_reason = Column(Text, nullable=True)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # Relationships
    approved_by = relationship("User", foreign_keys=[approved_by_id])
    organizer = relationship("User", foreign_keys=[organizer_id])
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


class TicketType(db.Model):
    """Different ticket tiers for an event"""
    __tablename__ = "event_ticket_types"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    event_id = Column(BigInteger, ForeignKey("events.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(100), nullable=False)  # e.g., VIP, Regular, Early Bird
    description = Column(Text)
    price = Column(Numeric(10, 2), default=0)
    capacity = Column(Integer)  # Null if unlimited
    available_from = Column(DateTime)
    available_until = Column(DateTime)
    is_active = Column(Boolean, default=True)

    # Relationships
    event = relationship("Event", back_populates="ticket_types")
    registrations = relationship("EventRegistration", back_populates="ticket_type_rel")

    def __repr__(self):
        return f"<TicketType {self.name} for {self.event.name}>"


class EventRegistration(db.Model):
    """Event Registration - Personal passport for each attendee"""
    __tablename__ = "event_registrations"
    __table_args__ = (
        UniqueConstraint("registration_ref", name="uq_reg_ref"),
        UniqueConstraint("ticket_number", name="uq_ticket_number"),
        UniqueConstraint("qr_token", name="uq_qr_token"),
        Index("idx_reg_event_user", "event_id", "user_id"),
        Index("idx_reg_event_status", "event_id", "status"),
        Index("idx_reg_qr_token", "qr_token"),
        Index("idx_reg_email", "email"),
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    registration_ref = Column(String(60), unique=True, nullable=False, index=True)
    # format: ER-CRUSADE-2026-00001

    # Event link
    event_id = Column(BigInteger, ForeignKey("events.id", ondelete="RESTRICT"), nullable=False, index=True)
    event = relationship("Event", back_populates="registrations")

    # Ticket Type link
    ticket_type_id = Column(BigInteger, ForeignKey("event_ticket_types.id", ondelete="SET NULL"), nullable=True)
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

    # Ticket (Snapshot of ticket type at time of registration)
    ticket_type = Column(String(50), default="general")
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
    # confirmed, cancelled, checked_in, no_show

    # Check-in
    checked_in_at = Column(DateTime, nullable=True)
    checked_in_by_id = Column(BigInteger, ForeignKey("users.id"), nullable=True)
    checked_in_by = relationship("User", foreign_keys=[checked_in_by_id])

    # Metadata
    registered_by = Column(String(30), default="self")
    # self, organizer, bulk_import, admin
    notes = Column(Text, nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

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


class EventRole(db.Model):
    """Event-specific roles for staff management"""
    __tablename__ = "event_roles"
    __table_args__ = (
        UniqueConstraint("event_id", "user_id", "role", name="uq_event_user_role"),
        Index("idx_event_roles_event", "event_id"),
        Index("idx_event_roles_user", "user_id"),
        Index("idx_event_roles_role", "role"),
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
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

    # Timestamps
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # Relationships
    event = relationship("Event", backref="staff_roles")
    user = relationship("User", foreign_keys=[user_id])
    organisation = relationship("Organisation", foreign_keys=[organisation_id])
    assigned_by = relationship("User", foreign_keys=[assigned_by_id])

    def __repr__(self):
        return f"<EventRole {self.event.slug}: {self.user.email} as {self.role}>"
