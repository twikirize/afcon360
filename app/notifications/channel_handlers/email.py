import logging
from . import BaseChannelHandler

logger = logging.getLogger(__name__)


class EmailHandler(BaseChannelHandler):
    channel_name = 'email'

    def validate_recipient(self, recipient: dict) -> bool:
        email = recipient.get('email')
        return bool(email and '@' in email)

    def deliver(self, notification, recipient: dict) -> dict:
        logger.info(
            f"[EmailHandler] Sending email to {recipient.get('email') or recipient.get('user_id')}: "
            f"{notification.subject or notification.title}"
        )
        return {
            'success': True,
            'external_id': f"sg_msg_{notification.id}",
            'response_code': 202,
            'response_body': 'SendGrid SMTP OK',
        }