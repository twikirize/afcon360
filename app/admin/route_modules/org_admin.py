"""
Organization Admin Routes for AFCON360 - Production Ready.
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
# Organization Admin Dashboard
# -----------------------------
@admin_bp.route("/org-admin", endpoint="org_admin_dashboard")
@login_required
@require_role("org_admin")
def org_admin_dashboard():
    """Organization Admin Dashboard with comprehensive organization management."""
    try:
        # Import organization modules
        from app.organization.models import Organization, OrganizationMember
        from app.organization.services import OrganizationService
        
        # Get organization statistics
        org_stats = OrganizationService.get_admin_dashboard_data()
        total_organizations = org_stats.get('total_organizations', 0)
        total_members = org_stats.get('total_members', 0)
        active_admins = org_stats.get('active_admins', 0)
        compliance_score = org_stats.get('compliance_score', 0)
        
        # Get recent organizations
        recent_organizations = Organization.query.filter_by(
            is_deleted=False
        ).order_by(Organization.created_at.desc()).limit(10).all()
        
        # Get pending organization requests
        pending_organizations = Organization.query.filter_by(
            status='pending',
            is_deleted=False
        ).order_by(Organization.created_at.desc()).limit(5).all()
        
        return render_template(
            "admin/org_admin_dashboard.html",
            total_organizations=total_organizations,
            total_members=total_members,
            active_admins=active_admins,
            compliance_score=compliance_score,
            recent_organizations=recent_organizations,
            pending_organizations=pending_organizations,
        )
    except Exception as e:
        logger.error(f"Error loading org admin dashboard: {e}")
        flash("Error loading dashboard.", "danger")
        return redirect(url_for('admin.dashboard'))


# -----------------------------
# Organization Management Routes
# -----------------------------
@admin_bp.route("/org-admin/organizations", endpoint="org_admin_organizations")
@login_required
@require_role("org_admin")
def org_admin_organizations():
    """List and manage all organizations."""
    try:
        from app.organization.models import Organization
        
        page = request.args.get('page', 1, type=int)
        status = request.args.get('status', 'all')
        
        query = Organization.query.filter_by(is_deleted=False)
        
        if status != 'all':
            query = query.filter_by(status=status)
        
        organizations = query.order_by(Organization.created_at.desc()).paginate(
            page=page, per_page=20, error_out=False
        )
        
        return render_template(
            "admin/org_admin/organizations.html",
            organizations=organizations,
            current_status=status
        )
    except Exception as e:
        logger.error(f"Error loading organizations: {e}")
        flash("Error loading organizations.", "danger")
        return redirect(url_for('admin.org_admin_dashboard'))


@admin_bp.route("/org-admin/organizations/create", endpoint="org_admin_create_organization", methods=['GET', 'POST'])
@login_required
@require_role("org_admin")
def org_admin_create_organization():
    """Create new organization."""
    try:
        if request.method == 'POST':
            from app.organization.models import Organization
            from app.organization.services import OrganizationService
            
            # Process organization creation
            org_data = {
                'name': request.form.get('name'),
                'description': request.form.get('description'),
                'type': request.form.get('type'),
                'industry': request.form.get('industry'),
                'website': request.form.get('website'),
                'contact_email': request.form.get('contact_email'),
                'contact_phone': request.form.get('contact_phone'),
                'address': request.form.get('address'),
                'created_by': current_user.id
            }
            
            organization = OrganizationService.create_organization(org_data)
            if organization:
                flash("Organization created successfully.", "success")
                return redirect(url_for('admin.org_admin_organizations'))
            else:
                flash("Error creating organization.", "danger")
        
        return render_template("admin/org_admin/create_organization.html")
    except Exception as e:
        logger.error(f"Error creating organization: {e}")
        flash("Error creating organization.", "danger")
        return redirect(url_for('admin.org_admin_organizations'))


@admin_bp.route("/org-admin/organizations/<int:org_id>/edit", endpoint="org_admin_edit_organization", methods=['GET', 'POST'])
@login_required
@require_role("org_admin")
def org_admin_edit_organization(org_id):
    """Edit existing organization."""
    try:
        from app.organization.models import Organization
        from app.organization.services import OrganizationService
        
        organization = Organization.query.get_or_404(org_id)
        
        if request.method == 'POST':
            # Process organization update
            org_data = {
                'name': request.form.get('name'),
                'description': request.form.get('description'),
                'type': request.form.get('type'),
                'industry': request.form.get('industry'),
                'website': request.form.get('website'),
                'contact_email': request.form.get('contact_email'),
                'contact_phone': request.form.get('contact_phone'),
                'address': request.form.get('address'),
                'status': request.form.get('status')
            }
            
            if OrganizationService.update_organization(org_id, org_data):
                flash("Organization updated successfully.", "success")
                return redirect(url_for('admin.org_admin_organizations'))
            else:
                flash("Error updating organization.", "danger")
        
        return render_template("admin/org_admin/edit_organization.html", organization=organization)
    except Exception as e:
        logger.error(f"Error editing organization: {e}")
        flash("Error editing organization.", "danger")
        return redirect(url_for('admin.org_admin_organizations'))


@admin_bp.route("/org-admin/organizations/<int:org_id>/delete", endpoint="org_admin_delete_organization", methods=['POST'])
@login_required
@require_role("org_admin")
@require_fresh_user
def org_admin_delete_organization(org_id):
    """Delete organization."""
    try:
        from app.organization.models import Organization
        from app.organization.services import OrganizationService
        
        organization = Organization.query.get_or_404(org_id)
        
        if OrganizationService.delete_organization(org_id):
            flash(f"Organization '{organization.name}' deleted successfully.", "warning")
        else:
            flash("Error deleting organization.", "danger")
        
        return redirect(url_for('admin.org_admin_organizations'))
    except Exception as e:
        logger.error(f"Error deleting organization: {e}")
        flash("Error deleting organization.", "danger")
        return redirect(url_for('admin.org_admin_organizations'))


# -----------------------------
# Member Management Routes
# -----------------------------
@admin_bp.route("/org-admin/members", endpoint="org_admin_members")
@login_required
@require_role("org_admin")
def org_admin_members():
    """Manage organization members."""
    try:
        from app.organization.models import OrganizationMember
        
        page = request.args.get('page', 1, type=int)
        status = request.args.get('status', 'all')
        role = request.args.get('role', 'all')
        
        query = OrganizationMember.query.filter_by(is_deleted=False)
        
        if status != 'all':
            query = query.filter_by(status=status)
        
        if role != 'all':
            query = query.filter_by(role=role)
        
        members = query.order_by(
            OrganizationMember.created_at.desc()
        ).paginate(page=page, per_page=20, error_out=False)
        
        return render_template(
            "admin/org_admin/members.html",
            members=members,
            current_status=status,
            current_role=role
        )
    except Exception as e:
        logger.error(f"Error loading members: {e}")
        flash("Error loading members.", "danger")
        return redirect(url_for('admin.org_admin_dashboard'))


@admin_bp.route("/org-admin/members/<int:member_id>/approve", endpoint="org_admin_approve_member", methods=['POST'])
@login_required
@require_role("org_admin")
def org_admin_approve_member(member_id):
    """Approve organization member."""
    try:
        from app.organization.models import OrganizationMember
        from app.organization.services import OrganizationService
        
        member = OrganizationMember.query.get_or_404(member_id)
        
        if OrganizationService.approve_member(member_id, approved_by=current_user.id):
            flash(f"Member {member.user.username} approved successfully.", "success")
        else:
            flash("Error approving member.", "danger")
        
        return redirect(url_for('admin.org_admin_members'))
    except Exception as e:
        logger.error(f"Error approving member: {e}")
        flash("Error approving member.", "danger")
        return redirect(url_for('admin.org_admin_members'))


@admin_bp.route("/org-admin/members/<int:member_id>/reject", endpoint="org_admin_reject_member", methods=['POST'])
@login_required
@require_role("org_admin")
def org_admin_reject_member(member_id):
    """Reject organization member."""
    try:
        from app.organization.models import OrganizationMember
        from app.organization.services import OrganizationService
        
        member = OrganizationMember.query.get_or_404(member_id)
        reason = request.form.get('reason', 'No reason provided')
        
        if OrganizationService.reject_member(member_id, reason, rejected_by=current_user.id):
            flash(f"Member {member.user.username} rejected.", "warning")
        else:
            flash("Error rejecting member.", "danger")
        
        return redirect(url_for('admin.org_admin_members'))
    except Exception as e:
        logger.error(f"Error rejecting member: {e}")
        flash("Error rejecting member.", "danger")
        return redirect(url_for('admin.org_admin_members'))


@admin_bp.route("/org-admin/members/<int:member_id>/remove", endpoint="org_admin_remove_member", methods=['POST'])
@login_required
@require_role("org_admin")
@require_fresh_user
def org_admin_remove_member(member_id):
    """Remove organization member."""
    try:
        from app.organization.models import OrganizationMember
        from app.organization.services import OrganizationService
        
        member = OrganizationMember.query.get_or_404(member_id)
        
        if OrganizationService.remove_member(member_id, removed_by=current_user.id):
            flash(f"Member {member.user.username} removed from organization.", "warning")
        else:
            flash("Error removing member.", "danger")
        
        return redirect(url_for('admin.org_admin_members'))
    except Exception as e:
        logger.error(f"Error removing member: {e}")
        flash("Error removing member.", "danger")
        return redirect(url_for('admin.org_admin_members'))


# -----------------------------
# Permission Control Routes
# -----------------------------
@admin_bp.route("/org-admin/permissions", endpoint="org_admin_permissions")
@login_required
@require_role("org_admin")
def org_admin_permissions():
    """Configure roles and access permissions."""
    try:
        from app.organization.models import OrganizationRole, OrganizationPermission
        
        roles = OrganizationRole.query.filter_by(
            is_deleted=False
        ).order_by(OrganizationRole.created_at.desc()).all()
        
        permissions = OrganizationPermission.query.filter_by(
            is_deleted=False
        ).order_by(OrganizationPermission.created_at.desc()).all()
        
        return render_template(
            "admin/org_admin/permissions.html",
            roles=roles,
            permissions=permissions
        )
    except Exception as e:
        logger.error(f"Error loading permissions: {e}")
        flash("Error loading permissions.", "danger")
        return redirect(url_for('admin.org_admin_dashboard'))


@admin_bp.route("/org-admin/permissions/create-role", endpoint="org_admin_create_role", methods=['GET', 'POST'])
@login_required
@require_role("org_admin")
def org_admin_create_role():
    """Create new organization role."""
    try:
        if request.method == 'POST':
            from app.organization.models import OrganizationRole
            from app.organization.services import OrganizationService
            
            # Process role creation
            role_data = {
                'name': request.form.get('name'),
                'description': request.form.get('description'),
                'permissions': request.form.getlist('permissions'),
                'created_by': current_user.id
            }
            
            role = OrganizationService.create_role(role_data)
            if role:
                flash("Role created successfully.", "success")
                return redirect(url_for('admin.org_admin_permissions'))
            else:
                flash("Error creating role.", "danger")
        
        return render_template("admin/org_admin/create_role.html")
    except Exception as e:
        logger.error(f"Error creating role: {e}")
        flash("Error creating role.", "danger")
        return redirect(url_for('admin.org_admin_permissions'))


# -----------------------------
# Invitation Management Routes
# -----------------------------
@admin_bp.route("/org-admin/invitations", endpoint="org_admin_invitations")
@login_required
@require_role("org_admin")
def org_admin_invitations():
    """Manage organization invitations and requests."""
    try:
        from app.organization.models import OrganizationInvitation
        
        page = request.args.get('page', 1, type=int)
        status = request.args.get('status', 'all')
        
        query = OrganizationInvitation.query.filter_by(is_deleted=False)
        
        if status != 'all':
            query = query.filter_by(status=status)
        
        invitations = query.order_by(
            OrganizationInvitation.created_at.desc()
        ).paginate(page=page, per_page=20, error_out=False)
        
        return render_template(
            "admin/org_admin/invitations.html",
            invitations=invitations,
            current_status=status
        )
    except Exception as e:
        logger.error(f"Error loading invitations: {e}")
        flash("Error loading invitations.", "danger")
        return redirect(url_for('admin.org_admin_dashboard'))


@admin_bp.route("/org-admin/invitations/create", endpoint="org_admin_create_invitation", methods=['GET', 'POST'])
@login_required
@require_role("org_admin")
def org_admin_create_invitation():
    """Create new organization invitation."""
    try:
        if request.method == 'POST':
            from app.organization.models import OrganizationInvitation
            from app.organization.services import OrganizationService
            
            # Process invitation creation
            invitation_data = {
                'email': request.form.get('email'),
                'organization_id': request.form.get('organization_id', type=int),
                'role': request.form.get('role'),
                'message': request.form.get('message'),
                'expires_at': request.form.get('expires_at'),
                'created_by': current_user.id
            }
            
            invitation = OrganizationService.create_invitation(invitation_data)
            if invitation:
                flash("Invitation sent successfully.", "success")
                return redirect(url_for('admin.org_admin_invitations'))
            else:
                flash("Error sending invitation.", "danger")
        
        return render_template("admin/org_admin/create_invitation.html")
    except Exception as e:
        logger.error(f"Error creating invitation: {e}")
        flash("Error creating invitation.", "danger")
        return redirect(url_for('admin.org_admin_invitations'))


# -----------------------------
# Analytics and Settings
# -----------------------------
@admin_bp.route("/org-admin/analytics", endpoint="org_admin_analytics")
@login_required
@require_role("org_admin")
def org_admin_analytics():
    """Organization analytics and performance data."""
    try:
        from app.organization.services import OrganizationService
        
        # Get analytics data
        analytics = OrganizationService.get_analytics_data()
        
        return render_template(
            "admin/org_admin/analytics.html",
            analytics=analytics
        )
    except Exception as e:
        logger.error(f"Error loading analytics: {e}")
        flash("Error loading analytics.", "danger")
        return redirect(url_for('admin.org_admin_dashboard'))


@admin_bp.route("/org-admin/settings", endpoint="org_admin_settings")
@login_required
@require_role("org_admin")
def org_admin_settings():
    """Organization admin settings."""
    try:
        return render_template("admin/org_admin/settings.html")
    except Exception as e:
        from app.utils.error_handler import log_error_to_audit
        from flask_login import current_user
        log_error_to_audit(
            user_id=current_user.id if current_user.is_authenticated else None,
            error_type="SETTINGS_LOAD_ERROR",
            error_message=str(e),
            context={"module": "org_admin", "template": "settings.html"}
        )
        flash("Unable to load settings. Please try again later.", "warning")
        return redirect(url_for('admin.org_admin_dashboard'))
