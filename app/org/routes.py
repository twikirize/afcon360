"""
Organization dashboard and management routes
"""
from flask import Blueprint, render_template, abort, session, redirect, url_for
from flask_login import login_required, current_user
from app.extensions import db
from app.auth.decorators import require_profile_completion, require_kyc_tier

org_bp = Blueprint('org', __name__, url_prefix='/org')

@org_bp.route('/<int:org_id>/dashboard')
@login_required
@require_profile_completion
def dashboard(org_id):
    """Organization dashboard page."""
    # Try to import organization models
    try:
        from app.identity.models.organisation import Organisation
        from app.identity.models.organisation_member import OrganisationMember
    except ImportError:
        # If models don't exist, show a placeholder dashboard
        return render_template('org/dashboard.html',
                             org={'id': org_id, 'name': 'Organization', 'verified': False},
                             org_role_name='Member',
                             member_count=1,
                             active_listings=0,
                             monthly_revenue='UGX 0',
                             pending_bookings=0,
                             recent_activities=[],
                             recent_members=[])

    # Check if user has access to this organization
    membership = OrganisationMember.query.filter_by(
        user_id=current_user.id,
        organisation_id=org_id,
        is_deleted=False,
        is_active=True
    ).first()

    if not membership:
        abort(403)

    # Get organization
    org = Organisation.query.get(org_id)
    if not org:
        abort(404)

    # Get user's role in this organization
    org_role_name = membership.role if hasattr(membership, 'role') else "Member"

    # Get member count
    member_count = OrganisationMember.query.filter_by(
        organisation_id=org_id,
        is_deleted=False,
        is_active=True
    ).count()

    # Placeholder data for other stats
    active_listings = 0
    monthly_revenue = "UGX 0"
    pending_bookings = 0

    # Recent activities placeholder
    recent_activities = [
        {"icon": "👤", "text": "New member joined", "time": "2 hours ago"},
        {"icon": "📊", "text": "Monthly report generated", "time": "1 day ago"},
        {"icon": "✅", "text": "Booking confirmed", "time": "2 days ago"},
    ]

    # Recent members placeholder
    recent_members = [
        {"initials": "JD", "name": "John Doe", "role": "Admin", "status": "active"},
        {"initials": "JS", "name": "Jane Smith", "role": "Member", "status": "active"},
    ]

    return render_template('org/dashboard.html',
                         org=org,
                         org_role_name=org_role_name,
                         member_count=member_count,
                         active_listings=active_listings,
                         monthly_revenue=monthly_revenue,
                         pending_bookings=pending_bookings,
                         recent_activities=recent_activities,
                         recent_members=recent_members)

@org_bp.route('/register', endpoint='register')
@login_required
@require_profile_completion
@require_kyc_tier(4)
def register():
    """Organization registration page."""
    from flask import flash
    flash("Organization registration requires KYC Tier 4 business verification.", "info")
    # In a real implementation, this would render an organization registration form
    return render_template('org/register.html')
