"""
Accommodation Admin Routes for AFCON360 - Compat Redirect Layer.

The canonical accommodation admin dashboard and management pages live in the
``accommodation`` blueprint (``accommodation.admin_dashboard``,
``accommodation.admin_properties``, ``accommodation.admin_bookings``, etc.).
This module keeps the legacy ``/admin/accommodation-admin/...`` URL space
alive by redirecting to those working pages instead of re-implementing
broken template/service duplicates.
"""

import logging
from flask import redirect, url_for
from flask_login import login_required

from app.admin import admin_bp
from app.auth.decorators import require_role

logger = logging.getLogger(__name__)


@admin_bp.route("/accommodation-admin", endpoint="accommodation_admin_dashboard")
@login_required
@require_role("accommodation_admin")
def accommodation_admin_dashboard():
    """Redirect to the canonical accommodation admin dashboard."""
    return redirect(url_for("accommodation.admin_dashboard"))


@admin_bp.route("/accommodation-admin/properties", endpoint="accommodation_admin_properties")
@login_required
@require_role("accommodation_admin")
def accommodation_admin_properties():
    """Redirect to the canonical property management page."""
    return redirect(url_for("accommodation.admin_properties"))


@admin_bp.route("/accommodation-admin/properties/<int:property_id>/verify",
                endpoint="accommodation_admin_verify_property", methods=["POST"])
@login_required
@require_role("accommodation_admin")
def accommodation_admin_verify_property(property_id):
    """Delegate property verification to the canonical verification flow."""
    return redirect(url_for("accommodation.admin_verification"))


@admin_bp.route("/accommodation-admin/properties/<int:property_id>/reject",
                endpoint="accommodation_admin_reject_property", methods=["POST"])
@login_required
@require_role("accommodation_admin")
def accommodation_admin_reject_property(property_id):
    """Delegate property rejection to the canonical verification flow."""
    return redirect(url_for("accommodation.admin_verification"))


@admin_bp.route("/accommodation-admin/properties/<int:property_id>/delete",
                endpoint="accommodation_admin_delete_property", methods=["POST"])
@login_required
@require_role("accommodation_admin")
def accommodation_admin_delete_property(property_id):
    """Deleted via the canonical property management page."""
    return redirect(url_for("accommodation.admin_properties"))


@admin_bp.route("/accommodation-admin/bookings", endpoint="accommodation_admin_bookings")
@login_required
@require_role("accommodation_admin")
def accommodation_admin_bookings():
    """Redirect to the canonical booking management page."""
    return redirect(url_for("accommodation.admin_bookings"))


@admin_bp.route("/accommodation-admin/bookings/<int:booking_id>/approve",
                endpoint="accommodation_admin_approve_booking", methods=["POST"])
@login_required
@require_role("accommodation_admin")
def accommodation_admin_approve_booking(booking_id):
    """Booking approval happens on the canonical booking management page."""
    return redirect(url_for("accommodation.admin_bookings"))


@admin_bp.route("/accommodation-admin/bookings/<int:booking_id>/reject",
                endpoint="accommodation_admin_reject_booking", methods=["POST"])
@login_required
@require_role("accommodation_admin")
def accommodation_admin_reject_booking(booking_id):
    """Booking rejection happens on the canonical booking management page."""
    return redirect(url_for("accommodation.admin_bookings"))


@admin_bp.route("/accommodation-admin/reviews", endpoint="accommodation_admin_reviews")
@login_required
@require_role("accommodation_admin")
def accommodation_admin_reviews():
    """Redirect to the canonical accommodation admin hub (review management
    is exercised from the working property/booking pages)."""
    return redirect(url_for("accommodation.admin_dashboard"))


@admin_bp.route("/accommodation-admin/reviews/<int:review_id>/approve",
                endpoint="accommodation_admin_approve_review", methods=["POST"])
@login_required
@require_role("accommodation_admin")
def accommodation_admin_approve_review(review_id):
    """Review approval happens on the canonical accommodation pages."""
    return redirect(url_for("accommodation.admin_dashboard"))


@admin_bp.route("/accommodation-admin/reviews/<int:review_id>/reject",
                endpoint="accommodation_admin_reject_review", methods=["POST"])
@login_required
@require_role("accommodation_admin")
def accommodation_admin_reject_review(review_id):
    """Review rejection happens on the canonical accommodation pages."""
    return redirect(url_for("accommodation.admin_dashboard"))


@admin_bp.route("/accommodation-admin/analytics", endpoint="accommodation_admin_analytics")
@login_required
@require_role("accommodation_admin")
def accommodation_admin_analytics():
    """Redirect to the canonical analytics page."""
    return redirect(url_for("accommodation.admin_analytics"))


@admin_bp.route("/accommodation-admin/settings", endpoint="accommodation_admin_settings")
@login_required
@require_role("accommodation_admin")
def accommodation_admin_settings():
    """Redirect to the canonical settings page."""
    return redirect(url_for("accommodation.admin_settings"))


@admin_bp.route("/accommodation-admin/pricing", endpoint="accommodation_admin_pricing")
@login_required
@require_role("accommodation_admin")
def accommodation_admin_pricing():
    """Redirect to the canonical settings page (pricing is configured there)."""
    return redirect(url_for("accommodation.admin_settings"))


@admin_bp.route("/accommodation-admin/verification", endpoint="accommodation_admin_verification")
@login_required
@require_role("accommodation_admin")
def accommodation_admin_verification():
    """Redirect to the canonical verification page."""
    return redirect(url_for("accommodation.admin_verification"))