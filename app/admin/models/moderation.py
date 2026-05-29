# app/admin/models/moderation.py
"""
Moderation-specific models to avoid circular imports
"""

from datetime import datetime, timezone, timedelta
from sqlalchemy import Column, BigInteger, Integer, String, Boolean, DateTime, JSON, ForeignKey, Text, Float
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


class ContentFlag(BaseModel):
    """
    Enterprise-grade content flagging system
    Supports AI detection, human review, and escalation workflows
    """
    __tablename__ = "content_flags"

    # Core identification
    id = Column(BigInteger, primary_key=True)
    entity_type = Column(String(50), nullable=False, index=True)  # user, content_submission, manageable_item, etc.
    entity_id = Column(BigInteger, nullable=False, index=True)
    
    # Content analysis for enterprise moderation
    content_hash = Column(String(64), nullable=True, index=True)  # For duplicate detection
    content_type = Column(String(50), nullable=False, index=True)  # post, comment, listing, profile, etc.
    risk_score = Column(Float, default=0.0, index=True)  # AI-calculated risk score (0-100)
    category = Column(String(50), nullable=False, index=True)  # spam, hate, violence, fraud, etc.
    severity = Column(String(20), default="medium")  # low, medium, high, critical
    
    # Flag details
    reason = Column(Text, nullable=False)
    priority = Column(String(20), default="normal", index=True)  # low, normal, medium, high, critical
    status = Column(String(20), default="open", index=True)  # open, in_review, resolved, escalated, closed
    
    # AI detection and automation
    detection_source = Column(String(50), default="human")  # ai, human, hybrid, automated
    ai_confidence = Column(Float, nullable=True)  # AI model confidence score (0-1)
    detection_model = Column(String(100), nullable=True)  # AI model version
    auto_processed = Column(Boolean, default=False)  # If handled by AI automatically
    
    # Enterprise workflow management
    moderation_level = Column(String(20), default="level_1")  # level_1, level_2, level_3
    assigned_to = Column(BigInteger, ForeignKey("users.id"), nullable=True, index=True)
    assigned_team = Column(String(50), nullable=True)  # trust_safety, content_quality, fraud, etc.
    
    # Escalation tracking (enterprise feature)
    escalated_from_level = Column(String(20), nullable=True)
    escalated_to_level = Column(String(20), nullable=True)
    escalation_reason = Column(Text, nullable=True)
    escalation_count = Column(Integer, default=0)
    escalation_priority = Column(String(20), nullable=True)  # urgent, high, normal
    
    # Resolution tracking
    resolved_by = Column(BigInteger, ForeignKey("users.id"), nullable=True)
    resolved_at = Column(DateTime, nullable=True)
    resolution_action = Column(String(50), nullable=True)  # approved, rejected, suspended, banned, etc.
    resolution_notes = Column(Text, nullable=True)
    appeal_count = Column(Integer, default=0)
    final_resolution = Column(Boolean, default=False)
    
    # SLA tracking (enterprise feature)
    sla_due_at = Column(DateTime, nullable=False, index=True)
    sla_breached = Column(Boolean, default=False)
    sla_priority = Column(String(20), default="normal")  # immediate, urgent, normal, low
    processing_time_seconds = Column(Integer, nullable=True)
    
    # Quality and performance metrics (enterprise feature)
    reviewer_quality_score = Column(Float, nullable=True)  # Peer review of moderator quality
    user_satisfaction_score = Column(Float, nullable=True)  # Post-resolution feedback
    accuracy_score = Column(Float, nullable=True)  # Decision accuracy based on appeals
    
    # Compliance and legal (enterprise feature)
    legal_review_required = Column(Boolean, default=False)
    legal_review_completed = Column(Boolean, default=False)
    legal_review_by = Column(BigInteger, ForeignKey("users.id"), nullable=True)
    compliance_case_id = Column(BigInteger, nullable=True)
    reported_to_authorities = Column(Boolean, default=False)
    
    # Geographic and language (enterprise feature)
    country_code = Column(String(2), nullable=True)  # ISO country code
    language_code = Column(String(5), nullable=True)  # ISO language code
    regional_policy_applied = Column(Boolean, default=False)
    
    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    extra_data = Column(JSON, default=dict)  # Additional context, evidence, etc.

    # Legacy fields for compatibility
    flagged_by = Column(BigInteger, ForeignKey("users.id"), nullable=False, index=True)
    escalated_to_role = Column(String(50), nullable=True)  # admin, compliance_officer, etc.
    auto_priority = Column(Boolean, default=False)
    referred_to_compliance = Column(Boolean, default=False)
    referred_at = Column(DateTime, nullable=True)
    referred_by = Column(BigInteger, ForeignKey("users.id"), nullable=True)

    # Relationships
    flagger = relationship("User", foreign_keys=[flagged_by])
    resolver = relationship("User", foreign_keys=[resolved_by])
    assignee = relationship("User", foreign_keys=[assigned_to])
    referrer = relationship("User", foreign_keys=[referred_by])
    legal_reviewer = relationship("User", foreign_keys=[legal_review_by])
    
    # Enterprise indexes for performance
    __table_args__ = (
        db.Index('ix_content_flags_entity', 'entity_type', 'entity_id'),
        db.Index('ix_content_flags_status_priority', 'status', 'priority', 'created_at'),
        db.Index('ix_content_flags_level_team', 'moderation_level', 'assigned_team'),
        db.Index('ix_content_flags_sla', 'sla_due_at', 'status'),
        db.Index('ix_content_flags_risk_score', 'risk_score', 'status'),
        db.Index('ix_content_flags_content_hash', 'content_hash'),
    )

    def __repr__(self):
        return f"<ContentFlag {self.entity_type}:{self.entity_id} level={self.moderation_level}>"

    def calculate_sla_breached(self) -> bool:
        """Check if SLA is breached"""
        if self.sla_due_at and self.status == "open":
            return datetime.now(timezone.utc) > self.sla_due_at
        return False
    
    def get_priority_weight(self) -> int:
        """Get numeric weight for queue ordering"""
        weights = {
            "critical": 1000,
            "high": 100,
            "medium": 10,
            "normal": 1,
            "low": 0,
        }
        return weights.get(self.priority, 0)
    
    def get_enterprise_priority(self) -> str:
        """Get enterprise-level priority based on risk score and category"""
        if self.risk_score >= 80 or self.severity == "critical":
            return "critical"
        elif self.risk_score >= 60 or self.severity == "high":
            return "high"
        elif self.risk_score >= 40 or self.severity == "medium":
            return "medium"
        else:
            return "normal"


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
