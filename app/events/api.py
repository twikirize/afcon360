#app/events/api.py
"""JSON API endpoints for attendee event preferences."""

from flask import Blueprint, jsonify
from flask_login import current_user, login_required

from app.events.services import EventService


event_favorites_api_bp = Blueprint(
    "event_favorites_api",
    __name__,
    url_prefix="/api/events",
)


@event_favorites_api_bp.route("/<public_id>/toggle-favorite", methods=["POST"])
@login_required
def toggle_favorite(public_id):
    """Toggle an event in the authenticated user's saved events."""
    favorited, favorite_count, error = EventService.toggle_favorite(
        public_id,
        current_user.id,
    )
    if error:
        status_code = 404 if error == "Event not found" else 400
        return jsonify({"success": False, "error": error}), status_code

    return jsonify({
        "success": True,
        "event_id": public_id,
        "favorited": favorited,
        "favorite_count": favorite_count,
    })


@event_favorites_api_bp.route("/become-organizer/eligibility", methods=["GET"])
@login_required
def become_organizer_eligibility():
    """Check if current user is eligible to become an organizer."""
    result = EventService.check_organizer_eligibility(current_user.id)
    return jsonify({"success": True, **result})