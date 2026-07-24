"""
Guest Profile model – stores guest preferences, loyalty points, and special requests history.
"""

from datetime import datetime, timezone
from decimal import Decimal
from sqlalchemy import (
    Column, BigInteger, String, Boolean, DateTime, Date,
    ForeignKey, Integer, Text, Numeric, JSON,
    Index, UniqueConstraint
)
from sqlalchemy.orm import relationship, validates
from app.extensions import db
from app.models.base import BaseModel


class GuestProfile(BaseModel):
    """
    Extended profile for accommodation guests.
    One-to-one with User (guest_user_id).
    """
    __tablename__ = "accommodation_guest_profiles"
    __table_args__ = (
        UniqueConstraint("guest_user_id", name="uq_guest_profile_user"),
        Index("idx_guest_profile_user", "guest_user_id"),
    )

    # -------------------------------
    # Identifiers
    # -------------------------------
    guest_user_id = Column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    guest = relationship("User", foreign_keys=[guest_user_id], backref="accommodation_guest_profile")

    # -------------------------------
    # Preferences
    # -------------------------------
    preferred_currency = Column(String(3), default="USD")
    preferred_language = Column(String(10), default="en")
    special_requests_template = Column(Text, nullable=True)  # e.g., "extra pillows, late check-in"
    dietary_restrictions = Column(Text, nullable=True)
    accessibility_needs = Column(Text, nullable=True)

    # -------------------------------
    # Loyalty / Points
    # -------------------------------
    loyalty_points = Column(Integer, default=0, nullable=False)
    total_stays = Column(Integer, default=0, nullable=False)
    total_spent = Column(Numeric(12, 2), default=Decimal("0.00"), nullable=False)
    last_stay_date = Column(Date, nullable=True)

    # -------------------------------
    # Communication preferences
    # -------------------------------
    marketing_opt_in = Column(Boolean, default=False, nullable=False)
    sms_notifications = Column(Boolean, default=True, nullable=False)
    email_notifications = Column(Boolean, default=True, nullable=False)

    # -------------------------------
    # Internal notes (host/admin only)
    # -------------------------------
    internal_notes = Column(Text, nullable=True)

    # -------------------------------
    # Timestamps
    # -------------------------------
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    # -------------------------------
    # Methods
    # -------------------------------
    def add_stay(self, nights: int, amount: Decimal):
        """Increment loyalty points and totals after a completed stay."""
        self.total_stays += 1
        self.total_spent = Decimal(str(self.total_spent or 0)) + amount
        self.loyalty_points += nights * 10  # 10 points per night
        self.last_stay_date = datetime.now(timezone.utc).date()

    def __repr__(self):
        return f"<GuestProfile user_id={self.guest_user_id} points={self.loyalty_points}>"
