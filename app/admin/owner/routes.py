#app/admin/owner/routes.py
"""
Owner routes - Highest privilege level
All routes are under /admin/owner/
Templates are in templates/owner/ (main templates folder)
"""

from datetime import datetime, timedelta
import pyotp
import qrcode
import io
import base64
import csv
from io import StringIO
from flask import (
    render_template, redirect, url_for, flash,
    request, session, jsonify, make_response
)
from flask_login import login_required, current_user

from app.extensions import db, redis_client
from app.identity.models.organisation import Organisation
from app.identity.models.roles_permission import Role
from app.identity.models import User, UserRole
from app.identity.models.organisation_member import OrganisationMember
from app.profile.models import UserProfile
from app.admin.owner.models import OwnerSettings, OwnerAuditLog
from app.admin.owner.decorators import owner_required, owner_password_confirm_required
from app.admin.owner.utils import log_owner_action, get_system_health
from app.auth.roles import assign_global_role, revoke_global_role

# 🔴 NEW: Import audit decorators
from app.admin.owner.audit import audit_owner_action, audit_danger_zone_action, audit_batch_operation

# Import owner blueprint
from app.admin.owner import owner_bp

@owner_bp.context_processor
def utility_processor():
    """Add utility functions to template context"""
    def format_datetime(dt, format='%Y-%m-%d %H:%M'):
        if dt:
            return dt.strftime(format)
        return ''
    def now():
        """Return current UTC datetime"""
        return datetime.utcnow()

    return dict(
        format_datetime=format_datetime,
        now=now  # This makes {{ now() }} work in templates
    )

# ============================================================================
# Owner Dashboard
# ============================================================================

@owner_bp.route('/dashboard')
@login_required
@owner_required
# 🔴 NEW: Add decorator - REMOVE the manual log_owner_action inside function
@audit_owner_action('viewed_dashboard', 'navigation')
def dashboard():
    """Owner dashboard - platform overview"""

    # Platform stats
    total_users = User.query.count()
    verified_users = User.query.filter_by(is_verified=True).count()
    active_users = User.query.filter_by(is_active=True).count()
    new_users_today = User.query.filter(
        User.created_at >= datetime.utcnow().date()
    ).count()

    # Organisation stats
    total_orgs = Organisation.query.count()
    active_orgs = Organisation.query.filter_by(is_active=True).count()
    pending_orgs = Organisation.query.filter_by(verification_status='pending').count()

    # Role stats
    total_roles = Role.query.count()

    # Get super admins
    super_admin_role = Role.query.filter_by(name='super_admin').first()
    super_admins = []
    if super_admin_role:
        super_admins = User.query.join(User.roles).filter(
            UserRole.role_id == super_admin_role.id
        ).all()

    # Get regular users (not super admin, not owner)
    owner_role = Role.query.filter_by(name='owner').first()
    regular_users = []
    if super_admin_role and owner_role:
        regular_users = User.query.filter(
            ~User.roles.any(UserRole.role_id.in_([
                super_admin_role.id,
                owner_role.id
            ]))
        ).order_by(User.username).limit(20).all()

    # Recent signups
    recent_users = User.query.order_by(User.created_at.desc()).limit(10).all()

    # System health
    health = get_system_health()

    # Recent audit logs
    recent_logs = OwnerAuditLog.query.order_by(
        OwnerAuditLog.created_at.desc()
    ).limit(10).all()

    # User growth chart data (last 7 days)
    from sqlalchemy import func
    dates = []
    counts = []
    for i in range(6, -1, -1):
        date = (datetime.utcnow() - timedelta(days=i)).date()
        count = User.query.filter(
            func.date(User.created_at) == date
        ).count()
        dates.append(date.strftime('%a'))
        counts.append(count)

    # 🔴 REMOVED: Manual log_owner_action call (now handled by decorator)

    return render_template(
        'owner/dashboard.html',
        total_users=total_users,
        verified_users=verified_users,
        active_users=active_users,
        new_users_today=new_users_today,
        total_orgs=total_orgs,
        active_orgs=active_orgs,
        pending_orgs=pending_orgs,
        total_roles=total_roles,
        super_admins=super_admins,
        regular_users=regular_users,
        recent_users=recent_users,
        recent_logs=recent_logs,
        health=health,
        chart_labels=dates,
        chart_data=counts
    )


# ============================================================================
# Super Admin Management
# ============================================================================

@owner_bp.route('/super-admins')
@login_required
@owner_required
# 🔴 NEW: Add decorator
@audit_owner_action('viewed_super_admins', 'user_management')
def super_admins():
    """Manage super admins"""

    super_admin_role = Role.query.filter_by(name='super_admin').first()
    super_admins = []
    if super_admin_role:
        super_admins = User.query.join(User.roles).filter(
            UserRole.role_id == super_admin_role.id
        ).all()

    # Get regular users
    owner_role = Role.query.filter_by(name='owner').first()
    regular_users = User.query.filter(
        ~User.roles.any(UserRole.role_id.in_([
            super_admin_role.id if super_admin_role else 0,
            owner_role.id if owner_role else 0
        ]))
    ).order_by(User.username).all()

    return render_template(
        'owner/super_admins.html',
        super_admins=super_admins,
        regular_users=regular_users
    )


@owner_bp.route('/super-admins/add', methods=['POST'])
@login_required
@owner_required
# 🔴 NOTE: No decorator here - we keep manual logs for detailed context
def add_super_admin():
    """Add a super admin"""
    user_id = request.form.get('user_id')

    if not user_id:
        flash('Please select a user', 'danger')
        return redirect(url_for('owner.dashboard'))

    user = User.query.get(user_id)
    if not user:
        flash('User not found', 'danger')
        return redirect(url_for('owner.dashboard'))

    try:
        assign_global_role(
            user_id=user.id,
            role_name='super_admin',
            assigned_by_id=current_user.id
        )

        # ✅ KEEP manual log for detailed context
        log_owner_action(
            action='added_super_admin',
            category='user_management',
            details={
                'target_user_id': user.id,
                'target_email': user.email
            }
        )

        flash(f'{user.email} is now a super admin', 'success')

    except Exception as e:
        flash(f'Error: {str(e)}', 'danger')
        # ✅ KEEP manual log for error details
        log_owner_action(
            action='add_super_admin_failed',
            category='user_management',
            status='failure',
            failure_reason=str(e)
        )

    return redirect(url_for('owner.dashboard'))


@owner_bp.route('/super-admins/<int:user_id>/remove', methods=['POST'])
@login_required
@owner_required
# 🔴 NOTE: No decorator - keep manual logs
def remove_super_admin(user_id):
    """Remove super admin privileges"""
    user = User.query.get_or_404(user_id)

    # Don't allow removing owner
    if any(r.role.name == 'owner' for r in user.roles):
        flash('Cannot remove owner privileges', 'danger')
        return redirect(url_for('owner.dashboard'))

    try:
        revoke_global_role(
            user_id=user.id,
            role_name='super_admin',
            revoked_by_id=current_user.id
        )

        # ✅ KEEP manual log
        log_owner_action(
            action='removed_super_admin',
            category='user_management',
            details={
                'target_user_id': user.id,
                'target_email': user.email
            }
        )

        flash(f'Super admin privileges removed from {user.email}', 'warning')

    except Exception as e:
        flash(f'Error: {str(e)}', 'danger')

    return redirect(url_for('owner.dashboard'))


# ============================================================================
# User Management
# ============================================================================

@owner_bp.route('/users')
@login_required
@owner_required
# 🔴 NEW: Add decorator
@audit_owner_action('viewed_users_list', 'user_management')
def users():
    """View all users"""
    page = request.args.get('page', 1, type=int)
    per_page = 50

    users = User.query.order_by(User.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )

    return render_template('owner/users.html', users=users)


@owner_bp.route('/users/<int:user_id>')
@login_required
@owner_required
# 🔴 NEW: Add decorator
@audit_owner_action('viewed_user_details', 'user_management')
def view_user(user_id):
    """View specific user details"""
    user = User.query.get_or_404(user_id)

    # Get user's roles
    roles = [ur.role.name for ur in user.roles if ur.role]

    # Get user's organisations
    orgs = OrganisationMember.query.filter_by(
        user_id=user.id,
        is_deleted=False
    ).all()

    return render_template(
        'owner/view_user.html',
        user=user,
        roles=roles,
        organisations=orgs
    )


@owner_bp.route('/users/<int:user_id>/impersonate')
@login_required
@owner_required
# 🔴 NOTE: Keep manual log for sensitive action
def impersonate_user(user_id):
    """Impersonate a user"""
    user = User.query.get_or_404(user_id)

    # Store original owner session
    session['owner_impersonating'] = True
    session['original_owner_id'] = current_user.id

    # Log in as user
    from flask_login import login_user
    login_user(user)

    # ✅ KEEP manual log for sensitive action
    log_owner_action(
        action='user_impersonated',
        category='user_management',
        details={
            'target_user_id': user.id,
            'target_username': user.username
        }
    )

    flash(f'Now impersonating {user.username}', 'warning')
    return redirect(url_for('index'))


@owner_bp.route('/stop-impersonating')
@login_required
# 🔴 NEW: Add decorator
@audit_owner_action('stopped_impersonating', 'user_management')
def stop_impersonating():
    """Stop impersonating and return to owner"""
    if session.get('owner_impersonating'):
        owner_id = session.pop('original_owner_id', None)
        session.pop('owner_impersonating', None)

        if owner_id:
            from flask_login import login_user
            owner = User.query.get(owner_id)
            if owner:
                login_user(owner)
                flash('Returned to owner account', 'success')

    return redirect(url_for('owner.dashboard'))


# ============================================================================
# Role Management
# ============================================================================

@owner_bp.route('/roles')
@login_required
@owner_required
# 🔴 NEW: Add decorator
@audit_owner_action('viewed_roles', 'role_management')
def manage_roles():
    """Manage all roles"""
    roles = Role.query.order_by(Role.level).all()
    users = User.query.limit(100).all()

    return render_template(
        'owner/manage_roles.html',
        roles=roles,
        users=users
    )


# ============================================================================
# Audit Logs
# ============================================================================

@owner_bp.route('/audit-logs')
@login_required
@owner_required
# 🔴 NEW: Add decorator - REMOVE manual log inside
@audit_owner_action('viewed_audit_logs', 'audit')
def audit_logs():
    """View owner audit logs"""
    page = request.args.get('page', 1, type=int)
    per_page = 50
    category = request.args.get('category')

    query = OwnerAuditLog.query.filter_by(owner_id=current_user.id)
    if category and category != 'all':
        query = query.filter_by(category=category)

    logs = query.order_by(
        OwnerAuditLog.created_at.desc()
    ).paginate(page=page, per_page=per_page, error_out=False)

    # Get distinct categories for filter
    categories = db.session.query(OwnerAuditLog.category).distinct().all()
    categories = [c[0] for c in categories]

    return render_template(
        'owner/audit_logs.html',
        logs=logs,
        categories=categories,
        current_category=category
    )


@owner_bp.route('/audit-logs/export')
@login_required
@owner_required
# 🔴 NOTE: Keep manual log for action with details
def export_audit_logs():
    """Export audit logs as CSV"""
    # Get logs
    logs = OwnerAuditLog.query.filter_by(
        owner_id=current_user.id
    ).order_by(OwnerAuditLog.created_at.desc()).all()

    # Create CSV
    si = StringIO()
    cw = csv.writer(si)
    cw.writerow(['Timestamp', 'Action', 'Category', 'Details', 'IP Address', 'Status', 'Failure Reason'])

    for log in logs:
        cw.writerow([
            log.created_at,
            log.action,
            log.category,
            str(log.details) if log.details else '',
            log.ip_address or '',
            log.status,
            log.failure_reason or ''
        ])

    output = make_response(si.getvalue())
    output.headers["Content-Disposition"] = f"attachment; filename=owner_audit_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
    output.headers["Content-type"] = "text/csv"

    # ✅ KEEP manual log to track export
    log_owner_action(
        action='audit_exported',
        category='audit'
    )

    return output


# ============================================================================
# System Health
# ============================================================================

@owner_bp.route('/system-health')
@login_required
@owner_required
# 🔴 NEW: Add decorator - REMOVE manual log inside
@audit_owner_action('viewed_system_health', 'system')
def system_health():
    """System health monitoring"""
    health = get_system_health()

    # Get database stats
    db_size = db.session.execute(
        "SELECT pg_database_size(current_database())"
    ).scalar() if 'postgresql' in str(db.engine.url) else 0

    # Get user growth (last 30 days)
    from sqlalchemy import func
    growth_data = db.session.query(
        func.date_trunc('day', User.created_at).label('day'),
        func.count().label('count')
    ).group_by('day').order_by('day').limit(30).all()

    # 🔴 REMOVED: Manual log_owner_action call

    return render_template(
        'owner/system_health.html',
        health=health,
        db_size=db_size,
        growth_data=growth_data
    )


# ============================================================================
# Owner Settings & 2FA
# ============================================================================

@owner_bp.route('/settings', methods=['GET', 'POST'])
@login_required
@owner_required
# 🔴 NEW: Add decorator for GET requests
@audit_owner_action('accessed_settings', 'settings')
def settings():
    """Owner account settings"""

    settings = OwnerSettings.query.filter_by(owner_id=current_user.id).first()
    if not settings:
        settings = OwnerSettings(owner_id=current_user.id)
        db.session.add(settings)
        db.session.commit()

    if request.method == 'POST':
        # Update settings
        settings.session_timeout_minutes = int(request.form.get('session_timeout', 120))
        settings.max_login_attempts = int(request.form.get('max_attempts', 5))
        settings.lockout_minutes = int(request.form.get('lockout_minutes', 15))
        settings.email_alerts = 'email_alerts' in request.form
        settings.alert_on_new_device = 'alert_on_new_device' in request.form
        settings.alert_on_danger_action = 'alert_on_danger_action' in request.form
        settings.require_password_for_danger = 'require_password' in request.form
        settings.danger_action_delay_hours = int(request.form.get('danger_delay', 24))

        db.session.commit()

        # ✅ KEEP manual log for detailed changes
        log_owner_action(
            action='updated_settings',
            category='settings',
            details={'fields': list(request.form.keys())}
        )

        flash('Settings updated successfully', 'success')
        return redirect(url_for('owner.settings'))

    return render_template('owner/settings.html', settings=settings)


@owner_bp.route('/setup-2fa', methods=['GET', 'POST'])
@login_required
@owner_required
# 🔴 NEW: Add decorator
@audit_owner_action('accessed_2fa_setup', 'security')
def setup_2fa():
    """Setup 2FA"""
    settings = OwnerSettings.query.filter_by(owner_id=current_user.id).first()

    if request.method == 'POST':
        code = request.form.get('code')
        totp = pyotp.TOTP(session.get('2fa_secret'))

        if totp.verify(code):
            settings.twofa_secret = session.get('2fa_secret')
            settings.twofa_enabled = True
            db.session.commit()

            # Generate backup codes
            import secrets
            from werkzeug.security import generate_password_hash

            codes = []
            hashed_codes = []
            for _ in range(10):
                code = secrets.token_hex(4)
                codes.append(code)
                hashed_codes.append(generate_password_hash(code))
            settings.twofa_backup_codes = hashed_codes
            db.session.commit()

            session.pop('2fa_secret', None)

            # ✅ KEEP manual log for success
            log_owner_action(
                action='enabled_2fa',
                category='security'
            )

            flash('2FA enabled successfully', 'success')
            return render_template('owner/backup_codes.html', codes=codes, new=True)
        else:
            flash('Invalid verification code', 'danger')

    # Generate new secret
    secret = pyotp.random_base32()
    session['2fa_secret'] = secret

    # Generate QR code
    totp_uri = pyotp.totp.TOTP(secret).provisioning_uri(
        name=current_user.email,
        issuer_name="AFCON360 Platform"
    )

    qr = qrcode.QRCode(version=1, box_size=10, border=5)
    qr.add_data(totp_uri)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")

    buffered = io.BytesIO()
    img.save(buffered, format="PNG")
    qr_code = base64.b64encode(buffered.getvalue()).decode()

    return render_template(
        'owner/setup_2fa.html',
        secret=secret,
        qr_code=qr_code
    )


@owner_bp.route('/disable-2fa', methods=['POST'])
@login_required
@owner_required
# 🔴 NOTE: Keep manual log for action with result
def disable_2fa():
    """Disable 2FA"""
    settings = OwnerSettings.query.filter_by(owner_id=current_user.id).first()

    settings.twofa_enabled = False
    settings.twofa_secret = None
    settings.twofa_backup_codes = None
    db.session.commit()

    # ✅ KEEP manual log
    log_owner_action(
        action='disabled_2fa',
        category='security'
    )

    flash('2FA disabled', 'warning')
    return redirect(url_for('owner.settings'))


@owner_bp.route('/backup-codes')
@login_required
@owner_required
# 🔴 NEW: Add decorator
@audit_owner_action('viewed_backup_codes', 'security')
def backup_codes():
    """View backup codes"""
    settings = OwnerSettings.query.filter_by(owner_id=current_user.id).first()

    if not settings or not settings.twofa_enabled:
        flash('Enable 2FA first', 'danger')
        return redirect(url_for('owner.settings'))

    # Generate new codes if requested
    if request.args.get('generate'):
        import secrets
        from werkzeug.security import generate_password_hash

        codes = []
        hashed_codes = []
        for _ in range(10):
            code = secrets.token_hex(4)
            codes.append(code)
            hashed_codes.append(generate_password_hash(code))
        settings.twofa_backup_codes = hashed_codes
        db.session.commit()

        # ✅ KEEP manual log for generation
        log_owner_action(
            action='generated_backup_codes',
            category='security'
        )

        return render_template('owner/backup_codes.html', codes=codes, new=True)

    # Show masked codes
    masked_codes = ['••••••••' for _ in range(10)] if settings.twofa_backup_codes else []
    return render_template(
        'owner/backup_codes.html',
        codes=masked_codes,
        masked=True
    )


# ============================================================================
# Danger Zone
# ============================================================================

@owner_bp.route('/danger-zone')
@login_required
@owner_required
@owner_password_confirm_required
# 🔴 NEW: Use danger zone decorator
@audit_danger_zone_action('accessed_danger_zone')
def danger_zone():
    """Danger zone - critical platform actions"""

    # Check for pending actions
    pending_email_change = session.get('pending_email_change')
    pending_platform_disable = session.get('pending_platform_disable')

    return render_template(
        'owner/danger_zone.html',
        pending_email_change=pending_email_change,
        pending_platform_disable=pending_platform_disable
    )


@owner_bp.route('/danger-zone/change-email', methods=['POST'])
@login_required
@owner_required
@owner_password_confirm_required
# 🔴 NEW: Use danger zone decorator
@audit_danger_zone_action('email_change_requested')
def change_email():
    """Request email change with delay"""
    new_email = request.form.get('new_email')

    if not new_email:
        flash('Email required', 'danger')
        return redirect(url_for('owner.danger_zone'))

    # Check if email already exists
    existing = User.query.filter_by(email=new_email).first()
    if existing and existing.id != current_user.id:
        flash('Email already in use', 'danger')
        return redirect(url_for('owner.danger_zone'))

    # Get delay from settings
    settings = OwnerSettings.query.filter_by(owner_id=current_user.id).first()
    delay_hours = settings.danger_action_delay_hours if settings else 24

    # Store pending change with delay
    session['pending_email_change'] = {
        'new_email': new_email,
        'requested_at': datetime.utcnow().isoformat(),
        'confirm_by': (datetime.utcnow() + timedelta(hours=delay_hours)).isoformat()
    }

    # ✅ KEEP manual log for details
    log_owner_action(
        action='email_change_requested',
        category='danger',
        details={'new_email': new_email, 'delay_hours': delay_hours}
    )

    flash(f'Email change requested. Confirmation required after {delay_hours} hours.', 'warning')
    return redirect(url_for('owner.danger_zone'))


@owner_bp.route('/danger-zone/confirm-email-change')
@login_required
@owner_required
# 🔴 NEW: Use danger zone decorator
@audit_danger_zone_action('email_change_confirmed')
def confirm_email_change():
    """Confirm email change after delay"""
    pending = session.get('pending_email_change')
    if not pending:
        flash('No pending email change', 'danger')
        return redirect(url_for('owner.danger_zone'))

    # Check if delay has passed
    confirm_by = datetime.fromisoformat(pending['confirm_by'])
    if datetime.utcnow() < confirm_by:
        remaining = (confirm_by - datetime.utcnow()).seconds // 3600
        flash(f'Please wait {remaining} more hours', 'warning')
        return redirect(url_for('owner.danger_zone'))

    # Apply change
    old_email = current_user.email
    current_user.email = pending['new_email']
    db.session.commit()

    # ✅ KEEP manual log for details
    log_owner_action(
        action='email_changed',
        category='danger',
        details={'old_email': old_email, 'new_email': pending['new_email']}
    )

    session.pop('pending_email_change', None)
    flash('Email changed successfully', 'success')
    return redirect(url_for('owner.settings'))


@owner_bp.route('/danger-zone/export-data', methods=['POST'])
@login_required
@owner_required
@owner_password_confirm_required
# 🔴 NEW: Use danger zone decorator
@audit_danger_zone_action('data_export_requested')
def export_data():
    """Request full platform data export"""

    # In production, this would queue a Celery task
    # ✅ KEEP manual log
    log_owner_action(
        action='data_export_requested',
        category='danger'
    )

    flash('Data export requested. You will receive an email when ready.', 'info')
    return redirect(url_for('owner.danger_zone'))


@owner_bp.route('/danger-zone/disable-platform', methods=['POST'])
@login_required
@owner_required
@owner_password_confirm_required
# 🔴 NEW: Use danger zone decorator
@audit_danger_zone_action('platform_disable_requested')
def disable_platform():
    """Request platform disable with 7-day delay"""

    session['pending_platform_disable'] = {
        'requested_at': datetime.utcnow().isoformat(),
        'confirm_by': (datetime.utcnow() + timedelta(days=7)).isoformat(),
        'confirmed': False
    }

    # ✅ KEEP manual log for status
    log_owner_action(
        action='platform_disable_requested',
        category='danger',
        status='pending'
    )

    flash('Platform disable requested. This will take effect after 7 days if confirmed.', 'danger')
    return redirect(url_for('owner.danger_zone'))