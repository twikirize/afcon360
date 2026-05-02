"""
Compliance routes for regulatory compliance and case management
"""
from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for
from flask_login import login_required, current_user
from app.auth.decorators import require_role
from app.extensions import db
from app.admin.compliance.models import (
    ComplianceCase, DataSubjectRequest, ComplianceReport,
    ComplianceCaseStatus, ComplianceCasePriority, ComplianceCaseType,
    DataSubjectRequestType, DataSubjectRequestStatus,
    ComplianceReportType
)
from app.admin.compliance.services import (
    ComplianceCaseService, DataSubjectRequestService, ComplianceReportService
)
from app.kyc.models import KycRecord
from app.kyc.services import KycService
# from app.wallet.models import PayoutRequest  # DELETED - will be rebuilt in new architecture
from app.identity.models.organisation import Organisation
from app.admin.models import ContentFlag
from datetime import datetime, timezone

compliance_bp = Blueprint('compliance', __name__, url_prefix='/compliance')

@compliance_bp.route('/dashboard')
@login_required
@require_role('compliance_officer', 'admin', 'super_admin', 'owner')
def dashboard():
    """Compliance main dashboard"""
    # Get statistics
    case_stats = ComplianceCaseService.get_case_statistics()
    
    # Get pending KYC verifications
    pending_kyc = KycRecord.query.filter_by(status='pending').order_by(
        KycRecord.submitted_at.desc()
    ).limit(10).all()
    
    # Get pending payout requests
    # pending_payouts = PayoutRequest.query.filter_by(status='pending').order_by(
    #     PayoutRequest.created_at.desc()
    # ).limit(10).all()
    pending_payouts = []  # DISABLED - PayoutRequest model deleted
    
    # Get pending organisations
    pending_orgs = Organisation.query.filter_by(
        verification_status='pending'
    ).order_by(Organisation.created_at.desc()).limit(10).all()
    
    # Get open cases
    open_cases = ComplianceCaseService.get_cases_by_status(ComplianceCaseStatus.OPEN)
    
    # Get overdue cases
    overdue_cases = ComplianceCaseService.get_overdue_cases()
    
    # Get pending data subject requests
    pending_dsr = DataSubjectRequestService.get_requests_by_status(DataSubjectRequestStatus.PENDING)
    
    return render_template('admin/compliance/dashboard.html',
                          case_stats=case_stats,
                          pending_kyc=pending_kyc,
                          pending_payouts=pending_payouts,
                          pending_orgs=pending_orgs,
                          open_cases=open_cases,
                          overdue_cases=overdue_cases,
                          pending_dsr=pending_dsr,
                          title="Compliance Dashboard")


@compliance_bp.route('/kyc-queue')
@login_required
@require_role('compliance_officer', 'admin', 'super_admin', 'owner')
def kyc_queue():
    """KYC compliance queue"""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    status = request.args.get('status', 'pending')
    
    query = KycRecord.query
    
    if status != 'all':
        query = query.filter_by(status=status)
    
    kyc_records = query.order_by(
        KycRecord.submitted_at.desc()
    ).paginate(page=page, per_page=per_page, error_out=False)
    
    return render_template('admin/compliance/kyc_queue.html',
                          kyc_records=kyc_records,
                          status=status,
                          title="KYC Queue")


@compliance_bp.route('/kyc/<int:kyc_id>')
@login_required
@require_role('compliance_officer', 'admin', 'super_admin', 'owner')
def view_kyc(kyc_id):
    """View KYC record details"""
    kyc_record = KycRecord.query.get_or_404(kyc_id)
    
    # Get related compliance case if exists
    compliance_case = None
    if kyc_record.compliance_case_id:
        compliance_case = ComplianceCase.query.get(kyc_record.compliance_case_id)
    
    return render_template('admin/compliance/view_kyc.html',
                          kyc_record=kyc_record,
                          compliance_case=compliance_case,
                          title="View KYC")


@compliance_bp.route('/kyc/<int:kyc_id>/action', methods=['POST'])
@login_required
@require_role('compliance_officer', 'admin', 'super_admin', 'owner')
def kyc_action(kyc_id):
    """Handle KYC compliance actions"""
    action = request.form.get('action')
    notes = request.form.get('notes', '')
    
    if action == 'approve':
        KycService.compliance_approve_kyc(kyc_id, current_user.id, notes)
        flash(f'KYC record {kyc_id} approved from compliance.', 'success')
    elif action == 'reject':
        reason = request.form.get('rejection_reason', notes)
        KycService.compliance_reject_kyc(kyc_id, current_user.id, reason)
        flash(f'KYC record {kyc_id} rejected from compliance.', 'warning')
    elif action == 'escalate':
        reason = request.form.get('escalation_reason', notes)
        KycService.refer_to_compliance(kyc_id, current_user.id, reason)
        flash(f'KYC record {kyc_id} escalated.', 'warning')
    else:
        flash('Invalid action.', 'danger')
    
    return redirect(url_for('compliance.kyc_queue'))


@compliance_bp.route('/payouts')
@login_required
@require_role('compliance_officer', 'admin', 'super_admin', 'owner')
def payouts():
    """Payout compliance queue"""
    # DISABLED - PayoutRequest model deleted during architecture rebuild
    flash('Payout module temporarily unavailable during architecture rebuild', 'warning')
    return redirect(url_for('compliance.dashboard'))


@compliance_bp.route('/payout/<int:payout_id>')
@login_required
@require_role('compliance_officer', 'admin', 'super_admin', 'owner')
def view_payout(payout_id):
    """View payout request details"""
    # DISABLED - PayoutRequest model deleted during architecture rebuild
    flash('Payout module temporarily unavailable during architecture rebuild', 'warning')
    return redirect(url_for('compliance.dashboard'))


@compliance_bp.route('/payout/<int:payout_id>/action', methods=['POST'])
@login_required
@require_role('compliance_officer', 'admin', 'super_admin', 'owner')
def payout_action(payout_id):
    """Handle payout compliance actions"""
    # DISABLED - PayoutRequest model deleted during architecture rebuild
    flash('Payout module temporarily unavailable during architecture rebuild', 'warning')
    return redirect(url_for('compliance.dashboard'))


@compliance_bp.route('/aml-queue')
@login_required
@require_role('compliance_officer', 'admin', 'super_admin', 'owner')
def aml_queue():
    """AML monitoring queue"""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    
    # Get AML alert cases
    aml_cases = ComplianceCase.query.filter_by(
        case_type=ComplianceCaseType.AML_ALERT
    ).order_by(
        ComplianceCase.created_at.desc()
    ).paginate(page=page, per_page=per_page, error_out=False)
    
    return render_template('admin/compliance/aml_queue.html',
                          aml_cases=aml_cases,
                          title="AML Queue")


@compliance_bp.route('/escalations')
@login_required
@require_role('compliance_officer', 'admin', 'super_admin', 'owner')
def escalations():
    """Escalations from moderators"""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    
    # Get escalated flags that have compliance cases
    escalated_flags = ContentFlag.query.filter(
        ContentFlag.referred_to_compliance == True
    ).order_by(
        ContentFlag.referred_at.desc()
    ).paginate(page=page, per_page=per_page, error_out=False)
    
    return render_template('admin/compliance/escalations.html',
                          escalated_flags=escalated_flags,
                          title="Escalations")


@compliance_bp.route('/organisations')
@login_required
@require_role('compliance_officer', 'admin', 'super_admin', 'owner')
def organisations():
    """Organisation KYB compliance queue"""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    status = request.args.get('status', 'pending')
    
    query = Organisation.query
    
    if status != 'all':
        query = query.filter_by(verification_status=status)
    
    organisations = query.order_by(
        Organisation.created_at.desc()
    ).paginate(page=page, per_page=per_page, error_out=False)
    
    return render_template('admin/compliance/organisations.html',
                          organisations=organisations,
                          status=status,
                          title="Organisation Queue")


@compliance_bp.route('/organisation/<int:org_id>')
@login_required
@require_role('compliance_officer', 'admin', 'super_admin', 'owner')
def view_org(org_id):
    """View organisation details"""
    org = Organisation.query.get_or_404(org_id)
    
    # Get related compliance case if exists
    compliance_case = None
    if org.compliance_case_id:
        compliance_case = ComplianceCase.query.get(org.compliance_case_id)
    
    return render_template('admin/compliance/view_org.html',
                          org=org,
                          compliance_case=compliance_case,
                          title="View Organisation")


@compliance_bp.route('/organisation/<int:org_id>/action', methods=['POST'])
@login_required
@require_role('compliance_officer', 'admin', 'super_admin', 'owner')
def org_action(org_id):
    """Handle organisation compliance actions"""
    from app.admin.compliance.services import ComplianceCaseService
    
    action = request.form.get('action')
    notes = request.form.get('notes', '')
    
    org = Organisation.query.get_or_404(org_id)
    
    if action == 'approve':
        org.compliance_status = 'approved'
        org.compliance_reviewed_at = datetime.now(timezone.utc)
        org.compliance_reviewed_by = current_user.id
        org.compliance_notes = notes
        flash(f'Organisation {org_id} approved from compliance.', 'success')
    elif action == 'reject':
        org.compliance_status = 'rejected'
        org.compliance_reviewed_at = datetime.now(timezone.utc)
        org.compliance_reviewed_by = current_user.id
        org.rejection_reason = request.form.get('rejection_reason', notes)
        flash(f'Organisation {org_id} rejected from compliance.', 'warning')
    elif action == 'escalate':
        reason = request.form.get('escalation_reason', notes)
        ComplianceCaseService.create_case(
            case_type=ComplianceCaseType.KYB_REVIEW,
            title=f'KYB Review - Organisation {org.org_id}',
            description=f'Organisation escalated for compliance review: {reason}',
            created_by=current_user.id,
            organisation_id=org_id,
            priority=ComplianceCasePriority.HIGH,
            escalated_from=current_user.id,
            escalation_reason=reason
        )
        flash(f'Organisation {org_id} escalated.', 'warning')
    else:
        flash('Invalid action.', 'danger')
    
    db.session.commit()
    return redirect(url_for('compliance.organisations'))


@compliance_bp.route('/licences')
@login_required
@require_role('compliance_officer', 'admin', 'super_admin', 'owner')
def licences():
    """License compliance queue"""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    
    # Get license review cases
    licence_cases = ComplianceCase.query.filter_by(
        case_type=ComplianceCaseType.LICENSE_REVIEW
    ).order_by(
        ComplianceCase.created_at.desc()
    ).paginate(page=page, per_page=per_page, error_out=False)
    
    return render_template('admin/compliance/licences.html',
                          licence_cases=licence_cases,
                          title="Licence Queue")


@compliance_bp.route('/data-requests')
@login_required
@require_role('compliance_officer', 'admin', 'super_admin', 'owner')
def data_requests():
    """Data subject requests queue"""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    status = request.args.get('status', 'pending')
    
    query = DataSubjectRequest.query
    
    if status != 'all':
        query = query.filter_by(status=status)
    
    requests = query.order_by(
        DataSubjectRequest.created_at.desc()
    ).paginate(page=page, per_page=per_page, error_out=False)
    
    return render_template('admin/compliance/data_requests.html',
                          requests=requests,
                          status=status,
                          title="Data Requests")


@compliance_bp.route('/data-request/<int:request_id>')
@login_required
@require_role('compliance_officer', 'admin', 'super_admin', 'owner')
def view_data_request(request_id):
    """View data subject request details"""
    dsr = DataSubjectRequest.query.get_or_404(request_id)
    
    return render_template('admin/compliance/view_data_request.html',
                          dsr=dsr,
                          title="View Data Request")


@compliance_bp.route('/data-request/<int:request_id>/action', methods=['POST'])
@login_required
@require_role('compliance_officer', 'admin', 'super_admin', 'owner')
def data_request_action(request_id):
    """Handle data subject request actions"""
    action = request.form.get('action')
    
    if action == 'verify':
        method = request.form.get('verification_method', 'manual')
        DataSubjectRequestService.verify_identity(request_id, current_user.id, method)
        flash(f'Identity verified for request {request_id}.', 'success')
    elif action == 'assign':
        assigned_to = request.form.get('assigned_to', type=int)
        if assigned_to:
            DataSubjectRequestService.assign_request(request_id, assigned_to, current_user.id)
            flash(f'Request {request_id} assigned.', 'success')
    elif action == 'complete':
        response = request.form.get('response', '')
        DataSubjectRequestService.complete_request(request_id, current_user.id, response)
        flash(f'Request {request_id} completed.', 'success')
    elif action == 'reject':
        reason = request.form.get('rejection_reason', '')
        DataSubjectRequestService.reject_request(request_id, current_user.id, reason)
        flash(f'Request {request_id} rejected.', 'warning')
    else:
        flash('Invalid action.', 'danger')
    
    return redirect(url_for('compliance.data_requests'))


@compliance_bp.route('/reports')
@login_required
@require_role('compliance_officer', 'admin', 'super_admin', 'owner')
def reports():
    """Compliance reports list"""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    
    reports = ComplianceReport.query.order_by(
        ComplianceReport.created_at.desc()
    ).paginate(page=page, per_page=per_page, error_out=False)
    
    return render_template('admin/compliance/reports.html',
                          reports=reports,
                          title="Compliance Reports")


@compliance_bp.route('/reports/generate', methods=['GET', 'POST'])
@login_required
@require_role('compliance_officer', 'admin', 'super_admin', 'owner')
def generate_report():
    """Generate compliance report"""
    if request.method == 'POST':
        report_type = request.form.get('report_type')
        title = request.form.get('title')
        description = request.form.get('description', '')
        
        report_type_enum = ComplianceReportType(report_type) if report_type else ComplianceReportType.KYC_SUMMARY
        
        report = ComplianceReportService.create_report(
            report_type=report_type_enum,
            title=title,
            description=description,
            created_by=current_user.id
        )
        
        flash(f'Report {report.report_number} generated successfully.', 'success')
        return redirect(url_for('compliance.reports'))
    
    return render_template('admin/compliance/generate_report.html',
                          report_types=ComplianceReportType,
                          title="Generate Report")


@compliance_bp.route('/case/<int:case_id>')
@login_required
@require_role('compliance_officer', 'admin', 'super_admin', 'owner')
def view_case(case_id):
    """View compliance case details"""
    case = ComplianceCase.query.get_or_404(case_id)
    
    return render_template('admin/compliance/view_case.html',
                          case=case,
                          title="View Case")


@compliance_bp.route('/case/<int:case_id>/action', methods=['POST'])
@login_required
@require_role('compliance_officer', 'admin', 'super_admin', 'owner')
def case_action(case_id):
    """Handle compliance case actions"""
    action = request.form.get('action')
    notes = request.form.get('notes', '')
    
    if action == 'assign':
        assigned_to = request.form.get('assigned_to', type=int)
        if assigned_to:
            ComplianceCaseService.assign_case(case_id, assigned_to, current_user.id)
            flash(f'Case {case_id} assigned.', 'success')
    elif action == 'approve':
        ComplianceCaseService.update_case_status(case_id, ComplianceCaseStatus.APPROVED, current_user.id, notes)
        flash(f'Case {case_id} approved.', 'success')
    elif action == 'reject':
        ComplianceCaseService.update_case_status(case_id, ComplianceCaseStatus.REJECTED, current_user.id, notes)
        flash(f'Case {case_id} rejected.', 'warning')
    elif action == 'escalate':
        reason = request.form.get('escalation_reason', notes)
        new_priority = request.form.get('new_priority')
        priority_enum = ComplianceCasePriority(new_priority) if new_priority else None
        ComplianceCaseService.escalate_case(case_id, current_user.id, reason, priority_enum)
        flash(f'Case {case_id} escalated.', 'warning')
    else:
        flash('Invalid action.', 'danger')
    
    return redirect(url_for('compliance.dashboard'))


@compliance_bp.route('/cases')
@login_required
@require_role('compliance_officer', 'admin', 'super_admin', 'owner')
def cases():
    """All compliance cases"""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    status = request.args.get('status', 'all')
    
    query = ComplianceCase.query
    
    if status != 'all':
        query = query.filter_by(status=ComplianceCaseStatus(status))
    
    cases = query.order_by(
        ComplianceCase.created_at.desc()
    ).paginate(page=page, per_page=per_page, error_out=False)
    
    return render_template('admin/compliance/cases.html',
                          cases=cases,
                          status=status,
                          title="Compliance Cases")


@compliance_bp.route('/case-history')
@login_required
@require_role('compliance_officer', 'admin', 'super_admin', 'owner')
def case_history():
    """Case history and audit trail"""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)
    
    # Get resolved/closed cases
    history_cases = ComplianceCase.query.filter(
        ComplianceCase.status.in_([
            ComplianceCaseStatus.APPROVED,
            ComplianceCaseStatus.REJECTED,
            ComplianceCaseStatus.CLOSED
        ])
    ).order_by(
        ComplianceCase.resolved_at.desc()
    ).paginate(page=page, per_page=per_page, error_out=False)
    
    return render_template('admin/compliance/case_history.html',
                          cases=history_cases,
                          title="Case History")
