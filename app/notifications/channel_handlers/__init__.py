from abc import ABC, abstractmethod


class BaseChannelHandler(ABC):
    channel_name: str

    @abstractmethod
    def validate_recipient(self, recipient: dict) -> bool:
        pass

    @abstractmethod
    def deliver(self, notification, recipient: dict) -> dict:
        pass


from .email import EmailHandler
from .sms import SmsHandler
from .push import PushHandler
from .in_app import InAppHandler
from .webhook import WebhookHandler

__all__ = [
    'BaseChannelHandler',
    'EmailHandler',
    'SmsHandler',
    'PushHandler',
    'InAppHandler',
    'WebhookHandler',
]
