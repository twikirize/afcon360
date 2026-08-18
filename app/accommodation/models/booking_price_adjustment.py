"""
Booking Price Adjustment Model - Tracks price changes from date modifications,
early check-outs, and late check-ins.

Each adjustment records the old and new dates, the price delta, and the reason.
"""

import enum
from datetime import date
from decimal import Decimal
from sqlalchemy import (
    Column, BigInteger, String, Boolean, DateTime, Date,
    ForeignKey, Integer, Text, Numeric, JSON,
    Index, CheckConstraint,
)
from sqlalchemy.orm import relationship
from app.extensions import db
from app.models.base import BaseModel


class PriceAdjustmentType(enum.Enum):
    """Types of price adjustments, stored as String in DB."""
    DATE_MODIFICATION = "date_modification"
    EARLY_CHECKOUT = "early_checkout"
    LATE_CHECKIN = "late_checkin"


class BookingPriceAdjustment(BaseModel):
    """
    Record of a price/dates change for a booking.

    Created whenever a host modifies booking dates (via the modify-dates
    flow or the check-in/check-out adjust-date flows). Captures a full
    before/after snapshot so the price delta is fully auditable.
    """
    __tablename__ = "accommodation_booking_price_adjustments"
    __table_args__ = (
        Index("idx_price_adj_booking", "booking_id"),
        Index("idx_price_adj_created", "created_at"),
        Index("idx_price_adj_type", "adjustment_type"),
        CheckConstraint(
            "adjustment_type IN ('date_modification', 'early_checkout', 'late_checkin')",
            name="ck_price_adj_type_valid",
        ),
        CheckConstraint("new_num_nights >= 0", name="ck_price_adj_new_nights_positive"),
    )

    # -------------------------------
    # Relationships
    # -------------------------------
    booking_id = Column(
        BigInteger,
        ForeignKey("accommodation_bookings.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    booking = relationship("AccommodationBooking", backref="price_adjustments")

    # -------------------------------
    # Adjustment Details
    # -------------------------------
    adjustment_type = Column(String(50), nullable=False)

    # Date snapshot (before/after)
    old_check_in = Column(Date, nullable=True)
    old_check_out = Column(Date, nullable=True)
    new_check_in = Column(Date, nullable=True)
    new_check_out = Column(Date, nullable=True)

    old_num_nights = Column(Integer, nullable=True)
    new_num_nights = Column(Integer, nullable=False, default=0)

    # Pricing snapshot (before/after)
    old_total_amount = Column(Numeric(10, 2), nullable=True)
    new_total_amount = Column(Numeric(10, 2), nullable=True)
    old_nightly_rate = Column(Numeric(10, 2), nullable=True)

    # delta_amount: positive => guest owes more, negative => guest gets refund
    delta_amount = Column(Numeric(10, 2), nullable=False, default=0)

    old_amount_paid = Column(Numeric(10, 2), nullable=True)
    new_amount_due = Column(Numeric(10, 2), nullable=True)
    refund_amount = Column(Numeric(10, 2), default=0)

    # -------------------------------
    # Metadata
    # -------------------------------
    reason = Column(Text, nullable=True)
    notify_guest = Column(Boolean, default=False, nullable=False)
    payment_processed = Column(Boolean, default=False, nullable=False)

    # Who made the change (host_id or admin_id — internal BigInteger FK)
    changed_by_user_id = Column(BigInteger, ForeignKey("users.id"), nullable=True)
    changed_by_user = relationship("User", foreign_keys=[changed_by_user_id])

    # Extra context (e.g. cancellation policy details, idempotency info)
    adjustment_metadata = Column(JSON, default=dict)
