# app/accommodation/models/feedback.py
"""
Guest feedback models - complaints and booking amendments.

These power the guest dashboard "Raise a complaint" and "Amend booking"
capabilities. Both inherit from BaseModel (soft-delete + timestamps) and use
String columns with application-level CHECK constraints instead of PostgreSQL
ENUM types (per the scalability roadmap).
"""

import enum
import uuid
from datetime import datetime, timezone, date

from sqlalchemy import (
    Column, BigInteger, String, Boolean, DateTime, Date,
    ForeignKey, Integer, Text, Numeric, JSON,
    Index, UniqueConstraint, CheckConstraint,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.extensions import db
from app.models.base import BaseModel


# ==========================================
# Namespaced Enums (Python only, String storage)
# ==========================================

class ComplaintCategory(enum.Enum):
    CLEANLINESS = "cleanliness"
    SAFETY = "safety"
    BILLING = "billing"
    HOST = "host"
    FACILITY = "facility"
    BOOKING = "booking"
    OTHER = "other"


class ComplaintStatus(enum.Enum):
    OPEN = "open"
    IN_REVIEW = "in_review"
    ESCALATED = "escalated"
    RESOLVED = "resolved"
    CLOSED = "closed"


class ComplaintPriority(enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


class AmendmentType(enum.Enum):
    DATES = "dates"
    GUESTS = "guests"
    SPECIAL_REQUESTS = "special_requests"
    OTHER = "other"


class AmendmentStatus(enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


# ==========================================
# Complaint Model
# ==========================================

class AccommodationComplaint(BaseModel):
    __tablename__ = "accommodation_complaints"
    __table_args__ = (
        Index("idx_complaint_user", "user_id"),
        Index("idx_complaint_booking", "booking_id"),
        Index("idx_complaint_property", "property_id"),
        Index("idx_complaint_status", "status"),
        CheckConstraint(
            "category IN ('cleanliness','safety','billing','host','facility','booking','other')",
            name="ck_complaint_category_valid",
        ),
        CheckConstraint(
            "status IN ('open','in_review','escalated','resolved','closed')",
            name="ck_complaint_status_valid",
        ),
        CheckConstraint(
            "priority IN ('low','medium','high','urgent')",
            name="ck_complaint_priority_valid",
        ),
    )

    public_id = Column(String(64), unique=True, nullable=False, default=lambda: str(uuid.uuid4()))
    reference = Column(String(50), unique=True, nullable=False)

    # Who raised it
    user_id = Column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    user = relationship("User", foreign_keys=[user_id])

    # Context (at least one of booking/property should be present)
    booking_id = Column(BigInteger, ForeignKey("accommodation_bookings.id", ondelete="CASCADE"), nullable=True, index=True)
    booking = relationship("AccommodationBooking", foreign_keys=[booking_id])

    property_id = Column(BigInteger, ForeignKey("accommodation_properties.id", ondelete="CASCADE"), nullable=True, index=True)
    related_property = relationship("Property", foreign_keys=[property_id])

    host_user_id = Column(BigInteger, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    category = Column(String(30), nullable=False, default=ComplaintCategory.OTHER.value)
    subject = Column(String(255), nullable=False)
    description = Column(Text, nullable=False)

    status = Column(String(30), nullable=False, default=ComplaintStatus.OPEN.value)
    priority = Column(String(30), nullable=False, default=ComplaintPriority.MEDIUM.value)

    resolution = Column(Text, nullable=True)
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    assigned_to_user_id = Column(BigInteger, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    def generate_reference(self):
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M")
        random_part = uuid.uuid4().hex[:6].upper()
        self.reference = f"CMP-{timestamp}-{random_part}"

    @property
    def status_enum(self):
        return ComplaintStatus(self.status)

    @property
    def priority_enum(self):
        return ComplaintPriority(self.priority)

    @property
    def category_enum(self):
        return ComplaintCategory(self.category)


# ==========================================
# Booking Amendment Model
# ==========================================

class AccommodationBookingAmendment(BaseModel):
    __tablename__ = "accommodation_booking_amendments"
    __table_args__ = (
        Index("idx_amendment_booking", "booking_id"),
        Index("idx_amendment_status", "status"),
        Index("idx_amendment_requested_by", "requested_by_user_id"),
        CheckConstraint(
            "amendment_type IN ('dates','guests','special_requests','other')",
            name="ck_amendment_type_valid",
        ),
        CheckConstraint(
            "status IN ('pending','approved','rejected','cancelled')",
            name="ck_amendment_status_valid",
        ),
    )

    public_id = Column(String(64), unique=True, nullable=False, default=lambda: str(uuid.uuid4()))

    booking_id = Column(BigInteger, ForeignKey("accommodation_bookings.id", ondelete="CASCADE"), nullable=False, index=True)

    requested_by_user_id = Column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    requested_by = relationship("User", foreign_keys=[requested_by_user_id])

    amendment_type = Column(String(30), nullable=False, default=AmendmentType.OTHER.value)

    # Dates (nullable; only set when amendment_type == dates)
    current_check_in = Column(Date, nullable=True)
    current_check_out = Column(Date, nullable=True)
    requested_check_in = Column(Date, nullable=True)
    requested_check_out = Column(Date, nullable=True)

    # Guests (nullable; only set when amendment_type == guests)
    current_guests = Column(Integer, nullable=True)
    requested_guests = Column(Integer, nullable=True)

    # Special requests / other notes (free text the guest wants changed)
    requested_special_requests = Column(Text, nullable=True)

    reason = Column(Text, nullable=True)

    status = Column(String(30), nullable=False, default=AmendmentStatus.PENDING.value)
    host_response = Column(Text, nullable=True)
    responded_at = Column(DateTime(timezone=True), nullable=True)
    responded_by_user_id = Column(BigInteger, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    @property
    def status_enum(self):
        return AmendmentStatus(self.status)

    @property
    def amendment_type_enum(self):
        return AmendmentType(self.amendment_type)
