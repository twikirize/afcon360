from datetime import datetime
import inspect
from types import SimpleNamespace

from flask import Flask

from app.auth import routes as auth_routes
from app.auth.config_model import AuthConfiguration
from app.auth.otp_service import OTPService
from app.auth.phone_verification import PhoneVerificationService


def _request_app():
    app = Flask("phone-verification-tests")
    app.secret_key = "phone-verification-test-secret"
    app.add_url_rule("/", endpoint="index", view_func=lambda: "ok")
    app.add_url_rule(
        "/account",
        endpoint="profile.account_overview",
        view_func=lambda: "account",
    )
    app.add_url_rule(
        "/verify-phone",
        endpoint="auth.verify_phone",
        view_func=lambda: "ok",
    )
    return app


def _user():
    return SimpleNamespace(
        id=7,
        public_id="user-public-id",
        email="person@example.com",
        phone_verified=False,
        phone_verified_at=None,
    )


def _profile():
    return SimpleNamespace(
        phone_number="+256700000000",
        phone_verified=False,
    )


def test_phone_verification_updates_user_and_profile(monkeypatch):
    user = _user()
    profile = _profile()
    app = _request_app()

    monkeypatch.setattr(auth_routes, "current_user", user)
    monkeypatch.setattr(
        "app.profile.models.get_profile_by_user",
        lambda _: profile,
    )
    monkeypatch.setattr(
        OTPService,
        "verify_otp",
        staticmethod(lambda **_: (True, "OTP verified successfully")),
    )
    monkeypatch.setattr(auth_routes.db.session, "commit", lambda: None)

    with app.test_request_context("/verify-phone", method="POST", data={"code": "123456"}):
        response = inspect.unwrap(auth_routes.verify_phone)()

    assert response.status_code == 302
    assert user.phone_verified is True
    assert isinstance(user.phone_verified_at, datetime)
    assert profile.phone_verified is True
    assert response.headers["Location"] == "/account"


def test_invalid_phone_code_keeps_both_identity_layers_unverified(monkeypatch):
    user = _user()
    profile = _profile()
    app = _request_app()

    monkeypatch.setattr(auth_routes, "current_user", user)
    monkeypatch.setattr(
        "app.profile.models.get_profile_by_user",
        lambda _: profile,
    )
    monkeypatch.setattr(
        OTPService,
        "verify_otp",
        staticmethod(lambda **_: (False, "Invalid OTP")),
    )

    with app.test_request_context("/verify-phone", method="POST", data={"code": "000000"}):
        response = inspect.unwrap(auth_routes.verify_phone)()

    assert response.status_code == 302
    assert user.phone_verified is False
    assert user.phone_verified_at is None
    assert profile.phone_verified is False


def test_request_code_uses_account_email_as_temporary_transport(monkeypatch):
    user = _user()
    profile = _profile()
    sent = {}

    monkeypatch.setattr(OTPService, "generate_otp", staticmethod(lambda length=6: "654321"))
    monkeypatch.setattr(
        OTPService,
        "store_otp",
        staticmethod(lambda **kwargs: sent.update(stored=kwargs) or True),
    )
    monkeypatch.setattr(
        OTPService,
        "send_email_otp_checked",
        staticmethod(lambda **kwargs: sent.update(delivery=kwargs) or {"success": True}),
    )

    result = PhoneVerificationService.request_code(user, profile, "+256701111111")

    assert result["success"] is True
    assert sent["stored"]["identifier"] == user.email
    assert sent["stored"]["purpose"] == "phone_verification"
    assert sent["delivery"]["email"] == user.email
    assert user.phone == "+256701111111"
    assert profile.phone_number == "+256701111111"
    assert user.phone_verified is False


def test_failed_email_delivery_invalidates_stored_phone_code(monkeypatch):
    user = _user()
    profile = _profile()
    invalidated = []

    monkeypatch.setattr(OTPService, "generate_otp", staticmethod(lambda length=6: "654321"))
    monkeypatch.setattr(OTPService, "store_otp", staticmethod(lambda **_: True))
    monkeypatch.setattr(
        OTPService,
        "send_email_otp_checked",
        staticmethod(lambda **_: {"success": False, "message": "delivery failed"}),
    )
    monkeypatch.setattr(
        OTPService,
        "invalidate_otp",
        staticmethod(lambda identifier, purpose: invalidated.append((identifier, purpose)) or True),
    )

    result = PhoneVerificationService.request_code(user, profile, profile.phone_number)

    assert result["success"] is False
    assert invalidated == [(user.email, "phone_verification")]


def test_phone_verification_transport_defaults_to_email():
    config = AuthConfiguration(otp_channels={"email": {"enabled": True}})

    assert config.get_phone_verification_transport() == "email"


def test_owner_selected_sms_transport_delivers_using_configured_provider(monkeypatch):
    user = _user()
    profile = _profile()
    delivered = {}
    config = AuthConfiguration(
        otp_channels={"phone_verification": {"transport": "sms"}},
        twilio_enabled=True,
        twilio_account_sid="AC123",
        twilio_auth_token="secret",
        twilio_phone_number="+123456789",
        sms_provider_preference="twilio",
    )

    monkeypatch.setattr(AuthConfiguration, "get_config", classmethod(lambda cls: config))
    monkeypatch.setattr(OTPService, "generate_otp", staticmethod(lambda length=6: "654321"))
    monkeypatch.setattr(OTPService, "store_otp", staticmethod(lambda **_: True))
    monkeypatch.setattr(
        "app.auth.phone_verification.SMSService",
        lambda **kwargs: delivered.update(service=kwargs) or SimpleNamespace(
            send_message=lambda phone_number, message: delivered.update(
                phone=phone_number, message=message
            ) or {"success": True, "provider": "twilio"}
        ),
    )

    result = PhoneVerificationService.request_code(user, profile, "+256701111111")

    assert result["success"] is True
    assert result["transport"] == "sms"
    assert delivered["service"]["provider"] == "twilio"
    assert delivered["phone"] == "+256701111111"
    assert user.phone_verified is False


def test_sms_transport_fails_closed_when_no_provider_is_configured(monkeypatch):
    user = _user()
    profile = _profile()
    invalidated = []
    config = AuthConfiguration(
        otp_channels={"phone_verification": {"transport": "sms"}},
        twilio_enabled=False,
        africa_talking_enabled=False,
    )

    monkeypatch.setattr(AuthConfiguration, "get_config", classmethod(lambda cls: config))
    monkeypatch.setattr(OTPService, "generate_otp", staticmethod(lambda length=6: "654321"))
    monkeypatch.setattr(OTPService, "store_otp", staticmethod(lambda **_: True))
    monkeypatch.setattr(
        OTPService,
        "invalidate_otp",
        staticmethod(lambda identifier, purpose: invalidated.append((identifier, purpose)) or True),
    )

    result = PhoneVerificationService.request_code(user, profile, "+256701111111")

    assert result["success"] is False
    assert result["code"] == "sms_unavailable"
    assert invalidated == [(user.email, "phone_verification")]
