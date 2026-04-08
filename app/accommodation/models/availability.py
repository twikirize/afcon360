# app/accommodation/models/availability.py
"""
Availability models - Property availability management
Includes blocked dates and recurring availability rules
"""

from datetime import date, timedelta  # FIX 1: added timedelta (was missing, caused NameError in all helper functions)
from sqlalchemy import (
    Column, BigInteger, String, Boolean, DateTime, Date,
    ForeignKey, Integer, Text,
    Index, UniqueConstraint, CheckConstraint
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.extensions import db
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

class BlockedDate(db.Model):
    """
    Individual blocked dates for a property.
    One row per blocked date - simple and queryable.
    """
    __tablename__ = "accommodation_blocked_dates"
    __table_args__ = (
        UniqueConstraint("property_id", "blocked_date", name="uq_property_blocked_date"),
        Index("idx_blocked_property_date", "property_id", "blocked_date"),
        Index("idx_blocked_booking", "booking_id"),
        # FIX 2: Removed CheckConstraint("blocked_date >= CURRENT_DATE") — enforcing this at the
        # DB level breaks `db upgrade` whenever historical blocked dates exist in the table.
        # Validate future-only dates in the service/API layer instead.
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)

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
    reason = Column(db.Enum(AccommodationBlockedReason), nullable=False)
    note = Column(Text, nullable=True)

    # -------------------------------
    # Timestamps
    # -------------------------------
    created_at = Column(DateTime, default=func.now())
    created_by = Column(BigInteger, ForeignKey("users.id"), nullable=True)

    def __repr__(self):
        return f"<BlockedDate property={self.property_id} date={self.blocked_date} reason={self.reason.value}>"

    def is_active(self):
        """Check if this blocked date is still in the future"""
        return self.blocked_date >= date.today()


# ==========================================
# Availability Rule Model (Recurring rules)
# ==========================================

class AvailabilityRule(db.Model):
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

    id = Column(BigInteger, primary_key=True, autoincrement=True)

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

    # -------------------------------
    # Timestamps
    # -------------------------------
    created_at = Column(DateTime, default=func.now())

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


# ==========================================
# Availability Service Helper Functions
# ==========================================

def is_date_available(property_id: int, check_date: date) -> bool:
    """
    Check if a specific date is available for a property.
    Returns True if available, False if blocked.
    """
    from app.accommodation.models.booking import AccommodationBookingStatus, Booking

    # Check for blocked dates
    blocked = BlockedDate.query.filter(
        BlockedDate.property_id == property_id,
        BlockedDate.blocked_date == check_date
    ).first()

    if blocked:
        return False

    # Check for confirmed bookings that cover this date
    booking = Booking.query.filter(
        Booking.property_id == property_id,
        Booking.status.in_([AccommodationBookingStatus.CONFIRMED, AccommodationBookingStatus.CHECKED_IN]),
        Booking.check_in <= check_date,
        Booking.check_out > check_date
    ).first()

    if booking:
        return False

    # Check recurring availability rules
    rules = AvailabilityRule.query.filter(
        AvailabilityRule.property_id == property_id
    ).all()

    for rule in rules:
        if rule.applies_to_date(check_date):
            return rule.is_available

    return True


def get_available_dates(
        property_id: int,
        start_date: date,
        end_date: date,
        exclude_booked: bool = True
) -> list[date]:
    """
    Get all available dates for a property within a date range.
    Returns a list of available dates.
    """
    from app.accommodation.models.booking import AccommodationBookingStatus, Booking

    available_dates = []
    current_date = start_date

    # Get all blocked dates
    blocked_dates = {bd.blocked_date for bd in BlockedDate.query.filter(
        BlockedDate.property_id == property_id,
        BlockedDate.blocked_date.between(start_date, end_date)
    ).all()}

    # Get all booked dates
    booked_dates = set()
    if exclude_booked:
        bookings = Booking.query.filter(
            Booking.property_id == property_id,
            Booking.status.in_([AccommodationBookingStatus.CONFIRMED, AccommodationBookingStatus.CHECKED_IN]),
            Booking.check_out > start_date,
            Booking.check_in < end_date
        ).all()

        for booking in bookings:
            booking_date = booking.check_in
            while booking_date < booking.check_out:
                if start_date <= booking_date <= end_date:
                    booked_dates.add(booking_date)
                booking_date += timedelta(days=1)

    # Get availability rules
    rules = AvailabilityRule.query.filter(
        AvailabilityRule.property_id == property_id
    ).all()

    while current_date <= end_date:
        is_available = True

        # Check blocked dates
        if current_date in blocked_dates:
            is_available = False

        # Check booked dates
        elif current_date in booked_dates:
            is_available = False

        # Check rules
        else:
            for rule in rules:
                if rule.applies_to_date(current_date):
                    is_available = rule.is_available
                    break

        if is_available:
            available_dates.append(current_date)

        current_date += timedelta(days=1)

    return available_dates


def block_dates(
        property_id: int,
        start_date: date,
        end_date: date,
        reason: AccommodationBlockedReason,
        booking_id: int = None,
        created_by: int = None
) -> int:
    """
    Block a range of dates for a property.
    Returns the number of dates blocked.
    """
    blocked_count = 0
    current_date = start_date

    while current_date <= end_date:
        # Check if already blocked
        existing = BlockedDate.query.filter(
            BlockedDate.property_id == property_id,
            BlockedDate.blocked_date == current_date
        ).first()

        if not existing:
            blocked = BlockedDate(
                property_id=property_id,
                blocked_date=current_date,
                reason=reason,
                booking_id=booking_id,
                created_by=created_by
            )
            db.session.add(blocked)
            blocked_count += 1

        current_date += timedelta(days=1)

    db.session.commit()
    return blocked_count


def unblock_dates(property_id: int, start_date: date, end_date: date) -> int:
    """
    Unblock a range of dates for a property.
    Returns the number of dates unblocked.
    """
    result = BlockedDate.query.filter(
        BlockedDate.property_id == property_id,
        BlockedDate.blocked_date.between(start_date, end_date),
        BlockedDate.reason != AccommodationBlockedReason.BOOKED
    ).delete(synchronize_session=False)

    db.session.commit()
    return result
