"""
AFCON360 Feed Models

Post — user/org/system published content for the homepage feed.
Advertisement — managed ad tiles that appear in the feed and sidebars.

Both inherit BaseModel (soft-delete, BIGINT id, timestamps).
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Column, BigInteger, String, Text, Boolean, Integer, DateTime,
    ForeignKey, Index, CheckConstraint,
)
from sqlalchemy.orm import relationship

from app.extensions import db
from app.models.base import BaseModel


class Post(BaseModel):
    """
    User / organization / system published content.

    A post can be standalone text/media, or a 'share' of an existing item
    (event, property, transport route) via source_item_id + source_item_type.
    """
    __tablename__ = "feed_posts"
    __table_args__ = (
        Index("idx_feed_posts_status_vis", "status", "visibility", "created_at"),
        Index("idx_feed_posts_module", "source_module"),
        Index("idx_feed_posts_author", "author_id"),
        Index("idx_feed_posts_pinned", "is_pinned", "created_at"),
        CheckConstraint(
            "status IN ('draft', 'published', 'archived', 'deleted')",
            name="ck_feed_posts_status",
        ),
        CheckConstraint(
            "visibility IN ('public', 'followers', 'private')",
            name="ck_feed_posts_visibility",
        ),
        CheckConstraint(
            "author_type IN ('individual', 'organization', 'system')",
            name="ck_feed_posts_author_type",
        ),
    )

    public_id = Column(
        String(64), unique=True, nullable=False, index=True,
        default=lambda: str(uuid.uuid4()),
    )
    author_id = Column(BigInteger, db.ForeignKey("users.id"), nullable=True, index=True)
    author_type = Column(String(20), nullable=False, default="individual")

    # Content
    body = Column(Text, nullable=False, server_default="")
    media_url = Column(String(512), nullable=True)
    link_url = Column(String(512), nullable=True)
    link_title = Column(String(255), nullable=True)

    # Optional link to a source item (e.g. sharing an event)
    source_module = Column(String(32), nullable=True, index=True)
    source_item_id = Column(BigInteger, nullable=True)
    source_item_type = Column(String(50), nullable=True)

    # Lifecycle
    status = Column(String(20), nullable=False, default="published", index=True)
    visibility = Column(String(20), nullable=False, default="public")
    is_pinned = Column(Boolean, default=False, nullable=False, index=True, server_default="false")

    # Denormalized engagement counters
    likes_count = Column(Integer, default=0, nullable=False)
    comments_count = Column(Integer, default=0, nullable=False)

    # Relationships
    author = relationship("User", foreign_keys=[author_id], lazy="noload")

    def __repr__(self):
        return f"<Post {self.id}: {self.author_type} ({self.status})>"


class Advertisement(BaseModel):
    """
    Managed advertisement tiles.

    Placement controls where the ad appears:
      home_feed   — inline within the middle feed
      home_left   — left sidebar ad slot
      home_right  — right sidebar ad slot
      dashboard   — module dashboard sidebar

    The homepage sidebars fall back to hardcoded placeholder cards when no
    active ads exist for a placement, so the UI is never empty.
    """
    __tablename__ = "feed_advertisements"
    __table_args__ = (
        Index("idx_feed_ads_placement", "status", "placement", "start_date", "end_date"),
        Index("idx_feed_ads_priority", "priority"),
        CheckConstraint(
            "status IN ('pending', 'approved', 'active', 'paused', 'expired', 'rejected')",
            name="ck_feed_ads_status",
        ),
        CheckConstraint(
            "ad_type IN ('banner', 'tile', 'inline_feed', 'sidebar')",
            name="ck_feed_ads_type",
        ),
        CheckConstraint(
            "placement IN ('home_feed', 'home_left', 'home_right', 'dashboard')",
            name="ck_feed_ads_placement",
        ),
    )

    public_id = Column(
        String(64), unique=True, nullable=False, index=True,
        default=lambda: str(uuid.uuid4()),
    )

    # Content
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    image_url = Column(String(512), nullable=True)
    link_url = Column(String(512), nullable=True)

    # Placement
    ad_type = Column(String(20), nullable=False, default="sidebar")
    placement = Column(String(30), nullable=False, default="home_right")

    # Advertiser
    advertiser_id = Column(BigInteger, db.ForeignKey("users.id"), nullable=True)
    advertiser_name = Column(String(120), nullable=True)
    source_module = Column(String(32), nullable=True)

    # Lifecycle
    status = Column(String(20), nullable=False, default="pending", index=True)
    start_date = Column(DateTime, nullable=True)
    end_date = Column(DateTime, nullable=True)
    priority = Column(Integer, default=5, nullable=False)

    # Metrics (denormalized)
    impressions_count = Column(Integer, default=0, nullable=False)
    clicks_count = Column(Integer, default=0, nullable=False)

    # Relationships
    advertiser = relationship("User", foreign_keys=[advertiser_id], lazy="noload")

    def is_currently_active(self) -> bool:
        """True if status=active and within the date window."""
        if self.status != "active":
            return False
        now = datetime.now(timezone.utc)
        if self.start_date and now < self.start_date:
            return False
        if self.end_date and now > self.end_date:
            return False
        return True

    def __repr__(self):
        return f"<Advertisement {self.id}: {self.placement}/{self.status} '{self.title}'>"
