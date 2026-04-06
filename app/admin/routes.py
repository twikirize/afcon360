# app/admin/routes.py
"""
Admin Routes for AFCON360 - Production Ready.
All decorators imported from app.auth.decorators.
"""

from datetime import datetime
import uuid
import logging
from flask import (
    render_template, redirect, url_for,
    current_app, request, flash, jsonify
)
from flask_login import login_required, current_user

from app.admin import admin_bp
from app.extensions import db
from app.auth.decorators import (
    admin_required,
    owner_only,
    require_permission,
    require_role
)

# Setup logging
logger = logging.getLogger(__name__)


# -----------------------------
# Helper Functions
# -----------------------------

def assign_role(user_id, role_name):
    """Helper function to assign a role to a user."""
    from app.identity.models import Role, UserRole
    try:
        role = Role.query.filter_by(name=role_name).first()
        if role:
            user_role = UserRole.query.filter_by(user_id=user_id, role_id=role.id).first()
            if not user_role:
                user_role = UserRole(user_id=user_id, role_id=role.id)
                db.session.add(user_role)
                db.session.commit()
                return True
        return False
    except Exception as e:
        logger.error(f"Error assigning role: {e}")
        db.session.rollback()
        return False


def remove_role(user_id, role_name):
    """Helper function to remove a role."""
    from app.identity.models import Role, UserRole
    try:
        role = Role.query.filter_by(name=role_name).first()
        if role:
            user_role = UserRole.query.filter_by(user_id=user_id, role_id=role.id).first()
            if user_role:
                db.session.delete(user_role)
                db.session.commit()
                return True
        return False
    except Exception as e:
        logger.error(f"Error removing role: {e}")
        db.session.rollback()
        return False


# -----------------------------
# Super Admin Dashboard
# -----------------------------
@admin_bp.route("/super", endpoint="super_dashboard")
@login_required
@admin_required
def super_dashboard():
    from app.identity.models.user import User
    from app.identity.models import OrganisationAuditLog
    from app.admin.models import ManageableCategory, ManageableItem

    try:
        total_users = User.query.count()
        verified_users = User.query.filter_by(is_verified=True).count()
        unverified_users = total_users - verified_users
        active_users = total_users - unverified_users

        audit_logs = OrganisationAuditLog.query.order_by(
            OrganisationAuditLog.changed_at.desc()
        ).limit(10).all()

        manageable_categories = ManageableCategory.query.filter_by(is_active=True).all()
        manageable_items = ManageableItem.query.filter_by(is_approved=True).all()

        return render_template(
            "super_admindashboard.html",
            total_users=total_users,
            verified_users=verified_users,
            unverified_users=unverified_users,
            active_users=active_users,
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
        db.session.rollback()
        logger.error(f"Error loading dashboard: {e}")
        flash("Error loading dashboard.", "danger")
        return redirect(url_for('index'))


# -----------------------------
# User Management
# -----------------------------
@admin_bp.route("/users", endpoint="manage_users")
@login_required
@admin_required
def manage_users():
    from app.identity.models.user import User
    try:
        users = User.query.order_by(User.created_at.desc()).all()
        return render_template("admin/manage_users.html", users=users)
    except Exception as e:
        logger.error(f"Error loading users: {e}")
        flash("Error loading users.", "danger")
        return redirect(url_for("admin.super_dashboard"))


@admin_bp.route("/users/<string:user_id>/verify", methods=["POST"], endpoint="verify_user")
@login_required
@admin_required
def verify_user(user_id):
    from app.identity.models.user import User
    from app.profile.models import UserProfile
    try:
        user = User.query.filter_by(user_id=user_id).first()
        if user:
            user.is_verified = True
            profile = UserProfile.query.filter_by(user_id=user.user_id).first()
            if profile:
                profile.mark_verified(reviewer="admin")
            db.session.commit()
            flash(f"User {user.username} verified successfully.", "success")
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error verifying user: {e}")
        flash(f"Error verifying user: {e}", "danger")
    return redirect(url_for("admin.manage_users"))


@admin_bp.route("/users/<string:user_id>/activate", methods=["POST"], endpoint="activate_user")
@login_required
@admin_required
def activate_user(user_id):
    from app.identity.models.user import User
    try:
        user = User.query.filter_by(user_id=user_id).first()
        if user:
            user.is_active = True
            db.session.commit()
            flash(f"User {user.username} activated successfully.", "success")
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error activating user: {e}")
        flash(f"Error activating user: {e}", "danger")
    return redirect(url_for("admin.manage_users"))


@admin_bp.route("/users/<string:user_id>/deactivate", methods=["POST"], endpoint="deactivate_user")
@login_required
@admin_required
def deactivate_user(user_id):
    from app.identity.models.user import User
    try:
        user = User.query.filter_by(user_id=user_id).first()
        if user:
            user.is_active = False
            db.session.commit()
            flash(f"User {user.username} deactivated.", "warning")
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error deactivating user: {e}")
        flash(f"Error deactivating user: {e}", "danger")
    return redirect(url_for("admin.manage_users"))


# -----------------------------
# Module Toggles (Owner Only - Most Sensitive)
# -----------------------------
@admin_bp.route("/toggle/<module>", methods=["POST"], endpoint="toggle_module")
@login_required
@owner_only  # Only platform owner can toggle modules
def toggle_module(module):
    def _redirect_after_toggle():
        return redirect(url_for("admin.super_dashboard"))

    try:
        flags = current_app.config.get("MODULE_FLAGS")
        if not isinstance(flags, dict) or module not in flags:
            flash(f"Module '{module}' not found.", "warning")
            return _redirect_after_toggle()

        old_value = bool(flags.get(module))
        new_value = not old_value
        reason = (request.form.get("reason", "") or "Toggled by admin").strip()
        confirm = (request.form.get("confirm", "") or "").strip().lower()

        # Emergency kill switch requires reason and confirmation
        if module == "wallet" and not new_value:
            if not reason or confirm != "yes":
                flash("Emergency action requires reason and confirmation.", "danger")
                return _redirect_after_toggle()

        flags[module] = new_value

        # Log the action
        try:
            from app.audit.comprehensive_audit import AuditService, AuditSeverity
            severity = AuditSeverity.CRITICAL if module == "wallet" and not new_value else AuditSeverity.WARNING
            AuditService.security(
                event_type=f"module_{module}_toggle",
                severity=severity,
                description=f"Module {module} {'disabled' if not new_value else 'enabled'} by {current_user.username}",
                user_id=current_user.id,
                ip_address=request.remote_addr,
                metadata={"module": module, "new_state": new_value, "reason": reason}
            )
        except Exception as e:
            logger.error(f"Failed to log module toggle: {e}")

        flash(f"Module '{module}' {'enabled' if new_value else 'disabled'} successfully.", "success")
    except Exception as e:
        logger.error(f"Toggle error: {e}")
        flash("Unexpected error occurred.", "danger")

    return _redirect_after_toggle()


@admin_bp.route("/toggle-wallet-feature/<feature>", methods=["POST"], endpoint="toggle_wallet_feature")
@login_required
@admin_required
def toggle_wallet_feature(feature):
    """Enable/disable a wallet feature."""
    try:
        wallet_flags = current_app.config.get("WALLET_FEATURES", {})
        if feature in wallet_flags:
            if isinstance(wallet_flags[feature], bool):
                old_value = wallet_flags[feature]
                wallet_flags[feature] = not wallet_flags[feature]
            elif isinstance(wallet_flags[feature], dict) and "enabled" in wallet_flags[feature]:
                old_value = wallet_flags[feature]["enabled"]
                wallet_flags[feature]["enabled"] = not wallet_flags[feature]["enabled"]
            else:
                flash(f"Feature '{feature}' configuration not supported.", "warning")
                return redirect(url_for("admin.super_dashboard"))

            logger.info(f"Wallet feature {feature} toggled: {old_value} → {wallet_flags[feature]}")
            flash(f"Wallet feature '{feature}' updated successfully.", "success")
        else:
            flash(f"Wallet feature '{feature}' not found.", "warning")
    except Exception as e:
        logger.error(f"Error toggling wallet feature {feature}: {e}")
        flash("Error updating wallet feature.", "danger")

    return redirect(url_for("admin.super_dashboard"))


@admin_bp.route("/update-withdraw-settings", methods=["POST"], endpoint="update_withdraw_settings")
@login_required
@admin_required
def update_withdraw_settings():
    """Update withdrawal settings."""
    try:
        wallet_features = current_app.config.get("WALLET_FEATURES", {})
        withdraw_settings = wallet_features.get("withdraw", {})

        if withdraw_settings:
            withdraw_settings["daily_limit"] = int(request.form.get("daily_limit", 1000))
            withdraw_settings["require_verification"] = "require_verification" in request.form
            withdraw_settings["require_2fa"] = "require_2fa" in request.form

            flash("Withdrawal settings updated successfully.", "success")
        else:
            flash("Withdrawal settings not found.", "warning")
    except ValueError:
        flash("Invalid daily limit value.", "danger")
    except Exception as e:
        logger.error(f"Error updating withdrawal settings: {e}")
        flash("Error updating withdrawal settings.", "danger")

    return redirect(request.referrer or url_for("admin.super_dashboard"))


@admin_bp.route("/update-transport-settings", methods=["POST"], endpoint="update_transport_settings")
@login_required
@admin_required
def update_transport_settings():
    """Update transport module settings."""
    try:
        transport_features = current_app.config.get("TRANSPORT_FEATURES", {})

        if "booking" in transport_features:
            transport_features["booking"]["max_advance_days"] = int(request.form.get("max_advance_days", 90))
            transport_features["booking"]["cancellation_hours"] = int(request.form.get("cancellation_hours", 24))
            transport_features["booking"]["require_deposit"] = "require_deposit" in request.form
            transport_features["booking"]["deposit_percentage"] = int(request.form.get("deposit_percentage", 20))

        if "driver_verification" in transport_features:
            transport_features["driver_verification"]["require_license"] = "require_license" in request.form
            transport_features["driver_verification"]["require_background_check"] = "require_background_check" in request.form
            transport_features["driver_verification"]["license_expiry_alert_days"] = int(request.form.get("license_expiry_alert_days", 30))

        if "vehicle_requirements" in transport_features:
            transport_features["vehicle_requirements"]["max_vehicle_age"] = int(request.form.get("max_vehicle_age", 10))
            transport_features["vehicle_requirements"]["require_insurance"] = "require_insurance" in request.form
            transport_features["vehicle_requirements"]["require_inspection"] = "require_inspection" in request.form

        flash("Transport settings updated successfully.", "success")
    except ValueError:
        flash("Invalid input value. Please check your entries.", "danger")
    except Exception as e:
        logger.error(f"Error updating transport settings: {e}")
        flash("Error updating transport settings.", "danger")

    return redirect(request.referrer or url_for("admin.super_dashboard"))


@admin_bp.route("/toggle-transport-feature/<feature>", methods=["POST"], endpoint="toggle_transport_feature")
@login_required
@admin_required
def toggle_transport_feature(feature):
    """Enable/disable a transport feature."""
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

    return redirect(request.referrer or url_for("admin.super_dashboard"))


# -----------------------------
# Organisations
# -----------------------------
@admin_bp.route("/orgs", endpoint="manage_orgs")
@login_required
@admin_required
def manage_orgs():
    from sqlalchemy import func, case
    from app.identity.models import Organisation
    try:
        counts = db.session.query(
            func.count(Organisation.id).label("total"),
            func.count(case((Organisation.is_active == True, 1))).label("active"),
            func.count(case((Organisation.verification_status == "pending", 1))).label("pending")
        ).one()
        orgs = Organisation.query.order_by(Organisation.created_at.desc()).all()
        return render_template("admin/manage_orgs.html", orgs=orgs, counts=counts)
    except Exception as e:
        logger.error(f"Org load error: {e}")
        flash("Error loading organisations.", "danger")
        return redirect(url_for("admin.super_dashboard"))


# -----------------------------
# Content Management
# -----------------------------
@admin_bp.route("/content", endpoint="content_dashboard")
@login_required
@admin_required
def content_dashboard():
    from app.admin.models import ManageableCategory, ManageableItem, ContentSubmission
    try:
        categories = ManageableCategory.query.filter_by(is_active=True).all()
        recent_items = ManageableItem.query.order_by(ManageableItem.created_at.desc()).limit(10).all()
        pending_submissions = ContentSubmission.query.filter_by(status="pending").count()
        return render_template("admin/content_dashboard.html", categories=categories, recent_items=recent_items, pending_submissions=pending_submissions)
    except Exception as e:
        logger.error(f"Content error: {e}")
        flash("Error loading content dashboard.", "danger")
        return redirect(url_for("admin.super_dashboard"))


@admin_bp.route("/submissions", endpoint="manage_submissions")
@login_required
@admin_required
def manage_submissions():
    from app.admin.models import ContentSubmission
    try:
        submissions = ContentSubmission.query.order_by(ContentSubmission.created_at.desc()).all()
        return render_template("admin/manage_submissions.html", submissions=submissions)
    except Exception as e:
        logger.error(f"Submissions error: {e}")
        flash("Error loading submissions.", "danger")
        return redirect(url_for("admin.super_dashboard"))


# -----------------------------
# Admin Dashboard Pages
# -----------------------------
@admin_bp.route('/dashboard')
@login_required
@admin_required
def dashboard():
    return render_template('admin/dashboard.html')


@admin_bp.route('/wallets')
@login_required
@admin_required
def wallet_list():
    return render_template('admin/wallets.html')


@admin_bp.route('/wallets/<int:user_id>')
@login_required
@admin_required
def wallet_detail(user_id):
    return render_template('admin/wallet_detail.html', user_id=user_id)


@admin_bp.route('/wallet-stats')
@login_required
@admin_required
def wallet_stats():
    return render_template('admin/wallet_stats.html')


@admin_bp.route('/wallet-control')
@login_required
@admin_required
def wallet_control():
    return render_template('admin/wallet_control.html')


# -----------------------------
# Error Handlers
# -----------------------------
@admin_bp.errorhandler(403)
def forbidden(e):
    flash("You don't have permission to access this page.", "danger")
    return redirect(url_for("admin.super_dashboard"))


@admin_bp.errorhandler(404)
def not_found(e):
    flash("Page not found.", "danger")
    return redirect(url_for("admin.super_dashboard"))