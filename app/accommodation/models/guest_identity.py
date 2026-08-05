from datetime import datetime, timezone
from sqlalchemy import (
    Column, BigInteger, String, Boolean, DateTime, Text,
    ForeignKey, Index, UniqueConstraint
)
from sqlalchemy.orm import relationship
from app.extensions import db
from app.models.base import BaseModel


class GuestIdentityProfile(BaseModel):
    """
    Guest identity verification profile.
    Stores passport/national ID details for VIP and compliance requirements.
    """
    __tablename__ = "accommodation_guest_identity_profiles"
    __table_args__ = (
        Index("idx_guest_identity_user", "user_id"),
        UniqueConstraint("user_id", name="uq_guest_identity_user"),
    )

    user_id = Column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True)
    user = relationship("User", foreign_keys=[user_id], backref="accommodation_guest_identity")

    # Identity documents
    passport_number = Column(String(50), nullable=True)
    national_id = Column(String(50), nullable=True)
    document_image = Column(String(500), nullable=True)  # URL or storage key

    # Verification
    verification_status = Column(String(30), default="unverified")
    # Values: unverified, pending, verified, rejected

    verified_at = Column(DateTime(timezone=True), nullable=True)
    verified_by = Column(BigInteger, ForeignKey("users.id"), nullable=True)

    # Metadata
    notes = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    def __repr__(self):
        return f"<GuestIdentityProfile user_id={self.user_id} status={self.verification_status}>"
