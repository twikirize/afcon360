import pytest
from types import SimpleNamespace


def test_alert_owner_dead_letter(app, monkeypatch):
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

    # Stub the exact joined owner lookup used by the production helper.
    # Patching User.query alone is insufficient because the helper first
    # calls db.session.query(User).join(...).filter(...).first().
    import app.extensions as ext

    class FakeOwnerQuery:
        def join(self, *args, **kwargs):
            return self

        def filter(self, *args, **kwargs):
            return self

        def order_by(self, *args, **kwargs):
            return self

        def first(self):
            return owner

    def install_owner_query_stub():
        session = ext.db.session()
        monkeypatch.setattr(
            session,
            "query",
            lambda model: FakeOwnerQuery(),
        )

    # Patch SMS sender
    sms_called = {"ok": False}

    def fake_send_sms(phone, message):
        sms_called["ok"] = True
        assert "AFCON360 ALERT" in message

    monkeypatch.setattr("app.notifications.sms_service.send_sms", fake_send_sms, raising=False)

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

    # Patch Redis increment without resolving the lazy client.
    incr_called = {"ok": False}

    def fake_incr(key):
        assert key == "dead_letter_count"
        incr_called["ok"] = True

    # Replace the lazy proxy itself; reading ext.redis_client.incr first
    # would resolve the Redis connection before the test can stub it.
    monkeypatch.setattr(
        ext,
        "redis_client",
        SimpleNamespace(incr=fake_incr),
    )

    # Create fake event
    ev = SimpleNamespace(id=99, provider="flutterwave", event_type="charge.completed")

    # Call helper
    with app.app_context():
        install_owner_query_stub()
        _alert_owner_dead_letter(ev)

    assert sms_called["ok"] or email_called["ok"]
    assert incr_called["ok"]

