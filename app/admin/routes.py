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
from app.admin.models import ContentFlag

# Import event-related modules
try:
    from app.events.services import EventService
    from app.events.models import Event
    EVENTS_MODULE_AVAILABLE = True
except ImportError:
    EVENTS_MODULE_AVAILABLE = False
    EventService = None
    Event = None

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


def get_user_roles_map(users):
    """Helper to get role names for a list of users."""
    roles_map = {}
    for user in users:
        role_names = []
        if hasattr(user, 'roles'):
            for user_role in user.roles:
                if user_role.role and hasattr(user_role.role, 'name'):
                    role_names.append(user_role.role.name)
        roles_map[user.id] = role_names
    return roles_map


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

        # Event statistics
        total_events = 0
        active_events = 0
        pending_events = 0
        total_registrations = 0
        pending_events_list = []

        if EVENTS_MODULE_AVAILABLE and EventService and Event:
            try:
                event_stats = EventService.get_admin_dashboard_data()
                total_events = event_stats.get('total_events', 0)
                active_events = event_stats.get('active_events', 0)
                pending_events = event_stats.get('pending_events', 0)
                total_registrations = event_stats.get('total_registrations', 0)

                # Get pending events list
                pending_events_list = Event.query.filter_by(
                    status='pending',
                    is_deleted=False
                ).order_by(Event.created_at.desc()).limit(10).all()
            except Exception as e:
                logger.warning(f"Could not load event statistics: {e}")

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
            # Event statistics
            total_events=total_events,
            active_events=active_events,
            pending_events=pending_events,
            total_registrations=total_registrations,
            pending_events_list=pending_events_list,
        )
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error loading dashboard: {e}")
        flash("Error loading dashboard.", "danger")
        return redirect(url_for('index'))


# -----------------------------
# User Management
# -----------------------------
@admin_bp.route("/users", endpoint="manage_users", methods=['GET'])
@login_required
@admin_required
def manage_users():
    from app.identity.models.user import User
    try:
        users = User.query.order_by(User.created_at.desc()).all()
        user_roles_map = get_user_roles_map(users)
        return render_template("admin/manage_users.html", users=users, user_roles_map=user_roles_map)
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
    """Promote a user to the next higher role in hierarchy."""
    from app.identity.models.user import User
    from app.identity.models import Role, UserRole

    # Full role hierarchy from seed_roles.py
    ROLE_HIERARCHY = [
        "owner", "super_admin", "admin", "auditor", "compliance_officer",
        "moderator", "support", "event_manager", "transport_admin",
        "wallet_admin", "accommodation_admin", "tourism_admin", "fan"
    ]

    try:
        user = User.query.filter_by(public_id=user_id).first()
        if not user:
            flash("User not found.", "danger")
            return redirect(url_for("admin.manage_users"))

        current_role_names = []
        for user_role in user.roles:
            if user_role.role and hasattr(user_role.role, 'name'):
                current_role_names.append(user_role.role.name)

        current_index = -1
        current_role = None
        for i, role_name in enumerate(ROLE_HIERARCHY):
            if role_name in current_role_names:
                current_index = i
                current_role = role_name
                break

        if current_index == -1:
            current_index = len(ROLE_HIERARCHY) - 1
            current_role = ROLE_HIERARCHY[-1]

        if current_index > 0:
            next_role_name = ROLE_HIERARCHY[current_index - 1]

            if next_role_name == "owner":
                flash("Cannot promote to Owner. Only the platform owner can assign owner role.", "warning")
                return redirect(url_for("admin.manage_users"))

            role = Role.query.filter_by(name=next_role_name).first()
            if role:
                existing = UserRole.query.filter_by(user_id=user.id, role_id=role.id).first()
                if not existing:
                    user_role = UserRole(user_id=user.id, role_id=role.id)
                    db.session.add(user_role)
                    db.session.commit()
                    flash(f"User {user.username} promoted to {next_role_name.replace('_', ' ').title()}.", "success")
                else:
                    flash(f"User {user.username} already has role {next_role_name}.", "info")
            else:
                flash(f"Role '{next_role_name}' not found.", "danger")
        else:
            flash(f"User {user.username} already has the highest role ({current_role}).", "warning")

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error promoting user: {e}")
        flash(f"Error promoting user: {str(e)}", "danger")

    return redirect(url_for("admin.manage_users"))


@admin_bp.route("/users/<string:user_id>/demote", methods=["POST"], endpoint="demote_user")
@login_required
@admin_required
def demote_user(user_id):
    """Demote a user to the next lower role in hierarchy."""
    from app.identity.models.user import User
    from app.identity.models import Role, UserRole

    ROLE_HIERARCHY = [
        "owner", "super_admin", "admin", "auditor", "compliance_officer",
        "moderator", "support", "event_manager", "transport_admin",
        "wallet_admin", "accommodation_admin", "tourism_admin", "fan"
    ]

    try:
        user = User.query.filter_by(public_id=user_id).first()
        if not user:
            flash("User not found.", "danger")
            return redirect(url_for("admin.manage_users"))

        if user.user_id == current_user.user_id:
            flash("You cannot demote yourself.", "danger")
            return redirect(url_for("admin.manage_users"))

        current_role_names = []
        for user_role in user.roles:
            if user_role.role and hasattr(user_role.role, 'name'):
                current_role_names.append(user_role.role.name)

        current_index = -1
        current_role = None
        for i, role_name in enumerate(ROLE_HIERARCHY):
            if role_name in current_role_names and role_name != "owner":
                current_index = i
                current_role = role_name
                break

        if current_index == -1:
            flash(f"User {user.username} has no demotable roles.", "warning")
            return redirect(url_for("admin.manage_users"))

        if current_index < len(ROLE_HIERARCHY) - 1:
            next_role_name = ROLE_HIERARCHY[current_index + 1]

            role = Role.query.filter_by(name=next_role_name).first()
            if role:
                current_role_obj = Role.query.filter_by(name=current_role).first()
                if current_role_obj:
                    user_role = UserRole.query.filter_by(
                        user_id=user.id, role_id=current_role_obj.id
                    ).first()
                    if user_role:
                        db.session.delete(user_role)

                existing = UserRole.query.filter_by(user_id=user.id, role_id=role.id).first()
                if not existing:
                    new_role = UserRole(user_id=user.id, role_id=role.id)
                    db.session.add(new_role)

                db.session.commit()
                flash(f"User {user.username} demoted to {next_role_name.replace('_', ' ').title()}.", "warning")
            else:
                flash(f"Role '{next_role_name}' not found.", "danger")
        else:
            flash(f"User {user.username} is already at the lowest role level.", "info")

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


@admin_bp.route("/users/bulk-activate", methods=["POST"], endpoint="bulk_activate_users")
@login_required
@admin_required
def bulk_activate_users():
    """Bulk activate multiple users."""
    from app.identity.models.user import User
    try:
        user_ids = request.form.getlist('user_ids')
        if not user_ids:
            flash("No users selected for bulk activation.", "warning")
            return redirect(url_for("admin.manage_users"))

        activated_count = 0
        for user_id in user_ids:
            user = User.query.filter_by(public_id=user_id).first()
            if user and not user.is_active:
                user.is_active = True
                activated_count += 1

        db.session.commit()
        flash(f"Successfully activated {activated_count} users.", "success")
        logger.info(f"Bulk activated {activated_count} users by {current_user.username}")

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error in bulk activation: {e}")
        flash(f"Error in bulk activation: {str(e)}", "danger")
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
    from flask import abort
    from app.auth.kyc_compliance import calculate_kyc_tier

    print("=" * 60)
    print(f"DEBUG view_user: user_id parameter = '{user_id}'")
    print(f"DEBUG view_user: user_id length = {len(user_id) if user_id else 0}")
    print("=" * 60)

    # Check if user_id is empty
    if not user_id or user_id.strip() == "":
        print("ERROR: Empty user_id provided")
        abort(404)

    # Try to find user by public_id
    user = User.query.filter_by(public_id=user_id).first()
    if not user:
        print(f"ERROR: No user found with public_id='{user_id}'")
        # Try to find by id as fallback
        try:
            user_id_int = int(user_id)
            user = User.query.get(user_id_int)
            if user:
                print(f"DEBUG: Found user by integer id {user_id_int}")
        except ValueError:
            pass

    if not user:
        abort(404)

    print(f"DEBUG view_user: Found user - id={user.id}, public_id={user.public_id}, username={user.username}")

    # Debug: check if user has roles attribute
    print(f"DEBUG view_user: hasattr(user, 'roles') = {hasattr(user, 'roles')}")
    if hasattr(user, 'roles'):
        try:
            print(f"DEBUG view_user: user.roles = {user.roles}")
            print(f"DEBUG view_user: type(user.roles) = {type(user.roles)}")
            print(f"DEBUG view_user: len(list(user.roles)) = {len(list(user.roles)) if user.roles else 0}")
        except Exception as e:
            print(f"DEBUG view_user: Error accessing user.roles: {e}")

    # Get user roles using the helper function
    user_roles_map = get_user_roles_map([user])
    print(f"DEBUG view_user: user_roles_map = {user_roles_map}")
    user_roles = user_roles_map.get(user.id, [])
    print(f"DEBUG view_user: user_roles = {user_roles}")

    # Ensure user_roles is always a list
    if user_roles is None:
        user_roles = []

    # Get KYC tier information
    try:
        kyc_info = calculate_kyc_tier(user.id)
        print(f"DEBUG view_user: kyc_info = {kyc_info}")
    except Exception as e:
        print(f"DEBUG view_user: Error calculating KYC tier: {e}")
        kyc_info = None

    return render_template("admin/view_user.html",
                          user=user,
                          user_roles=user_roles,
                          kyc_info=kyc_info)

@admin_bp.route("/users/username/<string:username>/view", endpoint="view_user_by_username")
@login_required
@admin_required
def view_user_by_username(username):
    """View user by username instead of UUID."""
    from app.identity.models.user import User
    from app.profile.models import get_profile_by_user
    from app.auth.kyc_compliance import calculate_kyc_tier

    user = User.query.filter_by(username=username).first_or_404()
    profile = get_profile_by_user(user)
    user_roles = get_user_roles_map([user]).get(user.id, [])

    # Get KYC tier information
    try:
        kyc_info = calculate_kyc_tier(user.id)
    except Exception as e:
        print(f"Error calculating KYC tier for user {username}: {e}")
        kyc_info = None

    return render_template("admin/view_user.html",
                          user=user,
                          profile=profile,
                          user_roles=user_roles,
                          kyc_info=kyc_info)

@admin_bp.route("/users/username/<string:username>/update", methods=["GET", "POST"], endpoint="update_user_by_username")
@login_required
@admin_required
def update_user_by_username(username):
    """Update user by username instead of UUID."""
    from app.identity.models.user import User
    user = User.query.filter_by(username=username).first_or_404()

    if request.method == "POST":
        # Change reason is optional for account updates (default reason provided)
        change_reason = request.form.get('change_reason', '').strip()
        if not change_reason:
            change_reason = f"Account update by {current_user.username}"

        # Process changes...
        if 'username' in request.form:
            new_username = request.form.get('username', user.username)
            if new_username != user.username:
                user.username = new_username

        if 'email' in request.form:
            new_email = request.form.get('email', user.email)
            if new_email != user.email:
                user.email = new_email

        if 'phone' in request.form:
            new_phone = request.form.get('phone', user.phone)
            if new_phone != user.phone:
                user.phone = new_phone

        db.session.commit()

        # Audit log the change
        from app.audit.comprehensive_audit import AuditService
        AuditService.data_change(
            entity_type="user",
            entity_id=user.public_id,
            operation="update",
            changed_by=current_user.id,
            ip_address=request.remote_addr,
            extra_data={"reason": change_reason}
        )

        flash(f"User {user.username} updated successfully.", "success")
        return redirect(url_for('admin.view_user_by_username', username=user.username))

    return render_template("admin/update_user.html", user=user)

@admin_bp.route("/users/username/<string:username>/profile", methods=["GET", "POST"], endpoint="update_profile_by_username")
@login_required
@admin_required
def update_profile_by_username(username):
    """Update user profile by username instead of UUID."""
    from app.identity.models.user import User
    from app.profile.models import get_profile_by_user, UserProfile
    from app.auth.kyc_compliance import calculate_kyc_tier

    user = User.query.filter_by(username=username).first_or_404()
    profile = get_profile_by_user(user)
    if not profile:
        profile = UserProfile(user_id=user.id)
        db.session.add(profile)
        db.session.commit()

    kyc_info = calculate_kyc_tier(user.id)

    if request.method == "POST":
        change_reason = request.form.get('change_reason', '').strip()
        if not change_reason:
            flash("Reason for change is required.", "danger")
            return render_template("admin/update_profile.html", user=user, profile=profile, kyc_info=kyc_info)

        changes_made = {}

        # Update profile fields
        new_address = request.form.get('address', '')
        if new_address != (profile.address or ''):
            profile.address = new_address
            changes_made['address'] = {'old': profile.address, 'new': new_address}

        if hasattr(profile, 'city'):
            new_city = request.form.get('city', '')
            if new_city != (profile.city or ''):
                profile.city = new_city
                changes_made['city'] = {'old': profile.city, 'new': new_city}

        if hasattr(profile, 'country'):
            new_country = request.form.get('country', '')
            if new_country != (profile.country or ''):
                profile.country = new_country
                changes_made['country'] = {'old': profile.country, 'new': new_country}

        # Handle phone number update with uniqueness validation
        new_phone = request.form.get('phone', '').strip()

        if new_phone:
            # Check if phone is already used by ANOTHER user (different ID)
            from app.identity.models.user import User
            existing_user = User.query.filter(User.phone == new_phone, User.id != user.id).first()
            if existing_user:
                flash(f"Phone number {new_phone} is already registered to another user: {existing_user.username}. Please use a different phone number.", "danger")
                return render_template("admin/update_profile.html", user=user, profile=profile, kyc_info=kyc_info)

            # Only update if phone number changed
            if new_phone != (user.phone or ''):
                user.phone = new_phone
                changes_made['phone'] = {'old': user.phone, 'new': new_phone}

        if changes_made:
            db.session.commit()

            # Log the changes to audit service
            try:
                from app.audit.comprehensive_audit import AuditService
                AuditService.data_change(
                    entity_type="user_profile",
                    entity_id=user.public_id,
                    operation="update",
                    old_value={k: v['old'] for k, v in changes_made.items()},
                    new_value={k: v['new'] for k, v in changes_made.items()},
                    changed_by=current_user.id,
                    ip_address=request.remote_addr,
                    user_agent=request.user_agent.string if request.user_agent else None,
                    extra_data={"reason": change_reason}
                )
            except Exception as e:
                logger.error(f"Failed to log profile update audit: {e}")

            flash(f"Profile updated successfully. Changes logged for audit.", "success")
        else:
            flash("No changes were made.", "info")

        return redirect(url_for('admin.view_user_by_username', username=user.username))

    return render_template("admin/update_profile.html", user=user, profile=profile, kyc_info=kyc_info)


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
            return redirect(url_for("admin.view_user", user_id=user.public_id))

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

    return redirect(url_for("admin.view_user", user_id=user.public_id))


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
            return redirect(url_for("admin.view_user", user_id=user.public_id))

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

    return redirect(url_for("admin.view_user", user_id=user.public_id))


# -----------------------------
# Email Verification Toggle
# -----------------------------
@admin_bp.route("/toggle-email-verification", methods=["POST"], endpoint="toggle_email_verification")
@login_required
@admin_required
def toggle_email_verification():
    """Toggle email verification requirement."""
    try:
        # Get current value, default to True if not set
        current_value = current_app.config.get('REQUIRE_EMAIL_VERIFICATION', True)
        new_value = not current_value

        # Update the configuration
        current_app.config['REQUIRE_EMAIL_VERIFICATION'] = new_value

        # Audit the change
        try:
            from app.audit.comprehensive_audit import AuditService, AuditSeverity
            AuditService.security(
                event_type="email_verification_toggle",
                severity=AuditSeverity.WARNING,
                description=f"Email verification requirement {'enabled' if new_value else 'disabled'} by {current_user.username}",
                user_id=current_user.id,
                ip_address=request.remote_addr,
                metadata={
                    "old_value": current_value,
                    "new_value": new_value,
                    "action": "toggle_email_verification"
                }
            )
        except Exception as e:
            logger.error(f"Failed to log email verification toggle: {e}")

        flash(f"Email verification requirement {'enabled' if new_value else 'disabled'} successfully.", "success")
    except Exception as e:
        logger.error(f"Error toggling email verification: {e}")
        flash("Error toggling email verification requirement.", "danger")

    return redirect(url_for("admin.super_dashboard"))

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
# Placeholder routes for template compatibility
# -----------------------------
@admin_bp.route("/events/dashboard", endpoint="events__admin_dashboard")
@login_required
@admin_required
def events_placeholder_dashboard():
    """Placeholder to prevent template errors."""
    flash("Events module is not yet implemented. This is a placeholder.", "info")
    return redirect(url_for("admin.super_dashboard"))

@admin_bp.route("/api/events/admin_stats", endpoint="events__api_admin_stats")
@login_required
@admin_required
def events_api_stats():
    """Placeholder API endpoint for event statistics."""
    return jsonify({
        "success": True,
        "total_events": 0,
        "active_events": 0,
        "pending_events": 0,
        "total_registrations": 0
    })

@admin_bp.route("/events/admin", endpoint="events__admin_events")
@login_required
@admin_required
def events_admin():
    """Placeholder for events admin page."""
    flash("Events admin page is not yet implemented. This is a placeholder.", "info")
    return redirect(url_for("admin.super_dashboard"))

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


# -----------------------------
# Moderation Flags (Admin Queue)
# -----------------------------
@admin_bp.route('/moderation/flags')
@login_required
@admin_required
@require_permission('content.moderate')
def moderation_flags():
    """Admin escalation queue for open content flags."""
    sort = request.args.get('sort', 'priority')  # priority|time
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 25, type=int)

    query = ContentFlag.query.filter_by(status='open')
    if sort == 'priority':
        # Custom ordering: critical > high > medium > normal > low
        priority_order = db.case(
            (
                (ContentFlag.priority == 'critical', 1),
                (ContentFlag.priority == 'high', 2),
                (ContentFlag.priority == 'medium', 3),
                (ContentFlag.priority == 'normal', 4),
                (ContentFlag.priority == 'low', 5),
            ),
            else_=6
        )
        query = query.order_by(priority_order, ContentFlag.created_at.asc())
    else:
        query = query.order_by(ContentFlag.created_at.desc())

    flags = query.paginate(page=page, per_page=per_page, error_out=False)

    # Build per-flag review URL via registry
    try:
        from app.admin.moderator.registry import get_review_url
        flag_rows = [{
            "flag": flag,
            "review_url": get_review_url(flag.entity_type, flag.entity_id)
        } for flag in flags.items]
    except Exception:
        flag_rows = [{"flag": flag, "review_url": None} for flag in flags.items]

    return render_template('admin/moderation/flags.html', flags=flags, flag_rows=flag_rows, sort=sort, title='Moderation Flags')


@admin_bp.route('/moderation/flags/<int:flag_id>/resolve', methods=['POST'])
@login_required
@admin_required
@require_permission('content.moderate')
def resolve_flag(flag_id: int):
    from app.admin.owner.models import OwnerAuditLog
    flag = ContentFlag.query.get_or_404(flag_id)
    action = request.form.get('action')  # approve|reject|suspend|ignore|request_changes
    notes = request.form.get('notes', '')

    flag.status = 'resolved'
    flag.resolved_by = current_user.id
    flag.resolution_action = action
    flag.resolution_notes = notes
    flag.resolved_at = datetime.utcnow()
    db.session.commit()

    OwnerAuditLog.log_action(
        current_user,
        action='flag.resolve',
        category='moderation',
        details={
            'flag_id': int(flag.id),
            'entity_type': flag.entity_type,
            'entity_id': int(flag.entity_id),
            'resolution_action': action,
            'notes': notes,
        }
    )

    flash('Flag resolved', 'success')
    if request.is_json:
        return jsonify({'ok': True})
    return redirect(url_for('admin.moderation_flags'))


@admin_bp.route('/moderation/flags/<int:flag_id>/reject', methods=['POST'])
@login_required
@admin_required
@require_permission('content.moderate')
def reject_flag(flag_id: int):
    from app.admin.owner.models import OwnerAuditLog
    flag = ContentFlag.query.get_or_404(flag_id)
    notes = request.form.get('notes', '')

    flag.status = 'rejected'
    flag.resolved_by = current_user.id
    flag.resolution_action = 'reject_flag'
    flag.resolution_notes = notes
    flag.resolved_at = datetime.utcnow()
    db.session.commit()

    OwnerAuditLog.log_action(
        current_user,
        action='flag.reject',
        category='moderation',
        details={'flag_id': int(flag.id), 'notes': notes}
    )

    flash('Flag rejected', 'info')
    if request.is_json:
        return jsonify({'ok': True})
    return redirect(url_for('admin.moderation_flags'))


@admin_bp.route('/moderation/flags/<int:flag_id>/escalate', methods=['POST'])
@login_required
@admin_required
@require_permission('content.moderate')
def escalate_flag(flag_id: int):
    from app.admin.owner.models import OwnerAuditLog
    flag = ContentFlag.query.get_or_404(flag_id)
    role = request.form.get('role')  # e.g., admin, super_admin, owner
    assignee = request.form.get('assignee_id', type=int)

    flag.escalated_to_role = role
    flag.assigned_to = assignee
    flag.status = 'in_review'
    db.session.commit()

    OwnerAuditLog.log_action(
        current_user,
        action='flag.escalate',
        category='moderation',
        details={'flag_id': int(flag.id), 'role': role, 'assignee': assignee}
    )

    flash('Flag escalated', 'warning')
    if request.is_json:
        return jsonify({'ok': True})
    return redirect(url_for('admin.moderation_flags'))


@admin_bp.route("/users/<string:user_id>/update", methods=["GET", "POST"], endpoint="update_user")
@login_required
@admin_required
def update_user(user_id):
    """Update user account information (username, email, phone only)."""
    from app.identity.models.user import User
    from app.audit.comprehensive_audit import AuditService

    user = User.query.filter_by(public_id=user_id).first_or_404()
    is_compliance_officer = current_user.has_global_role('compliance_officer')
    compliance_override = request.form.get('compliance_override') == 'on' if is_compliance_officer else False

    if request.method == "POST":
        change_reason = request.form.get('change_reason', '').strip()

        if not change_reason:
            flash("Reason for change is required for audit trail.", "danger")
            return render_template("admin/update_user.html", user=user, is_compliance_officer=is_compliance_officer)

        changes_made = {}

        # Username change
        new_username = request.form.get('username', user.username)
        if new_username != user.username:
            if user.is_verified and not compliance_override and not is_compliance_officer:
                flash("Cannot change username for verified accounts. Contact compliance officer.", "danger")
                return render_template("admin/update_user.html", user=user, is_compliance_officer=is_compliance_officer)

            existing = User.query.filter_by(username=new_username).first()
            if existing and existing.id != user.id:
                flash("Username already taken.", "danger")
                return render_template("admin/update_user.html", user=user, is_compliance_officer=is_compliance_officer)

            changes_made['username'] = {'old': user.username, 'new': new_username}
            user.username = new_username

        # Email change
        new_email = request.form.get('email', user.email)
        if new_email != user.email:
            if user.is_verified and not compliance_override and not is_compliance_officer:
                flash("Cannot change email for verified accounts. Contact compliance officer.", "danger")
                return render_template("admin/update_user.html", user=user, is_compliance_officer=is_compliance_officer)

            if new_email:
                existing = User.query.filter_by(email=new_email).first()
                if existing and existing.id != user.id:
                    flash("Email already in use.", "danger")
                    return render_template("admin/update_user.html", user=user, is_compliance_officer=is_compliance_officer)

            changes_made['email'] = {'old': user.email, 'new': new_email}
            user.email = new_email
            if user.is_verified:
                user.is_verified = False
                changes_made['verification_reset'] = True

        # Phone change
        new_phone = request.form.get('phone', user.phone)
        if new_phone != user.phone:
            changes_made['phone'] = {'old': user.phone, 'new': new_phone}
            user.phone = new_phone

        if changes_made:
            db.session.commit()

            AuditService.data_change(
                entity_type="user",
                entity_id=user.public_id,
                operation="update",
                old_value=changes_made,
                new_value={k: v['new'] if isinstance(v, dict) else v for k, v in changes_made.items()},
                changed_by=current_user.id,
                ip_address=request.remote_addr,
                user_agent=request.user_agent.string if request.user_agent else None,
                extra_data={"reason": change_reason, "compliance_override": compliance_override}
            )

            flash(f"User {user.username} updated successfully. Changes logged for audit.", "success")
        else:
            flash("No changes were made.", "info")

        return redirect(url_for("admin.view_user", user_id=user.public_id))

    return render_template("admin/update_user.html", user=user, is_compliance_officer=is_compliance_officer)

@admin_bp.route("/users/<string:user_id>/profile", methods=["GET", "POST"], endpoint="update_profile")
@login_required
@admin_required
def update_profile(user_id):
    """Update user profile (KYC/personal information)."""
    from app.identity.models.user import User
    from app.profile.models import get_profile_by_user, UserProfile
    from app.auth.kyc_compliance import calculate_kyc_tier
    from app.audit.comprehensive_audit import AuditService

    user = User.query.filter_by(public_id=user_id).first_or_404()
    profile = get_profile_by_user(user)
    if not profile:
        profile = UserProfile(user_id=user.id)
        db.session.add(profile)
        db.session.commit()

    kyc_info = calculate_kyc_tier(user.id)
    is_compliance_officer = current_user.has_global_role('compliance_officer')

    if request.method == "POST":
        change_reason = request.form.get('change_reason', '').strip()

        if not change_reason:
            flash("Reason for change is required for audit trail.", "danger")
            return render_template("admin/update_profile.html", user=user, profile=profile, kyc_info=kyc_info, is_compliance_officer=is_compliance_officer)

        changes_made = {}

        # Update address field (which we know exists)
        new_address = request.form.get('address', '')
        if new_address != (profile.address or ''):
            changes_made['address'] = {'old': profile.address, 'new': new_address}
            profile.address = new_address

        # Check if city field exists before trying to update it
        # Use hasattr to safely check for the attribute
        if hasattr(profile, 'city'):
            new_city = request.form.get('city', '')
            if new_city != (profile.city or ''):
                changes_made['city'] = {'old': profile.city, 'new': new_city}
                profile.city = new_city

        # Check if country field exists before trying to update it
        if hasattr(profile, 'country'):
            new_country = request.form.get('country', '')
            if new_country != (profile.country or ''):
                changes_made['country'] = {'old': profile.country, 'new': new_country}
                profile.country = new_country

        if changes_made:
            db.session.commit()

            AuditService.data_change(
                entity_type="user_profile",
                entity_id=user.public_id,
                operation="update",
                old_value=changes_made,
                new_value={k: v['new'] if isinstance(v, dict) else v for k, v in changes_made.items()},
                changed_by=current_user.id,
                ip_address=request.remote_addr,
                user_agent=request.user_agent.string if request.user_agent else None,
                extra_data={"reason": change_reason}
            )

            flash(f"Profile updated successfully. Changes logged for audit.", "success")
        else:
            flash("No changes were made.", "info")

        return redirect(url_for("admin.view_user", user_id=user.public_id))

    return render_template("admin/update_profile.html", user=user, profile=profile, kyc_info=kyc_info, is_compliance_officer=is_compliance_officer)

# -----------------------------
# Compliance & Auditor Routes
# -----------------------------
@admin_bp.route("/compliance/dashboard", endpoint="compliance_dashboard")
@login_required
@require_role('compliance_officer')
def compliance_dashboard():
    """Redirect to the new compliance dashboard."""
    return redirect(url_for('compliance.dashboard'))

@admin_bp.route("/compliance/action/<string:verification_id>", methods=["POST"], endpoint="compliance_action")
@login_required
@require_role('compliance_officer')
def compliance_action(verification_id):
    """Redirect compliance actions to the new compliance routes."""
    return redirect(url_for('compliance.compliance_action', verification_id=verification_id))

@admin_bp.route("/auditor/dashboard", endpoint="auditor_dashboard")
@login_required
@require_role('auditor')
def auditor_dashboard():
    """Auditor dashboard for read-only access to all logs."""
    from app.audit.comprehensive_audit import FinancialAuditLog, SecurityEventLog, DataAccessLog
    from app.identity.models.user import User

    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    user_id = request.args.get('user_id')
    action_type = request.args.get('action_type')

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

    financial_logs = financial_query.order_by(FinancialAuditLog.created_at.desc()).limit(100).all()
    security_logs = security_query.order_by(SecurityEventLog.created_at.desc()).limit(100).all()
    data_access_logs = data_access_query.order_by(DataAccessLog.created_at.desc()).limit(100).all()

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

    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    user_id = request.args.get('user_id')

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

    output = StringIO()
    writer = csv.writer(output)

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

    from flask import Response
    output.seek(0)
    return Response(
        output,
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment;filename={filename}"}
    )


# -----------------------------
# Events Module Placeholder Routes
# -----------------------------
@admin_bp.route("/events/dashboard", endpoint="events_admin_dashboard")
@login_required
@admin_required
def events_admin_dashboard():
    """Placeholder for events admin dashboard."""
    flash("Events module is not yet implemented.", "info")
    return redirect(url_for("admin.super_dashboard"))

@admin_bp.route("/api/events/admin_stats", endpoint="events_api_admin_stats")
@login_required
@admin_required
def events_api_admin_stats():
    """Placeholder API for events statistics."""
    return jsonify({
        "success": True,
        "total_events": 0,
        "active_events": 0,
        "pending_events": 0,
        "total_registrations": 0
    })

@admin_bp.route("/events/admin", endpoint="events_admin_events")
@login_required
@admin_required
def events_admin_events():
    """Placeholder for events management page."""
    flash("Events management is not yet implemented.", "info")
    return redirect(url_for("admin.super_dashboard"))

# -----------------------------
# User Activity Log
# -----------------------------
@admin_bp.route("/users/<string:user_id>/activity", endpoint="user_activity")
@login_required
@admin_required
def user_activity(user_id):
    """View user activity history (logins, actions, etc.)"""
    from app.identity.models.user import User
    from app.audit.comprehensive_audit import (
        SecurityEventLog, DataAccessLog, DataChangeLog, APIAuditLog
    )

    user = User.query.filter_by(public_id=user_id).first_or_404()

    # Get security events for this user
    security_events = SecurityEventLog.query.filter_by(
        user_id=user.id
    ).order_by(SecurityEventLog.created_at.desc()).limit(50).all()

    # Get data access logs for this user
    data_access_logs = DataAccessLog.query.filter_by(
        accessed_by=user.id
    ).order_by(DataAccessLog.created_at.desc()).limit(50).all()

    # Get data changes made by this user
    data_changes = DataChangeLog.query.filter_by(
        changed_by=user.id
    ).order_by(DataChangeLog.created_at.desc()).limit(50).all()

    # Get API calls made by this user
    api_calls = APIAuditLog.query.filter_by(
        user_id=user.id
    ).order_by(APIAuditLog.created_at.desc()).limit(50).all()

    return render_template(
        "admin/user_activity.html",
        user=user,
        security_events=security_events,
        data_access_logs=data_access_logs,
        data_changes=data_changes,
        api_calls=api_calls
    )


# -----------------------------
# KYC Document Viewer
# -----------------------------
@admin_bp.route("/users/<string:user_id>/kyc-documents", endpoint="view_kyc_documents")
@login_required
@admin_required
def view_kyc_documents(user_id):
    """View KYC documents for a user."""
    from app.identity.models.user import User
    from app.identity.individuals.individual_document import IndividualKYCDocument

    user = User.query.filter_by(public_id=user_id).first_or_404()

    # Get KYC documents
    kyc_documents = IndividualKYCDocument.query.filter_by(
        user_id=user.id
    ).order_by(IndividualKYCDocument.created_at.desc()).all()

    # Get KYC tier info
    from app.auth.kyc_compliance import calculate_kyc_tier
    kyc_info = calculate_kyc_tier(user.id)

    return render_template(
        "admin/kyc_documents.html",
        user=user,
        kyc_documents=kyc_documents,
        kyc_info=kyc_info
    )


# -----------------------------
# KYC Document Approval
# -----------------------------
@admin_bp.route("/users/<string:user_id>/kyc-documents/<int:doc_id>/approve",
                methods=["POST"], endpoint="approve_kyc_document")
@login_required
@require_role('compliance_officer')
def approve_kyc_document(user_id, doc_id):
    """Approve a KYC document."""
    from app.identity.models.user import User
    from app.identity.individuals.individual_document import IndividualKYCDocument
    from app.audit.comprehensive_audit import AuditService, AuditSeverity

    user = User.query.filter_by(public_id=user_id).first_or_404()
    document = IndividualKYCDocument.query.get_or_404(doc_id)

    if document.user_id != user.id:
        flash("Document does not belong to this user.", "danger")
        return redirect(url_for("admin.view_kyc_documents", user_id=user_id))

    reason = request.form.get("reason", "").strip()
    if not reason:
        flash("Approval reason is required.", "danger")
        return redirect(url_for("admin.view_kyc_documents", user_id=user_id))

    try:
        old_status = document.status
        document.status = "approved"
        document.reviewed_by = current_user.id
        document.reviewed_at = datetime.utcnow()
        document.review_notes = reason

        db.session.commit()

        # Log the approval
        AuditService.data_change(
            entity_type="kyc_document",
            entity_id=str(document.id),
            operation="approve",
            old_value={"status": old_status},
            new_value={"status": "approved", "reviewed_by": current_user.id},
            changed_by=current_user.id,
            ip_address=request.remote_addr,
            user_agent=request.user_agent.string if request.user_agent else None,
            extra_data={"reason": reason, "document_type": document.document_type}
        )

        flash(f"KYC document {document.document_type} approved successfully.", "success")

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error approving KYC document: {e}")
        flash(f"Error approving document: {str(e)}", "danger")

    return redirect(url_for("admin.view_kyc_documents", user_id=user_id))


@admin_bp.route("/users/<string:user_id>/kyc-documents/<int:doc_id>/reject",
                methods=["POST"], endpoint="reject_kyc_document")
@login_required
@require_role('compliance_officer')
def reject_kyc_document(user_id, doc_id):
    """Reject a KYC document."""
    from app.identity.models.user import User
    from app.identity.individuals.individual_document import IndividualKYCDocument
    from app.audit.comprehensive_audit import AuditService, AuditSeverity

    user = User.query.filter_by(public_id=user_id).first_or_404()
    document = IndividualKYCDocument.query.get_or_404(doc_id)

    if document.user_id != user.id:
        flash("Document does not belong to this user.", "danger")
        return redirect(url_for("admin.view_kyc_documents", user_id=user_id))

    reason = request.form.get("reason", "").strip()
    if not reason:
        flash("Rejection reason is required.", "danger")
        return redirect(url_for("admin.view_kyc_documents", user_id=user_id))

    try:
        old_status = document.status
        document.status = "rejected"
        document.reviewed_by = current_user.id
        document.reviewed_at = datetime.utcnow()
        document.review_notes = reason

        db.session.commit()

        # Log the rejection
        AuditService.data_change(
            entity_type="kyc_document",
            entity_id=str(document.id),
            operation="reject",
            old_value={"status": old_status},
            new_value={"status": "rejected", "reviewed_by": current_user.id},
            changed_by=current_user.id,
            ip_address=request.remote_addr,
            user_agent=request.user_agent.string if request.user_agent else None,
            extra_data={"reason": reason, "document_type": document.document_type}
        )

        flash(f"KYC document {document.document_type} rejected.", "warning")

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error rejecting KYC document: {e}")
        flash(f"Error rejecting document: {str(e)}", "danger")

    return redirect(url_for("admin.view_kyc_documents", user_id=user_id))


# -----------------------------
# Enhanced Audit Logging for Existing Endpoints
# -----------------------------
def _log_role_change(user, action, role_name, changed_by, ip_address, reason=None):
    """Helper to log role changes to audit service."""
    from app.audit.comprehensive_audit import AuditService

    try:
        AuditService.data_change(
            entity_type="user_role",
            entity_id=user.public_id,
            operation=action,
            old_value={"roles_before": [r.role.name for r in user.roles]},
            new_value={"roles_after": [r.role.name for r in user.roles]},
            changed_by=changed_by,
            ip_address=ip_address,
            extra_data={
                "specific_role": role_name,
                "reason": reason or f"{action} by admin",
                "username": user.username
            }
        )
    except Exception as e:
        logger.error(f"Failed to log role change audit: {e}")


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
