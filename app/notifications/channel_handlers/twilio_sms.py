"""
Twilio SMS Channel Handler

Sends SMS messages via Twilio REST API.
Supports both regular SMS and WhatsApp messages via Twilio's Messaging API.
"""

import logging
from typing import Dict, Any
from flask import current_app
from . import BaseChannelHandler

logger = logging.getLogger(__name__)


def _read_owner_setting(key: str):
    """Read a DB-backed setting only inside a Flask app context.

    NotificationService constructs channel handlers during module import, before
    Flask has pushed an application context. In that phase the handler must not
    query Flask-SQLAlchemy. A real decrypt failure must still fail closed.
    """
    from flask import has_app_context

    if not has_app_context():
        return None

    from app.models.system_config import SystemConfig
    try:
        return SystemConfig.get(key)
    except RuntimeError:
        # Never fall back to plaintext/env secrets if Fernet decryption fails.
        raise
    except Exception as exc:
        logger.warning(
            "System SMS setting unavailable (key=%s, exception_type=%s)",
            key,
            type(exc).__name__,
        )
        return None


class TwilioSmsHandler(BaseChannelHandler):
    """SMS handler using Twilio REST API."""
    channel_name = 'twilio_sms'

    def __init__(self, auth_config=None):
        self.auth_config = auth_config
        self.account_sid = self._get_config('TWILIO_ACCOUNT_SID')
        self.auth_token = self._get_config('TWILIO_AUTH_TOKEN')
        self.from_number = self._get_config('TWILIO_FROM_NUMBER')
        self.messaging_service_sid = self._get_config('TWILIO_MESSAGING_SERVICE_SID')
        self._enabled = bool(self._get_config('TWILIO_SMS_ENABLED', False)) or bool(
            getattr(auth_config, 'twilio_enabled', False)
        )
        self._client = None

    def _get_config(self, key: str, default=None):
        """Resolve owner settings first, then compatible auth config/env values."""
        val = _read_owner_setting(key)
        if val is not None and val != '':
            return val

        auth_fields = {
            'TWILIO_ACCOUNT_SID': 'twilio_account_sid',
            'TWILIO_AUTH_TOKEN': 'twilio_auth_token',
            'TWILIO_FROM_NUMBER': 'twilio_phone_number',
        }
        field = auth_fields.get(key)
        if field and self.auth_config is not None:
            value = getattr(self.auth_config, field, None)
            if value:
                return value

        import os
        env_val = os.getenv(key)
        if env_val is not None:
            return env_val
        return default

    def _refresh_config(self):
        """Refresh owner settings and invalidate a client after credential rotation."""
        previous_credentials = (self.account_sid, self.auth_token)
        account_sid = self._get_config('TWILIO_ACCOUNT_SID')
        auth_token = self._get_config('TWILIO_AUTH_TOKEN')
        if previous_credentials != (account_sid, auth_token):
            self._client = None

        self.account_sid = account_sid
        self.auth_token = auth_token
        self.from_number = self._get_config('TWILIO_FROM_NUMBER')
        self.messaging_service_sid = self._get_config('TWILIO_MESSAGING_SERVICE_SID')
        self._enabled = bool(self._get_config('TWILIO_SMS_ENABLED', False)) or bool(
            getattr(self.auth_config, 'twilio_enabled', False)
        )

    def _get_client(self):
        """Lazy initialization and refresh of the owner-managed Twilio client."""
        self._refresh_config()
        if not self._enabled:
            logger.warning("[Twilio SMS] SMS not enabled (TWILIO_SMS_ENABLED=false)")
            return None
        if self._client is None:
            if not self.account_sid or not self.auth_token:
                logger.warning("[Twilio SMS] Credentials not configured")
                return None
            try:
                from twilio.rest import Client
                self._client = Client(self.account_sid, self.auth_token)
                logger.info("[Twilio SMS] Client initialized")
            except Exception as exc:
                logger.warning(
                    "[Twilio SMS] Client initialization failed (exception_type=%s)",
                    type(exc).__name__,
                )
                return None
        return self._client

    def validate_recipient(self, recipient: dict) -> bool:
        phone = recipient.get('phone')
        return bool(phone and len(phone) >= 8)

    def deliver(self, notification, recipient: dict) -> dict:
        to_phone = recipient.get('phone')
        if not to_phone:
            return {'success': False, 'response_code': 400, 'response_body': 'No recipient phone number'}

        client = self._get_client()
        if not client:
            return {'success': False, 'response_code': 500, 'response_body': 'Twilio client not configured'}

        body_text = notification.body or ''
        if len(body_text) > 1600:
            body_text = body_text[:1597] + '...'

        try:
            # Build message parameters
            params = {
                'to': to_phone,
                'body': body_text,
            }

            # Use messaging service SID if configured, otherwise from_number
            if self.messaging_service_sid:
                params['messaging_service_sid'] = self.messaging_service_sid
            elif self.from_number:
                params['from_'] = self.from_number
            else:
                return {'success': False, 'response_code': 500, 'response_body': 'No from_number or messaging_service_sid configured'}

            message = client.messages.create(**params)

            logger.info(f"[Twilio SMS] Sent to {to_phone}: SID={message.sid}, Status={message.status}")
            return {
                'success': True,
                'external_id': message.sid,
                'response_code': 200,
                'response_body': f'Twilio SMS sent: {message.status}',
            }

        except Exception as exc:
            logger.warning(
                "[Twilio SMS] Delivery failed (exception_type=%s)",
                type(exc).__name__,
            )
            return {
                'success': False,
                'response_code': 502,
                'response_body': 'Twilio SMS delivery failed',
            }


class TwilioWhatsAppHandler(BaseChannelHandler):
    """WhatsApp handler using Twilio WhatsApp Business API."""
    channel_name = 'twilio_whatsapp'

    def __init__(self):
        self.account_sid = self._get_config('TWILIO_ACCOUNT_SID')
        self.auth_token = self._get_config('TWILIO_AUTH_TOKEN')
        self.whatsapp_from = self._get_config('TWILIO_WHATSAPP_FROM')  # e.g., 'whatsapp:+14155238886'
        self._enabled = self._get_config('TWILIO_WHATSAPP_ENABLED', False)
        self._client = None

    def _get_config(self, key: str, default=None):
        """Read owner-managed settings only when a Flask app context exists."""
        val = _read_owner_setting(key)
        if val is not None and val != '':
            return val

        import os
        env_val = os.getenv(key)
        if env_val is not None:
            return env_val
        return default

    def _refresh_config(self):
        """Refresh owner settings and invalidate a client after credential rotation."""
        previous_credentials = (self.account_sid, self.auth_token)
        account_sid = self._get_config('TWILIO_ACCOUNT_SID')
        auth_token = self._get_config('TWILIO_AUTH_TOKEN')
        if previous_credentials != (account_sid, auth_token):
            self._client = None

        self.account_sid = account_sid
        self.auth_token = auth_token
        self.whatsapp_from = self._get_config('TWILIO_WHATSAPP_FROM')
        self._enabled = bool(self._get_config('TWILIO_WHATSAPP_ENABLED', False))

    def _get_client(self):
        """Lazy initialization and refresh of the owner-managed Twilio client."""
        self._refresh_config()
        if not self._enabled:
            logger.warning("[Twilio WhatsApp] WhatsApp not enabled (TWILIO_WHATSAPP_ENABLED=false)")
            return None
        if self._client is None:
            if not self.account_sid or not self.auth_token:
                logger.warning("[Twilio WhatsApp] Credentials not configured")
                return None
            try:
                from twilio.rest import Client
                self._client = Client(self.account_sid, self.auth_token)
                logger.info("[Twilio WhatsApp] Client initialized")
            except Exception as exc:
                logger.warning(
                    "[Twilio WhatsApp] Client initialization failed (exception_type=%s)",
                    type(exc).__name__,
                )
                return None
        return self._client

    def validate_recipient(self, recipient: dict) -> bool:
        phone = recipient.get('phone')
        return bool(phone and len(phone) >= 8)

    def deliver(self, notification, recipient: dict) -> dict:
        to_phone = recipient.get('phone')
        if not to_phone:
            return {'success': False, 'response_code': 400, 'response_body': 'No recipient phone number'}

        # Ensure WhatsApp format: whatsapp:+1234567890
        if not to_phone.startswith('whatsapp:'):
            to_whatsapp = f'whatsapp:{to_phone}'
        else:
            to_whatsapp = to_phone

        client = self._get_client()
        if not client:
            return {'success': False, 'response_code': 500, 'response_body': 'Twilio client not configured'}

        if not self.whatsapp_from:
            return {'success': False, 'response_code': 500, 'response_body': 'TWILIO_WHATSAPP_FROM not configured'}

        body_text = notification.body or ''
        if len(body_text) > 1600:
            body_text = body_text[:1597] + '...'

        try:
            message = client.messages.create(
                from_=self.whatsapp_from,
                to=to_whatsapp,
                body=body_text,
            )

            logger.info(f"[Twilio WhatsApp] Sent to {to_whatsapp}: SID={message.sid}, Status={message.status}")
            return {
                'success': True,
                'external_id': message.sid,
                'response_code': 200,
                'response_body': f'Twilio WhatsApp sent: {message.status}',
            }

        except Exception as exc:
            logger.warning(
                "[Twilio WhatsApp] Delivery failed (exception_type=%s)",
                type(exc).__name__,
            )
            return {
                'success': False,
                'response_code': 502,
                'response_body': 'Twilio WhatsApp delivery failed',
            }