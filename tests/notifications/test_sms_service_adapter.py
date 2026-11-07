"""Regression tests for the authentication SMS adapter and owner secret storage."""

from types import SimpleNamespace


def test_sms_service_restores_twilio_send_message_contract(app, monkeypatch):
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

    app.config["SMS_DELIVERY_ENABLED"] = True
    with app.app_context():
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


def test_sms_service_refuses_unknown_provider_without_console_fallback(app):
    from app.notifications.sms_service import SMSService

    # This test checks provider validation, so explicitly pass the global
    # delivery gate before exercising the unsupported-provider branch.
    app.config["SMS_DELIVERY_ENABLED"] = True
    with app.app_context():
        result = SMSService(provider="console").send_message("+256700000001", "test")

    assert result["success"] is False
    assert result["error"] == "unsupported_sms_provider"


def test_system_config_encrypts_and_decrypts_twilio_auth_token(monkeypatch):
    from app.models.system_config import SystemConfig
    from app.utils import security

    import base64

    class FakeFernet:
        def encrypt(self, value):
            return base64.urlsafe_b64encode(b"test-envelope:" + value)

        def decrypt(self, value):
            decoded = base64.urlsafe_b64decode(value)
            prefix = b"test-envelope:"
            if not decoded.startswith(prefix):
                raise ValueError("bad ciphertext")
            return decoded[len(prefix):]

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


def test_twilio_sms_handler_uses_shared_settings_and_verified_sender(app, monkeypatch):
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

    app.config["SMS_DELIVERY_ENABLED"] = True
    with app.app_context():
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


def test_multi_channel_storage_happens_before_provider_delivery(app, monkeypatch):
    from app.auth.otp_service import OTPService

    order = []

    def store_otp(identifier, otp, purpose, ttl):
        order.append(("store", identifier, purpose))
        return True

    class FakeHandler:
        def deliver(self, notification, recipient):
            order.append(("deliver", recipient["phone"]))
            return {"success": True, "external_id": "SM-order-test"}

    monkeypatch.setattr(OTPService, "store_otp", staticmethod(store_otp))
    monkeypatch.setattr(OTPService, "_dev_fallback_allowed", staticmethod(lambda: False))
    monkeypatch.setattr(OTPService, "invalidate_otp", staticmethod(lambda *_: True))
    monkeypatch.setattr(
        "app.notifications.channel_handlers.twilio_sms.TwilioSmsHandler",
        lambda: FakeHandler(),
    )

    app.config["SMS_DELIVERY_ENABLED"] = True
    with app.app_context():
        result = OTPService.send_otp_multi_channel(
            identifier="account-123",
            otp="582741",
            purpose="login",
            channels=["twilio_sms"],
            phone="+256700000001",
            max_retries=1,
        )

    assert result["success"] is True
    assert order[0] == ("store", "account-123", "login")
    assert order[1][0] == "deliver"


def test_multi_channel_stops_when_shared_otp_storage_fails(app, monkeypatch):
    from app.auth.otp_service import OTPService

    delivered = []
    monkeypatch.setattr(OTPService, "store_otp", staticmethod(lambda **_: False))
    monkeypatch.setattr(OTPService, "_dev_fallback_allowed", staticmethod(lambda: False))
    monkeypatch.setattr(
        "app.notifications.channel_handlers.twilio_sms.TwilioSmsHandler",
        lambda: delivered.append(True),
    )

    with app.app_context():
        result = OTPService.send_otp_multi_channel(
            identifier="account-456",
            otp="194826",
            purpose="phone",
            channels=["twilio_sms"],
            phone="+256700000002",
            max_retries=1,
        )

    assert result["success"] is False
    assert result["code"] == "storage_failed"
    assert delivered == []


def test_sms_otp_storage_uses_same_identity_as_verification(app, monkeypatch):
    from app.auth.otp_service import OTPService
    from app.notifications import sms_service

    stored = {}
    monkeypatch.setattr(
        OTPService,
        "store_otp",
        staticmethod(lambda identifier, otp, purpose, ttl: stored.update(
            identifier=identifier, purpose=purpose, ttl=ttl
        ) or True),
    )
    monkeypatch.setattr(sms_service, "send_sms", lambda phone, message: True)

    app.config["SMS_DELIVERY_ENABLED"] = True
    with app.app_context():
        sent, returned_code = OTPService.send_sms_otp(
            phone="+256700000003",
            otp="482061",
            internal_user_id=987,
        )

    assert sent is True
    assert returned_code == "482061"
    assert stored == {
        "identifier": "987",
        "purpose": "sms_verification",
        "ttl": 300,
    }



def test_sms_service_blocks_delivery_when_global_switch_is_off(app, monkeypatch):
    from app.notifications.sms_service import SMSService

    attempted = []
    monkeypatch.setattr(
        "app.notifications.channel_handlers.twilio_sms.TwilioSmsHandler",
        lambda **kwargs: attempted.append(True),
    )
    app.config["SMS_DELIVERY_ENABLED"] = False

    with app.app_context():
        result = SMSService(provider="twilio").send_message(
            "+256700000001",
            "This message must not be sent",
        )

    assert result["success"] is False
    assert result["error"] == "sms_delivery_disabled"
    assert attempted == []


def test_explicit_sms_otp_channel_falls_back_to_email_when_master_switch_is_off(app, monkeypatch):
    from app.auth.otp_service import OTPService

    stored = []
    sent = {}
    sms_attempts = []
    monkeypatch.setattr(OTPService, "store_otp", staticmethod(lambda **kwargs: stored.append(kwargs) or True))
    monkeypatch.setattr(OTPService, "_dev_fallback_allowed", staticmethod(lambda: False))
    monkeypatch.setattr(OTPService, "send_email_otp_checked", staticmethod(
        lambda **kwargs: sent.update(kwargs) or {"success": True}
    ))
    monkeypatch.setattr(
        "app.notifications.channel_handlers.twilio_sms.TwilioSmsHandler",
        lambda: sms_attempts.append(True),
    )
    app.config["SMS_DELIVERY_ENABLED"] = False

    with app.app_context():
        result = OTPService.send_otp_multi_channel(
            identifier="account-email-otp",
            otp="384921",
            purpose="phone_verification",
            channels=["twilio_sms"],
            email="person@example.test",
            phone="+256700000001",
            max_retries=1,
        )

    assert result["success"] is True
    assert result["channel_used"] == "email"
    assert sent["email"] == "person@example.test"
    assert sms_attempts == []



def test_twilio_handler_cannot_send_when_global_switch_is_off(app, monkeypatch):
    from app.models.system_config import SystemConfig
    from app.notifications.channel_handlers.twilio_sms import TwilioSmsHandler

    values = {
        "TWILIO_ACCOUNT_SID": "AC" + "1" * 32,
        "TWILIO_AUTH_TOKEN": "configured-test-token",
        "TWILIO_FROM_NUMBER": "+15005550006",
        "TWILIO_SMS_ENABLED": True,
    }
    monkeypatch.setattr(
        SystemConfig,
        "get",
        classmethod(lambda cls, key, default=None: values.get(key, default)),
    )
    client_attempts = []
    monkeypatch.setattr(
        "twilio.rest.Client",
        lambda *args, **kwargs: client_attempts.append((args, kwargs)),
    )
    app.config["SMS_DELIVERY_ENABLED"] = False

    class TestNotification:
        body = "This must not be sent while the master switch is off."

    with app.app_context():
        result = TwilioSmsHandler().deliver(
            TestNotification(),
            {"phone": "+256700000001"},
        )

    assert result["success"] is False
    assert client_attempts == []
