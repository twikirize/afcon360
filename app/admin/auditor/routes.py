"""
Auditor Dashboard - View forensic logs and compliance data
"""
from flask import Blueprint, render_template, request, jsonify, current_app, flash, redirect, url_for
from flask_login import login_required, current_user
from app.auth.decorators import require_role
from app.audit.comprehensive_audit import AuditService, FinancialAuditLog, SecurityEventLog, DataAccessLog, APIAuditLog
from datetime import datetime, timedelta

auditor_bp = Blueprint('auditor', __name__, url_prefix='/auditor')

@auditor_bp.route('/dashboard')
@login_required
@require_role('auditor', 'admin', 'super_admin', 'owner')
def dashboard():
    """Auditor main dashboard"""
    # Get statistics for the last 30 days
    thirty_days_ago = datetime.utcnow() - timedelta(days=30)

    # Financial audit stats
    financial_count = FinancialAuditLog.query.filter(
        FinancialAuditLog.created_at >= thirty_days_ago
    ).count()

    # Security event stats
    security_count = SecurityEventLog.query.filter(
        SecurityEventLog.created_at >= thirty_days_ago
    ).count()

    # Data access stats
    data_access_count = DataAccessLog.query.filter(
        DataAccessLog.created_at >= thirty_days_ago
    ).count()

    # API audit stats
    api_audit_count = APIAuditLog.query.filter(
        APIAuditLog.created_at >= thirty_days_ago
    ).count()

    # Get recent high-severity security events
    recent_security_events = SecurityEventLog.query.filter(
        SecurityEventLog.severity.in_(['critical', 'high'])
    ).order_by(SecurityEventLog.created_at.desc()).limit(10).all()

    # Get large financial transactions
    large_transactions = FinancialAuditLog.query.filter(
        FinancialAuditLog.amount >= 1000000  # 1M threshold
    ).order_by(FinancialAuditLog.created_at.desc()).limit(10).all()

    return render_template('admin/auditor/dashboard.html',
                          financial_count=financial_count,
                          security_count=security_count,
                          data_access_count=data_access_count,
                          api_audit_count=api_audit_count,
                          recent_security_events=recent_security_events,
                          large_transactions=large_transactions,
                          title="Auditor Dashboard")

@auditor_bp.route('/forensic-logs')
@login_required
@require_role('auditor', 'admin', 'super_admin', 'owner')
def forensic_logs():
    """Get forensic audit logs with pagination"""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)
    entity_type = request.args.get('entity_type')
    action = request.args.get('action')

    # This would query the ForensicAuditLog model
    # For now, we'll use a placeholder
    logs = []

    return render_template('admin/auditor/forensic_logs.html',
                          logs=logs,
                          page=page,
                          per_page=per_page,
                          entity_type=entity_type,
                          action=action,
                          title="Forensic Logs")

@auditor_bp.route('/financial-audit')
@login_required
@require_role('auditor', 'admin', 'super_admin', 'owner')
def financial_audit():
    """Financial audit logs"""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)
    transaction_type = request.args.get('type')
    status = request.args.get('status')

    query = FinancialAuditLog.query

    if transaction_type and transaction_type != 'all':
        query = query.filter_by(transaction_type=transaction_type)

    if status and status != 'all':
        query = query.filter_by(status=status)

    logs = query.order_by(
        FinancialAuditLog.created_at.desc()
    ).paginate(page=page, per_page=per_page, error_out=False)

    return render_template('admin/auditor/financial_audit.html',
                          logs=logs,
                          transaction_type=transaction_type,
                          status=status,
                          title="Financial Audit")

@auditor_bp.route('/security-events')
@login_required
@require_role('auditor', 'admin', 'super_admin', 'owner')
def security_events():
    """Security event logs"""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)
    severity = request.args.get('severity')
    event_type = request.args.get('event_type')

    query = SecurityEventLog.query

    if severity and severity != 'all':
        query = query.filter_by(severity=severity)

    if event_type and event_type != 'all':
        query = query.filter_by(event_type=event_type)

    events = query.order_by(
        SecurityEventLog.created_at.desc()
    ).paginate(page=page, per_page=per_page, error_out=False)

    return render_template('admin/auditor/security_events.html',
                          events=events,
                          severity=severity,
                          event_type=event_type,
                          title="Security Events")

@auditor_bp.route('/data-access')
@login_required
@require_role('auditor', 'admin', 'super_admin', 'owner')
def data_access_logs():
    """Data access logs for GDPR compliance"""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)
    access_type = request.args.get('access_type')

    query = DataAccessLog.query

    if access_type and access_type != 'all':
        query = query.filter_by(access_type=access_type)

    logs = query.order_by(
        DataAccessLog.created_at.desc()
    ).paginate(page=page, per_page=per_page, error_out=False)

    return render_template('admin/auditor/data_access.html',
                          logs=logs,
                          access_type=access_type,
                          title="Data Access Logs")

@auditor_bp.route('/api-audit')
@login_required
@require_role('auditor', 'admin', 'super_admin', 'owner')
def api_audit_logs():
    """API audit logs"""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)
    service_name = request.args.get('service_name')
    status = request.args.get('status')

    query = APIAuditLog.query

    if service_name and service_name != 'all':
        query = query.filter_by(service_name=service_name)

    if status and status != 'all':
        query = query.filter_by(status=status)

    logs = query.order_by(
        APIAuditLog.created_at.desc()
    ).paginate(page=page, per_page=per_page, error_out=False)

    return render_template('admin/auditor/api_audit.html',
                          logs=logs,
                          service_name=service_name,
                          status=status,
                          title="API Audit Logs")

@auditor_bp.route('/reports')
@login_required
@require_role('auditor', 'admin', 'super_admin', 'owner')
def compliance_reports():
    """View compliance reports"""
    return render_template('admin/auditor/compliance_reports.html',
                          title="Compliance Reports")

@auditor_bp.route('/export/<log_type>')
@login_required
@require_role('auditor', 'admin', 'super_admin', 'owner')
def export_logs(log_type):
    """Export logs in CSV format"""
    # This would generate CSV exports
    # Implementation would depend on the log_type
    flash(f'Export for {log_type} logs would be generated here', 'info')
    return redirect(url_for('auditor.dashboard'))
