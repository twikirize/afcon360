from types import SimpleNamespace
import uuid

from app.notifications.models import Notification
from app.notifications.services import NotificationService
from app.identity.models.user import User
from app.extensions import db


def _make_user(app):
    with app.app_context():
        user = User(
            email=f'test_user_{uuid.uuid4().hex[:6]}@example.com',
            username=f'testuser_{uuid.uuid4().hex[:6]}',
            password_hash='hashed',
            is_active=True,
            is_verified=True,
        )
        db.session.add(user)
        db.session.commit()
        return user.id


def test_notification_user_controls(app, db_session):
    user_id = _make_user(app)
    notification = Notification(user_id=user_id, type='system_alert', module='system', body='Test')
    db_session.add(notification)
    db_session.commit()

    assert NotificationService.set_read_state(notification.id, user_id, True)
    db_session.refresh(notification)
    assert notification.is_read is True

    assert NotificationService.set_read_state(notification.id, user_id, False)
    db_session.refresh(notification)
    assert notification.is_read is False

    assert NotificationService.set_important(notification.id, user_id, True)
    db_session.refresh(notification)
    assert notification.is_important is True

    assert not NotificationService.set_important(notification.id, 999999, False)