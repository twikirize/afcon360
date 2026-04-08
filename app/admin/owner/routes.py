# app/admin/owner/routes.py
"""
Owner routes - Highest privilege level
Includes Master Key Impersonation by Role
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

# Import audit decorators
from app.admin.owner.audit import audit_owner_action

# Import owner blueprint
from app.admin.owner import owner_bp

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
                               owner_username=current_user.username,
                               owner_is_verified=current_user.is_verified)
    except Exception as e:
        logger.error(f"Owner dashboard error: {e}")
        return render_template('owner/dashboard.html',
                               total_users=0, active_users=0, verified_users=0,
                               new_users_today=0, total_orgs=0, pending_orgs=0,
                               total_roles=0, role_stats={}, super_admins=[],
                               regular_users=[], total_super_admins=0,
                               recent_users=[], recent_logs=[], health=None,
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
    """View owner audit logs - temporarily disabled"""
    try:
        # Temporarily disabled due to schema issues
        logs = []
        flash("Audit logs temporarily disabled due to database schema issues", "warning")
        return render_template('owner/audit_logs.html', logs=logs)
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
            return redirect(url_for('owner.settings'))

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
        return render_template('owner/danger_zone.html')
    except Exception as e:
        logger.error(f"Danger zone error: {e}")
        flash("Error loading danger zone", "danger")
        return redirect(url_for('admin.owner.dashboard'))

@owner_bp.route('/system-health')
@owner_login_required
@audit_owner_action('viewed_system_health', 'navigation')
def system_health():
    """View system health metrics"""
    try:
        health = get_system_health()
        return render_template('owner/system_health.html', health=health)
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
