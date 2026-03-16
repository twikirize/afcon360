# app/identity/models/individual_verification.py

from sqlalchemy import Column, BigInteger, String, Text, DateTime, Enum, ForeignKey, JSON, Index
from sqlalchemy.orm import relationship
from datetime import datetime
from app.extensions import db

class IndividualVerification(db.Model):
    __tablename__ = "individual_verifications"
    __table_args__ = (
        Index("ix_ind_verification_user_id", "user_id"),
        Index("ix_ind_verification_status", "status"),
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)

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

    status = Column(
        Enum("pending", "verified", "rejected", "expired", "suspended", name="ind_verification_status"),
        default="pending",
        nullable=False,
        index=True
    )
    scope = Column(JSON, default=dict)  # e.g. {"identity": True, "address": False}
    provider_id = Column(String(128))
    notes = Column(Text)

    requested_at = Column(DateTime, default=datetime.utcnow, nullable=False)
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