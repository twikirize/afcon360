# app/models/system_config.py
"""
System configuration model for storing platform-wide settings
"""

from sqlalchemy import Column, String, Text, BigInteger, ForeignKey, Boolean, DateTime
from app.models.base import BaseModel
from app.extensions import db
from datetime import datetime, timezone
import json
import logging


logger = logging.getLogger(__name__)


class SystemConfig(BaseModel):
    """System configuration key-value store"""
    __tablename__ = 'system_configs'

    key = Column(String(100), unique=True, nullable=False, index=True)
    value = Column(Text, nullable=True)
    value_type = Column(String(20), default='str')
    category = Column(String(50), default='general', index=True)
    description = Column(Text, nullable=True)
    is_public = Column(Boolean, default=False)
    requires_restart = Column(Boolean, default=False)
    updated_by = Column(BigInteger, ForeignKey('users.id'), nullable=True)
    
    _SECRET_KEYS = frozenset({"TWILIO_AUTH_TOKEN"})
    _SECRET_PREFIX = "afcon360:fernet:v1:"

    @classmethod
    def _encrypt_secret(cls, value: str) -> str:
        """Encrypt an owner-supplied integration secret using the deployment key."""
        from app.utils.security import _get_fernet

        encrypted = _get_fernet().encrypt(value.encode("utf-8")).decode("ascii")
        return f"{cls._SECRET_PREFIX}{encrypted}"

    @classmethod
    def _decrypt_secret(cls, value: str) -> str:
        """Read current encrypted values and legacy plaintext values during rotation."""
        if not isinstance(value, str) or not value.startswith(cls._SECRET_PREFIX):
            # Existing deployments may have saved this value before encryption
            # was added. Continue reading it so the owner can rotate/re-save it.
            return value or ""

        from app.utils.security import _get_fernet

        try:
            token = value[len(cls._SECRET_PREFIX):].encode("ascii")
            return _get_fernet().decrypt(token).decode("utf-8")
        except Exception:
            logger.error(
                "Unable to decrypt stored Twilio Auth Token; check preserved ENCRYPTION_KEY"
            )
            raise RuntimeError(
                "Stored Twilio Auth Token cannot be decrypted with the configured ENCRYPTION_KEY"
            ) from None

    def __repr__(self):
        if self.key in self._SECRET_KEYS:
            display_value = "[REDACTED]"
        else:
            display_value = self.value
        return f'<SystemConfig {self.key}={display_value}>'
    
    @classmethod
    def get(cls, key: str, default=None):
        """Get a configuration value by key with type handling"""
        setting = cls.query.filter_by(key=key).first()
        if not setting:
            return default
        
        if key in cls._SECRET_KEYS:
            if setting.value is None:
                return default
            secret = cls._decrypt_secret(setting.value)
            return secret or default

        if setting.value_type == 'bool':
            return setting.value.lower() in ('true', '1', 'yes', 'on') if setting.value else False
        elif setting.value_type == 'int':
            try:
                return int(setting.value)
            except (ValueError, TypeError):
                return default
        elif setting.value_type == 'json':
            try:
                return json.loads(setting.value) if setting.value else {}
            except (ValueError, TypeError):
                return default
        return setting.value or default

    @classmethod
    def set(cls, key: str, value, value_type='str', category='general', description=None,
            is_public=False, requires_restart=False, updated_by=None, commit=True):
        """Create or update a system setting"""
        setting = cls.query.filter_by(key=key).first()
        if not setting:
            setting = cls(key=key)
            db.session.add(setting)

        if key in cls._SECRET_KEYS:
            if value is None:
                setting.value = None
            elif str(value).strip():
                # Blank password fields mean "keep the saved token". The owner
                # rotates it by entering a new value; a missing form value never
                # erases working production credentials.
                setting.value = cls._encrypt_secret(str(value).strip())
            elif setting.value and not setting.value.startswith(cls._SECRET_PREFIX):
                # A save from the owner settings page also upgrades a legacy
                # plaintext value without requiring the owner to retype it.
                setting.value = cls._encrypt_secret(setting.value)
            elif not setting.value:
                setting.value = ''
        elif value is None:
            setting.value = None
        else:
            if value_type == 'bool':
                setting.value = 'true' if value else 'false'
            elif value_type == 'int':
                setting.value = str(int(value))
            elif value_type == 'json':
                # Normalise string input so a caller passing a JSON document as
                # text cannot double-encode it (which previously stored a quoted
                # string and silently broke every json-typed consumer).
                if isinstance(value, str):
                    try:
                        value = json.loads(value)
                    except (ValueError, TypeError):
                        pass
                setting.value = json.dumps(value)
            else:
                setting.value = str(value)

        setting.value_type = value_type
        setting.category = category
        setting.description = description
        setting.is_public = is_public
        setting.requires_restart = requires_restart
        setting.updated_by = updated_by
        setting.updated_at = datetime.now(timezone.utc)

        if commit:
            db.session.commit()

        # Invalidate KYC runtime caches whenever a kyc_* setting is written so a
        # policy change is honoured immediately instead of up to one cache-TTL
        # later (and without requiring an app restart).
        if category == 'kyc' or (isinstance(key, str) and key.lower().startswith('kyc_')):
            try:
                from app.kyc_config_schema import clear_kyc_config_cache
                clear_kyc_config_cache()
            except Exception:
                pass

        return setting

    @classmethod
    def initialize_defaults(cls, commit=True):
        """Initialize default system settings.

        Returns the number of settings created. When ``commit`` is ``False``
        the caller owns transaction control (used by ``flask
        init-wallet-config`` so both initializers commit together).
        """
        defaults = [
            # REQUIRE_OWNER_MFA is intentionally not default-seeded here. Its
            # absence must preserve the explicit bootstrap environment value;
            # once saved, the owner-controlled database setting is authoritative.
            {'key': 'SITE_NAME', 'value': 'AFCON 360', 'value_type': 'str', 'category': 'branding', 'description': 'Site display name'},
            {'key': 'MAINTENANCE_MODE', 'value': 'false', 'value_type': 'bool', 'category': 'system', 'description': 'Enable maintenance mode'},
            {'key': 'SOCKETIO_ENABLED', 'value': 'true', 'value_type': 'bool', 'category': 'system', 'description': 'Enable Socket.IO real-time streaming. Requires an app restart.', 'requires_restart': True},
            {'key': 'payment_cash_globally_enabled', 'value': 'true', 'value_type': 'bool', 'category': 'payments', 'description': 'Allow cash payments system-wide'},
            {'key': 'payment_cash_development_mode', 'value': 'true', 'value_type': 'bool', 'category': 'payments', 'description': 'Bypass fraud checks for cash (development/testing)'},
            {'key': 'payment_cash_requires_kyc', 'value': 'true', 'value_type': 'bool', 'category': 'payments', 'description': 'Require KYC for cash payments'},
            {'key': 'payment_cash_min_kyc_level', 'value': '2', 'value_type': 'int', 'category': 'payments', 'description': 'Minimum KYC level for cash'},
            {'key': 'payment_cash_requires_verified_phone', 'value': 'true', 'value_type': 'bool', 'category': 'payments', 'description': 'Require phone verification for cash'},
            {'key': 'payment_cash_requires_verified_email', 'value': 'true', 'value_type': 'bool', 'category': 'payments', 'description': 'Require email verification for cash'},
            {'key': 'payment_cash_requires_previous_booking', 'value': 'true', 'value_type': 'bool', 'category': 'payments', 'description': 'Require at least 1 previous booking for cash'},
            {'key': 'payment_cash_max_amount', 'value': '500000', 'value_type': 'int', 'category': 'payments', 'description': 'Maximum cash booking amount (UGX)'},
            {'key': 'payment_cash_default_deposit_pct', 'value': '30', 'value_type': 'int', 'category': 'payments', 'description': 'Default deposit percentage for cash bookings'},
            {'key': 'home_feed_layout', 'value': 'mixed', 'value_type': 'str', 'category': 'homepage', 'description': 'Homepage feed layout mode (mixed/sections/tabbed)', 'is_public': True},
            # OCI Email Delivery (Owner/Super Admin configurable)
            {'key': 'OCI_EMAIL_REGION', 'value': 'eu-frankfurt-1', 'value_type': 'str', 'category': 'email', 'description': 'OCI Email Delivery region (e.g., eu-frankfurt-1)'},
            {'key': 'OCI_EMAIL_COMPARTMENT_ID', 'value': '', 'value_type': 'str', 'category': 'email', 'description': 'OCI Compartment OCID for Email Delivery'},
            {'key': 'OCI_EMAIL_SENDER_ADDRESS', 'value': 'noreply@pamoja.space', 'value_type': 'str', 'category': 'email', 'description': 'Approved sender email address in OCI Email Delivery'},
            {'key': 'OCI_EMAIL_SUPPRESSION_LIST', 'value': 'true', 'value_type': 'bool', 'category': 'email', 'description': 'Use OCI suppression list for bounces/complaints'},
            # Twilio SMS/WhatsApp (Owner/Super Admin configurable) - ALL OFF BY DEFAULT
            {'key': 'TWILIO_ACCOUNT_SID', 'value': '', 'value_type': 'str', 'category': 'sms', 'description': 'Twilio Account SID'},
            {'key': 'TWILIO_AUTH_TOKEN', 'value': '', 'value_type': 'str', 'category': 'sms', 'description': 'Twilio Auth Token'},
            {'key': 'TWILIO_FROM_NUMBER', 'value': '', 'value_type': 'str', 'category': 'sms', 'description': 'Twilio verified sender phone number (E.164 format)'},
            {'key': 'TWILIO_MESSAGING_SERVICE_SID', 'value': '', 'value_type': 'str', 'category': 'sms', 'description': 'Twilio Messaging Service SID (optional, alternative to from_number)'},
            {'key': 'TWILIO_WHATSAPP_FROM', 'value': '', 'value_type': 'str', 'category': 'sms', 'description': 'Twilio WhatsApp sender (e.g., whatsapp:+14155238886)'},
            {'key': 'TWILIO_WHATSAPP_ENABLED', 'value': 'false', 'value_type': 'bool', 'category': 'sms', 'description': 'Enable WhatsApp via Twilio'},
            {'key': 'TWILIO_SMS_ENABLED', 'value': 'false', 'value_type': 'bool', 'category': 'sms', 'description': 'Enable SMS via Twilio'},
        ]

        # KYC configuration (Owner/Super Admin configurable). Seeded from the
        # single source of truth in app/kyc_config_schema so the page, the
        # runtime getters and the database defaults never drift apart.
        from app.kyc_config_schema import KYC_CONFIG_SCHEMA
        import json as _json

        for item in KYC_CONFIG_SCHEMA:
            default = item['default']
            if item['type'] == 'json':
                value = _json.dumps(default)
            elif item['type'] == 'bool':
                value = 'true' if default else 'false'
            elif item['type'] == 'int':
                value = None if default is None else str(int(default))
            else:
                value = str(default)
            defaults.append({
                'key': item['key'],
                'value': value,
                'value_type': item['type'],
                'category': 'kyc',
                'description': f"{item['label']}: {item['description']}",
            })
        created = 0
        for item in defaults:
            if not cls.query.filter_by(key=item['key']).first():
                db.session.add(cls(**item))
                created += 1
        if commit:
            db.session.commit()
        return created

