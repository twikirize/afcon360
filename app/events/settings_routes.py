# app/events/settings_routes.py
"""
Event Settings routes - admin-only platform configuration.

Register on the events blueprint:
    from app.events.settings_routes import register_settings_routes
    register_settings_routes(events_bp)

Or import directly if using a separate blueprint.
"""

from flask import render_template, request, jsonify, redirect, url_for, flash
from flask_login import login_required, current_user

from app.extensions import db

import logging
log = logging.getLogger(__name__)


def register_settings_routes(bp):
    """Attach settings routes to the given blueprint."""

    @bp.route("/admin/settings", methods=["GET"])
    @login_required
    def admin_settings():
        """Event platform settings page - admin only."""
        from app.events.permissions import is_system_admin
        from app.events.settings_model import EventSettings

        if not is_system_admin(current_user):
            flash("Admin access required.", "danger")
            return redirect(url_for("events.list"))

        settings = EventSettings.get()
        return render_template(
            "events/admin/settings.html",
            settings=settings,
            page_title="Event Settings",
        )

    @bp.route("/admin/settings", methods=["POST"])
    @login_required
    def admin_settings_save():
        """Save event platform settings - admin only."""
        from app.events.permissions import is_system_admin
        from app.events.settings_model import EventSettings

        if not is_system_admin(current_user):
            return jsonify({"success": False, "error": "Unauthorized"}), 403

        # IMPORTANT: Load the attached database row, not a Redis-cached
        # transient object. EventSettings.get() may return a detached object
        # that cannot be committed reliably.
        settings = EventSettings.query.first()
        if not settings:
            settings = EventSettings()
            db.session.add(settings)

        # ── Boolean toggles ────────────────────────────────────────────────
        bool_fields = [
            # Approval workflow
            "auto_publish",
            "require_approval",
            "event_manager_auto_approve",

            # Trust-based publishing
            "enable_trust_based_publishing",
            "enable_role_bypass",
            "enable_kyc_boost",
            "enable_account_age_boost",
            "enable_event_history_boost",

            # Capacity & registration
            "allow_free_events",

            # Lifecycle automation
            "auto_complete_events",
            "allow_organiser_cancel",
            "allow_organiser_delete",

            # Notifications
            "notify_admin_on_submit",
            "notify_organiser_on_decision",
            "notify_organiser_on_suspend",

            # Ticket controls
            "allow_multiple_ticket_types",
            "allow_discount_codes",

            # Display
            "show_attendee_count",
            "show_remaining_capacity",
        ]

        # ── Integer fields ─────────────────────────────────────────────────
        int_fields = [
            # Trust thresholds
            "high_trust_threshold",
            "medium_trust_threshold",

            # Capacity & registration
            "max_capacity_limit",
            "registration_open_days_before",

            # Lifecycle
            "auto_archive_after_days",

            # Ticket controls
            "max_ticket_types_per_event",
        ]

        if request.is_json:
            data = request.get_json() or {}
            for field in bool_fields:
                if field in data:
                    setattr(settings, field, bool(data[field]))
            for field in int_fields:
                if field in data:
                    try:
                        setattr(settings, field, int(data[field]))
                    except (ValueError, TypeError):
                        pass
            if "notes" in data:
                settings.notes = data["notes"]
        else:
            # Form POST.
            for field in bool_fields:
                setattr(settings, field, field in request.form)
            for field in int_fields:
                val = request.form.get(field)
                if val is not None:
                    try:
                        setattr(settings, field, int(val))
                    except (ValueError, TypeError):
                        pass
            settings.notes = request.form.get("notes", settings.notes)

        # ── Business rule: auto_publish overrides require_approval ─────────
        if settings.auto_publish:
            settings.require_approval = False

        settings.updated_by_id = current_user.id

        try:
            db.session.commit()
            EventSettings.invalidate_cache()
            ok, err = True, None
        except Exception as exc:
            db.session.rollback()
            log.error(f"EventSettings save failed: {exc}")
            ok, err = False, str(exc)

        if request.is_json:
            if ok:
                return jsonify({"success": True, "message": "Settings saved."})
            return jsonify({"success": False, "error": err}), 500

        if ok:
            flash("Settings saved successfully.", "success")
        else:
            flash(f"Failed to save settings: {err}", "danger")
        return redirect(url_for("events.admin_settings"))