"""
Event Manager Routes for AFCON360 - Production Ready.
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
# Event Manager Dashboard
# -----------------------------
@admin_bp.route("/event-manager", endpoint="event_manager_dashboard")
@login_required
@require_role("event_manager")
def event_manager_dashboard():
    """Event Manager Dashboard with comprehensive event management."""
    try:
        # Import event modules
        from app.events.models import Event
        from app.events.services import EventService
        
        # Get event statistics
        event_stats = EventService.get_admin_dashboard_data()
        total_events = event_stats.get('total_events', 0)
        active_events = event_stats.get('active_events', 0)
        pending_events = event_stats.get('pending_events', 0)
        total_registrations = event_stats.get('total_registrations', 0)
        
        # Get recent events
        recent_events = Event.query.filter_by(
            is_deleted=False
        ).order_by(Event.created_at.desc()).limit(10).all()
        
        # Get pending events for review
        pending_events_list = Event.query.filter_by(
            status='pending',
            is_deleted=False
        ).order_by(Event.created_at.desc()).limit(5).all()
        
        return render_template(
            "admin/event_manager_dashboard.html",
            total_events=total_events,
            active_events=active_events,
            pending_events=pending_events,
            total_registrations=total_registrations,
            recent_events=recent_events,
            pending_events_list=pending_events_list,
        )
    except Exception as e:
        logger.error(f"Error loading event manager dashboard: {e}")
        flash("Error loading dashboard.", "danger")
        return redirect(url_for('admin.dashboard'))


# -----------------------------
# Event Management Routes
# -----------------------------
@admin_bp.route("/event-manager/events", endpoint="event_manager_events")
@login_required
@require_role("event_manager")
def event_manager_events():
    """List and manage all events."""
    try:
        from app.events.models import Event
        
        page = request.args.get('page', 1, type=int)
        status = request.args.get('status', 'all')
        
        query = Event.query.filter_by(is_deleted=False)
        
        if status != 'all':
            query = query.filter_by(status=status)
        
        events = query.order_by(Event.created_at.desc()).paginate(
            page=page, per_page=20, error_out=False
        )
        
        return render_template(
            "admin/event_manager/events.html",
            events=events,
            current_status=status
        )
    except Exception as e:
        logger.error(f"Error loading events: {e}")
        flash("Error loading events.", "danger")
        return redirect(url_for('admin.event_manager_dashboard'))


@admin_bp.route("/event-manager/events/create", endpoint="event_manager_create_event", methods=['GET', 'POST'])
@login_required
@require_role("event_manager")
def event_manager_create_event():
    """Create new event."""
    try:
        if request.method == 'POST':
            from app.events.models import Event
            from app.events.services import EventService
            
            # Process event creation
            event_data = {
                'title': request.form.get('title'),
                'description': request.form.get('description'),
                'start_date': request.form.get('start_date'),
                'end_date': request.form.get('end_date'),
                'location': request.form.get('location'),
                'capacity': request.form.get('capacity', type=int),
                'price': request.form.get('price', type=float),
                'category': request.form.get('category'),
                'created_by': current_user.id
            }
            
            event = EventService.create_event(event_data)
            if event:
                flash("Event created successfully.", "success")
                return redirect(url_for('admin.event_manager_events'))
            else:
                flash("Error creating event.", "danger")
        
        return render_template("admin/event_manager/create_event.html")
    except Exception as e:
        logger.error(f"Error creating event: {e}")
        flash("Error creating event.", "danger")
        return redirect(url_for('admin.event_manager_events'))


@admin_bp.route("/event-manager/events/<int:event_id>/edit", endpoint="event_manager_edit_event", methods=['GET', 'POST'])
@login_required
@require_role("event_manager")
def event_manager_edit_event(event_id):
    """Edit existing event."""
    try:
        from app.events.models import Event
        from app.events.services import EventService
        
        event = Event.query.get_or_404(event_id)
        
        if request.method == 'POST':
            # Process event update
            event_data = {
                'title': request.form.get('title'),
                'description': request.form.get('description'),
                'start_date': request.form.get('start_date'),
                'end_date': request.form.get('end_date'),
                'location': request.form.get('location'),
                'capacity': request.form.get('capacity', type=int),
                'price': request.form.get('price', type=float),
                'category': request.form.get('category')
            }
            
            if EventService.update_event(event_id, event_data):
                flash("Event updated successfully.", "success")
                return redirect(url_for('admin.event_manager_events'))
            else:
                flash("Error updating event.", "danger")
        
        return render_template("admin/event_manager/edit_event.html", event=event)
    except Exception as e:
        logger.error(f"Error editing event: {e}")
        flash("Error editing event.", "danger")
        return redirect(url_for('admin.event_manager_events'))


@admin_bp.route("/event-manager/events/<int:event_id>/delete", endpoint="event_manager_delete_event", methods=['POST'])
@login_required
@require_role("event_manager")
@require_fresh_user
def event_manager_delete_event(event_id):
    """Delete event."""
    try:
        from app.events.models import Event
        from app.events.services import EventService
        
        event = Event.query.get_or_404(event_id)
        
        if EventService.delete_event(event_id):
            flash(f"Event '{event.title}' deleted successfully.", "warning")
        else:
            flash("Error deleting event.", "danger")
        
        return redirect(url_for('admin.event_manager_events'))
    except Exception as e:
        logger.error(f"Error deleting event: {e}")
        flash("Error deleting event.", "danger")
        return redirect(url_for('admin.event_manager_events'))


# -----------------------------
# Registration Management
# -----------------------------
@admin_bp.route("/event-manager/registrations", endpoint="event_manager_registrations")
@login_required
@require_role("event_manager")
def event_manager_registrations():
    """Manage event registrations."""
    try:
        from app.events.models import EventRegistration
        
        page = request.args.get('page', 1, type=int)
        status = request.args.get('status', 'all')
        
        query = EventRegistration.query
        
        if status != 'all':
            query = query.filter_by(status=status)
        
        registrations = query.order_by(
            EventRegistration.created_at.desc()
        ).paginate(page=page, per_page=20, error_out=False)
        
        return render_template(
            "admin/event_manager/registrations.html",
            registrations=registrations,
            current_status=status
        )
    except Exception as e:
        logger.error(f"Error loading registrations: {e}")
        flash("Error loading registrations.", "danger")
        return redirect(url_for('admin.event_manager_dashboard'))


@admin_bp.route("/event-manager/registrations/<int:reg_id>/approve", endpoint="event_manager_approve_registration", methods=['POST'])
@login_required
@require_role("event_manager")
def event_manager_approve_registration(reg_id):
    """Approve event registration."""
    try:
        from app.events.models import EventRegistration
        from app.events.services import EventService
        
        registration = EventRegistration.query.get_or_404(reg_id)
        
        if EventService.approve_registration(reg_id):
            flash(f"Registration for {registration.user.username} approved.", "success")
        else:
            flash("Error approving registration.", "danger")
        
        return redirect(url_for('admin.event_manager_registrations'))
    except Exception as e:
        logger.error(f"Error approving registration: {e}")
        flash("Error approving registration.", "danger")
        return redirect(url_for('admin.event_manager_registrations'))


@admin_bp.route("/event-manager/registrations/<int:reg_id>/reject", endpoint="event_manager_reject_registration", methods=['POST'])
@login_required
@require_role("event_manager")
def event_manager_reject_registration(reg_id):
    """Reject event registration."""
    try:
        from app.events.models import EventRegistration
        from app.events.services import EventService
        
        registration = EventRegistration.query.get_or_404(reg_id)
        reason = request.form.get('reason', 'No reason provided')
        
        if EventService.reject_registration(reg_id, reason):
            flash(f"Registration for {registration.user.username} rejected.", "warning")
        else:
            flash("Error rejecting registration.", "danger")
        
        return redirect(url_for('admin.event_manager_registrations'))
    except Exception as e:
        logger.error(f"Error rejecting registration: {e}")
        flash("Error rejecting registration.", "danger")
        return redirect(url_for('admin.event_manager_registrations'))


# -----------------------------
# Analytics and Reports
# -----------------------------
@admin_bp.route("/event-manager/analytics", endpoint="event_manager_analytics")
@login_required
@require_role("event_manager")
def event_manager_analytics():
    """Event analytics and reports."""
    try:
        from app.events.services import EventService
        
        # Get analytics data
        analytics = EventService.get_analytics_data()
        
        return render_template(
            "admin/event_manager/analytics.html",
            analytics=analytics
        )
    except Exception as e:
        logger.error(f"Error loading analytics: {e}")
        flash("Error loading analytics.", "danger")
        return redirect(url_for('admin.event_manager_dashboard'))


# -----------------------------
# Settings
# -----------------------------
@admin_bp.route("/event-manager/settings", endpoint="event_manager_settings")
@login_required
@require_role("event_manager")
def event_manager_settings():
    """Event manager settings."""
    try:
        return render_template("admin/event_manager/settings.html")
    except Exception as e:
        from app.utils.error_handler import log_error_to_audit
        from flask_login import current_user
        log_error_to_audit(
            user_id=current_user.id if current_user.is_authenticated else None,
            error_type="SETTINGS_LOAD_ERROR",
            error_message=str(e),
            context={"module": "event_manager", "template": "settings.html"}
        )
        flash("Unable to load settings. Please try again later.", "warning")
        return redirect(url_for('admin.event_manager_dashboard'))
