"""
Organization Member Routes for AFCON360 - Production Ready.
All decorators imported from app.auth.decorators.
"""

from datetime import datetime, timezone
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
    require_permission,
    require_role,
    require_fresh_user
)

# Setup logging
logger = logging.getLogger(__name__)


# -----------------------------
# Organization Member Dashboard
# -----------------------------
@admin_bp.route("/org-member", endpoint="org_member_dashboard")
@login_required
@require_role("org_member")
def org_member_dashboard():
    """Organization Member Dashboard with comprehensive membership management."""
    try:
        # Import organization modules
        from app.organization.models import OrganizationMember, Organization
        from app.organization.services import OrganizationService
        
        # Get member statistics
        member_stats = OrganizationService.get_member_dashboard_data(current_user.id)
        my_events = member_stats.get('my_events', 0)
        my_registrations = member_stats.get('my_registrations', 0)
        organization_members = member_stats.get('organization_members', 0)
        average_rating = member_stats.get('average_rating', 0)
        
        # Get user's organizations
        user_organizations = OrganizationMember.query.filter_by(
            user_id=current_user.id,
            is_deleted=False
        ).all()
        
        # Get recent activities
        recent_activities = OrganizationService.get_member_activities(current_user.id, limit=10)
        
        return render_template(
            "admin/org_member_dashboard.html",
            my_events=my_events,
            my_registrations=my_registrations,
            organization_members=organization_members,
            average_rating=average_rating,
            user_organizations=user_organizations,
            recent_activities=recent_activities,
        )
    except Exception as e:
        logger.error(f"Error loading org member dashboard: {e}")
        flash("Error loading dashboard.", "danger")
        return redirect(url_for('dashboard.dashboard'))


# -----------------------------
# Event Registration Routes
# -----------------------------
@admin_bp.route("/org-member/registrations", endpoint="org_member_registrations")
@login_required
@require_role("org_member")
def org_member_registrations():
    """View and manage event registrations."""
    try:
        from app.organization.services import OrganizationService
        
        page = request.args.get('page', 1, type=int)
        status = request.args.get('status', 'all')
        
        registrations = OrganizationService.get_member_registrations(
            current_user.id, 
            page=page, 
            status=status
        )
        
        return render_template(
            "admin/org_member/registrations.html",
            registrations=registrations,
            current_status=status
        )
    except Exception as e:
        logger.error(f"Error loading registrations: {e}")
        flash("Error loading registrations.", "danger")
        return redirect(url_for('admin.org_member_dashboard'))


@admin_bp.route("/org-member/registrations/<int:reg_id>/cancel", endpoint="org_member_cancel_registration", methods=['POST'])
@login_required
@require_role("org_member")
def org_member_cancel_registration(reg_id):
    """Cancel event registration."""
    try:
        from app.organization.services import OrganizationService
        
        if OrganizationService.cancel_registration(reg_id, current_user.id):
            flash("Registration cancelled successfully.", "success")
        else:
            flash("Error cancelling registration.", "danger")
        
        return redirect(url_for('admin.org_member_registrations'))
    except Exception as e:
        logger.error(f"Error cancelling registration: {e}")
        flash("Error cancelling registration.", "danger")
        return redirect(url_for('admin.org_member_registrations'))


# -----------------------------
# Organization Members Routes
# -----------------------------
@admin_bp.route("/org-member/members", endpoint="org_member_members")
@login_required
@require_role("org_member")
def org_member_members():
    """View and interact with organization members."""
    try:
        from app.organization.services import OrganizationService
        
        # Get user's organizations
        user_organizations = OrganizationMember.query.filter_by(
            user_id=current_user.id,
            is_deleted=False
        ).all()
        
        # Get members from user's organizations
        org_ids = [org.organization_id for org in user_organizations]
        members = OrganizationService.get_organization_members(org_ids)
        
        return render_template(
            "admin/org_member/members.html",
            members=members,
            user_organizations=user_organizations
        )
    except Exception as e:
        logger.error(f"Error loading members: {e}")
        flash("Error loading members.", "danger")
        return redirect(url_for('admin.org_member_dashboard'))


@admin_bp.route("/org-member/members/<int:member_id>/contact", endpoint="org_member_contact_member", methods=['GET', 'POST'])
@login_required
@require_role("org_member")
def org_member_contact_member(member_id):
    """Contact organization member."""
    try:
        from app.organization.models import OrganizationMember
        from app.organization.services import OrganizationService
        
        if request.method == 'POST':
            message = request.form.get('message')
            subject = request.form.get('subject')
            
            if OrganizationService.send_member_message(
                current_user.id, 
                member_id, 
                subject, 
                message
            ):
                flash("Message sent successfully.", "success")
                return redirect(url_for('admin.org_member_members'))
            else:
                flash("Error sending message.", "danger")
        
        member = OrganizationMember.query.get_or_404(member_id)
        return render_template("admin/org_member/contact_member.html", member=member)
    except Exception as e:
        logger.error(f"Error contacting member: {e}")
        flash("Error contacting member.", "danger")
        return redirect(url_for('admin.org_member_members'))


# -----------------------------
# Organization Activities Routes
# -----------------------------
@admin_bp.route("/org-member/activities", endpoint="org_member_activities")
@login_required
@require_role("org_member")
def org_member_activities():
    """View organization activities and updates."""
    try:
        from app.organization.services import OrganizationService
        
        page = request.args.get('page', 1, type=int)
        activity_type = request.args.get('type', 'all')
        
        activities = OrganizationService.get_member_activities(
            current_user.id,
            page=page,
            activity_type=activity_type
        )
        
        return render_template(
            "admin/org_member/activities.html",
            activities=activities,
            current_type=activity_type
        )
    except Exception as e:
        logger.error(f"Error loading activities: {e}")
        flash("Error loading activities.", "danger")
        return redirect(url_for('admin.org_member_dashboard'))


# -----------------------------
# Profile and Settings Routes
# -----------------------------
@admin_bp.route("/org-member/profile", endpoint="org_member_profile")
@login_required
@require_role("org_member")
def org_member_profile():
    """Organization member profile."""
    try:
        from app.organization.services import OrganizationService
        
        # Get user's profile data
        profile_data = OrganizationService.get_member_profile(current_user.id)
        
        return render_template(
            "admin/org_member/profile.html",
            profile=profile_data
        )
    except Exception as e:
        logger.error(f"Error loading profile: {e}")
        flash("Error loading profile.", "danger")
        return redirect(url_for('admin.org_member_dashboard'))


@admin_bp.route("/org-member/profile/update", endpoint="org_member_update_profile", methods=['GET', 'POST'])
@login_required
@require_role("org_member")
def org_member_update_profile():
    """Update organization member profile."""
    try:
        if request.method == 'POST':
            from app.organization.services import OrganizationService
            
            # Process profile update
            profile_data = {
                'bio': request.form.get('bio'),
                'phone': request.form.get('phone'),
                'location': request.form.get('location'),
                'skills': request.form.getlist('skills'),
                'interests': request.form.getlist('interests'),
                'notification_preferences': request.form.get('notification_preferences')
            }
            
            if OrganizationService.update_member_profile(current_user.id, profile_data):
                flash("Profile updated successfully.", "success")
                return redirect(url_for('admin.org_member_profile'))
            else:
                flash("Error updating profile.", "danger")
        
        # Get current profile data
        from app.organization.services import OrganizationService
        profile_data = OrganizationService.get_member_profile(current_user.id)
        
        return render_template("admin/org_member/update_profile.html", profile=profile_data)
    except Exception as e:
        logger.error(f"Error updating profile: {e}")
        flash("Error updating profile.", "danger")
        return redirect(url_for('admin.org_member_profile'))


@admin_bp.route("/org-member/settings", endpoint="org_member_settings")
@login_required
@require_role("org_member")
def org_member_settings():
    """Organization member settings."""
    try:
        from app.organization.services import OrganizationService
        
        # Get user's settings
        settings = OrganizationService.get_member_settings(current_user.id)
        
        return render_template(
            "admin/org_member/settings.html",
            settings=settings
        )
    except Exception as e:
        from app.utils.error_handler import log_error_to_audit
        from flask_login import current_user
        log_error_to_audit(
            user_id=current_user.id if current_user.is_authenticated else None,
            error_type="SETTINGS_LOAD_ERROR",
            error_message=str(e),
            context={"module": "org_member", "template": "settings.html"}
        )
        flash("Unable to load settings. Please try again later.", "warning")
        return redirect(url_for('admin.org_member_dashboard'))


@admin_bp.route("/org-member/settings/update", endpoint="org_member_update_settings", methods=['POST'])
@login_required
@require_role("org_member")
def org_member_update_settings():
    """Update organization member settings."""
    try:
        from app.organization.services import OrganizationService
        
        # Process settings update
        settings_data = {
            'email_notifications': request.form.get('email_notifications', type=bool),
            'push_notifications': request.form.get('push_notifications', type=bool),
            'privacy_level': request.form.get('privacy_level'),
            'language': request.form.get('language'),
            'timezone': request.form.get('timezone')
        }
        
        if OrganizationService.update_member_settings(current_user.id, settings_data):
            flash("Settings updated successfully.", "success")
        else:
            flash("Error updating settings.", "danger")
        
        return redirect(url_for('admin.org_member_settings'))
    except Exception as e:
        logger.error(f"Error updating settings: {e}")
        flash("Error updating settings.", "danger")
        return redirect(url_for('admin.org_member_settings'))


# -----------------------------
# Browse Events Routes
# -----------------------------
@admin_bp.route("/org-member/events", endpoint="org_member_events")
@login_required
@require_role("org_member")
def org_member_events():
    """Browse and discover events."""
    try:
        from app.organization.services import OrganizationService
        
        page = request.args.get('page', 1, type=int)
        category = request.args.get('category', 'all')
        location = request.args.get('location', '')
        
        events = OrganizationService.browse_events(
            current_user.id,
            page=page,
            category=category,
            location=location
        )
        
        return render_template(
            "admin/org_member/events.html",
            events=events,
            current_category=category,
            current_location=location
        )
    except Exception as e:
        logger.error(f"Error browsing events: {e}")
        flash("Error browsing events.", "danger")
        return redirect(url_for('admin.org_member_dashboard'))


@admin_bp.route("/org-member/events/<int:event_id>/register", endpoint="org_member_register_event", methods=['POST'])
@login_required
@require_role("org_member")
def org_member_register_event(event_id):
    """Register for an event."""
    try:
        from app.organization.services import OrganizationService
        
        if OrganizationService.register_for_event(event_id, current_user.id):
            flash("Event registration successful.", "success")
        else:
            flash("Error registering for event.", "danger")
        
        return redirect(url_for('admin.org_member_events'))
    except Exception as e:
        logger.error(f"Error registering for event: {e}")
        flash("Error registering for event.", "danger")
        return redirect(url_for('admin.org_member_events'))
