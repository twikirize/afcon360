"""Regression tests for in-place delivery of scheduled notification rows."""

import uuid
from datetime import datetime, timedelta, timezone

from app.extensions import db
from app.notifications.models import (
    Notification,
    NotificationChannel,
    NotificationModule,
    NotificationStatus,
    NotificationType,
)
from app.notifications.services import NotificationService
from app.identity.models.user import User


class _SuccessfulInAppHandler:
    def validate_recipient(self, recipient):
        return bool(recipient.get("user_id"))

    def deliver(self, notification, recipient):
        return {"external_id": f"test-{notification.id}", "response_code": 200}


def test_scheduled_notification_delivery_reuses_original_row(
    app, db_session, monkeypatch
):
    user = User(
        username=f"celery-notif-{uuid.uuid4().hex[:8]}",
        email=f"celery-notif-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="test-hash",
        is_verified=True,
        is_active=True,
    )
    db_session.add(user)
    db_session.flush()

    scheduled = Notification(
        user_id=user.id,
        email=user.email,
        type=NotificationType.BOOKING_CONFIRMED,
        module=NotificationModule.ACCOMMODATION,
        channel=NotificationChannel.IN_APP,
        subject="Your booking is confirmed",
        body="This is your scheduled reminder.",
        status=NotificationStatus.PENDING,
        scheduled_for=datetime.now(timezone.utc) - timedelta(minutes=1),
        attempts=1,
    )
    db_session.add(scheduled)
    db_session.commit()

    original_id = scheduled.id
    original_count = Notification.query.filter_by(user_id=user.id).count()

    monkeypatch.setattr(
        NotificationService,
        "_resolve_delivery_zone",
        lambda *args, **kwargs: [NotificationChannel.IN_APP.value],
    )
    monkeypatch.setitem(
        NotificationService.HANDLERS,
        NotificationChannel.IN_APP,
        _SuccessfulInAppHandler(),
    )

    delivered = NotificationService.send(
        user_id=user.id,
        notification_type=scheduled.type,
        title=scheduled.subject,
        message=scheduled.body,
        data=scheduled.context or {},
        channels=[NotificationChannel.IN_APP.value],
        link=scheduled.link,
        priority=scheduled.priority,
        module=scheduled.module,
        existing_notification=scheduled,
    )

    assert delivered is not None
    assert delivered.id == original_id
    assert delivered.status == NotificationStatus.DELIVERED
    assert delivered.scheduled_for is None
    assert Notification.query.filter_by(user_id=user.id).count() == original_count
