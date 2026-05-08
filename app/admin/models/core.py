# app/admin/models/core.py
"""
Core admin models to avoid circular imports
"""

from datetime import datetime, timezone, timedelta
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


class SystemConfiguration(BaseModel):
    """
    System-wide configuration settings stored in database
    """
    __tablename__ = "system_configurations"

    key = Column(String(100), nullable=False, unique=True, index=True)
    value = Column(Text, nullable=False)
    description = Column(Text, nullable=True)
    value_type = Column(String(50), default="string")  # string, int, bool, json
    category = Column(String(50), nullable=True)  # permissions, features, security, etc.
    is_public = Column(Boolean, default=False)  # Whether this setting can be exposed to clients

    def __repr__(self):
        return f"<SystemConfiguration {self.key}={self.value}>"
