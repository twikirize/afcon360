# app/monitor/routes.py
"""Owner mission-control live monitoring dashboard (real-time system feed)."""
import os

from flask import render_template, current_app

from app.monitor import monitor_bp
from app.auth.decorators import require_role
from app.extensions import socketio


@monitor_bp.route("/monitor")
@require_role("owner", "super_admin")
def monitor_dashboard():
    """Live system monitor for the owner / super admin.

    Renders a browser-based, auto-updating dashboard that shows reservation
    attempts, ticket sales, sold-out and error events pushed over SocketIO.
    No console required. The page is environment-aware: it surfaces which
    runtime environment is active and whether the realtime transport is
    available, so the owner can tell a dev box from production at a glance.
    """
    app_env = os.getenv("APP_ENV") or os.getenv("FLASK_ENV") or "local"
    flask_env = os.getenv("FLASK_ENV", "production")
    try:
        async_mode = socketio.async_mode or "unknown"
    except Exception:
        async_mode = "unknown"

    return render_template(
        "monitor.html",
        app_env=app_env,
        flask_env=flask_env,
        debug=bool(current_app.debug),
        async_mode=async_mode,
    )
