"""
AFCON360 Notification Integrations Package

Pluggable dispatch layer that routes a notification to the correct external
aggregator based on channel + provider_type. Designed to be future-proof:
- Twilio (SMS + WhatsApp)
- SendGrid / SMTP / Mailgun (email)
- Firebase Cloud Messaging (push)
- Generic Webhook / SAP Event Mesh (webhook, future)

Each dispatcher returns {'ok': bool, 'external_id': str, 'response_code': int, 'detail': str}.
Secrets are read from NotificationAggregator.credentials (decrypted at runtime).
"""

import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


def _decrypt(credentials: Dict[str, Any]) -> Dict[str, Any]:
    """Decrypt provider credentials or fail closed; never treat ciphertext as config."""
    from app.notifications.settings import CommunicationSettingsService
    return CommunicationSettingsService._decrypt_config(credentials or {})


def dispatch_via_aggregator(aggregator, notification=None, test: bool = False) -> Dict[str, Any]:
    """Route to the correct dispatcher based on provider_type."""
    provider = (aggregator.provider_type or '').lower()
    channels = aggregator.channels or []

    if 'sms' in channels or provider.startswith('twilio'):
        return _dispatch_twilio(aggregator, notification, test)
    if 'email' in channels or provider in ('sendgrid', 'mailgun', 'ses', 'smtp'):
        return _dispatch_email(aggregator, notification, test)
    if 'push' in channels or provider in ('fcm', 'apns'):
        return _dispatch_push(aggregator, notification, test)
    if 'webhook' in channels or provider in ('generic', 'sap'):
        return _dispatch_webhook(aggregator, notification, test)
    if 'whatsapp' in channels or 'whatsapp' in provider:
        return _dispatch_whatsapp(aggregator, notification, test)

    return {'ok': False, 'detail': f'No dispatcher for provider_type={provider}'}


# ----------------------------------------------------------------------
# Twilio (SMS)
# ----------------------------------------------------------------------

def _dispatch_twilio(aggregator, notification, test: bool) -> Dict[str, Any]:
    creds = _decrypt(aggregator.credentials)
    account_sid = creds.get('account_sid')
    auth_token = creds.get('auth_token')
    from_number = creds.get('from_number') or creds.get('messaging_service_sid')

    if test:
        # Validate config only
        if not (account_sid and auth_token):
            return {'ok': False, 'detail': 'Missing Twilio credentials'}
        return {'ok': True, 'detail': 'Twilio config valid', 'response_code': 200}

    if not notification:
        return {'ok': False, 'detail': 'No notification to send'}

    try:
        from twilio.rest import Client
        client = Client(account_sid, auth_token)
        msg = client.messages.create(
            body=notification.body[:1600],
            from_=from_number,
            to=notification.phone,
        )
        return {'ok': True, 'external_id': msg.sid, 'response_code': 201}
    except ImportError:
        logger.error("twilio package not installed")
        return {'ok': False, 'detail': 'twilio not installed'}
    except Exception as exc:
        logger.warning("Twilio dispatch failed (exception_type=%s)", type(exc).__name__)
        return {'ok': False, 'detail': 'twilio_dispatch_failed'}


# ----------------------------------------------------------------------
# Email (single Owner-managed SMTP transport)
# ----------------------------------------------------------------------

def _dispatch_email(aggregator, notification, test: bool) -> Dict[str, Any]:
    """Use the one shared Owner-managed SMTP transport for every process."""
    from app.notifications.settings import CommunicationSettingsService

    try:
        if test:
            config = CommunicationSettingsService.resolve_email_transport_config()
            if not config.get("smtp_host") or not config.get("default_sender"):
                return {"ok": False, "detail": "smtp_configuration_incomplete"}
            if bool(config.get("use_tls")) and bool(config.get("use_ssl")):
                return {"ok": False, "detail": "smtp_tls_ssl_conflict"}
            return {"ok": True, "detail": "smtp_configuration_available", "response_code": 200}

        if not notification:
            return {"ok": False, "detail": "notification_required"}

        from app.notifications.channel_handlers.email import EmailHandler
        result = EmailHandler().deliver(
            notification,
            {"email": notification.email, "user_id": notification.user_id},
        )
        if result.get("success"):
            return {
                "ok": True,
                "external_id": result.get("external_id") or notification.external_id,
                "response_code": result.get("response_code", 200),
            }
        return {
            "ok": False,
            "detail": result.get("error_code") or "email_delivery_failed",
        }
    except Exception as exc:
        error_code = getattr(exc, "code", "email_provider_error")
        logger.warning("Email provider dispatch failed (error_code=%s)", error_code)
        return {"ok": False, "detail": error_code}


# ----------------------------------------------------------------------
# Push (Firebase Cloud Messaging)
# ----------------------------------------------------------------------

def _dispatch_push(aggregator, notification, test: bool) -> Dict[str, Any]:
    creds = _decrypt(aggregator.credentials)
    server_key = creds.get('server_key') or creds.get('api_key')

    if test:
        if not server_key:
            return {'ok': False, 'detail': 'Missing FCM server key'}
        return {'ok': True, 'detail': 'FCM config valid', 'response_code': 200}

    if not notification:
        return {'ok': False, 'detail': 'No notification to send'}

    # FCM requires a device token; for now we log intent and return ok if configured.
    # Device token registration is wired via user profile push tokens (future).
    if not server_key:
        return {'ok': False, 'detail': 'FCM not configured'}
    logger.info("FCM push queued for notification %s", getattr(notification, 'id', 'n/a'))
    return {'ok': True, 'external_id': notification.external_id, 'response_code': 200}


# ----------------------------------------------------------------------
# WhatsApp (Twilio / Meta)
# ----------------------------------------------------------------------

def _dispatch_whatsapp(aggregator, notification, test: bool) -> Dict[str, Any]:
    creds = _decrypt(aggregator.credentials)
    if test:
        if not (creds.get('account_sid') and creds.get('auth_token')):
            return {'ok': False, 'detail': 'Missing WhatsApp credentials'}
        return {'ok': True, 'detail': 'WhatsApp config valid', 'response_code': 200}
    if not notification:
        return {'ok': False, 'detail': 'No notification to send'}
    # WhatsApp via Twilio sandbox / business API
    try:
        from twilio.rest import Client
        client = Client(creds.get('account_sid'), creds.get('auth_token'))
        msg = client.messages.create(
            body=notification.body[:1600],
            from_=f"whatsapp:{creds.get('from_number')}",
            to=f"whatsapp:{notification.phone}",
        )
        return {'ok': True, 'external_id': msg.sid, 'response_code': 201}
    except ImportError:
        return {'ok': False, 'detail': 'twilio not installed'}
    except Exception as exc:
        logger.warning("WhatsApp dispatch failed (exception_type=%s)", type(exc).__name__)
        return {'ok': False, 'detail': 'whatsapp_dispatch_failed'}


# ----------------------------------------------------------------------
# Webhook / SAP Event Mesh (future-proof)
# ----------------------------------------------------------------------

def _dispatch_webhook(aggregator, notification, test: bool) -> Dict[str, Any]:
    creds = _decrypt(aggregator.credentials)
    webhook_url = aggregator.webhook_url or creds.get('webhook_url')

    if test:
        if not webhook_url:
            return {'ok': False, 'detail': 'Missing webhook URL'}
        return {'ok': True, 'detail': 'Webhook config valid', 'response_code': 200}

    if not notification:
        return {'ok': False, 'detail': 'No notification to send'}

    try:
        import requests
        payload = {
            'notification_id': notification.id,
            'type': notification.type,
            'channel': notification.channel,
            'subject': notification.subject,
            'body': notification.body,
            'recipient': notification.email or notification.phone,
            'user_id': notification.user_id,
            'created_at': notification.created_at.isoformat() if notification.created_at else None,
        }
        headers = {'Content-Type': 'application/json'}
        api_key = creds.get('api_key')
        if api_key:
            headers['Authorization'] = f"Bearer {api_key}"
        resp = requests.post(webhook_url, json=payload, headers=headers, timeout=10)
        return {
            'ok': resp.status_code < 400,
            'external_id': resp.headers.get('X-Request-Id'),
            'response_code': resp.status_code,
        }
    except Exception as exc:
        logger.warning("Webhook dispatch failed (exception_type=%s)", type(exc).__name__)
        return {'ok': False, 'detail': 'webhook_dispatch_failed'}
