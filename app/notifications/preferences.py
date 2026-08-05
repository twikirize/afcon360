"""
AFCON360 Notification Preferences Service

Manages per-user, per-type, per-channel notification preferences.
"""

from typing import List, Optional
from app.extensions import db
from app.notifications.models import UserNotificationPreference, NotificationType, NotificationChannel


class PreferenceService:
    """Manages user notification preferences."""

    @staticmethod
    def get_preferences(user_id: int) -> List[UserNotificationPreference]:
        """Get all notification preferences for a user."""
        return UserNotificationPreference.query.filter_by(user_id=user_id).all()

    @staticmethod
    def get_preference(user_id: int, notification_type: str, channel: str) -> Optional[UserNotificationPreference]:
        """Get a specific preference for a user."""
        return UserNotificationPreference.query.filter_by(
            user_id=user_id,
            notification_type=notification_type,
            channel=channel,
        ).first()

    @staticmethod
    def update_preference(user_id: int, notification_type: str, channel: str, enabled: bool) -> UserNotificationPreference:
        """
        Update or create a notification preference.
        """
        pref = PreferenceService.get_preference(user_id, notification_type, channel)
        if pref:
            pref.enabled = enabled
        else:
            pref = UserNotificationPreference(
                user_id=user_id,
                notification_type=notification_type,
                channel=channel,
                enabled=enabled,
            )
            db.session.add(pref)
        db.session.commit()
        return pref

    @staticmethod
    def set_all_enabled(user_id: int, enabled: bool) -> int:
        """Enable or disable all preferences for a user."""
        prefs = PreferenceService.get_preferences(user_id)
        for pref in prefs:
            pref.enabled = enabled
        if prefs:
            db.session.commit()
        return len(prefs)

    @staticmethod
    def is_allowed(user_id: int, notification_type: str, channels: List[str]) -> bool:
        """
        Check if a user allows notifications of a given type on any of the specified channels.
        Returns True if at least one channel is enabled for this notification type.
        If no preferences exist for this type, defaults to True (notifications allowed).
        """
        for channel in channels:
            pref = PreferenceService.get_preference(user_id, notification_type, channel)
            if pref and pref.enabled:
                return True
            if pref is None:
                # No explicit preference = default to allowed
                return True
        # If we have explicit preferences and none are enabled, disallow
        # But if there are NO preferences at all for this type, allow by default
        has_any_pref = UserNotificationPreference.query.filter_by(
            user_id=user_id,
            notification_type=notification_type,
        ).first()
        return has_any_pref is None

    @staticmethod
    def get_enabled_channels(user_id: int, notification_type: str) -> List[str]:
        """Get list of enabled channels for a user and notification type."""
        prefs = UserNotificationPreference.query.filter_by(
            user_id=user_id,
            notification_type=notification_type,
            enabled=True,
        ).all()
        return [pref.channel for pref in prefs]

    @staticmethod
    def delete_preference(user_id: int, notification_type: str, channel: str) -> bool:
        """Delete a specific preference."""
        pref = PreferenceService.get_preference(user_id, notification_type, channel)
        if pref:
            db.session.delete(pref)
            db.session.commit()
            return True
        return False

    @staticmethod
    def get_all_for_user(user_id: int) -> List[dict]:
        """Return all preferences serialized for API."""
        prefs = PreferenceService.get_preferences(user_id)
        return [
            {
                'notification_type': p.notification_type,
                'channel': p.channel,
                'enabled': p.enabled,
            }
            for p in prefs
        ]

    @staticmethod
    def bulk_update(user_id: int, items: List[dict]) -> List[UserNotificationPreference]:
        """Bulk update/create preferences from a list of dicts.

        Each item: {notification_type, channel, enabled}
        """
        updated = []
        for item in items:
            ntype = item.get('notification_type')
            channel = item.get('channel')
            enabled = item.get('enabled', True)
            if not ntype or not channel:
                continue
            updated.append(
                PreferenceService.update_preference(user_id, ntype, channel, enabled)
            )
        return updated

    @staticmethod
    def set_channel_enabled(user_id: int, channel: str, enabled: bool) -> int:
        """Enable/disable every preference row for a given channel for the user.

        If the user has no rows for that channel yet, seed defaults from all
        NotificationType values so the toggle takes effect going forward.
        """
        prefs = UserNotificationPreference.query.filter_by(
            user_id=user_id, channel=channel
        ).all()
        if not prefs:
            # Seed defaults for all known types
            for ntype in NotificationType:
                db.session.add(UserNotificationPreference(
                    user_id=user_id,
                    notification_type=ntype.value,
                    channel=channel,
                    enabled=enabled,
                ))
        else:
            for pref in prefs:
                pref.enabled = enabled
        db.session.commit()
        return len(prefs) or len(list(NotificationType))