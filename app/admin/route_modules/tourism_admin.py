"""
Tourism Admin Routes for AFCON360 - Production Ready.
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
# Tourism Admin Dashboard
# -----------------------------
@admin_bp.route("/tourism-admin", endpoint="tourism_admin_dashboard")
@login_required
@require_role("tourism_admin")
def tourism_admin_dashboard():
    """Tourism Admin Dashboard with comprehensive tourism content management."""
    try:
        # Import tourism modules
        from app.tourism.models import Attraction, Destination, TourismContent
        from app.tourism.services import TourismService
        
        # Get tourism statistics
        tourism_stats = TourismService.get_admin_dashboard_data()
        total_attractions = tourism_stats.get('total_attractions', 0)
        total_destinations = tourism_stats.get('total_destinations', 0)
        total_tourists = tourism_stats.get('total_tourists', 0)
        average_rating = tourism_stats.get('average_rating', 0)
        
        # Get recent attractions
        recent_attractions = Attraction.query.filter_by(
            is_deleted=False
        ).order_by(Attraction.created_at.desc()).limit(10).all()
        
        # Get pending content
        pending_content = TourismContent.query.filter_by(
            status='pending',
            is_deleted=False
        ).order_by(TourismContent.created_at.desc()).limit(5).all()
        
        return render_template(
            "admin/tourism_admin_dashboard.html",
            total_attractions=total_attractions,
            total_destinations=total_destinations,
            total_tourists=total_tourists,
            average_rating=average_rating,
            recent_attractions=recent_attractions,
            pending_content=pending_content,
        )
    except Exception as e:
        logger.error(f"Error loading tourism admin dashboard: {e}")
        flash("Error loading dashboard.", "danger")
        return redirect(url_for('admin.dashboard'))


# -----------------------------
# Attraction Management Routes
# -----------------------------
@admin_bp.route("/tourism-admin/attractions", endpoint="tourism_admin_attractions")
@login_required
@require_role("tourism_admin")
def tourism_admin_attractions():
    """List and manage all attractions."""
    try:
        from app.tourism.models import Attraction
        
        page = request.args.get('page', 1, type=int)
        status = request.args.get('status', 'all')
        category = request.args.get('category', 'all')
        
        query = Attraction.query.filter_by(is_deleted=False)
        
        if status != 'all':
            query = query.filter_by(status=status)
        
        if category != 'all':
            query = query.filter_by(category=category)
        
        attractions = query.order_by(Attraction.created_at.desc()).paginate(
            page=page, per_page=20, error_out=False
        )
        
        return render_template(
            "admin/tourism_admin/attractions.html",
            attractions=attractions,
            current_status=status,
            current_category=category
        )
    except Exception as e:
        logger.error(f"Error loading attractions: {e}")
        flash("Error loading attractions.", "danger")
        return redirect(url_for('admin.tourism_admin_dashboard'))


@admin_bp.route("/tourism-admin/attractions/create", endpoint="tourism_admin_create_attraction", methods=['GET', 'POST'])
@login_required
@require_role("tourism_admin")
def tourism_admin_create_attraction():
    """Create new attraction."""
    try:
        if request.method == 'POST':
            from app.tourism.models import Attraction
            from app.tourism.services import TourismService
            
            # Process attraction creation
            attraction_data = {
                'name': request.form.get('name'),
                'description': request.form.get('description'),
                'category': request.form.get('category'),
                'location': request.form.get('location'),
                'latitude': request.form.get('latitude', type=float),
                'longitude': request.form.get('longitude', type=float),
                'opening_hours': request.form.get('opening_hours'),
                'entry_fee': request.form.get('entry_fee', type=float),
                'contact_info': request.form.get('contact_info'),
                'created_by': current_user.id
            }
            
            attraction = TourismService.create_attraction(attraction_data)
            if attraction:
                flash("Attraction created successfully.", "success")
                return redirect(url_for('admin.tourism_admin_attractions'))
            else:
                flash("Error creating attraction.", "danger")
        
        return render_template("admin/tourism_admin/create_attraction.html")
    except Exception as e:
        logger.error(f"Error creating attraction: {e}")
        flash("Error creating attraction.", "danger")
        return redirect(url_for('admin.tourism_admin_attractions'))


@admin_bp.route("/tourism-admin/attractions/<int:attraction_id>/edit", endpoint="tourism_admin_edit_attraction", methods=['GET', 'POST'])
@login_required
@require_role("tourism_admin")
def tourism_admin_edit_attraction(attraction_id):
    """Edit existing attraction."""
    try:
        from app.tourism.models import Attraction
        from app.tourism.services import TourismService
        
        attraction = Attraction.query.get_or_404(attraction_id)
        
        if request.method == 'POST':
            # Process attraction update
            attraction_data = {
                'name': request.form.get('name'),
                'description': request.form.get('description'),
                'category': request.form.get('category'),
                'location': request.form.get('location'),
                'latitude': request.form.get('latitude', type=float),
                'longitude': request.form.get('longitude', type=float),
                'opening_hours': request.form.get('opening_hours'),
                'entry_fee': request.form.get('entry_fee', type=float),
                'contact_info': request.form.get('contact_info'),
                'status': request.form.get('status')
            }
            
            if TourismService.update_attraction(attraction_id, attraction_data):
                flash("Attraction updated successfully.", "success")
                return redirect(url_for('admin.tourism_admin_attractions'))
            else:
                flash("Error updating attraction.", "danger")
        
        return render_template("admin/tourism_admin/edit_attraction.html", attraction=attraction)
    except Exception as e:
        logger.error(f"Error editing attraction: {e}")
        flash("Error editing attraction.", "danger")
        return redirect(url_for('admin.tourism_admin_attractions'))


@admin_bp.route("/tourism-admin/attractions/<int:attraction_id>/delete", endpoint="tourism_admin_delete_attraction", methods=['POST'])
@login_required
@require_role("tourism_admin")
@require_fresh_user
def tourism_admin_delete_attraction(attraction_id):
    """Delete attraction."""
    try:
        from app.tourism.models import Attraction
        from app.tourism.services import TourismService
        
        attraction = Attraction.query.get_or_404(attraction_id)
        
        if TourismService.delete_attraction(attraction_id):
            flash(f"Attraction '{attraction.name}' deleted successfully.", "warning")
        else:
            flash("Error deleting attraction.", "danger")
        
        return redirect(url_for('admin.tourism_admin_attractions'))
    except Exception as e:
        logger.error(f"Error deleting attraction: {e}")
        flash("Error deleting attraction.", "danger")
        return redirect(url_for('admin.tourism_admin_attractions'))


# -----------------------------
# Destination Management Routes
# -----------------------------
@admin_bp.route("/tourism-admin/destinations", endpoint="tourism_admin_destinations")
@login_required
@require_role("tourism_admin")
def tourism_admin_destinations():
    """List and manage all destinations."""
    try:
        from app.tourism.models import Destination
        
        page = request.args.get('page', 1, type=int)
        status = request.args.get('status', 'all')
        region = request.args.get('region', 'all')
        
        query = Destination.query.filter_by(is_deleted=False)
        
        if status != 'all':
            query = query.filter_by(status=status)
        
        if region != 'all':
            query = query.filter_by(region=region)
        
        destinations = query.order_by(Destination.created_at.desc()).paginate(
            page=page, per_page=20, error_out=False
        )
        
        return render_template(
            "admin/tourism_admin/destinations.html",
            destinations=destinations,
            current_status=status,
            current_region=region
        )
    except Exception as e:
        logger.error(f"Error loading destinations: {e}")
        flash("Error loading destinations.", "danger")
        return redirect(url_for('admin.tourism_admin_dashboard'))


@admin_bp.route("/tourism-admin/destinations/create", endpoint="tourism_admin_create_destination", methods=['GET', 'POST'])
@login_required
@require_role("tourism_admin")
def tourism_admin_create_destination():
    """Create new destination."""
    try:
        if request.method == 'POST':
            from app.tourism.models import Destination
            from app.tourism.services import TourismService
            
            # Process destination creation
            destination_data = {
                'name': request.form.get('name'),
                'description': request.form.get('description'),
                'region': request.form.get('region'),
                'country': request.form.get('country'),
                'latitude': request.form.get('latitude', type=float),
                'longitude': request.form.get('longitude', type=float),
                'climate': request.form.get('climate'),
                'best_time_to_visit': request.form.get('best_time_to_visit'),
                'created_by': current_user.id
            }
            
            destination = TourismService.create_destination(destination_data)
            if destination:
                flash("Destination created successfully.", "success")
                return redirect(url_for('admin.tourism_admin_destinations'))
            else:
                flash("Error creating destination.", "danger")
        
        return render_template("admin/tourism_admin/create_destination.html")
    except Exception as e:
        logger.error(f"Error creating destination: {e}")
        flash("Error creating destination.", "danger")
        return redirect(url_for('admin.tourism_admin_destinations'))


@admin_bp.route("/tourism-admin/destinations/<int:destination_id>/edit", endpoint="tourism_admin_edit_destination", methods=['GET', 'POST'])
@login_required
@require_role("tourism_admin")
def tourism_admin_edit_destination(destination_id):
    """Edit existing destination."""
    try:
        from app.tourism.models import Destination
        from app.tourism.services import TourismService
        
        destination = Destination.query.get_or_404(destination_id)
        
        if request.method == 'POST':
            # Process destination update
            destination_data = {
                'name': request.form.get('name'),
                'description': request.form.get('description'),
                'region': request.form.get('region'),
                'country': request.form.get('country'),
                'latitude': request.form.get('latitude', type=float),
                'longitude': request.form.get('longitude', type=float),
                'climate': request.form.get('climate'),
                'best_time_to_visit': request.form.get('best_time_to_visit'),
                'status': request.form.get('status')
            }
            
            if TourismService.update_destination(destination_id, destination_data):
                flash("Destination updated successfully.", "success")
                return redirect(url_for('admin.tourism_admin_destinations'))
            else:
                flash("Error updating destination.", "danger")
        
        return render_template("admin/tourism_admin/edit_destination.html", destination=destination)
    except Exception as e:
        logger.error(f"Error editing destination: {e}")
        flash("Error editing destination.", "danger")
        return redirect(url_for('admin.tourism_admin_destinations'))


@admin_bp.route("/tourism-admin/destinations/<int:destination_id>/delete", endpoint="tourism_admin_delete_destination", methods=['POST'])
@login_required
@require_role("tourism_admin")
@require_fresh_user
def tourism_admin_delete_destination(destination_id):
    """Delete destination."""
    try:
        from app.tourism.models import Destination
        from app.tourism.services import TourismService
        
        destination = Destination.query.get_or_404(destination_id)
        
        if TourismService.delete_destination(destination_id):
            flash(f"Destination '{destination.name}' deleted successfully.", "warning")
        else:
            flash("Error deleting destination.", "danger")
        
        return redirect(url_for('admin.tourism_admin_destinations'))
    except Exception as e:
        logger.error(f"Error deleting destination: {e}")
        flash("Error deleting destination.", "danger")
        return redirect(url_for('admin.tourism_admin_destinations'))


# -----------------------------
# Content Management Routes
# -----------------------------
@admin_bp.route("/tourism-admin/content", endpoint="tourism_admin_content")
@login_required
@require_role("tourism_admin")
def tourism_admin_content():
    """Manage tourism content and articles."""
    try:
        from app.tourism.models import TourismContent
        
        page = request.args.get('page', 1, type=int)
        status = request.args.get('status', 'all')
        content_type = request.args.get('type', 'all')
        
        query = TourismContent.query.filter_by(is_deleted=False)
        
        if status != 'all':
            query = query.filter_by(status=status)
        
        if content_type != 'all':
            query = query.filter_by(content_type=content_type)
        
        content = query.order_by(
            TourismContent.created_at.desc()
        ).paginate(page=page, per_page=20, error_out=False)
        
        return render_template(
            "admin/tourism_admin/content.html",
            content=content,
            current_status=status,
            current_type=content_type
        )
    except Exception as e:
        logger.error(f"Error loading content: {e}")
        flash("Error loading content.", "danger")
        return redirect(url_for('admin.tourism_admin_dashboard'))


@admin_bp.route("/tourism-admin/content/<int:content_id>/approve", endpoint="tourism_admin_approve_content", methods=['POST'])
@login_required
@require_role("tourism_admin")
def tourism_admin_approve_content(content_id):
    """Approve tourism content."""
    try:
        from app.tourism.models import TourismContent
        from app.tourism.services import TourismService
        
        content = TourismContent.query.get_or_404(content_id)
        
        if TourismService.approve_content(content_id, approved_by=current_user.id):
            flash(f"Content '{content.title}' approved successfully.", "success")
        else:
            flash("Error approving content.", "danger")
        
        return redirect(url_for('admin.tourism_admin_content'))
    except Exception as e:
        logger.error(f"Error approving content: {e}")
        flash("Error approving content.", "danger")
        return redirect(url_for('admin.tourism_admin_content'))


@admin_bp.route("/tourism-admin/content/<int:content_id>/reject", endpoint="tourism_admin_reject_content", methods=['POST'])
@login_required
@require_role("tourism_admin")
def tourism_admin_reject_content(content_id):
    """Reject tourism content."""
    try:
        from app.tourism.models import TourismContent
        from app.tourism.services import TourismService
        
        content = TourismContent.query.get_or_404(content_id)
        reason = request.form.get('reason', 'No reason provided')
        
        if TourismService.reject_content(content_id, reason, rejected_by=current_user.id):
            flash(f"Content '{content.title}' rejected.", "warning")
        else:
            flash("Error rejecting content.", "danger")
        
        return redirect(url_for('admin.tourism_admin_content'))
    except Exception as e:
        logger.error(f"Error rejecting content: {e}")
        flash("Error rejecting content.", "danger")
        return redirect(url_for('admin.tourism_admin_content'))


# -----------------------------
# Analytics and Settings
# -----------------------------
@admin_bp.route("/tourism-admin/analytics", endpoint="tourism_admin_analytics")
@login_required
@require_role("tourism_admin")
def tourism_admin_analytics():
    """Tourism analytics and visitor data."""
    try:
        from app.tourism.services import TourismService
        
        # Get analytics data
        analytics = TourismService.get_analytics_data()
        
        return render_template(
            "admin/tourism_admin/analytics.html",
            analytics=analytics
        )
    except Exception as e:
        logger.error(f"Error loading analytics: {e}")
        flash("Error loading analytics.", "danger")
        return redirect(url_for('admin.tourism_admin_dashboard'))


@admin_bp.route("/tourism-admin/settings", endpoint="tourism_admin_settings")
@login_required
@require_role("tourism_admin")
def tourism_admin_settings():
    """Tourism admin settings."""
    try:
        return render_template("admin/tourism_admin/settings.html")
    except Exception as e:
        from app.utils.error_handler import log_error_to_audit
        from flask_login import current_user
        log_error_to_audit(
            user_id=current_user.id if current_user.is_authenticated else None,
            error_type="SETTINGS_LOAD_ERROR",
            error_message=str(e),
            context={"module": "tourism_admin", "template": "settings.html"}
        )
        flash("Unable to load settings. Please try again later.", "warning")
        return redirect(url_for('admin.tourism_admin_dashboard'))
