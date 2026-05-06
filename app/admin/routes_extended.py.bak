"""
Extended Admin Routes for AFCON360
Additional functionality for role management and dashboards
"""

from flask import Blueprint, render_template, redirect, url_for, request, flash
from flask_login import login_required, current_user
import logging

from app.extensions import db
from app.auth.decorators import admin_required, require_role

logger = logging.getLogger(__name__)

# Create a separate blueprint for extended admin routes
admin_extended_bp = Blueprint('admin_extended', __name__, url_prefix='/admin')


# -----------------------------
# Role Management
# -----------------------------
@admin_extended_bp.route("/roles", endpoint="manage_roles")
@login_required
@admin_required
def manage_roles():
    """Manage system roles and permissions"""
    from app.identity.models.roles_permission import Role
    from app.identity.models.user import User

    try:
        roles = Role.query.order_by(Role.level.asc()).all()

        # Get user count for each role
        role_stats = {}
        for role in roles:
            try:
                from app.identity.models.roles_permission import UserRole
                user_count = db.session.query(UserRole.user_id).filter(UserRole.role_id == role.id).count()
                role_stats[role.id] = user_count
            except Exception:
                role_stats[role.id] = 0

        return render_template("admin/manage_roles.html", roles=roles, role_stats=role_stats)
    except Exception as e:
        logger.error(f"Error loading roles: {e}")
        flash("Error loading roles.", "danger")
        return redirect(url_for("admin.super_dashboard"))


@admin_extended_bp.route("/roles/<int:role_id>/users", endpoint="role_users")
@login_required
@admin_required
def role_users(role_id):
    """View users with a specific role"""
    from app.identity.models.roles_permission import Role, UserRole
    from app.identity.models.user import User

    try:
        role = Role.query.get_or_404(role_id)

        # Get users with this role
        users = db.session.query(User).join(UserRole).filter(UserRole.role_id == role_id).all()

        return render_template("admin/role_users.html", role=role, users=users)
    except Exception as e:
        logger.error(f"Error loading role users: {e}")
        flash("Error loading role users.", "danger")
        return redirect(url_for("admin.manage_roles"))


@admin_extended_bp.route("/roles/assign", methods=["POST"], endpoint="assign_role")
@login_required
@admin_required
def assign_role():
    """Assign a role to a user"""
    from app.identity.models.user import User
    from app.identity.models.roles_permission import Role
    from app.auth.roles import assign_global_role

    try:
        user_id = request.form.get("user_id")
        role_id = request.form.get("role_id")

        if not user_id or not role_id:
            flash("User ID and Role ID are required.", "danger")
            return redirect(url_for("admin.manage_roles"))

        user = User.query.get(user_id)
        role = Role.query.get(role_id)

        if not user or not role:
            flash("User or role not found.", "danger")
            return redirect(url_for("admin.manage_roles"))

        assign_global_role(user.id, role.name)
        flash(f"Role '{role.name}' assigned to {user.username}.", "success")

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error assigning role: {e}")
        flash(f"Error assigning role: {e}", "danger")

    return redirect(url_for("admin.manage_roles"))


@admin_extended_bp.route("/roles/remove", methods=["POST"], endpoint="remove_role")
@login_required
@admin_required
def remove_role():
    """Remove a role from a user"""
    from app.identity.models.user import User
    from app.identity.models.roles_permission import Role, UserRole
    from app.auth.roles import revoke_global_role

    try:
        user_id = request.form.get("user_id")
        role_id = request.form.get("role_id")

        if not user_id or not role_id:
            flash("User ID and Role ID are required.", "danger")
            return redirect(url_for("admin.manage_roles"))

        user = User.query.get(user_id)
        role = Role.query.get(role_id)

        if not user or not role:
            flash("User or role not found.", "danger")
            return redirect(url_for("admin.manage_roles"))

        # Prevent removing owner role from owner
        if role.name == "owner" and user.user_id == current_user.user_id:
            flash("You cannot remove the owner role from yourself.", "danger")
            return redirect(url_for("admin.manage_roles"))

        revoke_global_role(user.id, role.name)
        flash(f"Role '{role.name}' removed from {user.username}.", "success")

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error removing role: {e}")
        flash(f"Error removing role: {e}", "danger")

    return redirect(url_for("admin.manage_roles"))


# -----------------------------
# Dashboard Routes
# -----------------------------
@admin_extended_bp.route("/super-dashboard", endpoint="super_dashboard")
@login_required
@admin_required
def super_dashboard():
    """Super Admin Dashboard"""
    from app.identity.models.user import User
    from app.identity.models.roles_permission import Role
    from app.identity.models.organisation import Organisation

    try:
        # Get statistics
        total_users = User.query.count()
        active_users = User.query.filter_by(is_active=True).count()
        total_roles = Role.query.count()
        total_orgs = Organisation.query.count() if Organisation else 0

        return render_template("admin/super_dashboard.html",
                             total_users=total_users,
                             active_users=active_users,
                             total_roles=total_roles,
                             total_orgs=total_orgs)
    except Exception as e:
        logger.error(f"Error loading super dashboard: {e}")
        return render_template("admin/super_dashboard.html")


@admin_extended_bp.route("/moderator-dashboard", endpoint="moderator_dashboard")
@login_required
@require_role("moderator", "admin", "super_admin", "owner")
def moderator_dashboard():
    """Moderator Dashboard"""
    try:
        # Mock data for demonstration
        return render_template("admin/moderator_dashboard.html",
                             pending_reports=5,
                             flagged_content=12,
                             moderated_today=8,
                             active_users=156)
    except Exception as e:
        logger.error(f"Error loading moderator dashboard: {e}")
        return render_template("admin/moderator_dashboard.html")


@admin_extended_bp.route("/support-dashboard", endpoint="support_dashboard")
@login_required
@require_role("support", "admin", "super_admin", "owner")
def support_dashboard():
    """Support Dashboard"""
    try:
        # Mock data for demonstration
        return render_template("admin/support_dashboard.html",
                             open_tickets=23,
                             pending_responses=8,
                             resolved_today=15,
                             avg_response_time="2.5h")
    except Exception as e:
        logger.error(f"Error loading support dashboard: {e}")
        return render_template("admin/support_dashboard.html")


@admin_extended_bp.route("/auditor-dashboard", endpoint="auditor_dashboard")
@login_required
@require_role("auditor", "admin", "super_admin", "owner")
def auditor_dashboard():
    """Auditor Dashboard"""
    try:
        # Mock data for demonstration
        return render_template("admin/auditor_dashboard.html",
                             critical_findings=2,
                             pending_reviews=7,
                             compliance_score="96%",
                             audits_completed=24)
    except Exception as e:
        logger.error(f"Error loading auditor dashboard: {e}")
        return render_template("admin/auditor_dashboard.html")
