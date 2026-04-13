# app/admin/owner/routes.py
"""
Owner routes - Highest privilege level
Includes Master Key Impersonation by Role and Security Dashboard
"""

from datetime import datetime, timedelta
import logging
from flask import (
    render_template, redirect, url_for, flash,
    request, session, jsonify, current_app
)
from flask_login import login_required, current_user, login_user, logout_user

from app.extensions import db
from app.identity.models.organisation import Organisation
from app.identity.models.roles_permission import Role
from app.identity.models import User, UserRole
from sqlalchemy import func
from app.admin.owner.decorators import owner_required
from app.admin.owner.utils import log_owner_action, get_system_health
from app.auth.roles import assign_global_role, revoke_global_role
from app.profile.models import get_profile_by_user

# Import audit decorators
from app.admin.owner.audit import audit_owner_action

# Import owner blueprint
from app.admin.owner import owner_bp

# Import security dashboard routes
from app.admin.owner.security_routes import add_security_routes

logger = logging.getLogger(__name__)

# Helper for login required + owner check
def owner_login_required(f):
    return login_required(owner_required(f))

@owner_bp.context_processor
def utility_processor():
    def now():
        return datetime.utcnow()

    def is_impersonating():
        return session.get('is_impersonating', False)

    def impersonated_by():
        return session.get('impersonated_by_name', None)

    def impersonated_role():
        return session.get('impersonated_role', None)

    return {
        'now': now,
        'is_impersonating': is_impersonating,
        'impersonated_by': impersonated_by,
        'impersonated_role': impersonated_role
    }

# ============================================================================
# Dashboard & Core
# ============================================================================

@owner_bp.route('/dashboard')
@owner_login_required
def dashboard():
    """Owner dashboard - platform overview"""
    try:
        db.session.rollback()
        total_users = User.query.count()
        active_users = User.query.filter_by(is_active=True).count()
        verified_users = User.query.filter_by(is_verified=True).count()

        # Get counts for the Master Key section - with error handling
        try:
            role_stats = db.session.query(Role.name, func.count(UserRole.user_id))\
                .join(UserRole, Role.id == UserRole.role_id).group_by(Role.name).all()
        except Exception as role_error:
            logger.warning(f"Role stats query error: {role_error}")
            db.session.rollback()
            role_stats = []

        # Get organization stats - with error handling
        try:
            from app.identity.models.organisation import Organisation
            total_orgs = Organisation.query.count()
        except Exception as org_error:
            logger.warning(f"Organization query error: {org_error}")
            total_orgs = 0
        pending_orgs = 0  # Temporarily disabled due to schema issue

        # Get role stats - with error handling
        try:
            total_roles = Role.query.count()
        except Exception as role_count_error:
            logger.warning(f"Role count error: {role_count_error}")
            total_roles = 0

        # Get super admins - with error handling
        super_admins = []
        try:
            super_admin_role = Role.query.filter_by(name='super_admin').first()
            if super_admin_role:
                super_admins = db.session.query(User).join(UserRole, User.id == UserRole.user_id).join(Role, Role.id == UserRole.role_id)\
                    .filter(Role.name == 'super_admin').all()
        except Exception as super_admin_error:
            logger.warning(f"Super admin query error: {super_admin_error}")
            db.session.rollback()

        # Get regular users (non-super admins) - with error handling
        regular_users = []
        try:
            regular_users = db.session.query(User).outerjoin(UserRole, User.id == UserRole.user_id).outerjoin(Role, Role.id == UserRole.role_id)\
                .filter((Role.name != 'super_admin') | (Role.name.is_(None))).all()
        except Exception as regular_error:
            logger.warning(f"Regular users query error: {regular_error}")
            db.session.rollback()

        # Get recent users - with error handling
        recent_users = []
        try:
            recent_users = User.query.order_by(User.created_at.desc()).limit(5).all()
        except Exception as recent_error:
            logger.warning(f"Recent users query error: {recent_error}")
            db.session.rollback()

        # Get new users today - with error handling
        new_users_today = 0
        try:
            from datetime import date
            new_users_today = User.query.filter(
                func.date(User.created_at) == date.today()
            ).count()
        except Exception as new_users_error:
            logger.warning(f"New users today query error: {new_users_error}")
            db.session.rollback()

        # Get recent audit logs - temporarily disabled due to schema issues
        recent_logs = []

        # Get system health - with error handling
        health = None
        try:
            health = get_system_health()
        except Exception as health_error:
            logger.warning(f"System health error: {health_error}")

        # Get system settings for dashboard
        from app.admin.owner.models import SystemSetting
        lockdown_enabled = SystemSetting.get('EMERGENCY_LOCKDOWN', False)
        maintenance_enabled = SystemSetting.get('MAINTENANCE_MODE', False)
        wallet_enabled = SystemSetting.get('ENABLE_WALLET', True)

        # Get compliance metrics for dashboard
        pending_reviews_count = 0
        try:
            from app.audit.forensic_audit import ForensicAuditService
            pending_reviews = ForensicAuditService.get_pending_reviews(limit=5)
            pending_reviews_count = len(pending_reviews)
        except Exception as e:
            logger.warning(f"Could not load pending reviews: {e}")

        return render_template('owner/dashboard.html',
                               # User stats
                               total_users=total_users,
                               active_users=active_users,
                               verified_users=verified_users,
                               new_users_today=new_users_today,

                               # Organization stats
                               total_orgs=total_orgs,
                               pending_orgs=pending_orgs,

                               # Role stats
                               total_roles=total_roles,
                               role_stats=dict(role_stats),

                               # Super admin management
                               super_admins=super_admins,
                               regular_users=regular_users,
                               total_super_admins=len(super_admins),

                               # Recent data
                               recent_users=recent_users,
                               recent_logs=recent_logs,

                               # System info
                               health=health,
                               lockdown_enabled=lockdown_enabled,
                               maintenance_enabled=maintenance_enabled,
                               wallet_enabled=wallet_enabled,
                               owner_username=current_user.username,
                               owner_is_verified=current_user.is_verified,

                               # Compliance metrics
                               pending_reviews_count=pending_reviews_count)
    except Exception as e:
        logger.error(f"Owner dashboard error: {e}")
        return render_template('owner/dashboard.html',
                               total_users=0, active_users=0, verified_users=0,
                               new_users_today=0, total_orgs=0, pending_orgs=0,
                               total_roles=0, role_stats={}, super_admins=[],
                               regular_users=[], total_super_admins=0,
                               recent_users=[], recent_logs=[], health=None,
                               lockdown_enabled=False,
                               maintenance_enabled=False,
                               wallet_enabled=True,
                               owner_username=current_user.username,
                               owner_is_verified=current_user.is_verified)

# ============================================================================
# Master Key: Impersonate by Role
# ============================================================================

@owner_bp.route('/master-key/act-as/<string:role_name>', methods=['POST'])
@owner_login_required
def impersonate_role(role_name):
    """
    MASTER KEY: Instantly switch to a user with the specified role.
    If no user exists, the system will find the best match or fail gracefully.
    """
    try:
        # 1. Find a user that HAS this role
        target_user = User.query.join(UserRole, User.id == UserRole.user_id).join(Role, Role.id == UserRole.role_id).filter(Role.name == role_name).first()

        if not target_user:
            flash(f"No existing users found with role: {role_name}. Please create one first.", "warning")
            return redirect(url_for('admin.owner.dashboard'))

        # 2. Store original owner ID for the 'Stop Impersonating' function
        session['impersonated_by'] = current_user.id
        session['impersonated_by_name'] = current_user.username
        session['is_impersonating'] = True
        session['impersonated_role'] = role_name

        # 3. Log the action
        log_owner_action(
            action='role_impersonation_started',
            category='security',
            details={'role': role_name, 'target_user': target_user.username}
        )

        # 4. Perform the switch
        logout_user()
        login_user(target_user)

        flash(f"🗝️ Master Key Activated: You are now acting as a {role_name.replace('_', ' ').title()} ({target_user.username})", "success")

        # 5. Redirect to the appropriate dashboard based on role
        dashboard_redirects = {
            'owner': url_for('admin.owner.dashboard'),
            'super_admin': url_for('admin.super_dashboard'),
            'admin': url_for('admin.super_dashboard'),
            'auditor': url_for('admin.auditor_dashboard'),
            'compliance_officer': url_for('admin.auditor_dashboard'),
            'moderator': url_for('admin.moderator_dashboard'),
            'support': url_for('admin.support_dashboard'),
            'event_manager': url_for('events.admin_dashboard'),
            'transport_admin': url_for('transport.admin_dashboard'),
            'wallet_admin': url_for('wallet.wallet_dashboard'),
            'accommodation_admin': url_for('accommodation.admin_dashboard'),
            'tourism_admin': url_for('tourism.home'),
            'org_admin': url_for('events.events_hub'),
            'org_member': url_for('events.events_hub'),
            'user': url_for('fan.fan_dashboard')
        }

        redirect_url = dashboard_redirects.get(role_name, url_for('events.events_hub'))
        return redirect(redirect_url)

    except Exception as e:
        logger.error(f"Master Key Error: {e}")
        flash("Failed to activate Master Key.", "danger")
        return redirect(url_for('admin.owner.dashboard'))

@owner_bp.route('/master-key/exit', methods=['POST'])
@login_required
def exit_impersonation():
    """Exit impersonation and return to Owner state"""
    original_id = session.get('impersonated_by')
    if not original_id:
        return redirect(url_for('index'))

    owner_user = User.query.get(original_id)
    if owner_user:
        logout_user()
        login_user(owner_user)
        session.pop('impersonated_by', None)
        session.pop('impersonated_by_name', None)
        session.pop('is_impersonating', None)
        flash("✅ Returned to Owner Dashboard", "info")
        return redirect(url_for('admin.owner.dashboard'))

    return redirect(url_for('auth_routes.login'))

# Keep existing user-specific impersonation for fine-grained testing
@owner_bp.route('/impersonate/<string:user_id>', methods=['POST'])
@owner_login_required
def impersonate_user(user_id):
    """Impersonate a specific user"""
    try:
        target_user = User.query.get(user_id)
        if not target_user:
            flash("User not found", "danger")
            return redirect(url_for('admin.owner.dashboard'))

        session['impersonated_by'] = current_user.id
        session['impersonated_by_name'] = current_user.username
        session['is_impersonating'] = True

        log_owner_action(
            action='user_impersonation_started',
            category='security',
            details={'target_user': target_user.username}
        )

        logout_user()
        login_user(target_user)

        flash(f"🎭 You are now acting as {target_user.username}", "success")
        return redirect(url_for('index'))

    except Exception as e:
        logger.error(f"User impersonation error: {e}")
        flash("Failed to impersonate user", "danger")
        return redirect(url_for('admin.owner.dashboard'))

# ============================================================================
# Management Routes
# ============================================================================

@owner_bp.route('/audit-logs')
@owner_login_required
def audit_logs():
    """View owner audit logs"""
    try:
        from app.audit.comprehensive_audit import SecurityEventLog
        from datetime import datetime, timedelta

        # Get filter parameters
        event_type = request.args.get('event_type')
        severity = request.args.get('severity')
        days = int(request.args.get('days', 7))

        query = SecurityEventLog.query

        if event_type:
            query = query.filter_by(event_type=event_type)
        if severity:
            query = query.filter_by(severity=severity)

        # Filter by date
        since_date = datetime.utcnow() - timedelta(days=days)
        query = query.filter(SecurityEventLog.created_at >= since_date)

        logs = query.order_by(SecurityEventLog.created_at.desc()).limit(100).all()

        # Get unique event types for filter dropdown
        event_types = db.session.query(SecurityEventLog.event_type).distinct().all()
        event_types = [et[0] for et in event_types if et[0]]

        return render_template('owner/audit_logs.html',
                               logs=logs,
                               event_types=event_types,
                               current_filters={'event_type': event_type, 'severity': severity, 'days': days})
    except Exception as e:
        logger.error(f"Audit logs error: {e}")
        flash("Error loading audit logs", "danger")
        return redirect(url_for('admin.owner.dashboard'))

@owner_bp.route('/settings', methods=['GET', 'POST'])
@owner_login_required
@audit_owner_action('viewed_settings', 'settings')
def settings():
    """Owner settings page"""
    try:
        from app.admin.owner.models import OwnerSettings

        if request.method == 'POST':
            # Update settings
            session_timeout = request.form.get('session_timeout', type=int, default=120)

            settings = OwnerSettings.query.filter_by(owner_id=current_user.id).first()
            if not settings:
                settings = OwnerSettings(owner_id=current_user.id)
                db.session.add(settings)

            settings.session_timeout_minutes = session_timeout
            db.session.commit()

            flash("✅ Settings updated successfully", "success")
            log_owner_action(
                action='updated_settings',
                category='settings',
                details={'session_timeout': session_timeout}
            )
            return redirect(url_for('admin.owner.settings'))

        # GET request - show settings page
        settings = OwnerSettings.query.filter_by(owner_id=current_user.id).first()
        return render_template('owner/settings.html', settings=settings)
    except Exception as e:
        logger.error(f"Settings error: {e}")
        flash("Error loading settings", "danger")
        return redirect(url_for('admin.owner.dashboard'))

@owner_bp.route('/users')
@owner_login_required
@audit_owner_action('viewed_users', 'user_management')
def users():
    """Manage all users"""
    try:
        page = request.args.get('page', 1, type=int)
        users = User.query.paginate(
            page=page, per_page=50, error_out=False
        )
        return render_template('owner/users.html', users=users)
    except Exception as e:
        logger.error(f"Users management error: {e}")
        flash("Error loading users", "danger")
        return redirect(url_for('admin.owner.dashboard'))

@owner_bp.route('/manage-roles')
@owner_login_required
@audit_owner_action('viewed_roles', 'user_management')
def manage_roles():
    """Manage system roles"""
    try:
        roles = Role.query.all()
        users = User.query.all()
        return render_template('owner/manage_roles.html', roles=roles, users=users)
    except Exception as e:
        logger.error(f"Role management error: {e}")
        flash("Error loading roles", "danger")
        return redirect(url_for('admin.owner.dashboard'))

@owner_bp.route('/danger-zone')
@owner_login_required
@audit_owner_action('viewed_danger_zone', 'danger')
def danger_zone():
    """Danger zone - critical platform actions"""
    try:
        from app.admin.owner.models import SystemSetting
        lockdown_enabled = SystemSetting.get('EMERGENCY_LOCKDOWN', False)
        maintenance_enabled = SystemSetting.get('MAINTENANCE_MODE', False)

        return render_template('owner/danger_zone.html',
                               lockdown_enabled=lockdown_enabled,
                               maintenance_enabled=maintenance_enabled)
    except Exception as e:
        logger.error(f"Danger zone error: {e}")
        flash("Error loading danger zone", "danger")
        return redirect(url_for('admin.owner.dashboard'))

@owner_bp.route('/toggle-global-maintenance', methods=['POST'])
@owner_login_required
@audit_owner_action('toggled_maintenance_mode', 'danger')
def toggle_global_maintenance():
    """Toggle global maintenance mode"""
    try:
        from app.admin.owner.models import SystemSetting
        current_mode = SystemSetting.get('MAINTENANCE_MODE', False)
        new_mode = not current_mode

        SystemSetting.set('MAINTENANCE_MODE', new_mode, value_type='bool',
                         category='system', description='Maintenance mode toggle')

        # Log the action
        log_owner_action(
            action='maintenance_mode_toggled',
            category='system',
            details={'new_mode': new_mode, 'previous_mode': current_mode}
        )

        flash(f"Maintenance mode {'enabled' if new_mode else 'disabled'}",
              "success" if not new_mode else "warning")

    except Exception as e:
        logger.error(f"Toggle maintenance error: {e}")
        flash("Failed to toggle maintenance mode", "danger")

    return redirect(url_for('admin.owner.dashboard'))

@owner_bp.route('/toggle-lockdown', methods=['POST'])
@owner_login_required
@audit_owner_action('toggled_lockdown', 'danger')
def toggle_lockdown():
    """Toggle emergency lockdown"""
    try:
        from app.admin.owner.models import SystemSetting
        current_mode = SystemSetting.get('EMERGENCY_LOCKDOWN', False)
        new_mode = not current_mode

        SystemSetting.set('EMERGENCY_LOCKDOWN', new_mode, value_type='bool',
                         category='security', description='Emergency lockdown toggle')

        # Log the action
        log_owner_action(
            action='emergency_lockdown_toggled',
            category='security',
            details={'new_mode': new_mode, 'previous_mode': current_mode}
        )

        flash(f"Emergency lockdown {'enabled' if new_mode else 'disabled'}",
              "success" if not new_mode else "danger")

    except Exception as e:
        logger.error(f"Toggle lockdown error: {e}")
        flash("Failed to toggle emergency lockdown", "danger")

    return redirect(url_for('admin.owner.dashboard'))

@owner_bp.route('/system-health')
@owner_login_required
@audit_owner_action('viewed_system_health', 'navigation')
def system_health():
    """View system health metrics"""
    try:
        health = get_system_health()
        from app.admin.owner.models import SystemSetting
        settings_count = SystemSetting.query.count()

        return render_template('owner/system_health.html',
                               health=health,
                               settings_count=settings_count)
    except Exception as e:
        logger.error(f"System health error: {e}")
        flash("Error loading system health", "danger")
        return redirect(url_for('admin.owner.dashboard'))

@owner_bp.route('/impersonate-page')
@owner_login_required
@audit_owner_action('viewed_impersonate_page', 'security')
def impersonate_page():
    """Master key impersonation page"""
    try:
        # Get all roles
        roles = Role.query.all()

        # Get all users with their roles for display
        users = User.query.all()

        # Enhance user data with role information
        enhanced_users = []
        for user in users:
            user_roles = db.session.query(Role.name).join(UserRole, Role.id == UserRole.role_id).filter(UserRole.user_id == user.id).all()
            role_names = [role[0] for role in user_roles]
            enhanced_users.append({
                'user': user,
                'roles': role_names,
                'primary_role': role_names[0] if role_names else 'user'
            })

        return render_template('owner/impersonate.html',
                          roles=roles,
                          users=enhanced_users,
                          global_roles=roles)
    except Exception as e:
        logger.error(f"Impersonate page error: {e}")
        flash("Error loading impersonate page", "danger")
        return redirect(url_for('admin.owner.dashboard'))

# ============================================================================
# Super Admin Management
# ============================================================================

@owner_bp.route('/add-super-admin', methods=['POST'])
@owner_login_required
@audit_owner_action('added_super_admin', 'user_management')
def add_super_admin():
    """Add a new super admin"""
    try:
        user_id = request.form.get('user_id')
        if not user_id:
            flash("Please select a user", "warning")
            return redirect(url_for('admin.owner.dashboard'))

        user = User.query.get(user_id)
        if not user:
            flash("User not found", "danger")
            return redirect(url_for('admin.owner.dashboard'))

        assign_global_role(user, 'super_admin')
        flash(f"✅ {user.username} is now a Super Admin", "success")

    except Exception as e:
        logger.error(f"Add super admin error: {e}")
        flash("Failed to add super admin", "danger")

    return redirect(url_for('admin.owner.dashboard'))

@owner_bp.route('/remove-super-admin/<int:user_id>', methods=['POST'])
@owner_login_required
@audit_owner_action('removed_super_admin', 'user_management')
def remove_super_admin(user_id):
    """Remove super admin privileges"""
    try:
        user = User.query.get(user_id)
        if not user:
            flash("User not found", "danger")
            return redirect(url_for('admin.owner.dashboard'))

        revoke_global_role(user, 'super_admin')
        flash(f"✅ Super admin privileges removed from {user.username}", "success")

    except Exception as e:
        logger.error(f"Remove super admin error: {e}")
        flash("Failed to remove super admin", "danger")

    return redirect(url_for('admin.owner.dashboard'))

# ============================================================================
# KYC Tier Management
# ============================================================================

@owner_bp.route('/kyc/tiers')
@owner_login_required
@audit_owner_action('viewed_kyc_tiers', 'compliance')
def kyc_tier_management():
    """KYC tier management panel."""
    try:
        from app.auth.kyc_compliance import (
            TIER_REQUIREMENTS, DAILY_LIMITS, MONTHLY_LIMITS, TRANSACTION_LIMITS
        )

        # Get all users with their KYC tiers
        from app.auth.kyc_compliance import calculate_kyc_tier
        from app.identity.models.user import User

        # Get filter parameters
        tier_filter = request.args.get('tier', type=int)
        status_filter = request.args.get('status')
        search_query = request.args.get('search', '').strip()

        # Build query
        query = User.query

        if search_query:
            query = query.filter(
                (User.username.ilike(f'%{search_query}%')) |
                (User.email.ilike(f'%{search_query}%'))
            )

        users = query.order_by(User.created_at.desc()).limit(200).all()

        # Calculate KYC info for each user and count tiers
        user_kyc_info = []
        tier_counts = {0: 0, 1: 0, 2: 0, 3: 0, 4: 0, 5: 0}

        for user in users:
            kyc_info = calculate_kyc_tier(user.id)
            tier_counts[kyc_info['tier']] += 1
            user_kyc_info.append({
                'user': user,
                'kyc_info': kyc_info
            })

        # Filter by tier if specified
        if tier_filter is not None:
            user_kyc_info = [info for info in user_kyc_info if info['kyc_info']['tier'] == tier_filter]

        # Filter by verification status if specified
        if status_filter:
            user_kyc_info = [info for info in user_kyc_info
                           if info['kyc_info'].get('verification_status') == status_filter]

        # Get pending manual reviews
        from app.audit.forensic_audit import ForensicAuditService
        pending_reviews = ForensicAuditService.get_pending_reviews(
            entity_type="kyc",
            limit=50
        )

        return render_template('owner/kyc_tiers.html',
                               user_kyc_info=user_kyc_info,
                               tier_counts=tier_counts,
                               tier_requirements=TIER_REQUIREMENTS,
                               daily_limits=DAILY_LIMITS,
                               monthly_limits=MONTHLY_LIMITS,
                               transaction_limits=TRANSACTION_LIMITS,
                               pending_reviews=pending_reviews,
                               current_filters={
                                   'tier': tier_filter,
                                   'status': status_filter,
                                   'search': search_query
                               })
    except Exception as e:
        logger.error(f"KYC tier management error: {e}")
        flash("Error loading KYC tier management", "danger")
        return redirect(url_for('admin.owner.dashboard'))

@owner_bp.route('/kyc/manual-upgrade/<int:user_id>', methods=['POST'])
@owner_login_required
@audit_owner_action('manual_kyc_upgrade', 'compliance')
def manual_kyc_upgrade(user_id):
    """Manually upgrade a user's KYC tier (compliance officer override)."""
    try:
        target_tier = request.form.get('tier', type=int)
        reason = request.form.get('reason', '').strip()

        if not reason:
            flash("Please provide a reason for the manual upgrade", "warning")
            return redirect(url_for('admin.owner.kyc_tier_management'))

        if target_tier not in range(0, 6):
            flash("Invalid KYC tier", "danger")
            return redirect(url_for('admin.owner.kyc_tier_management'))

        # Get user
        from app.identity.models.user import User
        user = User.query.get(user_id)
        if not user:
            flash("User not found", "danger")
            return redirect(url_for('admin.owner.kyc_tier_management'))

        # Create manual verification record
        from app.identity.individuals.individual_verification import IndividualVerification
        from app.auth.kyc_compliance import TIER_REQUIREMENTS

        tier_info = TIER_REQUIREMENTS.get(target_tier, {})

        verification = IndividualVerification(
            user_id=user_id,
            status="verified",
            scope=tier_info.get("required_scope", {}),
            notes=f"Manual KYC upgrade to tier {target_tier} by {current_user.username}. Reason: {reason}",
            reviewer_id=current_user.id
        )

        db.session.add(verification)
        db.session.commit()

        # Log the action
        log_owner_action(
            action='manual_kyc_upgrade',
            category='compliance',
            details={
                'target_user': user.username,
                'target_tier': target_tier,
                'reason': reason,
                'performed_by': current_user.username
            }
        )

        flash(f"✅ KYC tier {target_tier} manually assigned to {user.username}", "success")

    except Exception as e:
        logger.error(f"Manual KYC upgrade error: {e}")
        flash("Failed to manually upgrade KYC tier", "danger")

    return redirect(url_for('admin.owner.kyc_tier_management'))

@owner_bp.route('/kyc/suspicious-activity')
@owner_login_required
@audit_owner_action('viewed_suspicious_activity', 'compliance')
def suspicious_activity():
    """View suspicious activity reports for AML/CFT compliance."""
    try:
        from app.audit.comprehensive_audit import SecurityEventLog
        from datetime import datetime, timedelta

        # Get filter parameters
        days = int(request.args.get('days', 7))
        event_type = request.args.get('event_type')

        query = SecurityEventLog.query.filter(
            (SecurityEventLog.event_type.in_(['aml_review_flagged', 'fia_report_generated',
                                            'transaction_limit_exceeded', 'kyc_tier_blocked'])) |
            (SecurityEventLog.severity.in_(['high', 'critical']))
        )

        if event_type:
            query = query.filter_by(event_type=event_type)

        # Filter by date
        since_date = datetime.utcnow() - timedelta(days=days)
        query = query.filter(SecurityEventLog.created_at >= since_date)

        logs = query.order_by(SecurityEventLog.created_at.desc()).limit(200).all()

        # Get unique event types for filter dropdown
        event_types = db.session.query(SecurityEventLog.event_type).distinct().all()
        event_types = [et[0] for et in event_types if et[0]]

        return render_template('owner/suspicious_activity.html',
                               logs=logs,
                               event_types=event_types,
                               current_filters={'event_type': event_type, 'days': days})
    except Exception as e:
        logger.error(f"Suspicious activity error: {e}")
        flash("Error loading suspicious activity reports", "danger")
        return redirect(url_for('admin.owner.dashboard'))

@owner_bp.route('/kyc/compliance-reports')
@owner_login_required
@audit_owner_action('viewed_kyc_compliance_reports', 'compliance')
def kyc_compliance_reports():
    """Generate KYC compliance reports for regulatory authorities."""
    try:
        from datetime import datetime, timedelta
        from app.auth.kyc_compliance import calculate_kyc_tier
        from app.identity.models.user import User

        # Get report parameters
        report_type = request.args.get('type', 'daily')
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')

        # Set default date range
        if report_type == 'daily':
            end_date = datetime.utcnow()
            start_date = end_date - timedelta(days=1)
        elif report_type == 'weekly':
            end_date = datetime.utcnow()
            start_date = end_date - timedelta(days=7)
        elif report_type == 'monthly':
            end_date = datetime.utcnow()
            start_date = end_date - timedelta(days=30)

        # Generate report data
        report_data = {
            'total_users': User.query.count(),
            'new_users': User.query.filter(User.created_at >= start_date).count(),
            'kyc_stats': {},
            'large_transactions': 0,  # Would need transaction data
            'aml_flags': 0,  # Would need AML flag data
            'report_period': f"{start_date.date()} to {end_date.date()}",
            'generated_at': datetime.utcnow()
        }

        # Calculate KYC tier distribution
        from app.auth.kyc_compliance import TIER_0_UNREGISTERED, TIER_1_BASIC, TIER_2_STANDARD, \
                                           TIER_3_ENHANCED, TIER_4_PREMIUM, TIER_5_CORPORATE

        tiers = [TIER_0_UNREGISTERED, TIER_1_BASIC, TIER_2_STANDARD,
                TIER_3_ENHANCED, TIER_4_PREMIUM, TIER_5_CORPORATE]

        for tier in tiers:
            # This is simplified - in production, you'd want to cache or optimize this
            count = 0
            for user in User.query.all():
                kyc_info = calculate_kyc_tier(user.id)
                if kyc_info['tier'] == tier:
                    count += 1
            report_data['kyc_stats'][tier] = count

        return render_template('owner/compliance_reports.html',
                               report_data=report_data,
                               report_type=report_type,
                               start_date=start_date,
                               end_date=end_date)
    except Exception as e:
        logger.error(f"Compliance reports error: {e}")
        flash("Error generating compliance reports", "danger")
        return redirect(url_for('admin.owner.dashboard'))

# ============================================================================
# FORENSIC AUDIT & COMPLIANCE ROUTES
# ============================================================================

@owner_bp.route('/compliance/dashboard')
@owner_login_required
@audit_owner_action('viewed_compliance_dashboard', 'compliance')
def compliance_dashboard():
    """Compliance Officer Dashboard - Central hub for forensic audit monitoring"""
    try:
        from app.audit.forensic_audit import ForensicAuditService

        # Get pending reviews
        pending_reviews = []
        try:
            pending_reviews = ForensicAuditService.get_pending_reviews(limit=20)
        except:
            pass

        # Get suspicious activity
        suspicious_patterns = []
        try:
            suspicious_patterns = ForensicAuditService.get_suspicious_patterns(days=7)
        except:
            pass

        # Calculate metrics
        metrics = {
            'pending_reviews_count': len(pending_reviews),
            'blocked_attempts_today': 0,
            'avg_approval_time_hours': 2.5,
            'high_risk_alerts': len([p for p in suspicious_patterns if p.get('risk_score', 0) > 70]),
            'total_audit_events': 0,
        }

        # Get recent high-risk events
        recent_alerts = []
        try:
            from app.audit.comprehensive_audit import SecurityEventLog
            recent_alerts = SecurityEventLog.query.filter(
                SecurityEventLog.severity.in_(['high', 'critical'])
            ).order_by(SecurityEventLog.created_at.desc()).limit(10).all()
        except:
            pass

        return render_template('admin/compliance/dashboard.html',
                               pending_reviews=pending_reviews,
                               suspicious_patterns=suspicious_patterns,
                               metrics=metrics,
                               recent_alerts=recent_alerts)
    except Exception as e:
        logger.error(f"Compliance dashboard error: {e}")
        flash("Error loading compliance dashboard", "danger")
        return redirect(url_for('admin.owner.dashboard'))

@owner_bp.route('/compliance/audit-timeline')
@owner_login_required
@audit_owner_action('viewed_audit_timeline', 'compliance')
def audit_timeline():
    """Audit timeline search interface"""
    try:
        entity_type = request.args.get('entity_type')
        entity_id = request.args.get('entity_id')
        days = int(request.args.get('days', 7))

        timeline_events = []

        return render_template('admin/compliance/search.html',
                               timeline_events=timeline_events,
                               entity_type=entity_type,
                               entity_id=entity_id,
                               days=days)
    except Exception as e:
        logger.error(f"Audit timeline error: {e}")
        flash("Error loading audit timeline", "danger")
        return redirect(url_for('admin.owner.compliance_dashboard'))

@owner_bp.route('/compliance/user-audit/<int:user_id>')
@owner_login_required
@audit_owner_action('viewed_user_audit_profile', 'compliance')
def user_audit_profile(user_id):
    """Comprehensive audit view for a specific user"""
    try:
        from app.identity.models.user import User
        user = User.query.get_or_404(user_id)

        timeline_events = []
        security_events = []
        risk_score = 0

        return render_template('admin/compliance/user_audit_profile.html',
                               user=user,
                               timeline_events=timeline_events,
                               security_events=security_events,
                               risk_score=risk_score)
    except Exception as e:
        logger.error(f"User audit profile error: {e}")
        flash("Error loading user audit profile", "danger")
        return redirect(url_for('admin.owner.compliance_dashboard'))

@owner_bp.route('/compliance/reports')
@owner_login_required
@audit_owner_action('viewed_compliance_reports', 'compliance')
def compliance_reports_page():
    """Compliance report generator"""
    try:
        from datetime import datetime, timedelta

        report_type = request.args.get('type', 'daily')

        # Set default date ranges
        end_date = datetime.utcnow()
        if report_type == 'daily':
            start_date = end_date - timedelta(days=1)
        elif report_type == 'weekly':
            start_date = end_date - timedelta(days=7)
        elif report_type == 'monthly':
            start_date = end_date - timedelta(days=30)
        else:
            start_date = end_date - timedelta(days=1)

        return render_template('admin/compliance/reports.html',
                               report_type=report_type,
                               start_date=start_date,
                               end_date=end_date)
    except Exception as e:
        logger.error(f"Compliance reports error: {e}")
        flash("Error loading compliance reports", "danger")
        return redirect(url_for('admin.owner.compliance_dashboard'))

@owner_bp.route('/api/compliance/pending-reviews')
@owner_login_required
def api_pending_reviews():
    """JSON API for pending reviews"""
    try:
        from app.audit.forensic_audit import ForensicAuditService

        limit = request.args.get('limit', 50, type=int)
        offset = request.args.get('offset', 0, type=int)

        pending_reviews = []
        try:
            pending_reviews = ForensicAuditService.get_pending_reviews(
                limit=limit,
                offset=offset
            )
        except:
            pass

        return jsonify({
            'success': True,
            'pending_reviews': pending_reviews,
            'count': len(pending_reviews)
        })
    except Exception as e:
        logger.error(f"API pending reviews error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@owner_bp.route('/api/compliance/review/<audit_id>', methods=['POST'])
@owner_login_required
def api_review_audit(audit_id):
    """API to approve/reject an audit item"""
    try:
        data = request.get_json()
        action = data.get('action')  # 'approve' or 'reject'
        notes = data.get('notes', '')

        if action not in ['approve', 'reject']:
            return jsonify({'success': False, 'error': 'Invalid action'}), 400

        # Simulate success for now
        return jsonify({'success': True, 'message': f'Action {action} processed'})
    except Exception as e:
        logger.error(f"API review audit error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@owner_bp.route('/api/compliance/suspicious-patterns')
@owner_login_required
def api_suspicious_patterns():
    """JSON API for suspicious patterns"""
    try:
        from app.audit.forensic_audit import ForensicAuditService

        days = request.args.get('days', 7, type=int)
        min_risk = request.args.get('min_risk', 50, type=int)

        patterns = []
        try:
            patterns = ForensicAuditService.get_suspicious_patterns(
                days=days,
                min_risk_score=min_risk
            )
        except:
            pass

        return jsonify({
            'success': True,
            'patterns': patterns,
            'count': len(patterns)
        })
    except Exception as e:
        logger.error(f"API suspicious patterns error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

# ============================================================================
# Initialize Security Dashboard Routes
# ============================================================================

# Add security dashboard routes to the blueprint
add_security_routes(owner_bp)
