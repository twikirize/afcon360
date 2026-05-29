# app/admin/decorators.py
"""
Admin decorators with emergency access support.
"""

from functools import wraps
from flask import flash, redirect, url_for, request
from flask_login import current_user, login_required

from app.auth.decorators import admin_required
from app.admin.models.emergency_access import EmergencyAccess


def require_emergency_access_or_role(*required_roles, action="access"):
    """
    Require either normal role permissions OR valid emergency access.
    
    This decorator allows emergency access to bypass normal role restrictions
    during critical incidents while maintaining audit trails.
    
    Args:
        *required_roles: Normal role requirements
        action: The action being performed (for emergency access validation)
    """
    def decorator(f):
        @wraps(f)
        @login_required
        def decorated_function(*args, **kwargs):
            # Check normal role permissions first
            from app.auth.helpers import has_global_role
            if has_global_role(current_user, *required_roles):
                return f(*args, **kwargs)
            
            # Check emergency access
            emergency_access = EmergencyAccess.get_active_emergency_access(current_user.id)
            if not emergency_access:
                flash("This action requires admin privileges.", "danger")
                return redirect(url_for("auth.login"))
            
            # Validate emergency access for this specific action
            valid_access = None
            for access in emergency_access:
                if access.can_perform_action(action):
                    valid_access = access
                    break
            
            if not valid_access:
                flash(f"Emergency access does not permit action: {action}", "danger")
                return redirect(url_for("auth.login"))
            
            # Add emergency access context to request
            request.emergency_access = valid_access
            
            # Log emergency access usage
            try:
                from app.audit.comprehensive_audit import AuditService
                AuditService.data_change(
                    entity_type="emergency_access_usage",
                    entity_id=valid_access.id,
                    operation="use",
                    old_value=None,
                    new_value={
                        "action": action,
                        "endpoint": request.endpoint,
                        "user_id": current_user.id,
                        "access_level": valid_access.access_level
                    },
                    changed_by=current_user.id,
                    ip_address=request.remote_addr,
                    user_agent=request.user_agent.string if request.user_agent else None,
                    extra_data={
                        "jira_ticket": valid_access.jira_ticket,
                        "emergency_access_id": valid_access.id
                    }
                )
            except Exception as e:
                import logging
                logging.error(f"Failed to audit emergency access usage: {e}")
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator


def emergency_access_required(action="access"):
    """
    Require valid emergency access (no normal role bypass).
    
    Used for highly sensitive operations that should only be available
    during emergency situations.
    """
    def decorator(f):
        @wraps(f)
        @login_required
        def decorated_function(*args, **kwargs):
            emergency_access = EmergencyAccess.get_active_emergency_access(current_user.id)
            if not emergency_access:
                flash("This action requires emergency access privileges.", "danger")
                return redirect(url_for("auth.login"))
            
            # Validate emergency access for this specific action
            valid_access = None
            for access in emergency_access:
                if access.can_perform_action(action):
                    valid_access = access
                    break
            
            if not valid_access:
                flash(f"Emergency access does not permit action: {action}", "danger")
                return redirect(url_for("auth.login"))
            
            # Add emergency access context to request
            request.emergency_access = valid_access
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator


def owner_or_emergency_access_required(action="owner_action"):
    """
    Require owner role OR valid emergency access with full privileges.
    
    This allows emergency access to perform owner-level actions during
    critical incidents while maintaining security.
    """
    def decorator(f):
        @wraps(f)
        @login_required
        def decorated_function(*args, **kwargs):
            # Check owner status first
            from app.auth.helpers import is_owner
            if is_owner(current_user):
                return f(*args, **kwargs)
            
            # Check emergency access
            emergency_access = EmergencyAccess.get_active_emergency_access(current_user.id)
            if not emergency_access:
                flash("This action requires owner privileges.", "danger")
                return redirect(url_for("auth.login"))
            
            # Validate emergency access has full privileges
            valid_access = None
            for access in emergency_access:
                if access.access_level == "full" and access.can_perform_action(action):
                    valid_access = access
                    break
            
            if not valid_access:
                flash(f"Emergency access requires full privileges for action: {action}", "danger")
                return redirect(url_for("auth.login"))
            
            # Add emergency access context to request
            request.emergency_access = valid_access
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator
