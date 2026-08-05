import logging
from . import BaseChannelHandler

logger = logging.getLogger(__name__)


class PushHandler(BaseChannelHandler):
    channel_name = 'push'

    def validate_recipient(self, recipient: dict) -> bool:
        return bool(recipient.get('user_id'))

    def deliver(self, notification, recipient: dict) -> dict:
        logger.info(
            f"[PushHandler] FCM Push to user_id={recipient.get('user_id')}: "
            f"{notification.title}"
        )
        return {
            'success': True,
            'external_id': f"fcm_{notification.id}",
            'response_code': 200,
            'response_body': 'Firebase Cloud Messaging Push OK',
        }