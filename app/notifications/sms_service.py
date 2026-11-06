"""
SMS Service using Twilio

Provides SMS sending functionality via Twilio API.
"""

import logging
from typing import Optional
from flask import current_app

logger = logging.getLogger(__name__)


def send_sms(to_number: str, message: str) -> bool:
    """
    Send an SMS message via Twilio.

    Args:
        to_number: Destination phone number in E.164 format (e.g., +15551234567)
        message: Message body (max 1600 characters)

    Returns:
        True if sent successfully, False otherwise
    """
    try:
        # Get Twilio credentials from SystemConfig
        from app.models.system_config import SystemConfig

        account_sid = SystemConfig.get('TWILIO_ACCOUNT_SID')
        auth_token = SystemConfig.get('TWILIO_AUTH_TOKEN')
        from_number = SystemConfig.get('TWILIO_FROM_NUMBER')
        messaging_service_sid = SystemConfig.get('TWILIO_MESSAGING_SERVICE_SID')

        if not account_sid or not auth_token:
            logger.warning("[SMS] Twilio credentials not configured")
            return False

        if not from_number and not messaging_service_sid:
            logger.warning("[SMS] No from_number or messaging_service_sid configured")
            return False

        from twilio.rest import Client

        client = Client(account_sid, auth_token)

        # Build message parameters
        params = {
            'to': to_number,
            'body': message,
        }

        # Use messaging service SID if configured, otherwise from_number
        if messaging_service_sid:
            params['messaging_service_sid'] = messaging_service_sid
        elif from_number:
            params['from_'] = from_number
        else:
            logger.error("[SMS] No from_number or messaging_service_sid configured")
            return False

        message = client.messages.create(**params)

        logger.info(f"[SMS] Sent to {to_number}: SID={message.sid}, Status={message.status}")
        return True

    except Exception as e:
        logger.error(f"[SMS] Failed to send to {to_number}: {e}")
        return False


def send_whatsapp(to_number: str, message: str) -> bool:
    """
    Send a WhatsApp message via Twilio.

    Args:
        to_number: Destination phone number in E.164 format (e.g., +15551234567)
        message: Message body (max 1600 characters)

    Returns:
        True if sent successfully, False otherwise
    """
    try:
        # Get Twilio credentials from SystemConfig
        from app.models.system_config import SystemConfig

        account_sid = SystemConfig.get('TWILIO_ACCOUNT_SID')
        auth_token = SystemConfig.get('TWILIO_AUTH_TOKEN')
        whatsapp_from = SystemConfig.get('TWILIO_WHATSAPP_FROM')

        if not account_sid or not auth_token:
            logger.warning("[WhatsApp] Twilio credentials not configured")
            return False

        if not whatsapp_from:
            logger.warning("[WhatsApp] No WhatsApp from number configured")
            return False

        from twilio.rest import Client

        client = Client(account_sid, auth_token)

        # Ensure WhatsApp format: whatsapp:+1234567890
        if not to_number.startswith('whatsapp:'):
            to_whatsapp = f'whatsapp:{to_number}'
        else:
            to_whatsapp = to_number

        message = client.messages.create(
            from_=whatsapp_from,
            to=to_whatsapp,
            body=message,
        )

        logger.info(f"[WhatsApp] Sent to {to_whatsapp}: SID={message.sid}, Status={message.status}")
        return True

    except Exception as e:
        logger.error(f"[WhatsApp] Failed to send to {to_number}: {e}")
        return False