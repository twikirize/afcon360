# app/events/routes_organizer.py
"""Organizer dispatch (universal) landing routes.

Each route lists ALL events the current user organizes and lets them
pick one, then routes to that event's specific tool. Mirrors the
accommodation_manage_universal / community_hosts_universal pattern in
routes_accommodation.py and routes_community_hosts.py.

The function names intentionally match the endpoint names referenced by
the Organizer Hub template (events_hub.html) via safe_url(...), so the
hub's quick-action cards resolve without any template edits.
"""
from flask import render_template
from flask_login import login_required, current_user
from app.events import events_bp
from app.events.services import EventService


def _dispatch(template_ctx: dict):
    """Fetch all organizer events and render the shared dispatch template."""
    events = EventService.get_organizer_event_models(current_user)
    return render_template('events/organizer/dispatch_universal.html',
                           events=events, **template_ctx)


@events_bp.route("/organizer/dashboards")
@login_required
def organizer_dashboards():
    """All-events dispatch: pick an event to open its organizer dashboard."""
    return _dispatch({
        'page_title': 'Event Dashboards',
        'page_icon': 'fa-tachometer-alt',
        'page_desc': 'Pick an event to open its organizer dashboard.',
        'target_endpoint': 'events.organizer_dashboard',
        'target_label': 'Open Dashboard',
    })


@events_bp.route("/organizer/scanner")
@login_required
def organizer_scanner():
    """All-events dispatch: pick an event to open its check-in scanner."""
    return _dispatch({
        'page_title': 'Scanner',
        'page_icon': 'fa-qrcode',
        'page_desc': 'Pick an event to open its check-in scanner.',
        'target_endpoint': 'events.scanner',
        'target_label': 'Open Scanner',
    })


@events_bp.route("/organizer/export")
@login_required
def organizer_export():
    """All-events dispatch: pick an event to export its attendee list."""
    return _dispatch({
        'page_title': 'Export Attendees',
        'page_icon': 'fa-file-csv',
        'page_desc': 'Pick an event to export its attendee list.',
        'target_endpoint': 'events.export_attendees',
        'target_label': 'Export Attendees',
    })


@events_bp.route("/organizer/staff")
@login_required
def organizer_staff():
    """All-events dispatch: pick an event to manage its co-organizers & volunteers."""
    return _dispatch({
        'page_title': 'Staff',
        'page_icon': 'fa-user-shield',
        'page_desc': 'Pick an event to manage its co-organizers & volunteers.',
        'target_endpoint': 'events.event_staff',
        'target_label': 'Manage Staff',
    })


@events_bp.route("/organizer/waitlist")
@login_required
def organizer_waitlist():
    """All-events dispatch: review pending waitlists across your events.

    No dedicated per-event waitlist management route exists yet, so each
    event card routes to the per-event organizer dashboard (where
    waitlist data is surfaced) and pending counts are shown as badges.
    A dedicated per-event waitlist view can be slotted in later by
    changing ``target_endpoint`` for this route.
    """
    events = EventService.get_organizer_event_models(current_user)
    counts = {}
    try:
        Waitlist = EventService._get_waitlist_class()
        from app.extensions import db
        from sqlalchemy import func
        rows = db.session.query(
            Waitlist.event_id,
            func.count(Waitlist.id),
        ).filter(Waitlist.status == 'pending').group_by(Waitlist.event_id).all()
        counts = {eid: cnt for eid, cnt in rows}
    except Exception:
        counts = {}
    return render_template('events/organizer/dispatch_universal.html',
                           events=events, waitlist_counts=counts,
                           page_title='Waitlist',
                           page_icon='fa-clock',
                           page_desc='Review pending waitlists across your events.',
                           target_endpoint='events.organizer_dashboard',
                           target_label='Manage Event')
