"""Centralized, host-actionable special requests for accommodation bookings."""

from datetime import datetime, timezone

from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import relationship

from app.extensions import db
from app.models.base import BaseModel


class BookingSpecialRequest(BaseModel):
    """A single request from any supported booking touchpoint."""

    __tablename__ = "accommodation_booking_special_requests"
    __table_args__ = (
        Index("idx_special_request_booking", "booking_id"),
        Index("idx_special_request_status", "status"),
    )

    booking_id = Column(
        BigInteger,
        ForeignKey(
            "accommodation_bookings.id",
            ondelete="CASCADE",
            name="fk_special_request_booking",
        ),
        nullable=False,
    )
    booking = relationship("AccommodationBooking", back_populates="special_requests_list")

    guest_registration_id = Column(
        BigInteger,
        ForeignKey(
            "accommodation_guest_registrations.id",
            ondelete="SET NULL",
            name="fk_special_request_guest_registration",
        ),
        nullable=True,
    )
    requested_by_user_id = Column(
        BigInteger,
        ForeignKey("users.id", name="fk_special_request_requested_by_user"),
        nullable=True,
    )
    request_type = Column(String(50), nullable=True)
    request_text = Column(Text, nullable=False)
    source = Column(String(30), nullable=False)
    status = Column(String(20), nullable=False, default="pending", server_default="pending")
    host_response_note = Column(Text, nullable=True)
    responded_by_user_id = Column(
        BigInteger,
        ForeignKey("users.id", name="fk_special_request_responded_by_user"),
        nullable=True,
    )
    responded_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )