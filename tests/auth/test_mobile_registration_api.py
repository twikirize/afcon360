from types import SimpleNamespace


def _registration_payload():
    return {
        "username": "native_signup_user",
        "email": "native-signup@example.test",
        "password": "StrongNative#2026",
    }


def test_native_login_route_is_registered_by_app_factory(app):
    rules = [
        rule for rule in app.url_map.iter_rules()
        if rule.rule == "/api/mobile/v1/auth/login"
    ]
    assert rules
    assert any("POST" in rule.methods for rule in rules)


def test_native_registration_uses_pending_email_verification(client, monkeypatch):
    from app.auth import registration_policy, validators, pending_registration

    monkeypatch.setattr(registration_policy, "email_password_signup_allowed", lambda: True)
    monkeypatch.setattr(registration_policy, "email_verification_required", lambda: True)
    monkeypatch.setattr(validators, "validate_registration", lambda *args, **kwargs: (True, ""))
    monkeypatch.setattr(
        pending_registration,
        "start_pending_registration",
        lambda **kwargs: SimpleNamespace(
            success=True,
            token="opaque-native-registration-token",
            email="native-signup@example.test",
            message="A verification code has been sent.",
            retry_after=None,
            code=None,
            debug_otp="must-not-be-returned",
        ),
    )

    response = client.post("/api/mobile/v1/auth/register", json=_registration_payload())

    assert response.status_code == 202
    body = response.get_json()
    assert body["success"] is True
    assert body["registration_pending"] is True
    assert body["data"]["registration_token"] == "opaque-native-registration-token"
    assert "password" not in body
    assert "debug_otp" not in body
    assert "must-not-be-returned" not in response.get_data(as_text=True)


def test_native_registration_uses_canonical_register_service_when_otp_not_required(client, monkeypatch):
    from app.auth import registration_policy, services, validators

    monkeypatch.setattr(registration_policy, "email_password_signup_allowed", lambda: True)
    monkeypatch.setattr(registration_policy, "email_verification_required", lambda: False)
    monkeypatch.setattr(validators, "validate_registration", lambda *args, **kwargs: (True, ""))
    captured = {}

    def fake_register_user(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(username=kwargs["username"], email=kwargs["email"])

    monkeypatch.setattr(services, "register_user", fake_register_user)

    response = client.post("/api/mobile/v1/auth/register", json=_registration_payload())

    assert response.status_code == 201
    assert response.get_json()["success"] is True
    assert captured["username"] == "native_signup_user"
    assert captured["email"] == "native-signup@example.test"
    assert captured["password"] == _registration_payload()["password"]
    assert "ip_address" in captured
    assert "user_agent" in captured


def test_native_registration_verify_uses_pending_registration_service(client, monkeypatch):
    from app.auth import pending_registration

    captured = {}

    def fake_verify(token, code, **kwargs):
        captured.update({"token": token, "code": code, **kwargs})
        return SimpleNamespace(
            success=True,
            message="Email verified. Your account is ready.",
            already_existed=False,
        )

    monkeypatch.setattr(pending_registration, "verify_pending_registration", fake_verify)

    response = client.post(
        "/api/mobile/v1/auth/register/verify",
        json={"registration_token": "opaque-native-registration-token", "code": "123456"},
    )

    assert response.status_code == 200
    assert response.get_json()["success"] is True
    assert captured["token"] == "opaque-native-registration-token"
    assert captured["code"] == "123456"
    assert "ip" in captured
    assert "user_agent" in captured


def test_native_registration_respects_owner_signup_switch(client, monkeypatch):
    from app.auth import registration_policy

    monkeypatch.setattr(registration_policy, "email_password_signup_allowed", lambda: False)

    response = client.post("/api/mobile/v1/auth/register", json=_registration_payload())

    assert response.status_code == 403
    assert response.get_json()["code"] == "signup_disabled"


def test_native_login_success_returns_bearer_token_contract(client, monkeypatch):
    from flask import jsonify
    from app.auth import mobile_api, services

    user = SimpleNamespace(
        public_id="user-public-id",
        username="native_login_user",
        display_name="Native User",
        email="native-login@example.test",
    )
    captured = {}

    def fake_authenticate(**kwargs):
        captured["auth"] = kwargs
        return services.AuthResult.SUCCESS, {"user": user, "session_id": "server-session-id"}

    def fake_complete(user_arg, client_arg, device_id, device_name, server_session_id):
        captured["completion"] = {
            "user": user_arg,
            "client": client_arg,
            "device_id": device_id,
            "device_name": device_name,
            "server_session_id": server_session_id,
        }
        return jsonify({
            "success": True,
            "data": {
                "token_type": "Bearer",
                "access_token": "access-token",
                "expires_in": 900,
                "refresh_token": "refresh-token",
                "refresh_expires_in": 2592000,
                "user": {
                    "public_id": user.public_id,
                    "username": user.username,
                    "display_name": user.display_name,
                    "email": user.email,
                    "client": "user",
                },
            },
        }), 200

    monkeypatch.setattr(services, "authenticate_user", fake_authenticate)
    monkeypatch.setattr(mobile_api, "_verify_login_eligibility", lambda user_arg, client_arg: None)
    monkeypatch.setattr(mobile_api, "_complete_native_login", fake_complete)

    response = client.post(
        "/api/mobile/v1/auth/login",
        json={
            "identifier": user.email,
            "password": "CorrectHorse#2026",
            "client": "user",
            "device_id": "user-installation-12345",
            "device_name": "AFCON360 User",
        },
    )

    assert response.status_code == 200
    body = response.get_json()
    assert body["success"] is True
    assert body["data"]["token_type"] == "Bearer"
    assert body["data"]["access_token"] == "access-token"
    assert body["data"]["refresh_token"] == "refresh-token"
    assert body["data"]["user"]["public_id"] == user.public_id
    assert captured["auth"]["identifier"] == user.email
    assert captured["completion"]["client"] == "user"
    assert captured["completion"]["device_id"] == "user-installation-12345"
    assert captured["completion"]["server_session_id"] == "server-session-id"


def test_native_login_returns_totp_challenge_contract(client, monkeypatch):
    import json
    from app.auth import mobile_api, services

    user = SimpleNamespace(
        public_id="mfa-user-public-id",
        username="mfa_user",
        email="mfa-user@example.test",
    )
    saved = {}

    class FakeRedis:
        def setex(self, key, ttl, value):
            saved.update(key=key, ttl=ttl, value=json.loads(value))

    monkeypatch.setattr(
        services,
        "authenticate_user",
        lambda **kwargs: (services.AuthResult.MFA_REQUIRED, {"user": user, "mfa_type": "totp"}),
    )
    monkeypatch.setattr(mobile_api, "_verify_login_eligibility", lambda user_arg, client_arg: None)
    monkeypatch.setattr(mobile_api, "_redis", lambda: FakeRedis())
    monkeypatch.setattr(mobile_api.secrets, "token_urlsafe", lambda length: "one-time-challenge-token")

    response = client.post(
        "/api/mobile/v1/auth/login",
        json={
            "identifier": user.username,
            "password": "CorrectHorse#2026",
            "client": "user",
            "device_id": "user-installation-67890",
            "device_name": "AFCON360 User",
        },
    )

    assert response.status_code == 202
    body = response.get_json()
    assert body["success"] is True
    assert body["mfa_required"] is True
    assert body["challenge_token"] == "one-time-challenge-token"
    assert body["mfa_type"] == "totp"
    assert body["expires_in"] == 300
    assert saved["ttl"] == 300
    assert saved["value"]["user_public_id"] == user.public_id
    assert saved["value"]["device_id"] == "user-installation-67890"
    assert saved["value"]["client"] == "user"


def test_native_login_rejects_invalid_credentials(client, monkeypatch):
    from app.auth import services

    monkeypatch.setattr(
        services,
        "authenticate_user",
        lambda **kwargs: (services.AuthResult.INVALID_CREDENTIALS, None),
    )

    response = client.post(
        "/api/mobile/v1/auth/login",
        json={
            "identifier": "unknown@example.test",
            "password": "WrongPassword#2026",
            "client": "user",
            "device_id": "user-installation-invalid",
            "device_name": "AFCON360 User",
        },
    )

    assert response.status_code == 401
    body = response.get_json()
    assert body["success"] is False
    assert body["code"] == "invalid_credentials"
    assert "access_token" not in body
