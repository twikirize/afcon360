# app/accommodation/routes/admin_routes.py
"""
Admin routes for accommodation module oversight
To be implemented in Phase 5
"""

from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from app.auth.policy import can

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
