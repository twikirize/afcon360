"""
Compliance routes for regulatory compliance and case management
"""
import uuid
from datetime import datetime, timezone, timedelta
from types import SimpleNamespace
from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for, abort, current_app
from flask_login import login_required, current_user
from app.auth.decorators import require_role
from app.extensions import db
from app.identity.models.user import User
from app.wallet.models.fraud_alert import FraudAlert
from app.wallet.models.transaction import TransactionModel
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
from app.identity.models.kyb import OrganisationKYBDocument
from app.notifications.services import NotificationService
from app.kyc.reupload import (
    get_organisation_reupload_requests,
    set_individual_reupload_request,
    set_organisation_reupload_request,
)
from app.admin.models import ContentFlag
from app.compliance.aml_regulatory_models import (
    JurisdictionProfile, RegulatoryReport, CtrAlert, TerminatedEntity,
    OrganisationAmlProfile, MonitoringScenario, AmlBacktestRun,
    AmlTrainingRecord, AmlAttestation, RetentionPolicy,
)
from app.compliance import aml_regulatory_service as aml_reg
from datetime import datetime, timezone

compliance_bp = Blueprint('compliance', __name__, url_prefix='/compliance')


def _sidebar_stats() -> dict:
    """Build the stats dict used by base_compliance.html sidebar badges."""
    case_stats = ComplianceCaseService.get_case_statistics()
    pending_dsr = DataSubjectRequestService.get_requests_by_status(DataSubjectRequestStatus.PENDING)
    return {
        'kyc_pending': KycRecord.query.filter_by(status='pending').count(),
        'orgs_pending': Organisation.query.filter_by(verification_status='pending').count(),
        'payouts_pending': 0,
        'aml_alerts': 0,
        'open_cases': case_stats.get('open', 0),
        'escalations': 0,
        'data_requests': len(pending_dsr) if hasattr(pending_dsr, '__len__') else 0,
    }


@compliance_bp.route('/dashboard')
@login_required
@require_role('compliance_officer', 'admin', 'super_admin', 'owner')
def dashboard():
    """Compliance main dashboard"""
    # Get statistics
    case_stats = ComplianceCaseService.get_case_statistics()
    
    # Get pending KYC verifications
    pending_kyc = KycRecord.query.filter_by(status='pending').order_by(
        KycRecord.created_at.desc()
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
    
    # Build stats dict for sidebar badges
    stats = {
        'kyc_pending': len(pending_kyc),
        'orgs_pending': len(pending_orgs),
        'payouts_pending': len(pending_payouts),
        'aml_alerts': 0,
        'open_cases': case_stats.get('open', 0),
        'escalations': 0,
        'data_requests': len(pending_dsr) if hasattr(pending_dsr, '__len__') else 0,
    }
    
    return render_template('admin/compliance/dashboard.html',
                          stats=stats,
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
        KycRecord.created_at.desc()
    ).paginate(page=page, per_page=per_page, error_out=False)
    
    # Get case statistics and pending DSRs for stats badges
    case_stats = ComplianceCaseService.get_case_statistics()
    pending_dsr = DataSubjectRequestService.get_requests_by_status(DataSubjectRequestStatus.PENDING)

    # Build stats dict for sidebar badges
    stats = {
        'kyc_pending': KycRecord.query.filter_by(status='pending').count(),
        'orgs_pending': Organisation.query.filter_by(verification_status='pending').count(),
        'payouts_pending': 0,
        'aml_alerts': 0,
        'open_cases': case_stats.get('open', 0),
        'escalations': 0,
        'data_requests': len(pending_dsr) if hasattr(pending_dsr, '__len__') else 0,
    }

    return render_template('admin/compliance/kyc_queue.html',
                          items=kyc_records.items,
                          pagination=kyc_records,
                          status=status,
                          stats=stats,
                          title="KYC Queue")


@compliance_bp.route('/kyc/<kyc_id_or_uuid>')
@login_required
@require_role('compliance_officer', 'admin', 'super_admin', 'owner')
def view_kyc(kyc_id_or_uuid):
    """View KYC record details"""
    kyc_record = None
    if str(kyc_id_or_uuid).isdigit():
        kyc_record = KycRecord.query.get(int(kyc_id_or_uuid))

    if not kyc_record:
        kyc_record = KycRecord.query.filter_by(reference_code=str(kyc_id_or_uuid)).first()

    if not kyc_record:
        # Try looking up user by public_id and get latest kyc record
        from app.identity.models.user import User
        user = User.query.filter_by(public_id=str(kyc_id_or_uuid)).first()
        if user:
            kyc_record = KycRecord.query.filter_by(user_id=user.id).order_by(KycRecord.created_at.desc()).first()

    if not kyc_record:
        abort(404)

    kyc_id = kyc_record.id
    
    # Get related compliance case if exists
    compliance_case = None
    if kyc_record.compliance_case_id:
        compliance_case = db.session.get(ComplianceCase, kyc_record.compliance_case_id)

    # Resolve document/selfie URLs so historical bare media_id references
    # (stored before async processing finished) still render in the review UI.
    doc_url = _resolve_kyc_media_url(kyc_record.document_url)
    selfie_url = _resolve_kyc_media_url(kyc_record.selfie_url)

    return render_template('admin/compliance/view_kyc.html',
                          kyc_record=kyc_record,
                          doc_url=doc_url,
                          selfie_url=selfie_url,
                          compliance_case=compliance_case,
                          stats=_sidebar_stats(),
                          title="View KYC")


@compliance_bp.route('/kyc/<kyc_id>', endpoint='view_kyc_legacy')
@login_required
@require_role('compliance_officer', 'admin', 'super_admin', 'owner')
def view_kyc_legacy(kyc_id):
    """Legacy route for view_kyc accepting kyc_id"""
    return view_kyc(kyc_id)


def _resolve_kyc_media_url(value):
    """Return a servable URL for a KYC document reference.

    Stored values may be: a full URL/path, or a bare media public_id (UUID)
    from uploads that completed before async URL generation finished.
    """
    if not value:
        return None
    if '/' in value:
        return value
    try:
        from app.media.models import Media
        from app.media.storage import get_storage_backend
        media = db.session.query(Media).filter(
            Media.public_id == value, Media.is_deleted == False
        ).first()
        if media and media.storage_key:
            return get_storage_backend().get_url(media.storage_key)
    except Exception:
        pass
    return value


@compliance_bp.route('/kyc/<kyc_id_or_uuid>/action', methods=['POST'], endpoint='kyc_action_uuid')
@compliance_bp.route('/kyc/<kyc_id>/action', methods=['POST'], endpoint='kyc_action')
@login_required
@require_role('compliance_officer', 'admin', 'super_admin', 'owner')
def kyc_action(kyc_id_or_uuid=None, kyc_id=None, **route_values):
    """Handle KYC compliance actions"""
    identifier = (
        kyc_id_or_uuid
        if kyc_id_or_uuid is not None
        else kyc_id if kyc_id is not None else route_values.get('id')
    )
    if identifier is None:
        abort(400)

    kyc_record = None
    if str(identifier).isdigit():
        kyc_record = KycRecord.query.get(int(identifier))
    if not kyc_record:
        kyc_record = KycRecord.query.filter_by(reference_code=str(identifier)).first()
    if not kyc_record:
        from app.identity.models.user import User
        user = User.query.filter_by(public_id=str(identifier)).first()
        if user:
            kyc_record = KycRecord.query.filter_by(user_id=user.id).order_by(KycRecord.created_at.desc()).first()
    if not kyc_record:
        abort(404)
    kyc_id = kyc_record.id

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
    elif action == 'assign_to_me':
        record = db.session.get(KycRecord, kyc_id)
        if record and record.status == 'pending':
            record.status = 'in_review'
            record.checked_by = str(current_user.id)
            db.session.commit()
            flash(f'KYC record {kyc_id} assigned to you for review.', 'info')
        else:
            flash('KYC record is not available for assignment.', 'warning')
    elif action == 'request_reupload':
        record = db.session.get(KycRecord, kyc_id)
        document_key = request.form.get('document_key', 'document').strip()
        reason = request.form.get('reupload_reason', notes).strip()
        if not record:
            abort(404)
        if record.status not in ('pending', 'in_review', 'reupload_requested'):
            flash('A replacement can only be requested while this submission is under review.', 'warning')
        elif document_key not in ('document', 'selfie'):
            flash('Choose either the identity document or selfie as the replacement target.', 'danger')
        elif not reason:
            flash('Explain why the selected document must be uploaded again.', 'danger')
        else:
            record.compliance_notes = set_individual_reupload_request(
                record.compliance_notes,
                document_key=document_key,
                reason=reason,
                requested_by=current_user.id,
            )
            record.compliance_status = 'reupload_requested'
            record.status = 'pending'
            record.compliance_reviewed_at = datetime.now(timezone.utc)
            record.compliance_reviewed_by = current_user.id
            record.checked_by = None
            db.session.commit()
            try:
                NotificationService.notify_kyc_reupload_requested(
                    user_id=record.user_id,
                    document_label=(
                        'primary identity document'
                        if document_key == 'document' else 'verification selfie'
                    ),
                    reason=reason,
                )
            except Exception:
                current_app.logger.exception('Could not notify user of KYC replacement request')
            flash('The user has been asked to replace only the selected document.', 'info')
    elif action == 'revert' or action == 'recancel':
        reason = request.form.get('revert_reason', notes)
        if not reason:
            reason = 'Administrative re-cancellation due to document invalidity or discrepancy.'
        try:
            KycService.revert_kyc(kyc_id, current_user.id, reason,
                                 ip_address=request.remote_addr,
                                 user_agent=request.user_agent.string if request.user_agent else None)
            flash(f'KYC record {kyc_id} has been successfully re-cancelled and reverted. The user has been notified to fulfill requirements.', 'warning')
        except Exception as e:
            current_app.logger.error(f"Failed to revert KYC {kyc_id}: {e}", exc_info=True)
            flash(f'Failed to revert KYC: {str(e)}', 'danger')
    else:
        flash('Invalid action.', 'danger')
    
    return redirect(url_for('admin.compliance.kyc_queue'))


@compliance_bp.route('/payouts')
@login_required
@require_role('compliance_officer', 'admin', 'super_admin', 'owner')
def payouts():
    """Payout compliance queue"""
    # DISABLED - PayoutRequest model deleted during architecture rebuild
    flash('Payout module temporarily unavailable during architecture rebuild', 'warning')
    return redirect(url_for('admin.compliance.dashboard'))


@compliance_bp.route('/payout/<int:payout_id>')
@login_required
@require_role('compliance_officer', 'admin', 'super_admin', 'owner')
def view_payout(payout_id):
    """View payout request details"""
    # DISABLED - PayoutRequest model deleted during architecture rebuild
    flash('Payout module temporarily unavailable during architecture rebuild', 'warning')
    return redirect(url_for('admin.compliance.dashboard'))


@compliance_bp.route('/payout/<int:payout_id>/action', methods=['POST'])
@login_required
@require_role('compliance_officer', 'admin', 'super_admin', 'owner')
def payout_action(payout_id):
    """Handle payout compliance actions"""
    # DISABLED - PayoutRequest model deleted during architecture rebuild
    flash('Payout module temporarily unavailable during architecture rebuild', 'warning')
    return redirect(url_for('admin.compliance.dashboard'))


@compliance_bp.route('/aml-queue')
@login_required
@require_role('compliance_officer', 'admin', 'super_admin', 'owner')
def aml_queue():
    """AML monitoring queue — suspicious activity, patterns and flagged users."""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)

    # Active fraud alerts drive the AML feed (suspicious activity monitoring).
    active_statuses = ['open', 'escalated', 'reviewing']
    fraud_query = FraudAlert.query.filter(
        FraudAlert.status.in_(active_statuses)
    )

    # High-risk transactions (alerts joined with their transaction where present).
    fraud_alerts_page = fraud_query.order_by(
        FraudAlert.risk_score.desc(),
        FraudAlert.created_at.desc()
    ).paginate(page=page, per_page=per_page, error_out=False)

    high_risk_transactions = []
    for fa in fraud_alerts_page.items:
        tx = TransactionModel.query.get(fa.transaction_id) if fa.transaction_id else None
        user = User.query.get(fa.user_id)
        high_risk_transactions.append(SimpleNamespace(
            id=fa.transaction_id,
            user=user,
            amount=float(tx.amount) if tx and tx.amount is not None else 0.0,
            currency=tx.currency if tx else 'UGX',
            transaction_type=fa.action,
            created_at=fa.created_at,
            risk_score=int(fa.risk_score) if fa.risk_score is not None else 0,
            fraud_alert=fa,
        ))

    # Pattern alerts — aggregate active fraud alerts by detected pattern.
    active_alerts = fraud_query.all()
    pattern_map = {}
    for fa in active_alerts:
        for pattern in (fa.patterns or []):
            entry = pattern_map.setdefault(pattern, {
                'user_ids': set(),
                'count': 0,
                'max_score': 0,
                'detected_at': None,
            })
            entry['count'] += 1
            entry['user_ids'].add(fa.user_id)
            score = int(fa.risk_score) if fa.risk_score is not None else 0
            entry['max_score'] = max(entry['max_score'], score)
            if entry['detected_at'] is None or fa.created_at > entry['detected_at']:
                entry['detected_at'] = fa.created_at

    pattern_alerts = []
    for pattern, data in pattern_map.items():
        severity = ('critical' if data['max_score'] >= 80
                    else 'high' if data['max_score'] >= 50
                    else 'medium')
        pattern_alerts.append(SimpleNamespace(
            pattern_type=pattern,
            user_ids=list(data['user_ids']),
            users=[User.query.get(uid) for uid in data['user_ids'] if User.query.get(uid)],
            transaction_count=data['count'],
            severity=severity,
            detected_at=data['detected_at'],
        ))
    pattern_alerts.sort(key=lambda p: p.transaction_count, reverse=True)

    # Flagged users — distinct users with active high-risk alerts.
    flagged_user_rows = db.session.query(
        FraudAlert.user_id
    ).filter(
        FraudAlert.status.in_(['open', 'escalated'])
    ).distinct().all()

    flagged_users = []
    for (uid,) in flagged_user_rows:
        user = User.query.get(uid)
        if not user:
            continue
        max_score = db.session.query(
            db.func.max(FraudAlert.risk_score)
        ).filter(
            FraudAlert.user_id == uid,
            FraudAlert.status.in_(['open', 'escalated'])
        ).scalar() or 0
        flagged_users.append(SimpleNamespace(
            username=user.username,
            risk_score=int(max_score),
            public_id=user.public_id,
            user=user,
        ))
    flagged_users.sort(key=lambda u: u.risk_score, reverse=True)

    # Stats for the dashboard header.
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    critical_alerts = fraud_query.filter(FraudAlert.risk_score >= 80).count()
    high_risk_tx = fraud_query.filter(FraudAlert.risk_score >= 50).count()
    suspicious_users = len(flagged_users)
    total_volume = db.session.query(
        db.func.sum(TransactionModel.amount)
    ).filter(
        TransactionModel.created_at >= today_start
    ).scalar() or 0

    stats = {
        'kyc_pending': KycRecord.query.filter_by(status='pending').count(),
        'orgs_pending': Organisation.query.filter_by(verification_status='pending').count(),
        'payouts_pending': 0,
        'aml_alerts': high_risk_tx,
        'critical_alerts': critical_alerts,
        'high_risk_tx': high_risk_tx,
        'suspicious_users': suspicious_users,
        'total_volume': float(total_volume),
        'open_cases': ComplianceCaseService.get_case_statistics().get('open', 0),
        'escalations': 0,
        'data_requests': len(DataSubjectRequestService.get_requests_by_status(
            DataSubjectRequestStatus.PENDING
        )),
    }

    return render_template('admin/compliance/aml_queue.html',
                          high_risk_transactions=high_risk_transactions,
                          pattern_alerts=pattern_alerts,
                          flagged_users=flagged_users,
                          pagination=fraud_alerts_page,
                          stats=stats,
                          title="AML Queue")


@compliance_bp.route('/transaction/<tx_id>')
@login_required
@require_role('compliance_officer', 'admin', 'super_admin', 'owner')
def view_transaction(tx_id):
    """Investigate a specific transaction referenced by a fraud alert."""
    tx = TransactionModel.query.get(tx_id)
    if not tx:
        abort(404)

    related_alerts = FraudAlert.query.filter_by(
        transaction_id=str(tx_id)
    ).order_by(FraudAlert.risk_score.desc()).all()

    user = User.query.get(tx.user_id) if tx.user_id else None
    recipient = User.query.get(tx.recipient_user_id) if tx.recipient_user_id else None

    return render_template('admin/compliance/view_transaction.html',
                          tx=tx,
                          user=user,
                          recipient=recipient,
                          related_alerts=related_alerts,
                          stats=_sidebar_stats(),
                          title="Transaction Investigation")


@compliance_bp.route('/user-audit/<user_id>')
@login_required
@require_role('compliance_officer', 'admin', 'super_admin', 'owner')
def user_audit(user_id):
    """User audit profile for AML / compliance review (keyed by public_id)."""
    user = User.get_by_public_id(user_id)
    if not user:
        abort(404)

    fraud_alerts = FraudAlert.query.filter_by(user_id=user.id).order_by(
        FraudAlert.risk_score.desc(),
        FraudAlert.created_at.desc()
    ).limit(50).all()

    kyc_record = KycRecord.query.filter_by(user_id=user.id).order_by(
        KycRecord.created_at.desc()
    ).first()

    compliance_cases = ComplianceCase.query.filter(
        ComplianceCase.user_id == user.id
    ).order_by(
        ComplianceCase.created_at.desc()
    ).limit(50).all()

    return render_template('admin/compliance/user_audit.html',
                          user=user,
                          fraud_alerts=fraud_alerts,
                          kyc_record=kyc_record,
                          compliance_cases=compliance_cases,
                          stats=_sidebar_stats(),
                          title="User Audit")


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
                          stats=_sidebar_stats(),
                          title="Escalations")


@compliance_bp.route('/sar-filing', methods=['GET', 'POST'])
@login_required
@require_role('compliance_officer', 'admin', 'super_admin', 'owner')
def sar_filing():
    """Suspicious Activity Report (SAR) filing — separate workflow from escalations."""
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        description = request.form.get('description', '').strip()
        case_id = request.form.get('case_id', type=int)

        if not title:
            flash('SAR title is required.', 'danger')
        else:
            report = ComplianceReportService.create_report(
                report_type=ComplianceReportType.REGULATORY_FILING,
                title=title,
                description=description,
                created_by=current_user.id
            )
            flash(f'SAR {report.report_number} filed successfully.', 'success')
            return redirect(url_for('admin.compliance.sar_filing'))

    # Open AML alerts that may warrant a SAR
    aml_cases = ComplianceCase.query.filter_by(
        case_type=ComplianceCaseType.AML_ALERT
    ).order_by(
        ComplianceCase.priority.desc(),
        ComplianceCase.created_at.desc()
    ).limit(50).all()

    # Previously filed SARs
    sars = ComplianceReport.query.filter_by(
        report_type=ComplianceReportType.REGULATORY_FILING
    ).order_by(
        ComplianceReport.created_at.desc()
    ).limit(20).all()

    return render_template('admin/compliance/sar_filing.html',
                          aml_cases=aml_cases,
                          sars=sars,
                          stats=_sidebar_stats(),
                          title="SAR Filing")


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
    
    # Get case statistics and pending DSRs for stats badges
    case_stats = ComplianceCaseService.get_case_statistics()
    pending_dsr = DataSubjectRequestService.get_requests_by_status(DataSubjectRequestStatus.PENDING)

    # Build stats dict for sidebar badges
    stats = {
        'kyc_pending': KycRecord.query.filter_by(status='pending').count(),
        'orgs_pending': Organisation.query.filter_by(verification_status='pending').count(),
        'payouts_pending': 0,
        'aml_alerts': 0,
        'open_cases': case_stats.get('open', 0),
        'escalations': 0,
        'data_requests': len(pending_dsr) if hasattr(pending_dsr, '__len__') else 0,
    }

    return render_template('admin/compliance/organisations.html',
                          organisations=organisations.items,
                          pagination=organisations,
                          status=status,
                          stats=stats,
                          title="Organisation Queue")


@compliance_bp.route('/organisation/<int:org_id>')
@login_required
@require_role('compliance_officer', 'admin', 'super_admin', 'owner')
def view_org(org_id):
    """View organisation details"""
    org = Organisation.query.get_or_404(org_id)
    kyb_documents = OrganisationKYBDocument.query.filter_by(
        organisation_id=org.id,
        is_deleted=False,
    ).order_by(OrganisationKYBDocument.created_at.desc()).all()
    
    # Get related compliance case if exists
    compliance_case = None
    if org.compliance_case_id:
        compliance_case = db.session.get(ComplianceCase, org.compliance_case_id)
    
    return render_template('admin/compliance/view_org.html',
                          org=org,
                          kyb_documents=kyb_documents,
                          reupload_requests=(
                              get_organisation_reupload_requests(org.compliance_notes)
                          ),
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
    elif action == 'request_reupload':
        document_id = request.form.get('document_id', '').strip()
        document_type = request.form.get('document_type', '').strip()
        reason = request.form.get('reupload_reason', notes).strip()
        document = None
        if document_id.isdigit():
            document = OrganisationKYBDocument.query.filter_by(
                id=int(document_id),
                organisation_id=org.id,
                is_deleted=False,
            ).first()
        if not document:
            flash('Select an organisation document before requesting a replacement.', 'danger')
        elif document.verification_status not in ('pending', 'rejected'):
            flash('A replacement can only be requested for a document awaiting review.', 'warning')
        elif not reason:
            flash('Explain why the selected organisation document must be uploaded again.', 'danger')
        else:
            org.compliance_notes = set_organisation_reupload_request(
                org.compliance_notes,
                document_id=document.id,
                document_type=document_type or document.document_type,
                reason=reason,
                requested_by=current_user.id,
            )
            org.compliance_status = 'reupload_requested'
            org.verification_status = 'pending'
            org.compliance_reviewed_at = datetime.now(timezone.utc)
            org.compliance_reviewed_by = current_user.id
            db.session.commit()
            if org.primary_contact_user_id:
                try:
                    NotificationService.notify_kyc_reupload_requested(
                        user_id=org.primary_contact_user_id,
                        document_label=document_type or document.document_type,
                        reason=reason,
                        organisation_name=org.legal_name,
                    )
                except Exception:
                    current_app.logger.exception(
                        'Could not notify organisation contact of KYB replacement request'
                    )
            flash('The organisation contact has been asked to replace only the selected document.', 'info')
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
    return redirect(url_for('admin.compliance.organisations'))


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
    
    # Get case statistics and pending DSRs for stats badges
    case_stats = ComplianceCaseService.get_case_statistics()
    pending_dsr = DataSubjectRequestService.get_requests_by_status(DataSubjectRequestStatus.PENDING)

    # Build stats dict for sidebar badges
    stats = {
        'kyc_pending': KycRecord.query.filter_by(status='pending').count(),
        'orgs_pending': Organisation.query.filter_by(verification_status='pending').count(),
        'payouts_pending': 0,
        'aml_alerts': 0,
        'open_cases': case_stats.get('open', 0),
        'escalations': 0,
        'data_requests': len(pending_dsr) if hasattr(pending_dsr, '__len__') else 0,
    }

    return render_template('admin/compliance/licences.html',
                          licence_cases=licence_cases,
                          stats=stats,
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
    
    # Get case statistics and pending DSRs for stats badges
    case_stats = ComplianceCaseService.get_case_statistics()
    pending_dsr = DataSubjectRequestService.get_requests_by_status(DataSubjectRequestStatus.PENDING)

    # Build stats dict for sidebar badges
    stats = {
        'kyc_pending': KycRecord.query.filter_by(status='pending').count(),
        'orgs_pending': Organisation.query.filter_by(verification_status='pending').count(),
        'payouts_pending': 0,
        'aml_alerts': 0,
        'open_cases': case_stats.get('open', 0),
        'escalations': 0,
        'data_requests': len(pending_dsr) if hasattr(pending_dsr, '__len__') else 0,
    }

    return render_template('admin/compliance/data_requests.html',
                          requests=requests,
                          status=status,
                          stats=stats,
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
    
    return redirect(url_for('admin.compliance.data_requests'))


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
    
    # Get case statistics and pending DSRs for stats badges
    case_stats = ComplianceCaseService.get_case_statistics()
    pending_dsr = DataSubjectRequestService.get_requests_by_status(DataSubjectRequestStatus.PENDING)

    # Build stats dict for sidebar badges
    stats = {
        'kyc_pending': KycRecord.query.filter_by(status='pending').count(),
        'orgs_pending': Organisation.query.filter_by(verification_status='pending').count(),
        'payouts_pending': 0,
        'aml_alerts': 0,
        'open_cases': case_stats.get('open', 0),
        'escalations': 0,
        'data_requests': len(pending_dsr) if hasattr(pending_dsr, '__len__') else 0,
    }

    return render_template('admin/compliance/reports.html',
                          reports=reports,
                          stats=stats,
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
        return redirect(url_for('admin.compliance.reports'))
    
    # Get case statistics and pending DSRs for stats badges
    case_stats = ComplianceCaseService.get_case_statistics()
    pending_dsr = DataSubjectRequestService.get_requests_by_status(DataSubjectRequestStatus.PENDING)

    # Build stats dict for sidebar badges
    stats = {
        'kyc_pending': KycRecord.query.filter_by(status='pending').count(),
        'orgs_pending': Organisation.query.filter_by(verification_status='pending').count(),
        'payouts_pending': 0,
        'aml_alerts': 0,
        'open_cases': case_stats.get('open', 0),
        'escalations': 0,
        'data_requests': len(pending_dsr) if hasattr(pending_dsr, '__len__') else 0,
    }

    return render_template('admin/compliance/generate_report.html',
                          report_types=ComplianceReportType,
                          stats=stats,
                          title="Generate Report")


@compliance_bp.route('/case/<int:case_id>')
@login_required
@require_role('compliance_officer', 'admin', 'super_admin', 'owner')
def view_case(case_id):
    """View compliance case details"""
    case = ComplianceCase.query.get_or_404(case_id)
    
    from app.admin.compliance.services import ComplianceCaseService
    notes = ComplianceCaseService.get_case_notes(case.id)
    history = ComplianceCaseService.get_case_history(case.id)

    return render_template('admin/compliance/view_case.html',
                          case=case,
                          notes=notes,
                          history=history,
                          stats=_sidebar_stats(),
                          now=datetime.now(),
                          title="View Case")


@compliance_bp.route('/case/<int:case_id>/action', methods=['POST'])
@login_required
@require_role('compliance_officer', 'admin', 'super_admin', 'owner')
def case_action(case_id):
    """Handle compliance case actions"""
    from app.admin.compliance.services import ComplianceCaseService

    action = request.form.get('action')
    notes = request.form.get('notes', '') or request.form.get('resolution', '') or request.form.get('note', '')

    if action == 'assign':
        assigned_to = request.form.get('assigned_to', type=int)
        if assigned_to:
            ComplianceCaseService.assign_case(case_id, assigned_to, current_user.id)
            flash(f'Case {case_id} assigned.', 'success')
    elif action == 'assign_to_me':
        ComplianceCaseService.assign_case(case_id, current_user.id, current_user.id)
        flash(f'Case {case_id} assigned to you.', 'success')
    elif action == 'approve':
        ComplianceCaseService.update_case_status(case_id, ComplianceCaseStatus.APPROVED, current_user.id, notes)
        flash(f'Case {case_id} approved.', 'success')
    elif action == 'reject':
        ComplianceCaseService.update_case_status(case_id, ComplianceCaseStatus.REJECTED, current_user.id, notes)
        flash(f'Case {case_id} rejected.', 'warning')
    elif action == 'resolve':
        # Resolve modal → terminal CLOSED state with resolution text.
        ComplianceCaseService.update_case_status(case_id, ComplianceCaseStatus.CLOSED, current_user.id, notes)
        flash(f'Case {case_id} resolved.', 'success')
    elif action == 'request_info':
        ComplianceCaseService.request_info(case_id, current_user.id, notes)
        flash(f'Additional information requested for case {case_id}.', 'info')
    elif action == 'close':
        ComplianceCaseService.close_case(case_id, current_user.id, notes)
        flash(f'Case {case_id} closed.', 'success')
    elif action == 'reopen':
        ComplianceCaseService.reopen_case(case_id, current_user.id)
        flash(f'Case {case_id} reopened.', 'info')
    elif action == 'escalate':
        reason = request.form.get('escalation_reason', notes)
        new_priority = request.form.get('new_priority')
        priority_enum = ComplianceCasePriority(new_priority) if new_priority else None
        ComplianceCaseService.escalate_case(case_id, current_user.id, reason, priority_enum)
        flash(f'Case {case_id} escalated.', 'warning')
    elif action == 'add_note':
        if not notes.strip():
            flash('Note cannot be empty.', 'danger')
        else:
            ComplianceCaseService.add_note(case_id, current_user.id, notes)
            flash('Note added.', 'success')
    else:
        flash('Invalid action.', 'danger')
    
    return redirect(url_for('admin.compliance.view_case', case_id=case_id))


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
    
    # Get case statistics and pending DSRs for stats badges
    case_stats = ComplianceCaseService.get_case_statistics()
    pending_dsr = DataSubjectRequestService.get_requests_by_status(DataSubjectRequestStatus.PENDING)

    # Build stats dict for sidebar badges
    stats = {
        'kyc_pending': KycRecord.query.filter_by(status='pending').count(),
        'orgs_pending': Organisation.query.filter_by(verification_status='pending').count(),
        'payouts_pending': 0,
        'aml_alerts': 0,
        'open_cases': case_stats.get('open', 0),
        'escalations': 0,
        'data_requests': len(pending_dsr) if hasattr(pending_dsr, '__len__') else 0,
    }

    return render_template('admin/compliance/cases.html',
                          cases=cases,
                          status=status,
                          stats=stats,
                          now=datetime.now(),
                          title="Compliance Cases")


@compliance_bp.route('/case/new', methods=['GET', 'POST'])
@login_required
@require_role('compliance_officer', 'admin', 'super_admin', 'owner')
def create_case():
    """Create a new compliance case"""
    from app.admin.compliance.services import ComplianceCaseService

    if request.method == 'POST':
        case_type_raw = request.form.get('case_type', 'other')
        priority_raw = request.form.get('priority', 'medium')
        title = request.form.get('title', '').strip()
        description = request.form.get('description', '').strip()
        user_id = request.form.get('user_id', type=int)
        organisation_id = request.form.get('organisation_id', type=int)

        try:
            case_type = ComplianceCaseType(case_type_raw)
        except ValueError:
            case_type = ComplianceCaseType.OTHER

        try:
            priority = ComplianceCasePriority(priority_raw)
        except ValueError:
            priority = ComplianceCasePriority.MEDIUM

        if not title:
            flash('Case title is required.', 'danger')
            return render_template('admin/compliance/create_case.html',
                                  case_types=ComplianceCaseType,
                                  priorities=ComplianceCasePriority,
                                  stats=_sidebar_stats(),
                                  title="New Compliance Case")

        case = ComplianceCaseService.create_case(
            case_type=case_type,
            title=title,
            description=description,
            created_by=current_user.id,
            user_id=user_id,
            organisation_id=organisation_id,
            priority=priority
        )

        flash(f'Case {case.case_number} created successfully.', 'success')
        return redirect(url_for('admin.compliance.view_case', case_id=case.id))

    return render_template('admin/compliance/create_case.html',
                          case_types=ComplianceCaseType,
                          priorities=ComplianceCasePriority,
                          stats=_sidebar_stats(),
                          title="New Compliance Case")


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
                          stats=_sidebar_stats(),
                          title="Case History")


# ===========================================================================
# AML REGULATORY PROGRAM (jurisdiction-aware: serves large & small regimes)
# ===========================================================================
@compliance_bp.route('/aml/jurisdictions')
@login_required
@require_role('compliance_officer', 'admin', 'super_admin', 'owner')
def aml_jurisdictions():
    """View configured jurisdiction profiles and seed defaults if missing."""
    if JurisdictionProfile.query.count() == 0:
        aml_reg.seed_jurisdictions()
    jurisdictions = aml_reg.list_jurisdictions()
    return render_template('admin/compliance/aml_jurisdictions.html',
                          jurisdictions=jurisdictions,
                          stats=_sidebar_stats(),
                          title="AML Jurisdictions")


@compliance_bp.route('/aml/reports')
@login_required
@require_role('compliance_officer', 'admin', 'super_admin', 'owner')
def aml_reports():
    """List regulatory filings (STR/SAR/CTR/IWTR/TFR)."""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 25, type=int)
    reports = RegulatoryReport.query.order_by(
        RegulatoryReport.created_at.desc()
    ).paginate(page=page, per_page=per_page, error_out=False)
    return render_template('admin/compliance/aml_reports.html',
                          reports=reports,
                          stats=_sidebar_stats(),
                          title="Regulatory Reports")


@compliance_bp.route('/aml/report/<int:report_id>')
@login_required
@require_role('compliance_officer', 'admin', 'super_admin', 'owner')
def aml_report_detail(report_id):
    """View a single regulatory report and its goAML XML."""
    report = RegulatoryReport.query.get_or_404(report_id)
    return render_template('admin/compliance/aml_report_detail.html',
                          report=report,
                          stats=_sidebar_stats(),
                          title=f"Report {report.report_number}")


@compliance_bp.route('/aml/report/<int:report_id>/file', methods=['POST'])
@login_required
@require_role('compliance_officer', 'admin', 'super_admin', 'owner')
def aml_report_file(report_id):
    """Mark a regulatory report as filed to the FIU (records external reference)."""
    report = RegulatoryReport.query.get_or_404(report_id)
    report.status = 'filed'
    report.filed_at = datetime.now(timezone.utc)
    report.filed_by = current_user.id
    report.external_reference = request.form.get('external_reference') or report.external_reference
    db.session.commit()
    flash(f'Report {report.report_number} marked as filed.', 'success')
    return redirect(url_for('admin.compliance.aml_report_detail', report_id=report.id))


@compliance_bp.route('/aml/ctr')
@login_required
@require_role('compliance_officer', 'super_admin', 'owner')
def aml_ctr():
    """Large-cash (CTR) and structuring alerts."""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 25, type=int)
    alerts = CtrAlert.query.order_by(
        CtrAlert.period_date.desc(), CtrAlert.alert_type.asc()
    ).paginate(page=page, per_page=per_page, error_out=False)
    default_jur = aml_reg.get_default_jurisdiction()
    return render_template('admin/compliance/aml_ctr.html',
                          alerts=alerts,
                          default_threshold=float(default_jur.cash_threshold_amount) if default_jur else 0,
                          currency=default_jur.currency_code if default_jur else '',
                          stats=_sidebar_stats(),
                          title="CTR / Structuring")


@compliance_bp.route('/aml/ctr/detect', methods=['POST'])
@login_required
@require_role('compliance_officer', 'admin', 'super_admin', 'owner')
def aml_ctr_detect():
    """Run the CTR / structuring detection engine across recent activity."""
    created = aml_reg.detect_cash_and_structuring()
    flash(f'Detection run complete. {len(created)} new alert(s) raised.', 'info')
    return redirect(url_for('admin.compliance.aml_ctr'))


@compliance_bp.route('/aml/terminated')
@login_required
@require_role('compliance_officer', 'admin', 'super_admin', 'owner')
def aml_terminated():
    """Terminated / high-risk entity registry (MATCH / VMSS equivalent)."""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 25, type=int)
    entities = TerminatedEntity.query.order_by(
        TerminatedEntity.created_at.desc()
    ).paginate(page=page, per_page=per_page, error_out=False)
    return render_template('admin/compliance/aml_terminated.html',
                          entities=entities,
                          stats=_sidebar_stats(),
                          title="Terminated Entities")


@compliance_bp.route('/aml/terminated/add', methods=['POST'])
@login_required
@require_role('compliance_officer', 'admin', 'super_admin', 'owner')
def aml_terminated_add():
    """Add an entity to the terminated registry."""
    aml_reg.add_terminated_entity(
        name=request.form.get('name', '').strip(),
        entity_type=request.form.get('entity_type', 'organisation'),
        registration_number=request.form.get('registration_number') or None,
        national_id=request.form.get('national_id') or None,
        source=request.form.get('source', 'manual'),
        reason_code=request.form.get('reason_code') or None,
        reason_text=request.form.get('reason_text') or None,
        added_by=current_user.id,
    )
    flash('Entity added to terminated registry.', 'success')
    return redirect(url_for('admin.compliance.aml_terminated'))


@compliance_bp.route('/organisation/<int:org_id>/screen', methods=['POST'])
@login_required
@require_role('compliance_officer', 'admin', 'super_admin', 'owner')
def aml_screen_org(org_id):
    """Screen an organisation against the terminated registry during KYB."""
    hits = aml_reg.screen_organisation(org_id)
    if hits:
        names = ', '.join(h.name for h in hits)
        flash(f'TERMINATED-ENTITY MATCH: {names}. Do not onboard without escalation.', 'danger')
    else:
        flash('No terminated-entity matches found.', 'success')
    return redirect(url_for('admin.compliance.view_org', org_id=org_id))


@compliance_bp.route('/aml/scenarios')
@login_required
@require_role('compliance_officer', 'admin', 'super_admin', 'owner')
def aml_scenarios():
    """Transaction-monitoring scenarios (TMS calibration)."""
    scenarios = MonitoringScenario.query.order_by(MonitoringScenario.category.asc()).all()
    return render_template('admin/compliance/aml_scenarios.html',
                          scenarios=scenarios,
                          stats=_sidebar_stats(),
                          title="Monitoring Scenarios")


@compliance_bp.route('/aml/scenario/add', methods=['POST'])
@login_required
@require_role('compliance_officer', 'admin', 'super_admin', 'owner')
def aml_scenario_add():
    """Add a monitoring scenario."""
    threshold = request.form.get('threshold_value')
    scenario = MonitoringScenario(
        public_id=str(uuid.uuid4()),
        name=request.form.get('name', '').strip(),
        description=request.form.get('description') or None,
        category=request.form.get('category', 'pattern'),
        risk_weight=int(request.form.get('risk_weight', 0) or 0),
        threshold_value=float(threshold) if threshold else None,
        is_enabled=True,
        parameters={'created_by': current_user.id},
    )
    db.session.add(scenario)
    db.session.commit()
    flash('Monitoring scenario added.', 'success')
    return redirect(url_for('admin.compliance.aml_scenarios'))


@compliance_bp.route('/aml/scenario/<int:scenario_id>/calibrate', methods=['POST'])
@login_required
@require_role('compliance_officer', 'admin', 'super_admin', 'owner')
def aml_scenario_calibrate(scenario_id):
    """Enable/disable or re-weight a scenario (calibration)."""
    scenario = MonitoringScenario.query.get_or_404(scenario_id)
    toggle = request.form.get('toggle')
    if toggle in ('enable', 'disable'):
        scenario.is_enabled = (toggle == 'enable')
    new_weight = request.form.get('risk_weight')
    if new_weight is not None:
        scenario.risk_weight = int(new_weight)
    new_threshold = request.form.get('threshold_value')
    if new_threshold is not None and new_threshold != '':
        scenario.threshold_value = float(new_threshold)
    scenario.last_calibrated_at = datetime.now(timezone.utc)
    scenario.last_calibrated_by = current_user.id
    db.session.commit()
    flash('Scenario calibrated.', 'success')
    return redirect(url_for('admin.compliance.aml_scenarios'))


@compliance_bp.route('/aml/backtest', methods=['GET', 'POST'])
@login_required
@require_role('compliance_officer', 'admin', 'super_admin', 'owner')
def aml_backtest():
    """Run a back-test of a monitoring scenario over a historical window."""
    run = None
    if request.method == 'POST':
        scenario_id = request.form.get('scenario_id', type=int)
        window_start = datetime.now(timezone.utc) - timedelta(days=int(request.form.get('days', 30) or 30))
        window_end = datetime.now(timezone.utc)
        run = aml_reg.run_backtest(scenario_id, window_start, window_end)
    scenarios = MonitoringScenario.query.filter_by(is_enabled=True).all()
    runs = AmlBacktestRun.query.order_by(AmlBacktestRun.run_at.desc()).limit(20).all()
    return render_template('admin/compliance/aml_backtest.html',
                          scenarios=scenarios, runs=runs, run=run,
                          stats=_sidebar_stats(),
                          title="TMS Back-testing")


@compliance_bp.route('/aml/training', methods=['GET', 'POST'])
@login_required
@require_role('compliance_officer', 'admin', 'super_admin', 'owner')
def aml_training():
    """Staff AML/CFT training records."""
    if request.method == 'POST':
        AmlTrainingRecord(
            public_id=str(uuid.uuid4()),
            user_id=request.form.get('user_id', type=int),
            training_module=request.form.get('training_module', '').strip(),
            completed_at=datetime.now(timezone.utc),
            score=request.form.get('score', type=int),
            certificate_ref=request.form.get('certificate_ref') or None,
            delivered_by=request.form.get('delivered_by') or None,
        ).save()
        flash('Training record added.', 'success')
        return redirect(url_for('admin.compliance.aml_training'))
    records = AmlTrainingRecord.query.order_by(AmlTrainingRecord.completed_at.desc()).limit(50).all()
    return render_template('admin/compliance/aml_training.html',
                          records=records,
                          stats=_sidebar_stats(),
                          title="AML Training")


@compliance_bp.route('/aml/attestations', methods=['GET', 'POST'])
@login_required
@require_role('compliance_officer', 'admin', 'super_admin', 'owner')
def aml_attestations():
    """MLRO / compliance officer attestations of program effectiveness."""
    if request.method == 'POST':
        AmlAttestation(
            public_id=str(uuid.uuid4()),
            attestation_type=request.form.get('attestation_type', 'mlro_quarterly'),
            period_start=datetime.now(timezone.utc) - timedelta(days=90),
            period_end=datetime.now(timezone.utc),
            attested_by=current_user.id,
            statement=request.form.get('statement') or None,
            status='submitted',
        ).save()
        flash('Attestation recorded.', 'success')
        return redirect(url_for('admin.compliance.aml_attestations'))
    attestations = AmlAttestation.query.order_by(AmlAttestation.attested_at.desc()).limit(50).all()
    return render_template('admin/compliance/aml_attestations.html',
                          attestations=attestations,
                          stats=_sidebar_stats(),
                          title="AML Attestations")


@compliance_bp.route('/aml/retention')
@login_required
@require_role('compliance_officer', 'admin', 'super_admin', 'owner')
def aml_retention():
    """Record-retention policies and aged-record summary."""
    aml_reg.ensure_default_retention_policies()
    summary = aml_reg.get_retention_summary()
    return render_template('admin/compliance/aml_retention.html',
                          summary=summary,
                          stats=_sidebar_stats(),
                          title="Retention Policies")

