import logging
from . import BaseChannelHandler

logger = logging.getLogger(__name__)


class InAppHandler(BaseChannelHandler):
    channel_name = 'in_app'

    def validate_recipient(self, recipient: dict) -> bool:
        return bool(recipient.get('user_id'))

    def deliver(self, notification, recipient: dict) -> dict:
        logger.info(
            f"[InAppHandler] In-app message stored for user_id={recipient.get('user_id')}: "
            f"{notification.subject}"
        )
        return {
            'success': True,
            'external_id': f"inapp_{notification.id}",
            'response_code': 200,
            'response_body': 'In-App notification inbox record stored.',
        }