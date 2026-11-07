from datetime import datetime, timezone
import logging
from sqlalchemy import (
    Column,
    Boolean,
    String,
    Integer,
    DateTime,
    JSON,
    ForeignKey,
)
from sqlalchemy.orm import relationship
from app.extensions import db
from app.models.base import BaseModel

logger = logging.getLogger(__name__)


class AuthConfiguration(BaseModel):
    """
    Stores authentication and verification service settings.
    Only accessible by app owner role.
    """
    __tablename__ = "auth_configurations"
    
    # Google OAuth
    google_oauth_enabled = Column(Boolean, default=True, nullable=False)
    google_client_id = Column(String(255), nullable=True)
    google_client_secret = Column(String(255), nullable=True)
    
    # SendGrid Email Service
    sendgrid_enabled = Column(Boolean, default=True, nullable=False)
    sendgrid_api_key = Column(String(255), nullable=True)
    sendgrid_from_email = Column(String(255), nullable=True)
    sendgrid_from_name = Column(String(255), default="AFCON360", nullable=True)
    
    # Twilio SMS Service (Global)
    twilio_enabled = Column(Boolean, default=False, nullable=False)
    twilio_account_sid = Column(String(255), nullable=True)
    twilio_auth_token = Column(String(255), nullable=True)
    twilio_phone_number = Column(String(255), nullable=True)
    
    # Africa's Talking SMS Service (Africa)
    africa_talking_enabled = Column(Boolean, default=False, nullable=False)
    africa_talking_username = Column(String(255), nullable=True)
    africa_talking_api_key = Column(String(255), nullable=True)
    
    # SMS Routing Configuration
    sms_provider_preference = Column(
        String(50), 
        default='auto', 
        nullable=False
    )  # Options: auto, twilio, africa_talking
    african_countries = Column(
        JSON, 
        default=lambda: ['UG', 'KE', 'TZ', 'RW', 'BI', 'CD', 'SS', 'ET', 'SO', 'DZ', 'AO', 'BW', 'NA', 'ZA', 'ZW', 'ZM', 'MW', 'MZ', 'NG', 'GH', 'CI', 'SN', 'ML', 'BF', 'NE', 'TD', 'SD', 'LY', 'EG', 'MA', 'TN', 'DZ'],
        nullable=False
    )
    
    # Feature Flags - Verification Requirements
    email_verification_required = Column(Boolean, default=False, nullable=False)
    phone_verification_required = Column(Boolean, default=False, nullable=False)
    google_oauth_required = Column(Boolean, default=False, nullable=False)
    otp_channels = Column(
        JSON,
        default=lambda: {"email": {"enabled": True, "priority": 1}, "sms": {"enabled": False, "priority": 2}, "whatsapp": {"enabled": False, "priority": 3}},
        nullable=False
    )
    email_verification_required_for = Column(
        JSON,
        default=lambda: ["booking", "payment"],
        nullable=False
    )
    
    # Feature Flags - KYC Requirements
    kyc_required_for_tier_2 = Column(Boolean, default=True, nullable=False)
    kyc_required_for_tier_3 = Column(Boolean, default=True, nullable=False)
    
    # Feature Flags - Signup Restrictions
    allow_email_password_signup = Column(Boolean, default=True, nullable=False)
    allow_google_oauth_signup = Column(Boolean, default=True, nullable=False)
    
    # Rate Limiting
    email_verification_rate_limit = Column(Integer, default=5, nullable=False)  # Per hour
    sms_verification_rate_limit = Column(Integer, default=3, nullable=False)  # Per hour
    
    # Audit fields
    updated_by = Column(Integer, ForeignKey('users.id'), nullable=True)
    
    # Relationships
    updater = relationship('User', foreign_keys=[updated_by])
    
    def __repr__(self):
        return f"<AuthConfiguration id={self.id} google_oauth={self.google_oauth_enabled}>"

    @staticmethod
    def _sms_delivery_enabled():
        """Return the provider-neutral outbound SMS master switch."""
        try:
            from flask import current_app, has_app_context
            if not has_app_context():
                return False
            value = current_app.config.get('SMS_DELIVERY_ENABLED', False)
            if isinstance(value, str):
                return value.strip().lower() in {'1', 'true', 'yes', 'on'}
            return value is True
        except Exception:
            return False

    def get_phone_verification_transport(self):
        """Return the active phone OTP transport, defaulting safely to email.

        A stale saved SMS choice can never bypass the global SMS kill switch.
        """
        channels = self.otp_channels if isinstance(self.otp_channels, dict) else {}
        phone_settings = channels.get('phone_verification', {})
        transport = phone_settings.get('transport') if isinstance(phone_settings, dict) else None
        if transport == 'sms' and self._sms_delivery_enabled():
            return 'sms'
        return 'email'

    def set_phone_verification_transport(self, transport):
        """Persist a validated owner-selected phone OTP transport."""
        if transport not in {'email', 'sms'}:
            raise ValueError("Phone verification transport must be 'email' or 'sms'")
        if transport == 'sms' and not self._sms_delivery_enabled():
            raise ValueError("SMS delivery is globally disabled until a provider is configured and activated")

        channels = dict(self.otp_channels or {})
        phone_settings = dict(channels.get('phone_verification') or {})
        phone_settings['transport'] = transport
        channels['phone_verification'] = phone_settings
        self.otp_channels = channels

    def get_sms_provider_for_phone(self, phone_number):
        """Resolve the configured SMS provider for a phone number."""
        phone_number = (phone_number or '').strip()
        country_code = 'UG'
        country_prefixes = {
            '+1': 'US',
            '+20': 'EG',
            '+27': 'ZA',
            '+250': 'RW',
            '+254': 'KE',
            '+255': 'TZ',
            '+256': 'UG',
            '+257': 'BI',
            '+44': 'GB',
        }
        for prefix, country in sorted(country_prefixes.items(), key=lambda item: len(item[0]), reverse=True):
            if phone_number.startswith(prefix):
                country_code = country
                break
        return self.get_active_sms_provider(country_code)
    
    def get_active_sms_provider(self, country_code):
        """
        Determine which SMS provider to use based on configuration and location.

        Returns:
            String: 'twilio', 'africa_talking', or None.
        """
        if not self._sms_delivery_enabled():
            return None

        # The unified owner OTP settings page writes these operational toggles
        # to SystemConfig. The AuthConfiguration flags remain a compatibility
        # source for the older authentication settings page.
        try:
            from app.models.system_config import SystemConfig
            twilio_enabled = bool(self.twilio_enabled) or bool(
                SystemConfig.get('TWILIO_SMS_ENABLED', False)
            )
        except Exception:
            twilio_enabled = bool(self.twilio_enabled)
        try:
            from app.models.system_config import SystemConfig
            africa_enabled = bool(self.africa_talking_enabled) or bool(
                SystemConfig.get('AFRICA_TALKING_SMS_ENABLED', False)
            )
        except Exception:
            africa_enabled = bool(self.africa_talking_enabled)

        if self.sms_provider_preference == 'twilio':
            return 'twilio' if twilio_enabled else None
        elif self.sms_provider_preference == 'africa_talking':
            return 'africa_talking' if africa_enabled else None

        # Auto routing based on location
        african_countries = self.african_countries or []
        if country_code in african_countries:
            if africa_enabled:
                return 'africa_talking'
            elif twilio_enabled:
                return 'twilio'
        else:
            if twilio_enabled:
                return 'twilio'
            elif africa_enabled:
                return 'africa_talking'
        
        return None
    
    @classmethod
    def get_config(cls):
        """Get the current auth configuration (singleton pattern)"""
        # Expire any cached instance so callers (e.g. the registration policy)
        # always see the latest owner-managed values, not a stale copy from an
        # earlier read in the same session.
        try:
            from app.extensions import db
            db.session.expire_all()
        except Exception:
            pass
        config = cls.query.first()
        if not config:
            # Create default configuration
            config = cls(
                google_oauth_enabled=True,
                sendgrid_enabled=True,
                twilio_enabled=False,
                africa_talking_enabled=False,
                sms_provider_preference='auto',
                email_verification_required=False,
                phone_verification_required=False,
                google_oauth_required=False,
                otp_channels={"email": {"enabled": True, "priority": 1}, "sms": {"enabled": False, "priority": 2}, "whatsapp": {"enabled": False, "priority": 3}},
                email_verification_required_for=["booking", "payment"],
                allow_email_password_signup=True,
                allow_google_oauth_signup=True,
            )
            db.session.add(config)
            db.session.commit()
        return cls._hydrate_provider_secrets(config)

    @classmethod
    def _hydrate_provider_secrets(cls, config):
        """Hydrate Google, SendGrid and Africa's Talking secrets from encrypted storage.

        Twilio credentials remain in the encrypted SystemConfig store introduced
        by the current SMS adapter work.
        """
        encrypted_fields = (
            'google_client_secret',
            'sendgrid_api_key',
            'africa_talking_username',
            'africa_talking_api_key',
        )
        try:
            from sqlalchemy.orm.attributes import set_committed_value
            from app.notifications.models import CommunicationSettings
            from app.notifications.settings import CommunicationSettingsService
            from app.utils.log_redaction import register_secret_mapping

            setting = CommunicationSettings.query.filter_by(
                key='auth_providers',
                is_deleted=False,
            ).first()
            if setting is not None:
                try:
                    stored = CommunicationSettingsService._decrypt_config(setting.config or {})
                except Exception as exc:
                    for field in encrypted_fields:
                        set_committed_value(config, field, None)
                    logger.error(
                        'Encrypted auth provider credentials unavailable (exception_type=%s)',
                        type(exc).__name__,
                    )
                    return config
                for field in encrypted_fields:
                    set_committed_value(config, field, stored.get(field))

            register_secret_mapping({
                field: getattr(config, field, None)
                for field in encrypted_fields
            })
        except Exception as exc:
            # During early bootstrap the shared settings table may not yet be
            # available. Keep existing legacy values readable until the owner
            # performs the encrypted first save; never log their contents.
            try:
                db.session.rollback()
            except Exception:
                pass
            logger.warning(
                'Encrypted auth provider settings unavailable (exception_type=%s)',
                type(exc).__name__,
            )
            try:
                from app.utils.log_redaction import register_secret_mapping
                register_secret_mapping({
                    field: getattr(config, field, None)
                    for field in encrypted_fields
                })
            except Exception:
                pass
        return config
    
    def to_dict(self, include_secrets=False):
        """
        Convert configuration to dictionary.
        Secrets are excluded by default for security.
        
        Args:
            include_secrets: If True, include API keys and secrets
            
        Returns:
            Dictionary representation
        """
        data = {
            'id': self.id,
            'google_oauth_enabled': self.google_oauth_enabled,
            'sendgrid_enabled': self.sendgrid_enabled,
            'twilio_enabled': self.twilio_enabled,
            'africa_talking_enabled': self.africa_talking_enabled,
            'sms_provider_preference': self.sms_provider_preference,
            'african_countries': self.african_countries,
            'email_verification_required': self.email_verification_required,
            'phone_verification_required': self.phone_verification_required,
            'google_oauth_required': self.google_oauth_required,
            'otp_channels': self.otp_channels,
            'email_verification_required_for': self.email_verification_required_for,
            'kyc_required_for_tier_2': self.kyc_required_for_tier_2,
            'kyc_required_for_tier_3': self.kyc_required_for_tier_3,
            'allow_email_password_signup': self.allow_email_password_signup,
            'allow_google_oauth_signup': self.allow_google_oauth_signup,
            'email_verification_rate_limit': self.email_verification_rate_limit,
            'sms_verification_rate_limit': self.sms_verification_rate_limit,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }
        
        if include_secrets:
            twilio_sid_configured = bool(self.twilio_account_sid)
            twilio_token_configured = bool(self.twilio_auth_token)
            try:
                from app.models.system_config import SystemConfig
                twilio_sid_configured = bool(
                    SystemConfig.get('TWILIO_ACCOUNT_SID', '') or twilio_sid_configured
                )
                twilio_token_configured = bool(
                    SystemConfig.get('TWILIO_AUTH_TOKEN', '') or twilio_token_configured
                )
            except Exception:
                pass
            # Compatibility callers may ask for secret status, never values.
            data.update({
                'google_client_id': self.google_client_id,
                'google_client_secret_configured': bool(self.google_client_secret),
                'sendgrid_api_key_configured': bool(self.sendgrid_api_key),
                'twilio_account_sid_configured': twilio_sid_configured,
                'twilio_auth_token_configured': twilio_token_configured,
                'africa_talking_username_configured': bool(self.africa_talking_username),
                'africa_talking_api_key_configured': bool(self.africa_talking_api_key),
                'sendgrid_from_email': self.sendgrid_from_email,
                'sendgrid_from_name': self.sendgrid_from_name,
                'twilio_phone_number': self.twilio_phone_number,
            })

        return data
