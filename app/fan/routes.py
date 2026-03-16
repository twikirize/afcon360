from flask import Blueprint, render_template, request, redirect, url_for, flash
from app.fan.services.registry import get_or_create_fan, update_fan_profile

from app.wallet.models import Wallet
from app.wallet.utils import get_or_create_wallet

fan_routes = Blueprint("fan_routes", __name__)

@fan_routes.route("/fan/profile")
def view_fan_profile():
    wallet = get_or_create_wallet()
    profile = get_or_create_fan(wallet.user_id)
    return render_template("fan_profile.html", profile=profile, wallet=wallet)

@fan_routes.route("/fan/profile/update", methods=["POST"])
def update_fan_profile_route():
    wallet = get_or_create_wallet()
    name = request.form.get("name")
    nationality = request.form.get("nationality")
    favorite_team = request.form.get("favorite_team")
    avatar_url = request.form.get("avatar_url")
    update_fan_profile(wallet["user_id"], name, nationality, favorite_team, avatar_url)
    flash("Profile updated.", "success")
    return redirect(url_for("fan_routes.view_fan_profile"))