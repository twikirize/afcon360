# app/event_accommodation/models/badge.py
"""
Event Badge model - Represents temporary or event-specific participation credentials for properties.
"""

from sqlalchemy import Column, BigInteger, String, DateTime, ForeignKey, CheckConstraint, Index
from app.models.base import BaseModel
import uuid as uuid_lib

class EventBadge(BaseModel):
    __tablename__ = "event_badges"
    __table_args__ = (
        Index("idx_badge_event_property", "event_id", "property_id"),
        Index("idx_badge_status", "status"),
        CheckConstraint(
            "badge_type IN ('community_host', 'event_partner', 'vip_host', 'volunteer_host', 'organiser_selected')",
            name="ck_badge_type_valid"
        ),
        CheckConstraint(
            "status IN ('requested', 'invited', 'accepted', 'active', 'expired', 'revoked')",
            name="ck_badge_status_valid"
        ),
    )

    public_id = Column(
        String(64), unique=True, nullable=False, index=True,
        default=lambda: str(uuid_lib.uuid4()),
    )
    event_id = Column(BigInteger, ForeignKey("events.id", ondelete="CASCADE"), nullable=False)
    property_id = Column(BigInteger, ForeignKey("accommodation_properties.id", ondelete="CASCADE"), nullable=False)
    badge_type = Column(String(50), nullable=False, default="community_host")
    visibility = Column(String(50), nullable=False, default="event_guests")  # event_guests, public, private
    approval_status = Column(String(30), nullable=False, default="pending")  # pending, approved, rejected
    approved_by = Column(BigInteger, ForeignKey("users.id"), nullable=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)
    starts_at = Column(DateTime(timezone=True), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    status = Column(String(30), nullable=False, default="requested")
