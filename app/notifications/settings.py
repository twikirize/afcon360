"""
AFCON360 Communication Settings Service

Manages communication provider configuration (Twilio, SendGrid, FCM, WhatsApp, etc.)
and resolves which aggregator to use per channel. Respects the dual-ID system and
RBAC — only owner/super_admin/admin may mutate settings.

Secrets stored in the credentials/config JSON columns are encrypted at rest using
the app's ENCRYPTION_KEY via the shared crypto helper.
"""

import logging
import re
from typing import Dict, Any, List, Optional

from app.extensions import db
from app.utils.log_redaction import is_sensitive_name, register_secret_mapping

from app.notifications.models import (
    CommunicationSettings,
    NotificationAggregator,
    NotificationChannel,
)

logger = logging.getLogger(__name__)

# These belong in protected process/server secrets, never in provider records.
_RUNTIME_SECRET_FIELDS = frozenset({
    "secret_key", "app_secret_key", "encryption_key", "security_salt",
    "wtf_csrf_secret_key", "database_url", "sqlalchemy_database_uri",
    "db_host", "db_port", "db_name", "db_user", "db_username",
    "db_pass", "db_password", "postgres_host", "postgres_port",
    "postgres_db", "postgres_user", "postgres_username", "postgres_pass",
    "postgres_password", "redis_url", "redis_host", "redis_port",
    "redis_user", "redis_username", "redis_pass", "redis_password",
    "celery_broker_url", "celery_result_backend",
})


def _assert_no_runtime_secret_fields(value: Any, parent_path: tuple = ()) -> None:
    """Reject root application/database/Redis secrets in provider records."""
    root_namespaces = {
        "app", "flask", "db", "database", "postgres", "postgresql", "redis",
        "celery",
    }
    connection_fields = {
        "url", "uri", "dsn", "host", "port", "name", "user", "username",
        "pass", "password", "credentials", "credential", "broker", "backend",
        "result",
    }
    if isinstance(value, dict):
        for raw_key, item in value.items():
            key = re.sub(r"[^a-z0-9]+", "_", str(raw_key).strip().lower()).strip("_")
            key_parts = tuple(part for part in key.split("_") if part)
            current_path = parent_path + key_parts
            in_root_namespace = bool(set(parent_path).intersection(root_namespaces))
            root_service_field = (
                (in_root_namespace and bool(set(key_parts).intersection(connection_fields)))
                or (
                    key.startswith(("db_", "database_", "postgres_", "postgresql_", "redis_"))
                    and bool(set(key_parts).intersection(connection_fields))
                )
            )
            if key in _RUNTIME_SECRET_FIELDS or root_service_field:
                raise ValueError(
                    "System secrets must be configured through protected server-side secrets"
                )
            _assert_no_runtime_secret_fields(item, current_path)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _assert_no_runtime_secret_fields(item, parent_path)
    elif isinstance(value, str):
        candidate = value.strip().lower()
        if candidate.startswith((
            "postgres://", "postgresql://", "postgresql+", "redis://", "rediss://"
        )):
            raise ValueError(
                "Database and Redis connection strings must remain server-side secrets"
            )


# Default provider catalog — what the system can integrate with out of the box.
PROVIDER_CATALOG = {
    'email': [
        {'provider': 'smtp', 'label': 'Owner-managed SMTP (shared by web and Celery)'},
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
        if commit:
            db.session.commit()
        return setting

    @classmethod
    def get_provider_config(cls, channel: str) -> Optional[Dict[str, Any]]:
        """Return decrypted internal config for an enabled channel provider.

        This method is internal-only. API serializers must always redact its
        result before returning anything to a browser.
        """
        # Preserve legacy channel-based resolution for SMS, push and webhook
        # providers. Owner SMTP has its own canonical email_provider resolver.
        setting = CommunicationSettings.query.filter_by(
            channel=channel,
            enabled=True,
            is_deleted=False,
        ).first()
        if not setting:
            return None
        config = cls._decrypt_config(setting.config or {})
        # One-time migration for older rows saved by the former plaintext fallback.
        from app.utils.crypto import is_encrypted_json
        if config and not is_encrypted_json(setting.config):
            setting.config = cls._encrypt_config(config)
            db.session.commit()
        return {
            'provider': setting.provider,
            'config': config,
            'key': setting.key,
        }

    @classmethod
    def get_email_setting(cls) -> Optional[CommunicationSettings]:
        """Fetch the one canonical Owner-managed email provider row, enabled or not."""
        return CommunicationSettings.query.filter_by(
            key="email_provider",
            channel="email",
            is_deleted=False,
        ).first()

    @classmethod
    def resolve_email_transport_config(cls) -> Dict[str, Any]:
        """Resolve the shared SMTP transport configuration.

        The database row is authoritative once created. Environment settings
        are only a migration fallback for installations that have not yet
        configured an Owner-managed provider.
        """
        setting = cls.get_email_setting()
        if setting is not None:
            if not setting.enabled:
                raise RuntimeError("Email delivery is disabled by Owner configuration")
            provider = (setting.provider or "smtp").strip().lower()
            if provider != "smtp":
                raise RuntimeError("The configured email provider is not supported by this SMTP transport")
            config = cls._decrypt_config(setting.config or {})
            from app.utils.crypto import is_encrypted_json
            if config and not is_encrypted_json(setting.config):
                setting.config = cls._encrypt_config(config)
                db.session.commit()
            resolved = {
                "provider": provider,
                "smtp_host": config.get("smtp_host") or config.get("MAIL_SERVER"),
                "smtp_port": config.get("smtp_port") or config.get("MAIL_PORT") or 587,
                "smtp_user": config.get("smtp_user") or config.get("MAIL_USERNAME"),
                "smtp_pass": config.get("smtp_pass") or config.get("MAIL_PASSWORD"),
                "use_tls": config.get("use_tls", config.get("MAIL_USE_TLS", True)),
                "use_ssl": config.get("use_ssl", config.get("MAIL_USE_SSL", False)),
                "default_sender": config.get("default_sender") or config.get("MAIL_DEFAULT_SENDER"),
                "source": "database",
            }
            register_secret_mapping(config)
            return resolved

        # Legacy environment fallback. Web and worker execute this same resolver.
        from flask import current_app
        cfg = current_app.config
        return {
            "provider": "smtp",
            "smtp_host": cfg.get("MAIL_SERVER"),
            "smtp_port": cfg.get("MAIL_PORT", 587),
            "smtp_user": cfg.get("MAIL_USERNAME"),
            "smtp_pass": cfg.get("MAIL_PASSWORD"),
            "use_tls": cfg.get("MAIL_USE_TLS", True),
            "use_ssl": cfg.get("MAIL_USE_SSL", False),
            "default_sender": cfg.get("MAIL_DEFAULT_SENDER"),
            "source": "environment",
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
        clear_secret_keys: List[str] = None,
        commit: bool = True,
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
            if not isinstance(config, dict):
                raise TypeError("Provider configuration must be an object")
            existing = cls._decrypt_config(setting.config or {})
            merged = dict(existing)
            clear_keys = set(clear_secret_keys or [])
            for secret_key in clear_keys:
                if not is_sensitive_name(secret_key):
                    raise ValueError("Only secret fields may be explicitly cleared")
                merged.pop(secret_key, None)
            for name, value in config.items():
                if is_sensitive_name(name) and (
                    value is None or value == "" or value == "***REDACTED***"
                ):
                    # A blank password field means "keep the existing secret".
                    continue
                merged[name] = value
            register_secret_mapping(merged)
            setting.config = cls._encrypt_config(merged)
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
        clear_webhook_url: bool = False,
    ) -> NotificationAggregator:
        agg = NotificationAggregator.query.filter_by(name=name, is_deleted=False).first()
        if not agg:
            agg = NotificationAggregator(name=name)
            db.session.add(agg)
        agg.provider_type = provider_type
        agg.channels = channels
        agg.enabled = enabled

        existing = cls._decrypt_config(agg.credentials or {})
        merged = dict(existing)
        if credentials is not None:
            if not isinstance(credentials, dict):
                raise TypeError("Aggregator credentials must be an object")
            for name, value in credentials.items():
                if is_sensitive_name(name) and (
                    value is None or value == "" or value == "***REDACTED***"
                ):
                    continue
                merged[name] = value

        # Webhook URLs may contain embedded API tokens or Basic Auth. Move both
        # new and legacy plaintext values into the encrypted credential envelope.
        if clear_webhook_url:
            merged.pop("webhook_url", None)
        else:
            effective_webhook_url = webhook_url or agg.webhook_url
            if effective_webhook_url:
                merged["webhook_url"] = effective_webhook_url

        if credentials is not None or existing or webhook_url or agg.webhook_url or clear_webhook_url:
            register_secret_mapping(merged)
            agg.credentials = cls._encrypt_config(merged)
        agg.webhook_url = None
        agg.priority = priority
        agg.updated_by = updated_by
        db.session.commit()
        return agg

    # ------------------------------------------------------------------
    # Encryption helpers (defer to shared crypto utility)
    # ------------------------------------------------------------------

    @staticmethod
    def _encrypt_config(cfg: Dict[str, Any]) -> Dict[str, Any]:
        """Encrypt the complete configuration before persisting it.

        Fail closed: a missing/invalid ENCRYPTION_KEY must prevent the write.
        Never silently store plaintext credentials.
        """
        if not isinstance(cfg, dict):
            raise TypeError("Provider configuration must be an object")
        _assert_no_runtime_secret_fields(cfg)
        from app.utils.crypto import encrypt_json
        register_secret_mapping(cfg)
        return encrypt_json(cfg)

    @staticmethod
    def _decrypt_config(cfg: Dict[str, Any]) -> Dict[str, Any]:
        """Decrypt stored configuration; invalid ciphertext is never returned."""
        from app.utils.crypto import decrypt_json
        result = decrypt_json(cfg)
        register_secret_mapping(result)
        return result
