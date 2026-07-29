# app/event_accommodation/models/visibility.py
"""
Event Visibility model - Controls property visibility permissions per event or channel.
"""

from sqlalchemy import Column, BigInteger, String, Boolean, ForeignKey, Index
from app.models.base import BaseModel
import uuid as uuid_lib

class EventVisibility(BaseModel):
    __tablename__ = "event_visibility"
    __table_args__ = (
        Index("idx_event_visibility_prop_event", "property_id", "event_id"),
    )

    public_id = Column(
        String(64), unique=True, nullable=False, index=True,
        default=lambda: str(uuid_lib.uuid4()),
    )
    property_id = Column(BigInteger, ForeignKey("accommodation_properties.id", ondelete="CASCADE"), nullable=False, index=True)
    event_id = Column(BigInteger, ForeignKey("events.id", ondelete="CASCADE"), nullable=True, index=True)  # NULL = global channel
    visible = Column(Boolean, default=True, nullable=False)
    discovered_by = Column(String(50), default="badge", nullable=False)  # badge, invitation, search
