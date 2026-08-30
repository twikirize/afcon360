"""
AFCON360 Feed Routes

GET  /api/home/feed       — paginated JSON feed for infinite scroll
POST /api/home/feed/layout — owner/super_admin toggles the feed layout

The feed endpoint is public (the homepage is visible to everyone).
The layout toggle requires an authenticated owner or super_admin.
"""

import logging

from flask import request, jsonify, session
from flask_login import current_user, login_required

from app.feed import feed_bp
from app.feed.services import FeedService
from app.models.system_config import SystemConfig

logger = logging.getLogger(__name__)

VALID_LAYOUTS = ("mixed", "sections", "tabbed")


def _current_layout() -> str:
    """Read the active layout from SystemConfig (defaults to 'mixed')."""
    try:
        layout = SystemConfig.get("home_feed_layout", "mixed")
    except Exception:
        layout = "mixed"
    return layout if layout in VALID_LAYOUTS else "mixed"


@feed_bp.route("/feed")
def feed():
    """Paginated JSON feed for infinite scroll.

    Query params:
        page      — page number (default 1)
        per_page  — items per page (default 10, max 30)
        layout    — override layout for this request (default: system config)
        seed      — pagination seed (stable within a session)
    """
    try:
        page = max(1, request.args.get("page", 1, type=int))
        per_page = min(30, max(1, request.args.get("per_page", 10, type=int)))
        seed = request.args.get("seed") or None
        layout = request.args.get("layout") or _current_layout()

        user_id = current_user.id if current_user.is_authenticated else None

        result = FeedService.get_feed(
            page=page,
            per_page=per_page,
            layout=layout,
            seed=seed,
            user_id=user_id,
        )
        return jsonify(result), 200
    except Exception as e:
        logger.error(f"Feed API error: {e}", exc_info=True)
        return jsonify({
            "items": [],
            "page": 1,
            "per_page": 10,
            "has_more": False,
            "layout": "mixed",
            "seed": "",
            "error": "Feed temporarily unavailable",
        }), 200  # Return 200 with empty list so the UI doesn't crash


@feed_bp.route("/feed/layout", methods=["POST"])
@login_required
def set_layout():
    """Owner / super_admin toggles the homepage feed layout.

    Expects JSON: {"layout": "mixed" | "sections" | "tabbed"}
    """
    from app.events.permissions import is_super_admin

    if not (is_super_admin(current_user) or current_user.is_app_owner()):
        return jsonify({"status": "error", "message": "Permission denied"}), 403

    data = request.get_json(silent=True) or {}
    layout = (data.get("layout") or "").strip().lower()

    if layout not in VALID_LAYOUTS:
        return jsonify({
            "status": "error",
            "message": f"Invalid layout. Choose from: {', '.join(VALID_LAYOUTS)}",
        }), 400

    try:
        SystemConfig.set(
            "home_feed_layout",
            layout,
            value_type="str",
            category="homepage",
            description="Homepage feed layout mode (mixed/sections/tabbed)",
            is_public=True,
            updated_by=current_user.id,
        )
        return jsonify({
            "status": "ok",
            "layout": layout,
            "message": f"Feed layout set to '{layout}'",
        }), 200
    except Exception as e:
        logger.error(f"Layout toggle error: {e}", exc_info=True)
        return jsonify({"status": "error", "message": "Failed to save layout"}), 500
