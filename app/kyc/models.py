# app/kyc/models.py
from typing import Dict, Any, List
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

    # Compliance integration
    compliance_case_id = db.Column(db.Integer, db.ForeignKey("compliance_cases.id"), nullable=True, index=True)
    compliance_status = db.Column(db.String(50), nullable=True, index=True)  # pending, approved, rejected, escalated
    compliance_notes = db.Column(db.Text, nullable=True)
    compliance_reviewed_at = db.Column(db.DateTime, nullable=True)
    compliance_reviewed_by = db.Column(db.BigInteger, db.ForeignKey("users.id"), nullable=True)
    referred_to_compliance = db.Column(db.Boolean, default=False, nullable=False, index=True)
    referred_at = db.Column(db.DateTime, nullable=True)
    referred_by = db.Column(db.BigInteger, db.ForeignKey("users.id"), nullable=True)

    # Enhanced KYC fields
    expiry_date = db.Column(db.DateTime, nullable=True)
    enhanced_risk_score = db.Column(db.Float, default=0.0)
    risk_factors = db.Column(db.JSON, default=list)
    aml_screened = db.Column(db.Boolean, default=False, nullable=False)
    pep_screened = db.Column(db.Boolean, default=False, nullable=False)
    sanctions_screened = db.Column(db.Boolean, default=False, nullable=False)
    
    # Relationships - use string references to avoid import issues
    user = db.relationship("User", foreign_keys=[user_id], back_populates="kyc_records")
    verified_by = db.relationship("User", foreign_keys=[verified_by_id], lazy="joined")
    compliance_reviewer = db.relationship("User", foreign_keys=[compliance_reviewed_by], lazy="joined")
    referrer = db.relationship("User", foreign_keys=[referred_by], lazy="joined")
    
    def calculate_enhanced_risk(self) -> Dict[str, Any]:
        """Calculate enhanced risk assessment."""
        risk_score = 0.0
        risk_factors = []
        
        # Age risk
        if self.user and self.user.date_of_birth:
            age = datetime.utcnow().year - self.user.date_of_birth.year
            if age < 18:
                risk_score += 0.8
                risk_factors.append('under_age')
            elif age < 21:
                risk_score += 0.3
                risk_factors.append('under_21')
        
        # Country risk
        if self.country:
            high_risk_countries = ['AFG', 'IRN', 'PRK', 'SYR', 'MMR', 'SSD', 'VEN', 'YEM']
            if self.country in high_risk_countries:
                risk_score += 0.6
                risk_factors.append('high_risk_country')
        
        # Document quality risk
        if self.verification_score and self.verification_score < 70:
            risk_score += 0.4
            risk_factors.append('low_verification_score')
        
        # Update enhanced risk
        self.enhanced_risk_score = risk_score
        self.risk_factors = risk_factors
        
        return {
            'risk_score': risk_score,
            'risk_level': 'high' if risk_score >= 0.7 else 'medium' if risk_score >= 0.4 else 'low',
            'risk_factors': risk_factors
        }
    
    def is_expiring_soon(self, days: int = 30) -> bool:
        """Check if document is expiring soon."""
        if not self.expiry_date:
            return False
        return (self.expiry_date - datetime.utcnow()).days <= days
    
    def get_kyc_tier_requirements(self) -> Dict[str, Any]:
        """Get KYC tier requirements based on record type."""
        from app.auth.kyc_compliance import TIER_REQUIREMENTS, TIER_2_STANDARD
        
        # Map record types to tier requirements
        tier_mapping = {
            'national_id': TIER_2_STANDARD,
            'passport': TIER_2_STANDARD,
            'driving_license': TIER_2_STANDARD,
            'voter_card': TIER_2_STANDARD,
            'nira_verification': TIER_2_STANDARD
        }
        
        tier = tier_mapping.get(self.record_type, TIER_2_STANDARD)
        return TIER_REQUIREMENTS.get(tier, {})

    def __repr__(self):
        return f"<KycRecord {self.id}: User {self.user_id} - {self.status} ({self.record_type})>"
