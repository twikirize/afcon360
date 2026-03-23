# app/accommodation/models/review.py
"""
Review models - Guest reviews for properties
"""

from datetime import datetime
from sqlalchemy import (
    Column, BigInteger, String, Boolean, DateTime,
    ForeignKey, Integer, Text,
    Index, UniqueConstraint, CheckConstraint
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.extensions import db
import enum


# ==========================================
# Namespaced Enum for Review
# ==========================================

class AccommodationReviewStatus(enum.Enum):
    """Review status - matches DB enum 'accommodation_reviewstatus'"""
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    FLAGGED = "flagged"


# ==========================================
# Review Model
# ==========================================

class Review(db.Model):
    __tablename__ = "accommodation_reviews"
    __table_args__ = (
        UniqueConstraint("booking_id", name="uq_review_per_booking"),
        Index("idx_review_property", "property_id"),
        Index("idx_review_reviewer", "reviewer_id"),
        Index("idx_review_status", "status"),
        Index("idx_review_rating", "overall_rating"),
        CheckConstraint("overall_rating BETWEEN 1 AND 5", name="ck_overall_rating_range"),
        CheckConstraint("cleanliness_rating BETWEEN 1 AND 5", name="ck_cleanliness_range"),
        CheckConstraint("accuracy_rating BETWEEN 1 AND 5", name="ck_accuracy_range"),
        CheckConstraint("checkin_rating BETWEEN 1 AND 5", name="ck_checkin_range"),
        CheckConstraint("communication_rating BETWEEN 1 AND 5", name="ck_communication_range"),
        CheckConstraint("location_rating BETWEEN 1 AND 5", name="ck_location_range"),
        CheckConstraint("value_rating BETWEEN 1 AND 5", name="ck_value_range"),
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)

    # -------------------------------
    # Relationships
    # -------------------------------
    booking_id = Column(BigInteger, ForeignKey("accommodation_bookings.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    booking = relationship("AccommodationBooking", back_populates="review")

    property_id = Column(BigInteger, ForeignKey("accommodation_properties.id", ondelete="CASCADE"), nullable=False, index=True)
    property = relationship("Property", back_populates="reviews")

    reviewer_id = Column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    reviewer = relationship("User", foreign_keys=[reviewer_id], backref="accommodation_reviews")

    # -------------------------------
    # Ratings (1-5)
    # -------------------------------
    overall_rating = Column(Integer, nullable=False)
    cleanliness_rating = Column(Integer, nullable=True)
    accuracy_rating = Column(Integer, nullable=True)
    checkin_rating = Column(Integer, nullable=True)
    communication_rating = Column(Integer, nullable=True)
    location_rating = Column(Integer, nullable=True)
    value_rating = Column(Integer, nullable=True)

    # -------------------------------
    # Content
    # -------------------------------
    comment = Column(Text, nullable=True)
    host_response = Column(Text, nullable=True)
    responded_at = Column(DateTime, nullable=True)

    # -------------------------------
    # Moderation
    # -------------------------------
    status = Column(db.Enum(AccommodationReviewStatus), default=AccommodationReviewStatus.PENDING, nullable=False, index=True)
    moderated_by = Column(BigInteger, ForeignKey("users.id"), nullable=True)
    moderation_reason = Column(Text, nullable=True)
    moderated_at = Column(DateTime, nullable=True)

    # -------------------------------
    # Publishing
    # -------------------------------
    is_published = Column(Boolean, default=False, index=True)
    published_at = Column(DateTime, nullable=True)

    # -------------------------------
    # Timestamps
    # -------------------------------
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # -------------------------------
    # Core Methods
    # -------------------------------
    def __repr__(self):
        return f"<Review {self.id}: rating={self.overall_rating}>"

    def publish(self, moderator_id):
        self.status = AccommodationReviewStatus.APPROVED
        self.is_published = True
        self.published_at = datetime.utcnow()
        self.moderated_by = moderator_id
        self.moderated_at = datetime.utcnow()

    def reject(self, moderator_id, reason):
        self.status = AccommodationReviewStatus.REJECTED
        self.moderation_reason = reason
        self.moderated_by = moderator_id
        self.moderated_at = datetime.utcnow()

    def respond(self, response_text):
        self.host_response = response_text
        self.responded_at = datetime.utcnow()