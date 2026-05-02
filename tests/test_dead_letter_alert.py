import pytest
from types import SimpleNamespace


def test_alert_owner_dead_letter(monkeypatch):
    """Ensure the dead-letter alert helper attempts SMS, email and Redis increment."""
    # Import the helper
    from app.tasks.webhook_processor import _alert_owner_dead_letter

    # Prepare a fake owner user object
    owner = SimpleNamespace(
        id=123,
        phone=b"+256700000000",
        phone_verified=True,
        email="owner@example.com",
        email_verified=True,
        # method style on SimpleNamespace
        is_super_admin=lambda: True
    )

    # Patch User.query.all to return our fake owner
    import app.identity.models.user as user_mod

    class FakeQuery:
        def all(self):
            return [owner]

    monkeypatch.setattr(user_mod.User, "query", FakeQuery())

    # Patch SMS sender
    sms_called = {"ok": False}

    def fake_send_sms(phone, message):
        sms_called["ok"] = True
        assert "AFCON360 ALERT" in message

    monkeypatch.setattr("app.services.sms_service.send_sms", fake_send_sms, raising=False)

    # Patch email sender
    email_called = {"ok": False}

    class FakeNotificationService:
        @staticmethod
        def send_email(to, subject, body):
            email_called["ok"] = True
            assert "AFCON360 ALERT" in subject or "AFCON360 ALERT" in body

    monkeypatch.setattr(
        "app.transport.services.notification_service.NotificationService",
        FakeNotificationService,
        raising=False,
    )

    # Patch Redis incr
    import app.extensions as ext

    incr_called = {"ok": False}

    def fake_incr(key):
        assert key == "dead_letter_count"
        incr_called["ok"] = True

    monkeypatch.setattr(ext.redis_client, "incr", fake_incr)

    # Create fake event
    ev = SimpleNamespace(id=99, provider="flutterwave", event_type="charge.completed")

    # Call helper
    _alert_owner_dead_letter(ev)

    assert sms_called["ok"] or email_called["ok"]
    assert incr_called["ok"]

