#app/admin/routes.py
"""
Admin Routes for AFCON360 - Super Admin, Content Management, User Management
"""

from datetime import datetime
import uuid
import logging
from flask import (
    render_template, redirect, url_for,
    current_app, request, flash, jsonify
)
from flask_login import login_required, current_user
from functools import wraps

from app.admin import admin_bp
from app.extensions import db
from app.identity.models import Organisation, Role, OrganisationAuditLog
from app.identity.models.user import User
from app.profile.models import UserProfile
from sqlalchemy import func, case, or_, and_
from sqlalchemy.orm import joinedload

# Import content management models
from app.admin.models import (
    ManageableCategory, ManageableItem,
    ContentSubmission, UserDashboardConfig
)

# Setup logging
logger = logging.getLogger(__name__)


# -------------------------------
# Decorators
# -------------------------------

def admin_required(f):
    """Decorator to require admin access."""

    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            flash("Please login to access admin area", "warning")
            return redirect(url_for('auth.login'))

        # Check if user has admin role
        if not current_user.has_global_role('admin', 'super_admin', 'app_owner'):
            flash("Access denied. Admin privileges required.", "danger")
            return redirect(url_for('index'))

        return f(*args, **kwargs)

    return decorated_function


def assign_role(user_id, role_name):
    """Helper function to assign a role to a user."""
    try:
        role = Role.query.filter_by(name=role_name).first()
        if role:
            from app.identity.models import UserRole
            user_role = UserRole.query.filter_by(
                user_id=user_id,
                role_id=role.id
            ).first()
            if not user_role:
                user_role = UserRole(user_id=user_id, role_id=role.id)
                db.session.add(user_role)
                return True
        return False
    except Exception as e:
        logger.error(f"Error assigning role {role_name} to user {user_id}: {e}")
        return False


def remove_role(user_id, role_name):
    """Helper function to remove a role from a user."""
    try:
        role = Role.query.filter_by(name=role_name).first()
        if role:
            from app.identity.models import UserRole
            user_role = UserRole.query.filter_by(
                user_id=user_id,
                role_id=role.id
            ).first()
            if user_role:
                db.session.delete(user_role)
                return True
        return False
    except Exception as e:
        logger.error(f"Error removing role {role_name} from user {user_id}: {e}")
        return False


# -----------------------------
# Super Admin Dashboard
# -----------------------------
@admin_bp.route("/super", endpoint="super_dashboard")
# @admin_required
def super_dashboard():
    """
    Super Admin overview dashboard:
    - Shows user stats (total, verified, unverified)
    - Displays module/feature toggles
    - Transport module settings
    """
    try:
        total_users = User.query.count()
        verified_users = User.query.filter_by(is_verified=True).count()
        unverified_users = total_users - verified_users

        # Get recent audit logs
        audit_logs = OrganisationAuditLog.query.order_by(
            OrganisationAuditLog.changed_at.desc()
        ).limit(10).all()

        # Get content stats
        manageable_categories = ManageableCategory.query.filter_by(is_active=True).all()
        manageable_items = ManageableItem.query.filter_by(is_approved=True).all()

        return render_template(
            "super_admindashboard.html",
            total_users=total_users,
            verified_users=verified_users,
            unverified_users=unverified_users,
            audit_logs=audit_logs,
            manageable_categories=manageable_categories,
            manageable_items=manageable_items,
            modules=current_app.config.get("MODULE_FLAGS", {}),
            wallet_features=current_app.config.get("WALLET_FEATURES", {}),
            tourism_features=current_app.config.get("TOURISM_FEATURES", {}),
            accommodation_features=current_app.config.get("ACCOMMODATION_FEATURES", {}),
            transport_features=current_app.config.get("TRANSPORT_FEATURES", {}),
        )
    except Exception as e:
        logger.error(f"Error loading super admin dashboard: {e}")
        flash("Error loading dashboard. Please try again.", "danger")
        return redirect(url_for('index'))


# -----------------------------
# Manage Users
# -----------------------------
@admin_bp.route("/users", endpoint="manage_users")
# @admin_required
def manage_users():
    """List all users for admin management."""
    try:
        users = User.query.order_by(User.created_at.desc()).all()
        return render_template("admin/manage_users.html", users=users)
    except Exception as e:
        logger.error(f"Error loading users list: {e}")
        flash("Error loading users. Please try again.", "danger")
        return redirect(url_for("admin.super_dashboard"))


# -----------------------------
# Single User Actions
# -----------------------------
@admin_bp.route("/users/<string:user_id>/verify", methods=["POST"], endpoint="verify_user")
# @admin_required
def verify_user(user_id):
    """Verify a user account."""
    try:
        user = User.query.filter_by(user_id=user_id).first()
        if not user:
            flash("User not found.", "danger")
            return redirect(url_for("admin.manage_users"))

        user.is_verified = True
        profile = UserProfile.query.filter_by(user_id=user.user_id).first()
        if profile:
            profile.mark_verified(reviewer="admin")

        db.session.commit()
        logger.info(f"User {user.username} verified by admin")
        flash(f"User {user.username} verified successfully.", "success")

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error verifying user {user_id}: {e}")
        flash(f"Error verifying user: {str(e)}", "danger")

    return redirect(url_for("admin.manage_users"))


@admin_bp.route("/users/<string:user_id>/activate", methods=["POST"], endpoint="activate_user")
# @admin_required
def activate_user(user_id):
    """Activate a user account."""
    try:
        user = User.query.filter_by(user_id=user_id).first()
        if not user:
            flash("User not found.", "danger")
            return redirect(url_for("admin.manage_users"))

        user.is_active = True
        db.session.commit()
        logger.info(f"User {user.username} activated by admin")
        flash(f"User {user.username} activated successfully.", "success")

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error activating user {user_id}: {e}")
        flash(f"Error activating user: {str(e)}", "danger")

    return redirect(url_for("admin.manage_users"))


@admin_bp.route("/users/<string:user_id>/deactivate", methods=["POST"], endpoint="deactivate_user")
# @admin_required
def deactivate_user(user_id):
    """Deactivate a user account."""
    try:
        user = User.query.filter_by(user_id=user_id).first()
        if not user:
            flash("User not found.", "danger")
            return redirect(url_for("admin.manage_users"))

        user.is_active = False
        db.session.commit()
        logger.info(f"User {user.username} deactivated by admin")
        flash(f"User {user.username} deactivated successfully.", "warning")

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error deactivating user {user_id}: {e}")
        flash(f"Error deactivating user: {str(e)}", "danger")

    return redirect(url_for("admin.manage_users"))


# -----------------------------
# Bulk Actions
# -----------------------------
@admin_bp.route("/users/bulk_verify", methods=["POST"], endpoint="bulk_verify_users")
# @admin_required
def bulk_verify_users():
    """Bulk verify multiple users."""
    try:
        ids = request.form.getlist("user_ids")
        if not ids:
            flash("No users selected.", "warning")
            return redirect(url_for("admin.manage_users"))

        valid_ids = []
        for uid in ids:
            try:
                uuid.UUID(uid)
                valid_ids.append(uid)
            except ValueError:
                continue

        if not valid_ids:
            flash("No valid user IDs submitted.", "danger")
            return redirect(url_for("admin.manage_users"))

        updated = User.query.filter(User.user_id.in_(valid_ids)).update(
            {"is_verified": True}, synchronize_session=False
        )
        db.session.commit()

        logger.info(f"Bulk verified {updated} users")
        flash(f"{updated} users verified successfully." if updated else "No matching users found.", "success")

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error in bulk verify: {e}")
        flash(f"Error verifying users: {str(e)}", "danger")

    return redirect(url_for("admin.manage_users"))


@admin_bp.route("/users/bulk_deactivate", methods=["POST"], endpoint="bulk_deactivate_users")
# @admin_required
def bulk_deactivate_users():
    """Bulk deactivate multiple users."""
    try:
        ids = request.form.getlist("user_ids")
        if not ids:
            flash("No users selected.", "warning")
            return redirect(url_for("admin.manage_users"))

        valid_ids = []
        for uid in ids:
            try:
                uuid.UUID(uid)
                valid_ids.append(uid)
            except ValueError:
                continue

        if not valid_ids:
            flash("No valid user IDs submitted.", "danger")
            return redirect(url_for("admin.manage_users"))

        updated = User.query.filter(User.user_id.in_(valid_ids)).update(
            {"is_active": False}, synchronize_session=False
        )
        db.session.commit()

        logger.info(f"Bulk deactivated {updated} users")
        flash(f"{updated} users deactivated successfully." if updated else "No matching users found.", "info")

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error in bulk deactivate: {e}")
        flash(f"Error deactivating users: {str(e)}", "danger")

    return redirect(url_for("admin.manage_users"))


# -----------------------------
# View User
# -----------------------------
@admin_bp.route("/users/<string:user_id>", endpoint="view_user")
# @admin_required
def view_user(user_id):
    """View detailed user information."""
    try:
        user = User.query.filter_by(user_id=user_id).first_or_404()
        return render_template("admin/view_user.html", user=user)
    except Exception as e:
        logger.error(f"Error viewing user {user_id}: {e}")
        flash("Error loading user details.", "danger")
        return redirect(url_for("admin.manage_users"))


# -----------------------------
# Module Toggles
# -----------------------------
@admin_bp.route("/toggle/<module>", methods=["POST"], endpoint="toggle_module")
# @admin_required
def toggle_module(module):
    """Enable/disable a whole module from config flags."""
    try:
        flags = current_app.config.get("MODULE_FLAGS", {})
        if module in flags:
            old_value = flags[module]
            flags[module] = not bool(flags[module])
            logger.info(f"Module {module} toggled: {old_value} → {flags[module]}")
            flash(f"Module '{module}' {'enabled' if flags[module] else 'disabled'} successfully.", "success")
        else:
            flash(f"Module '{module}' not found.", "warning")
    except Exception as e:
        logger.error(f"Error toggling module {module}: {e}")
        flash("Error updating module settings.", "danger")

    return redirect(url_for("admin.super_dashboard"))


@admin_bp.route("/toggle-wallet/<feature>", methods=["POST"], endpoint="toggle_wallet_feature")
# @admin_required
def toggle_wallet_feature(feature):
    """Enable/disable a wallet feature or sub-feature."""
    try:
        wallet_flags = current_app.config.get("WALLET_FEATURES", {})
        if feature in wallet_flags:
            if isinstance(wallet_flags[feature], bool):
                old_value = wallet_flags[feature]
                wallet_flags[feature] = not wallet_flags[feature]
            elif isinstance(wallet_flags[feature], dict) and "enabled" in wallet_flags[feature]:
                old_value = wallet_flags[feature]["enabled"]
                wallet_flags[feature]["enabled"] = not wallet_flags[feature]["enabled"]

            logger.info(f"Wallet feature {feature} toggled: {old_value} → {wallet_flags[feature]}")
            flash(f"Wallet feature '{feature}' updated successfully.", "success")
        else:
            flash(f"Wallet feature '{feature}' not found.", "warning")
    except Exception as e:
        logger.error(f"Error toggling wallet feature {feature}: {e}")
        flash("Error updating wallet feature.", "danger")

    return redirect(url_for("admin.super_dashboard"))


@admin_bp.route("/update-withdraw-settings", methods=["POST"], endpoint="update_withdraw_settings")
# @admin_required
def update_withdraw_settings():
    """Update withdraw feature settings (daily limit, verification requirement)."""
    try:
        withdraw_settings = current_app.config["WALLET_FEATURES"].get("withdraw", {})
        if withdraw_settings:
            old_limit = withdraw_settings.get("daily_limit", 0)
            old_verification = withdraw_settings.get("require_verification", False)

            withdraw_settings["daily_limit"] = int(request.form.get("daily_limit", 1000))
            withdraw_settings["require_verification"] = "require_verification" in request.form
            withdraw_settings["require_2fa"] = "require_2fa" in request.form

            logger.info(f"Withdrawal settings updated - Limit: {old_limit} → {withdraw_settings['daily_limit']}")
            flash("Withdrawal settings updated successfully.", "success")
        else:
            flash("Withdrawal settings not found.", "warning")
    except ValueError:
        flash("Invalid daily limit value.", "danger")
    except Exception as e:
        logger.error(f"Error updating withdrawal settings: {e}")
        flash("Error updating withdrawal settings.", "danger")

    return redirect(url_for("admin.super_dashboard"))


# -----------------------------
# Transport Module Settings
# -----------------------------
@admin_bp.route("/toggle-transport/<feature>", methods=["POST"], endpoint="toggle_transport_feature")
# @admin_required
def toggle_transport_feature(feature):
    """Enable/disable a transport feature or sub-feature."""
    try:
        transport_flags = current_app.config.get("TRANSPORT_FEATURES", {})
        if feature in transport_flags:
            if isinstance(transport_flags[feature], bool):
                old_value = transport_flags[feature]
                transport_flags[feature] = not transport_flags[feature]
            elif isinstance(transport_flags[feature], dict) and "enabled" in transport_flags[feature]:
                old_value = transport_flags[feature]["enabled"]
                transport_flags[feature]["enabled"] = not transport_flags[feature]["enabled"]

            logger.info(f"Transport feature {feature} toggled: {old_value} → {transport_flags[feature]}")
            flash(f"Transport feature '{feature}' updated successfully.", "success")
        else:
            flash(f"Transport feature '{feature}' not found.", "warning")
    except Exception as e:
        logger.error(f"Error toggling transport feature {feature}: {e}")
        flash("Error updating transport feature.", "danger")

    return redirect(url_for("admin.super_dashboard"))


@admin_bp.route("/update-transport-settings", methods=["POST"], endpoint="update_transport_settings")
# @admin_required
def update_transport_settings():
    """Update transport module settings."""
    try:
        transport_features = current_app.config.get("TRANSPORT_FEATURES", {})

        # Update booking settings
        if "booking" in transport_features and isinstance(transport_features["booking"], dict):
            transport_features["booking"]["max_advance_days"] = int(request.form.get("max_advance_days", 90))
            transport_features["booking"]["cancellation_hours"] = int(request.form.get("cancellation_hours", 24))
            transport_features["booking"]["require_deposit"] = "require_deposit" in request.form
            transport_features["booking"]["deposit_percentage"] = int(request.form.get("deposit_percentage", 20))

        # Update driver settings
        if "driver_verification" in transport_features and isinstance(transport_features["driver_verification"], dict):
            transport_features["driver_verification"]["require_license"] = "require_license" in request.form
            transport_features["driver_verification"][
                "require_background_check"] = "require_background_check" in request.form
            transport_features["driver_verification"]["license_expiry_alert_days"] = int(
                request.form.get("license_expiry_alert_days", 30))

        # Update vehicle settings
        if "vehicle_requirements" in transport_features and isinstance(transport_features["vehicle_requirements"],
                                                                       dict):
            transport_features["vehicle_requirements"]["max_vehicle_age"] = int(request.form.get("max_vehicle_age", 10))
            transport_features["vehicle_requirements"]["require_insurance"] = "require_insurance" in request.form
            transport_features["vehicle_requirements"]["require_inspection"] = "require_inspection" in request.form

        logger.info("Transport settings updated successfully")
        flash("Transport settings updated successfully.", "success")

    except ValueError as e:
        flash("Invalid input value. Please check your entries.", "danger")
        logger.error(f"ValueError in transport settings: {e}")
    except Exception as e:
        logger.error(f"Error updating transport settings: {e}")
        flash("Error updating transport settings.", "danger")

    return redirect(url_for("admin.super_dashboard"))


# -----------------------------
# Organisation List
# -----------------------------
@admin_bp.route("/orgs", endpoint="manage_orgs")
# @admin_required
def manage_orgs():
    """Manage all organisations"""
    try:
        # Aggregate counts in one query
        counts = db.session.query(
            func.count(Organisation.id).label("total"),
            func.count(case((Organisation.is_active == True, 1))).label("active"),
            func.count(case((Organisation.is_active == False, 1))).label("suspended"),
            func.count(case((Organisation.verification_status == "pending", 1))).label("pending")
        ).one()

        orgs = Organisation.query.order_by(Organisation.created_at.desc()).all()

        return render_template(
            "admin/manage_orgs.html",
            orgs=orgs,
            total_orgs=counts.total,
            active_orgs=counts.active,
            suspended_orgs=counts.suspended,
            pending_orgs=counts.pending
        )
    except Exception as e:
        logger.error(f"Error loading organisations: {e}")
        flash("Error loading organisations. Please try again.", "danger")
        return redirect(url_for("admin.super_dashboard"))


# -----------------------------
# Ownership Transfer
# -----------------------------
@admin_bp.route("/orgs/<int:org_id>/transfer_owner", methods=["POST"], endpoint="transfer_org_owner")
# @admin_required
def transfer_org_owner(org_id):
    """Transfer organisation ownership to another user."""
    try:
        org = Organisation.query.get(org_id)
        if not org:
            flash("Organisation not found.", "danger")
            return redirect(url_for("admin.manage_orgs"))

        new_owner_id = request.form.get("new_owner_id")
        new_owner = User.query.get(new_owner_id)
        if not new_owner:
            flash("New owner not found.", "danger")
            return redirect(url_for("admin.manage_orgs"))

        old_owner_id = org.owner_id
        org.owner_id = new_owner.id
        db.session.commit()

        logger.info(f"Ownership of {org.name} transferred from user {old_owner_id} to {new_owner.username}")
        flash(f"Ownership of {org.name} transferred to {new_owner.username}.", "success")

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error transferring ownership for org {org_id}: {e}")
        flash("Error transferring ownership.", "danger")

    return redirect(url_for("admin.manage_orgs"))


# -----------------------------
# Activate / Deactivate Organisation
# -----------------------------
@admin_bp.route("/orgs/<int:org_id>/activate", methods=["POST"], endpoint="activate_org")
# @admin_required
def activate_org(org_id):
    """Activate an organisation."""
    try:
        org = Organisation.query.get(org_id)
        if org:
            org.is_active = True
            db.session.commit()
            logger.info(f"Organisation {org.name} activated")
            flash(f"Organisation {org.name} activated successfully.", "success")
        else:
            flash("Organisation not found.", "danger")
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error activating organisation {org_id}: {e}")
        flash("Error activating organisation.", "danger")

    return redirect(url_for("admin.manage_orgs"))


@admin_bp.route("/orgs/<int:org_id>/deactivate", methods=["POST"], endpoint="deactivate_org")
# @admin_required
def deactivate_org(org_id):
    """Deactivate an organisation."""
    try:
        org = Organisation.query.get(org_id)
        if org:
            org.is_active = False
            db.session.commit()
            logger.info(f"Organisation {org.name} deactivated")
            flash(f"Organisation {org.name} deactivated successfully.", "warning")
        else:
            flash("Organisation not found.", "danger")
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error deactivating organisation {org_id}: {e}")
        flash("Error deactivating organisation.", "danger")

    return redirect(url_for("admin.manage_orgs"))


# -----------------------------
# Organisation Members View
# -----------------------------
@admin_bp.route("/orgs/<int:org_id>/members", endpoint="org_members")
# @admin_required
def org_members(org_id):
    """View and manage organisation members."""
    try:
        org = Organisation.query.get(org_id)
        if not org:
            flash("Organisation not found.", "danger")
            return redirect(url_for("admin.manage_orgs"))
        return render_template("admin/org_members.html", org=org)
    except Exception as e:
        logger.error(f"Error loading org members for org {org_id}: {e}")
        flash("Error loading organisation members.", "danger")
        return redirect(url_for("admin.manage_orgs"))


# -----------------------------
# Member Actions
# -----------------------------
@admin_bp.route("/orgs/<int:org_id>/members/<int:user_id>/promote", methods=["POST"], endpoint="promote_member")
# @admin_required
def promote_member(org_id, user_id):
    """Promote member to org admin."""
    try:
        member = User.query.get(user_id)
        if member:
            if assign_role(user_id, "org_admin"):
                db.session.commit()
                logger.info(f"User {member.username} promoted to org_admin in org {org_id}")
                flash(f"{member.username} promoted to organisation admin.", "success")
            else:
                flash("Error promoting user. Role may already be assigned.", "warning")
        else:
            flash("Member not found.", "danger")
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error promoting member {user_id} in org {org_id}: {e}")
        flash("Error promoting member.", "danger")

    return redirect(url_for("admin.org_members", org_id=org_id))


@admin_bp.route("/orgs/<int:org_id>/members/<int:user_id>/demote", methods=["POST"], endpoint="demote_member")
# @admin_required
def demote_member(org_id, user_id):
    """Demote org admin to regular member."""
    try:
        member = User.query.get(user_id)
        if member:
            if remove_role(user_id, "org_admin"):
                db.session.commit()
                logger.info(f"User {member.username} demoted from org_admin in org {org_id}")
                flash(f"{member.username} demoted from organisation admin.", "warning")
            else:
                flash("Error demoting user. Role may not be assigned.", "warning")
        else:
            flash("Member not found.", "danger")
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error demoting member {user_id} in org {org_id}: {e}")
        flash("Error demoting member.", "danger")

    return redirect(url_for("admin.org_members", org_id=org_id))


@admin_bp.route("/orgs/<int:org_id>/members/<int:user_id>/verify", methods=["POST"], endpoint="verify_member")
# @admin_required
def verify_member(org_id, user_id):
    """Verify organisation member."""
    try:
        member = User.query.get(user_id)
        if member:
            member.is_verified = True
            db.session.commit()
            logger.info(f"User {member.username} verified in org {org_id}")
            flash(f"{member.username} verified in organisation.", "success")
        else:
            flash("Member not found.", "danger")
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error verifying member {user_id} in org {org_id}: {e}")
        flash("Error verifying member.", "danger")

    return redirect(url_for("admin.org_members", org_id=org_id))


@admin_bp.route("/orgs/<int:org_id>/members/<int:user_id>/remove", methods=["POST"], endpoint="remove_member")
# @admin_required
def remove_member(org_id, user_id):
    """Remove member from organisation."""
    try:
        org = Organisation.query.get(org_id)
        member = User.query.get(user_id)
        if org and member and member in org.members:
            org.members.remove(member)
            db.session.commit()
            logger.info(f"User {member.username} removed from org {org.name}")
            flash(f"{member.username} removed from {org.name}.", "info")
        else:
            flash("Member or organisation not found.", "danger")
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error removing member {user_id} from org {org_id}: {e}")
        flash("Error removing member.", "danger")

    return redirect(url_for("admin.org_members", org_id=org_id))


# -----------------------------
# Audit logs
# -----------------------------
def log_org_action(org, action, actor):
    """Log organisation audit action"""
    try:
        entry = OrganisationAuditLog(
            organisation_id=org.id,
            change_type=action,
            changed_by=actor.id,
            changed_at=datetime.utcnow()
        )
        db.session.add(entry)
        db.session.commit()
        logger.info(f"Audit log created: {action} on {org.name} by {actor.username}")
    except Exception as e:
        logger.error(f"Error creating audit log: {e}")


# -----------------------------
# view_org_audit
# -----------------------------
@admin_bp.route("/orgs/<int:org_id>/audit", endpoint="view_org_audit")
# @admin_required
def view_org_audit(org_id):
    """View organisation audit logs."""
    try:
        org = Organisation.query.get_or_404(org_id)
        audit_logs = (
            OrganisationAuditLog.query
            .filter_by(organisation_id=org.id)
            .order_by(OrganisationAuditLog.changed_at.desc())
            .limit(50)  # show latest 50 entries
            .all()
        )
        return render_template(
            "admin/org_audit.html",
            org=org,
            audit_logs=audit_logs
        )
    except Exception as e:
        logger.error(f"Error loading audit logs for org {org_id}: {e}")
        flash("Error loading audit logs.", "danger")
        return redirect(url_for("admin.manage_orgs"))


# -----------------------------
# Content Management Dashboard
# -----------------------------
@admin_bp.route("/content", endpoint="content_dashboard")
# @admin_required
def content_dashboard():
    """Main content management dashboard"""
    try:
        categories = ManageableCategory.query.filter_by(is_active=True).all()
        recent_items = ManageableItem.query.order_by(ManageableItem.created_at.desc()).limit(10).all()
        pending_submissions = ContentSubmission.query.filter_by(status="pending").count()

        return render_template(
            "admin/content_dashboard.html",
            categories=categories,
            recent_items=recent_items,
            pending_submissions=pending_submissions
        )
    except Exception as e:
        logger.error(f"Error loading content dashboard: {e}")
        flash("Error loading content dashboard.", "danger")
        return redirect(url_for("admin.super_dashboard"))


# -----------------------------
# Manage Categories
# -----------------------------
@admin_bp.route("/content/categories", endpoint="manage_categories")
# @admin_required
def manage_categories():
    """Manage content categories"""
    try:
        categories = ManageableCategory.query.order_by(ManageableCategory.name).all()
        return render_template("admin/manage_categories.html", categories=categories)
    except Exception as e:
        logger.error(f"Error loading categories: {e}")
        flash("Error loading categories.", "danger")
        return redirect(url_for("admin.content_dashboard"))


@admin_bp.route("/content/categories/create", methods=["GET", "POST"], endpoint="create_category")
# @admin_required
def create_category():
    """Create a new content category"""
    if request.method == "POST":
        try:
            name = request.form.get("name")
            slug = request.form.get("slug")
            description = request.form.get("description")

            # Validation
            if not name or not slug:
                flash("Name and slug are required.", "danger")
                return render_template("admin/create_category.html")

            # Check for duplicate slug
            existing = ManageableCategory.query.filter_by(slug=slug).first()
            if existing:
                flash(f"Category with slug '{slug}' already exists.", "danger")
                return render_template("admin/create_category.html")

            # Basic fields config
            fields_config = {
                "fields": [
                    {"name": "description", "type": "textarea", "required": False},
                    {"name": "image_url", "type": "url", "required": False},
                    {"name": "contact_phone", "type": "tel", "required": False},
                    {"name": "contact_email", "type": "email", "required": False},
                ]
            }

            category = ManageableCategory(
                name=name,
                slug=slug,
                description=description,
                fields_config=fields_config,
                editable_by_admins=True,
                editable_by_org_admins="editable_by_org_admins" in request.form,
                editable_by_users="editable_by_users" in request.form
            )

            db.session.add(category)
            db.session.commit()

            logger.info(f"Category '{name}' created successfully")
            flash(f"Category '{name}' created successfully", "success")
            return redirect(url_for("admin.manage_categories"))

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error creating category: {e}")
            flash(f"Error creating category: {str(e)}", "danger")
            return render_template("admin/create_category.html")

    return render_template("admin/create_category.html")


# -----------------------------
# Manage Items by Category
# -----------------------------
@admin_bp.route("/content/<string:category_slug>", endpoint="manage_category_items")
# @admin_required
def manage_category_items(category_slug):
    """Manage items in a specific category"""
    try:
        category = ManageableCategory.query.filter_by(slug=category_slug).first_or_404()
        items = ManageableItem.query.filter_by(category_id=category.id).order_by(ManageableItem.name).all()

        return render_template(
            "admin/manage_items.html",
            category=category,
            items=items
        )
    except Exception as e:
        logger.error(f"Error loading category items for {category_slug}: {e}")
        flash("Error loading category items.", "danger")
        return redirect(url_for("admin.content_dashboard"))


@admin_bp.route("/content/<string:category_slug>/create", methods=["GET", "POST"], endpoint="create_item")
# @admin_required
def create_item(category_slug):
    """Create a new item in a category"""
    try:
        category = ManageableCategory.query.filter_by(slug=category_slug).first_or_404()

        if request.method == "POST":
            name = request.form.get("name")
            slug = request.form.get("slug", "").lower().replace(" ", "-")
            description = request.form.get("description")

            # Validation
            if not name:
                flash("Item name is required.", "danger")
                return render_template("admin/create_item.html", category=category)

            # Collect dynamic data based on category fields
            data = {}
            for field in category.fields_config.get("fields", []):
                field_name = field["name"]
                if field_name in request.form:
                    data[field_name] = request.form.get(field_name)

            item = ManageableItem(
                category_id=category.id,
                name=name,
                slug=slug,
                description=description,
                data=data,
                is_active="is_active" in request.form,
                is_featured="is_featured" in request.form,
                created_by=current_user.id if current_user.is_authenticated else None
            )

            db.session.add(item)
            db.session.commit()

            logger.info(f"Item '{name}' created in category '{category.name}'")
            flash(f"Item '{name}' created successfully", "success")
            return redirect(url_for("admin.manage_category_items", category_slug=category_slug))

        return render_template("admin/create_item.html", category=category)

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error creating item in category {category_slug}: {e}")
        flash("Error creating item.", "danger")
        return redirect(url_for("admin.manage_category_items", category_slug=category_slug))


# -----------------------------
# Pending Submissions
# -----------------------------
@admin_bp.route("/content/submissions", endpoint="manage_submissions")
# @admin_required
def manage_submissions():
    """Manage user submissions waiting for approval"""
    try:
        submissions = ContentSubmission.query.filter_by(status="pending").order_by(
            ContentSubmission.created_at.desc()).all()

        return render_template("admin/manage_submissions.html", submissions=submissions)
    except Exception as e:
        logger.error(f"Error loading submissions: {e}")
        flash("Error loading submissions.", "danger")
        return redirect(url_for("admin.content_dashboard"))


@admin_bp.route("/content/submissions/<int:submission_id>/approve", methods=["POST"], endpoint="approve_submission")
# @admin_required
def approve_submission(submission_id):
    """Approve a user submission"""
    try:
        submission = ContentSubmission.query.get_or_404(submission_id)

        # Create or update item
        if submission.item_id:
            item = ManageableItem.query.get(submission.item_id)
            if item:
                item.name = submission.name
                item.data = submission.data
                item.is_approved = True
        else:
            item = ManageableItem(
                category_id=submission.category_id,
                name=submission.name,
                slug=submission.name.lower().replace(" ", "-"),
                data=submission.data,
                created_by=submission.submitted_by,
                owned_by_org=submission.submitted_by_org,
                is_approved=True
            )
            db.session.add(item)
            db.session.flush()  # Get the ID
            submission.item_id = item.id

        # Update submission
        submission.status = "approved"
        submission.reviewed_by = current_user.id if current_user.is_authenticated else None
        submission.reviewed_at = datetime.utcnow()

        db.session.commit()

        logger.info(f"Submission '{submission.name}' approved")
        flash(f"Submission '{submission.name}' approved successfully", "success")

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error approving submission {submission_id}: {e}")
        flash("Error approving submission.", "danger")

    return redirect(url_for("admin.manage_submissions"))


@admin_bp.route("/content/submissions/<int:submission_id>/reject", methods=["POST"], endpoint="reject_submission")
# @admin_required
def reject_submission(submission_id):
    """Reject a user submission"""
    try:
        submission = ContentSubmission.query.get_or_404(submission_id)

        submission.status = "rejected"
        submission.reviewed_by = current_user.id if current_user.is_authenticated else None
        submission.reviewed_at = datetime.utcnow()
        submission.review_notes = request.form.get("rejection_reason", "")

        db.session.commit()

        logger.info(f"Submission '{submission.name}' rejected")
        flash(f"Submission '{submission.name}' rejected", "warning")

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error rejecting submission {submission_id}: {e}")
        flash("Error rejecting submission.", "danger")

    return redirect(url_for("admin.manage_submissions"))


# -----------------------------
# User Dashboard Routes (for regular users)
# -----------------------------
@admin_bp.route("/my-content", endpoint="user_content_dashboard")
@login_required
def user_content_dashboard():
    """User's personal content management dashboard"""
    try:
        # Get categories editable by users
        editable_categories = ManageableCategory.query.filter_by(
            is_active=True,
            editable_by_users=True
        ).all()

        # Get user's submissions
        submissions = ContentSubmission.query.filter_by(
            submitted_by=current_user.id
        ).order_by(ContentSubmission.created_at.desc()).all()

        # Get user's approved items
        items = ManageableItem.query.filter_by(
            created_by=current_user.id,
            is_approved=True
        ).order_by(ManageableItem.created_at.desc()).all()

        return render_template(
            "user/content_dashboard.html",
            categories=editable_categories,
            submissions=submissions,
            items=items
        )
    except Exception as e:
        logger.error(f"Error loading user content dashboard: {e}")
        flash("Error loading your content.", "danger")
        return redirect(url_for("index"))


@admin_bp.route("/my-content/submit/<string:category_slug>", methods=["GET", "POST"], endpoint="submit_content")
@login_required
def submit_content(category_slug):
    """Users submit new content for approval"""
    try:
        category = ManageableCategory.query.filter_by(
            slug=category_slug,
            is_active=True,
            editable_by_users=True
        ).first_or_404()

        if request.method == "POST":
            name = request.form.get("name")

            if not name:
                flash("Content name is required.", "danger")
                return render_template("user/submit_content.html", category=category)

            # Collect dynamic data
            data = {}
            for field in category.fields_config.get("fields", []):
                field_name = field["name"]
                if field_name in request.form:
                    data[field_name] = request.form.get(field_name)

            submission = ContentSubmission(
                category_id=category.id,
                name=name,
                data=data,
                submitted_by=current_user.id,
                submitted_by_org=current_user.default_org_id if hasattr(current_user, 'default_org_id') else None
            )

            db.session.add(submission)
            db.session.commit()

            logger.info(f"User {current_user.username} submitted content '{name}' for approval")
            flash(f"Your submission '{name}' has been sent for approval", "success")
            return redirect(url_for("admin.user_content_dashboard"))

        return render_template("user/submit_content.html", category=category)

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error submitting content: {e}")
        flash("Error submitting content.", "danger")
        return redirect(url_for("admin.user_content_dashboard"))


# -----------------------------
# Organization Dashboard (for org admins)
# -----------------------------
@admin_bp.route("/org-content/<int:org_id>", endpoint="org_content_dashboard")
@login_required
def org_content_dashboard(org_id):
    """Organization content management dashboard"""
    try:
        # Check if user has permission in this org
        if hasattr(current_user, 'has_org_permission'):
            if not current_user.has_org_permission(org_id, "manage_content"):
                flash("You don't have permission to manage content for this organization", "danger")
                return redirect(url_for("index"))
        else:
            # Fallback permission check
            flash("Permission check not available. Please contact administrator.", "warning")
            return redirect(url_for("index"))

        # Get categories editable by org admins
        editable_categories = ManageableCategory.query.filter_by(
            is_active=True,
            editable_by_org_admins=True
        ).all()

        # Get organization's items
        items = ManageableItem.query.filter_by(
            owned_by_org=org_id,
            is_approved=True
        ).order_by(ManageableItem.created_at.desc()).all()

        return render_template(
            "org/content_dashboard.html",
            org_id=org_id,
            categories=editable_categories,
            items=items
        )
    except Exception as e:
        logger.error(f"Error loading org content dashboard for org {org_id}: {e}")
        flash("Error loading organization content.", "danger")
        return redirect(url_for("index"))


#---------------------------------
# Admin Base
#_________________________________
@admin_bp.route('/dashboard')
def dashboard():
    return render_template('admin/dashboard.html')