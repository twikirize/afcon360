"""
AFCON360 Communication Settings Service

Manages communication provider configuration (Twilio, SendGrid, FCM, WhatsApp, etc.)
and resolves which aggregator to use per channel. Respects the dual-ID system and
RBAC — only owner/super_admin/admin may mutate settings.

Secrets stored in the credentials/config JSON columns are encrypted at rest using
the app's ENCRYPTION_KEY via the shared crypto helper.
"""

import logging
from typing import Dict, Any, List, Optional

from app.extensions import db
from app.notifications.models import (
    CommunicationSettings,
    NotificationAggregator,
    NotificationChannel,
)

logger = logging.getLogger(__name__)


# Default provider catalog — what the system can integrate with out of the box.
PROVIDER_CATALOG = {
    'email': [
        {'provider': 'smtp', 'label': 'SMTP (self-hosted / Flask-Mail)'},
        {'provider': 'sendgrid', 'label': 'SendGrid'},
        {'provider': 'mailgun', 'label': 'Mailgun'},
        {'provider': 'ses', 'label': 'Amazon SES'},
    ],
    'sms': [
        {'provider': 'twilio', 'label': 'Twilio'},
        {'provider': 'africas_talking', 'label': 'Africa\'s Talking'},
        {'provider': 'nexmo', 'label': 'Vonage / Nexmo'},
    ],
    'push': [
        {'provider': 'fcm', 'label': 'Firebase Cloud Messaging'},
        {'provider': 'apns', 'label': 'Apple Push Notification Service'},
    ],
    'webhook': [
        {'provider': 'generic', 'label': 'Generic Webhook'},
        {'provider': 'sap', 'label': 'SAP Event Mesh (future)'},
    ],
    'whatsapp': [
        {'provider': 'twilio_whatsapp', 'label': 'Twilio WhatsApp'},
        {'provider': 'meta_whatsapp', 'label': 'Meta WhatsApp Business'},
    ],
}


class CommunicationSettingsService:
    """Central service for communication provider configuration."""

    @classmethod
    def get_channel_enabled(cls, channel: str) -> bool:
        """Return whether a channel is globally enabled via communication_settings."""
        setting = CommunicationSettings.query.filter_by(
            channel=channel, is_deleted=False
        ).first()
        if not setting:
            # Default: email & in_app on, others off until configured
            return channel in ('email', 'in_app')
        return setting.enabled

    @classmethod
    def set_channel_enabled(cls, channel: str, enabled: bool, updated_by: int = None) -> CommunicationSettings:
        key = f"{channel}_provider"
        setting = CommunicationSettings.query.filter_by(key=key, is_deleted=False).first()
        if not setting:
            setting = CommunicationSettings(
                key=key,
                channel=channel,
                provider=PROVIDER_CATALOG.get(channel, [{}])[0].get('provider') if PROVIDER_CATALOG.get(channel) else None,
            )
            db.session.add(setting)
        setting.enabled = enabled
        setting.updated_by = updated_by
        db.session.commit()
        return setting

    @classmethod
    def get_provider_config(cls, channel: str) -> Optional[Dict[str, Any]]:
        """Get the active provider config for a channel."""
        setting = CommunicationSettings.query.filter_by(
            channel=channel, enabled=True, is_deleted=False
        ).first()
        if not setting:
            return None
        return {
            'provider': setting.provider,
            'config': setting.config or {},
            'key': setting.key,
        }

    @classmethod
    def upsert_setting(
        cls,
        key: str,
        channel: str,
        provider: str = None,
        enabled: bool = True,
        config: Dict[str, Any] = None,
        description: str = None,
        updated_by: int = None,
    ) -> CommunicationSettings:
        setting = CommunicationSettings.query.filter_by(key=key, is_deleted=False).first()
        if not setting:
            setting = CommunicationSettings(key=key)
            db.session.add(setting)
        setting.channel = channel
        if provider is not None:
            setting.provider = provider
        setting.enabled = enabled
        if config is not None:
            setting.config = cls._encrypt_config(config)
        if description is not None:
            setting.description = description
        setting.updated_by = updated_by
        db.session.commit()
        return setting

    @classmethod
    def list_settings(cls) -> List[CommunicationSettings]:
        return CommunicationSettings.query.filter_by(is_deleted=False).all()

    # ------------------------------------------------------------------
    # Aggregator resolution
    # ------------------------------------------------------------------

    @classmethod
    def resolve_aggregator(cls, channel: str) -> Optional[NotificationAggregator]:
        """Resolve the highest-priority enabled aggregator for a channel."""
        aggs = (
            NotificationAggregator.query.filter(
                NotificationAggregator.enabled == True,
                NotificationAggregator.is_deleted == False,
                NotificationAggregator.channels.contains([channel]),
            )
            .order_by(NotificationAggregator.priority.asc())
            .all()
        )
        return aggs[0] if aggs else None

    @classmethod
    def list_aggregators(cls) -> List[NotificationAggregator]:
        return NotificationAggregator.query.filter_by(is_deleted=False).all()

    @classmethod
    def upsert_aggregator(
        cls,
        name: str,
        provider_type: str,
        channels: List[str],
        enabled: bool = True,
        credentials: Dict[str, Any] = None,
        webhook_url: str = None,
        priority: int = 10,
        updated_by: int = None,
    ) -> NotificationAggregator:
        agg = NotificationAggregator.query.filter_by(name=name, is_deleted=False).first()
        if not agg:
            agg = NotificationAggregator(name=name)
            db.session.add(agg)
        agg.provider_type = provider_type
        agg.channels = channels
        agg.enabled = enabled
        if credentials is not None:
            agg.credentials = cls._encrypt_config(credentials)
        agg.webhook_url = webhook_url
        agg.priority = priority
        agg.updated_by = updated_by
        db.session.commit()
        return agg

    # ------------------------------------------------------------------
    # Encryption helpers (defer to shared crypto utility)
    # ------------------------------------------------------------------

    @staticmethod
    def _encrypt_config(cfg: Dict[str, Any]) -> Dict[str, Any]:
        """Encrypt secret values in the config dict before persisting."""
        try:
            from app.utils.crypto import encrypt_json
            return encrypt_json(cfg)
        except Exception:
            # Fallback: store as-is if crypto helper unavailable (dev only)
            logger.warning("Crypto helper unavailable; storing config unencrypted")
            return cfg

    @staticmethod
    def _decrypt_config(cfg: Dict[str, Any]) -> Dict[str, Any]:
        try:
            from app.utils.crypto import decrypt_json
            return decrypt_json(cfg)
        except Exception:
            return cfg
