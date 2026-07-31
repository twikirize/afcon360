# app/accommodation/models/availability.py
"""
Availability models - Property availability management
Includes blocked dates and recurring availability rules
"""

from datetime import date, datetime, timedelta, timezone
from sqlalchemy import (
    Column, BigInteger, String, Boolean, DateTime, Date,
    ForeignKey, Integer, Text,
    Index, UniqueConstraint, CheckConstraint
)
from sqlalchemy.orm import relationship, validates
from sqlalchemy.sql import func
from app.extensions import db
from app.models.base import BaseModel
import enum


# ==========================================
# Namespaced Enum for Blocked Reason
# ==========================================

# Add TEMPORARY_HOLD to the enum
class AccommodationBlockedReason(enum.Enum):
    """Blocked reason - matches DB enum 'accommodation_blockedreason'"""
    BOOKED = "booked"
    TEMPORARY_HOLD = "temporary_hold"
    OWNER_BLOCKED = "owner_blocked"
    MAINTENANCE = "maintenance"
    SEASONAL = "seasonal"


# ==========================================
# Blocked Date Model (Individual blocked dates)
# ==========================================

class BlockedDate(BaseModel):
    """
    Individual blocked dates for a property.
    One row per blocked date - simple and queryable.
    """
    __tablename__ = "accommodation_blocked_dates"
    __table_args__ = (
        UniqueConstraint("property_id", "blocked_date", name="uq_property_blocked_date"),
        Index("idx_blocked_property_date", "property_id", "blocked_date"),
        Index("idx_blocked_booking", "booking_id"),
        # FIX 2: Removed CheckConstraint("blocked_date >= CURRENT_DATE") - enforcing this at the
        # DB level breaks `db upgrade` whenever historical blocked dates exist in the table.
        # Validate future-only dates in the service/API layer instead.
        CheckConstraint(
            "reason IN ('booked', 'temporary_hold', 'owner_blocked', 'maintenance', 'seasonal')",
            name="ck_blocked_reason_valid"
        ),
    )

    # -------------------------------
    # Relationships
    # -------------------------------
    property_id = Column(BigInteger, ForeignKey("accommodation_properties.id", ondelete="CASCADE"), nullable=False,
                         index=True)
    property = relationship("Property", back_populates="blocked_dates")

    booking_id = Column(BigInteger, ForeignKey("accommodation_bookings.id", ondelete="SET NULL"), nullable=True)
    booking = relationship("AccommodationBooking")

    # -------------------------------
    # Blocked Date Details
    # -------------------------------
    blocked_date = Column(Date, nullable=False)
    reason = Column(String(50), nullable=False)
    note = Column(Text, nullable=True)

    # -------------------------------
    # Timestamps
    # -------------------------------
    created_by = Column(BigInteger, ForeignKey("users.id"), nullable=True)

    @validates('reason')
    def validate_reason(self, key, value):
        if isinstance(value, enum.Enum):
            return value.value
        return value

    def __repr__(self):
        return f"<BlockedDate property={self.property_id} date={self.blocked_date} reason={self.reason}>"

    def is_active(self):
        """Check if this blocked date is still in the future"""
        return self.blocked_date >= date.today()


class RoomHold(BaseModel):
    """
    Short-lived inventory hold used during checkout.

    Holds are intentionally separate from bookings so inventory can be reserved
    before payment/approval and released safely when the checkout timer expires.
    """
    __tablename__ = "accommodation_room_holds"
    __table_args__ = (
        Index("idx_room_hold_property_dates", "property_id", "check_in", "check_out"),
        Index("idx_room_hold_room_type_dates", "room_type_id", "check_in", "check_out"),
        Index("idx_room_hold_expires", "status", "expires_at"),
        CheckConstraint("check_out > check_in", name="ck_room_hold_dates_valid"),
        CheckConstraint("hold_minutes > 0", name="ck_room_hold_minutes_positive"),
        CheckConstraint("status IN ('active', 'released', 'expired', 'converted')", name="ck_room_hold_status_valid"),
    )

    property_id = Column(BigInteger, ForeignKey("accommodation_properties.id", ondelete="CASCADE"), nullable=False, index=True)
    room_type_id = Column(BigInteger, ForeignKey("accommodation_room_types.id", ondelete="SET NULL"), nullable=True, index=True)
    booking_id = Column(BigInteger, ForeignKey("accommodation_bookings.id", ondelete="SET NULL"), nullable=True, index=True)
    guest_user_id = Column(BigInteger, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)

    check_in = Column(Date, nullable=False)
    check_out = Column(Date, nullable=False)
    units = Column(Integer, nullable=False, default=1)
    hold_minutes = Column(Integer, nullable=False, default=15)
    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)
    status = Column(String(20), nullable=False, default="active", index=True)
    release_reason = Column(Text, nullable=True)

    property = relationship("Property")
    room_type = relationship("RoomType")
    booking = relationship("AccommodationBooking")

    @property
    def is_expired_flag(self) -> bool:
        expires_at = self.expires_at
        if expires_at and expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        return self.status == "active" and expires_at <= datetime.now(timezone.utc)

    def mark_released(self, reason: str = None):
        self.status = "released"
        self.release_reason = reason

    def mark_expired(self):
        self.status = "expired"
        self.release_reason = "Hold expired"

    def mark_converted(self, booking_id: int):
        self.status = "converted"
        self.booking_id = booking_id
        self.release_reason = "Converted to booking"


# ==========================================
# Availability Rule Model (Recurring rules)
# ==========================================

class AvailabilityRule(BaseModel):
    """
    Recurring availability rules (e.g., closed on Sundays, seasonal closures)
    """
    __tablename__ = "accommodation_availability_rules"
    __table_args__ = (
        Index("idx_rule_property", "property_id"),
        Index("idx_rule_dates", "start_date", "end_date"),
        CheckConstraint("end_date >= start_date", name="ck_rule_dates_valid"),
        CheckConstraint("day_of_week BETWEEN 0 AND 6", name="ck_day_of_week_valid"),
    )

    # -------------------------------
    # Relationships
    # -------------------------------
    property_id = Column(BigInteger, ForeignKey("accommodation_properties.id", ondelete="CASCADE"), nullable=False,
                         index=True)
    property = relationship("Property", back_populates="availability_rules")

    # -------------------------------
    # Rule Definition
    # -------------------------------
    # Either day_of_week OR date range, not both
    day_of_week = Column(Integer, nullable=True)  # 0-6 (Monday=0, Sunday=6)
    start_date = Column(Date, nullable=True)
    end_date = Column(Date, nullable=True)

    is_available = Column(Boolean, default=True)  # False = blocked
    reason = Column(Text, nullable=True)

    def __repr__(self):
        if self.day_of_week is not None:
            days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
            return f"<AvailabilityRule property={self.property_id} day={days[self.day_of_week]} available={self.is_available}>"
        return f"<AvailabilityRule property={self.property_id} dates={self.start_date}-{self.end_date} available={self.is_available}>"

    def is_active_today(self):
        """Check if this rule applies to today's date"""
        today = date.today()
        if self.day_of_week is not None:
            return self.day_of_week == today.weekday()
        if self.start_date and self.end_date:
            return self.start_date <= today <= self.end_date
        return False

    def applies_to_date(self, check_date: date):
        """Check if this rule applies to a specific date"""
        if self.day_of_week is not None:
            return self.day_of_week == check_date.weekday()
        if self.start_date and self.end_date:
            return self.start_date <= check_date <= self.end_date
        return False
