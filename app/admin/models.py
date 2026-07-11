#app/admin/models.py
"""
Dynamic Content Management Models
Allows frontend management of cities, vehicles, hotels, etc.
"""
from datetime import datetime, timezone
from sqlalchemy import Column, BigInteger, Integer, String, Boolean, DateTime, JSON, ForeignKey, Text
from sqlalchemy.orm import relationship, validates
from sqlalchemy.sql import func
from app.extensions import db
from app.models.base import BaseModel


class ManageableCategory(BaseModel):
    """
    Categories for manageable content (Cities, Vehicles, Hotels, etc.)
    """
    __tablename__ = "manageable_categories"

    name = Column(String(100), nullable=False, unique=True)  # Cities, Vehicles, Hotels
    slug = Column(String(100), nullable=False, unique=True)  # cities, vehicles, hotels
    description = Column(Text, nullable=True)
    icon = Column(String(50), nullable=True)  # Bootstrap icon class
    color = Column(String(20), nullable=True)  # Bootstrap color class

    # Who can manage this category
    editable_by_admins = Column(Boolean, default=True)
    editable_by_org_admins = Column(Boolean, default=False)
    editable_by_users = Column(Boolean, default=False)

    # Fields configuration (JSON schema)
    fields_config = Column(JSON, nullable=False, default=dict)

    is_active = Column(Boolean, default=True)

    # Relationships
    items = relationship("ManageableItem", back_populates="category", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<ManageableCategory {self.slug}>"


class ManageableItem(BaseModel):
    """
    Individual items that can be managed (Kampala City, Toyota Hiace, etc.)
    """
    __tablename__ = "manageable_items"

    category_id = Column(BigInteger, ForeignKey("manageable_categories.id"), nullable=False)
    name = Column(String(200), nullable=False)
    slug = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)

    # Content data (dynamic based on category)
    data = Column(JSON, nullable=False, default=dict)

    # Status
    is_active = Column(Boolean, default=True)
    is_approved = Column(Boolean, default=True)  # For user submissions
    is_featured = Column(Boolean, default=False)

    # Ownership
    created_by = Column(BigInteger, ForeignKey("users.id"), nullable=True)
    owned_by_org = Column(BigInteger, ForeignKey("organisations.id"), nullable=True)

    # Metadata
    views = Column(Integer, default=0)
    rating = Column(Integer, default=0)  # 1-5

    # Relationships
    category = relationship("ManageableCategory", back_populates="items")
    creator = relationship("User", foreign_keys=[created_by])
    organization = relationship("Organisation", foreign_keys=[owned_by_org])

    # Indexes
    __table_args__ = (
        db.Index('ix_manageable_items_category_active', 'category_id', 'is_active'),
        db.Index('ix_manageable_items_slug', 'slug'),
    )

    def __repr__(self):
        return f"<ManageableItem {self.slug}>"


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
        from datetime import datetime, timezone, timedelta
        if not self.sla_due_at:
            self.sla_due_at = datetime.now(timezone.utc) + timedelta(hours=72)

    def __repr__(self):
        return f"<ContentSubmission {self.name}>"


class UserDashboardConfig(BaseModel):
    """
    User-specific dashboard configurations
    """
    __tablename__ = "user_dashboard_configs"

    user_id = Column(BigInteger, ForeignKey("users.id"), unique=True, nullable=False)

    # Dashboard preferences
    layout = Column(String(50), default="grid")  # grid, list, cards
    visible_categories = Column(JSON, default=list)  # Which categories to show
    featured_items = Column(JSON, default=list)  # User's favorite items

    # Notification preferences
    notify_new_content = Column(Boolean, default=True)
    notify_approvals = Column(Boolean, default=True)
    notify_rejections = Column(Boolean, default=True)

    # Relationship
    user = relationship("User", backref="dashboard_config")

    def __repr__(self):
        return f"<UserDashboardConfig user_id={self.user_id}>"


# ContentFlag moved to __init__.py to avoid circular imports


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
