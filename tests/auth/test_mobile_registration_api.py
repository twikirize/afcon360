from types import SimpleNamespace


def _registration_payload():
    return {
        "username": "native_signup_user",
        "email": "native-signup@example.test",
        "password": "StrongNative#2026",
    }


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
