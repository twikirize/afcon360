#app/admin/models.py
"""
Dynamic Content Management Models
Allows frontend management of cities, vehicles, hotels, etc.
"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Boolean, DateTime, JSON, ForeignKey, Text
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

    category_id = Column(Integer, ForeignKey("manageable_categories.id"), nullable=False)
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
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    owned_by_org = Column(Integer, ForeignKey("organisations.id"), nullable=True)

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

    item_id = Column(Integer, ForeignKey("manageable_items.id"), nullable=True)
    category_id = Column(Integer, ForeignKey("manageable_categories.id"), nullable=False)

    # Submission data
    name = Column(String(200), nullable=False)
    data = Column(JSON, nullable=False, default=dict)

    # Status
    status = Column(String(20), default="pending")  # pending, approved, rejected
    reviewed_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    review_notes = Column(Text, nullable=True)

    # Submitted by
    submitted_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    submitted_by_org = Column(Integer, ForeignKey("organisations.id"), nullable=True)

    reviewed_at = Column(DateTime, nullable=True)

    # Relationships
    category = relationship("ManageableCategory")
    item = relationship("ManageableItem")
    submitter = relationship("User", foreign_keys=[submitted_by])
    reviewer = relationship("User", foreign_keys=[reviewed_by])
    organization = relationship("Organisation", foreign_keys=[submitted_by_org])

    def __repr__(self):
        return f"<ContentSubmission {self.name}>"


class UserDashboardConfig(BaseModel):
    """
    User-specific dashboard configurations
    """
    __tablename__ = "user_dashboard_configs"

    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)

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


class ContentFlag(BaseModel):
    """
    Polymorphic content flag used for moderation escalation across entities.
    Does NOT change entity state; purely an escalation record.
    """
    __tablename__ = "content_flags"

    # Polymorphic target
    entity_type = Column(String(50), nullable=False, index=True)  # e.g., "event", "manageable_item"
    entity_id = Column(Integer, nullable=False, index=True)

    # Who flagged it
    flagged_by = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    # Reason + context
    reason = Column(Text, nullable=False)
    priority = Column(String(20), default="normal", index=True)  # low|normal|medium|high|critical
    category = Column(String(50), nullable=True)

    # Workflow state
    status = Column(String(20), default="open", index=True)  # open | in_review | resolved | rejected

    # Escalation routing
    escalated_to_role = Column(String(50), nullable=True)
    assigned_to = Column(Integer, ForeignKey("users.id"), nullable=True)

    # Resolution
    resolved_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    resolution_action = Column(String(50), nullable=True)
    resolution_notes = Column(Text, nullable=True)
    resolved_at = Column(DateTime, nullable=True)

    # Relationships
    flagger = relationship("User", foreign_keys=[flagged_by])
    assignee = relationship("User", foreign_keys=[assigned_to])
    resolver = relationship("User", foreign_keys=[resolved_by])

    __table_args__ = (
        db.Index('ix_flags_entity', 'entity_type', 'entity_id'),
        db.Index('ix_flags_status_priority', 'status', 'priority'),
    )

    def __repr__(self):
        return f"<ContentFlag {self.entity_type}:{self.entity_id} status={self.status}>"
