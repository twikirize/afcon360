"""
Compliance Dashboard - Regulatory compliance and risk management
"""
from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for
from flask_login import login_required, current_user
from app.auth.decorators import require_role
from app.extensions import db
from app.audit.comprehensive_audit import FinancialAuditLog, SecurityEventLog
from app.identity.individuals.individual_verification import IndividualVerification
from app.identity.models.organisation import Organisation
from app.identity.models.user import User
from datetime import datetime, timedelta

compliance_bp = Blueprint('compliance', __name__, url_prefix='/compliance')

@compliance_bp.route('/dashboard')
@login_required
@require_role('compliance_officer', 'admin', 'super_admin', 'owner')
def dashboard():
    """Compliance main dashboard"""
    from app.identity.models.user import User
    from flask import current_app

    # Get pending KYC verifications
    pending_verifications = IndividualVerification.query.filter_by(
        status='pending'
    ).order_by(IndividualVerification.requested_at.desc()).limit(50).all()

    # Get user public_ids for display
    user_ids = [v.user_id for v in pending_verifications]
    users = User.query.filter(User.id.in_(user_ids)).all() if user_ids else []
    user_map = {user.id: user.public_id for user in users}

    # Get high-risk transactions (AML alerts)
    high_risk_transactions = FinancialAuditLog.query.filter(
        FinancialAuditLog.amount >= 5000000  # UGX 5M threshold
    ).order_by(FinancialAuditLog.created_at.desc()).limit(50).all()

    # Get public_ids for transaction users
    transaction_user_ids = [t.user_id for t in high_risk_transactions if t.user_id]
    transaction_users = User.query.filter(User.id.in_(transaction_user_ids)).all() if transaction_user_ids else []
    transaction_user_map = {user.id: user.public_id for user in transaction_users}

    # Get pending organisation verifications
    pending_orgs = Organisation.query.filter_by(
        verification_status='pending'
    ).count()

    # Get high-risk transactions count (last 7 days)
    week_ago = datetime.utcnow() - timedelta(days=7)
    high_risk_tx = FinancialAuditLog.query.filter(
        FinancialAuditLog.created_at >= week_ago,
        FinancialAuditLog.risk_score >= 70
    ).count()

    # Get AML flagged transactions count
    aml_flagged = FinancialAuditLog.query.filter_by(
        aml_flagged=True
    ).count()

    # Get recent security events
    recent_security_events = SecurityEventLog.query.filter(
        SecurityEventLog.severity.in_(['critical', 'high'])
    ).order_by(SecurityEventLog.created_at.desc()).limit(10).all()

    # Get large transactions for review
    large_transactions = FinancialAuditLog.query.filter(
        FinancialAuditLog.amount >= 5000000  # 5M threshold
    ).order_by(FinancialAuditLog.created_at.desc()).limit(10).all()

    return render_template('admin/compliance/dashboard.html',
                          pending_verifications=pending_verifications,
                          high_risk_transactions=high_risk_transactions,
                          user_map=user_map,
                          transaction_user_map=transaction_user_map,
                          pending_orgs=pending_orgs,
                          high_risk_tx=high_risk_tx,
                          aml_flagged=aml_flagged,
                          recent_security_events=recent_security_events,
                          large_transactions=large_transactions,
                          title="Compliance Dashboard")

@compliance_bp.route('/kyc-review')
@login_required
@require_role('compliance_officer', 'admin', 'super_admin', 'owner')
def kyc_review_panel():
    """KYC review panel"""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    status = request.args.get('status', 'pending')

    query = IndividualVerification.query

    if status != 'all':
        query = query.filter_by(status=status)

    verifications = query.order_by(
        IndividualVerification.requested_at.desc()
    ).paginate(page=page, per_page=per_page, error_out=False)

    return render_template('admin/compliance/kyc_review.html',
                          verifications=verifications,
                          status=status,
                          title="KYC Review")

@compliance_bp.route('/org-review')
@login_required
@require_role('compliance_officer', 'admin', 'super_admin', 'owner')
def org_review_panel():
    """Organisation review panel"""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    status = request.args.get('status', 'pending')

    query = Organisation.query

    if status != 'all':
        query = query.filter_by(verification_status=status)

    organisations = query.order_by(
        Organisation.created_at.desc()
    ).paginate(page=page, per_page=per_page, error_out=False)

    return render_template('admin/compliance/org_review.html',
                          organisations=organisations,
                          status=status,
                          title="Organisation Review")

@compliance_bp.route('/aml-monitoring')
@login_required
@require_role('compliance_officer', 'admin', 'super_admin', 'owner')
def aml_monitoring():
    """AML monitoring dashboard"""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)

    # Get AML flagged transactions
    aml_transactions = FinancialAuditLog.query.filter_by(
        aml_flagged=True
    ).order_by(
        FinancialAuditLog.created_at.desc()
    ).paginate(page=page, per_page=per_page, error_out=False)

    # Get high-risk transactions
    high_risk_query = FinancialAuditLog.query.filter(
        FinancialAuditLog.risk_score >= 70
    )

    high_risk_count = high_risk_query.count()

    return render_template('admin/compliance/aml_monitoring.html',
                          aml_transactions=aml_transactions,
                          high_risk_count=high_risk_count,
                          title="AML Monitoring")

@compliance_bp.route('/transaction-monitoring')
@login_required
@require_role('compliance_officer', 'admin', 'super_admin', 'owner')
def transaction_monitoring():
    """Transaction monitoring"""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    min_amount = request.args.get('min_amount', 1000000, type=int)  # Default 1M

    query = FinancialAuditLog.query.filter(
        FinancialAuditLog.amount >= min_amount
    )

    transactions = query.order_by(
        FinancialAuditLog.created_at.desc()
    ).paginate(page=page, per_page=per_page, error_out=False)

    return render_template('admin/compliance/transaction_monitoring.html',
                          transactions=transactions,
                          min_amount=min_amount,
                          title="Transaction Monitoring")

@compliance_bp.route('/risk-assessment')
@login_required
@require_role('compliance_officer', 'admin', 'super_admin', 'owner')
def risk_assessment():
    """Risk assessment dashboard"""
    # Calculate risk scores for various entities
    # This would be more complex in a real implementation

    return render_template('admin/compliance/risk_assessment.html',
                          title="Risk Assessment")

@compliance_bp.route('/reports')
@login_required
@require_role('compliance_officer', 'admin', 'super_admin', 'owner')
def compliance_reports():
    """Compliance reports"""
    return render_template('admin/compliance/reports.html',
                          title="Compliance Reports")

@compliance_bp.route('/action/<int:verification_id>', methods=['POST'])
@login_required
@require_role('compliance_officer', 'admin', 'super_admin', 'owner')
def compliance_action(verification_id):
    """Handle compliance actions"""
    action = request.form.get('action')
    notes = request.form.get('notes', '')

    verification = IndividualVerification.query.get_or_404(verification_id)

    if action == 'approve':
        verification.status = 'verified'
        verification.verified_at = datetime.utcnow()
        verification.verified_by = current_user.id
        flash(f'KYC verification {verification_id} approved.', 'success')
    elif action == 'reject':
        verification.status = 'rejected'
        verification.rejection_reason = notes
        verification.verified_at = datetime.utcnow()
        verification.verified_by = current_user.id
        flash(f'KYC verification {verification_id} rejected.', 'warning')
    elif action == 'request_info':
        verification.status = 'pending'
        flash(f'More information requested for verification {verification_id}.', 'info')
    else:
        flash('Invalid action.', 'danger')

    db.session.commit()

    # Redirect back to the dashboard instead of kyc_review_panel
    return redirect(url_for('compliance.dashboard'))
