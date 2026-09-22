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
- Single responsibility: routing only - business logic lives in services
"""
from datetime import datetime, timezone
import logging
from sqlalchemy.orm import joinedload

from flask import render_template, jsonify, request, url_for, flash, redirect, session, abort
from flask_login import login_required, current_user

from app.extensions import csrf
from app.transport.decorator import module_enabled_required, role_required, rate_limit
from app.auth.kyc_compliance import require_kyc_tier
from app.auth.decorators import (
    require_profile_completion,
    require_moderator,
    admin_required,
)
from app.auth.context import (
    ContextType,
    active_context_required,
    switch_context,
    ContextSwitchError,
)
from app.transport import transport_bp, transport_admin_bp
from app.utils.module_guard import module_enabled as check_module_enabled
from app.utils.exceptions import NotFoundError, ServiceUnavailableError, ValidationError
from app.utils.audit import audit_log
from app.transport.services.payment_methods import get_available_payment_methods
from app.transport.services import get_booking_service, get_provider_service, get_dashboard_service
from app.transport.services.go_live_service import can_go_live
from app.transport.services.passenger_service import get_passenger_service
from app.transport.models import Booking, DriverProfile, Vehicle, TransportPassenger, ServiceType
from app.transport.models import (
    ComplianceStatus, VehicleMarketplaceListing, DriverVehicleApplication,
    MarketplaceListingStatus, CompensationModel,
)
from app.extensions import db
from app.transport.services.marketplace_service import get_marketplace_service
from app.identity.services.organization_permissions import OrganizationPermissionService
from app.identity.models.user import User
from app.identity.models.organisation import Organisation

logger = logging.getLogger(__name__)   # noqa: E402


# =========================================================================
# Helpers
# =========================================================================

def _require_ownership(resource, user_id_attr, admin_allowed=True):
    """
    Check if current_user owns the resource or is admin.
    Returns the resource if check passes, otherwise aborts.
    """
    from flask_login import current_user

    if not resource:
        abort(404)

    if not hasattr(resource, user_id_attr):
        abort(404)

    # Admin can access anything if allowed
    if admin_allowed and (
        hasattr(current_user, 'has_global_role')
        and current_user.has_global_role('admin', 'super_admin', 'owner')
    ):
        return resource

    # Check ownership
    if getattr(resource, user_id_attr) != current_user.id:
        logger.warning(f"Ownership check failed: user_id={current_user.id} tried to access resource owned by {getattr(resource, user_id_attr)}")
        abort(403)

    return resource


def _require_vehicle_ownership(vehicle_model):
    """
    Ownership check for vehicles whose owner is a driver profile
    (owner_type='driver', owner_id=DriverProfile.id) or an organisation.
    Admins may access anything.
    """
    from flask_login import current_user

    if not vehicle_model:
        abort(404)

    if hasattr(current_user, 'is_admin') and current_user.is_admin:
        return vehicle_model

    owner_type = getattr(vehicle_model, 'owner_type', None)
    owner_id = getattr(vehicle_model, 'owner_id', None)

    if owner_type == 'driver':
        driver_ids = [d.id for d in DriverProfile.query.filter_by(
            user_id=current_user.id, is_deleted=False
        ).all()]
        if owner_id in driver_ids:
            return vehicle_model
    elif owner_id == current_user.id:
        return vehicle_model

    logger.warning(
        f"Ownership check failed: user_id={current_user.id} tried to access "
        f"vehicle owned by {owner_type}:{owner_id}"
    )
    abort(403)

def _count_open_incidents():
    """Count transport incidents that are still open."""
    from app.transport.models import TransportIncident

    try:
        return TransportIncident.query.filter(
            TransportIncident.is_deleted == False,  # noqa: E712
            TransportIncident.status.in_(["reported", "under_investigation"]),
        ).count()
    except Exception as e:
        logger.warning(f"Unable to count open incidents: {e}")
        return 0


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
# Transport Admin Access Restriction
# All routes rendering transport/base.html require admin roles
# =========================================================================

_PUBLIC_ENDPOINTS = {
    # Public / landing
    "transport.home",
    "transport.new_home",
    "transport.service_detail",
    "transport.api_status",
    "transport.api_estimate_fare",
    "transport.api_availability",
    "transport.api_nearby_drivers",

    # Rider-facing (must be reachable by any authenticated rider)
    "transport.book_transport",
    "transport.bookings_index",
    "transport.bookings_show",
    "transport.bookings_cancel",
    "transport.bookings_edit",
    "transport.bookings_timeline",
    "transport.bookings_payments",
    "transport.become_driver",
    "transport.register_vehicle",
    "transport.vehicle_dashboard",
    "transport.driver_dashboard",
    "transport.driver_dashboard_slash",
    "transport.vehicle_marketplace",
}

@transport_bp.before_request
def _restrict_transport_admin():
    if request.endpoint in _PUBLIC_ENDPOINTS:
        return
    if not current_user.is_authenticated:
        return redirect(url_for("auth.login"))
    from app.auth.helpers import has_global_role
    if not has_global_role(current_user, "owner", "super_admin", "admin", "transport_admin"):
        flash("You do not have permission to access this page.", "danger")
        return redirect(url_for("transport.home"))


# =========================================================================
# Health & Status  (no auth - intentional)
# =========================================================================

@transport_bp.route("/api/status", methods=["GET"])
def api_status():
    """Check transport module status"""
    return jsonify({
        "module": "transport",
        "enabled": check_module_enabled("transport"),
        "timestamp": datetime.now(timezone.utc).isoformat()
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
        "timestamp": datetime.now(timezone.utc).isoformat()
    })


# =========================================================================
# New Home Page API Endpoints  (no auth - intentional for public page)
# =========================================================================

@csrf.exempt
@transport_bp.route("/api/fare/estimate", methods=["POST"])
def api_estimate_fare():
    """Estimate fare for a given trip"""
    from app.transport.services.fare_service import calculate_estimate
    data = request.get_json(force=True) if request.is_json else {}
    service_type = data.get("service_type", "on_demand")
    vehicle_class = data.get("vehicle_class", "economy")
    distance_km = float(data.get("distance_km", 5))

    try:
        breakdown = calculate_estimate(
            service_type=service_type,
            vehicle_class=vehicle_class,
            distance_km=distance_km,
        )
        return jsonify({"success": True, "fare": breakdown})
    except Exception as e:
        logger.error(f"Fare estimation error: {e}")
        return jsonify({"success": False, "error": str(e)}), 400


@csrf.exempt
@transport_bp.route("/api/availability", methods=["GET"])
def api_availability():
    """Get real-time vehicle availability"""
    from app.transport.services.availability_service import available_by_class
    try:
        vehicles = available_by_class()
        return jsonify({"success": True, "vehicles": vehicles})
    except Exception as e:
        logger.error(f"Availability error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@csrf.exempt
@transport_bp.route("/api/drivers/nearby", methods=["GET"])
def api_nearby_drivers():
    """Get nearby active drivers"""
    provider_service = get_provider_service()
    try:
        zone = request.args.get("zone", type=str)
        vehicle_class = request.args.get("vehicle_class", type=str)
        limit = request.args.get("limit", 5, type=int)
        drivers = provider_service.get_available_drivers(
            zone=zone, vehicle_class=vehicle_class, limit=limit
        )
        return jsonify({"success": True, "drivers": drivers})
    except Exception as e:
        logger.error(f"Nearby drivers error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


# =========================================================================
# Public / Fan-facing
# =========================================================================

@transport_bp.route("/", methods=["GET"])
@module_enabled_required("transport")
def home():
    """Transport module homepage with integrated booking form."""
    is_pane = request.args.get('_pane') == '1'

    # Canonical, backend-sourced ride/service types for the front page cards.
    # These come from the real ServiceType enum (app/transport/models.py), never
    # fabricated in the template. Fares are NOT displayed because there is no
    # per-service fare shown before trip details; the booking form/quote flow
    # computes pricing. Honest pre-price messaging is used instead.
    service_labels = {
        "airport_arrival": "Airport Arrival",
        "airport_departure": "Airport Departure",
        "stadium_shuttle": "Stadium Shuttle",
        "hotel_transfer": "Hotel Transfer",
        "city_tour": "City Tour",
        "on_demand": "On-Demand Ride",
        "scheduled_route": "Scheduled Route",
        "custom_tour": "Custom Tour",
    }
    services = [
        {"key": st.value, "name": service_labels.get(st.value, st.value.replace("_", " ").title())}
        for st in ServiceType
    ]

    # Booking form context (prefill from query params so the form works inline)
    pickup_value = request.args.get("pickup_location", "").strip()
    dropoff_value = request.args.get("dropoff_location", "").strip()
    selected_service = request.args.get("service_type", "").strip()

    # User-scoped recent rides. Only surfaced for an authenticated user; never
    # leaks another user's bookings. Anonymous visitors get an honest login CTA.
    recent_rides = []
    ride_count = 0
    is_authenticated = bool(current_user.is_authenticated) if not current_user.is_anonymous else False
    if is_authenticated:
        try:
            booking_service = get_booking_service()
            recent_rides = booking_service.get_user_bookings(current_user.id, limit=5)
            ride_count = booking_service.count_user_bookings(current_user.id)
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error loading user bookings for user_id={_uid()}: {e}")

    logger.info(f"Transport home accessed by user_id={_uid()}, pane={is_pane}")

    # Active drivers count for map display
    active_drivers = 0
    try:
        from app.transport.services.provider_service import get_provider_service
        active_drivers = get_provider_service().count_active_drivers()
    except Exception:
        active_drivers = 0

    ctx = dict(
        title="AFCON Transport & Travel",
        services=services,                    # already there: ServiceType enum
        transport_enabled=check_module_enabled("transport"),
        recent_rides=recent_rides,
        ride_count=ride_count,
        is_authenticated=is_authenticated,
        pickup_value=pickup_value,
        dropoff_value=dropoff_value,
        selected_service=selected_service,
        payment_methods=get_available_payment_methods(
            current_user.id if is_authenticated else None
        ),
        default_service=(
            selected_service
            if selected_service in {s["key"] for s in services}
            else "on_demand"
        ),
        active_drivers=active_drivers,
    )

    return render_template("transport/home.html", **ctx)


@transport_bp.route("/new-home", methods=["GET"])
@module_enabled_required("transport")
def new_home():
    """Temporary new home page for testing - will replace home() when approved."""
    is_pane = request.args.get('_pane') == '1'

    service_labels = {
        "airport_arrival": "Airport Arrival",
        "airport_departure": "Airport Departure",
        "stadium_shuttle": "Stadium Shuttle",
        "hotel_transfer": "Hotel Transfer",
        "city_tour": "City Tour",
        "on_demand": "On-Demand Ride",
        "scheduled_route": "Scheduled Route",
        "custom_tour": "Custom Tour",
    }
    services = [
        {"key": st.value, "name": service_labels.get(st.value, st.value.replace("_", " ").title())}
        for st in ServiceType
    ]

    pickup_value = request.args.get("pickup_location", "").strip()
    dropoff_value = request.args.get("dropoff_location", "").strip()
    selected_service = request.args.get("service_type", "").strip()

    recent_rides = []
    ride_count = 0
    is_authenticated = bool(current_user.is_authenticated) if not current_user.is_anonymous else False
    if is_authenticated:
        try:
            booking_service = get_booking_service()
            recent_rides = booking_service.get_user_bookings(current_user.id, limit=5)
            ride_count = booking_service.count_user_bookings(current_user.id)
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error loading user bookings for user_id={_uid()}: {e}")

    active_drivers = 0
    try:
        from app.transport.services.provider_service import get_provider_service
        active_drivers = get_provider_service().count_active_drivers()
    except Exception:
        active_drivers = 0

    ctx = dict(
        title="AFCON360 - Your Ride, Your Game!",
        services=services,
        transport_enabled=check_module_enabled("transport"),
        recent_rides=recent_rides,
        ride_count=ride_count,
        is_authenticated=is_authenticated,
        pickup_value=pickup_value,
        dropoff_value=dropoff_value,
        selected_service=selected_service,
        payment_methods=get_available_payment_methods(
            current_user.id if is_authenticated else None
        ),
        default_service=(
            selected_service
            if selected_service in {s["key"] for s in services}
            else "on_demand"
        ),
        active_drivers=active_drivers,
    )

    return render_template("transport/new_home.html", **ctx)


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
@transport_bp.route("/dashboard", endpoint="transport_dashboard")
@module_enabled_required("transport")
@login_required
def dashboard_overview():
    """Transport dashboard overview"""
    logger.info(f"Dashboard overview accessed by user_id={_uid()}")
    try:
        ctx = dict(get_dashboard_service().get_cached_admin_dashboard())
    except Exception as e:
        logger.error(
            f"Error building dashboard overview for user_id={_uid()}: {e}",
            exc_info=True,
        )
        ctx = {}

    ctx.setdefault('total_bookings', 0)
    ctx.setdefault('active_drivers', 0)
    ctx.setdefault('available_vehicles', 0)
    ctx.setdefault('recent_bookings', [])

    ctx['open_incidents'] = _count_open_incidents()
    ctx['open_incidents_count'] = ctx['open_incidents']
    ctx['pending_bookings_count'] = ctx.get('pending_bookings', 0)

    return _json_or_template("transport/dashboard/overview.html", **ctx)


@transport_bp.route("/dashboard/performance")
@module_enabled_required("transport")
@login_required
def dashboard_performance():
    """Transport performance dashboard"""
    logger.info(f"Dashboard performance accessed by user_id={_uid()}")
    return _json_or_template("transport/analytics/performance.html")


# =========================================================================
# Marketplace — Owner Application Review (Part A)
# =========================================================================

@transport_bp.route("/listings/<int:listing_id>/applications", methods=["GET"])
@module_enabled_required("transport")
@login_required
def owner_application_review(listing_id):
    """Owner reviews applications for a listing."""
    marketplace_service = get_marketplace_service()
    listing = marketplace_service.get_listing(listing_id)
    if not listing:
        abort(404)

    listing = VehicleMarketplaceListing.query.options(
        joinedload(VehicleMarketplaceListing.vehicle)
    ).filter_by(id=listing_id, is_deleted=False).first()
    if not listing:
        abort(404)

    if not _is_listing_owner(listing):
        abort(403)

    applications = DriverVehicleApplication.query.options(
        joinedload(DriverVehicleApplication.driver)
        .joinedload(DriverProfile.user)
    ).filter(
        DriverVehicleApplication.listing_id == listing_id,
        DriverVehicleApplication.is_deleted == False,
    ).order_by(
        DriverVehicleApplication.applied_at.desc()
    ).all()

    return _json_or_template(
        "transport/owner_application_review.html",
        listing=listing,
        applications=applications,
        vehicle=listing.vehicle,
    )


@transport_bp.route("/listings/<int:listing_id>/applications/<int:application_id>/approve", methods=["POST"])
@module_enabled_required("transport")
@login_required
def owner_application_approve(listing_id, application_id):
    """Owner approves an application."""
    marketplace_service = get_marketplace_service()
    listing = marketplace_service.get_listing(listing_id)
    if not listing:
        abort(404)

    if not _is_listing_owner(listing):
        abort(403)

    application = DriverVehicleApplication.query.filter_by(
        id=application_id, is_deleted=False,
    ).first()
    if not application or application.listing_id != listing_id:
        abort(404)

    try:
        contract = marketplace_service.approve_application(
            application_id=application_id,
            owner_id=listing.owner_id,
        )
        if not contract:
            flash("Failed to approve application", "danger")
        else:
            flash("Application approved", "success")
    except ValueError as ve:
        flash(str(ve), "danger")
    except Exception as e:
        logger.error(f"Approve error: {e}")
        flash("An error occurred", "danger")

    return redirect(url_for("transport.owner_application_review", listing_id=listing_id))


@transport_bp.route("/listings/<int:listing_id>/applications/<int:application_id>/reject", methods=["POST"])
@module_enabled_required("transport")
@login_required
def owner_application_reject(listing_id, application_id):
    """Owner rejects an application."""
    marketplace_service = get_marketplace_service()
    listing = marketplace_service.get_listing(listing_id)
    if not listing:
        abort(404)

    if not _is_listing_owner(listing):
        abort(403)

    application = DriverVehicleApplication.query.filter_by(
        id=application_id, is_deleted=False,
    ).first()
    if not application or application.listing_id != listing_id:
        abort(404)

    try:
        success = marketplace_service.reject_application(
            application_id=application_id,
            owner_id=listing.owner_id,
            reason="Rejected by owner",
        )
        if not success:
            flash("Failed to reject application", "danger")
        else:
            flash("Application rejected", "success")
    except Exception as e:
        logger.error(f"Reject error: {e}")
        flash("An error occurred", "danger")

    return redirect(url_for("transport.owner_application_review", listing_id=listing_id))


def _is_listing_owner(listing):
    """Check if current_user owns the listing (user or organisation member with permission)."""
    # Get the actual user object to access internal ID
    user_obj = current_user._get_current_object()
    # Direct ownership: listing.owner_id references users.id
    if listing.owner_id == user_obj.id:
        return True
    # Organisation ownership: check if listing owner belongs to an org
    # and current user has org.transport.manage permission
    owner_user = db.session.get(User, listing.owner_id)
    if owner_user:
        # Check if owner user has an organisation membership
        from app.identity.models.organisation_member import OrganisationMember
        owner_membership = OrganisationMember.query.filter_by(
            user_id=owner_user.id, is_deleted=False
        ).first()
        if owner_membership:
            organisation = db.session.get(Organisation, owner_membership.organisation_id)
            if organisation:
                return OrganizationPermissionService.has_permission(
                    user_obj, organisation, 'org.transport.manage',
                )
    return False


def _marketplace_listing_views(limit=None):
    """Build the public view objects for the driver marketplace browse surface.

    Listing-backed (Part A): only active + public listings are surfaced, and a
    user's own listings are excluded. Only public display fields are exposed —
    no internal ids, no licence numbers (§12.1). request_url is built
    server-side, so the internal vehicle id never reaches the template.
    """
    query = (
        VehicleMarketplaceListing.query.options(
            joinedload(VehicleMarketplaceListing.vehicle),
        )
        .filter(
            VehicleMarketplaceListing.is_deleted == False,  # noqa: E712
            VehicleMarketplaceListing.listing_status == MarketplaceListingStatus.ACTIVE.value,
            VehicleMarketplaceListing.visibility == "public",
            VehicleMarketplaceListing.owner_id != current_user.id,
        )
        .order_by(VehicleMarketplaceListing.listed_at.desc())
    )
    if limit is not None:
        query = query.limit(limit)
    results = query.all()

    views = []
    for listing in results:
        vehicle = listing.vehicle
        if not vehicle or vehicle.is_deleted:
            continue
        views.append(
            {
                "title": listing.title or (f"{vehicle.make} {vehicle.model}"),
                "make": vehicle.make,
                "model": vehicle.model,
                "year": vehicle.year,
                "status": listing.listing_status.value,
                "description": listing.description,
                "vehicle_class": (
                    vehicle.vehicle_class.value
                    if hasattr(vehicle.vehicle_class, "value")
                    else vehicle.vehicle_class
                ),
                "passenger_capacity": vehicle.passenger_capacity,
                "owner_type_label": _owner_type_label(vehicle.owner_type),
                "compensation_label": _compensation_label(listing),
                "request_url": url_for(
                    "transport_api.vehicle_contract_request",
                    vehicle_id=vehicle.id,
                ),
            }
        )
    return views


def _owner_type_label(owner_type):
    """Human-readable owner label for a listing view object."""
    if owner_type == "organisation":
        return "Organisation"
    if owner_type == "driver":
        return "Driver owner"
    return "Private owner"


def _compensation_label(listing):
    """Human-readable compensation line for a listing view object."""
    value = (
        listing.compensation_model.value
        if hasattr(listing.compensation_model, "value")
        else listing.compensation_model
    )
    if value == CompensationModel.REVENUE_SPLIT.value:
        return f"{float(listing.driver_revenue_share_pct):g}% revenue share"
    if value == CompensationModel.FIXED_RENTAL.value:
        amount = float(listing.fixed_rental_amount or 0)
        frequency = listing.rental_frequency or ""
        return f"Fixed rental UGX {amount:,.0f}{' / ' + frequency if frequency else ''}"
    if value == CompensationModel.HYBRID.value:
        return (
            f"{float(listing.driver_revenue_share_pct):g}% revenue share"
            + (f" + UGX {float(listing.fixed_rental_amount or 0):,.0f}" if listing.fixed_rental_amount else "")
        )
    return "Compensation per agreement"


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
def bookings_new():
    """Retired: /transport/ is now the only rider booking entry."""
    return redirect(url_for("transport.home"), code=301)


@transport_bp.route("/book", methods=["GET", "POST"])
@module_enabled_required("transport")
@login_required
@require_profile_completion
@require_kyc_tier(2)  # Tier 2 required for booking transport
@rate_limit("book_transport", per_minute=5)
def book_transport():
    """Submit a booking"""
    if request.method == "GET":
        # Cross-domain return journey: remember a safe local "back to" target
        # (e.g. a guest roster that called "Book Transport"). The value is
        # honored on successful booking so the operator lands back on the
        # assignment page with the fresh resource list loaded.
        _capture_return_to("transport_book_return_to")
        return render_template("transport/book.html")

    try:
        from app.schemas.transport import BookingSchema
        data = BookingSchema().load(request.form)
    except ImportError:
        logger.warning("BookingSchema not found - using raw form data")
        data = request.form.to_dict()
    except ValidationError as err:
        logger.warning(f"Booking validation failed for user_id={_uid()}: {err.messages}")
        for error in err.messages.values():
            flash(error[0], "danger")
        return redirect(url_for("transport.book_transport"))

    try:
        booking = get_booking_service().create_booking(current_user.id, data)
        ref = booking["data"]["booking_reference"]
        booking_id = booking["data"]["booking_id"]
        logger.info(f"Booking created: user_id={_uid()}, ref={ref}")
        flash(f"Booking confirmed! Reference: {ref}", "success")
        return_to = session.pop("transport_book_return_to", None)
        if return_to:
            return redirect(return_to)
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


def _capture_return_to(session_key: str):
    """Store only a root-relative, same-origin path in the session. Absolute
    URLs and protocol-relative URLs are rejected (open-redirect guard)."""
    target = (request.args.get("next") or "").strip()
    if target.startswith("/") and not target.startswith("//"):
        session[session_key] = target


@transport_bp.route("/bookings/<int:id>")
@module_enabled_required("transport")
@login_required
def bookings_show(id):
    """View booking details"""
    try:
        # Get booking model with ownership check
        from app.transport.models import Booking
        booking_model = db.session.get(Booking, id)

        if not booking_model:
            if request.is_json:
                return jsonify({"status": "error", "message": "Booking not found"}), 404
            flash("Booking not found", "warning")
            return redirect(url_for("transport.bookings_index"))

        # Check ownership
        _require_ownership(booking_model, "user_id")

        # Get service representation
        booking = get_booking_service().get_booking(id)

        # Rider live-tracking approval (GEO rider node): the same
        # Transport-owned subject decision as the booking stream, so
        # the page never offers tracking the stream would deny.
        tracking_allowed = False
        tracking_booking_ref = None
        try:
            from flask_login import current_user as _cu
            from app.auth.helpers import has_global_role as _hgr
            from app.transport.services.tracking_service import (
                TrackingService as _TS)
            _subject = _TS.get_rider_tracking_subject(
                booking_model.booking_reference, int(_cu.id),
                bool(_hgr(_cu, "admin", "super_admin", "owner")))
            tracking_allowed = bool(_subject.get("allowed"))
            if tracking_allowed:
                tracking_booking_ref = booking_model.booking_reference
        except Exception:
            tracking_allowed = False
            tracking_booking_ref = None

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error loading booking {id} for user_id={_uid()}: {e}")
        booking = None

    if not booking:
        if request.is_json:
            return jsonify({"status": "error", "message": "Booking not found"}), 404
        flash("Booking not found", "warning")
        return redirect(url_for("transport.bookings_index"))

    return _json_or_template("transport/bookings/show.html", booking=booking, id=id,
                             tracking_allowed=tracking_allowed,
                             tracking_booking_ref=tracking_booking_ref)


@transport_bp.route("/bookings/<int:id>/cancel", methods=["POST"])
@module_enabled_required("transport")
@login_required
def bookings_cancel(id):
    """Passenger cancel binding (Policy A, TH-3-D2).

    A passenger may cancel only while the booking is in a pre-assignment
    status (PENDING_PAYMENT / CONFIRMED). The service applies the atomic
    Race-E status gate (conditional UPDATE, rowcount == 1); once a driver
    has been assigned the booking is no longer passenger-cancellable.
    """
    try:
        booking_model = db.session.get(Booking, id)
        if not booking_model:
            abort(404)
        _require_ownership(booking_model, "user_id")

        result = get_booking_service().cancel_booking(
            id, user_id=current_user.id, reason="passenger_request"
        )
        audit_log(action="booking_cancelled_passenger", resource_type="booking",
                  resource_id=id, user_id=current_user.id,
                  details={"status": "cancelled", "source": "passenger"})
        logger.info(f"Booking {id} cancelled by passenger user_id={_uid()}")
        if request.is_json:
            return jsonify({"status": "success", **result}), 200
        flash("Booking cancelled successfully", "success")
    except ValidationError as e:
        logger.warning(f"Passenger cancel booking {id} rejected: {e}")
        if request.is_json:
            return jsonify({"status": "error", "message": str(e)}), 409
        flash(str(e), "danger")
    except PermissionError as e:
        logger.warning(f"Passenger cancel booking {id} forbidden: {e}")
        if request.is_json:
            return jsonify({"status": "error", "message": str(e)}), 403
        flash(str(e), "danger")
    except NotFoundError as e:
        if request.is_json:
            return jsonify({"status": "error", "message": str(e)}), 404
        flash(str(e), "warning")
    except Exception as e:
        db.session.rollback()
        logger.error(f"Unexpected error while passenger cancelled booking {id}: {e}", exc_info=True)
        if request.is_json:
            return jsonify({"status": "error", "message": "Unable to cancel booking"}), 500
        flash("Unable to cancel booking", "danger")

    return redirect(url_for("transport.bookings_show", id=id))


# ---------------------------------------------------------------------------
# Stage 5 – cross-domain accommodation coordination (TASK2: Transport → Accommodation)
# ---------------------------------------------------------------------------

@transport_bp.route("/bookings/<int:booking_id>/passengers/accommodation/pane", methods=["GET"], endpoint="booking_accommodation_pane")
@module_enabled_required("transport")
@login_required
def booking_accommodation_pane(booking_id):
    """Read-side pane data for the booking show page: every passenger plus its
    accommodation assignment summary."""
    from app.transport.models import Booking
    from app.transport.services.accommodation_coordination import (
        PassengerAccommodationCoordinationService,
        TransportAccommodationCoordinationError,
    )
    try:
        booking_model = db.session.get(Booking, booking_id)
        if not booking_model:
            return jsonify({"success": False, "error": "Booking not found"}), 404
        _require_ownership(booking_model, "user_id")
        result = PassengerAccommodationCoordinationService.pane(current_user, booking_id)
        for item in result.get("items", []):
            item["assign_url"] = url_for(
                "transport.assign_accommodation_for_passenger",
                booking_id=booking_id,
                passenger_id=item["passenger_id"],
            )
            item["unassign_url"] = url_for(
                "transport.unassign_accommodation_for_passenger",
                booking_id=booking_id,
                passenger_id=item["passenger_id"],
            )
        return jsonify({"success": True, **result})
    except TransportAccommodationCoordinationError as exc:
        return jsonify({"success": False, "code": exc.code, "error": exc.message}), 400
    except Exception:
        logger.exception("Accommodation pane failed for transport booking %s", booking_id)
        return jsonify({"success": False, "error": "The accommodation pane could not be loaded"}), 500


@transport_bp.route("/bookings/<int:booking_id>/passengers/accommodation/available", methods=["GET"], endpoint="booking_accommodation_available")
@module_enabled_required("transport")
@login_required
def booking_accommodation_available(booking_id):
    """Eligible Accommodation bookings owned by the current user, for the
    assign dropdown on the booking show page.

    Read-only cross-module query: Transport presents candidate target
    resources from the operator's own accommodation bookings, but
    Accommodation revalidates ownership/status/room/capacity atomically on
    every assignment — this list is a convenience for the operator, never a
    gate. The only client input on assignment is one of the booking references
    returned here."""
    from app.transport.services.accommodation_coordination import (
        PassengerAccommodationCoordinationService,
        ACCOMMODATION_ASSIGNABLE_STATUSES,
        _module_available,
        _status_value,
    )
    booking_model = db.session.get(Booking, booking_id)
    if not booking_model:
        return jsonify({"success": False, "error": "Booking not found"}), 404
    _require_ownership(booking_model, "user_id")

    items = []
    count_total = 0
    if _module_available("accommodation"):
        from app.accommodation.models.booking import AccommodationBooking

        owned = AccommodationBooking.query.filter(
            AccommodationBooking.is_deleted == False,  # noqa: E712
            db.or_(
                AccommodationBooking.booked_by_user_id == current_user.id,
                AccommodationBooking.booking_owner_id == current_user.id,
            ),
        ).all()
        count_total = len(owned)
        for candidate in owned:
            status = _status_value(getattr(candidate, "status", ""))
            if status not in ACCOMMODATION_ASSIGNABLE_STATUSES:
                continue
            entry = PassengerAccommodationCoordinationService._accommodation_summary(candidate)
            entry["status"] = status
            items.append(entry)
    return jsonify({
        "success": True,
        "count_total": count_total,
        "items": items,
        "assignable": sorted(ACCOMMODATION_ASSIGNABLE_STATUSES),
        "book_url": url_for(
            "accommodation.guest_search",
            next=url_for("transport.bookings_show", id=booking_id),
        ),
    })


def _accommodation_coordination_redirect(booking_id: int, *, unassign: bool = False, assignment_info: dict | None = None):
    """Post-change navigational fallback: flash and return to the booking show
    page (the assignment page) instead of a JSON response."""
    if assignment_info:
        passenger_name = assignment_info.get("passenger_name") or "Passenger"
        accommodation_ref = assignment_info.get("accommodation_booking_ref") or ""
        flash_message = (
            f"Accommodation assignment confirmed: {passenger_name} → "
            f"accommodation booking {accommodation_ref}."
        )
    else:
        flash_message = (
            "Accommodation booking assignment released."
            if unassign else
            "Accommodation booking assigned to the passenger."
        )
    flash(flash_message, "success")
    return redirect(url_for("transport.bookings_show", id=booking_id))


@transport_bp.route("/bookings/<int:booking_id>/passengers/<int:passenger_id>/accommodation/assign", methods=["POST"], endpoint="assign_accommodation_for_passenger")
@module_enabled_required("transport")
@login_required
def assign_accommodation_for_passenger(booking_id, passenger_id):
    """Assign an accommodation booking to a transport passenger."""
    from app.transport.services.accommodation_coordination import (
        PassengerAccommodationCoordinationService,
        TransportAccommodationCoordinationError,
    )
    if not request.is_json:
        ref = request.form.get("accommodation_booking_ref") or request.form.get("ref") or ""
        if not ref:
            flash("An accommodation booking reference is required", "danger")
            return _accommodation_coordination_redirect(booking_id)
        try:
            from app.transport.models import Booking
            booking_model = db.session.get(Booking, booking_id)
            if not booking_model:
                return _accommodation_coordination_redirect(booking_id)
            _require_ownership(booking_model, "user_id")
            result = PassengerAccommodationCoordinationService.assign_accommodation(
                current_user,
                transport_booking_id=booking_id,
                passenger_id=passenger_id,
                accommodation_booking_ref=ref,
            )
            return _accommodation_coordination_redirect(
                booking_id, assignment_info=result.get("assignment_info")
            )
        except TransportAccommodationCoordinationError as exc:
            db.session.rollback()
            flash(exc.message, "danger")
        except Exception:
            db.session.rollback()
            logger.exception("Accommodation assign failed for transport booking %s", booking_id)
            flash("The accommodation assignment could not be completed", "danger")
        return _accommodation_coordination_redirect(booking_id)
    try:
        from app.transport.models import Booking
        booking_model = db.session.get(Booking, booking_id)
        if not booking_model:
            return jsonify({"success": False, "error": "Booking not found"}), 404
        _require_ownership(booking_model, "user_id")
        data = request.get_json(silent=True) or {}
        ref = data.get("accommodation_booking_ref") or data.get("ref") or ""
        if not ref:
            return jsonify({"success": False, "error": "accommodation_booking_ref is required"}), 400
        result = PassengerAccommodationCoordinationService.assign_accommodation(
            current_user,
            transport_booking_id=booking_id,
            passenger_id=passenger_id,
            accommodation_booking_ref=ref,
        )
        return jsonify({"success": True, **result})
    except TransportAccommodationCoordinationError as exc:
        db.session.rollback()
        return jsonify({"success": False, "code": exc.code, "error": exc.message}), 400
    except Exception as exc:
        db.session.rollback()
        logger.exception("Accommodation assign failed for transport booking %s", booking_id)
        return jsonify({"success": False, "error": str(exc)}), 500


@transport_bp.route("/bookings/<int:booking_id>/passengers/<int:passenger_id>/accommodation/unassign", methods=["POST"], endpoint="unassign_accommodation_for_passenger")
@module_enabled_required("transport")
@login_required
def unassign_accommodation_for_passenger(booking_id, passenger_id):
    """Release the accommodation booking assignment from a transport passenger."""
    from app.transport.services.accommodation_coordination import (
        PassengerAccommodationCoordinationService,
        TransportAccommodationCoordinationError,
    )
    if not request.is_json:
        try:
            from app.transport.models import Booking
            booking_model = db.session.get(Booking, booking_id)
            if booking_model is None:
                return _accommodation_coordination_redirect(booking_id)
            _require_ownership(booking_model, "user_id")
            PassengerAccommodationCoordinationService.unassign_accommodation(
                current_user,
                transport_booking_id=booking_id,
                passenger_id=passenger_id,
            )
        except TransportAccommodationCoordinationError as exc:
            db.session.rollback()
            flash(exc.message, "danger")
        except Exception:
            db.session.rollback()
            logger.exception("Accommodation unassign failed for transport booking %s", booking_id)
            flash("The accommodation unassignment could not be completed", "danger")
        return _accommodation_coordination_redirect(booking_id, unassign=True)
    try:
        from app.transport.models import Booking
        booking_model = db.session.get(Booking, booking_id)
        if not booking_model:
            return jsonify({"success": False, "error": "Booking not found"}), 404
        _require_ownership(booking_model, "user_id")
        result = PassengerAccommodationCoordinationService.unassign_accommodation(
            current_user,
            transport_booking_id=booking_id,
            passenger_id=passenger_id,
        )
        return jsonify({"success": True, **result})
    except TransportAccommodationCoordinationError as exc:
        db.session.rollback()
        return jsonify({"success": False, "code": exc.code, "error": exc.message}), 400
    except Exception as exc:
        db.session.rollback()
        logger.exception("Accommodation unassign failed for transport booking %s", booking_id)
        return jsonify({"success": False, "error": str(exc)}), 500


@transport_bp.route("/bookings/<int:id>/edit")
@module_enabled_required("transport")
@login_required
def bookings_edit(id):
    """Edit a booking"""
    # Check ownership first
    booking_model = db.session.get(Booking, id)
    if not booking_model:
        abort(404)
    _require_ownership(booking_model, "user_id")

    logger.info(f"Booking edit {id} accessed by user_id={_uid()}")
    return _json_or_template("transport/bookings/edit.html", id=id)


@transport_bp.route("/bookings/<int:id>/timeline")
@module_enabled_required("transport")
@login_required
def bookings_timeline(id):
    """Booking event timeline"""
    # Check ownership first
    booking_model = db.session.get(Booking, id)
    if not booking_model:
        abort(404)
    _require_ownership(booking_model, "user_id")

    logger.info(f"Booking timeline {id} accessed by user_id={_uid()}")
    return _json_or_template("transport/bookings/timeline.html", id=id)


@transport_bp.route("/bookings/<int:id>/payments")
@module_enabled_required("transport")
@login_required
def bookings_payments(id):
    """Booking payment details"""
    # Check ownership first
    booking_model = db.session.get(Booking, id)
    if not booking_model:
        abort(404)
    _require_ownership(booking_model, "user_id")

    logger.info(f"Booking payments {id} accessed by user_id={_uid()}")
    return _json_or_template("transport/bookings/payments.html", id=id)


# =========================================================================
# Passengers (booker/coordinator management + secure claim)
# =========================================================================

@transport_bp.route("/bookings/<int:booking_id>/passengers", methods=["POST"])
@module_enabled_required("transport")
@login_required
def passenger_add(booking_id):
    """Add passengers to a booking (booker or authorised coordinator).
    Supports accountless passengers (name/email/phone only)."""
    booking = db.session.get(Booking, booking_id)
    if not booking:
        return jsonify({"status": "error", "message": "Booking not found"}), 404
    _require_ownership(booking, "user_id")

    data = request.get_json(silent=True) or request.form.to_dict()
    svc = get_passenger_service()

    raw_uid = data.get("user_id")
    try:
        linked_uid = int(raw_uid) if raw_uid not in (None, "", "None") else None
    except (TypeError, ValueError):
        linked_uid = None

    try:
        passenger = svc.add_passenger(
            booking,
            name=data.get("name"),
            email=data.get("email") or None,
            phone=data.get("phone") or None,
            user_id=linked_uid,
            seat_label=data.get("seat_label") or None,
        )
        db.session.commit()
    except ValidationError as err:
        db.session.rollback()
        return jsonify({"status": "error", "message": str(getattr(err, "message", err))}), 400
    except Exception as e:
        db.session.rollback()
        logger.error(f"Passenger add failed for user_id={_uid()}: {e}")
        return jsonify({"status": "error", "message": str(e)}), 400

    return jsonify({"status": "ok", "passenger": svc.serialize(passenger)}), 201


@transport_bp.route("/bookings/<int:booking_id>/passengers")
@module_enabled_required("transport")
@login_required
def passenger_list(booking_id):
    """List passengers for a booking (booker or authorised coordinator)."""
    booking = db.session.get(Booking, booking_id)
    if not booking:
        return jsonify({"status": "error", "message": "Booking not found"}), 404
    _require_ownership(booking, "user_id")

    svc = get_passenger_service()
    passengers = svc.passengers_for_booking(int(booking.id))
    return jsonify({
        "status": "ok",
        "passengers": [svc.serialize(p) for p in passengers],
    })


@transport_bp.route("/bookings/<int:booking_id>/passengers/bulk", methods=["POST"])
@module_enabled_required("transport")
@login_required
def passenger_bulk_add(booking_id):
    """Bulk add multiple passengers at once (booker or authorised coordinator).
    Supports group/multi-passenger bookings; capacity is enforced per assignment."""
    booking = db.session.get(Booking, booking_id)
    if not booking:
        return jsonify({"status": "error", "message": "Booking not found"}), 404
    _require_ownership(booking, "user_id")

    data = request.get_json(silent=True) or {}
    passengers = data.get("passengers", []) if isinstance(data, dict) else data
    if not isinstance(passengers, list) or not passengers:
        return jsonify({"status": "error", "message": "passengers list required"}), 400

    svc = get_passenger_service()
    try:
        created = svc.bulk_add_passengers(booking, passengers)
        db.session.commit()
    except ValidationError as err:
        db.session.rollback()
        return jsonify({"status": "error", "message": str(getattr(err, "message", err))}), 400
    except Exception as e:
        db.session.rollback()
        logger.error(f"Bulk passenger add failed for user_id={_uid()}: {e}")
        return jsonify({"status": "error", "message": str(e)}), 400

    return jsonify({"status": "ok", "created": len(created),
                    "passengers": [svc.serialize(p) for p in created]}), 201


@transport_bp.route("/passengers/<int:passenger_id>/claim-token", methods=["POST"])
@module_enabled_required("transport")
@login_required
def passenger_issue_claim_token(passenger_id):
    """Issue a single-use, expiry-bound claim token for a passenger (booker only).
    Requires the passenger to have an email or phone for secure recipient binding."""
    passenger = db.session.get(TransportPassenger, passenger_id)
    if not passenger:
        return jsonify({"status": "error", "message": "Passenger not found"}), 404
    booking = db.session.get(Booking, passenger.booking_id)
    if not booking:
        return jsonify({"status": "error", "message": "Booking not found"}), 404
    _require_ownership(booking, "user_id")

    svc = get_passenger_service()
    try:
        token = svc.create_claim_token(passenger)
        db.session.commit()
    except ValidationError as err:
        db.session.rollback()
        return jsonify({"status": "error", "message": str(getattr(err, "message", err))}), 400
    except Exception as e:
        db.session.rollback()
        logger.error(f"Claim token issue failed for user_id={_uid()}: {e}")
        return jsonify({"status": "error", "message": str(e)}), 400

    return jsonify({"status": "ok", "claim_token": token})


@transport_bp.route("/passenger/claim/<string:passenger_public_id>/<token>", methods=["GET"])
@module_enabled_required("transport")
@login_required
def passenger_claim_landing(passenger_public_id, token):
    """Landing page for a claim token. Requires authentication so the claim is
    bound to an AFCON360 user account (never a public form)."""
    svc = get_passenger_service()
    try:
        passenger = svc.validate_claim_token(passenger_public_id, token)
    except (ValidationError, PermissionError, NotFoundError) as err:
        flash(str(getattr(err, "message", err)), "danger")
        return redirect(url_for("transport.bookings_index"))
    return render_template("transport/passengers/claim.html",
                           passenger=passenger, token=token)


@transport_bp.route("/passenger/claim/<string:passenger_public_id>/<token>", methods=["POST"])
@module_enabled_required("transport")
@login_required
def passenger_claim(passenger_public_id, token):
    """Bind a claim token to the currently authenticated user (single-use)."""
    svc = get_passenger_service()
    try:
        passenger = svc.claim_with_token(passenger_public_id, token, current_user)
        db.session.commit()
    except (ValidationError, PermissionError, NotFoundError) as err:
        db.session.rollback()
        flash(str(getattr(err, "message", err)), "danger")
        return redirect(url_for("transport.home"))
    flash("Passenger linked to your account", "success")
    return redirect(url_for("transport.bookings_show", id=passenger.booking_id))


@transport_bp.route("/passengers/<int:passenger_id>/assign", methods=["POST"])
@module_enabled_required("transport")
@login_required
def passenger_assign_vehicle(passenger_id):
    """Assign (or reassign) a passenger to a specific vehicle, enforcing capacity
    and booking passenger-count bounds. Supports multi-vehicle group assignment."""
    passenger = db.session.get(TransportPassenger, passenger_id)
    if not passenger:
        return jsonify({"status": "error", "message": "Passenger not found"}), 404
    booking = db.session.get(Booking, passenger.booking_id)
    if not booking:
        return jsonify({"status": "error", "message": "Booking not found"}), 404
    _require_ownership(booking, "user_id")

    data = request.get_json(silent=True) or request.form.to_dict()
    vehicle_id = data.get("vehicle_id") or data.get("assigned_vehicle_id")
    try:
        vehicle_id = int(vehicle_id)
    except (TypeError, ValueError):
        return jsonify({"status": "error", "message": "vehicle_id required"}), 400

    vehicle = db.session.get(Vehicle, vehicle_id)
    if not vehicle or vehicle.is_deleted:
        return jsonify({"status": "error", "message": "Vehicle not found"}), 404

    svc = get_passenger_service()
    try:
        passenger = svc.assign_vehicle(passenger, vehicle, booking=booking)
        db.session.commit()
    except ValidationError as err:
        db.session.rollback()
        return jsonify({"status": "error", "message": str(getattr(err, "message", err))}), 400
    except Exception as e:
        db.session.rollback()
        logger.error(f"Passenger assign failed for user_id={_uid()}: {e}")
        return jsonify({"status": "error", "message": str(e)}), 400

    return jsonify({"status": "ok", "passenger": svc.serialize(passenger)})


# =========================================================================
# Drivers
# =========================================================================

@transport_bp.route("/drivers")
@module_enabled_required("transport")
@login_required
@admin_required
def drivers_index():
    """Drivers index"""
    logger.info(f"Drivers index accessed by user_id={_uid()}")
    return _json_or_template("transport/drivers/index.html")


@transport_bp.route("/drivers/new")
@module_enabled_required("transport")
@login_required
@admin_required
def drivers_new():
    """New driver form"""
    return render_template("transport/drivers/new.html")


@transport_bp.route("/become-driver", methods=["GET", "POST"])
@module_enabled_required("transport")
@login_required
@require_profile_completion
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
        result = get_provider_service().register_driver(
            user_id=current_user.id,
            driver_data=data,
        )
        driver_id = result['data']['driver_id']
        logger.info(f"Driver registered: user_id={_uid()}, driver_id={driver_id}")
        driver = db.session.get(DriverProfile, driver_id)
        driver_public_id = getattr(driver, "public_id", None) or getattr(
            driver, "driver_code", None
        )

        if driver_public_id:
            try:
                switch_context(current_user, {
                    "type": "driver",
                    "public_id": str(driver_public_id),
                })
            except ContextSwitchError:
                return redirect(url_for("transport.driver_dashboard"))

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
@admin_required
def drivers_show(id):
    """View driver profile"""
    try:
        # Get driver model with ownership check
        driver_model = db.session.get(DriverProfile, id)

        if not driver_model:
            if request.is_json:
                return jsonify({"status": "error", "message": "Driver not found"}), 404
            flash("Driver not found", "warning")
            return redirect(url_for("transport.drivers_index"))

        # Check ownership (driver.user_id) or admin
        _require_ownership(driver_model, "user_id", admin_allowed=True)

        # Get service representation
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
@admin_required
def drivers_edit(id):
    """Edit driver profile"""
    logger.info(f"Driver edit {id} accessed by user_id={_uid()}")
    return _json_or_template("transport/drivers/edit.html", id=id)


@transport_bp.route("/drivers/<int:id>/location")
@module_enabled_required("transport")
@login_required
@admin_required
def drivers_location(id):
    """Driver live location"""
    logger.info(f"Driver location {id} accessed by user_id={_uid()}")
    try:
        # GEO-14 CASE C repair: the template dereferences `driver`
        # (code, status, last location); the route previously passed only
        # `id`, so every visit raised UndefinedError ('driver' undefined).
        # Load the model the same way drivers_show does.
        driver_model = db.session.get(DriverProfile, id)

        if not driver_model:
            if request.is_json:
                return jsonify({"status": "error", "message": "Driver not found"}), 404
            flash("Driver not found", "warning")
            return redirect(url_for("transport.drivers_index"))

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error loading driver location {id} for user_id={_uid()}: {e}")

        if request.is_json:
            return jsonify({"status": "error", "message": "Driver not found"}), 404
        flash("Driver not found", "warning")
        return redirect(url_for("transport.drivers_index"))

    return _json_or_template("transport/drivers/location.html", driver=driver_model, id=id)


@transport_bp.route("/drivers/<int:id>/verification")
@module_enabled_required("transport")
@login_required
@admin_required
def drivers_verification(id):
    """Driver verification details"""
    logger.info(f"Driver verification {id} accessed by user_id={_uid()}")
    return _json_or_template("transport/drivers/verification.html", id=id)


@transport_bp.route("/driver-dashboard")
@module_enabled_required("transport")
@login_required
@active_context_required(ContextType.DRIVER)
def driver_dashboard():
    """Driver's personal dashboard (Driver Workspace home).

    Presentation-only consolidation (Phase C): the view reuses the existing
    transport services and adds no business logic. Workspace entry stays a
    PARTICIPATION capability — ``@active_context_required(ContextType.DRIVER)``
    above is unchanged, and go-live readiness remains composed solely by
    ``can_go_live``. Operational data (earnings, owned vs assigned vehicles,
    upcoming/recent bookings) is surfaced from the authoritative services so
    the home presents one coherent driver workspace instead of admin links.
    """
    provider_service = get_provider_service()
    booking_service = get_booking_service()
    try:
        profile = provider_service.get_driver_profile(current_user.id)
        approved = bool(
            profile and profile.compliance_status == ComplianceStatus.APPROVED
        )
        bookings = (
            booking_service.get_driver_bookings(current_user.id) if approved else []
        )
        upcoming = (
            booking_service.get_driver_upcoming_bookings(current_user.id, limit=5)
            if approved
            else []
        )
        recent = (
            booking_service.get_driver_recent_bookings(current_user.id, limit=5)
            if approved
            else []
        )
        earnings = (
            booking_service.get_driver_earnings(current_user.id) if profile else 0.0
        )
        owned_vehicles = (
            provider_service.get_user_vehicles(current_user.id) if profile else []
        )
        assigned_vehicle = profile.current_vehicle if profile else None
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error loading driver dashboard for user_id={_uid()}: {e}")
        profile = None
        bookings = []
        upcoming = []
        recent = []
        earnings = 0.0
        owned_vehicles = []
        assigned_vehicle = None

    # GO-LIVE capability: entering the Driver Workspace is participation;
    # going online composes the authoritative readiness gates. The result is
    # rendered to the template so the online toggle is disabled and the
    # checklist panel is shown until every required gate passes.
    go_live = can_go_live(profile) if profile is not None else None

    # Marketplace "Find Vehicle" section (Part A): listing-backed, in sync with
    # the browse page's source. Never fed from a raw Vehicle query.
    available_marketplace_vehicles = _marketplace_listing_views(limit=5)

    return _json_or_template(
        "transport/driver/driver_dashboard.html",
        driver_profile=profile,
        bookings=bookings,
        upcoming=upcoming,
        recent=recent,
        earnings=earnings,
        owned_vehicles=owned_vehicles,
        assigned_vehicle=assigned_vehicle,
        go_live=go_live,
        available_marketplace_vehicles=available_marketplace_vehicles,
    )


@transport_bp.route("/driver/dashboard")
@module_enabled_required("transport")
@login_required
@active_context_required(ContextType.DRIVER)
def driver_dashboard_slash():
    """Alias of driver_dashboard.

    Legacy duplicate of the working `driver_dashboard` route. Its original
    body referenced `Trip`, `DriverAvailability`, and `Vehicle.driver_id`,
    none of which exist in the current transport model, so every request
    raised ImportError (500). Redirect to the canonical route instead.
    """
    return redirect(url_for("transport.driver_dashboard"))


@transport_bp.route("/vehicle-marketplace")
@module_enabled_required("transport")
@login_required
@active_context_required(ContextType.DRIVER)
def vehicle_marketplace():
    """Driver marketplace browse: active + public listings seeking drivers.

    Listing-backed (Part A): queries VehicleMarketplaceListing (not raw
    Vehicle). Only ACTIVE + public listings are shown; a user's own listings
    are excluded by the view builder's filter. Display-only — the request
    action is handled by the delegated JS calling the existing request-contract
    API (server-built data-url; no internal ids rendered, §12.1).
    """
    marketplace_vehicles = _marketplace_listing_views()
    return render_template(
        "transport/vehicle_marketplace.html",
        marketplace_vehicles=marketplace_vehicles,
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
@require_profile_completion
@require_kyc_tier(3)  # Tier 3 required to register a vehicle
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
        svc = get_provider_service()
        driver = svc.get_driver_profile(current_user.id)
        if not driver:
            raise ValidationError(
                "You must be a registered driver to register a vehicle"
            )
        result = svc.register_vehicle(
            owner_type='driver',
            owner_id=driver.id,
            vehicle_data=data,
        )
        vehicle_id = result['data']['vehicle_id']
        logger.info(f"Vehicle registered: user_id={_uid()}, vehicle_id={vehicle_id}")
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
        # Get vehicle model with ownership check
        vehicle_model = db.session.get(Vehicle, id)

        if not vehicle_model:
            if request.is_json:
                return jsonify({"status": "error", "message": "Vehicle not found"}), 404
            flash("Vehicle not found", "warning")
            return redirect(url_for("transport.vehicles_index"))

        # Check ownership (vehicle owner driver/organisation) or admin
        _require_vehicle_ownership(vehicle_model)

        # Get service representation
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
@require_profile_completion
@require_kyc_tier(3)  # Tier 3 required to manage vehicles
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
    """Incident investigation panel - admin only"""
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
    """New organisation form - admin only"""
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
    """New route form - admin only"""
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
    # Provide default context to avoid template errors
    ctx = {
        "tab": "overview",
        "current_days": 30,
        "from_date": "",
        "to_date": "",
        "summary": {
            "total_bookings": 0,
            "completion_rate": 0,
            "avg_rating": "-",
            "total_revenue": "0",
            "on_time_rate": 0,
        },
        "chart_labels": [],
        "chart_bookings": [],
        "chart_revenue": [],
        "service_labels": [],
        "service_data": [],
        "chart_ontime": [],
        "top_drivers": [],
    }
    return _json_or_template("transport/analytics/index.html", **ctx)


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
    """Settings - admin only"""
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
# Admin - Bookings
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
        audit_log(action="booking_cancelled_admin", resource_type="booking",
                  resource_id=booking_id, user_id=current_user.id, details={"status": "cancelled"})
        flash(f"Booking {booking_id} cancelled successfully", "success")

    except NotFoundError as e:
        logger.warning(f"Cancel booking {booking_id} - not found - user_id={_uid()}: {e}")
        flash(str(e), "danger")

    except ServiceUnavailableError as e:
        logger.error(f"Service unavailable cancelling booking {booking_id} - user_id={_uid()}: {e}", exc_info=True)
        flash("Booking service unavailable", "danger")

    except ValidationError as e:
        logger.warning(f"Validation error cancelling booking {booking_id} - user_id={_uid()}: {e}")
        flash(str(e), "danger")

    except Exception as e:
        db.session.rollback()
        logger.error(f"Unexpected error cancelling booking {booking_id} - user_id={_uid()}: {e}", exc_info=True)
        flash("Unexpected error cancelling booking", "danger")

    return redirect(url_for("transport_admin.list_bookings"))


# -------------------------------------------------------------------------
# Admin - Drivers
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
    """Filtered drivers list - used for ?status=pending, ?online=true"""
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
        audit_log(action="driver_approved", resource_type="driver",
                  resource_id=driver_id, user_id=current_user.id, details={"status": "approved"})
        flash(f"Driver {driver_id} approved", "success")

    except NotFoundError as e:
        logger.warning(f"Approve driver {driver_id} - not found - user_id={_uid()}: {e}")
        flash(str(e), "danger")

    except ValidationError as e:
        logger.warning(f"Validation error approving driver {driver_id} - user_id={_uid()}: {e}")
        flash(str(e), "danger")

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error approving driver {driver_id} - user_id={_uid()}: {e}", exc_info=True)
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
        audit_log(action="driver_rejected", resource_type="driver",
                  resource_id=driver_id, user_id=current_user.id, details={"status": "rejected"})
        flash(f"Driver {driver_id} rejected", "warning")

    except NotFoundError as e:
        logger.warning(f"Reject driver {driver_id} - not found - user_id={_uid()}: {e}")
        flash(str(e), "danger")

    except ValidationError as e:
        logger.warning(f"Validation error rejecting driver {driver_id} - user_id={_uid()}: {e}")
        flash(str(e), "danger")

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error rejecting driver {driver_id} - user_id={_uid()}: {e}", exc_info=True)
        flash("Unable to reject driver", "danger")

    return redirect(url_for("transport_admin.list_drivers"))


# -------------------------------------------------------------------------
# Admin - Vehicles
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
        audit_log(action="vehicle_approved", resource_type="vehicle",
                  resource_id=vehicle_id, user_id=current_user.id, details={"status": "approved"})
        flash(f"Vehicle {vehicle_id} approved", "success")

    except NotFoundError as e:
        logger.warning(f"Approve vehicle {vehicle_id} - not found - user_id={_uid()}: {e}")
        flash(str(e), "danger")

    except ValidationError as e:
        logger.warning(f"Validation error approving vehicle {vehicle_id} - user_id={_uid()}: {e}")
        flash(str(e), "danger")

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error approving vehicle {vehicle_id} - user_id={_uid()}: {e}", exc_info=True)
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
        audit_log(action="vehicle_rejected", resource_type="vehicle",
                  resource_id=vehicle_id, user_id=current_user.id, details={"status": "rejected"})
        flash(f"Vehicle {vehicle_id} rejected", "warning")

    except NotFoundError as e:
        logger.warning(f"Reject vehicle {vehicle_id} - not found - user_id={_uid()}: {e}")
        flash(str(e), "danger")

    except ValidationError as e:
        logger.warning(f"Validation error rejecting vehicle {vehicle_id} - user_id={_uid()}: {e}")
        flash(str(e), "danger")

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error rejecting vehicle {vehicle_id} - user_id={_uid()}: {e}", exc_info=True)
        flash("Unable to reject vehicle", "danger")

    return redirect(url_for("transport_admin.list_vehicles"))


# -------------------------------------------------------------------------
# Admin - Routes
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
# Admin - Incidents
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
# Admin - Settings
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
# Admin - Reports
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
        logger.error(f"Service unavailable generating report - user_id={_uid()}: {e}", exc_info=True)
        flash("Reporting service temporarily unavailable", "danger")
        return redirect(url_for("transport_admin.admin_dashboard"))

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error generating booking report - user_id={_uid()}: {e}", exc_info=True)
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
        from datetime import datetime, timezone

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
            'now': datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M'),

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
            today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
            try:
                ctx['today_bookings'] = get_booking_service().count_bookings_since(today_start)
            except AttributeError:
                ctx['today_bookings'] = 0

            # Recent bookings
            ctx['recent_bookings'] = get_booking_service().get_recent_bookings(limit=5)

            # Status breakdown
            ctx['pending_bookings'] = get_booking_service().count_bookings_by_status('pending_payment')
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


# ============================================================================
# MODERATOR ROUTES
# ============================================================================

@transport_bp.route("/moderate")
@login_required
@require_moderator
def moderate():
    """Show all transport items for moderators (same data as admin view)"""
    # Show all items, not just pending
    all_bookings = Booking.query.filter_by(is_deleted=False).order_by(Booking.created_at.desc()).all()
    all_vehicles = Vehicle.query.filter_by(is_deleted=False).order_by(Vehicle.created_at.desc()).all()
    all_drivers = DriverProfile.query.order_by(DriverProfile.created_at.desc()).all()

    # Audit log for moderator viewing
    from app.audit.comprehensive_audit import AuditService
    AuditService.security(
        event_type="moderator_view_transport",
        severity="info",
        description=f"Moderator {current_user.id} viewed all transport items",
        user_id=current_user.id,
        ip_address=request.remote_addr,
    )

    return render_template('transport/moderate.html',
                          bookings=all_bookings,
                          vehicles=all_vehicles,
                          drivers=all_drivers,
                          is_moderator=True)


@transport_bp.route("/moderate/booking/<int:id>")
@login_required
@require_moderator
def moderate_booking(id):
    """Show single booking for moderation review"""
    booking = Booking.query.get_or_404(id)
    return render_template('transport/moderate_booking.html', booking=booking)


@transport_bp.route("/moderate/vehicle/<int:id>")
@login_required
@require_moderator
def moderate_vehicle(id):
    """Show single vehicle for moderation review"""
    vehicle = Vehicle.query.get_or_404(id)
    return render_template('transport/moderate_vehicle.html', vehicle=vehicle)


@transport_bp.route("/moderate/driver/<int:id>")
@login_required
@require_moderator
def moderate_driver(id):
    """Show single driver for moderation review"""
    driver = DriverProfile.query.get_or_404(id)
    return render_template('transport/moderate_driver.html', driver=driver)


@transport_bp.route("/moderate/<entity_type>/<int:id>/<action>", methods=['POST'])
@login_required
@require_moderator
def moderate_action(entity_type, id, action):
    """Approve, reject, or flag transport items"""
    
    if entity_type == 'booking':
        item = Booking.query.get_or_404(id)
        redirect_url = url_for('transport.moderate_booking', id=id)
    elif entity_type == 'vehicle':
        item = Vehicle.query.get_or_404(id)
        redirect_url = url_for('transport.moderate_vehicle', id=id)
    elif entity_type == 'driver':
        item = DriverProfile.query.get_or_404(id)
        redirect_url = url_for('transport.moderate_driver', id=id)
    else:
        flash('Invalid entity type.', 'danger')
        return redirect(url_for('transport.moderate'))
    
    if action == 'approve':
        if entity_type == 'vehicle':
            item.verification_status = 'verified'
            item.verified_at = datetime.now(timezone.utc)
        elif entity_type == 'driver':
            item.verification_status = 'verified'
            item.verified_at = datetime.now(timezone.utc)
        elif entity_type == 'booking':
            item.status = 'confirmed'
        
        db.session.commit()
        flash(f'{entity_type.capitalize()} approved successfully.', 'success')
    
    elif action == 'reject':
        reason = request.form.get('reason', '').strip()
        if not reason:
            flash('Rejection reason is required.', 'warning')
            return redirect(redirect_url)
        
        if entity_type == 'vehicle':
            item.verification_status = 'rejected'
            item.rejection_reason = reason
        elif entity_type == 'driver':
            item.verification_status = 'rejected'
            item.rejection_reason = reason
        elif entity_type == 'booking':
            item.status = 'cancelled'
            item.cancellation_reason = reason
        
        db.session.commit()
        flash(f'{entity_type.capitalize()} rejected successfully.', 'success')
    
    elif action == 'flag':
        from app.admin.services import create_flag
        reason = request.form.get('reason', '').strip()
        priority = request.form.get('priority', 'medium')
        
        if not reason:
            flash('Reason required for flagging.', 'warning')
            return redirect(redirect_url)
        
        ok, flag = create_flag(
            user=current_user,
            entity_type=f'transport_{entity_type}',
            entity_id=id,
            reason=reason,
            priority=priority
        )
        
        if ok:
            flash(f'{entity_type.capitalize()} flagged for review (Priority: {priority})', 'warning')
        else:
            flash(f'Failed to flag: {flag}', 'danger')
    
    return redirect(url_for('transport.moderate'))

