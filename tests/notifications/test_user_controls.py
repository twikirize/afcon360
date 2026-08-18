from types import SimpleNamespace

from app.notifications.models import Notification
from app.notifications.services import NotificationService


def test_notification_user_controls(db_session):
    notification = Notification(user_id=1, type='system_alert', module='system', body='Test')
    db_session.add(notification)
    db_session.commit()

    assert NotificationService.set_read_state(notification.id, 1, True)
    db_session.refresh(notification)
    assert notification.is_read is True

    assert NotificationService.set_read_state(notification.id, 1, False)
    db_session.refresh(notification)
    assert notification.is_read is False

    assert NotificationService.set_important(notification.id, 1, True)
    db_session.refresh(notification)
    assert notification.is_important is True

    assert not NotificationService.set_important(notification.id, 999999, False)