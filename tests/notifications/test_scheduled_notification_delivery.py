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
        return {
            "success": True,
            "external_id": f"test-{notification.id}",
            "response_code": 200,
        }


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


def test_scheduled_reminder_batches_advance_without_starving_later_rows(
    app, db_session, monkeypatch
):
    """A queued page must not be selected again before later pending rows."""
    from app.notifications.tasks import (
        schedule_reminders_task,
        send_notification_task,
    )

    now = datetime.now(timezone.utc)
    rows = [
        Notification(
            type=NotificationType.BOOKING_CONFIRMED,
            module=NotificationModule.ACCOMMODATION,
            channel=NotificationChannel.IN_APP,
            subject=f"Scheduled reminder {index}",
            body="Reminder test",
            status=NotificationStatus.PENDING,
            scheduled_for=now - timedelta(minutes=1),
        )
        for index in range(30)
    ]
    db_session.add_all(rows)
    db_session.commit()

    dispatched_ids = []
    continuation_calls = []

    def fake_send_apply_async(*, args, expires):
        assert expires == 55
        dispatched_ids.append(args[0])
        return None

    def fake_scheduler_apply_async(*, kwargs, countdown):
        continuation_calls.append((kwargs, countdown))
        return None

    monkeypatch.setattr(
        "app.notifications.tasks._get_task_flask_app",
        lambda: app,
    )
    monkeypatch.setattr(
        send_notification_task,
        "apply_async",
        fake_send_apply_async,
    )
    monkeypatch.setattr(
        schedule_reminders_task,
        "apply_async",
        fake_scheduler_apply_async,
    )

    first = schedule_reminders_task.run(batch_size=25)
    assert first["dispatched"] == 25
    assert first["continuation_queued"] is True
    assert len(set(dispatched_ids)) == 25
    assert len(continuation_calls) == 1

    # The continuation should select the five untouched rows, not repeat the
    # first 25 whose broker messages have not yet reached the worker.
    second = schedule_reminders_task.run(batch_size=25)
    assert second["dispatched"] == 5
    assert second["continuation_queued"] is False
    assert len(dispatched_ids) == 30
    assert len(set(dispatched_ids)) == 30

    third = schedule_reminders_task.run(batch_size=25)
    assert third["dispatched"] == 0
    assert len(dispatched_ids) == 30


def test_oci_email_handler_defers_credentials_until_configured_delivery(monkeypatch):
    from app.notifications.channel_handlers.oci_email import OCIEmailHandler

    monkeypatch.setattr(
        OCIEmailHandler,
        "_get_config",
        lambda self, key, default=None, value_type="str": default,
    )
    handler = OCIEmailHandler()
    initialization_calls = []

    def initialize():
        initialization_calls.append("attempted")

    monkeypatch.setattr(handler, "_init_client", initialize)
    assert handler.email_client is None
    assert initialization_calls == []

    handler.compartment_id = "ocid1.compartment.test"
    assert handler.email_client is None
    assert initialization_calls == ["attempted"]



def test_custom_oci_channel_fallback_uses_string_handler_keys(
    app, db_session, monkeypatch
):
    """Custom delivery channels must not be converted to NotificationChannel enums."""
    from app.notifications.models import NotificationLog
    from app.notifications.preferences import PreferenceService

    user = User(
        username=f"oci-fallback-{uuid.uuid4().hex[:8]}",
        email=f"oci-fallback-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="test-hash",
        is_verified=True,
        is_active=True,
    )
    db_session.add(user)
    db_session.flush()

    class _FailingOCIHandler:
        def validate_recipient(self, recipient):
            return bool(recipient.get("email"))

        def deliver(self, notification, recipient):
            return {
                "success": False,
                "error_code": "oci_unavailable",
                "response_code": 503,
                "response_body": "private-token=must-not-be-persisted",
            }

    class _SuccessfulSMTPHandler:
        def validate_recipient(self, recipient):
            return bool(recipient.get("email"))

        def deliver(self, notification, recipient):
            return {
                "success": True,
                "external_id": "smtp-fallback-accepted",
                "response_code": 250,
                "response_body": "accepted",
            }

    monkeypatch.setattr(
        NotificationService,
        "_resolve_delivery_zone",
        lambda *args, **kwargs: ["oci_email"],
    )
    monkeypatch.setattr(
        PreferenceService,
        "is_allowed",
        lambda *args, **kwargs: True,
    )
    monkeypatch.setitem(
        NotificationService.HANDLERS, "oci_email", _FailingOCIHandler()
    )
    monkeypatch.setitem(
        NotificationService.HANDLERS, "email", _SuccessfulSMTPHandler()
    )

    delivered = NotificationService.send(
        user_id=user.id,
        notification_type=NotificationType.BOOKING_CONFIRMED,
        title="Notification fallback test",
        message="Test the OCI to SMTP fallback.",
        email=user.email,
        channels=["oci_email"],
        module=NotificationModule.ACCOMMODATION,
        force_external=True,
    )

    assert delivered is not None
    assert delivered.status == NotificationStatus.DELIVERED
    logs = NotificationLog.query.filter_by(notification_id=delivered.id).all()
    assert any(log.channel == "email" and log.status == "success" for log in logs)
    assert all(
        "private-token" not in (log.response_body or "")
        for log in logs
    )
