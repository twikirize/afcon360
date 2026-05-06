# app/admin/models/moderation.py
"""
Moderation-specific models to avoid circular imports
"""

from datetime import datetime, timezone, timedelta
from sqlalchemy import Column, BigInteger, Integer, String, Boolean, DateTime, JSON, ForeignKey, Text
from sqlalchemy.orm import relationship
from app.extensions import db
from app.models.base import BaseModel


class ContentSubmission(BaseModel):
    """
    Tracks user submissions for content approval
    """
    __tablename__ = "content_submissions"

    item_id = Column(BigInteger, ForeignKey("manageable_items.id"), nullable=True)
    category_id = Column(BigInteger, ForeignKey("manageable_categories.id"), nullable=False)

    # Submission data
    name = Column(String(200), nullable=False)
    data = Column(JSON, nullable=False, default=dict)

    # Status
    status = Column(String(20), default="pending")  # pending, approved, rejected, changes_requested
    reviewed_by = Column(BigInteger, ForeignKey("users.id"), nullable=True)
    review_notes = Column(Text, nullable=True)

    # Submitted by
    submitted_by = Column(BigInteger, ForeignKey("users.id"), nullable=False)
    submitted_by_org = Column(BigInteger, ForeignKey("organisations.id"), nullable=True)

    reviewed_at = Column(DateTime, nullable=True)

    # Phase 3: Claim / assignment fields
    assigned_to_id = Column(BigInteger, ForeignKey("users.id"), nullable=True)
    claimed_at = Column(DateTime, nullable=True)
    resolved_at = Column(DateTime, nullable=True)
    processing_time_seconds = Column(Integer, nullable=True)  # seconds

    # SLA tracking
    sla_due_at = Column(DateTime, nullable=True)  # When this submission should be reviewed by

    # Internal moderation notes (separate from review_notes which go to submitter)
    moderation_notes = Column(Text, nullable=True)

    # Relationships
    category = relationship("ManageableCategory")
    item = relationship("ManageableItem")
    submitter = relationship("User", foreign_keys=[submitted_by])
    reviewer = relationship("User", foreign_keys=[reviewed_by])
    assignee = relationship("User", foreign_keys=[assigned_to_id])
    organization = relationship("Organisation", foreign_keys=[submitted_by_org])
    moderation_logs = relationship("ModerationLog", back_populates="submission", cascade="all, delete-orphan")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Set SLA due time on creation (72 hours for standard submissions)
        if not self.sla_due_at:
            self.sla_due_at = datetime.now(timezone.utc) + timedelta(hours=72)

    def __repr__(self):
        return f"<ContentSubmission {self.name}>"


class ModerationLog(BaseModel):
    """
    Audit log for moderation actions (approve, reject, claim, etc.)
    """
    __tablename__ = "moderation_logs"

    id = Column(BigInteger, primary_key=True)
    submission_id = Column(BigInteger, ForeignKey("content_submissions.id"), nullable=False, index=True)
    moderator_id = Column(BigInteger, ForeignKey("users.id"), nullable=False, index=True)
    action = Column(String(20), nullable=False)  # approve | reject | claim
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)
    notes = Column(Text, nullable=True)

    # Relationships
    submission = relationship("ContentSubmission", back_populates="moderation_logs")
    moderator = relationship("User", foreign_keys=[moderator_id])

    def __repr__(self):
        return f"<ModerationLog {self.action} submission={self.submission_id} by moderator={self.moderator_id}>"
