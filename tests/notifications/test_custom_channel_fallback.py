"""Regression coverage for custom notification-channel fallback lookup."""

from app.notifications.models import (
    Notification,
    NotificationChannel,
    NotificationModule,
    NotificationStatus,
    NotificationType,
)
from app.notifications.services import NotificationService


class _FailingCustomEmailHandler:
    def __init__(self, calls):
        self.calls = calls

    def validate_recipient(self, recipient):
        return bool(recipient.get("email"))

    def deliver(self, notification, recipient):
        self.calls.append(("oci_email", recipient["email"]))
        return {"success": False, "error_code": "oci_temporary_failure"}


class _WorkingSmtpHandler:
    def __init__(self, calls):
        self.calls = calls

    def validate_recipient(self, recipient):
        return bool(recipient.get("email"))

    def deliver(self, notification, recipient):
        self.calls.append(("email", recipient["email"]))
        return {"success": True, "external_id": "smtp-fallback-message", "response_code": 250}


def test_custom_channel_uses_string_key_and_falls_back_to_email(app, db_session, monkeypatch):
    calls = []
    email = "custom-fallback@example.com"

    monkeypatch.setattr(
        NotificationService,
        "_resolve_delivery_zone",
        lambda *args, **kwargs: ["oci_email"],
    )
    monkeypatch.setitem(
        NotificationService.HANDLERS,
        "oci_email",
        _FailingCustomEmailHandler(calls),
    )
    monkeypatch.setitem(
        NotificationService.HANDLERS,
        "email",
        _WorkingSmtpHandler(calls),
    )

    delivered = NotificationService.send(
        user_id=None,
        notification_type=NotificationType.BOOKING_CONFIRMED,
        title="OCI to SMTP fallback test",
        message="Prove custom notification channels use string registry keys.",
        channels=["oci_email"],
        email=email,
        module=NotificationModule.ACCOMMODATION,
    )

    assert delivered is not None
    assert delivered.status == NotificationStatus.DELIVERED
    assert calls == [("oci_email", email), ("email", email)]
    assert Notification.query.filter_by(id=delivered.id).one() is not None
