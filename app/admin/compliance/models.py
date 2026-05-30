"""
Compliance models for regulatory compliance, case management, and data subject requests
"""
from datetime import datetime
from enum import Enum
from app.extensions import db


class ComplianceCaseStatus(str, Enum):
    """Compliance case status enumeration"""
    OPEN = 'open'
    IN_REVIEW = 'in_review'
    PENDING_INFO = 'pending_info'
    APPROVED = 'approved'
    REJECTED = 'rejected'
    ESCALATED = 'escalated'
    CLOSED = 'closed'


class ComplianceCasePriority(str, Enum):
    """Compliance case priority enumeration"""
    CRITICAL = 'critical'
    HIGH = 'high'
    MEDIUM = 'medium'
    LOW = 'low'


class ComplianceCaseType(str, Enum):
    """Compliance case type enumeration"""
    KYC_REVIEW = 'kyc_review'
    KYB_REVIEW = 'kyb_review'
    AML_ALERT = 'aml_alert'
    PAYOUT_REVIEW = 'payout_review'
    DATA_REQUEST = 'data_request'
    FLAG_ESCALATION = 'flag_escalation'
    LICENSE_REVIEW = 'license_review'
    OTHER = 'other'


class DataSubjectRequestType(str, Enum):
    """Data subject request type enumeration (GDPR)"""
    ACCESS = 'access'
    DELETION = 'deletion'
    RECTIFICATION = 'rectification'
    PORTABILITY = 'portability'
    OBJECTION = 'objection'


class DataSubjectRequestStatus(str, Enum):
    """Data subject request status enumeration"""
    PENDING = 'pending'
    VERIFIED = 'verified'
    PROCESSING = 'processing'
    COMPLETED = 'completed'
    REJECTED = 'rejected'
    EXPIRED = 'expired'


class ComplianceReportType(str, Enum):
    """Compliance report type enumeration"""
    KYC_SUMMARY = 'kyc_summary'
    AML_SUMMARY = 'aml_summary'
    PAYOUT_SUMMARY = 'payout_summary'
    CASE_HISTORY = 'case_history'
    AUDIT_TRAIL = 'audit_trail'
    RISK_ASSESSMENT = 'risk_assessment'
    REGULATORY_FILING = 'regulatory_filing'


class ComplianceCase(db.Model):
    """Compliance case for tracking regulatory compliance issues"""
    __tablename__ = 'compliance_cases'

    id = db.Column(db.BigInteger, primary_key=True)
    public_id = db.Column(db.String(36), unique=True, nullable=False, index=True)
    
    # Case identification
    case_type = db.Column(db.Enum(ComplianceCaseType), nullable=False, index=True)
    case_number = db.Column(db.String(50), unique=True, nullable=False, index=True)
    title = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text)
    
    # Status and priority
    status = db.Column(db.Enum(ComplianceCaseStatus), default=ComplianceCaseStatus.OPEN, nullable=False, index=True)
    priority = db.Column(db.Enum(ComplianceCasePriority), default=ComplianceCasePriority.MEDIUM, nullable=False, index=True)
    
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
    escalation_reason = db.Column(db.Text)
    
    # SLA tracking
    sla_due_at = db.Column(db.DateTime, nullable=True, index=True)
    sla_priority = db.Column(db.Enum(ComplianceCasePriority), nullable=True)
    
    # Resolution
    resolution = db.Column(db.Text)
    resolved_at = db.Column(db.DateTime, nullable=True)
    resolved_by = db.Column(db.BigInteger, db.ForeignKey('users.id'), nullable=True)
    
    # Audit
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
    created_by = db.Column(db.BigInteger, db.ForeignKey('users.id'), nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # Relationships - Fixed to specify foreign_keys to avoid ambiguity
    user = db.relationship('User', foreign_keys=[user_id], backref='compliance_cases_user')
    organisation = db.relationship('Organisation', foreign_keys=[organisation_id], backref='compliance_cases_org')
    assignee = db.relationship('User', foreign_keys=[assigned_to], backref='assigned_compliance_cases')
    creator = db.relationship('User', foreign_keys=[created_by], backref='created_compliance_cases')
    resolver = db.relationship('User', foreign_keys=[resolved_by], backref='resolved_compliance_cases')
    
    # Allow table to be redefined if already exists
    __table_args__ = {'extend_existing': True}
    
    def __repr__(self):
        return f'<ComplianceCase {self.case_number}: {self.title}>'


class DataSubjectRequest(db.Model):
    """Data subject request for GDPR compliance (access, deletion, etc.)"""
    __tablename__ = 'data_subject_requests'

    id = db.Column(db.BigInteger, primary_key=True)
    public_id = db.Column(db.String(36), unique=True, nullable=False, index=True)
    request_number = db.Column(db.String(50), unique=True, nullable=False, index=True)
    
    # Request details
    request_type = db.Column(db.Enum(DataSubjectRequestType), nullable=False, index=True)
    status = db.Column(db.Enum(DataSubjectRequestStatus), default=DataSubjectRequestStatus.PENDING, nullable=False, index=True)
    
    # Requester information
    user_id = db.Column(db.BigInteger, db.ForeignKey('users.id'), nullable=False, index=True)
    requester_email = db.Column(db.String(255), nullable=False)
    requester_name = db.Column(db.String(255), nullable=False)
    
    # Request details
    request_details = db.Column(db.Text, nullable=False)
    data_categories = db.Column(db.Text)  # JSON string of requested data categories
    scope = db.Column(db.Text)  # Description of data scope
    
    # Verification
    identity_verified = db.Column(db.Boolean, default=False, nullable=False)
    verification_method = db.Column(db.String(100))
    verified_at = db.Column(db.DateTime, nullable=True)
    verified_by = db.Column(db.BigInteger, db.ForeignKey('users.id'), nullable=True)
    
    # Processing
    assigned_to = db.Column(db.BigInteger, db.ForeignKey('users.id'), nullable=True, index=True)
    assigned_at = db.Column(db.DateTime, nullable=True)
    
    # Response
    response = db.Column(db.Text)
    response_data = db.Column(db.Text)  # JSON string of response data
    completed_at = db.Column(db.DateTime, nullable=True)
    rejection_reason = db.Column(db.Text)
    
    # Legal basis
    legal_basis = db.Column(db.String(255))
    exemption_applied = db.Column(db.Boolean, default=False)
    exemption_reason = db.Column(db.Text)
    
    # SLA
    sla_due_at = db.Column(db.DateTime, nullable=True, index=True)
    
    # Audit
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
    created_by = db.Column(db.BigInteger, db.ForeignKey('users.id'), nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # Relationships
    user = db.relationship('User', foreign_keys=[user_id], backref='data_subject_requests')
    assignee = db.relationship('User', foreign_keys=[assigned_to], backref='assigned_data_requests')
    verifier = db.relationship('User', foreign_keys=[verified_by], backref='verified_data_requests')
    creator = db.relationship('User', foreign_keys=[created_by], backref='created_data_requests')
    
    # Allow table to be redefined if already exists
    __table_args__ = {'extend_existing': True}
    
    def __repr__(self):
        return f'<DataSubjectRequest {self.request_number}: {self.request_type.value}>'


class ComplianceReport(db.Model):
    """Compliance reports for regulatory filings and internal audits"""
    __tablename__ = 'compliance_reports'

    id = db.Column(db.BigInteger, primary_key=True)
    public_id = db.Column(db.String(36), unique=True, nullable=False, index=True)
    report_number = db.Column(db.String(50), unique=True, nullable=False, index=True)
    
    # Report details
    report_type = db.Column(db.Enum(ComplianceReportType), nullable=False, index=True)
    title = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text)
    
    # Report parameters
    parameters = db.Column(db.Text)  # JSON string of report parameters
    date_range_start = db.Column(db.DateTime, nullable=True)
    date_range_end = db.Column(db.DateTime, nullable=True)
    
    # Report content
    report_data = db.Column(db.Text)  # JSON string of report data
    summary = db.Column(db.Text)
    findings = db.Column(db.Text)
    recommendations = db.Column(db.Text)
    
    # Status
    status = db.Column(db.String(50), default='draft', nullable=False, index=True)
    
    # File storage
    file_path = db.Column(db.String(500))
    file_format = db.Column(db.String(20))  # pdf, csv, json, etc.
    file_size = db.Column(db.Integer)
    
    # Review and approval
    reviewed_by = db.Column(db.BigInteger, db.ForeignKey('users.id'), nullable=True)
    reviewed_at = db.Column(db.DateTime, nullable=True)
    approved_by = db.Column(db.BigInteger, db.ForeignKey('users.id'), nullable=True)
    approved_at = db.Column(db.DateTime, nullable=True)
    
    # Distribution
    distributed_to = db.Column(db.Text)  # JSON string of recipient list
    distributed_at = db.Column(db.DateTime, nullable=True)
    
    # Audit
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
    created_by = db.Column(db.BigInteger, db.ForeignKey('users.id'), nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # Relationships
    reviewer = db.relationship('User', foreign_keys=[reviewed_by], backref='reviewed_compliance_reports')
    approver = db.relationship('User', foreign_keys=[approved_by], backref='approved_compliance_reports')
    creator = db.relationship('User', foreign_keys=[created_by], backref='created_compliance_reports')
    
    # Allow table to be redefined if already exists
    __table_args__ = {'extend_existing': True}
    
    def __repr__(self):
        return f'<ComplianceReport {self.report_number}: {self.title}>'


