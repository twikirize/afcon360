# app/identity/models/individual_verification.py

from sqlalchemy import Column, BigInteger, String, Text, DateTime, ForeignKey, JSON, Index, CheckConstraint
from sqlalchemy.orm import relationship, validates
from datetime import datetime, timezone
from app.extensions import db
from app.models.base import BaseModel
from app.utils.enums import IndVerificationStatus


# ─────────────────────────────────────────────────────────────────
# ARCHITECTURAL BOUNDARY - identity module
# ─────────────────────────────────────────────────────────────────
# This module is part of the IDENTITY domain.
# It must NEVER import from or define relationships back to:
#   - app.fan.*
#   - app.tickets.*
#   - app.transport.*
#   - or any other feature module
#
# Dependency direction is one-way:
#   feature modules (fan, tickets, etc.) → identity module
#
# If you need to navigate from IndividualVerification → user profile,
# do it with an explicit query in the calling service:
#
#   profile = UserProfile.query.filter_by(user_id=user.public_id).first()
#
# Do NOT add a relationship here. This boundary is intentional and permanent.
# ─────────────────────────────────────────────────────────────────

class IndividualVerification(BaseModel):
    __tablename__ = "individual_verifications"
    __table_args__ = (
        Index("ix_ind_verification_user_id", "user_id"),
        Index("ix_ind_verification_status", "status"),
        CheckConstraint(IndVerificationStatus.check_constraint(), name="ck_ind_verification_status"),
    )

    # Foreign keys
    user_id = Column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False
    )
    reviewer_id = Column(
        BigInteger,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )

    # Use String + CHECK constraint instead of PostgreSQL ENUM
    status = Column(
        String(16),
        default=IndVerificationStatus.PENDING.value,
        nullable=False,
        index=True
    )
    scope = Column(JSON, default=dict)  # e.g. {"identity": True, "address": False}
    provider_id = Column(String(128))
    notes = Column(Text)

    requested_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    decided_at = Column(DateTime)
    expires_at = Column(DateTime)

    # Relationships
    user = relationship(
        "User",
        foreign_keys=[user_id],
        back_populates="verifications"
    )

    reviewer = relationship(
        "User",
        foreign_keys=[reviewer_id]
    )

    @validates("status")
    def validate_status(self, key, value):
        if value and value not in IndVerificationStatus.values():
            raise ValueError(f"Invalid status. Must be one of: {IndVerificationStatus.values()}")
        return value