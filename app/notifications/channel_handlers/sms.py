import logging
from . import BaseChannelHandler

logger = logging.getLogger(__name__)


class SmsHandler(BaseChannelHandler):
    channel_name = 'sms'

    def validate_recipient(self, recipient: dict) -> bool:
        phone = recipient.get('phone')
        return bool(phone and len(phone) >= 8)

    def deliver(self, notification, recipient: dict) -> dict:
        logger.info(
            f"[SmsHandler] Sending SMS to {recipient.get('phone') or recipient.get('user_id')}: "
            f"{notification.body[:30]}..."
        )
        return {
            'success': True,
            'external_id': f"tw_sid_{notification.id}",
            'response_code': 200,
            'response_body': 'Twilio SMS OK',
        }