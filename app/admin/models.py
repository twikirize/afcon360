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


class ManageableCategory(db.Model):
    """
    Categories for manageable content (Cities, Vehicles, Hotels, etc.)
    """
    __tablename__ = "manageable_categories"

    id = Column(Integer, primary_key=True)
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
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # Relationships
    items = relationship("ManageableItem", back_populates="category", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<ManageableCategory {self.slug}>"


class ManageableItem(db.Model):
    """
    Individual items that can be managed (Kampala City, Toyota Hiace, etc.)
    """
    __tablename__ = "manageable_items"

    id = Column(Integer, primary_key=True)
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

    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

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


class ContentSubmission(db.Model):
    """
    Tracks user submissions for content approval
    """
    __tablename__ = "content_submissions"

    id = Column(Integer, primary_key=True)
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

    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    reviewed_at = Column(DateTime, nullable=True)

    # Relationships
    category = relationship("ManageableCategory")
    item = relationship("ManageableItem")
    submitter = relationship("User", foreign_keys=[submitted_by])
    reviewer = relationship("User", foreign_keys=[reviewed_by])
    organization = relationship("Organisation", foreign_keys=[submitted_by_org])

    def __repr__(self):
        return f"<ContentSubmission {self.name}>"


class UserDashboardConfig(db.Model):
    """
    User-specific dashboard configurations
    """
    __tablename__ = "user_dashboard_configs"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)

    # Dashboard preferences
    layout = Column(String(50), default="grid")  # grid, list, cards
    visible_categories = Column(JSON, default=list)  # Which categories to show
    featured_items = Column(JSON, default=list)  # User's favorite items

    # Notification preferences
    notify_new_content = Column(Boolean, default=True)
    notify_approvals = Column(Boolean, default=True)
    notify_rejections = Column(Boolean, default=True)

    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # Relationship
    user = relationship("User", backref="dashboard_config")

    def __repr__(self):
        return f"<UserDashboardConfig user_id={self.user_id}>"