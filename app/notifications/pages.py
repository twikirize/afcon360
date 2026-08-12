"""
AFCON360 Communication Center — HTML pages

Renders the user-facing inbox UIs that the global header links to:

    /notifications   → full notification inbox (All / Unread / by module)
    /messages        → unified internal message center
                       (All / Unread / Archived / Sent — Sent is role-gated)

These are PRESENTATION-ONLY. They read from the existing
:class:`~app.notifications.models.Notification` and
:class:`~app.notifications.models.Message` via the existing
:class:`~app.notifications.services.NotificationService`. They do NOT create
new models, do NOT touch the event backbone, and do NOT duplicate the
``/api/notifications`` API blueprint.

Design rules honoured
---------------------
* One inbox page loads every item (read or unread); filtering is by query
  param, not by separate templates.
* One message template with conditional rendering per message *type*
  (KYC update, booking, etc.) — never one template per type.
* The "Sent" view is a system/admin capability: normal users cannot see it.
  It is gated by role so a support/admin sending "please update your KYC"
  appears in their Sent folder but not in a regular user's.
"""

from flask import (
    Blueprint,
    render_template,
    request,
    abort,
    redirect,
    url_for,
    current_app,
)
from flask_login import login_required, current_user

from app.notifications.models import (
    Notification,
    Message,
    NotificationModule,
    MODULE_LABELS,
    MODULE_COLORS,
)
from app.notifications.services import NotificationService
from app.auth.helpers import has_global_role

# Roles that may send messages on behalf of the platform (support, mods,
# compliance, module admins, owners). These users get a "Sent" folder.
SENT_VIEW_ROLES = [
    "owner",
    "super_admin",
    "admin",
    "support",
    "moderator",
    "compliance_officer",
    "accommodation_admin",
    "wallet_admin",
    "transport_admin",
    "tourism_admin",
    "event_manager",
]

communication_pages = Blueprint(
    "communication_pages", __name__, url_prefix="/"
)


def _can_view_sent() -> bool:
    """Whether the current user may see the platform 'Sent' folder."""
    if not current_user.is_authenticated:
        return False
    return has_global_role(current_user, *SENT_VIEW_ROLES)


def _group_by_day(items, date_attr="created_at"):
    """Bucket notifications/messages into Today / Yesterday / date groups."""
    from datetime import datetime, timezone

    today = datetime.now(timezone.utc).date()
    yesterday = (today - __import__("datetime").timedelta(days=1))
    groups = {}
    order = []
    for item in items:
        dt = getattr(item, date_attr, None)
        if dt is None:
            key = "Earlier"
        else:
            if dt.tzinfo is not None:
                d = dt.date()
            else:
                d = dt  # already date-like
            if d == today:
                key = "Today"
            elif d == yesterday:
                key = "Yesterday"
            else:
                key = dt.strftime("%d %b %Y")
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(item)
    return [(k, groups[k]) for k in order]


# ============================================================================
# NOTIFICATION INBOX — one page, filtered by query param
# ============================================================================

@communication_pages.route("/notifications", endpoint="notifications")
@login_required
def notifications_page():
    user_id = current_user.id

    filter_kind = request.args.get("filter", "all")  # all | unread
    module = request.args.get("module")  # accommodation | wallet | ... | None

    unread_only = filter_kind == "unread"

    notifications = NotificationService.get_user_notifications(
        user_id,
        limit=200,
        unread_only=unread_only,
        module=module,
    )

    # Counts for the filter tabs (computed server-side so they stay accurate
    # even before the client-side chips run).
    total = Notification.query.filter_by(user_id=user_id).count()
    unread_total = Notification.query.filter_by(
        user_id=user_id, is_read=False
    ).count()

    by_module_counts = NotificationService.get_unread_counts_by_module(user_id)

    modules_meta = [
        {
            "value": m.value,
            "label": MODULE_LABELS.get(m.value, m.value.title()),
            "color": MODULE_COLORS.get(m.value, "#7a8290"),
            "unread": by_module_counts.get(m.value, 0),
        }
        for m in NotificationModule
        if by_module_counts.get(m.value, 0) > 0
    ]

    grouped = _group_by_day(notifications)

    return render_template(
        "notifications/inbox.html",
        notifications=notifications,
        grouped=grouped,
        filter_kind=filter_kind,
        active_module=module,
        total=total,
        unread_total=unread_total,
        modules_meta=modules_meta,
        public_id=current_user.public_id,
    )


@communication_pages.route(
    "/notifications/<string:notification_id>", endpoint="notification_detail"
)
@login_required
def notification_detail(notification_id: str):
    """Load a single notification (read OR unread) and mark it read."""
    notif = Notification.query.filter_by(
        public_id=notification_id, user_id=current_user.id
    ).first() if hasattr(Notification, "public_id") else None

    if notif is None:
        # Fall back to internal id if public_id column is absent (legacy rows).
        try:
            nid = int(notification_id)
        except (TypeError, ValueError):
            abort(404)
        notif = Notification.query.filter_by(
            id=nid, user_id=current_user.id
        ).first_or_404()

    if not notif.is_read:
        NotificationService.mark_read(notif.id, current_user.id)

    return render_template(
        "notifications/inbox.html",
        notifications=[notif],
        grouped=_group_by_day([notif]),
        filter_kind="all",
        active_module=None,
        total=1,
        unread_total=0,
        modules_meta=[],
        focus_id=notif.id,
        public_id=current_user.public_id,
    )


# ============================================================================
# MESSAGE CENTER — one page, filtered by query param
# ============================================================================

@communication_pages.route("/messages", endpoint="messages")
@login_required
def messages_page():
    user_id = current_user.id
    filter_kind = request.args.get("filter", "all")
    # all | unread | archived | sent

    can_sent = _can_view_sent()

    unread_only = filter_kind == "unread"
    archived = filter_kind == "archived"
    direction = "outbound" if (filter_kind == "sent" and can_sent) else None

    messages = NotificationService.get_user_messages(
        user_id,
        limit=200,
        unread_only=unread_only,
        direction=direction,
        archived=archived,
    )

    # Sent is a platform action: only show the tab + items to permitted roles.
    if filter_kind == "sent" and not can_sent:
        abort(403)

    total = Message.query.filter(
        (Message.sender_id == user_id) | (Message.recipient_id == user_id)
    ).count()
    unread_total = Message.query.filter_by(
        recipient_id=user_id, is_read=False, archived=False
    ).count()
    archived_total = Message.query.filter(
        (Message.sender_id == user_id) | (Message.recipient_id == user_id),
        Message.archived.is_(True),
    ).count()
    sent_total = 0
    if can_sent:
        sent_total = Message.query.filter_by(
            sender_id=user_id, direction="outbound"
        ).count()

    grouped = _group_by_day(messages)

    return render_template(
        "notifications/messages.html",
        messages=messages,
        grouped=grouped,
        filter_kind=filter_kind,
        can_view_sent=can_sent,
        total=total,
        unread_total=unread_total,
        archived_total=archived_total,
        sent_total=sent_total,
        public_id=current_user.public_id,
    )


@communication_pages.route(
    "/messages/<string:message_id>", endpoint="message_detail"
)
@login_required
def message_detail(message_id: str):
    """Load a single message thread item (read OR unread) and mark it read."""
    msg = Message.query.filter_by(
        public_id=message_id
    ).first() if hasattr(Message, "public_id") else None

    if msg is None:
        try:
            mid = int(message_id)
        except (TypeError, ValueError):
            abort(404)
        msg = Message.query.filter_by(id=mid).first_or_404()
    else:
        if msg.sender_id != current_user.id and msg.recipient_id != current_user.id:
            abort(404)

    # Only the recipient marks-as-read; senders keep their copy unread-state.
    if msg.recipient_id == current_user.id and not msg.is_read:
        NotificationService.mark_message_read(msg.id, current_user.id)

    return render_template(
        "notifications/messages.html",
        messages=[msg],
        grouped=_group_by_day([msg]),
        filter_kind="all",
        can_view_sent=_can_view_sent(),
        total=1,
        unread_total=0,
        archived_total=0,
        sent_total=0,
        focus_id=msg.id,
        public_id=current_user.public_id,
    )
