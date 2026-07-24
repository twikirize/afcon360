"""
Booking Commission Model - Platform revenue tracking.

Stores the financial breakdown for each booking:
- Total amount paid by guest
- Platform commission
- Host payout (after commission)
- Status: held → released / refunded
"""

from decimal import Decimal
from datetime import datetime, timezone
from sqlalchemy import (
    Column, BigInteger, String, Numeric, DateTime,
    ForeignKey, Index, UniqueConstraint
)
from sqlalchemy.orm import relationship
from app.extensions import db
from app.models.base import BaseModel


class BookingCommission(BaseModel):
    """
    Tracks platform commission for each accommodation booking.
    One record per booking — created when guest pays, updated on payout/refund.
    """
    __tablename__ = "accommodation_booking_commissions"
    __table_args__ = (
        Index("idx_commission_booking", "booking_id"),
        Index("idx_commission_status", "status"),
        UniqueConstraint("booking_id", name="uq_commission_booking"),
    )

    booking_id = Column(
        BigInteger,
        ForeignKey("accommodation_bookings.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True
    )
    booking = relationship("AccommodationBooking", back_populates="commission")

    # ── Financial breakdown ──
    total_amount = Column(Numeric(10, 2), nullable=False)
    commission_amount = Column(Numeric(10, 2), nullable=False)
    host_payout = Column(Numeric(10, 2), nullable=False)
    platform_fee_pct = Column(Numeric(5, 2), nullable=False)

    # ── Status flow: pending → held → released / refunded ──
    status = Column(String(30), default='pending', nullable=False)

    # ── Payout tracking ──
    host_payout_transaction_id = Column(String(100), nullable=True)
    released_at = Column(DateTime(timezone=True), nullable=True)
    released_by = Column(BigInteger, ForeignKey("users.id"), nullable=True)

    # ── Refund tracking ──
    refund_amount = Column(Numeric(10, 2), default=0)
    refunded_at = Column(DateTime(timezone=True), nullable=True)

    # ── Metadata ──
    extra_data = Column(db.JSON, default=dict)

    def __repr__(self):
        return f"<BookingCommission booking={self.booking_id} status={self.status}>"
