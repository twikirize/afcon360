# app/events/admin_pages.py
"""
Event admin "quick action" pages.

These render the management pages linked from the Event Manager dashboard
(action cards that previously 404'd):
    /events/admin/registrations
    /events/admin/organizers
    /events/admin/ticketing
    /events/analytics

Register on the events blueprint:
    from app.events.admin_pages import register_admin_pages
    register_admin_pages(events_bp)
"""

from flask import render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from sqlalchemy import func, desc

from app.extensions import db
from app.events.models import Event, EventRegistration, TicketType
from app.events.permissions import is_system_admin

import logging

log = logging.getLogger(__name__)


def register_admin_pages(bp):
    """Attach the event-manager quick-action pages to the given blueprint."""

    # ── Registrations ──────────────────────────────────────────────────────
    @bp.route("/admin/registrations", methods=["GET"])
    @login_required
    def admin_registrations():
        """Platform-wide event registrations with optional status filter."""
        if not is_system_admin(current_user):
            flash("Admin access required.", "danger")
            return redirect(url_for("events.list"))

        status_filter = request.args.get("status", "all")

        query = (
            EventRegistration.query.join(Event, EventRegistration.event_id == Event.id)
            .filter(Event.is_deleted == False)
        )
        if status_filter != "all":
            query = query.filter(EventRegistration.status == status_filter)

        registrations = query.order_by(EventRegistration.created_at.desc()).limit(300).all()

        status_options = [
            ("all", "All"),
            (EventRegistration.STATUS_CONFIRMED, "Confirmed"),
            (EventRegistration.STATUS_PENDING_PAYMENT, "Pending Payment"),
            (EventRegistration.STATUS_CHECKED_IN, "Checked In"),
            (EventRegistration.STATUS_CANCELLED, "Cancelled"),
            (EventRegistration.STATUS_NO_SHOW, "No Show"),
            (EventRegistration.STATUS_EXPIRED, "Expired"),
        ]

        return render_template(
            "events/admin/registrations.html",
            registrations=registrations,
            current_filter=status_filter,
            status_options=status_options,
            page_title="Event Registrations",
        )

    # ── Organizers ─────────────────────────────────────────────────────────
    @bp.route("/admin/organizers", methods=["GET"])
    @login_required
    def admin_organizers():
        """List organizers (event owners) with their event counts."""
        if not is_system_admin(current_user):
            flash("Admin access required.", "danger")
            return redirect(url_for("events.list"))

        from app.identity.models.user import User

        rows = (
            db.session.query(Event.current_owner_id, func.count(Event.id))
            .filter(Event.is_deleted == False, Event.current_owner_id.isnot(None))
            .group_by(Event.current_owner_id)
            .all()
        )

        organizers = []
        for owner_id, event_count in rows:
            user = User.query.get(owner_id)
            if user is None:
                continue
            organizers.append({"user": user, "event_count": event_count})
        organizers.sort(key=lambda item: item["event_count"], reverse=True)

        return render_template(
            "events/admin/organizers.html",
            organizers=organizers,
            page_title="Organizer Management",
        )

    # ── Ticketing ──────────────────────────────────────────────────────────
    @bp.route("/admin/ticketing", methods=["GET"])
    @login_required
    def admin_ticketing():
        """Platform-wide ticket types with pricing and capacity."""
        if not is_system_admin(current_user):
            flash("Admin access required.", "danger")
            return redirect(url_for("events.list"))

        tickets = (
            TicketType.query.join(Event, TicketType.event_id == Event.id)
            .filter(Event.is_deleted == False)
            .order_by(desc(Event.created_at))
            .limit(300)
            .all()
        )

        return render_template(
            "events/admin/ticketing.html",
            tickets=tickets,
            page_title="Ticketing Settings",
        )

    # ── Analytics ──────────────────────────────────────────────────────────
    @bp.route("/analytics", methods=["GET"])
    @login_required
    def analytics():
        """Platform-wide event analytics dashboard."""
        if not (is_system_admin(current_user) or current_user.has_global_role("moderator")):
            flash("Admin access required.", "danger")
            return redirect(url_for("events.list"))

        from app.events.metrics_service import EventMetricsService

        metrics = EventMetricsService.get_system_wide_metrics(days=365)
        if isinstance(metrics, dict) and "error" in metrics:
            metrics = {}

        return render_template(
            "events/admin/analytics.html",
            metrics=metrics,
            page_title="Event Analytics",
        )
