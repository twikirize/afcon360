"""Capped, multi-use guest registration links."""

from datetime import datetime, timezone

from sqlalchemy import BigInteger, Boolean, Column, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import relationship

from app.extensions import db
from app.models.base import BaseModel


class BookingRegistrationLink(BaseModel):
    """One shareable, hash-backed registration link per booking."""

    __tablename__ = "accommodation_booking_registration_links"
    __table_args__ = (
        UniqueConstraint("booking_id", name="uq_registration_link_booking"),
        Index("idx_registration_link_token", "token_hash"),
    )

    booking_id = Column(
        BigInteger,
        ForeignKey(
            "accommodation_bookings.id",
            ondelete="CASCADE",
            name="fk_registration_link_booking",
        ),
        nullable=False,
    )
    booking = relationship("AccommodationBooking", back_populates="registration_link")
    token_hash = Column(String(64), nullable=False, unique=True, index=True)
    max_registrants = Column(Integer, nullable=False)
    is_active = Column(Boolean, default=True, server_default="true", nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    @property
    def registrants_count(self):
        from app.accommodation.models.guest_registration import GuestRegistration
        return GuestRegistration.query.filter_by(
            booking_id=self.booking_id, is_active=True
        ).count()

    @property
    def is_full(self):
        return self.registrants_count >= self.max_registrants

    @property
    def spots_remaining(self):
        return max(0, self.max_registrants - self.registrants_count)

    @property
    def is_expired(self):
        return bool(self.expires_at and datetime.now(timezone.utc) >= self.expires_at)