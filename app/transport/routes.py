# app/transport/routes.py
"""
Transport Module Routes
Merged from scaffold (comprehensive route coverage) and production file
(security, logging, error handling, AJAX support).

Design principles:
- Every route is protected: module check + login + role where applicable
- JSON fallback on all routes for AJAX compatibility
- Consistent logging with user_id context on all actions
- Granular exception handling (NotFoundError, ValidationError, ServiceUnavailableError)
- Single responsibility: routing only — business logic lives in services
"""
from datetime import datetime
import logging

from flask import render_template, jsonify, request, url_for, flash, redirect, session
from flask_login import login_required, current_user

from app.transport.decorator import module_enabled_required, role_required, rate_limit
from app.transport import transport_bp, transport_admin_bp
from app.utils.module_switch import check_module_enabled
from app.utils.exceptions import NotFoundError, ServiceUnavailableError, ValidationError
from app.utils.audit import audit_log
from app.transport.services import get_booking_service, get_provider_service, get_dashboard_service
from app.extensions import db

logger = logging.getLogger(__name__)


# =========================================================================
# Helpers
# =========================================================================

def _json_or_template(template, status=200, **ctx):
    """
    Returns JSON for AJAX/API clients, HTML for browsers.
    Detects via Accept header or X-Requested-With.
    """
    wants_json = (
        request.headers.get("X-Requested-With") == "XMLHttpRequest"
        or request.accept_mimetypes.best == "application/json"
    )
    if wants_json:
        return jsonify({"status": "ok", **ctx}), status
    return render_template(template, **ctx), status


def _paginate_args():
    """Extract page/per_page from query string. per_page capped at 100."""
    page = max(request.args.get("page", 1, type=int), 1)
    per_page = min(request.args.get("per_page", 25, type=int), 100)
    return page, per_page


def _uid():
    """Shorthand for current_user.id for log lines."""
    return getattr(current_user, "id", "anon")


# =========================================================================
# Health & Status  (no auth — intentional)
# =========================================================================

@transport_bp.route("/api/status", methods=["GET"])
def api_status():
    """Check transport module status"""
    return jsonify({
        "module": "transport",
        "enabled": check_module_enabled("transport"),
        "timestamp": datetime.utcnow().isoformat()
    })


@transport_bp.route("/health", methods=["GET"])
def health():
    """Health check for transport module"""
    return jsonify({
        "module": "transport",
        "enabled": check_module_enabled("transport"),
        "services_available": True,
        "provider_service": get_provider_service() is not None,
        "booking_service": get_booking_service() is not None,
        "timestamp": datetime.utcnow().isoformat()
    })


# =========================================================================
# Public / Fan-facing
# =========================================================================

@transport_bp.route("/", methods=["GET"])
@module_enabled_required("transport")
def home():
    """Transport module homepage"""
    try:
        booking_service = get_booking_service()
        services = booking_service.list_services() if hasattr(booking_service, "list_services") else []
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error loading transport services: {e}")
        services = []

    logger.info(f"Transport home accessed by user_id={_uid()}")
    return render_template(
        "transport/home.html",
        title="AFCON Transport & Travel",
        services=services,
        module_enabled=check_module_enabled("transport")
    )


@transport_bp.route("/service/<uuid:service_id>", methods=["GET"])
@module_enabled_required("transport")
def service_detail(service_id):
    """View transport service details. JSON response when called via AJAX."""
    try:
        booking_service = get_booking_service()
        service = booking_service.get_service(service_id) if hasattr(booking_service, "get_service") else None
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error loading service {service_id} for user_id={_uid()}: {e}")
        service = None

    if not service:
        logger.warning(f"Service not found: {service_id}")
        if request.is_json:
            return jsonify({"status": "error", "message": "Service not found"}), 404
        flash("Service not found", "warning")
        return redirect(url_for("transport.home"))

    return _json_or_template("transport/service_detail.html", service=service)


# =========================================================================
# Dashboard
# =========================================================================

@transport_bp.route("/dashboard")
@transport_bp.route("/dashboard/overview")
@module_enabled_required("transport")
@login_required
def dashboard_overview():
    """Transport dashboard overview"""
    logger.info(f"Dashboard overview accessed by user_id={_uid()}")
    return _json_or_template("transport/dashboard/overview.html")


@transport_bp.route("/dashboard/performance")
@module_enabled_required("transport")
@login_required
def dashboard_performance():
    """Transport performance dashboard"""
    logger.info(f"Dashboard performance accessed by user_id={_uid()}")
    return _json_or_template("transport/analytics/performance.html")


# =========================================================================
# Bookings
# =========================================================================

@transport_bp.route("/bookings")
@module_enabled_required("transport")
@login_required
def bookings_index():
    """Bookings index"""
    logger.info(f"Bookings index accessed by user_id={_uid()}")
    return _json_or_template("transport/bookings/index.html")


@transport_bp.route("/bookings/new", methods=["GET"])
@module_enabled_required("transport")
@login_required
def bookings_new():
    """New booking form"""
    return render_template("transport/bookings/new.html")


@transport_bp.route("/book", methods=["GET", "POST"])
@module_enabled_required("transport")
@login_required
@rate_limit("book_transport", per_minute=5)
def book_transport():
    """Submit a booking"""
    if request.method == "GET":
        return render_template("transport/book.html")

    try:
        from app.schemas.transport import BookingSchema
        data = BookingSchema().load(request.form)
    except ImportError:
        logger.warning("BookingSchema not found — using raw form data")
        data = request.form.to_dict()
    except ValidationError as err:
        logger.warning(f"Booking validation failed for user_id={_uid()}: {err.messages}")
        for error in err.messages.values():
            flash(error[0], "danger")
        return redirect(url_for("transport.book_transport"))

    try:
        booking = get_booking_service().create_booking(current_user.id, data)
        ref = booking["data"]["booking_code"]
        booking_id = booking["data"]["booking_id"]
        logger.info(f"Booking created: user_id={_uid()}, ref={ref}")
        flash(f"Booking confirmed! Reference: {ref}", "success")
        return redirect(url_for("transport.bookings_show", id=booking_id))

    except ServiceUnavailableError:
        logger.error(f"Booking service unavailable for user_id={_uid()}")
        flash("Booking service temporarily unavailable", "warning")
        return redirect(url_for("transport.home"))

    except Exception as e:
        db.session.rollback()
        logger.error(f"Booking error for user_id={_uid()}: {e}")
        flash(f"Booking error: {str(e)}", "danger")
        return redirect(url_for("transport.book_transport"))


@transport_bp.route("/bookings/<int:id>")
@module_enabled_required("transport")
@login_required
def bookings_show(id):
    """View booking details"""
    try:
        booking = get_booking_service().get_booking(id)
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error loading booking {id} for user_id={_uid()}: {e}")
        booking = None

    if not booking:
        if request.is_json:
            return jsonify({"status": "error", "message": "Booking not found"}), 404
        flash("Booking not found", "warning")
        return redirect(url_for("transport.bookings_index"))

    return _json_or_template("transport/bookings/show.html", booking=booking, id=id)


@transport_bp.route("/bookings/<int:id>/edit")
@module_enabled_required("transport")
@login_required
def bookings_edit(id):
    """Edit a booking"""
    logger.info(f"Booking edit {id} accessed by user_id={_uid()}")
    return _json_or_template("transport/bookings/edit.html", id=id)


@transport_bp.route("/bookings/<int:id>/timeline")
@module_enabled_required("transport")
@login_required
def bookings_timeline(id):
    """Booking event timeline"""
    logger.info(f"Booking timeline {id} accessed by user_id={_uid()}")
    return _json_or_template("transport/bookings/timeline.html", id=id)


@transport_bp.route("/bookings/<int:id>/payments")
@module_enabled_required("transport")
@login_required
def bookings_payments(id):
    """Booking payment details"""
    logger.info(f"Booking payments {id} accessed by user_id={_uid()}")
    return _json_or_template("transport/bookings/payments.html", id=id)


# =========================================================================
# Drivers
# =========================================================================

@transport_bp.route("/drivers")
@module_enabled_required("transport")
@login_required
def drivers_index():
    """Drivers index"""
    logger.info(f"Drivers index accessed by user_id={_uid()}")
    return _json_or_template("transport/drivers/index.html")


@transport_bp.route("/drivers/new")
@module_enabled_required("transport")
@login_required
def drivers_new():
    """New driver form"""
    return render_template("transport/drivers/new.html")


@transport_bp.route("/become-driver", methods=["GET", "POST"])
@module_enabled_required("transport")
@login_required
@role_required("provider")
def become_driver():
    """Register as a transport driver"""
    if request.method == "GET":
        from app.utils.validators import TransportValidators
        return render_template(
            "transport/become_driver.html",
            countries=sorted(TransportValidators.AFCON_COUNTRIES),
            vehicle_classes=["ECONOMY", "COMFORT", "PREMIUM", "LUXURY", "VAN", "BUS"]
        )

    try:
        from app.schemas.transport import DriverRegistrationSchema
        data = DriverRegistrationSchema().load(request.form)
    except ImportError:
        data = request.form.to_dict()
    except ValidationError as err:
        for error in err.messages.values():
            flash(error[0], "danger")
        return redirect(url_for("transport.become_driver"))

    try:
        driver = get_provider_service().register_driver(data, user_id=current_user.id)
        logger.info(f"Driver registered: user_id={_uid()}, driver_id={driver.id}")
        flash("Driver registration submitted for verification!", "success")
        return redirect(url_for("transport.driver_dashboard"))

    except Exception as e:
        db.session.rollback()
        logger.error(f"Driver registration error for user_id={_uid()}: {e}")
        flash(f"Registration error: {str(e)}", "danger")
        return redirect(url_for("transport.become_driver"))


@transport_bp.route("/drivers/<int:id>")
@module_enabled_required("transport")
@login_required
def drivers_show(id):
    """View driver profile"""
    try:
        driver = get_provider_service().get_driver(id)
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error loading driver {id} for user_id={_uid()}: {e}")
        driver = None

    if not driver:
        if request.is_json:
            return jsonify({"status": "error", "message": "Driver not found"}), 404
        flash("Driver not found", "warning")
        return redirect(url_for("transport.drivers_index"))

    return _json_or_template("transport/drivers/show.html", driver=driver, id=id)


@transport_bp.route("/drivers/<int:id>/edit")
@module_enabled_required("transport")
@login_required
def drivers_edit(id):
    """Edit driver profile"""
    logger.info(f"Driver edit {id} accessed by user_id={_uid()}")
    return _json_or_template("transport/drivers/edit.html", id=id)


@transport_bp.route("/drivers/<int:id>/location")
@module_enabled_required("transport")
@login_required
def drivers_location(id):
    """Driver live location"""
    logger.info(f"Driver location {id} accessed by user_id={_uid()}")
    return _json_or_template("transport/drivers/location.html", id=id)


@transport_bp.route("/drivers/<int:id>/verification")
@module_enabled_required("transport")
@login_required
def drivers_verification(id):
    """Driver verification details"""
    logger.info(f"Driver verification {id} accessed by user_id={_uid()}")
    return _json_or_template("transport/drivers/verification.html", id=id)


@transport_bp.route("/driver-dashboard")
@module_enabled_required("transport")
@login_required
@role_required("driver")
def driver_dashboard():
    """Driver's personal dashboard"""
    try:
        profile = get_provider_service().get_driver_profile(current_user.id)
        bookings = (
            get_booking_service().get_driver_bookings(current_user.id)
            if profile and profile.status == "approved"
            else []
        )
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error loading driver dashboard for user_id={_uid()}: {e}")
        profile = None
        bookings = []

    return _json_or_template(
        "transport/driver_dashboard.html",
        driver_profile=profile,
        bookings=bookings,
    )


# =========================================================================
# Vehicles
# =========================================================================

@transport_bp.route("/vehicles")
@module_enabled_required("transport")
@login_required
def vehicles_index():
    """Vehicles index"""
    logger.info(f"Vehicles index accessed by user_id={_uid()}")
    return _json_or_template("transport/vehicles/index.html")


@transport_bp.route("/vehicles/new")
@module_enabled_required("transport")
@login_required
def vehicles_new():
    """New vehicle form"""
    return render_template("transport/vehicles/new.html")


@transport_bp.route("/register-vehicle", methods=["GET", "POST"])
@module_enabled_required("transport")
@login_required
@role_required("provider")
def register_vehicle():
    """Register a vehicle for transport service"""
    if request.method == "GET":
        return render_template(
            "transport/register_vehicle.html",
            vehicle_classes=["ECONOMY", "COMFORT", "PREMIUM", "LUXURY", "VAN", "BUS", "MINIBUS"]
        )

    try:
        from app.schemas.transport import VehicleRegistrationSchema
        data = VehicleRegistrationSchema().load(request.form)
    except ImportError:
        data = request.form.to_dict()
    except ValidationError as err:
        for error in err.messages.values():
            flash(error[0], "danger")
        return redirect(url_for("transport.register_vehicle"))

    try:
        vehicle = get_provider_service().register_vehicle(data, user_id=current_user.id)
        logger.info(f"Vehicle registered: user_id={_uid()}, vehicle_id={vehicle.id}")
        flash("Vehicle registration submitted!", "success")
        return redirect(url_for("transport.vehicle_dashboard"))

    except Exception as e:
        db.session.rollback()
        logger.error(f"Vehicle registration error for user_id={_uid()}: {e}")
        flash(f"Registration error: {str(e)}", "danger")
        return redirect(url_for("transport.register_vehicle"))


@transport_bp.route("/vehicles/<int:id>")
@module_enabled_required("transport")
@login_required
def vehicles_show(id):
    """View vehicle details"""
    try:
        vehicle = get_provider_service().get_vehicle(id)
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error loading vehicle {id} for user_id={_uid()}: {e}")
        vehicle = None

    if not vehicle:
        if request.is_json:
            return jsonify({"status": "error", "message": "Vehicle not found"}), 404
        flash("Vehicle not found", "warning")
        return redirect(url_for("transport.vehicles_index"))

    return _json_or_template("transport/vehicles/show.html", vehicle=vehicle, id=id)


@transport_bp.route("/vehicles/<int:id>/edit")
@module_enabled_required("transport")
@login_required
def vehicles_edit(id):
    """Edit vehicle"""
    logger.info(f"Vehicle edit {id} accessed by user_id={_uid()}")
    return _json_or_template("transport/vehicles/edit.html", id=id)


@transport_bp.route("/vehicles/<int:id>/maintenance")
@module_enabled_required("transport")
@login_required
def vehicles_maintenance(id):
    """Vehicle maintenance records"""
    logger.info(f"Vehicle maintenance {id} accessed by user_id={_uid()}")
    return _json_or_template("transport/vehicles/maintenance.html", id=id)


@transport_bp.route("/vehicles/<int:id>/location")
@module_enabled_required("transport")
@login_required
def vehicles_location(id):
    """Vehicle live location"""
    logger.info(f"Vehicle location {id} accessed by user_id={_uid()}")
    return _json_or_template("transport/vehicles/location.html", id=id)


@transport_bp.route("/vehicle-dashboard")
@module_enabled_required("transport")
@login_required
@role_required("provider")
def vehicle_dashboard():
    """Vehicle management dashboard"""
    try:
        vehicles = get_provider_service().get_user_vehicles(current_user.id)
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error loading vehicle dashboard for user_id={_uid()}: {e}")
        vehicles = []

    return _json_or_template("transport/vehicle_dashboard.html", vehicles=vehicles)


# =========================================================================
# Incidents
# =========================================================================

@transport_bp.route("/incidents")
@module_enabled_required("transport")
@login_required
def incidents_index():
    """Incidents index"""
    logger.info(f"Incidents index accessed by user_id={_uid()}")
    return _json_or_template("transport/incidents/index.html")


@transport_bp.route("/incidents/new")
@module_enabled_required("transport")
@login_required
def incidents_new():
    """New incident form"""
    return render_template("transport/incidents/new.html")


@transport_bp.route("/incidents/<int:id>")
@module_enabled_required("transport")
@login_required
def incidents_show(id):
    """View incident details"""
    logger.info(f"Incident {id} accessed by user_id={_uid()}")
    return _json_or_template("transport/incidents/show.html", id=id)


@transport_bp.route("/incidents/<int:id>/investigate")
@module_enabled_required("transport")
@login_required
@role_required("admin")
def incidents_investigate(id):
    """Incident investigation panel — admin only"""
    logger.info(f"Incident investigation {id} accessed by user_id={_uid()}")
    return _json_or_template("transport/incidents/investigate.html", id=id)


@transport_bp.route("/incidents/<int:id>/evidence")
@module_enabled_required("transport")
@login_required
def incidents_evidence(id):
    """Incident evidence files"""
    logger.info(f"Incident evidence {id} accessed by user_id={_uid()}")
    return _json_or_template("transport/incidents/evidence.html", id=id)


# =========================================================================
# Organisations
# =========================================================================

@transport_bp.route("/organisations")
@module_enabled_required("transport")
@login_required
def organisations_index():
    """Organisations index"""
    logger.info(f"Organisations index accessed by user_id={_uid()}")
    return _json_or_template("transport/organisations/index.html")


@transport_bp.route("/organisations/new")
@module_enabled_required("transport")
@login_required
@role_required("admin")
def organisations_new():
    """New organisation form — admin only"""
    return render_template("transport/organisations/new.html")


@transport_bp.route("/organisations/<int:id>")
@module_enabled_required("transport")
@login_required
def organisations_show(id):
    """View organisation details"""
    logger.info(f"Organisation {id} accessed by user_id={_uid()}")
    return _json_or_template("transport/organisations/show.html", id=id)


@transport_bp.route("/organisations/<int:id>/drivers")
@module_enabled_required("transport")
@login_required
def organisations_drivers(id):
    """Organisation drivers list"""
    logger.info(f"Organisation drivers {id} accessed by user_id={_uid()}")
    return _json_or_template("transport/organisations/drivers.html", id=id)


@transport_bp.route("/organisations/<int:id>/vehicles")
@module_enabled_required("transport")
@login_required
def organisations_vehicles(id):
    """Organisation vehicles list"""
    logger.info(f"Organisation vehicles {id} accessed by user_id={_uid()}")
    return _json_or_template("transport/organisations/vehicles.html", id=id)


# =========================================================================
# Transport Routes
# =========================================================================

@transport_bp.route("/routes")
@module_enabled_required("transport")
@login_required
def routes_index():
    """Routes index"""
    logger.info(f"Routes index accessed by user_id={_uid()}")
    return _json_or_template("transport/routes/index.html")


@transport_bp.route("/routes/new")
@module_enabled_required("transport")
@login_required
@role_required("admin")
def routes_new():
    """New route form — admin only"""
    return render_template("transport/routes/new.html")


@transport_bp.route("/routes/<int:id>")
@module_enabled_required("transport")
@login_required
def routes_show(id):
    """View route details"""
    logger.info(f"Route {id} accessed by user_id={_uid()}")
    return _json_or_template("transport/routes/show.html", id=id)


@transport_bp.route("/routes/<int:id>/schedule")
@module_enabled_required("transport")
@login_required
def routes_schedule(id):
    """Route schedule"""
    logger.info(f"Route schedule {id} accessed by user_id={_uid()}")
    return _json_or_template("transport/routes/schedule.html", id=id)


# =========================================================================
# Analytics
# =========================================================================

@transport_bp.route("/analytics")
@module_enabled_required("transport")
@login_required
def analytics_index():
    """Analytics index"""
    logger.info(f"Analytics index accessed by user_id={_uid()}")
    return _json_or_template("transport/analytics/index.html")


@transport_bp.route("/analytics/revenue")
@module_enabled_required("transport")
@login_required
def analytics_revenue():
    """Revenue analytics"""
    logger.info(f"Analytics revenue accessed by user_id={_uid()}")
    return _json_or_template("transport/analytics/revenue.html")


@transport_bp.route("/analytics/performance")
@module_enabled_required("transport")
@login_required
def analytics_performance():
    """Performance analytics"""
    logger.info(f"Analytics performance accessed by user_id={_uid()}")
    return _json_or_template("transport/analytics/performance.html")


# =========================================================================
# Settings
# =========================================================================

@transport_bp.route("/settings")
@module_enabled_required("transport")
@login_required
@role_required("admin")
def settings_index():
    """Settings — admin only"""
    logger.info(f"Settings accessed by user_id={_uid()}")
    return _json_or_template("transport/settings/index.html")


# =========================================================================
# Organisation Dashboard
# =========================================================================
@transport_bp.route("/organisation/dashboard", methods=["GET"])
@module_enabled_required("transport")
@login_required
@role_required("organisation_admin")
def organisation_dashboard():
    """
    Organisation's transport dashboard
    """
    try:
        org_id = getattr(current_user, 'organisation_id', None)
        if not org_id:
            flash("Organisation not found", "danger")
            return redirect(url_for("transport.home"))

        ctx = get_dashboard_service().get_organisation_dashboard_context(org_id)
        return render_template("transport/organisation/dashboard.html", **ctx)

    except Exception as e:
        db.session.rollback()
        logger.error(f"Organisation dashboard error: {e}", exc_info=True)
        flash("Unable to load dashboard", "danger")
        return redirect(url_for("transport.home"))



# -------------------------------------------------------------------------
# Admin — Bookings
# -------------------------------------------------------------------------

@transport_admin_bp.route("/bookings", methods=["GET"])
@module_enabled_required("transport")
@login_required
@role_required("admin")
def list_bookings():
    """View all bookings with pagination"""
    page, per_page = _paginate_args()
    try:
        bookings = get_booking_service().list_all_bookings(page=page, per_page=per_page)
        logger.info(f"Bookings list accessed by user_id={_uid()} page={page}")
        return _json_or_template(
            "transport/admin/bookings.html",
            bookings=bookings, page=page, per_page=per_page
        )
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error listing bookings for user_id={_uid()}: {e}", exc_info=True)
        flash("Unable to load bookings", "danger")
        return redirect(url_for("transport.home"))


@transport_admin_bp.route("/bookings/<int:booking_id>/cancel", methods=["POST"])
@module_enabled_required("transport")
@login_required
@role_required("admin")
def cancel_booking(booking_id):
    """Cancel a booking as admin"""
    try:
        get_booking_service().cancel_booking(booking_id, user_id=current_user.id)
        logger.info(f"Booking {booking_id} cancelled by user_id={_uid()}")
        audit_log(action="booking_cancelled_admin", entity_type="booking",
                  entity_id=booking_id, user_id=current_user.id, details={"status": "cancelled"})
        flash(f"Booking {booking_id} cancelled successfully", "success")

    except NotFoundError as e:
        logger.warning(f"Cancel booking {booking_id} — not found — user_id={_uid()}: {e}")
        flash(str(e), "danger")

    except ServiceUnavailableError as e:
        logger.error(f"Service unavailable cancelling booking {booking_id} — user_id={_uid()}: {e}", exc_info=True)
        flash("Booking service unavailable", "danger")

    except ValidationError as e:
        logger.warning(f"Validation error cancelling booking {booking_id} — user_id={_uid()}: {e}")
        flash(str(e), "danger")

    except Exception as e:
        db.session.rollback()
        logger.error(f"Unexpected error cancelling booking {booking_id} — user_id={_uid()}: {e}", exc_info=True)
        flash("Unexpected error cancelling booking", "danger")

    return redirect(url_for("transport_admin.list_bookings"))


# -------------------------------------------------------------------------
# Admin — Drivers
# -------------------------------------------------------------------------

@transport_admin_bp.route("/drivers", methods=["GET"])
@module_enabled_required("transport")
@login_required
@role_required("admin")
def list_drivers():
    """List all drivers with pagination"""
    page, per_page = _paginate_args()
    try:
        drivers = get_provider_service().list_drivers(page=page, per_page=per_page)
        logger.info(f"Drivers list accessed by user_id={_uid()} page={page}")
        return _json_or_template(
            "transport/admin/drivers.html",
            drivers=drivers, page=page, per_page=per_page
        )
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error listing drivers for user_id={_uid()}: {e}", exc_info=True)
        flash("Unable to load drivers", "danger")
        return redirect(url_for("transport.home"))


@transport_admin_bp.route("/drivers/filter", methods=["GET"])
@module_enabled_required("transport")
@login_required
@role_required("admin")
def drivers_filter():
    """Filtered drivers list — used for ?status=pending, ?online=true"""
    page, per_page = _paginate_args()
    status = request.args.get("status")
    online = request.args.get("online")
    try:
        drivers_list = get_provider_service().list_drivers(
            page=page,
            per_page=per_page,
            status=status,
            online=online
        )
        return _json_or_template(
            "transport/drivers/index.html",
            drivers=drivers_list, page=page, per_page=per_page,
            status_filter=status, online_filter=online
        )
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error filtering drivers for user_id={_uid()}: {e}", exc_info=True)
        flash("Unable to load drivers", "danger")
        return redirect(url_for("transport_admin.list_drivers"))


@transport_admin_bp.route("/drivers/<int:driver_id>/approve", methods=["POST"])
@module_enabled_required("transport")
@login_required
@role_required("admin")
def approve_driver(driver_id):
    """Approve a driver registration"""
    try:
        get_provider_service().update_driver_status(driver_id, "approved")
        logger.info(f"Driver {driver_id} approved by user_id={_uid()}")
        audit_log(action="driver_approved", entity_type="driver",
                  entity_id=driver_id, user_id=current_user.id, details={"status": "approved"})
        flash(f"Driver {driver_id} approved", "success")

    except NotFoundError as e:
        logger.warning(f"Approve driver {driver_id} — not found — user_id={_uid()}: {e}")
        flash(str(e), "danger")

    except ValidationError as e:
        logger.warning(f"Validation error approving driver {driver_id} — user_id={_uid()}: {e}")
        flash(str(e), "danger")

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error approving driver {driver_id} — user_id={_uid()}: {e}", exc_info=True)
        flash("Unable to approve driver", "danger")

    return redirect(url_for("transport_admin.list_drivers"))


@transport_admin_bp.route("/drivers/<int:driver_id>/reject", methods=["POST"])
@module_enabled_required("transport")
@login_required
@role_required("admin")
def reject_driver(driver_id):
    """Reject a driver registration"""
    try:
        get_provider_service().update_driver_status(driver_id, "rejected")
        logger.info(f"Driver {driver_id} rejected by user_id={_uid()}")
        audit_log(action="driver_rejected", entity_type="driver",
                  entity_id=driver_id, user_id=current_user.id, details={"status": "rejected"})
        flash(f"Driver {driver_id} rejected", "warning")

    except NotFoundError as e:
        logger.warning(f"Reject driver {driver_id} — not found — user_id={_uid()}: {e}")
        flash(str(e), "danger")

    except ValidationError as e:
        logger.warning(f"Validation error rejecting driver {driver_id} — user_id={_uid()}: {e}")
        flash(str(e), "danger")

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error rejecting driver {driver_id} — user_id={_uid()}: {e}", exc_info=True)
        flash("Unable to reject driver", "danger")

    return redirect(url_for("transport_admin.list_drivers"))


# -------------------------------------------------------------------------
# Admin — Vehicles
# -------------------------------------------------------------------------

@transport_admin_bp.route("/vehicles", methods=["GET"])
@module_enabled_required("transport")
@login_required
@role_required("admin")
def list_vehicles():
    """List all registered vehicles with pagination"""
    page, per_page = _paginate_args()
    try:
        vehicles = get_provider_service().list_vehicles(page=page, per_page=per_page)
        logger.info(f"Vehicles list accessed by user_id={_uid()} page={page}")
        return _json_or_template(
            "transport/admin/vehicles.html",
            vehicles=vehicles, page=page, per_page=per_page
        )
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error listing vehicles for user_id={_uid()}: {e}", exc_info=True)
        flash("Unable to load vehicles", "danger")
        return redirect(url_for("transport.home"))


@transport_admin_bp.route("/vehicles/<int:vehicle_id>/approve", methods=["POST"])
@module_enabled_required("transport")
@login_required
@role_required("admin")
def approve_vehicle(vehicle_id):
    """Approve vehicle registration"""
    try:
        get_provider_service().update_vehicle_status(vehicle_id, "approved")
        logger.info(f"Vehicle {vehicle_id} approved by user_id={_uid()}")
        audit_log(action="vehicle_approved", entity_type="vehicle",
                  entity_id=vehicle_id, user_id=current_user.id, details={"status": "approved"})
        flash(f"Vehicle {vehicle_id} approved", "success")

    except NotFoundError as e:
        logger.warning(f"Approve vehicle {vehicle_id} — not found — user_id={_uid()}: {e}")
        flash(str(e), "danger")

    except ValidationError as e:
        logger.warning(f"Validation error approving vehicle {vehicle_id} — user_id={_uid()}: {e}")
        flash(str(e), "danger")

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error approving vehicle {vehicle_id} — user_id={_uid()}: {e}", exc_info=True)
        flash("Unable to approve vehicle", "danger")

    return redirect(url_for("transport_admin.list_vehicles"))


@transport_admin_bp.route("/vehicles/<int:vehicle_id>/reject", methods=["POST"])
@module_enabled_required("transport")
@login_required
@role_required("admin")
def reject_vehicle(vehicle_id):
    """Reject vehicle registration"""
    try:
        get_provider_service().update_vehicle_status(vehicle_id, "rejected")
        logger.info(f"Vehicle {vehicle_id} rejected by user_id={_uid()}")
        audit_log(action="vehicle_rejected", entity_type="vehicle",
                  entity_id=vehicle_id, user_id=current_user.id, details={"status": "rejected"})
        flash(f"Vehicle {vehicle_id} rejected", "warning")

    except NotFoundError as e:
        logger.warning(f"Reject vehicle {vehicle_id} — not found — user_id={_uid()}: {e}")
        flash(str(e), "danger")

    except ValidationError as e:
        logger.warning(f"Validation error rejecting vehicle {vehicle_id} — user_id={_uid()}: {e}")
        flash(str(e), "danger")

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error rejecting vehicle {vehicle_id} — user_id={_uid()}: {e}", exc_info=True)
        flash("Unable to reject vehicle", "danger")

    return redirect(url_for("transport_admin.list_vehicles"))


# -------------------------------------------------------------------------
# Admin — Routes
# -------------------------------------------------------------------------

@transport_admin_bp.route("/routes", methods=["GET"])
@module_enabled_required("transport")
@login_required
@role_required("admin")
def admin_routes():
    """Admin view of all scheduled routes"""
    page, per_page = _paginate_args()
    logger.info(f"Admin routes list accessed by user_id={_uid()}")
    return _json_or_template("transport/routes/index.html", page=page, per_page=per_page)


# -------------------------------------------------------------------------
# Admin — Incidents
# -------------------------------------------------------------------------

@transport_admin_bp.route("/incidents", methods=["GET"])
@module_enabled_required("transport")
@login_required
@role_required("admin")
def admin_incidents():
    """Admin view of all incidents"""
    page, per_page = _paginate_args()
    logger.info(f"Admin incidents list accessed by user_id={_uid()}")
    return _json_or_template("transport/incidents/index.html", page=page, per_page=per_page)


# -------------------------------------------------------------------------
# Admin — Settings
# -------------------------------------------------------------------------

@transport_admin_bp.route("/settings", methods=["GET", "POST"])
@module_enabled_required("transport")
@login_required
@role_required("admin")
def admin_settings():
    """Admin transport settings"""
    logger.info(f"Admin settings accessed by user_id={_uid()}")
    return _json_or_template("transport/settings/index.html")


# -------------------------------------------------------------------------
# Admin — Reports
# -------------------------------------------------------------------------

@transport_admin_bp.route("/reports/bookings", methods=["GET"])
@module_enabled_required("transport")
@login_required
@role_required("admin")
def bookings_report():
    """Generate booking reports"""
    try:
        report_data = get_booking_service().generate_booking_report()
        logger.info(f"Booking report generated by user_id={_uid()}")
        return _json_or_template("transport/admin/reports/bookings.html", report=report_data)

    except ServiceUnavailableError as e:
        logger.error(f"Service unavailable generating report — user_id={_uid()}: {e}", exc_info=True)
        flash("Reporting service temporarily unavailable", "danger")
        return redirect(url_for("transport_admin.admin_dashboard"))

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error generating booking report — user_id={_uid()}: {e}", exc_info=True)
        flash("Unable to generate report", "danger")
        return redirect(url_for("transport_admin.admin_dashboard"))


# -------------------------------------------------------------------------
# Transport Admin Dashboard - THE ONE SUPER ADMIN CLICKS
# -------------------------------------------------------------------------
@transport_admin_bp.route("/dashboard", methods=["GET"])
@module_enabled_required("transport")
@login_required
def dashboard():
    """Transport Admin Dashboard - accessible by admins and super admins"""
    try:
        from datetime import datetime

        # DEBUG - See what's happening with roles
        print(f"\n🔍 DASHBOARD ACCESS ATTEMPT")
        print(f"🔍 User: {current_user.username}")
        print(f"🔍 User ID: {current_user.id}")
        print(f"🔍 Is authenticated: {current_user.is_authenticated}")
        print(f"🔍 Is super admin: {current_user.is_super_admin()}")
        print(f"🔍 Has admin role: {current_user.has_global_role('admin')}")
        print(f"🔍 All roles: {current_user.role_names}")
        print(f"🔍 Session data: {dict(session)}\n")

        # Check if user has either admin or super_admin role
        if not (current_user.has_global_role('admin') or current_user.is_super_admin()):
            logger.warning(f"Access denied to transport admin dashboard for user_id={_uid()}")
            flash("Access denied. Admin privileges required.", "danger")
            return redirect(url_for("transport.home"))

        # If we get here, user has permission
        print(f"✅ ACCESS GRANTED for {current_user.username}")

        # Base template requirements (for transport/base.html)
        ctx = {
            # Navigation badges
            'pending_bookings_count': 0,
            'open_incidents_count': 0,
            'unread_notifications': 0,

            # Basic info
            'module_enabled': check_module_enabled('transport'),
            'now': datetime.utcnow().strftime('%Y-%m-%d %H:%M'),

            # Admin dashboard stats (with defaults)
            'total_bookings': 0,
            'pending_drivers': 0,
            'pending_vehicles': 0,
            'today_bookings': 0,
            'today_revenue': 0,
            'pending_bookings': 0,
            'confirmed_bookings': 0,
            'completed_bookings': 0,
            'cancelled_bookings': 0,
            'active_bookings': 0,
            'active_drivers': 0,
            'available_vehicles': 0,
            'recent_bookings': []
        }

        # Try to get real data from services
        try:
            ctx['total_bookings'] = get_booking_service().count_bookings()
            ctx['pending_drivers'] = get_provider_service().count_pending_drivers()
            ctx['pending_vehicles'] = get_provider_service().count_pending_vehicles()

            # Today's stats
            today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
            ctx['today_bookings'] = get_booking_service().count_bookings_since(today_start)

            # Recent bookings
            ctx['recent_bookings'] = get_booking_service().get_recent_bookings(limit=5)

            # Status breakdown
            ctx['pending_bookings'] = get_booking_service().count_bookings_by_status('pending')
            ctx['confirmed_bookings'] = get_booking_service().count_bookings_by_status('confirmed')
            ctx['completed_bookings'] = get_booking_service().count_bookings_by_status('completed')
            ctx['cancelled_bookings'] = get_booking_service().count_bookings_by_status('cancelled')

            # Derived stats
            ctx['active_bookings'] = ctx['confirmed_bookings']
            ctx['pending_bookings_count'] = ctx['pending_bookings']  # For badge
            ctx['active_drivers'] = get_provider_service().count_active_drivers()
            ctx['available_vehicles'] = get_provider_service().count_available_vehicles()

        except AttributeError as e:
            logger.warning(f"Some stats methods not available: {e}")
            # Keep defaults, template has |default filters

        logger.info(f"Transport admin dashboard loaded for user_id={_uid()}")
        return render_template("transport/admin/dashboard.html", **ctx)

    except Exception as e:
        db.session.rollback()
        logger.error(f"Transport admin dashboard error: {e}", exc_info=True)
        flash("Unable to load dashboard. Please try again.", "danger")
        return redirect(url_for("transport_admin.dashboard"))
