# app/kyc/models.py
from app.extensions import db
from app.models.base import ProtectedModel
from datetime import datetime

# User import is removed to avoid circular imports
# SQLAlchemy relationships use string references


class KycRecord(ProtectedModel):
    """KYC verification records"""
    __tablename__ = "kyc_records"
    __table_args__ = (
        db.Index("ix_kyc_user_status", "user_id", "status"),
    )

    user_id = db.Column(db.BigInteger, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    # ── New Generic Categorization ──────────────────────────────────────────
    # record_type identifies the business flow (e.g., 'nira_national_id')
    record_type = db.Column(db.String(50), nullable=False, index=True)

    # document_type identifies the format (e.g., 'jpeg', 'pdf', 'png')
    document_type = db.Column(db.String(50), nullable=True)

    # KYC content
    id_type = db.Column(db.String(50), nullable=True)  # Legacy support for passport, national_id
    id_number = db.Column(db.String(128), nullable=False)
    id_number_masked = db.Column(db.String(128), nullable=True)  # For UI display

    document_url = db.Column(db.String(2048), nullable=True)  # store in secure bucket
    selfie_url = db.Column(db.String(2048), nullable=True)
    address_line1 = db.Column(db.String(255), nullable=True)
    address_line2 = db.Column(db.String(255), nullable=True)
    city = db.Column(db.String(120), nullable=True)
    state = db.Column(db.String(120), nullable=True)
    postal_code = db.Column(db.String(20), nullable=True)
    country = db.Column(db.String(2), nullable=True)

    # Verification workflow
    status = db.Column(db.String(30), default="pending", nullable=False,
                       index=True)  # pending, verified, rejected, expired
    provider = db.Column(db.String(50), nullable=True)  # external KYC provider tag
    checked_by = db.Column(db.String(80), nullable=True)  # admin username or service id
    verified_at = db.Column(db.DateTime, nullable=True)
    rejection_reason = db.Column(db.String(1024), nullable=True)

    # Additional fields for compliance tracking
    verification_id = db.Column(db.String(100), nullable=True)
    document_number = db.Column(db.String(100), nullable=True)
    verified_by_id = db.Column(db.BigInteger, db.ForeignKey("users.id"), nullable=True)
    reference_code = db.Column(db.String(100), nullable=True, index=True)  # For external references like NIRA IDs

    # Document storage
    front_image_url = db.Column(db.String(500), nullable=True)
    back_image_url = db.Column(db.String(500), nullable=True)

    # Verification details
    verification_method = db.Column(db.String(50), nullable=True)
    verification_score = db.Column(db.Integer, nullable=True)
    risk_score = db.Column(db.Integer, default=0)
    scope = db.Column(db.JSON, default=dict)
    raw_response = db.Column(db.JSON, nullable=True)  # Full audit trail from NIRA/Provider

    # Relationships - use string references to avoid import issues
    user = db.relationship("User", foreign_keys=[user_id], back_populates="kyc_records")
    verified_by = db.relationship("User", foreign_keys=[verified_by_id], lazy="joined")

    def __repr__(self):
        return f"<KycRecord {self.id}: User {self.user_id} - {self.status} ({self.record_type})>"
