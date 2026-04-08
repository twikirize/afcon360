# app/fan/routes.py
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from app.fan.services.registry import get_or_create_fan, update_fan_profile
from app.admin.models import ManageableCategory, ManageableItem, ContentSubmission

# Use get_or_create_wallet when you need to ensure wallet exists
from app.wallet import get_or_create_wallet

# Standardized blueprint name: fan
fan_bp = Blueprint("fan", __name__)


@fan_bp.route("/fan/dashboard")
@login_required
def fan_dashboard():
    """General user/fan dashboard."""
    # Ensure user has a profile/wallet if needed
    # wallet = get_or_create_wallet(current_user.id)
    # profile = get_or_create_fan(current_user.id)

    # Categories that users can submit to
    categories = ManageableCategory.query.filter_by(
        is_active=True,
        editable_by_users=True
    ).all()

    # User's items and submissions (using integer .id for DB relationships)
    items = ManageableItem.query.filter_by(created_by=current_user.id).all()
    submissions = ContentSubmission.query.filter_by(submitted_by=current_user.id).all()

    return render_template(
        "user/content_dashboard.html",
        categories=categories,
        items=items,
        submissions=submissions
    )


@fan_bp.route("/fan/profile")
@login_required
def view_fan_profile():
    # This creates wallet if doesn't exist (for profile page that shows wallet info)
    wallet = get_or_create_wallet(current_user.id)
    profile = get_or_create_fan(wallet.user_id)
    return render_template("fan_profile.html", profile=profile, wallet=wallet)


@fan_bp.route("/fan/profile/update", methods=["POST"])
@login_required
def update_fan_profile_route():
    wallet = get_or_create_wallet(current_user.id)
    name = request.form.get("name")
    nationality = request.form.get("nationality")
    favorite_team = request.form.get("favorite_team")
    avatar_url = request.form.get("avatar_url")
    update_fan_profile(wallet.user_id, name, nationality, favorite_team, avatar_url)
    flash("Profile updated.", "success")
    return redirect(url_for("fan.view_fan_profile"))
