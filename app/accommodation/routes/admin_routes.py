# app/accommodation/routes/admin_routes.py
"""
Admin routes for accommodation module oversight
To be implemented in Phase 5
"""

from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from app.auth.policy import can
from app.auth.decorators import require_moderator

admin_bp = Blueprint('admin', __name__)


@admin_bp.route("/dashboard", endpoint="dashboard")
@login_required
def dashboard():
    """
    Admin dashboard for accommodation module
    Requires accommodation.manage permission
    """
    if not can(current_user, "accommodation.manage"):
        flash("Insufficient permissions", "danger")
        return redirect(url_for('index'))

    # TODO: Show platform-wide stats
    return render_template("accommodation/admin/dashboard.html")


@admin_bp.route("/listings", endpoint="listings")
@login_required
def listings():
    """
    Manage all property listings
    """
    if not can(current_user, "accommodation.manage"):
        flash("Insufficient permissions", "danger")
        return redirect(url_for('index'))

    # TODO: List all properties with moderation options
    return render_template("accommodation/admin/listings.html")


@admin_bp.route("/hosts", endpoint="hosts")
@login_required
def hosts():
    """
    Manage hosts (verify, suspend)
    """
    if not can(current_user, "accommodation.verify_host"):
        flash("Insufficient permissions", "danger")
        return redirect(url_for('index'))

    # TODO: List hosts pending verification
    return render_template("accommodation/admin/hosts.html")


from app.extensions import db
from app.accommodation.models.property import Property, AccommodationPropertyStatus
from app.accommodation.models.booking import AccommodationBooking
from app.accommodation.models.review import Review, AccommodationReviewStatus
from datetime import datetime, timezone


# ============================================================================
# MODERATOR ROUTES
# ============================================================================

@admin_bp.route("/moderate")
@login_required
@require_moderator
def moderate():
    """Show accommodation items needing moderation (for moderators only)"""
    
    pending_properties = Property.query.filter_by(status=AccommodationPropertyStatus.PENDING_REVIEW).all()
    pending_bookings = AccommodationBooking.query.filter_by(status='pending').all()
    pending_reviews = Review.query.filter_by(status=AccommodationReviewStatus.PENDING).all()
    
    return render_template('accommodation/moderate.html', properties=pending_properties, bookings=pending_bookings, reviews=pending_reviews)


@admin_bp.route("/moderate/property/<int:id>")
@login_required
@require_moderator
def moderate_property(id):
    """Show single property for moderation review"""
    
    property = Property.query.get_or_404(id)
    return render_template('accommodation/moderate_property.html', property=property)


@admin_bp.route("/moderate/booking/<int:id>")
@login_required
@require_moderator
def moderate_booking(id):
    """Show single booking for moderation review"""
    
    booking = AccommodationBooking.query.get_or_404(id)
    return render_template('accommodation/moderate_booking.html', booking=booking)


@admin_bp.route("/moderate/review/<int:id>")
@login_required
@require_moderator
def moderate_review(id):
    """Show single review for moderation review"""
    
    review = Review.query.get_or_404(id)
    return render_template('accommodation/moderate_review.html', review=review)


@admin_bp.route("/moderate/<entity_type>/<int:id>/<action>", methods=['POST'])
@login_required
@require_moderator
def moderate_action(entity_type, id, action):
    """Approve, reject, or flag accommodation items"""

    if entity_type == 'property':
        item = Property.query.get_or_404(id)
        redirect_url = url_for('accommodation.admin.moderate_property', id=id)
    elif entity_type == 'booking':
        item = AccommodationBooking.query.get_or_404(id)
        redirect_url = url_for('accommodation.admin.moderate_booking', id=id)
    elif entity_type == 'review':
        item = Review.query.get_or_404(id)
        redirect_url = url_for('accommodation.admin.moderate_review', id=id)
    else:
        flash('Invalid entity type.', 'danger')
        return redirect(url_for('accommodation.admin.moderate'))

    if action == 'approve':
        if entity_type == 'property':
            item.status = AccommodationPropertyStatus.ACTIVE
            item.is_verified = True
            item.verified_at = datetime.now(timezone.utc)
            item.verified_by = current_user.id
        elif entity_type == 'booking':
            item.status = 'confirmed'
        elif entity_type == 'review':
            item.status = AccommodationReviewStatus.APPROVED
            item.is_published = True
            item.published_at = datetime.now(timezone.utc)
            item.moderated_by = current_user.id
            item.moderated_at = datetime.now(timezone.utc)

        db.session.commit()
        flash(f'{entity_type.capitalize()} approved successfully.', 'success')

    elif action == 'reject':
        reason = request.form.get('reason', '').strip()
        if not reason:
            flash('Rejection reason is required.', 'warning')
            return redirect(redirect_url)

        if entity_type == 'property':
            item.status = AccommodationPropertyStatus.SUSPENDED
            item.verification_notes = reason
        elif entity_type == 'booking':
            item.status = 'cancelled'
            item.cancellation_reason = reason
        elif entity_type == 'review':
            item.status = AccommodationReviewStatus.REJECTED
            item.moderation_reason = reason
            item.moderated_by = current_user.id
            item.moderated_at = datetime.now(timezone.utc)

        db.session.commit()
        flash(f'{entity_type.capitalize()} rejected successfully.', 'success')

    elif action == 'flag':
        reason = request.form.get('reason', '').strip()
        priority = request.form.get('priority', 'normal').strip()
        if not reason:
            flash('Flag reason is required.', 'warning')
            return redirect(redirect_url)

        from app.admin.services import create_flag
        entity_type_map = {
            'property': 'accommodation_property',
            'booking': 'accommodation_booking',
            'review': 'accommodation_review'
        }

        ok, flag = create_flag(
            current_user,
            entity_type_map.get(entity_type, entity_type),
            id,
            reason,
            priority
        )

        if ok:
            flash(f'{entity_type.capitalize()} flagged for review (Priority: {priority})', 'warning')
        else:
            flash(f'Failed to flag: {flag}', 'danger')

    return redirect(redirect_url)


@admin_bp.route("/moderate/property/<int:id>/flag", methods=['POST'])
@login_required
@require_moderator
def flag_property(id):
    """Flag a property for moderation review."""
    property = Property.query.get_or_404(id)
    reason = request.form.get('reason', '').strip()
    priority = request.form.get('priority', 'normal').strip()

    if not reason:
        flash('Flag reason is required.', 'warning')
        return redirect(url_for('accommodation.admin.moderate_property', id=id))

    from app.admin.services import create_flag
    ok, flag = create_flag(current_user, 'accommodation_property', id, reason, priority)

    if ok:
        flash(f'Property flagged for review (Priority: {priority})', 'warning')
    else:
        flash(f'Failed to flag: {flag}', 'danger')

    return redirect(url_for('accommodation.admin.moderate_property', id=id))


@admin_bp.route("/moderate/review/<int:id>/flag", methods=['POST'])
@login_required
@require_moderator
def flag_review(id):
    """Flag a review for moderation review."""
    review = Review.query.get_or_404(id)
    reason = request.form.get('reason', '').strip()
    priority = request.form.get('priority', 'normal').strip()

    if not reason:
        flash('Flag reason is required.', 'warning')
        return redirect(url_for('accommodation.admin.moderate_review', id=id))

    from app.admin.services import create_flag
    ok, flag = create_flag(current_user, 'accommodation_review', id, reason, priority)

    if ok:
        flash(f'Review flagged for review (Priority: {priority})', 'warning')
    else:
        flash(f'Failed to flag: {flag}', 'danger')

    return redirect(url_for('accommodation.admin.moderate_review', id=id))
