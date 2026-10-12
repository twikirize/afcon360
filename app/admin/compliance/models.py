"""
Compliance models for regulatory compliance, case management, and data subject requests
"""
from datetime import datetime, timezone
from app.extensions import db
from sqlalchemy import Column, BigInteger, String, Text, DateTime, Index, CheckConstraint, ForeignKey
from sqlalchemy.orm import relationship, validates
from app.utils.enums import (
    ComplianceCaseStatus,
    ComplianceCasePriority,
    ComplianceCaseType,
    DataSubjectRequestType,
    DataSubjectRequestStatus,
    ComplianceReportType,
)
from app.models.base import BaseModel
from sqlalchemy import Column, BigInteger, String, Text, DateTime, Index, CheckConstraint, ForeignKey
from sqlalchemy.orm import relationship
from app.utils.enums import (
    ComplianceCaseStatus,
    ComplianceCasePriority,
    ComplianceCaseType,
    DataSubjectRequestType,
    DataSubjectRequestStatus,
    ComplianceReportType,
)
from app.models.base import BaseModel


class ComplianceCase(BaseModel):
    """Compliance case for tracking regulatory compliance issues"""
    __tablename__ = 'compliance_cases'
    __table_args__ = (
        CheckConstraint(ComplianceCaseType.check_constraint(), name="ck_compliance_case_type"),
        CheckConstraint(ComplianceCaseStatus.check_constraint(), name="ck_compliance_case_status"),
        CheckConstraint(ComplianceCasePriority.check_constraint(), name="ck_compliance_case_priority"),
    )

    id = db.Column(db.BigInteger, primary_key=True)
    public_id = db.Column(db.String(36), unique=True, nullable=False, index=True)
    
    # Case identification - Use String + CHECK constraint instead of PostgreSQL ENUM
    case_type = Column(String(30), nullable=False, index=True)
    case_number = db.Column(db.String(50), unique=True, nullable=False, index=True)
    title = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text)
    
    # Status and priority - Use String + CHECK constraint instead of PostgreSQL ENUM
    status = Column(String(20), default=ComplianceCaseStatus.OPEN.value, nullable=False, index=True)
    priority = Column(String(16), default=ComplianceCasePriority.MEDIUM.value, nullable=False, index=True)
    
    # Entity references
    user_id = db.Column(db.BigInteger, db.ForeignKey('users.id'), nullable=True, index=True)
    organisation_id = db.Column(db.BigInteger, db.ForeignKey('organisations.id'), nullable=True, index=True)
    kyc_id = db.Column(db.BigInteger, nullable=True, index=True)  # Reference to KYC record
    payout_id = db.Column(db.BigInteger, nullable=True, index=True)  # Reference to payout request
    flag_id = db.Column(db.BigInteger, nullable=True, index=True)  # Reference to content flag
    
    # Assignment
    assigned_to = db.Column(db.BigInteger, db.ForeignKey('users.id'), nullable=True, index=True)
    assigned_at = db.Column(db.DateTime, nullable=True)
    
    # Escalation
    escalated_from = db.Column(db.BigInteger, nullable=True)  # User ID who escalated
    escalated_at = db.Column(db.DateTime, nullable=True)

    __table_args__ = (
        CheckConstraint(ComplianceCaseType.check_constraint(), name="ck_compliance_case_type"),
        CheckConstraint(ComplianceCaseStatus.check_constraint(), name="ck_compliance_case_status"),
        CheckConstraint(ComplianceCasePriority.check_constraint(), name="ck_compliance_case_priority"),
    )

    @validates("case_type")
    def validate_case_type(self, key, value):
        if value and value not in ComplianceCaseType.values():
            raise ValueError(f"Invalid case_type. Must be one of: {ComplianceCaseType.values()}")
        return value

    @validates("status")
    def validate_status(self, key, value):
        if value and value not in ComplianceCaseStatus.values():
            raise ValueError(f"Invalid status. Must be one of: {ComplianceCaseStatus.values()}")
        return value

    @validates("priority")
    def validate_priority(self, key, value):
        if value and value not in ComplianceCasePriority.values():
            raise ValueError(f"Invalid priority. Must be one of: {ComplianceCasePriority.values()}")
        return value