from flask import Blueprint, render_template, session, redirect, url_for, flash
from app.identity.models.user import User
from app.profile.models import UserProfile
from app.extensions import db

profile_bp = Blueprint("profile_routes", __name__)

@profile_bp.route("/profile")
def view_profile():
    user_id = session.get("user_id")
    if not user_id:
        flash("Please log in first.", "warning")
        return redirect(url_for("auth_routes.login"))

    user = User.query.filter_by(user_id=user_id).first_or_404()
    return render_template("view.html", user=user)


