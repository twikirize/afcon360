# app/accommodation/models/booking.py
"""
Booking models - High-standard, using Python Enums with String DB storage
"""

from datetime import datetime, date, timedelta
from decimal import Decimal
from sqlalchemy import (
    Column, BigInteger, String, Boolean, DateTime, Date,
    ForeignKey, Integer, Text, Numeric, JSON,
    Index, UniqueConstraint, CheckConstraint
)
from sqlalchemy.orm import relationship, validates
from sqlalchemy.sql import func
from app.extensions import db
import secrets
import enum


# ==========================================
# Namespaced Enums for Booking (Python only)
# ==========================================

class AccommodationBookingStatus(enum.Enum):
    """Booking status - stored as string in DB"""
    PENDING = "pending"
    CONFIRMED = "confirmed"
    CHECKED_IN = "checked_in"
    CHECKED_OUT = "checked_out"
    CANCELLED = "cancelled"
    REFUNDED = "refunded"
    NO_SHOW = "no_show"


class AccommodationPaymentStatus(enum.Enum):
    """Payment status - stored as string in DB"""
    PENDING = "pending"
    PAID = "paid"
    FAILED = "failed"
    REFUNDED = "refunded"
    PARTIAL_REFUND = "partial_refund"


class AccommodationPaymentMethod(enum.Enum):
    """Payment method - stored as string in DB"""
    WALLET = "wallet"
    CARD = "card"
    MOBILE_MONEY = "mobile_money"
    BANK_TRANSFER = "bank_transfer"


class BookingContextType(enum.Enum):
    """Context type - stored as string in DB"""
    NONE = "none"
    EVENT = "event"
    TOUR = "tour"
    CORPORATE = "corporate"
    GROUP = "group"
    INDIVIDUAL = "individual"
    SPONSOR = "sponsor"
    ORGANIZER = "organizer"
    ASSIGNED = "assigned"


# ==========================================
# Booking Model
# ==========================================

class AccommodationBooking(db.Model):
    __tablename__ = "accommodation_bookings"
    __table_args__ = (
        UniqueConstraint("booking_reference", name="uq_booking_reference"),
        UniqueConstraint("idempotency_key", name="uq_booking_idempotency"),
        Index("idx_booking_property_dates", "property_id", "check_in", "check_out"),
        Index("idx_booking_guest_status", "guest_user_id", "status"),
        Index("idx_booking_status_created", "status", "created_at"),
        Index("idx_booking_dates", "check_in", "check_out"),
        Index("idx_booking_context", "context_type", "context_id"),  # ⚠️ This references context_type which is defined later
        CheckConstraint("check_out > check_in", name="ck_valid_dates"),
        CheckConstraint("num_guests >= 1", name="ck_guests_positive"),
        CheckConstraint("num_nights >= 1", name="ck_nights_positive"),
        CheckConstraint("total_amount >= 0", name="ck_total_amount_positive"),
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)

    # -------------------------------
    # Identifiers
    # -------------------------------
    booking_reference = Column(String(50), nullable=False, unique=True, index=True)
    idempotency_key = Column(String(64), unique=True, index=True, nullable=True)

    # -------------------------------
    # Relationships
    # -------------------------------
    property_id = Column(BigInteger, ForeignKey("accommodation_properties.id", ondelete="RESTRICT"), nullable=False, index=True)
    accommodation_property = relationship("Property", back_populates="bookings")

    guest_user_id = Column(BigInteger, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    guest = relationship("User", foreign_keys=[guest_user_id], backref="accommodation_bookings")

    host_user_id = Column(BigInteger, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    host = relationship("User", foreign_keys=[host_user_id])

    # -------------------------------
    # Booking Details
    # -------------------------------
    check_in = Column(Date, nullable=False)
    check_out = Column(Date, nullable=False)
    num_nights = Column(Integer, nullable=False)
    num_guests = Column(Integer, nullable=False, default=1)

    # -------------------------------
    # Pricing Snapshot
    # -------------------------------
    nightly_rate = Column(Numeric(10, 2), nullable=False)
    cleaning_fee = Column(Numeric(10, 2), default=0)
    service_fee = Column(Numeric(10, 2), default=0)
    taxes = Column(Numeric(10, 2), default=0)
    total_amount = Column(Numeric(10, 2), nullable=False)
    currency = Column(String(3), default="USD")

    # -------------------------------
    # Payment (String storage)
    # -------------------------------
    payment_method = Column(String(50), nullable=True)
    payment_status = Column(String(50), default=AccommodationPaymentStatus.PENDING.value, nullable=False)
    wallet_txn_id = Column(String(255), nullable=True)
    paid_at = Column(DateTime, nullable=True)

    # -------------------------------
    # Refund
    # -------------------------------
    refund_amount = Column(Numeric(10, 2), default=0)
    refunded_at = Column(DateTime, nullable=True)

    # -------------------------------
    # Booking Status (String storage)
    # -------------------------------
    status = Column(String(50), default=AccommodationBookingStatus.PENDING.value, nullable=False, index=True)

    # -------------------------------
    # Cancellation / Host Approval
    # -------------------------------
    cancelled_at = Column(DateTime, nullable=True)
    cancelled_by_user_id = Column(BigInteger, ForeignKey("users.id"), nullable=True)
    cancellation_reason = Column(Text, nullable=True)
    host_approved_at = Column(DateTime, nullable=True)
    host_rejected_at = Column(DateTime, nullable=True)
    host_rejection_reason = Column(Text, nullable=True)

    # -------------------------------
    # Guest Snapshot
    # -------------------------------
    guest_name = Column(String(255), nullable=False)
    guest_email = Column(String(255), nullable=False)
    guest_phone = Column(String(50), nullable=True)
    special_requests = Column(Text, nullable=True)
    host_message = Column(Text, nullable=True)

    # -------------------------------
    # Context Fields (String storage)
    # -------------------------------
    context_type = Column(String(50), default=BookingContextType.NONE.value, nullable=False, index=True)  # ✅ Has default
    context_id = Column(String(100), nullable=True, index=True)
    context_metadata = Column(JSON, default=dict)

    # -------------------------------
    # Check-in/out Tracking
    # -------------------------------
    checked_in_at = Column(DateTime, nullable=True)
    checked_out_at = Column(DateTime, nullable=True)

    # -------------------------------
    # Timestamps
    # -------------------------------
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    expires_at = Column(DateTime, nullable=True)

    # -------------------------------
    # Relationships (continued)
    # -------------------------------
    status_history = relationship("BookingStatusHistory", back_populates="booking", cascade="all, delete-orphan")
    review = relationship("Review", back_populates="booking", uselist=False)

    # ==========================================
    # PROPERTIES
    # ==========================================

    @property
    def listing(self):
        """Return the property listing (clear alias for accommodation_property)"""
        return self.accommodation_property

    @property
    def status_enum(self) -> AccommodationBookingStatus:
        """Get status as enum for type-safe operations"""
        return AccommodationBookingStatus(self.status)

    @property
    def payment_status_enum(self) -> AccommodationPaymentStatus:
        """Get payment status as enum"""
        return AccommodationPaymentStatus(self.payment_status)

    @property
    def context_type_enum(self) -> BookingContextType:
        """Get context type as enum"""
        return BookingContextType(self.context_type)

    # -------------------------------
    # Core Methods
    # -------------------------------
    def generate_reference(self):
        timestamp = datetime.utcnow().strftime("%Y%m%d%H%M")
        random_part = secrets.token_hex(4).upper()
        self.booking_reference = f"ACC-{timestamp}-{random_part}"

    def calculate_nights(self):
        self.num_nights = (self.check_out - self.check_in).days
        return self.num_nights

    def calculate_totals(self):
        self.num_nights = self.calculate_nights()
        self.total_amount = (self.nightly_rate * self.num_nights) + self.cleaning_fee + self.service_fee + self.taxes
        return self.total_amount

    def mark_paid(self, transaction_id=None):
        self.payment_status = AccommodationPaymentStatus.PAID.value
        self.paid_at = datetime.utcnow()
        self.wallet_txn_id = transaction_id

    def confirm(self):
        self.status = AccommodationBookingStatus.CONFIRMED.value

    def cancel(self, user_id, reason=None):
        can_cancel, msg, refund = self.can_cancel()
        if not can_cancel:
            return False, msg, 0

        self.status = AccommodationBookingStatus.CANCELLED.value
        self.cancelled_at = datetime.utcnow()
        self.cancelled_by_user_id = user_id
        self.cancellation_reason = reason

        if refund > 0:
            self.refund_amount = refund
            self.payment_status = AccommodationPaymentStatus.REFUNDED.value
            self.refunded_at = datetime.utcnow()

        return True, msg, refund

    def can_cancel(self):
        from app.accommodation.models.property import AccommodationCancellationPolicy

        current_status = self.status_enum

        if current_status not in [AccommodationBookingStatus.PENDING, AccommodationBookingStatus.CONFIRMED]:
            return False, "Cannot cancel at this stage", 0

        days_until = (self.check_in - datetime.utcnow().date()).days
        policy = self.accommodation_property.cancellation_policy

        if policy == AccommodationCancellationPolicy.FLEXIBLE:
            return True, "Full refund", self.total_amount
        elif policy == AccommodationCancellationPolicy.MODERATE:
            if days_until >= 5:
                return True, "Full refund", self.total_amount
            elif days_until >= 1:
                return True, "50% refund", self.total_amount * Decimal("0.5")
        elif policy == AccommodationCancellationPolicy.STRICT:
            if days_until >= 7:
                return True, "50% refund", self.total_amount * Decimal("0.5")
        return False, "Non-refundable", 0

    def is_available(self) -> bool:
        """Check if all dates in this booking are available"""
        from app.accommodation.models.availability import is_date_available

        current_date = self.check_in
        while current_date < self.check_out:
            if not is_date_available(self.property_id, current_date):
                return False
            current_date += timedelta(days=1)
        return True


# ==========================================
# Booking Status History
# ==========================================

class BookingStatusHistory(db.Model):
    __tablename__ = "accommodation_booking_history"
    __table_args__ = (
        Index("idx_history_booking", "booking_id"),
        Index("idx_history_timestamp", "changed_at"),
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    booking_id = Column(BigInteger, ForeignKey("accommodation_bookings.id", ondelete="CASCADE"), nullable=False, index=True)
    booking = relationship("AccommodationBooking", back_populates="status_history")

    from_status = Column(String(50), nullable=True)
    to_status = Column(String(50), nullable=False)
    changed_by_user_id = Column(BigInteger, ForeignKey("users.id"), nullable=True)
    reason = Column(Text, nullable=True)

    ip_address = Column(String(64), nullable=True)
    user_agent = Column(String(512), nullable=True)

    changed_at = Column(DateTime, default=func.now(), nullable=False)
    changed_by = relationship("User", foreign_keys=[changed_by_user_id])

    @property
    def from_status_enum(self) -> AccommodationBookingStatus:
        """Get from_status as enum"""
        return AccommodationBookingStatus(self.from_status) if self.from_status else None

    @property
    def to_status_enum(self) -> AccommodationBookingStatus:
        """Get to_status as enum"""
        return AccommodationBookingStatus(self.to_status) if self.from_status else None