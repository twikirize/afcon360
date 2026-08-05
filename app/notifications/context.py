"""
AFCON360 Notification Dashboard Helpers

Lightweight helpers for injecting notification + message state into every
module dashboard context (badge counts, recent items). Designed to be called
from any route's template context without circular import issues.
"""

import logging
from typing import Dict, Any

from flask_login import current_user

from app.notifications.models import Notification, Message
from app.notifications.services import NotificationService

logger = logging.getLogger(__name__)


def dashboard_badges(user_id: int = None) -> Dict[str, Any]:
    """
    Return notification + message badge counts for the current user.
    Safe to call when no user is logged in (returns zeros).
    """
    if user_id is None and current_user.is_authenticated:
        user_id = current_user.id

    if not user_id:
        return {
            'unread_notifications': 0,
            'unread_messages': 0,
            'total_unread': 0,
        }

    try:
        unread_notif = NotificationService.get_unread_count(user_id)
        unread_msgs = Message.query.filter_by(
            recipient_id=user_id, is_read=False, archived=False
        ).count()
        return {
            'unread_notifications': unread_notif,
            'unread_messages': unread_msgs,
            'total_unread': unread_notif + unread_msgs,
        }
    except Exception as e:
        logger.warning(f"dashboard_badges failed: {e}")
        return {'unread_notifications': 0, 'unread_messages': 0, 'total_unread': 0}


def recent_notifications(user_id: int = None, limit: int = 5) -> list:
    """Return recent notifications for the current user (for dropdown)."""
    if user_id is None and current_user.is_authenticated:
        user_id = current_user.id
    if not user_id:
        return []
    try:
        return NotificationService.get_user_notifications(user_id, limit=limit)
    except Exception as e:
        logger.warning(f"recent_notifications failed: {e}")
        return []


def inject_notification_context() -> Dict[str, Any]:
    """
    Jinja context processor payload: adds badges + recent items to all templates.
    Register via app.context_processor in app/__init__.py.
    """
    if not current_user.is_authenticated:
        return {}
    badges = dashboard_badges()
    return {
        'notif_badges': badges,
        'recent_notifications': recent_notifications(limit=5),
    }
