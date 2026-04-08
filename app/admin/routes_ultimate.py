"""
Ultimate Admin Routes for User Management
Combines the best features from all 3 versions with enhanced functionality
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
from flask_login import login_required, current_user
from sqlalchemy import func
from app.extensions import db
from app.identity.models.user import User
from app.identity.models.roles_permission import Role
from app.auth.roles import assign_global_role, revoke_global_role
from app.decorators import admin_required
import logging

logger = logging.getLogger(__name__)

admin_bp = Blueprint('admin_ultimate', __name__, url_prefix='/admin')

@admin_bp.route('/manage-users')
@login_required
@admin_required
def manage_users():
    """Ultimate user management interface"""
    try:
        page = request.args.get('page', 1, type=int)
        per_page = 50

        # Get users with pagination
        users = User.query.order_by(User.created_at.desc()).paginate(
            page=page, per_page=per_page, error_out=False
        )

        # Get total roles count
        total_roles = Role.query.count()

        return render_template('admin/manage_users_ultimate.html',
                             users=users,
                             total_roles=total_roles)

    except Exception as e:
        logger.error(f"Error loading user management: {e}")
        flash("Error loading user management interface", "danger")
        return redirect(url_for('index'))

@admin_bp.route('/verify-user/<int:user_id>', methods=['POST'])
@login_required
@admin_required
def verify_user(user_id):
    """Verify a user without email verification"""
    try:
        user = User.query.get_or_404(user_id)
        user.is_verified = True
        db.session.commit()

        logger.info(f"Admin {current_user.username} verified user {user.username}")
        flash(f"User {user.username} has been verified successfully", "success")

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error verifying user {user_id}: {e}")
        flash("Error verifying user", "danger")

    return redirect(url_for('admin_ultimate.manage_users'))

@admin_bp.route('/activate-user/<int:user_id>', methods=['POST'])
@login_required
@admin_required
def activate_user(user_id):
    """Activate a user account"""
    try:
        user = User.query.get_or_404(user_id)
        user.is_active = True
        db.session.commit()

        logger.info(f"Admin {current_user.username} activated user {user.username}")
        flash(f"User {user.username} has been activated", "success")

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error activating user {user_id}: {e}")
        flash("Error activating user", "danger")

    return redirect(url_for('admin_ultimate.manage_users'))

@admin_bp.route('/deactivate-user/<int:user_id>', methods=['POST'])
@login_required
@admin_required
def deactivate_user(user_id):
    """Deactivate a user account"""
    try:
        user = User.query.get_or_404(user_id)
        user.is_active = False
        db.session.commit()

        logger.info(f"Admin {current_user.username} deactivated user {user.username}")
        flash(f"User {user.username} has been deactivated", "warning")

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error deactivating user {user_id}: {e}")
        flash("Error deactivating user", "danger")

    return redirect(url_for('admin_ultimate.manage_users'))

@admin_bp.route('/delete-user/<int:user_id>', methods=['POST'])
@login_required
@admin_required
def delete_user(user_id):
    """Delete a user permanently"""
    try:
        user = User.query.get_or_404(user_id)

        # Prevent self-deletion
        if user.id == current_user.id:
            flash("You cannot delete your own account", "danger")
            return redirect(url_for('admin_ultimate.manage_users'))

        username = user.username
        db.session.delete(user)
        db.session.commit()

        logger.warning(f"Admin {current_user.username} deleted user {username}")
        flash(f"User {username} has been deleted permanently", "success")

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error deleting user {user_id}: {e}")
        flash("Error deleting user", "danger")

    return redirect(url_for('admin_ultimate.manage_users'))

@admin_bp.route('/bulk-verify-users', methods=['POST'])
@login_required
@admin_required
def bulk_verify_users():
    """Bulk verify multiple users"""
    try:
        user_ids = request.form.getlist('user_ids')
        if not user_ids:
            flash("No users selected", "warning")
            return redirect(url_for('admin_ultimate.manage_users'))

        verified_count = 0
        for user_id in user_ids:
            user = User.query.get(int(user_id))
            if user and not user.is_verified:
                user.is_verified = True
                verified_count += 1

        db.session.commit()

        logger.info(f"Admin {current_user.username} bulk verified {verified_count} users")
        flash(f"{verified_count} users have been verified successfully", "success")

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error in bulk verification: {e}")
        flash("Error in bulk verification", "danger")

    return redirect(url_for('admin_ultimate.manage_users'))

@admin_bp.route('/bulk-activate-users', methods=['POST'])
@login_required
@admin_required
def bulk_activate_users():
    """Bulk activate multiple users"""
    try:
        user_ids = request.form.getlist('user_ids')
        if not user_ids:
            flash("No users selected", "warning")
            return redirect(url_for('admin_ultimate.manage_users'))

        activated_count = 0
        for user_id in user_ids:
            user = User.query.get(int(user_id))
            if user and not user.is_active:
                user.is_active = True
                activated_count += 1

        db.session.commit()

        logger.info(f"Admin {current_user.username} bulk activated {activated_count} users")
        flash(f"{activated_count} users have been activated successfully", "success")

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error in bulk activation: {e}")
        flash("Error in bulk activation", "danger")

    return redirect(url_for('admin_ultimate.manage_users'))

@admin_bp.route('/bulk-deactivate-users', methods=['POST'])
@login_required
@admin_required
def bulk_deactivate_users():
    """Bulk deactivate multiple users"""
    try:
        user_ids = request.form.getlist('user_ids')
        if not user_ids:
            flash("No users selected", "warning")
            return redirect(url_for('admin_ultimate.manage_users'))

        deactivated_count = 0
        for user_id in user_ids:
            user = User.query.get(int(user_id))
            if user and user.is_active and user.id != current_user.id:
                user.is_active = False
                deactivated_count += 1

        db.session.commit()

        logger.info(f"Admin {current_user.username} bulk deactivated {deactivated_count} users")
        flash(f"{deactivated_count} users have been deactivated", "warning")

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error in bulk deactivation: {e}")
        flash("Error in bulk deactivation", "danger")

    return redirect(url_for('admin_ultimate.manage_users'))

@admin_bp.route('/view-user/<int:user_id>')
@login_required
@admin_required
def view_user(user_id):
    """View detailed user information"""
    try:
        user = User.query.get_or_404(user_id)

        # Get user roles
        user_roles = []
        try:
            from app.identity.models.roles_permission import UserRole
            roles = db.session.query(Role.name).join(UserRole).filter(UserRole.user_id == user.id).all()
            user_roles = [role[0] for role in roles]
        except Exception:
            user_roles = []

        return render_template('admin/view_user_ultimate.html',
                             user=user,
                             user_roles=user_roles)

    except Exception as e:
        logger.error(f"Error viewing user {user_id}: {e}")
        flash("Error loading user details", "danger")
        return redirect(url_for('admin_ultimate.manage_users'))

@admin_bp.route('/promote-user/<int:user_id>', methods=['POST'])
@login_required
@admin_required
def promote_user(user_id):
    """Promote user to next higher role"""
    try:
        user = User.query.get_or_404(user_id)

        # Define role hierarchy
        role_hierarchy = [
            'user',
            'org_member',
            'org_admin',
            'support',
            'moderator',
            'auditor',
            'compliance_officer',
            'admin',
            'super_admin'
        ]

        # Get current highest role
        current_roles = []
        try:
            from app.identity.models.roles_permission import UserRole
            roles = db.session.query(Role.name).join(UserRole).filter(UserRole.user_id == user.id).all()
            current_roles = [role[0] for role in roles if role[0] in role_hierarchy]
        except Exception:
            pass

        if not current_roles:
            current_role = 'user'
        else:
            # Find highest current role
            current_role = max(current_roles, key=lambda x: role_hierarchy.index(x))

        # Find next role in hierarchy
        current_index = role_hierarchy.index(current_role)
        if current_index < len(role_hierarchy) - 1:
            next_role = role_hierarchy[current_index + 1]
            assign_global_role(user.id, next_role)

            logger.info(f"Admin {current_user.username} promoted {user.username} to {next_role}")
            flash(f"User {user.username} promoted to {next_role.replace('_', ' ').title()}", "success")
        else:
            flash(f"User {user.username} is already at the highest role level", "info")

        db.session.commit()

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error promoting user {user_id}: {e}")
        flash("Error promoting user", "danger")

    return redirect(url_for('admin_ultimate.manage_users'))

@admin_bp.route('/demote-user/<int:user_id>', methods=['POST'])
@login_required
@admin_required
def demote_user(user_id):
    """Demote user to next lower role"""
    try:
        user = User.query.get_or_404(user_id)

        # Define role hierarchy
        role_hierarchy = [
            'user',
            'org_member',
            'org_admin',
            'support',
            'moderator',
            'auditor',
            'compliance_officer',
            'admin',
            'super_admin'
        ]

        # Get current highest role
        current_roles = []
        try:
            from app.identity.models.roles_permission import UserRole
            roles = db.session.query(Role.name).join(UserRole).filter(UserRole.user_id == user.id).all()
            current_roles = [role[0] for role in roles if role[0] in role_hierarchy]
        except Exception:
            pass

        if not current_roles:
            flash(f"User {user.username} is already at the lowest role level", "info")
            return redirect(url_for('admin_ultimate.manage_users'))

        # Find highest current role
        current_role = max(current_roles, key=lambda x: role_hierarchy.index(x))

        # Find previous role in hierarchy
        current_index = role_hierarchy.index(current_role)
        if current_index > 0:
            prev_role = role_hierarchy[current_index - 1]

            # Revoke current role and assign lower role
            revoke_global_role(user.id, current_role)
            assign_global_role(user.id, prev_role)

            logger.info(f"Admin {current_user.username} demoted {user.username} to {prev_role}")
            flash(f"User {user.username} demoted to {prev_role.replace('_', ' ').title()}", "warning")
        else:
            flash(f"User {user.username} is already at the lowest role level", "info")

        db.session.commit()

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error demoting user {user_id}: {e}")
        flash("Error demoting user", "danger")

    return redirect(url_for('admin_ultimate.manage_users'))

@admin_bp.route('/sign-in-as/<int:user_id>', methods=['POST'])
@login_required
@admin_required
def sign_in_as(user_id):
    """Sign in as another user (impersonation)"""
    try:
        target_user = User.query.get_or_404(user_id)

        # Prevent self-impersonation
        if target_user.id == current_user.id:
            flash("You cannot impersonate yourself", "warning")
            return redirect(url_for('admin_ultimate.manage_users'))

        # Store original admin info in session
        from flask import session
        session['impersonated_by'] = current_user.id
        session['impersonated_by_name'] = current_user.username
        session['is_impersonating'] = True

        # Log out current user and log in as target user
        from flask_login import logout_user, login_user
        logout_user()
        login_user(target_user)

        logger.info(f"Admin {current_user.username} started impersonating {target_user.username}")
        flash(f"You are now acting as {target_user.username}", "info")

        return redirect(url_for('index'))

    except Exception as e:
        logger.error(f"Error impersonating user {user_id}: {e}")
        flash("Error impersonating user", "danger")

    return redirect(url_for('admin_ultimate.manage_users'))

def register_admin_routes(app):
    """Register the ultimate admin routes"""
    app.register_blueprint(admin_bp)
