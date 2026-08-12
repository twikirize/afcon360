"""
AFCON360 Notification Dashboard Helpers

Lightweight helpers for injecting notification + message state into every
module dashboard context (badge counts, recent items). Designed to be called
from any route's template context without circular import issues.

Module awareness
----------------
AFCON360 runs several independent businesses (accommodation, transport, events,
wallet, tourism) on one notification system. These helpers therefore expose both
a global view and a per-module breakdown, so:

  * the global navbar bell can show everything, grouped by module; and
  * a module dashboard (e.g. transport) can scope its bell to just that module
    by setting `g.notification_module = 'transport'` in a before_request hook,
    or by passing `module=` directly.
"""

import logging
from typing import Dict, Any, List, Optional

from flask import g
from flask_login import current_user

from app.notifications.models import (
    Notification,
    Message,
    NotificationModule,
    MODULE_LABELS,
    MODULE_ICONS,
    MODULE_COLORS,
)
from app.notifications.services import NotificationService

logger = logging.getLogger(__name__)


def _active_module() -> Optional[str]:
    """
    The module the current request belongs to, if any.

    A module blueprint can set this in a before_request hook:

        @bp.before_request
        def _scope_notifications():
            g.notification_module = 'transport'

    When set, the notification bell scopes itself to that business.
    """
    return getattr(g, 'notification_module', None)


def dashboard_badges(user_id: int = None, module: str = None) -> Dict[str, Any]:
    """
    Return notification + message badge counts for the current user.

    Includes a `by_module` breakdown so the UI can differentiate a hotel
    booking from a bus booking. Safe to call when no user is logged in.
    """
    if user_id is None and current_user.is_authenticated:
        user_id = current_user.id

    empty = {
        'unread_notifications': 0,
        'unread_messages': 0,
        'total_unread': 0,
        'by_module': {},
        'scoped_module': module,
        'scoped_unread': 0,
    }
    if not user_id:
        return empty

    try:
        by_module = NotificationService.get_unread_counts_by_module(user_id)
        unread_notif = sum(by_module.values())
        unread_msgs = Message.query.filter_by(
            recipient_id=user_id, is_read=False, archived=False
        ).count()
        return {
            'unread_notifications': unread_notif,
            'unread_messages': unread_msgs,
            'total_unread': unread_notif + unread_msgs,
            'by_module': by_module,
            'scoped_module': module,
            'scoped_unread': by_module.get(module, 0) if module else unread_notif,
        }
    except Exception as e:
        logger.warning(f"dashboard_badges failed: {e}")
        return empty


def recent_notifications(user_id: int = None, limit: int = 5, module: str = None) -> list:
    """
    Return recent notifications for the current user (for the bell dropdown).

    Pass *module* (or set `g.notification_module`) to restrict the list to a
    single business.
    """
    if user_id is None and current_user.is_authenticated:
        user_id = current_user.id
    if not user_id:
        return []
    try:
        return NotificationService.get_user_notifications(
            user_id, limit=limit, module=module
        )
    except Exception as e:
        logger.warning(f"recent_notifications failed: {e}")
        return []


def module_summary(badges: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Build an ordered, display-ready per-module summary for the bell tabs.

    Only modules that actually have unread items are returned, so the UI stays
    clean for users who only use one part of the platform.
    """
    by_module = (badges or {}).get('by_module') or {}
    summary = []
    for mod in NotificationModule:
        count = by_module.get(mod.value, 0)
        if not count:
            continue
        summary.append({
            'module': mod.value,
            'label': MODULE_LABELS.get(mod.value, mod.value.title()),
            'icon': MODULE_ICONS.get(mod.value, 'bi-bell'),
            'color': MODULE_COLORS.get(mod.value, '#7a8290'),
            'count': count,
        })
    return summary


def inject_notification_context() -> Dict[str, Any]:
    """
    Jinja context processor payload: adds badges + recent items to all templates.
    Registered via app.context_processor in app/__init__.py.

    Exposes:
        notif_badges          - counts incl. `by_module` breakdown
        recent_notifications  - recent items (scoped to the active module)
        notif_modules         - per-module summary for tabs/filters
        notif_active_module   - the module this dashboard is scoped to (or None)
        notif_module_meta     - label/icon/colour lookup for rendering badges
    """
    if not current_user.is_authenticated:
        return {}

    module = _active_module()
    badges = dashboard_badges(module=module)
    return {
        'notif_badges': badges,
        'recent_notifications': recent_notifications(limit=6, module=module),
        'notif_modules': module_summary(badges),
        'notif_active_module': module,
        'notif_module_meta': {
            'labels': MODULE_LABELS,
            'icons': MODULE_ICONS,
            'colors': MODULE_COLORS,
        },
    }
