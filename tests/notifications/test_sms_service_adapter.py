"""Regression tests for the authentication SMS adapter and owner secret storage."""

from types import SimpleNamespace


def test_sms_service_restores_twilio_send_message_contract(monkeypatch):
    from app.notifications import sms_service

    delivered = {}

    class FakeHandler:
        def __init__(self, auth_config=None):
            delivered["auth_config"] = auth_config

        def deliver(self, notification, recipient):
            delivered["body"] = notification.body
            delivered["recipient"] = recipient
            return {"success": True, "external_id": "SM-test-001", "response_code": 200}

    monkeypatch.setattr(
        "app.notifications.channel_handlers.twilio_sms.TwilioSmsHandler",
        FakeHandler,
    )
    auth_config = SimpleNamespace(twilio_enabled=True)

    result = sms_service.SMSService(
        provider="twilio",
        auth_config=auth_config,
    ).send_message(
        phone_number="+256700000001",
        message="Your AFCON360 code is 123456",
    )

    assert result["success"] is True
    assert result["provider"] == "twilio"
    assert result["message_sid"] == "SM-test-001"
    assert delivered["auth_config"] is auth_config
    assert delivered["recipient"]["phone"] == "+256700000001"
    assert delivered["body"] == "Your AFCON360 code is 123456"


def test_sms_service_refuses_unknown_provider_without_console_fallback():
    from app.notifications.sms_service import SMSService

    result = SMSService(provider="console").send_message("+256700000001", "test")

    assert result["success"] is False
    assert result["error"] == "unsupported_sms_provider"


def test_system_config_encrypts_and_decrypts_twilio_auth_token(monkeypatch):
    from app.models.system_config import SystemConfig
    from app.utils import security

    class FakeFernet:
        def encrypt(self, value):
            return b"encrypted:" + value

        def decrypt(self, value):
            if not value.startswith(b"encrypted:"):
                raise ValueError("bad ciphertext")
            return value[len(b"encrypted:"):]

    monkeypatch.setattr(security, "_get_fernet", lambda: FakeFernet())

    secret = "example-auth-token"
    stored = SystemConfig._encrypt_secret(secret)

    assert stored.startswith(SystemConfig._SECRET_PREFIX)
    assert secret not in stored
    assert SystemConfig._decrypt_secret(stored) == secret


def test_system_config_repr_redacts_twilio_token():
    from app.models.system_config import SystemConfig

    secret = "example-auth-token"
    setting = SystemConfig(key="TWILIO_AUTH_TOKEN", value=secret)

    assert secret not in repr(setting)
    assert "[REDACTED]" in repr(setting)


def test_twilio_sms_handler_uses_shared_settings_and_verified_sender(monkeypatch):
    from app.models.system_config import SystemConfig
    from app.notifications.channel_handlers.twilio_sms import TwilioSmsHandler

    values = {
        "TWILIO_ACCOUNT_SID": "AC" + "1" * 32,
        "TWILIO_AUTH_TOKEN": "sample-decoded-value",
        "TWILIO_FROM_NUMBER": "+15005550006",
        "TWILIO_MESSAGING_SERVICE_SID": "MG" + "2" * 32,
        "TWILIO_SMS_ENABLED": True,
    }
    monkeypatch.setattr(
        SystemConfig,
        "get",
        classmethod(lambda cls, key, default=None: values.get(key, default)),
    )

    sent = {}

    class FakeMessage:
        sid = "SM-handler-test"
        status = "queued"

    class FakeMessages:
        def create(self, **kwargs):
            sent.update(kwargs)
            return FakeMessage()

    class FakeClient:
        def __init__(self, account_sid, auth_token):
            sent["account_sid"] = account_sid
            sent["auth_token"] = auth_token
            self.messages = FakeMessages()

    monkeypatch.setattr("twilio.rest.Client", FakeClient)

    class Notification:
        body = "AFCON360 code 654321"

    result = TwilioSmsHandler().deliver(
        Notification(),
        {"phone": "+256700000001"},
    )

    assert result["success"] is True
    assert result["external_id"] == "SM-handler-test"
    assert sent["account_sid"] == values["TWILIO_ACCOUNT_SID"]
    assert sent["auth_token"] == values["TWILIO_AUTH_TOKEN"]
    assert sent["to"] == "+256700000001"
    assert sent["messaging_service_sid"] == values["TWILIO_MESSAGING_SERVICE_SID"]
    assert sent["body"] == "AFCON360 code 654321"
