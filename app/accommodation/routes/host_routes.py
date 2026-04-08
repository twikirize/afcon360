# app/accommodation/routes/host_routes.py
"""
Host dashboard routes - For property owners
To be implemented in Phase 4
"""

from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from app.accommodation.services.identity_service import AccommodationIdentityService

host_bp = Blueprint('host', __name__)


@host_bp.route("/dashboard", endpoint="dashboard")
@login_required
def dashboard():
    """
    Host dashboard - Overview of listings and bookings
    """
    # Check if user can host
    can_host, reason = AccommodationIdentityService.can_host(current_user)
    if not can_host:
        flash(f"Cannot access host dashboard: {reason}", "warning")
        return redirect(url_for('index'))

    # Get host identity (individual or org)
    host_info = AccommodationIdentityService.get_host_identity(current_user)

    # TODO: Get listings and bookings for this host
    listings = []
    bookings = []

    return render_template(
        "accommodation/host/dashboard.html",
        host_info=host_info,
        listings=listings,
        bookings=bookings
    )


@host_bp.route("/listings/create", methods=['GET', 'POST'], endpoint="create_listing")
@login_required
def create_listing():
    """
    Create a new property listing
    To be implemented in Phase 4
    """
    # Check if user can host
    can_host, reason = AccommodationIdentityService.can_host(current_user)
    if not can_host:
        flash(f"Cannot create listing: {reason}", "warning")
        return redirect(url_for('index'))

    # TODO: Implement listing creation form
    return render_template("accommodation/host/create_listing.html")


@host_bp.route("/listings/<int:property_id>/edit", methods=['GET', 'POST'], endpoint="edit_listing")
@login_required
def edit_listing(property_id):
    """
    Edit existing property listing
    To be implemented in Phase 4
    """
    # TODO: Check ownership and edit
    return render_template("accommodation/host/edit_listing.html", property_id=property_id)


@host_bp.route("/calendar", endpoint="calendar")
@login_required
def calendar():
    """
    Availability calendar for host's properties
    To be implemented in Phase 4
    """
    return render_template("accommodation/host/calendar.html")


@host_bp.route("/bookings", endpoint="bookings")
@login_required
def bookings():
    """
    Booking inbox for host
    To be implemented in Phase 4
    """
    return render_template("accommodation/host/bookings.html")


@host_bp.route("/earnings", endpoint="earnings")
@login_required
def earnings():
    """
    Earnings dashboard for host
    To be implemented in Phase 4
    """
    return render_template("accommodation/host/earnings.html")
