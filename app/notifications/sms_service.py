"""
Provider-neutral SMS adapter used by authentication and phone-verification flows.

The notification channel handlers remain the canonical Twilio delivery
implementation. This adapter restores the older SMSService interface without
creating a second OTP store or a second Twilio configuration source.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class _SMSNotification:
    subject = "AFCON360 verification code"

    def __init__(self, body: str) -> None:
        self.body = body


class SMSService:
    """Compatibility adapter for owner-configured SMS providers."""

    def __init__(self, provider: Optional[str] = None, auth_config=None) -> None:
        self.provider = (provider or "twilio").strip().lower()
        self.auth_config = auth_config

    def send_message(self, phone_number: str, message: str) -> Dict[str, Any]:
        """Deliver a message but deliberately leave OTP storage to OTPService."""
        if not phone_number or not isinstance(phone_number, str):
            return {"success": False, "provider": self.provider, "error": "recipient_required"}
        if not message or not isinstance(message, str):
            return {"success": False, "provider": self.provider, "error": "message_required"}
        if len(message) > 1600:
            message = message[:1597] + "..."

        try:
            if self.provider == "twilio":
                return self._send_twilio(phone_number, message)
            if self.provider in {"africa_talking", "africas_talking"}:
                return self._send_africa_talking(phone_number, message)
            return {
                "success": False,
                "provider": self.provider,
                "error": "unsupported_sms_provider",
            }
        except Exception as exc:
            # Do not put provider exception text into API responses or logs:
            # SDK exceptions may include request details.
            logger.warning(
                "SMS delivery failed (provider=%s, exception_type=%s)",
                self.provider,
                type(exc).__name__,
            )
            return {
                "success": False,
                "provider": self.provider,
                "error": "provider_delivery_failed",
            }

    def _send_twilio(self, phone_number: str, message: str) -> Dict[str, Any]:
        from app.notifications.channel_handlers.twilio_sms import TwilioSmsHandler

        result = TwilioSmsHandler(auth_config=self.auth_config).deliver(
            _SMSNotification(message),
            {"phone": phone_number},
        )
        success = bool(result.get("success"))
        return {
            "success": success,
            "provider": "twilio",
            "message_sid": result.get("external_id"),
            "status": "accepted" if success else "failed",
            "error": None if success else "provider_delivery_failed",
        }

    def _send_africa_talking(self, phone_number: str, message: str) -> Dict[str, Any]:
        config = self.auth_config
        username = getattr(config, "africa_talking_username", None) if config else None
        api_key = getattr(config, "africa_talking_api_key", None) if config else None
        sender_id = os.getenv("AFRICAS_TALKING_SENDER_ID")

        if not username or not api_key:
            return {
                "success": False,
                "provider": "africa_talking",
                "error": "provider_credentials_missing",
            }

        import africastalking

        africastalking.initialize(username, api_key)
        response = africastalking.SMS.send(
            message,
            [phone_number],
            sender_id=sender_id or None,
        )
        recipients = (
            response.get("SMSMessageData", {}).get("Recipients", [])
            if isinstance(response, dict)
            else []
        )
        recipient = recipients[0] if recipients else {}
        status = str(recipient.get("status") or "")
        success = status.lower() in {"success", "success."}
        return {
            "success": success,
            "provider": "africa_talking",
            "status": status or "unknown",
            "message_id": recipient.get("messageId"),
            "error": None if success else "provider_delivery_failed",
        }


def send_sms(to_number: str, message: str) -> bool:
    """Backward-compatible bool API; OTPService owns code storage."""
    return bool(SMSService(provider="twilio").send_message(to_number, message).get("success"))


def send_whatsapp(to_number: str, message: str) -> bool:
    """Backward-compatible Twilio WhatsApp API used by older callers."""
    try:
        from app.notifications.channel_handlers.twilio_sms import TwilioWhatsAppHandler

        result = TwilioWhatsAppHandler().deliver(
            _SMSNotification(message),
            {"phone": to_number},
        )
        return bool(result.get("success"))
    except Exception as exc:
        logger.warning(
            "WhatsApp delivery failed (exception_type=%s)",
            type(exc).__name__,
        )
        return False
