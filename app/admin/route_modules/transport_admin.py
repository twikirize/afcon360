"""
Transport Admin Routes for AFCON360 - Production Ready.
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
# Transport Admin Dashboard
# -----------------------------
@admin_bp.route("/transport-admin", endpoint="transport_admin_dashboard")
@login_required
@require_role("transport_admin")
def transport_admin_dashboard():
    """Transport Admin Dashboard with comprehensive transport management."""
    try:
        # Import transport modules
        from app.transport.models import Vehicle, Driver, TransportBooking
        from app.transport.services import TransportService
        
        # Get transport statistics
        transport_stats = TransportService.get_admin_dashboard_data()
        total_vehicles = transport_stats.get('total_vehicles', 0)
        total_drivers = transport_stats.get('total_drivers', 0)
        total_bookings = transport_stats.get('total_bookings', 0)
        total_revenue = transport_stats.get('total_revenue', 0)
        
        # Get recent vehicles
        recent_vehicles = Vehicle.query.filter_by(
            is_deleted=False
        ).order_by(Vehicle.created_at.desc()).limit(10).all()
        
        # Get pending driver verifications
        pending_drivers = Driver.query.filter_by(
            verification_status='pending',
            is_deleted=False
        ).order_by(Driver.created_at.desc()).limit(5).all()
        
        return render_template(
            "admin/transport_admin_dashboard.html",
            total_vehicles=total_vehicles,
            total_drivers=total_drivers,
            total_bookings=total_bookings,
            total_revenue=total_revenue,
            recent_vehicles=recent_vehicles,
            pending_drivers=pending_drivers,
        )
    except Exception as e:
        logger.error(f"Error loading transport admin dashboard: {e}")
        flash("Error loading dashboard.", "danger")
        return redirect(url_for('admin.dashboard'))


# -----------------------------
# Vehicle Management Routes
# -----------------------------
@admin_bp.route("/transport-admin/vehicles", endpoint="transport_admin_vehicles")
@login_required
@require_role("transport_admin")
def transport_admin_vehicles():
    """List and manage all vehicles."""
    try:
        from app.transport.models import Vehicle
        
        page = request.args.get('page', 1, type=int)
        status = request.args.get('status', 'all')
        
        query = Vehicle.query.filter_by(is_deleted=False)
        
        if status != 'all':
            query = query.filter_by(status=status)
        
        vehicles = query.order_by(Vehicle.created_at.desc()).paginate(
            page=page, per_page=20, error_out=False
        )
        
        return render_template(
            "admin/transport_admin/vehicles.html",
            vehicles=vehicles,
            current_status=status
        )
    except Exception as e:
        logger.error(f"Error loading vehicles: {e}")
        flash("Error loading vehicles.", "danger")
        return redirect(url_for('admin.transport_admin_dashboard'))


@admin_bp.route("/transport-admin/vehicles/create", endpoint="transport_admin_create_vehicle", methods=['GET', 'POST'])
@login_required
@require_role("transport_admin")
def transport_admin_create_vehicle():
    """Create new vehicle."""
    try:
        if request.method == 'POST':
            from app.transport.models import Vehicle
            from app.transport.services import TransportService
            
            # Process vehicle creation
            vehicle_data = {
                'make': request.form.get('make'),
                'model': request.form.get('model'),
                'year': request.form.get('year', type=int),
                'license_plate': request.form.get('license_plate'),
                'vehicle_type': request.form.get('vehicle_type'),
                'capacity': request.form.get('capacity', type=int),
                'owner_id': request.form.get('owner_id', type=int),
                'created_by': current_user.id
            }
            
            vehicle = TransportService.create_vehicle(vehicle_data)
            if vehicle:
                flash("Vehicle created successfully.", "success")
                return redirect(url_for('admin.transport_admin_vehicles'))
            else:
                flash("Error creating vehicle.", "danger")
        
        return render_template("admin/transport_admin/create_vehicle.html")
    except Exception as e:
        logger.error(f"Error creating vehicle: {e}")
        flash("Error creating vehicle.", "danger")
        return redirect(url_for('admin.transport_admin_vehicles'))


@admin_bp.route("/transport-admin/vehicles/<int:vehicle_id>/edit", endpoint="transport_admin_edit_vehicle", methods=['GET', 'POST'])
@login_required
@require_role("transport_admin")
def transport_admin_edit_vehicle(vehicle_id):
    """Edit existing vehicle."""
    try:
        from app.transport.models import Vehicle
        from app.transport.services import TransportService
        
        vehicle = Vehicle.query.get_or_404(vehicle_id)
        
        if request.method == 'POST':
            # Process vehicle update
            vehicle_data = {
                'make': request.form.get('make'),
                'model': request.form.get('model'),
                'year': request.form.get('year', type=int),
                'license_plate': request.form.get('license_plate'),
                'vehicle_type': request.form.get('vehicle_type'),
                'capacity': request.form.get('capacity', type=int),
                'status': request.form.get('status')
            }
            
            if TransportService.update_vehicle(vehicle_id, vehicle_data):
                flash("Vehicle updated successfully.", "success")
                return redirect(url_for('admin.transport_admin_vehicles'))
            else:
                flash("Error updating vehicle.", "danger")
        
        return render_template("admin/transport_admin/edit_vehicle.html", vehicle=vehicle)
    except Exception as e:
        logger.error(f"Error editing vehicle: {e}")
        flash("Error editing vehicle.", "danger")
        return redirect(url_for('admin.transport_admin_vehicles'))


@admin_bp.route("/transport-admin/vehicles/<int:vehicle_id>/delete", endpoint="transport_admin_delete_vehicle", methods=['POST'])
@login_required
@require_role("transport_admin")
@require_fresh_user
def transport_admin_delete_vehicle(vehicle_id):
    """Delete vehicle."""
    try:
        from app.transport.models import Vehicle
        from app.transport.services import TransportService
        
        vehicle = Vehicle.query.get_or_404(vehicle_id)
        
        if TransportService.delete_vehicle(vehicle_id):
            flash(f"Vehicle '{vehicle.make} {vehicle.model}' deleted successfully.", "warning")
        else:
            flash("Error deleting vehicle.", "danger")
        
        return redirect(url_for('admin.transport_admin_vehicles'))
    except Exception as e:
        logger.error(f"Error deleting vehicle: {e}")
        flash("Error deleting vehicle.", "danger")
        return redirect(url_for('admin.transport_admin_vehicles'))


# -----------------------------
# Driver Management Routes
# -----------------------------
@admin_bp.route("/transport-admin/drivers", endpoint="transport_admin_drivers")
@login_required
@require_role("transport_admin")
def transport_admin_drivers():
    """List and manage all drivers."""
    try:
        from app.transport.models import Driver
        
        page = request.args.get('page', 1, type=int)
        status = request.args.get('status', 'all')
        
        query = Driver.query.filter_by(is_deleted=False)
        
        if status != 'all':
            query = query.filter_by(verification_status=status)
        
        drivers = query.order_by(Driver.created_at.desc()).paginate(
            page=page, per_page=20, error_out=False
        )
        
        return render_template(
            "admin/transport_admin/drivers.html",
            drivers=drivers,
            current_status=status
        )
    except Exception as e:
        logger.error(f"Error loading drivers: {e}")
        flash("Error loading drivers.", "danger")
        return redirect(url_for('admin.transport_admin_dashboard'))


@admin_bp.route("/transport-admin/drivers/<int:driver_id>/verify", endpoint="transport_admin_verify_driver", methods=['POST'])
@login_required
@require_role("transport_admin")
def transport_admin_verify_driver(driver_id):
    """Verify driver."""
    try:
        from app.transport.models import Driver
        from app.transport.services import TransportService
        
        driver = Driver.query.get_or_404(driver_id)
        
        if TransportService.verify_driver(driver_id, verified_by=current_user.id):
            flash(f"Driver {driver.name} verified successfully.", "success")
        else:
            flash("Error verifying driver.", "danger")
        
        return redirect(url_for('admin.transport_admin_drivers'))
    except Exception as e:
        logger.error(f"Error verifying driver: {e}")
        flash("Error verifying driver.", "danger")
        return redirect(url_for('admin.transport_admin_drivers'))


@admin_bp.route("/transport-admin/drivers/<int:driver_id>/reject", endpoint="transport_admin_reject_driver", methods=['POST'])
@login_required
@require_role("transport_admin")
def transport_admin_reject_driver(driver_id):
    """Reject driver verification."""
    try:
        from app.transport.models import Driver
        from app.transport.services import TransportService
        
        driver = Driver.query.get_or_404(driver_id)
        reason = request.form.get('reason', 'No reason provided')
        
        if TransportService.reject_driver(driver_id, reason):
            flash(f"Driver {driver.name} verification rejected.", "warning")
        else:
            flash("Error rejecting driver.", "danger")
        
        return redirect(url_for('admin.transport_admin_drivers'))
    except Exception as e:
        logger.error(f"Error rejecting driver: {e}")
        flash("Error rejecting driver.", "danger")
        return redirect(url_for('admin.transport_admin_drivers'))


# -----------------------------
# Booking Management
# -----------------------------
@admin_bp.route("/transport-admin/bookings", endpoint="transport_admin_bookings")
@login_required
@require_role("transport_admin")
def transport_admin_bookings():
    """Manage transport bookings."""
    try:
        from app.transport.models import TransportBooking
        
        page = request.args.get('page', 1, type=int)
        status = request.args.get('status', 'all')
        
        query = TransportBooking.query.filter_by(is_deleted=False)
        
        if status != 'all':
            query = query.filter_by(status=status)
        
        bookings = query.order_by(
            TransportBooking.created_at.desc()
        ).paginate(page=page, per_page=20, error_out=False)
        
        return render_template(
            "admin/transport_admin/bookings.html",
            bookings=bookings,
            current_status=status
        )
    except Exception as e:
        logger.error(f"Error loading bookings: {e}")
        flash("Error loading bookings.", "danger")
        return redirect(url_for('admin.transport_admin_dashboard'))


@admin_bp.route("/transport-admin/bookings/<int:booking_id>/approve", endpoint="transport_admin_approve_booking", methods=['POST'])
@login_required
@require_role("transport_admin")
def transport_admin_approve_booking(booking_id):
    """Approve transport booking."""
    try:
        from app.transport.models import TransportBooking
        from app.transport.services import TransportService
        
        booking = TransportBooking.query.get_or_404(booking_id)
        
        if TransportService.approve_booking(booking_id):
            flash(f"Booking for {booking.user.username} approved.", "success")
        else:
            flash("Error approving booking.", "danger")
        
        return redirect(url_for('admin.transport_admin_bookings'))
    except Exception as e:
        logger.error(f"Error approving booking: {e}")
        flash("Error approving booking.", "danger")
        return redirect(url_for('admin.transport_admin_bookings'))


@admin_bp.route("/transport-admin/bookings/<int:booking_id>/reject", endpoint="transport_admin_reject_booking", methods=['POST'])
@login_required
@require_role("transport_admin")
def transport_admin_reject_booking(booking_id):
    """Reject transport booking."""
    try:
        from app.transport.models import TransportBooking
        from app.transport.services import TransportService
        
        booking = TransportBooking.query.get_or_404(booking_id)
        reason = request.form.get('reason', 'No reason provided')
        
        if TransportService.reject_booking(booking_id, reason):
            flash(f"Booking for {booking.user.username} rejected.", "warning")
        else:
            flash("Error rejecting booking.", "danger")
        
        return redirect(url_for('admin.transport_admin_bookings'))
    except Exception as e:
        logger.error(f"Error rejecting booking: {e}")
        flash("Error rejecting booking.", "danger")
        return redirect(url_for('admin.transport_admin_bookings'))


# -----------------------------
# Organization Management
# -----------------------------
@admin_bp.route("/transport-admin/organizations", endpoint="transport_admin_organizations")
@login_required
@require_role("transport_admin")
def transport_admin_organizations():
    """Manage transport organizations."""
    try:
        from app.transport.models import TransportOrganization
        
        organizations = TransportOrganization.query.filter_by(
            is_deleted=False
        ).order_by(TransportOrganization.created_at.desc()).all()
        
        return render_template(
            "admin/transport_admin/organizations.html",
            organizations=organizations
        )
    except Exception as e:
        logger.error(f"Error loading organizations: {e}")
        flash("Error loading organizations.", "danger")
        return redirect(url_for('admin.transport_admin_dashboard'))


# -----------------------------
# Analytics and Settings
# -----------------------------
@admin_bp.route("/transport-admin/analytics", endpoint="transport_admin_analytics")
@login_required
@require_role("transport_admin")
def transport_admin_analytics():
    """Transport analytics and reports."""
    try:
        from app.transport.services import TransportService
        
        # Get analytics data
        analytics = TransportService.get_analytics_data()
        
        return render_template(
            "admin/transport_admin/analytics.html",
            analytics=analytics
        )
    except Exception as e:
        logger.error(f"Error loading analytics: {e}")
        flash("Error loading analytics.", "danger")
        return redirect(url_for('admin.transport_admin_dashboard'))


@admin_bp.route("/transport-admin/settings", endpoint="transport_admin_settings")
@login_required
@require_role("transport_admin")
def transport_admin_settings():
    """Transport admin settings."""
    try:
        return render_template("admin/transport_admin/settings.html")
    except Exception as e:
        from app.utils.error_handler import log_error_to_audit
        from flask_login import current_user
        log_error_to_audit(
            user_id=current_user.id if current_user.is_authenticated else None,
            error_type="SETTINGS_LOAD_ERROR",
            error_message=str(e),
            context={"module": "transport_admin", "template": "settings.html"}
        )
        flash("Unable to load settings. Please try again later.", "warning")
        return redirect(url_for('admin.transport_admin_dashboard'))
