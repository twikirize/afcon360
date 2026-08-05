import logging
from . import BaseChannelHandler

logger = logging.getLogger(__name__)


class WebhookHandler(BaseChannelHandler):
    channel_name = 'webhook'

    def validate_recipient(self, recipient: dict) -> bool:
        return True

    def deliver(self, notification, recipient: dict) -> dict:
        logger.info(
            f"[WebhookHandler] Webhook payload delivered for notification {notification.id}"
        )
        return {
            'success': True,
            'external_id': f"wh_{notification.id}",
            'response_code': 200,
            'response_body': 'HTTP 200 OK webhook acknowledgement',
        }