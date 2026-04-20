# app/events/models.py
import uuid
import enum
from datetime import datetime
from sqlalchemy import (
    Column, BigInteger, Integer, String, Boolean, DateTime, Date,
    ForeignKey, Text, Numeric, JSON, Index, UniqueConstraint, CheckConstraint
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.extensions import db
from app.models.base import BaseModel
from sqlalchemy import Enum as SAEnum


# ============================================================================
# PYTHON ENUM CLASSES
# ============================================================================

class CreatorType(str, enum.Enum):
    INDIVIDUAL = 'individual'
    ORGANIZATION = 'organization'
    SYSTEM = 'system'


class OwnerType(str, enum.Enum):
    INDIVIDUAL = 'individual'
    ORGANIZATION = 'organization'
    SYSTEM = 'system'


class TransferStatus(str, enum.Enum):
    PENDING = 'pending'
    APPROVED = 'approved'
    REJECTED = 'rejected'
    CANCELLED = 'cancelled'


class DiscountType(str, enum.Enum):
    PERCENTAGE = 'percentage'
    FIXED = 'fixed'


# ============================================================================
# EVENT MODEL
# ============================================================================

class Event(BaseModel):
    __tablename__ = "events"
    __table_args__ = (
        Index("idx_event_start_date", "start_date"),
        Index("idx_event_status_featured", "status", "featured"),
        Index("idx_event_is_deleted", "is_deleted"),
        Index("idx_event_slug_unique", "slug", "is_deleted", unique=True),
        UniqueConstraint("slug", name="uq_event_slug"),
        Index("idx_event_category", "category"),
        Index("idx_event_organizer_status", "organizer_id", "status"),
        Index("idx_event_status_start", "status", "start_date"),
        Index('idx_event_creator_type', 'created_by_type'),
        Index('idx_event_organization', 'organization_id'),
        Index('idx_event_system', 'is_system_event'),
        Index('idx_event_current_owner', 'current_owner_type', 'current_owner_id'),
        CheckConstraint("end_date >= start_date", name="ck_event_end_after_start"),
        CheckConstraint("max_capacity >= 0", name="ck_event_max_capacity_non_negative"),
    )

    # Primary identifiers
    public_id = Column(String(64), unique=True, nullable=False, default=lambda: str(uuid.uuid4()), index=True)
    event_ref = Column(String(50), unique=True)
    slug = Column(String(120), nullable=False)
    name = Column(String(255), nullable=False)
    description = Column(Text)
    category = Column(String(50), nullable=False, default="general")
    city = Column(String(100), nullable=False)
    country = Column(String(100), default="Uganda")
    venue = Column(String(255))
    start_date = Column(Date)
    end_date = Column(Date)
    max_capacity = Column(Integer, default=0, nullable=False)
    registration_required = Column(Boolean, default=False)
    registration_fee = Column(Numeric(10, 2), default=0, nullable=False)
    currency = Column(String(3), default="USD")
    status = Column(String(30), default="draft")
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

    # Moderation / Enforcement fields
    suspension_reason = Column(Text, nullable=True)
    suspension_duration = Column(String(20), nullable=True)
    suspended_at = Column(DateTime, nullable=True)
    suspended_by_id = Column(BigInteger, ForeignKey('users.id'), nullable=True)

    deactivation_reason = Column(Text, nullable=True)
    deactivated_at = Column(DateTime, nullable=True)
    deactivated_by_id = Column(BigInteger, ForeignKey('users.id'), nullable=True)

    takedown_reason = Column(Text, nullable=True)
    takedown_category = Column(String(50), nullable=True)
    taken_down_at = Column(DateTime, nullable=True)
    taken_down_by_id = Column(BigInteger, ForeignKey('users.id'), nullable=True)

    # Soft delete
    is_deleted = Column(Boolean, default=False, nullable=False, index=True)
    deleted_at = Column(DateTime, nullable=True)
    deleted_by_id = Column(BigInteger, ForeignKey("users.id"), nullable=True)

    # Versioning for optimistic locking
    version = Column(Integer, default=0, nullable=False)

    # Audit trail
    created_by_id = Column(BigInteger, ForeignKey("users.id"), nullable=True)
    updated_by_id = Column(BigInteger, ForeignKey("users.id"), nullable=True)

    # Ownership tracking (NEW)
    created_by_type = Column(SAEnum(CreatorType, name="creatortype"), nullable=False, default=CreatorType.INDIVIDUAL)
    organization_id = Column(BigInteger, ForeignKey('organisations.id', ondelete='SET NULL'), nullable=True, index=True)
    is_system_event = Column(Boolean, default=False, nullable=False, index=True)
    original_creator_id = Column(BigInteger, ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    current_owner_type = Column(SAEnum(OwnerType, name="ownertype"), nullable=False, default=OwnerType.INDIVIDUAL)
    current_owner_id = Column(BigInteger, nullable=False, index=True)

    # Relationships
    approved_by = relationship("User", foreign_keys=[approved_by_id])
    organizer = relationship("User", foreign_keys=[organizer_id])
    deleted_by = relationship("User", foreign_keys=[deleted_by_id])
    created_by = relationship("User", foreign_keys=[created_by_id])
    updated_by = relationship("User", foreign_keys=[updated_by_id])
    suspended_by = relationship('User', foreign_keys=[suspended_by_id])
    deactivated_by = relationship('User', foreign_keys=[deactivated_by_id])
    taken_down_by = relationship('User', foreign_keys=[taken_down_by_id])
    registrations = relationship("EventRegistration", back_populates="event", cascade="all, delete-orphan")
    ticket_types = relationship("TicketType", back_populates="event", cascade="all, delete-orphan")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if not self.public_id:
            self.public_id = str(uuid.uuid4())
        if not self.current_owner_id and self.organizer_id:
            self.current_owner_id = self.organizer_id

    def generate_ref(self):
        slug_part = self.slug.upper()[:20]
        self.event_ref = f"EVT-{slug_part}"

    def ensure_public_id(self):
        if not self.public_id:
            self.public_id = str(uuid.uuid4())

    def set_default_owner(self):
        if not self.current_owner_id and self.organizer_id:
            self.current_owner_type = OwnerType.INDIVIDUAL
            self.current_owner_id = self.organizer_id
            self.created_by_type = CreatorType.INDIVIDUAL
        if not self.public_id:
            self.public_id = str(uuid.uuid4())

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
        self.is_deleted = True
        self.deleted_at = func.now()
        self.deleted_by_id = user_id
        self.status = "archived"

    def restore(self):
        self.is_deleted = False
        self.deleted_at = None
        self.deleted_by_id = None

    def is_owned_by_user(self, user_id: int) -> bool:
        return self.current_owner_type == OwnerType.INDIVIDUAL and self.current_owner_id == user_id

    def is_owned_by_organization(self, org_id: int) -> bool:
        return self.current_owner_type == OwnerType.ORGANIZATION and self.current_owner_id == org_id


# ============================================================================
# TICKET TYPE MODEL
# ============================================================================

class TicketType(BaseModel):
    __tablename__ = "event_ticket_types"
    __table_args__ = (
        Index('idx_ticket_type_event_active', 'event_id', 'is_active'),
    )

    event_id = Column(BigInteger, ForeignKey("events.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(100), nullable=False)
    description = Column(Text)
    price = Column(Numeric(10, 2), default=0)
    capacity = Column(Integer, default=0, nullable=False)
    available_seats = Column(Integer, nullable=True)
    version = Column(Integer, default=0, nullable=False)
    available_from = Column(DateTime, nullable=True)
    available_until = Column(DateTime, nullable=True)
    is_active = Column(Boolean, default=True)

    event = relationship("Event", back_populates="ticket_types")
    registrations = relationship("EventRegistration", back_populates="ticket_type_rel")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if self.available_seats is None:
            self.available_seats = self.capacity

    def __repr__(self):
        return f"<TicketType {self.name} for {self.event.name}>"

    @property
    def is_sold_out(self):
        if self.capacity == 0:
            return False
        if self.available_seats is None:
            from app.extensions import db
            from sqlalchemy import func
            count = db.session.query(func.count(EventRegistration.id)).filter_by(
                ticket_type_id=self.id
            ).scalar()
            return count >= self.capacity
        return self.available_seats <= 0

    def reserve_seat(self):
        if self.capacity == 0:
            return True
        if self.available_seats is None:
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
        if self.capacity == 0:
            return
        if self.available_seats is None:
            self.available_seats = 0
        self.available_seats = min(self.capacity, self.available_seats + count)
        self.version += 1


# ============================================================================
# EVENT REGISTRATION MODEL
# ============================================================================

class EventRegistration(BaseModel):
    __tablename__ = "event_registrations"
    __table_args__ = (
        UniqueConstraint("registration_ref", name="uq_reg_ref"),
        UniqueConstraint("ticket_number", name="uq_ticket_number"),
        UniqueConstraint("qr_token", name="uq_qr_token"),
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

    PAYMENT_STATUS_FREE = 'free'
    PAYMENT_STATUS_PENDING = 'pending'
    PAYMENT_STATUS_PAID = 'paid'
    PAYMENT_STATUS_FAILED = 'failed'
    PAYMENT_STATUS_REFUNDED = 'refunded'
    PAYMENT_STATUS_EXPIRED = 'expired'

    STATUS_PENDING_PAYMENT = 'pending_payment'
    STATUS_CONFIRMED = 'confirmed'
    STATUS_CANCELLED = 'cancelled'
    STATUS_CHECKED_IN = 'checked_in'
    STATUS_NO_SHOW = 'no_show'
    STATUS_EXPIRED = 'expired'

    registration_ref = Column(String(60), unique=True, nullable=False, index=True)
    event_id = Column(BigInteger, ForeignKey("events.id", ondelete="RESTRICT"), nullable=False, index=True)
    event = relationship("Event", back_populates="registrations")
    ticket_type_id = Column(BigInteger, ForeignKey("event_ticket_types.id", ondelete="RESTRICT"), nullable=False)
    ticket_type_rel = relationship("TicketType", back_populates="registrations")
    user_id = Column(BigInteger, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    user = relationship("User", foreign_keys=[user_id])
    full_name = Column(String(255), nullable=False)
    email = Column(String(255), nullable=False)
    phone = Column(String(50))
    nationality = Column(String(64))
    id_number = Column(String(100))
    id_type = Column(String(30))
    ticket_type = Column(String(50), default="general", nullable=False)
    ticket_number = Column(String(50), unique=True, nullable=False)
    qr_token = Column(String(100), unique=True, nullable=False, index=True)
    registration_fee = Column(Numeric(10, 2), default=0)
    payment_status = Column(String(30), default="free")
    wallet_txn_id = Column(String(255), nullable=True)
    status = Column(String(30), default="confirmed", nullable=False, index=True)
    checked_in_at = Column(DateTime, nullable=True)
    checked_in_by_id = Column(BigInteger, ForeignKey("users.id"), nullable=True)
    checked_in_by = relationship("User", foreign_keys=[checked_in_by_id])
    discount_code_applied = Column(String(50), nullable=True)
    discount_amount = Column(Numeric(10, 2), default=0, nullable=False)
    registered_by = Column(String(30), default="self")
    notes = Column(Text, nullable=True)

    def generate_refs(self, event_slug: str, sequence: int):
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
        Index('idx_waitlist_notification', 'notification_sent', 'created_at'),
    )

    event_id = Column(BigInteger, ForeignKey("events.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    ticket_type_id = Column(BigInteger, ForeignKey("event_ticket_types.id", ondelete="CASCADE"), nullable=True)
    position = Column(Integer, nullable=False, default=1)
    status = Column(String(30), default="pending", nullable=False, index=True)
    email = Column(String(255), nullable=False)
    phone = Column(String(50), nullable=True)
    notes = Column(Text, nullable=True)
    notified_at = Column(DateTime, nullable=True)
    converted_at = Column(DateTime, nullable=True)
    notification_sent = Column(Boolean, default=False, nullable=False)
    conversion_attempts = Column(Integer, default=0, nullable=False)

    event = relationship("Event", backref="waitlist_entries")
    user = relationship("User", foreign_keys=[user_id])
    ticket_type = relationship("TicketType", foreign_keys=[ticket_type_id])

    def mark_notified(self):
        self.notified_at = datetime.utcnow()
        self.notification_sent = True

    def mark_converted(self):
        self.converted_at = datetime.utcnow()
        self.status = 'converted'

    def __repr__(self):
        return f"<Waitlist {self.event.slug}: {self.user_id} pos={self.position}>"


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
    organisation_id = Column(BigInteger, ForeignKey("organisations.id", ondelete="SET NULL"), nullable=True, index=True)
    permissions = Column(JSON, default=list)
    assigned_by_id = Column(BigInteger, ForeignKey("users.id"), nullable=True)
    assigned_at = Column(DateTime, default=func.now())
    is_active = Column(Boolean, default=True)

    event = relationship("Event", backref="staff_roles")
    user = relationship("User", foreign_keys=[user_id])
    organisation = relationship("Organisation", foreign_keys=[organisation_id])
    assigned_by = relationship("User", foreign_keys=[assigned_by_id])

    def __repr__(self):
        return f"<EventRole {self.event.slug}: {self.user.email} as {self.role}>"


# ============================================================================
# DISCOUNT CODE MODEL
# ============================================================================

class DiscountCode(BaseModel):
    __tablename__ = 'discount_codes'
    __table_args__ = (
        Index('idx_discount_code_event', 'event_id'),
        Index('idx_discount_code_active', 'is_active', 'valid_until'),
        UniqueConstraint('code', name='uq_discount_code'),
    )

    event_id = Column(BigInteger, ForeignKey('events.id', ondelete='CASCADE'), nullable=False, index=True)
    code = Column(String(50), nullable=False, unique=True, index=True)
    discount_type = Column(SAEnum(DiscountType, name="discounttype"), nullable=False)
    discount_value = Column(Numeric(10, 2), nullable=False)
    currency = Column(String(3), default='USD')
    valid_from = Column(DateTime, nullable=False, default=datetime.utcnow)
    valid_until = Column(DateTime, nullable=True)
    usage_limit = Column(Integer, nullable=True)
    used_count = Column(Integer, default=0, nullable=False)
    minimum_order = Column(Numeric(10, 2), default=0)
    is_active = Column(Boolean, default=True, nullable=False)
    created_by = Column(BigInteger, ForeignKey('users.id'), nullable=True)

    event = relationship('Event', backref='discount_codes')
    creator = relationship('User', foreign_keys=[created_by])

    def is_valid(self):
        now = datetime.utcnow()
        if not self.is_active:
            return False
        if now < self.valid_from:
            return False
        if self.valid_until and now > self.valid_until:
            return False
        if self.usage_limit and self.used_count >= self.usage_limit:
            return False
        return True

    def calculate_discount(self, amount):
        if self.discount_type == DiscountType.PERCENTAGE:
            return amount * (self.discount_value / 100)
        else:
            return min(self.discount_value, amount)


# ============================================================================
# EVENT TRANSFER REQUEST MODEL
# ============================================================================

class EventTransferRequest(BaseModel):
    __tablename__ = 'event_transfer_requests'
    __table_args__ = (
        Index('idx_transfer_event_status', 'event_id', 'status'),
        Index('idx_transfer_from_user', 'from_user_id'),
        Index('idx_transfer_to_org', 'to_organization_id'),
    )

    event_id = Column(BigInteger, ForeignKey('events.id', ondelete='CASCADE'), nullable=False)
    from_user_id = Column(BigInteger, ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    from_organization_id = Column(BigInteger, ForeignKey('organisations.id', ondelete='SET NULL'), nullable=True)
    to_user_id = Column(BigInteger, ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    to_organization_id = Column(BigInteger, ForeignKey('organisations.id', ondelete='SET NULL'), nullable=True)
    requested_by_id = Column(BigInteger, ForeignKey('users.id'), nullable=False)
    status = Column(SAEnum(TransferStatus, name="transferstatus"), nullable=False, default=TransferStatus.PENDING)
    reason = Column(Text, nullable=True)
    approved_by_id = Column(BigInteger, ForeignKey('users.id'), nullable=True)
    approved_at = Column(DateTime, nullable=True)
    expires_at = Column(DateTime, nullable=True)

    event = relationship('Event', foreign_keys=[event_id])
    from_user = relationship('User', foreign_keys=[from_user_id])
    from_organization = relationship('Organisation', foreign_keys=[from_organization_id])
    to_user = relationship('User', foreign_keys=[to_user_id])
    to_organization = relationship('Organisation', foreign_keys=[to_organization_id])
    requested_by = relationship('User', foreign_keys=[requested_by_id])
    approved_by = relationship('User', foreign_keys=[approved_by_id])

    def approve(self, approver_id: int):
        self.status = TransferStatus.APPROVED
        self.approved_by_id = approver_id
        self.approved_at = datetime.utcnow()

    def __repr__(self):
        return f"<EventTransferRequest {self.id}: event {self.event_id} status {self.status}>"


# ============================================================================
# EVENT TRANSFER LOG MODEL (FIXED - using OwnerType enum)
# ============================================================================

class EventTransferLog(BaseModel):
    __tablename__ = 'event_transfer_logs'

    event_id = Column(BigInteger, ForeignKey('events.id', ondelete='CASCADE'), nullable=False)
    from_owner_type = Column(SAEnum(OwnerType, name="ownertype"), nullable=False)
    from_owner_id = Column(BigInteger, nullable=False)
    to_owner_type = Column(SAEnum(OwnerType, name="ownertype"), nullable=False)
    to_owner_id = Column(BigInteger, nullable=False)
    transferred_by_id = Column(BigInteger, ForeignKey('users.id'), nullable=False)
    transferred_at = Column(DateTime, default=datetime.utcnow)
    extra_data = Column(JSON, default=dict)

    event = relationship('Event', foreign_keys=[event_id])
    transferred_by = relationship('User', foreign_keys=[transferred_by_id])

    def __repr__(self):
        return f"<EventTransferLog {self.id}: event {self.event_id} from {self.from_owner_type.value}:{self.from_owner_id} to {self.to_owner_type.value}:{self.to_owner_id}>"
