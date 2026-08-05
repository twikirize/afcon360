# app/event_accommodation/models/opportunity.py
"""
Event Accommodation Opportunity model - Represents accommodation demand created by event organisers.
"""

from sqlalchemy import Column, BigInteger, String, Text, Integer, DateTime, ForeignKey, JSON, CheckConstraint, Index
from app.models.base import BaseModel
import uuid as uuid_lib

class EventAccommodationOpportunity(BaseModel):
    __tablename__ = "event_accommodation_opportunities"
    __table_args__ = (
        Index("idx_opportunity_event", "event_id"),
        Index("idx_opportunity_status", "status"),
        CheckConstraint(
            "status IN ('draft', 'active', 'closed')",
            name="ck_opportunity_status_valid"
        ),
    )

    public_id = Column(
        String(64), unique=True, nullable=False, index=True,
        default=lambda: str(uuid_lib.uuid4()),
    )
    event_id = Column(BigInteger, ForeignKey("events.id", ondelete="CASCADE"), nullable=False)
    created_by_id = Column(BigInteger, ForeignKey("users.id"), nullable=False)
    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    required_beds = Column(Integer, nullable=True)
    location = Column(String(100), nullable=True)
    start_date = Column(DateTime(timezone=True), nullable=True)
    end_date = Column(DateTime(timezone=True), nullable=True)
    accepted_property_types = Column(JSON, nullable=True)
    accepted_host_types = Column(JSON, nullable=True)
    status = Column(String(30), nullable=False, default="draft")
