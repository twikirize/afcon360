"""
Accommodation Admin Routes for AFCON360 - Production Ready.
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
# Accommodation Admin Dashboard
# -----------------------------
@admin_bp.route("/accommodation-admin", endpoint="accommodation_admin_dashboard")
@login_required
@require_role("accommodation_admin")
def accommodation_admin_dashboard():
    """Accommodation Admin Dashboard with comprehensive property management."""
    try:
        # Import accommodation modules
        from app.accommodation.models import Property, Booking, Review
        from app.accommodation.services import AccommodationService
        
        # Get accommodation statistics
        accommodation_stats = AccommodationService.get_admin_dashboard_data()
        total_properties = accommodation_stats.get('total_properties', 0)
        total_bookings = accommodation_stats.get('total_bookings', 0)
        active_hosts = accommodation_stats.get('active_hosts', 0)
        average_rating = accommodation_stats.get('average_rating', 0)
        
        # Get recent properties
        recent_properties = Property.query.filter_by(
            is_deleted=False
        ).order_by(Property.created_at.desc()).limit(10).all()
        
        # Get pending property verifications
        pending_properties = Property.query.filter_by(
            verification_status='pending',
            is_deleted=False
        ).order_by(Property.created_at.desc()).limit(5).all()
        
        return render_template(
            "admin/accommodation_admin_dashboard.html",
            total_properties=total_properties,
            total_bookings=total_bookings,
            active_hosts=active_hosts,
            average_rating=average_rating,
            recent_properties=recent_properties,
            pending_properties=pending_properties,
        )
    except Exception as e:
        logger.error(f"Error loading accommodation admin dashboard: {e}")
        flash("Error loading dashboard.", "danger")
        return redirect(url_for('admin.dashboard'))


# -----------------------------
# Property Management Routes
# -----------------------------
@admin_bp.route("/accommodation-admin/properties", endpoint="accommodation_admin_properties")
@login_required
@require_role("accommodation_admin")
def accommodation_admin_properties():
    """List and manage all properties."""
    try:
        from app.accommodation.models import Property
        
        page = request.args.get('page', 1, type=int)
        status = request.args.get('status', 'all')
        verification_status = request.args.get('verification', 'all')
        
        query = Property.query.filter_by(is_deleted=False)
        
        if status != 'all':
            query = query.filter_by(status=status)
        
        if verification_status != 'all':
            query = query.filter_by(verification_status=verification_status)
        
        properties = query.order_by(Property.created_at.desc()).paginate(
            page=page, per_page=20, error_out=False
        )
        
        return render_template(
            "admin/accommodation_admin/properties.html",
            properties=properties,
            current_status=status,
            current_verification=verification_status
        )
    except Exception as e:
        logger.error(f"Error loading properties: {e}")
        flash("Error loading properties.", "danger")
        return redirect(url_for('admin.accommodation_admin_dashboard'))


@admin_bp.route("/accommodation-admin/properties/<int:property_id>/verify", endpoint="accommodation_admin_verify_property", methods=['POST'])
@login_required
@require_role("accommodation_admin")
def accommodation_admin_verify_property(property_id):
    """Verify property."""
    try:
        from app.accommodation.models import Property
        from app.accommodation.services import AccommodationService
        
        property = Property.query.get_or_404(property_id)
        
        if AccommodationService.verify_property(property_id, verified_by=current_user.id):
            flash(f"Property '{property.title}' verified successfully.", "success")
        else:
            flash("Error verifying property.", "danger")
        
        return redirect(url_for('admin.accommodation_admin_properties'))
    except Exception as e:
        logger.error(f"Error verifying property: {e}")
        flash("Error verifying property.", "danger")
        return redirect(url_for('admin.accommodation_admin_properties'))


@admin_bp.route("/accommodation-admin/properties/<int:property_id>/reject", endpoint="accommodation_admin_reject_property", methods=['POST'])
@login_required
@require_role("accommodation_admin")
def accommodation_admin_reject_property(property_id):
    """Reject property verification."""
    try:
        from app.accommodation.models import Property
        from app.accommodation.services import AccommodationService
        
        property = Property.query.get_or_404(property_id)
        reason = request.form.get('reason', 'No reason provided')
        
        if AccommodationService.reject_property(property_id, reason, rejected_by=current_user.id):
            flash(f"Property '{property.title}' verification rejected.", "warning")
        else:
            flash("Error rejecting property.", "danger")
        
        return redirect(url_for('admin.accommodation_admin_properties'))
    except Exception as e:
        logger.error(f"Error rejecting property: {e}")
        flash("Error rejecting property.", "danger")
        return redirect(url_for('admin.accommodation_admin_properties'))


@admin_bp.route("/accommodation-admin/properties/<int:property_id>/delete", endpoint="accommodation_admin_delete_property", methods=['POST'])
@login_required
@require_role("accommodation_admin")
@require_fresh_user
def accommodation_admin_delete_property(property_id):
    """Delete property."""
    try:
        from app.accommodation.models import Property
        from app.accommodation.services import AccommodationService
        
        property = Property.query.get_or_404(property_id)
        
        if AccommodationService.delete_property(property_id):
            flash(f"Property '{property.title}' deleted successfully.", "warning")
        else:
            flash("Error deleting property.", "danger")
        
        return redirect(url_for('admin.accommodation_admin_properties'))
    except Exception as e:
        logger.error(f"Error deleting property: {e}")
        flash("Error deleting property.", "danger")
        return redirect(url_for('admin.accommodation_admin_properties'))


# -----------------------------
# Booking Management Routes
# -----------------------------
@admin_bp.route("/accommodation-admin/bookings", endpoint="accommodation_admin_bookings")
@login_required
@require_role("accommodation_admin")
def accommodation_admin_bookings():
    """Manage accommodation bookings."""
    try:
        from app.accommodation.models import Booking
        
        page = request.args.get('page', 1, type=int)
        status = request.args.get('status', 'all')
        
        query = Booking.query.filter_by(is_deleted=False)
        
        if status != 'all':
            query = query.filter_by(status=status)
        
        bookings = query.order_by(
            Booking.created_at.desc()
        ).paginate(page=page, per_page=20, error_out=False)
        
        return render_template(
            "admin/accommodation_admin/bookings.html",
            bookings=bookings,
            current_status=status
        )
    except Exception as e:
        logger.error(f"Error loading bookings: {e}")
        flash("Error loading bookings.", "danger")
        return redirect(url_for('admin.accommodation_admin_dashboard'))


@admin_bp.route("/accommodation-admin/bookings/<int:booking_id>/approve", endpoint="accommodation_admin_approve_booking", methods=['POST'])
@login_required
@require_role("accommodation_admin")
def accommodation_admin_approve_booking(booking_id):
    """Approve accommodation booking."""
    try:
        from app.accommodation.models import Booking
        from app.accommodation.services import AccommodationService
        
        booking = Booking.query.get_or_404(booking_id)
        
        if AccommodationService.approve_booking(booking_id, approved_by=current_user.id):
            flash(f"Booking for {booking.user.username} approved.", "success")
        else:
            flash("Error approving booking.", "danger")
        
        return redirect(url_for('admin.accommodation_admin_bookings'))
    except Exception as e:
        logger.error(f"Error approving booking: {e}")
        flash("Error approving booking.", "danger")
        return redirect(url_for('admin.accommodation_admin_bookings'))


@admin_bp.route("/accommodation-admin/bookings/<int:booking_id>/reject", endpoint="accommodation_admin_reject_booking", methods=['POST'])
@login_required
@require_role("accommodation_admin")
def accommodation_admin_reject_booking(booking_id):
    """Reject accommodation booking."""
    try:
        from app.accommodation.models import Booking
        from app.accommodation.services import AccommodationService
        
        booking = Booking.query.get_or_404(booking_id)
        reason = request.form.get('reason', 'No reason provided')
        
        if AccommodationService.reject_booking(booking_id, reason, rejected_by=current_user.id):
            flash(f"Booking for {booking.user.username} rejected.", "warning")
        else:
            flash("Error rejecting booking.", "danger")
        
        return redirect(url_for('admin.accommodation_admin_bookings'))
    except Exception as e:
        logger.error(f"Error rejecting booking: {e}")
        flash("Error rejecting booking.", "danger")
        return redirect(url_for('admin.accommodation_admin_bookings'))


# -----------------------------
# Review Management Routes
# -----------------------------
@admin_bp.route("/accommodation-admin/reviews", endpoint="accommodation_admin_reviews")
@login_required
@require_role("accommodation_admin")
def accommodation_admin_reviews():
    """Moderate property reviews and ratings."""
    try:
        from app.accommodation.models import Review
        
        page = request.args.get('page', 1, type=int)
        status = request.args.get('status', 'all')
        
        query = Review.query.filter_by(is_deleted=False)
        
        if status != 'all':
            query = query.filter_by(status=status)
        
        reviews = query.order_by(
            Review.created_at.desc()
        ).paginate(page=page, per_page=20, error_out=False)
        
        return render_template(
            "admin/accommodation_admin/reviews.html",
            reviews=reviews,
            current_status=status
        )
    except Exception as e:
        logger.error(f"Error loading reviews: {e}")
        flash("Error loading reviews.", "danger")
        return redirect(url_for('admin.accommodation_admin_dashboard'))


@admin_bp.route("/accommodation-admin/reviews/<int:review_id>/approve", endpoint="accommodation_admin_approve_review", methods=['POST'])
@login_required
@require_role("accommodation_admin")
def accommodation_admin_approve_review(review_id):
    """Approve property review."""
    try:
        from app.accommodation.models import Review
        from app.accommodation.services import AccommodationService
        
        review = Review.query.get_or_404(review_id)
        
        if AccommodationService.approve_review(review_id, approved_by=current_user.id):
            flash(f"Review by {review.user.username} approved.", "success")
        else:
            flash("Error approving review.", "danger")
        
        return redirect(url_for('admin.accommodation_admin_reviews'))
    except Exception as e:
        logger.error(f"Error approving review: {e}")
        flash("Error approving review.", "danger")
        return redirect(url_for('admin.accommodation_admin_reviews'))


@admin_bp.route("/accommodation-admin/reviews/<int:review_id>/reject", endpoint="accommodation_admin_reject_review", methods=['POST'])
@login_required
@require_role("accommodation_admin")
def accommodation_admin_reject_review(review_id):
    """Reject property review."""
    try:
        from app.accommodation.models import Review
        from app.accommodation.services import AccommodationService
        
        review = Review.query.get_or_404(review_id)
        reason = request.form.get('reason', 'No reason provided')
        
        if AccommodationService.reject_review(review_id, reason, rejected_by=current_user.id):
            flash(f"Review by {review.user.username} rejected.", "warning")
        else:
            flash("Error rejecting review.", "danger")
        
        return redirect(url_for('admin.accommodation_admin_reviews'))
    except Exception as e:
        logger.error(f"Error rejecting review: {e}")
        flash("Error rejecting review.", "danger")
        return redirect(url_for('admin.accommodation_admin_reviews'))


# -----------------------------
# Analytics and Settings
# -----------------------------
@admin_bp.route("/accommodation-admin/analytics", endpoint="accommodation_admin_analytics")
@login_required
@require_role("accommodation_admin")
def accommodation_admin_analytics():
    """Accommodation analytics and performance data."""
    try:
        from app.accommodation.services import AccommodationService
        
        # Get analytics data
        analytics = AccommodationService.get_analytics_data()
        
        return render_template(
            "admin/accommodation_admin/analytics.html",
            analytics=analytics
        )
    except Exception as e:
        logger.error(f"Error loading analytics: {e}")
        flash("Error loading analytics.", "danger")
        return redirect(url_for('admin.accommodation_admin_dashboard'))


@admin_bp.route("/accommodation-admin/settings", endpoint="accommodation_admin_settings")
@login_required
@require_role("accommodation_admin")
def accommodation_admin_settings():
    """Accommodation admin settings."""
    try:
        return render_template("admin/accommodation_admin/settings.html")
    except Exception as e:
        from app.utils.error_handler import log_error_to_audit
        from flask_login import current_user
        log_error_to_audit(
            user_id=current_user.id if current_user.is_authenticated else None,
            error_type="SETTINGS_LOAD_ERROR",
            error_message=str(e),
            context={"module": "accommodation_admin", "template": "settings.html"}
        )
        flash("Unable to load settings. Please try again later.", "warning")
        return redirect(url_for('admin.accommodation_admin_dashboard'))


@admin_bp.route("/accommodation-admin/pricing", endpoint="accommodation_admin_pricing")
@login_required
@require_role("accommodation_admin")
def accommodation_admin_pricing():
    """Pricing configuration and commission structures."""
    try:
        from app.accommodation.models import PricingRule
        
        pricing_rules = PricingRule.query.filter_by(
            is_deleted=False
        ).order_by(PricingRule.created_at.desc()).all()
        
        return render_template(
            "admin/accommodation_admin/pricing.html",
            pricing_rules=pricing_rules
        )
    except Exception as e:
        logger.error(f"Error loading pricing: {e}")
        flash("Error loading pricing.", "danger")
        return redirect(url_for('admin.accommodation_admin_dashboard'))


@admin_bp.route("/accommodation-admin/verification", endpoint="accommodation_admin_verification")
@login_required
@require_role("accommodation_admin")
def accommodation_admin_verification():
    """Property verification and trust scoring."""
    try:
        from app.accommodation.models import Property
        
        # Get pending verifications
        pending_properties = Property.query.filter_by(
            verification_status='pending',
            is_deleted=False
        ).order_by(Property.created_at.desc()).all()
        
        # Get verification statistics
        total_pending = Property.query.filter_by(verification_status='pending').count()
        total_verified = Property.query.filter_by(verification_status='verified').count()
        total_rejected = Property.query.filter_by(verification_status='rejected').count()
        
        return render_template(
            "admin/accommodation_admin/verification.html",
            pending_properties=pending_properties,
            total_pending=total_pending,
            total_verified=total_verified,
            total_rejected=total_rejected
        )
    except Exception as e:
        logger.error(f"Error loading verification: {e}")
        flash("Error loading verification.", "danger")
        return redirect(url_for('admin.accommodation_admin_dashboard'))
