# app/accommodation/routes.py
from flask import render_template, request
from flask_login import login_required, current_user
from app.accommodation import accommodation_bp
from app.auth.decorators import require_role, require_profile_completion, require_kyc_tier, require_moderator, require_fresh_user
from app.audit.forensic_audit import ForensicAuditService
from app.utils.id_guard import IDGuard

@accommodation_bp.route("/", endpoint="home")
@login_required
@require_role('fan', 'admin', 'owner')
@require_profile_completion
def home():
    # Log access
    ForensicAuditService.log_attempt(
        entity_type="accommodation",
        entity_id="home",
        action="view_home",
        user_id=current_user.id,
        ip_address=request.remote_addr,
        user_agent=request.user_agent.string if request.user_agent else None
    )
    return render_template("accommodation_home.html")

@accommodation_bp.route("/detail/<string:public_id>", endpoint="detail")
@login_required
@require_role('fan', 'admin', 'owner')
def detail(public_id):
    # Validate public_id format
    IDGuard.check_public_id(public_id, "accommodation detail route")

    # Log access with forensic audit
    ForensicAuditService.log_attempt(
        entity_type="accommodation",
        entity_id=public_id,
        action="view_detail",
        user_id=current_user.id,
        ip_address=request.remote_addr,
        user_agent=request.user_agent.string if request.user_agent else None
    )

    # Get accommodation using public_id (implementation depends on your model)
    # For now, we'll pass the public_id to template
    return render_template('accommodation/detail.html', public_id=public_id)

@accommodation_bp.route("/host/register", endpoint="host_register")
@login_required
@require_profile_completion
@require_kyc_tier(3)
def host_register():
    """Host registration page."""
    from flask import flash
    flash("Host registration requires KYC Tier 3 verification.", "info")
    # In a real implementation, this would render a host registration form
    return render_template("accommodation/host_register.html")

@accommodation_bp.route("/admin/dashboard", endpoint="admin.dashboard")
@login_required
@require_role('admin', 'owner', 'accommodation_admin')
def admin_dashboard():
    """Accommodation admin dashboard."""
    return render_template("accommodation/admin/dashboard.html")


@accommodation_bp.route("/moderate")
@login_required
@require_moderator
def moderate():
    """Show all accommodation items for moderators"""
    from app.accommodation.models.property import Property
    from app.accommodation.models.booking import AccommodationBooking
    from app.accommodation.models.review import Review

    all_properties = Property.query.filter_by(is_deleted=False).order_by(Property.created_at.desc()).all()
    all_bookings = AccommodationBooking.query.order_by(AccommodationBooking.created_at.desc()).all()
    all_reviews = Review.query.order_by(Review.created_at.desc()).all()

    # Audit log for moderator viewing
    from app.audit.comprehensive_audit import AuditService
    AuditService.security(
        event_type="moderator_view_accommodation",
        severity="info",
        description=f"Moderator {current_user.id} viewed all accommodation items",
        user_id=current_user.id,
        ip_address=request.remote_addr,
    )

    return render_template('accommodation/moderate.html',
                          properties=all_properties,
                          bookings=all_bookings,
                          reviews=all_reviews,
                          is_moderator=True)
