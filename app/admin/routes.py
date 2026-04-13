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
from app.profile.models import get_profile_by_user

# Setup logging
logger = logging.getLogger(__name__)


# -----------------------------
# Helper Functions
# -----------------------------

def assign_role(user_uuid, role_name):
    """Helper function to assign a role to a user using their UUID."""
    from app.identity.models import Role, UserRole, User
    try:
        user = User.query.filter_by(public_id=user_uuid).first()
        if not user:
            return False

        role = Role.query.filter_by(name=role_name).first()
        if role:
            user_role = UserRole.query.filter_by(user_id=user.id, role_id=role.id).first()
            if not user_role:
                user_role = UserRole(user_id=user.id, role_id=role.id)
                db.session.add(user_role)
                db.session.commit()
                return True
        return False
    except Exception as e:
        logger.error(f"Error assigning role: {e}")
        db.session.rollback()
        return False


def remove_role(user_uuid, role_name):
    """Helper function to remove a role using user UUID."""
    from app.identity.models import Role, UserRole, User
    try:
        user = User.query.filter_by(public_id=user_uuid).first()
        if not user:
            return False

        role = Role.query.filter_by(name=role_name).first()
        if role:
            user_role = UserRole.query.filter_by(user_id=user.id, role_id=role.id).first()
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
    try:
        user = User.query.filter_by(public_id=user_id).first()
        if user:
            user.is_verified = True
            profile = get_profile_by_user(user)
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
        user = User.query.filter_by(public_id=user_id).first()
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
        user = User.query.filter_by(public_id=user_id).first()
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
# Additional User Management Routes
# -----------------------------

@admin_bp.route("/users/<string:user_id>/suspend", methods=["POST"], endpoint="suspend_user")
@login_required
@admin_required
def suspend_user(user_id):
    """Suspend a user account (temporary deactivation with reason)."""
    from app.identity.models.user import User
    try:
        user = User.query.filter_by(public_id=user_id).first()
        if user:
            if user.user_id == current_user.user_id:
                flash("You cannot suspend your own account.", "danger")
                return redirect(url_for("admin.manage_users"))

            reason = request.form.get("reason", "No reason provided")
            user.is_active = False
            db.session.commit()
            flash(f"User {user.username} suspended successfully. Reason: {reason}", "warning")
            logger.info(f"User {user.username} suspended by {current_user.username}. Reason: {reason}")
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error suspending user: {e}")
        flash(f"Error suspending user: {str(e)}", "danger")
    return redirect(url_for("admin.manage_users"))


@admin_bp.route("/users/<string:user_id>/delete", methods=["POST"], endpoint="delete_user")
@login_required
@admin_required
def delete_user(user_id):
    """Permanently delete a user account."""
    from app.identity.models.user import User
    try:
        user = User.query.filter_by(public_id=user_id).first()
        if user:
            if user.user_id == current_user.user_id:
                flash("You cannot delete your own account.", "danger")
                return redirect(url_for("admin.manage_users"))

            username = user.username
            db.session.delete(user)
            db.session.commit()
            flash(f"User {username} deleted permanently.", "success")
            logger.info(f"User {username} deleted by {current_user.username}")
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error deleting user: {e}")
        flash(f"Error deleting user: {str(e)}", "danger")
    return redirect(url_for("admin.manage_users"))


@admin_bp.route("/users/<string:user_id>/resend-activation", methods=["POST"], endpoint="resend_activation")
@login_required
@admin_required
def resend_activation(user_id):
    """Resend activation email to user."""
    from app.identity.models.user import User
    try:
        user = User.query.filter_by(public_id=user_id).first()
        if user:
            if user.is_verified:
                flash(f"User {user.username} is already verified.", "warning")
            else:
                # Try to send verification email
                from app.auth.email import send_verification_email
                send_verification_email(user)
                flash(f"Activation email resent to {user.email}.", "success")
                logger.info(f"Activation email resent to {user.username} by {current_user.username}")
    except ImportError:
        flash("Email service not configured. Please contact administrator.", "warning")
        logger.warning(f"Cannot resend activation - email service not available for user {user_id}")
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error resending activation: {e}")
        flash(f"Error resending activation: {str(e)}", "danger")
    return redirect(url_for("admin.manage_users"))


@admin_bp.route("/users/<string:user_id>/promote", methods=["POST"], endpoint="promote_user")
@login_required
@admin_required
def promote_user(user_id):
    """Promote a user to a higher role."""
    from app.identity.models.user import User
    from app.identity.models import Role, UserRole

    try:
        user = User.query.filter_by(public_id=user_id).first()
        if not user:
            flash("User not found.", "danger")
            return redirect(url_for("admin.manage_users"))

        user_roles = [role.name for role in user.roles]

        if 'user' in user_roles and 'org_admin' not in user_roles:
            role = Role.query.filter_by(name='org_admin').first()
            if role:
                user_role = UserRole(user_id=user.id, role_id=role.id)
                db.session.add(user_role)
                db.session.commit()
                flash(f"User {user.username} promoted to Org Admin.", "success")
        elif 'org_admin' in user_roles and 'admin' not in user_roles:
            role = Role.query.filter_by(name='admin').first()
            if role:
                user_role = UserRole(user_id=user.id, role_id=role.id)
                db.session.add(user_role)
                db.session.commit()
                flash(f"User {user.username} promoted to Admin.", "success")
        else:
            flash(f"User {user.username} cannot be promoted further or already has highest role.", "warning")

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error promoting user: {e}")
        flash(f"Error promoting user: {str(e)}", "danger")
    return redirect(url_for("admin.manage_users"))


@admin_bp.route("/users/<string:user_id>/demote", methods=["POST"], endpoint="demote_user")
@login_required
@admin_required
def demote_user(user_id):
    """Demote a user from their current role."""
    from app.identity.models.user import User
    from app.identity.models import Role, UserRole

    try:
        user = User.query.filter_by(public_id=user_id).first()
        if not user:
            flash("User not found.", "danger")
            return redirect(url_for("admin.manage_users"))

        if user.user_id == current_user.user_id:
            flash("You cannot demote yourself.", "danger")
            return redirect(url_for("admin.manage_users"))

        user_roles = [role.name for role in user.roles]

        if 'admin' in user_roles:
            role = Role.query.filter_by(name='admin').first()
            if role:
                user_role = UserRole.query.filter_by(user_id=user.id, role_id=role.id).first()
                if user_role:
                    db.session.delete(user_role)
                    db.session.commit()
                    flash(f"User {user.username} demoted from Admin.", "warning")
        elif 'org_admin' in user_roles:
            role = Role.query.filter_by(name='org_admin').first()
            if role:
                user_role = UserRole.query.filter_by(user_id=user.id, role_id=role.id).first()
                if user_role:
                    db.session.delete(user_role)
                    db.session.commit()
                    flash(f"User {user.username} demoted from Org Admin.", "warning")
        else:
            flash(f"User {user.username} has no roles to demote from.", "warning")

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error demoting user: {e}")
        flash(f"Error demoting user: {str(e)}", "danger")
    return redirect(url_for("admin.manage_users"))


@admin_bp.route("/users/<string:user_id>/sign-in-as", methods=["POST"], endpoint="sign_in_as")
@login_required
@admin_required
def sign_in_as(user_id):
    """Allow admin to sign in as another user (impersonation)."""
    from app.identity.models.user import User
    from flask_login import login_user
    from flask import session

    try:
        user = User.query.filter_by(public_id=user_id).first()
        if not user:
            flash("User not found.", "danger")
            return redirect(url_for("admin.manage_users"))

        session['impersonated_by'] = current_user.id
        login_user(user)
        flash(f"You are now signed in as {user.username}.", "info")
        logger.warning(f"User {current_user.username} impersonated {user.username}")

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error signing in as user: {e}")
        flash(f"Error signing in as user: {str(e)}", "danger")
    return redirect(url_for("index"))


@admin_bp.route("/stop-impersonating", methods=["POST"], endpoint="stop_impersonating")
@login_required
def stop_impersonating():
    """Stop impersonation and return to original admin account."""
    from app.identity.models.user import User
    from flask_login import login_user
    from flask import session

    original_user_id = session.get('impersonated_by')
    if original_user_id:
        original_user = User.query.get(original_user_id)
        if original_user:
            login_user(original_user)
            session.pop('impersonated_by', None)
            flash("Returned to your admin account.", "info")
            logger.info(f"Stopped impersonation, returned to {original_user.username}")
    return redirect(url_for("admin.manage_users"))


@admin_bp.route("/users/bulk-verify", methods=["POST"], endpoint="bulk_verify_users")
@login_required
@admin_required
def bulk_verify_users():
    """Bulk verify multiple users."""
    from app.identity.models.user import User
    try:
        user_ids = request.form.getlist('user_ids')
        if not user_ids:
            flash("No users selected for bulk verification.", "warning")
            return redirect(url_for("admin.manage_users"))

        verified_count = 0
        for user_id in user_ids:
            user = User.query.filter_by(public_id=user_id).first()
            if user and not user.is_verified:
                user.is_verified = True
                verified_count += 1

        db.session.commit()
        flash(f"Successfully verified {verified_count} users.", "success")
        logger.info(f"Bulk verified {verified_count} users by {current_user.username}")

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error in bulk verification: {e}")
        flash(f"Error in bulk verification: {str(e)}", "danger")
    return redirect(url_for("admin.manage_users"))


@admin_bp.route("/users/bulk-deactivate", methods=["POST"], endpoint="bulk_deactivate_users")
@login_required
@admin_required
def bulk_deactivate_users():
    """Bulk deactivate multiple users."""
    from app.identity.models.user import User
    try:
        user_ids = request.form.getlist('user_ids')
        if not user_ids:
            flash("No users selected for bulk deactivation.", "warning")
            return redirect(url_for("admin.manage_users"))

        deactivated_count = 0
        for user_id in user_ids:
            user = User.query.filter_by(public_id=user_id).first()
            if user and user.is_active and user.user_id != current_user.user_id:
                user.is_active = False
                deactivated_count += 1

        db.session.commit()
        flash(f"Successfully deactivated {deactivated_count} users.", "warning")
        logger.info(f"Bulk deactivated {deactivated_count} users by {current_user.username}")

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error in bulk deactivation: {e}")
        flash(f"Error in bulk deactivation: {str(e)}", "danger")
    return redirect(url_for("admin.manage_users"))


@admin_bp.route("/users/<string:user_id>/view", endpoint="view_user")
@login_required
@admin_required
def view_user(user_id):
    """View detailed user information."""
    from app.identity.models.user import User
    user = User.query.filter_by(public_id=user_id).first_or_404()
    return render_template("admin/view_user.html", user=user)


@admin_bp.route("/users/<string:user_id>/roles/add/<string:role_name>", methods=["POST"], endpoint="add_user_role")
@login_required
@admin_required
def add_user_role(user_id, role_name):
    """Add a role to a user."""
    from app.identity.models.user import User
    from app.identity.models import Role, UserRole

    try:
        user = User.query.filter_by(public_id=user_id).first()
        if not user:
            flash("User not found.", "danger")
            return redirect(url_for("admin.manage_users"))

        role = Role.query.filter_by(name=role_name).first()
        if not role:
            flash(f"Role '{role_name}' not found.", "danger")
            return redirect(url_for("admin.view_user", user_id=user.user_id))

        existing = UserRole.query.filter_by(user_id=user.id, role_id=role.id).first()
        if existing:
            flash(f"User already has role '{role_name}'.", "warning")
        else:
            user_role = UserRole(user_id=user.id, role_id=role.id)
            db.session.add(user_role)
            db.session.commit()
            flash(f"Role '{role_name}' added to {user.username}.", "success")

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error adding role: {e}")
        flash(f"Error adding role: {str(e)}", "danger")

    return redirect(url_for("admin.view_user", user_id=user.user_id))


@admin_bp.route("/users/<string:user_id>/roles/remove/<string:role_name>", methods=["POST"],
                endpoint="remove_user_role")
@login_required
@admin_required
def remove_user_role(user_id, role_name):
    """Remove a role from a user."""
    from app.identity.models.user import User
    from app.identity.models import Role, UserRole

    try:
        user = User.query.filter_by(public_id=user_id).first()
        if not user:
            flash("User not found.", "danger")
            return redirect(url_for("admin.manage_users"))

        if role_name == 'admin' and user.user_id == current_user.user_id:
            flash("You cannot remove the admin role from yourself.", "danger")
            return redirect(url_for("admin.view_user", user_id=user.user_id))

        role = Role.query.filter_by(name=role_name).first()
        if role:
            user_role = UserRole.query.filter_by(user_id=user.id, role_id=role.id).first()
            if user_role:
                db.session.delete(user_role)
                db.session.commit()
                flash(f"Role '{role_name}' removed from {user.username}.", "success")
            else:
                flash(f"User does not have role '{role_name}'.", "warning")

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error removing role: {e}")
        flash(f"Error removing role: {str(e)}", "danger")

    return redirect(url_for("admin.view_user", user_id=user.user_id))


# -----------------------------
# Module Toggles (Owner Only - Most Sensitive)
# -----------------------------
@admin_bp.route("/toggle/<module>", methods=["POST"], endpoint="toggle_module")
@login_required
@owner_only
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

        if module == "wallet" and not new_value:
            if not reason or confirm != "yes":
                flash("Emergency action requires reason and confirmation.", "danger")
                return _redirect_after_toggle()

        flags[module] = new_value

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
            transport_features["driver_verification"][
                "require_background_check"] = "require_background_check" in request.form
            transport_features["driver_verification"]["license_expiry_alert_days"] = int(
                request.form.get("license_expiry_alert_days", 30))

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
        return render_template("admin/content_dashboard.html", categories=categories, recent_items=recent_items,
                               pending_submissions=pending_submissions)
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


@admin_bp.route('/wallets/<string:user_id>')
@login_required
@admin_required
def wallet_detail(user_id):
    from app.identity.models.user import User
    user = User.query.filter_by(public_id=user_id).first_or_404()
    return render_template('admin/wallet_detail.html', user=user)


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


@admin_bp.route("/users/<string:user_id>/update", methods=["GET", "POST"], endpoint="update_user")
@login_required
@admin_required
def update_user(user_id):
    """Update user information."""
    from app.identity.models.user import User
    from flask import render_template_string

    user = User.query.filter_by(public_id=user_id).first_or_404()

    if request.method == "POST":
        try:
            user.username = request.form.get('username', user.username)
            user.email = request.form.get('email', user.email)
            user.phone = request.form.get('phone', user.phone)
            db.session.commit()
            flash(f"User {user.username} updated successfully.", "success")
            return redirect(url_for("admin.view_user", user_id=user.user_id))
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error updating user: {e}")
            flash(f"Error updating user: {str(e)}", "danger")

    # Simple inline form for update
    form_html = '''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Update User - {{ user.username }}</title>
        <style>
            body { font-family: Arial, sans-serif; margin: 40px; }
            .form-group { margin-bottom: 15px; }
            label { display: inline-block; width: 100px; font-weight: bold; }
            input[type="text"], input[type="email"] { width: 250px; padding: 5px; }
            button { padding: 8px 15px; background: #007bff; color: white; border: none; cursor: pointer; }
            .cancel { background: #6c757d; margin-left: 10px; }
        </style>
    </head>
    <body>
        <h1>Update User: {{ user.username }}</h1>
        <form method="post">
            <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
            <div class="form-group">
                <label>Username:</label>
                <input type="text" name="username" value="{{ user.username }}" required>
            </div>
            <div class="form-group">
                <label>Email:</label>
                <input type="email" name="email" value="{{ user.email or '' }}">
            </div>
            <div class="form-group">
                <label>Phone:</label>
                <input type="text" name="phone" value="{{ user.phone or '' }}">
            </div>
            <div class="form-group">
                <button type="submit">Update User</button>
                <a href="{{ url_for('admin.view_user', user_id=user.user_id) }}" class="cancel" style="background:#6c757d; padding:8px 15px; color:white; text-decoration:none; margin-left:10px;">Cancel</a>
            </div>
        </form>
    </body>
    </html>
    '''
    from flask import render_template_string
    return render_template_string(form_html, user=user, csrf_token=request.form.get('csrf_token', ''))

# -----------------------------
# Compliance & Auditor Routes
# -----------------------------
@admin_bp.route("/compliance/dashboard", endpoint="compliance_dashboard")
@login_required
@require_role('compliance_officer')
def compliance_dashboard():
    """Compliance officer dashboard for KYC reviews and AML alerts."""
    from app.audit.comprehensive_audit import FinancialAuditLog
    from app.identity.individuals.individual_verification import IndividualVerification
    from app.identity.models.user import User
    from app.audit.forensic_audit import ForensicAuditService

    # Get pending KYC verifications
    pending_verifications = IndividualVerification.query.filter_by(
        status='pending'
    ).order_by(IndividualVerification.requested_at.desc()).limit(50).all()

    # Get user public_ids for display
    user_ids = [v.user_id for v in pending_verifications]
    users = User.query.filter(User.id.in_(user_ids)).all() if user_ids else []
    user_map = {user.id: user.public_id for user in users}

    # Get high-risk transactions (AML alerts)
    # Assuming FinancialAuditLog has a 'risk_level' field or we can filter by amount
    high_risk_transactions = FinancialAuditLog.query.filter(
        FinancialAuditLog.amount >= 5000000  # UGX 5M threshold
    ).order_by(FinancialAuditLog.created_at.desc()).limit(50).all()

    # Get public_ids for transaction users
    transaction_user_ids = [t.user_id for t in high_risk_transactions if t.user_id]
    transaction_users = User.query.filter(User.id.in_(transaction_user_ids)).all() if transaction_user_ids else []
    transaction_user_map = {user.id: user.public_id for user in transaction_users}

    return render_template(
        "admin/compliance/dashboard.html",
        pending_verifications=pending_verifications,
        high_risk_transactions=high_risk_transactions,
        user_map=user_map,
        transaction_user_map=transaction_user_map
    )

@admin_bp.route("/compliance/action/<string:verification_id>", methods=["POST"], endpoint="compliance_action")
@login_required
@require_role('compliance_officer')
def compliance_action(verification_id):
    """Handle compliance actions (Approve, Reject, Request More Info)."""
    from app.identity.individuals.individual_verification import IndividualVerification
    from app.audit.forensic_audit import ForensicAuditService

    action = request.form.get('action')
    notes = request.form.get('notes', '')

    verification = IndividualVerification.query.filter_by(id=verification_id).first_or_404()

    # Log the completion to ForensicAuditService
    audit_id = f"kyc_review_{verification_id}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"

    if action == 'approve':
        verification.status = 'verified'
        status = 'approved'
        flash(f"KYC verification {verification_id} approved.", "success")
    elif action == 'reject':
        verification.status = 'rejected'
        status = 'rejected'
        flash(f"KYC verification {verification_id} rejected.", "warning")
    elif action == 'request_info':
        verification.status = 'pending'
        status = 'info_requested'
        flash(f"More information requested for verification {verification_id}.", "info")
    else:
        flash("Invalid action.", "danger")
        return redirect(url_for('admin.compliance_dashboard'))

    # Update verification
    db.session.commit()

    # Log to forensic audit
    ForensicAuditService.log_completion(
        audit_id=audit_id,
        status=status,
        reviewed_by=current_user.id,
        review_notes=notes,
        result_details={
            'verification_id': verification_id,
            'user_id': verification.user_id,
            'action': action,
            'notes': notes
        }
    )

    return redirect(url_for('admin.compliance_dashboard'))

@admin_bp.route("/auditor/dashboard", endpoint="auditor_dashboard")
@login_required
@require_role('auditor')
def auditor_dashboard():
    """Auditor dashboard for read-only access to all logs."""
    from app.audit.comprehensive_audit import FinancialAuditLog, SecurityEventLog, DataAccessLog
    from app.identity.models.user import User

    # Get filter parameters
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    user_id = request.args.get('user_id')
    action_type = request.args.get('action_type')

    # Build queries with filters
    financial_query = FinancialAuditLog.query
    security_query = SecurityEventLog.query
    data_access_query = DataAccessLog.query

    if start_date:
        try:
            start_dt = datetime.strptime(start_date, '%Y-%m-%d')
            financial_query = financial_query.filter(FinancialAuditLog.created_at >= start_dt)
            security_query = security_query.filter(SecurityEventLog.created_at >= start_dt)
            data_access_query = data_access_query.filter(DataAccessLog.created_at >= start_dt)
        except ValueError:
            pass

    if end_date:
        try:
            end_dt = datetime.strptime(end_date, '%Y-%m-%d')
            financial_query = financial_query.filter(FinancialAuditLog.created_at <= end_dt)
            security_query = security_query.filter(SecurityEventLog.created_at <= end_dt)
            data_access_query = data_access_query.filter(DataAccessLog.created_at <= end_dt)
        except ValueError:
            pass

    if user_id:
        financial_query = financial_query.filter(FinancialAuditLog.user_id == user_id)
        security_query = security_query.filter(SecurityEventLog.user_id == user_id)
        data_access_query = data_access_query.filter(DataAccessLog.user_id == user_id)

    # Apply limits for performance
    financial_logs = financial_query.order_by(FinancialAuditLog.created_at.desc()).limit(100).all()
    security_logs = security_query.order_by(SecurityEventLog.created_at.desc()).limit(100).all()
    data_access_logs = data_access_query.order_by(DataAccessLog.created_at.desc()).limit(100).all()

    # Get user public_ids for display
    all_user_ids = set()
    for log in financial_logs:
        if log.user_id:
            all_user_ids.add(log.user_id)
    for log in security_logs:
        if log.user_id:
            all_user_ids.add(log.user_id)
    for log in data_access_logs:
        if log.user_id:
            all_user_ids.add(log.user_id)

    users = User.query.filter(User.id.in_(list(all_user_ids))).all() if all_user_ids else []
    user_map = {user.id: user.public_id for user in users}

    return render_template(
        "auditor/dashboard.html",
        financial_logs=financial_logs,
        security_logs=security_logs,
        data_access_logs=data_access_logs,
        user_map=user_map,
        start_date=start_date,
        end_date=end_date,
        user_id=user_id,
        action_type=action_type
    )

@admin_bp.route("/auditor/export/<log_type>", endpoint="auditor_export")
@login_required
@require_role('auditor')
def auditor_export(log_type):
    """Export logs in CSV format."""
    from app.audit.comprehensive_audit import FinancialAuditLog, SecurityEventLog, DataAccessLog
    import csv
    from io import StringIO

    # Get filter parameters
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    user_id = request.args.get('user_id')

    # Determine which log type to export
    if log_type == 'financial':
        query = FinancialAuditLog.query
        model = FinancialAuditLog
        filename = 'financial_audit_logs.csv'
    elif log_type == 'security':
        query = SecurityEventLog.query
        model = SecurityEventLog
        filename = 'security_event_logs.csv'
    elif log_type == 'data_access':
        query = DataAccessLog.query
        model = DataAccessLog
        filename = 'data_access_logs.csv'
    else:
        flash("Invalid log type.", "danger")
        return redirect(url_for('admin.auditor_dashboard'))

    # Apply filters
    if start_date:
        try:
            start_dt = datetime.strptime(start_date, '%Y-%m-%d')
            query = query.filter(model.created_at >= start_dt)
        except ValueError:
            pass

    if end_date:
        try:
            end_dt = datetime.strptime(end_date, '%Y-%m-%d')
            query = query.filter(model.created_at <= end_dt)
        except ValueError:
            pass

    if user_id:
        query = query.filter(model.user_id == user_id)

    logs = query.order_by(model.created_at.desc()).limit(1000).all()

    # Create CSV
    output = StringIO()
    writer = csv.writer(output)

    # Write header based on model columns
    if log_type == 'financial':
        writer.writerow(['ID', 'Transaction ID', 'User ID', 'Amount', 'Currency', 'Type', 'Status', 'Created At'])
        for log in logs:
            writer.writerow([
                log.id, log.transaction_id, log.user_id, log.amount,
                log.currency, log.transaction_type, log.status, log.created_at
            ])
    elif log_type == 'security':
        writer.writerow(['ID', 'Event Type', 'Severity', 'Description', 'User ID', 'IP Address', 'Created At'])
        for log in logs:
            writer.writerow([
                log.id, log.event_type, log.severity, log.description,
                log.user_id, log.ip_address, log.created_at
            ])
    elif log_type == 'data_access':
        writer.writerow(['ID', 'Entity Type', 'Entity ID', 'Operation', 'User ID', 'IP Address', 'Created At'])
        for log in logs:
            writer.writerow([
                log.id, log.entity_type, log.entity_id, log.operation,
                log.user_id, log.ip_address, log.created_at
            ])

    # Prepare response
    from flask import Response
    output.seek(0)
    return Response(
        output,
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment;filename={filename}"}
    )

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
