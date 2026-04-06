# app/fan/routes.py
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from app.fan.services.registry import get_or_create_fan, update_fan_profile

# Use get_or_create_wallet when you need to ensure wallet exists
from app.wallet import get_or_create_wallet

fan_routes = Blueprint("fan_routes", __name__)


@fan_routes.route("/fan/profile")
@login_required
def view_fan_profile():
    # This creates wallet if doesn't exist (for profile page that shows wallet info)
    wallet = get_or_create_wallet(current_user.id)
    profile = get_or_create_fan(wallet.user_id)
    return render_template("fan_profile.html", profile=profile, wallet=wallet)


@fan_routes.route("/fan/profile/update", methods=["POST"])
@login_required
def update_fan_profile_route():
    wallet = get_or_create_wallet(current_user.id)
    name = request.form.get("name")
    nationality = request.form.get("nationality")
    favorite_team = request.form.get("favorite_team")
    avatar_url = request.form.get("avatar_url")
    update_fan_profile(wallet.user_id, name, nationality, favorite_team, avatar_url)
    flash("Profile updated.", "success")
    return redirect(url_for("fan_routes.view_fan_profile"))