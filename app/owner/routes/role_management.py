# app/owner/routes/role_management.py
"""
Owner Role Management Routes

Provides comprehensive role management functionality for:
- Owner role management (full control)
- Admin/Super Admin role delegation
- Permission toggles and controls
- Role hierarchy management
"""

from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for
from functools import wraps

from app.extensions import db
from app.identity.models.user import User
from app.auth.delegation import DelegationService, DelegationScope
from app.audit.comprehensive_audit import AuditService
from flask_login import login_required
import logging

logger = logging.getLogger(__name__)

role_management = Blueprint('owner_role_management', __name__, url_prefix='/owner/role-management')


def require_owner_role(f):
    """Decorator to require owner role"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Check if user has owner role or delegation permission
        user_role = getattr(request, 'user_role', 'user')
        
        if user_role != 'owner':
            # Check delegation
            delegation_service = DelegationService()
            if not delegation_service.check_delegation_permission(
                getattr(request, 'user_id', 1), 
                DelegationScope.SYSTEM_SETTINGS
            ):
                flash('Owner access required', 'danger')
                return redirect(url_for('dashboard.dashboard'))
        
        return f(*args, **kwargs)
    
    return decorated_function


@role_management.route('/')
@login_required
@require_owner_role
def role_management_dashboard():
    """Main role management dashboard"""
    try:
        # Get current role management settings
        from app.models.system_config import SystemConfig
        
        # Get role management permissions
        admin_role_management = SystemConfig.get('admin_role_management_enabled', False)
        super_admin_role_management = SystemConfig.get('super_admin_role_management_enabled', False)
        
        # Get user statistics by role
        role_stats = {}
        roles = ['owner', 'super_admin', 'admin', 'moderator', 'auditor', 'compliance_officer', 
                'support', 'event_manager', 'transport_admin', 'wallet_admin', 'accommodation_admin',
                'tourism_admin', 'org_admin', 'org_member', 'user']
        
        for role in roles:
            role_stats[role] = User.query.filter_by(role=role).count()
        
        # Get recent role changes
        audit_service = AuditService()
        recent_changes = audit_service.get_recent_role_changes(limit=10)
        
        return render_template('owner/role_management/dashboard.html',
                             admin_role_management=admin_role_management,
                             super_admin_role_management=super_admin_role_management,
                             role_stats=role_stats,
                             recent_changes=recent_changes)
        
    except Exception as e:
        logger.error(f"Error loading role management dashboard: {e}")
        flash('Error loading role management dashboard', 'danger')
        return redirect(url_for('owner.settings'))


@role_management.route('/toggle-admin-access', methods=['POST'])
@login_required
@require_owner_role
def toggle_admin_role_management():
    """Toggle admin role management permissions"""
    try:
        from app.models.system_config import SystemConfig
        
        authorize = request.form.get('authorize') == 'on'
        
        # Update system configuration
        SystemConfig.set('admin_role_management_enabled', authorize)
        
        # Log the action
        audit_service = AuditService()
        audit_service.log_role_management_action(
            user_id=getattr(request, 'user_id', 1),
            action='toggle_admin_role_management',
            details={'authorized': authorize}
        )
        
        status = 'enabled' if authorize else 'disabled'
        flash(f'Admin role management {status}', 'success')
        
    except Exception as e:
        logger.error(f"Error toggling admin role management: {e}")
        flash('Error updating admin role management permissions', 'danger')
    
    return redirect(url_for('admin.owner.owner_role_management.role_management_dashboard'))


@role_management.route('/toggle-super-admin-access', methods=['POST'])
@login_required
@require_owner_role
def toggle_super_admin_role_management():
    """Toggle super admin role management permissions"""
    try:
        from app.models.system_config import SystemConfig
        
        authorize = request.form.get('authorize') == 'on'
        
        # Update system configuration
        SystemConfig.set('super_admin_role_management_enabled', authorize)
        
        # Log the action
        audit_service = AuditService()
        audit_service.log_role_management_action(
            user_id=getattr(request, 'user_id', 1),
            action='toggle_super_admin_role_management',
            details={'authorized': authorize}
        )
        
        status = 'enabled' if authorize else 'disabled'
        flash(f'Super admin role management {status}', 'success')
        
    except Exception as e:
        logger.error(f"Error toggling super admin role management: {e}")
        flash('Error updating super admin role management permissions', 'danger')
    
    return redirect(url_for('admin.owner.owner_role_management.role_management_dashboard'))


@role_management.route('/assign-role', methods=['POST'])
@login_required
@require_owner_role
def assign_role():
    """Assign a role to a user"""
    try:
        user_id = request.form.get('user_id')
        role = request.form.get('role')
        reason = request.form.get('reason', 'Role assignment by owner')
        
        if not user_id or not role:
            flash('User ID and role are required', 'danger')
            return redirect(url_for('admin.owner.owner_role_management.role_management_dashboard'))
        
        user = User.query.get(user_id)
        if not user:
            flash('User not found', 'danger')
            return redirect(url_for('admin.owner.owner_role_management.role_management_dashboard'))
        
        # Store old role for audit
        old_role = user.role
        
        # Update user role
        user.role = role
        db.session.commit()
        
        # Log the action
        audit_service = AuditService()
        audit_service.log_role_change(
            user_id=user.id,
            old_role=old_role,
            new_role=role,
            changed_by=getattr(request, 'user_id', 1),
            reason=reason
        )
        
        flash(f'Role assigned successfully: {user.username} is now {role}', 'success')
        
    except Exception as e:
        logger.error(f"Error assigning role: {e}")
        flash('Error assigning role', 'danger')
    
    return redirect(url_for('admin.owner.owner_role_management.role_management_dashboard'))


@role_management.route('/revoke-role', methods=['POST'])
@login_required
@require_owner_role
def revoke_role():
    """Revoke a role from a user"""
    try:
        user_id = request.form.get('user_id')
        reason = request.form.get('reason', 'Role revocation by owner')
        
        if not user_id:
            flash('User ID is required', 'danger')
            return redirect(url_for('admin.owner.owner_role_management.role_management_dashboard'))
        
        user = User.query.get(user_id)
        if not user:
            flash('User not found', 'danger')
            return redirect(url_for('admin.owner.owner_role_management.role_management_dashboard'))
        
        # Store old role for audit
        old_role = user.role
        
        # Reset to user role
        user.role = 'user'
        db.session.commit()
        
        # Log the action
        audit_service = AuditService()
        audit_service.log_role_change(
            user_id=user.id,
            old_role=old_role,
            new_role='user',
            changed_by=getattr(request, 'user_id', 1),
            reason=reason
        )
        
        flash(f'Role revoked successfully: {user.username} is now a regular user', 'success')
        
    except Exception as e:
        logger.error(f"Error revoking role: {e}")
        flash('Error revoking role', 'danger')
    
    return redirect(url_for('admin.owner.owner_role_management.role_management_dashboard'))


@role_management.route('/users')
@login_required
@require_owner_role
def manage_users():
    """Manage all users with role assignment capabilities"""
    try:
        page = request.args.get('page', 1, type=int)
        search = request.args.get('search', '')
        role_filter = request.args.get('role', '')
        
        # Build query
        query = User.query
        
        if search:
            query = query.filter(
                User.username.ilike(f'%{search}%') |
                User.email.ilike(f'%{search}%')
            )
        
        if role_filter:
            query = query.filter_by(role=role_filter)
        
        # Paginate
        users = query.order_by(User.created_at.desc()).paginate(
            page=page, per_page=20, error_out=False
        )
        
        # Get available roles
        available_roles = [
            'user', 'moderator', 'auditor', 'compliance_officer', 'support',
            'event_manager', 'transport_admin', 'wallet_admin', 'accommodation_admin',
            'tourism_admin', 'org_admin', 'org_member', 'admin', 'super_admin'
        ]
        
        return render_template('owner/role_management/users.html',
                             users=users,
                             available_roles=available_roles,
                             search=search,
                             role_filter=role_filter)
        
    except Exception as e:
        logger.error(f"Error loading user management: {e}")
        flash('Error loading user management', 'danger')
        return redirect(url_for('admin.owner.owner_role_management.role_management_dashboard'))


@role_management.route('/audit-log')
@login_required
@require_owner_role
def role_audit_log():
    """View role management audit log"""
    try:
        page = request.args.get('page', 1, type=int)
        
        audit_service = AuditService()
        pagination, audit_items = audit_service.get_role_management_audit_log(
            page=page, per_page=50
        )
        
        # Create a simple pagination object for the template
        class SimplePagination:
            def __init__(self, page, per_page, total):
                self.page = page
                self.per_page = per_page
                self.total = total
                self.pages = (total + per_page - 1) // per_page
                
            @property
            def has_prev(self):
                return self.page > 1
                
            @property
            def has_next(self):
                return self.page < self.pages
                
            @property
            def prev_num(self):
                return self.page - 1 if self.has_prev else None
                
            @property
            def next_num(self):
                return self.page + 1 if self.has_next else None
                
            def iter_pages(self):
                current = self.page
                last = self.pages
                for num in range(1, last + 1):
                    if num == 1 or num == last or (current - 2 <= num <= current + 2):
                        yield num
                    elif num == current - 3 or num == current + 3:
                        yield '...'
        
        if pagination:
            audit_pagination = SimplePagination(page, 50, pagination.total)
        else:
            audit_pagination = SimplePagination(page, 50, 0)
        
        return render_template('owner/role_management/audit_log.html',
                             audit_logs=audit_pagination,
                             audit_items=audit_items)
        
    except Exception as e:
        logger.error(f"Error loading audit log: {e}")
        flash('Error loading audit log', 'danger')
        return redirect(url_for('admin.owner.owner_role_management.role_management_dashboard'))
