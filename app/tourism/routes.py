# app/tourism/routes.py

from flask import render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from app.tourism import tourism_bp
from app.auth.decorators import require_moderator
from app.auth.decorators import require_role
from app.audit.forensic_audit import ForensicAuditService
from app.auth.kyc_compliance import calculate_kyc_tier
from app.extensions import db
from datetime import datetime, timezone

# Attach routes to the tourism blueprint
@tourism_bp.route("/", endpoint="home")
def home():
    """Tourism home page.

    No forensic audit is recorded for the listing page.
    A lightweight analytics counter is tracked instead.
    """
    try:
        from app.services.analytics import AnalyticsService
        AnalyticsService.track_page_view("tourism")
    except Exception:
        pass
    return render_template("tourism_home.html")

@tourism_bp.route("/detail/<string:slug>", endpoint="detail")
@login_required
@require_role('fan', 'admin', 'owner')
def detail(slug):
    # Log access with forensic audit
    ForensicAuditService.log_attempt(
        entity_type="tourism",
        entity_id=slug,
        action="view_detail",
        user_id=current_user.id,
        ip_address=request.remote_addr,
        user_agent=request.user_agent.string if request.user_agent else None
    )

    # Check KYC tier if needed (for paid features)
    kyc_info = calculate_kyc_tier(current_user.id)

    return render_template('tourism_detail.html',
                         slug=slug,
                         kyc_info=kyc_info,
                         user_public_id=current_user.public_id)


# ============================================================================
# MODERATOR ROUTES
# ============================================================================

@tourism_bp.route("/moderate")
@login_required
@require_moderator
def moderate():
    """Show all tourism items for moderators (same data as admin view)"""
    
    # Show all listings, not just pending
    try:
        from app.tourism.models import TourismListing
        all_listings = TourismListing.query.filter_by(is_deleted=False).order_by(TourismListing.created_at.desc()).all()
    except ImportError:
        all_listings = []
    
    # Audit log for moderator viewing
    from app.audit.comprehensive_audit import AuditService
    AuditService.security(
        event_type="moderator_view_tourism",
        severity="info",
        description=f"Moderator {current_user.id} viewed all tourism listings",
        user_id=current_user.id,
        ip_address=request.remote_addr,
    )
    
    return render_template('tourism/moderate.html', listings=all_listings, is_moderator=True)


@tourism_bp.route("/moderate/listing/<int:id>")
@login_required
@require_moderator
def moderate_listing(id):
    """Show single listing for moderation review"""
    
    try:
        from app.tourism.models import TourismListing
        listing = TourismListing.query.get_or_404(id)
    except ImportError:
        flash('Tourism models not available.', 'danger')
        return redirect(url_for('tourism.moderate'))
    
    return render_template('tourism/moderate_listing.html', listing=listing)


@tourism_bp.route("/moderate/<entity_type>/<int:id>/<action>", methods=['POST'])
@login_required
@require_moderator
def moderate_action(entity_type, id, action):
    """Approve, reject, or flag tourism items"""
    
    try:
        from app.tourism.models import TourismListing
        item = TourismListing.query.get_or_404(id)
        redirect_url = url_for('tourism.moderate_listing', id=id)
    except ImportError:
        flash('Tourism models not available.', 'danger')
        return redirect(url_for('tourism.moderate'))
    
    if action == 'approve':
        item.status = 'published'
        item.published_at = datetime.now(timezone.utc)
        db.session.commit()
        flash('Listing approved successfully.', 'success')
    
    elif action == 'reject':
        reason = request.form.get('reason', '').strip()
        if not reason:
            flash('Rejection reason is required.', 'warning')
            return redirect(redirect_url)
        
        item.status = 'rejected'
        item.rejection_reason = reason
        db.session.commit()
        flash('Listing rejected successfully.', 'success')
    
    elif action == 'flag':
        from app.admin.services import create_flag
        reason = request.form.get('reason', '').strip()
        priority = request.form.get('priority', 'medium')
        
        if not reason:
            flash('Reason required for flagging.', 'warning')
            return redirect(redirect_url)
        
        ok, flag = create_flag(
            user=current_user,
            entity_type='tourism_listing',
            entity_id=id,
            reason=reason,
            priority=priority
        )
        
        if ok:
            flash(f'Listing flagged for review (Priority: {priority})', 'warning')
        else:
            flash(f'Failed to flag: {flag}', 'danger')

    return redirect(url_for('tourism.moderate'))


@tourism_bp.route("/moderate/listing/<int:id>/flag", methods=['POST'])
@login_required
@require_moderator
def flag_listing(id):
    """Flag a tourism listing for moderation review."""
    try:
        from app.tourism.models import TourismListing
        listing = TourismListing.query.get_or_404(id)
    except ImportError:
        flash('Tourism models not available.', 'danger')
        return redirect(url_for('tourism.moderate'))

    reason = request.form.get('reason', '').strip()
    priority = request.form.get('priority', 'normal').strip()

    if not reason:
        flash('Flag reason is required.', 'warning')
        return redirect(url_for('tourism.moderate_listing', id=id))

    from app.admin.services import create_flag
    ok, flag = create_flag(current_user, 'tourism_listing', id, reason, priority)

    if ok:
        flash(f'Listing flagged for review (Priority: {priority})', 'warning')
    else:
        flash(f'Failed to flag: {flag}', 'danger')

    return redirect(url_for('tourism.moderate_listing', id=id))
