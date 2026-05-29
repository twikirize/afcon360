# app/accommodation/models/wishlist.py
"""
Wishlist model for accommodation properties
"""

from datetime import datetime, timezone
from sqlalchemy import Column, BigInteger, ForeignKey, DateTime, Index, UniqueConstraint
from sqlalchemy.orm import relationship
from app.extensions import db
from app.models.base import BaseModel


class Wishlist(BaseModel):
    """User wishlist for accommodation properties"""
    __tablename__ = "accommodation_wishlists"
    __table_args__ = (
        UniqueConstraint("user_id", "property_id", name="uq_wishlist_user_property"),
        Index("idx_wishlist_user", "user_id"),
        Index("idx_wishlist_property", "property_id"),
    )

    user_id = Column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    property_id = Column(BigInteger, ForeignKey("accommodation_properties.id", ondelete="CASCADE"), nullable=False, index=True)

    # Relationships
    user = relationship("User", backref="accommodation_wishlists")
    property = relationship("Property", backref="wishlists")

    def __repr__(self):
        return f"<Wishlist user_id={self.user_id} property_id={self.property_id}>"

    @classmethod
    def is_wishlisted(cls, user_id, property_id):
        """Check if a property is in a user's wishlist"""
        return cls.query.filter_by(user_id=user_id, property_id=property_id).first() is not None

    @classmethod
    def toggle(cls, user_id, property_id):
        """Toggle a property in a user's wishlist"""
        existing = cls.query.filter_by(user_id=user_id, property_id=property_id).first()
        if existing:
            db.session.delete(existing)
            db.session.commit()
            return False, "Removed from wishlist"
        else:
            wishlist_item = cls(user_id=user_id, property_id=property_id)
            db.session.add(wishlist_item)
            db.session.commit()
            return True, "Added to wishlist"
