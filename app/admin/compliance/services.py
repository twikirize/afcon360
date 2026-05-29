"""
Compliance services for business logic layer
"""
import json
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any
from flask import current_app

from app.extensions import db
from app.admin.compliance.models import (
    ComplianceCase, DataSubjectRequest, ComplianceReport,
    ComplianceCaseStatus, ComplianceCasePriority, ComplianceCaseType,
    DataSubjectRequestType, DataSubjectRequestStatus,
    ComplianceReportType
)
from app.audit.forensic_audit import ForensicAuditService


class ComplianceCaseService:
    """Service for managing compliance cases"""
    
    @staticmethod
    def generate_case_number() -> str:
        """Generate a unique case number"""
        year = datetime.now(timezone.utc).year
        month = datetime.now(timezone.utc).month
        # Get count of cases this month
        count = ComplianceCase.query.filter(
            db.extract('year', ComplianceCase.created_at) == year,
            db.extract('month', ComplianceCase.created_at) == month
        ).count()
        return f"COMP-{year}{month:02d}-{count + 1:05d}"
    
    @staticmethod
    def create_case(
        case_type: ComplianceCaseType,
        title: str,
        description: str,
        created_by: int,
        user_id: Optional[int] = None,
        organisation_id: Optional[int] = None,
        kyc_id: Optional[int] = None,
        payout_id: Optional[int] = None,
        flag_id: Optional[int] = None,
        priority: ComplianceCasePriority = ComplianceCasePriority.MEDIUM,
        escalated_from: Optional[int] = None,
        escalation_reason: Optional[str] = None
    ) -> ComplianceCase:
        """Create a new compliance case"""
        case = ComplianceCase(
            public_id=str(uuid.uuid4()),
            case_number=ComplianceCaseService.generate_case_number(),
            case_type=case_type,
            title=title,
            description=description,
            status=ComplianceCaseStatus.OPEN,
            priority=priority,
            user_id=user_id,
            organisation_id=organisation_id,
            kyc_id=kyc_id,
            payout_id=payout_id,
            flag_id=flag_id,
            created_by=created_by,
            escalated_from=escalated_from,
            escalation_reason=escalation_reason
        )
        
        # Set SLA based on priority
        case.sla_priority = priority
        if priority == ComplianceCasePriority.CRITICAL:
            case.sla_due_at = datetime.now(timezone.utc) + timedelta(hours=4)
        elif priority == ComplianceCasePriority.HIGH:
            case.sla_due_at = datetime.now(timezone.utc) + timedelta(hours=12)
        elif priority == ComplianceCasePriority.MEDIUM:
            case.sla_due_at = datetime.now(timezone.utc) + timedelta(hours=24)
        else:
            case.sla_due_at = datetime.now(timezone.utc) + timedelta(hours=72)
        
        if escalated_from:
            case.escalated_at = datetime.now(timezone.utc)
        
        db.session.add(case)
        db.session.commit()
        
        # Log audit
        ForensicAuditService.log_action(
            action='create_compliance_case',
            user_id=created_by,
            resource_type='compliance_case',
            resource_id=case.id,
            details={
                'case_number': case.case_number,
                'case_type': case_type.value,
                'priority': priority.value
            }
        )
        
        return case
    
    @staticmethod
    def assign_case(case_id: int, assigned_to: int, assigned_by: int) -> Optional[ComplianceCase]:
        """Assign a compliance case to a user"""
        case = ComplianceCase.query.get(case_id)
        if not case:
            return None
        
        case.assigned_to = assigned_to
        case.assigned_at = datetime.now(timezone.utc)
        case.status = ComplianceCaseStatus.IN_REVIEW
        case.updated_at = datetime.now(timezone.utc)
        
        db.session.commit()
        
        # Log audit
        ForensicAuditService.log_action(
            action='assign_compliance_case',
            user_id=assigned_by,
            resource_type='compliance_case',
            resource_id=case.id,
            details={
                'case_number': case.case_number,
                'assigned_to': assigned_to
            }
        )
        
        return case
    
    @staticmethod
    def update_case_status(
        case_id: int,
        status: ComplianceCaseStatus,
        updated_by: int,
        resolution: Optional[str] = None
    ) -> Optional[ComplianceCase]:
        """Update compliance case status"""
        case = ComplianceCase.query.get(case_id)
        if not case:
            return None
        
        case.status = status
        case.updated_at = datetime.now(timezone.utc)
        
        if resolution:
            case.resolution = resolution
        
        if status in [ComplianceCaseStatus.APPROVED, ComplianceCaseStatus.REJECTED, ComplianceCaseStatus.CLOSED]:
            case.resolved_at = datetime.now(timezone.utc)
            case.resolved_by = updated_by
        
        db.session.commit()
        
        # Log audit
        ForensicAuditService.log_action(
            action='update_compliance_case_status',
            user_id=updated_by,
            resource_type='compliance_case',
            resource_id=case.id,
            details={
                'case_number': case.case_number,
                'status': status.value,
                'resolution': resolution
            }
        )
        
        return case
    
    @staticmethod
    def escalate_case(
        case_id: int,
        escalated_by: int,
        escalation_reason: str,
        new_priority: Optional[ComplianceCasePriority] = None
    ) -> Optional[ComplianceCase]:
        """Escalate a compliance case"""
        case = ComplianceCase.query.get(case_id)
        if not case:
            return None
        
        case.status = ComplianceCaseStatus.ESCALATED
        case.escalated_from = escalated_by
        case.escalated_at = datetime.now(timezone.utc)
        case.escalation_reason = escalation_reason
        case.updated_at = datetime.now(timezone.utc)
        
        if new_priority:
            case.priority = new_priority
            case.sla_priority = new_priority
            # Update SLA based on new priority
            if new_priority == ComplianceCasePriority.CRITICAL:
                case.sla_due_at = datetime.now(timezone.utc) + timedelta(hours=4)
            elif new_priority == ComplianceCasePriority.HIGH:
                case.sla_due_at = datetime.now(timezone.utc) + timedelta(hours=12)
            elif new_priority == ComplianceCasePriority.MEDIUM:
                case.sla_due_at = datetime.now(timezone.utc) + timedelta(hours=24)
            else:
                case.sla_due_at = datetime.now(timezone.utc) + timedelta(hours=72)
        
        db.session.commit()
        
        # Log audit
        ForensicAuditService.log_action(
            action='escalate_compliance_case',
            user_id=escalated_by,
            resource_type='compliance_case',
            resource_id=case.id,
            details={
                'case_number': case.case_number,
                'escalation_reason': escalation_reason,
                'new_priority': new_priority.value if new_priority else None
            }
        )
        
        return case
    
    @staticmethod
    def get_cases_by_status(status: ComplianceCaseStatus) -> List[ComplianceCase]:
        """Get cases by status"""
        return ComplianceCase.query.filter_by(status=status).order_by(
            ComplianceCase.priority.desc(),
            ComplianceCase.created_at.asc()
        ).all()
    
    @staticmethod
    def get_cases_by_type(case_type: ComplianceCaseType) -> List[ComplianceCase]:
        """Get cases by type"""
        return ComplianceCase.query.filter_by(case_type=case_type).order_by(
            ComplianceCase.created_at.desc()
        ).all()
    
    @staticmethod
    def get_overdue_cases() -> List[ComplianceCase]:
        """Get cases past SLA due time"""
        return ComplianceCase.query.filter(
            ComplianceCase.sla_due_at < datetime.now(timezone.utc),
            ComplianceCase.status.in_([
                ComplianceCaseStatus.OPEN,
                ComplianceCaseStatus.IN_REVIEW,
                ComplianceCaseStatus.PENDING_INFO
            ])
        ).order_by(ComplianceCase.sla_due_at.asc()).all()
    
    @staticmethod
    def get_case_statistics() -> Dict[str, Any]:
        """Get compliance case statistics"""
        total = ComplianceCase.query.count()
        open_cases = ComplianceCase.query.filter_by(status=ComplianceCaseStatus.OPEN).count()
        in_review = ComplianceCase.query.filter_by(status=ComplianceCaseStatus.IN_REVIEW).count()
        overdue = len(ComplianceCaseService.get_overdue_cases())
        
        by_type = {}
        for case_type in ComplianceCaseType:
            by_type[case_type.value] = ComplianceCase.query.filter_by(case_type=case_type).count()
        
        by_priority = {}
        for priority in ComplianceCasePriority:
            by_priority[priority.value] = ComplianceCase.query.filter_by(priority=priority).count()
        
        return {
            'total': total,
            'open': open_cases,
            'in_review': in_review,
            'overdue': overdue,
            'by_type': by_type,
            'by_priority': by_priority
        }


class DataSubjectRequestService:
    """Service for managing GDPR data subject requests"""
    
    @staticmethod
    def generate_request_number() -> str:
        """Generate a unique request number"""
        year = datetime.now(timezone.utc).year
        month = datetime.now(timezone.utc).month
        count = DataSubjectRequest.query.filter(
            db.extract('year', DataSubjectRequest.created_at) == year,
            db.extract('month', DataSubjectRequest.created_at) == month
        ).count()
        return f"DSR-{year}{month:02d}-{count + 1:05d}"
    
    @staticmethod
    def create_request(
        request_type: DataSubjectRequestType,
        user_id: int,
        requester_email: str,
        requester_name: str,
        request_details: str,
        created_by: int,
        data_categories: Optional[str] = None,
        scope: Optional[str] = None
    ) -> DataSubjectRequest:
        """Create a new data subject request"""
        request = DataSubjectRequest(
            public_id=str(uuid.uuid4()),
            request_number=DataSubjectRequestService.generate_request_number(),
            request_type=request_type,
            status=DataSubjectRequestStatus.PENDING,
            user_id=user_id,
            requester_email=requester_email,
            requester_name=requester_name,
            request_details=request_details,
            data_categories=data_categories,
            scope=scope,
            created_by=created_by
        )
        
        # Set SLA (30 days for most requests, can be extended)
        request.sla_due_at = datetime.now(timezone.utc) + timedelta(days=30)
        
        db.session.add(request)
        db.session.commit()
        
        # Log audit
        ForensicAuditService.log_action(
            action='create_data_subject_request',
            user_id=created_by,
            resource_type='data_subject_request',
            resource_id=request.id,
            details={
                'request_number': request.request_number,
                'request_type': request_type.value
            }
        )
        
        return request
    
    @staticmethod
    def verify_identity(
        request_id: int,
        verified_by: int,
        verification_method: str
    ) -> Optional[DataSubjectRequest]:
        """Verify identity of data subject request"""
        request = DataSubjectRequest.query.get(request_id)
        if not request:
            return None
        
        request.identity_verified = True
        request.verification_method = verification_method
        request.verified_at = datetime.now(timezone.utc)
        request.verified_by = verified_by
        request.status = DataSubjectRequestStatus.VERIFIED
        request.updated_at = datetime.now(timezone.utc)
        
        db.session.commit()
        
        # Log audit
        ForensicAuditService.log_action(
            action='verify_dsr_identity',
            user_id=verified_by,
            resource_type='data_subject_request',
            resource_id=request.id,
            details={
                'request_number': request.request_number,
                'verification_method': verification_method
            }
        )
        
        return request
    
    @staticmethod
    def assign_request(
        request_id: int,
        assigned_to: int,
        assigned_by: int
    ) -> Optional[DataSubjectRequest]:
        """Assign a data subject request"""
        request = DataSubjectRequest.query.get(request_id)
        if not request:
            return None
        
        request.assigned_to = assigned_to
        request.assigned_at = datetime.now(timezone.utc)
        request.status = DataSubjectRequestStatus.PROCESSING
        request.updated_at = datetime.now(timezone.utc)
        
        db.session.commit()
        
        # Log audit
        ForensicAuditService.log_action(
            action='assign_data_subject_request',
            user_id=assigned_by,
            resource_type='data_subject_request',
            resource_id=request.id,
            details={
                'request_number': request.request_number,
                'assigned_to': assigned_to
            }
        )
        
        return request
    
    @staticmethod
    def complete_request(
        request_id: int,
        completed_by: int,
        response: str,
        response_data: Optional[str] = None
    ) -> Optional[DataSubjectRequest]:
        """Complete a data subject request"""
        request = DataSubjectRequest.query.get(request_id)
        if not request:
            return None
        
        request.status = DataSubjectRequestStatus.COMPLETED
        request.response = response
        request.response_data = response_data
        request.completed_at = datetime.now(timezone.utc)
        request.updated_at = datetime.now(timezone.utc)
        
        db.session.commit()
        
        # Log audit
        ForensicAuditService.log_action(
            action='complete_data_subject_request',
            user_id=completed_by,
            resource_type='data_subject_request',
            resource_id=request.id,
            details={
                'request_number': request.request_number,
                'response': response
            }
        )
        
        return request
    
    @staticmethod
    def reject_request(
        request_id: int,
        rejected_by: int,
        rejection_reason: str
    ) -> Optional[DataSubjectRequest]:
        """Reject a data subject request"""
        request = DataSubjectRequest.query.get(request_id)
        if not request:
            return None
        
        request.status = DataSubjectRequestStatus.REJECTED
        request.rejection_reason = rejection_reason
        request.updated_at = datetime.now(timezone.utc)
        
        db.session.commit()
        
        # Log audit
        ForensicAuditService.log_action(
            action='reject_data_subject_request',
            user_id=rejected_by,
            resource_type='data_subject_request',
            resource_id=request.id,
            details={
                'request_number': request.request_number,
                'rejection_reason': rejection_reason
            }
        )
        
        return request
    
    @staticmethod
    def get_requests_by_status(status: DataSubjectRequestStatus) -> List[DataSubjectRequest]:
        """Get requests by status"""
        return DataSubjectRequest.query.filter_by(status=status).order_by(
            DataSubjectRequest.created_at.desc()
        ).all()
    
    @staticmethod
    def get_overdue_requests() -> List[DataSubjectRequest]:
        """Get requests past SLA due time"""
        return DataSubjectRequest.query.filter(
            DataSubjectRequest.sla_due_at < datetime.now(timezone.utc),
            DataSubjectRequest.status.in_([
                DataSubjectRequestStatus.PENDING,
                DataSubjectRequestStatus.VERIFIED,
                DataSubjectRequestStatus.PROCESSING
            ])
        ).order_by(DataSubjectRequest.sla_due_at.asc()).all()


class ComplianceReportService:
    """Service for generating compliance reports"""
    
    @staticmethod
    def generate_report_number() -> str:
        """Generate a unique report number"""
        year = datetime.now(timezone.utc).year
        month = datetime.now(timezone.utc).month
        count = ComplianceReport.query.filter(
            db.extract('year', ComplianceReport.created_at) == year,
            db.extract('month', ComplianceReport.created_at) == month
        ).count()
        return f"CRPT-{year}{month:02d}-{count + 1:05d}"
    
    @staticmethod
    def create_report(
        report_type: ComplianceReportType,
        title: str,
        description: str,
        created_by: int,
        parameters: Optional[Dict[str, Any]] = None,
        date_range_start: Optional[datetime] = None,
        date_range_end: Optional[datetime] = None
    ) -> ComplianceReport:
        """Create a new compliance report"""
        report = ComplianceReport(
            public_id=str(uuid.uuid4()),
            report_number=ComplianceReportService.generate_report_number(),
            report_type=report_type,
            title=title,
            description=description,
            parameters=json.dumps(parameters) if parameters else None,
            date_range_start=date_range_start,
            date_range_end=date_range_end,
            status='draft',
            created_by=created_by
        )
        
        db.session.add(report)
        db.session.commit()
        
        # Log audit
        ForensicAuditService.log_action(
            action='create_compliance_report',
            user_id=created_by,
            resource_type='compliance_report',
            resource_id=report.id,
            details={
                'report_number': report.report_number,
                'report_type': report_type.value
            }
        )
        
        return report
    
    @staticmethod
    def generate_report_data(
        report_id: int,
        report_data: Dict[str, Any],
        summary: str,
        findings: Optional[str] = None,
        recommendations: Optional[str] = None
    ) -> Optional[ComplianceReport]:
        """Generate report data"""
        report = ComplianceReport.query.get(report_id)
        if not report:
            return None
        
        report.report_data = json.dumps(report_data)
        report.summary = summary
        report.findings = findings
        report.recommendations = recommendations
        report.status = 'generated'
        report.updated_at = datetime.now(timezone.utc)
        
        db.session.commit()
        
        return report
    
    @staticmethod
    def approve_report(
        report_id: int,
        approved_by: int
    ) -> Optional[ComplianceReport]:
        """Approve a compliance report"""
        report = ComplianceReport.query.get(report_id)
        if not report:
            return None
        
        report.status = 'approved'
        report.approved_by = approved_by
        report.approved_at = datetime.now(timezone.utc)
        report.updated_at = datetime.now(timezone.utc)
        
        db.session.commit()
        
        # Log audit
        ForensicAuditService.log_action(
            action='approve_compliance_report',
            user_id=approved_by,
            resource_type='compliance_report',
            resource_id=report.id,
            details={
                'report_number': report.report_number
            }
        )
        
        return report
    
    @staticmethod
    def get_reports_by_type(report_type: ComplianceReportType) -> List[ComplianceReport]:
        """Get reports by type"""
        return ComplianceReport.query.filter_by(report_type=report_type).order_by(
            ComplianceReport.created_at.desc()
        ).all()


class ComplianceChecker:
    """
    Central compliance checker class.
    Can be used for Organisations (KYB) or Individuals (KYC).
    Handles compliance enforcement and logs every decision.
    """

    def __init__(self, entity, actor_id=None):
        """
        entity: Organisation or Individual instance
        actor_id: ID of the user/admin/system making the compliance check
        """
        self.entity = entity
        self.actor_id = actor_id

    def _log_decision(self, requirement_key, decision):
        """
        Internal helper: record every compliance decision in ComplianceAuditLog.
        """
        from app.admin.compliance.models import ComplianceAuditLog
        log = ComplianceAuditLog(
            entity_id=self.entity.id,
            entity_type=self.entity.__class__.__name__.lower(),  # "organisation" or "user"
            operation=requirement_key,
            decision=decision,
            requirement_key=requirement_key,
            compliance_level=self.compliance_level(),
            risk_tier=self.risk_tier(),
            context={"status": self.status_light()},
            decided_by=self.actor_id,
        )
        db.session.add(log)
        db.session.commit()

    def can_perform_operation(self, requirement_key):
        """
        Check if entity can perform a given operation
        based on compliance settings and verification state.
        Logs the decision automatically.
        """
        from app.identity.models import ComplianceSettings
        setting = ComplianceSettings.query.filter_by(requirement=requirement_key).first()
        if not setting or not setting.is_enabled:
            decision = "allowed"
            self._log_decision(requirement_key, decision)
            return True

        if setting.enforcement_level == "mandatory":
            result = self.entity.is_fully_verified()
        elif setting.enforcement_level == "conditional":
            result = self.entity.has_partial_verification()
        else:
            result = True

        decision = "allowed" if result else "blocked"
        self._log_decision(requirement_key, decision)
        return result

    def risk_tier(self):
        """
        Return a categorical risk tier: low, medium, high.
        Based on verification status and expired docs/licenses.
        """
        if self.entity.is_fully_verified() and not getattr(self.entity, "has_expired_license", False) and not getattr(self.entity, "has_expired_document", False):
            return "low"
        elif self.entity.has_partial_verification() or getattr(self.entity, "has_expired_document", False):
            return "medium"
        else:
            return "high"

    def compliance_level(self):
        """
        Return a progressive compliance level (0-3).
        Level 0: Registered only
        Level 1: Partial verification
        Level 2: Fully verified
        Level 3: Fully verified + controllers + licenses
        """
        if self.entity.is_fully_verified() and getattr(self.entity, "controllers", None) and getattr(self.entity, "licenses", None):
            return 3
        elif self.entity.is_fully_verified():
            return 2
        elif self.entity.has_partial_verification():
            return 1
        else:
            return 0

    def capabilities(self):
        """
        Return a dictionary of capability flags for operations.
        Used to gate features dynamically.
        """
        return {
            "can_list_offers": True,  # always allowed
            "can_receive_payments": self.entity.has_partial_verification(),
            "can_withdraw_funds": self.entity.is_fully_verified(),
        }

    def status_light(self):
        """
        Return a traffic light style compliance status (green/amber/red).
        Useful for dashboards and admin views.
        """
        if self.entity.is_fully_verified():
            return "green"
        elif self.entity.has_partial_verification():
            return "amber"
        else:
            return "red"


# Utility functions for compliance checking

def can_perform_operation_util(entity, requirement_key):
    """
    Check if an entity (Organisation or Individual) can perform a given operation
    based on compliance settings and verification state.
    """
    from app.identity.models import ComplianceSettings
    setting = ComplianceSettings.query.filter_by(requirement=requirement_key).first()
    if not setting or not setting.is_enabled:
        return True  # requirement disabled

    if setting.enforcement_level == "mandatory":
        return entity.is_fully_verified()
    elif setting.enforcement_level == "conditional":
        return entity.has_partial_verification()
    else:
        return True  # optional


def compliance_risk_tier(entity):
    """
    Return a categorical risk tier: low, medium, high.
    """
    if entity.is_fully_verified() and not getattr(entity, "has_expired_license", False) and not getattr(entity, "has_expired_document", False):
        return "low"
    elif entity.has_partial_verification() or getattr(entity, "has_expired_document", False):
        return "medium"
    else:
        return "high"


def compliance_level_util(entity):
    """
    Return a progressive compliance level (0-3).
    Level 0: Registered only
    Level 1: Partial verification
    Level 2: Fully verified
    Level 3: Fully verified + controllers + licenses
    """
    if entity.is_fully_verified() and getattr(entity, "controllers", None) and getattr(entity, "licenses", None):
        return 3
    elif entity.is_fully_verified():
        return 2
    elif entity.has_partial_verification():
        return 1
    else:
        return 0


def compliance_capabilities(entity):
    """
    Return a dictionary of capability flags for operations.
    These flags can be used to gate features dynamically.
    """
    return {
        "can_list_offers": True,  # always allowed
        "can_receive_payments": entity.has_partial_verification(),
        "can_withdraw_funds": entity.is_fully_verified(),
    }


def compliance_status_light(entity):
    """
    Return a traffic light style compliance status (green/amber/red).
    """
    if entity.is_fully_verified():
        return "green"
    elif entity.has_partial_verification():
        return "amber"
    else:
        return "red"
