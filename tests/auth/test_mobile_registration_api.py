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


def test_native_mobile_api_registers_the_expected_user_and_driver_routes(app):
    expected = {
        "/api/mobile/v1/auth/login",
        "/api/mobile/v1/auth/register",
        "/api/mobile/v1/auth/register/verify",
        "/api/mobile/v1/auth/register/resend",
        "/api/mobile/v1/auth/mfa/verify",
        "/api/mobile/v1/auth/refresh",
        "/api/mobile/v1/auth/logout",
        "/api/mobile/v1/auth/account-deletion",
        "/api/mobile/v1/auth/me",
        "/api/mobile/v1/transport/ride-options",
        "/api/mobile/v1/transport/payment-methods/options",
        "/api/mobile/v1/transport/ride-requests",
        "/api/mobile/v1/driver/me",
        "/api/mobile/v1/driver/offers",
        "/api/mobile/v1/driver/status",
        "/api/mobile/v1/driver/location",
        "/api/mobile/v1/driver/trips/active",
        "/api/mobile/v1/driver/earnings",
    }
    registered = {rule.rule for rule in app.url_map.iter_rules()}
    assert expected <= registered


def test_native_protected_endpoints_reject_browser_cookie_without_bearer(client):
    responses = [
        client.get("/api/mobile/v1/auth/me", headers={"Cookie": "session=browser-session"}),
        client.post("/api/mobile/v1/auth/logout", headers={"Cookie": "session=browser-session"}),
        client.post(
            "/api/mobile/v1/auth/account-deletion",
            json={},
            headers={"Cookie": "session=browser-session"},
        ),
    ]

    for response in responses:
        assert response.status_code == 401
        assert response.get_json()["code"] == "mobile_auth_required"


def test_native_refresh_rejects_missing_token_and_fails_closed_on_store_outage(client, monkeypatch):
    from app.auth import mobile_api

    missing = client.post("/api/mobile/v1/auth/refresh", json={})
    assert missing.status_code == 401
    assert missing.get_json()["code"] == "refresh_invalid"

    def redis_unavailable():
        raise RuntimeError("Redis unavailable for test")

    monkeypatch.setattr(mobile_api, "_redis", redis_unavailable)
    unavailable = client.post(
        "/api/mobile/v1/auth/refresh",
        json={"refresh_token": "syntactically-valid-but-unknown-refresh-token"},
    )
    assert unavailable.status_code == 503
    assert unavailable.get_json()["code"] == "auth_service_unavailable"


def test_native_client_context_cannot_cross_between_user_and_driver_apps(app, monkeypatch):
    from app.auth import mobile_tokens

    context = {
        "user": SimpleNamespace(public_id="driver-user"),
        "record": {"client": "driver"},
    }
    monkeypatch.setattr(
        mobile_tokens,
        "load_mobile_bearer_context",
        lambda request: context,
    )

    with app.test_request_context("/api/mobile/v1/transport/ride-options"):
        resolved, error = mobile_tokens.require_mobile_context("user")

    assert resolved is None
    assert error is not None
    assert error[1] == 403
    assert error[0].get_json()["code"] == "mobile_client_mismatch"


def test_native_logout_revokes_device_server_and_mobile_token_sessions(client, monkeypatch):
    from app.auth import mobile_api
    from app.auth import sessions

    user = SimpleNamespace(id=41, public_id="logout-user-public-id")
    context = {
        "user": user,
        "record": {
            "session_id": "device-session-logout-123",
            "server_session_id": "server-session-logout-123",
            "client": "user",
        },
    }
    calls = {}

    monkeypatch.setattr(
        mobile_api,
        "require_mobile_context",
        lambda expected_client=None: (context, None),
    )
    monkeypatch.setattr(
        sessions,
        "revoke_device_session",
        lambda session_id, **kwargs: calls.update(device=(session_id, kwargs)) or True,
    )
    monkeypatch.setattr(
        sessions,
        "revoke_session",
        lambda session_id, **kwargs: calls.update(server=(session_id, kwargs)) or True,
    )
    monkeypatch.setattr(
        mobile_api,
        "mark_mobile_session_revoked",
        lambda session_id: calls.update(redis=session_id),
    )

    response = client.post(
        "/api/mobile/v1/auth/logout",
        headers={"Authorization": "Bearer test-mobile-access-token"},
    )

    assert response.status_code == 200
    assert response.get_json()["data"]["revoked"] is True
    assert calls["device"][0] == "device-session-logout-123"
    assert calls["device"][1]["user_id"] == user.id
    assert calls["server"][0] == "server-session-logout-123"
    assert calls["server"][1]["revoked_by_user_id"] == user.id
    assert calls["redis"] == "device-session-logout-123"


def test_native_account_deletion_delegates_to_shared_account_closure_service(client, monkeypatch):
    from app.auth import mobile_api
    from app.auth import account_deletion_service

    user = SimpleNamespace(id=72, public_id="delete-user-public-id")
    context = {
        "user": user,
        "record": {"session_id": "device-session-delete-123", "client": "user"},
    }
    captured = {}

    monkeypatch.setattr(
        mobile_api,
        "require_mobile_context",
        lambda expected_client=None: (context, None),
    )

    def fake_delete(**kwargs):
        captured.update(kwargs)
        return {"status": "anonymized", "message": "Account closure accepted."}

    monkeypatch.setattr(account_deletion_service, "request_account_deletion", fake_delete)

    response = client.post(
        "/api/mobile/v1/auth/account-deletion",
        headers={"Authorization": "Bearer test-mobile-access-token"},
        json={
            "password": "CurrentPassword#2026",
            "confirmation": "DELETE MY ACCOUNT",
            "mfa_code": "123456",
        },
    )

    assert response.status_code == 200
    assert response.get_json()["data"]["status"] == "anonymized"
    assert captured["user"] is user
    assert captured["password"] == "CurrentPassword#2026"
    assert captured["confirmation"] == "DELETE MY ACCOUNT"
    assert captured["mfa_code"] == "123456"
    assert "ip_address" in captured
    assert "user_agent" in captured


def test_native_token_issuance_stores_only_token_digests(monkeypatch):
    from app.auth import mobile_tokens

    operations = []

    class FakePipeline:
        def setex(self, *args):
            operations.append(("setex", args))
            return self

        def sadd(self, *args):
            operations.append(("sadd", args))
            return self

        def expire(self, *args):
            operations.append(("expire", args))
            return self

        def execute(self):
            return True

    class FakeRedis:
        def pipeline(self, transaction=True):
            assert transaction is True
            return FakePipeline()

    monkeypatch.setattr(mobile_tokens, "_redis", lambda: FakeRedis())
    generated = iter(("raw-access-token-secret", "raw-refresh-token-secret"))
    monkeypatch.setattr(mobile_tokens.secrets, "token_urlsafe", lambda length: next(generated))

    credentials = mobile_tokens.issue_mobile_tokens(
        user_public_id="user-public-id",
        session_id="device-session-id",
        server_session_id="server-session-id",
        client="user",
        device_id="user-device-installation",
    )

    assert credentials["access_token"] == "raw-access-token-secret"
    assert credentials["refresh_token"] == "raw-refresh-token-secret"
    serialized_operations = repr(operations)
    assert "raw-access-token-secret" not in serialized_operations
    assert "raw-refresh-token-secret" not in serialized_operations
    assert mobile_tokens._token_key("access", credentials["access_token"]) in serialized_operations
    assert mobile_tokens._token_key("refresh", credentials["refresh_token"]) in serialized_operations

def test_native_mobile_api_registers_password_reset_routes(app):
    expected = {
        "/api/mobile/v1/auth/password-reset/request",
        "/api/mobile/v1/auth/password-reset/confirm",
    }
    registered = {rule.rule for rule in app.url_map.iter_rules()}
    assert expected <= registered


def test_native_password_reset_request_has_same_response_for_existing_and_unknown_accounts(client, monkeypatch):
    from app.auth import mobile_password_reset

    captured = []
    result_state = {"deliverable": False}

    def fake_request(identifier):
        captured.append(identifier)
        return result_state["deliverable"]

    monkeypatch.setattr(mobile_password_reset, "request_mobile_password_reset", fake_request)

    responses = []
    for deliverable in (False, True):
        result_state["deliverable"] = deliverable
        response = client.post(
            "/api/mobile/v1/auth/password-reset/request",
            json={"identifier": "member@example.test"},
        )
        responses.append((response.status_code, response.get_json()))

    assert captured == ["member@example.test", "member@example.test"]
    assert responses[0] == responses[1]
    assert responses[0][0] == 202
    assert responses[0][1]["success"] is True
    assert "code" not in responses[0][1]
    assert "otp" not in responses[0][1]
    assert responses[0][1]["data"]["expires_in"] == 600


def test_native_password_reset_confirm_route_delegates_and_returns_success(client, monkeypatch):
    from app.auth import mobile_password_reset

    captured = {}

    def fake_confirm(**kwargs):
        captured.update(kwargs)
        return True, "Your password has been reset. Sign in with your new password."

    monkeypatch.setattr(
        mobile_password_reset,
        "confirm_mobile_password_reset",
        fake_confirm,
    )

    response = client.post(
        "/api/mobile/v1/auth/password-reset/confirm",
        json={
            "identifier": "member@example.test",
            "code": "123456",
            "new_password": "Strong#Reset2026",
            "confirm_password": "Strong#Reset2026",
        },
    )

    assert response.status_code == 200
    assert response.get_json()["success"] is True
    assert captured == {
        "identifier": "member@example.test",
        "code": "123456",
        "new_password": "Strong#Reset2026",
    }


def test_native_password_reset_confirm_rejects_mismatched_passwords(client, monkeypatch):
    from app.auth import mobile_password_reset

    monkeypatch.setattr(
        mobile_password_reset,
        "confirm_mobile_password_reset",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("service must not run")),
    )

    response = client.post(
        "/api/mobile/v1/auth/password-reset/confirm",
        json={
            "identifier": "member@example.test",
            "code": "123456",
            "new_password": "Strong#Reset2026",
            "confirm_password": "Different#Reset2026",
        },
    )

    assert response.status_code == 400
    assert response.get_json()["code"] == "password_reset_password_mismatch"


def test_mobile_password_reset_stores_otp_by_public_id_and_sends_ten_minute_code(monkeypatch):
    from app.auth import mobile_password_reset
    from app.auth.otp_service import OTPService

    user = SimpleNamespace(
        id=81,
        public_id="password-reset-public-id",
        email="reset@example.test",
        is_active=True,
        is_deleted=False,
    )
    stored = {}
    sent = {}

    monkeypatch.setattr(mobile_password_reset, "_find_user", lambda identifier: user)
    monkeypatch.setattr(OTPService, "generate_otp", staticmethod(lambda length=6: "482915"))
    monkeypatch.setattr(
        OTPService,
        "store_otp",
        staticmethod(lambda **kwargs: stored.update(kwargs) or True),
    )
    monkeypatch.setattr(
        OTPService,
        "send_email_otp_checked",
        staticmethod(lambda **kwargs: sent.update(kwargs) or {"success": True}),
    )

    result = mobile_password_reset.request_mobile_password_reset("reset@example.test")

    assert result is True
    assert stored == {
        "identifier": "password-reset-public-id",
        "otp": "482915",
        "purpose": "mobile_password_reset",
        "ttl": 600,
    }
    assert sent["email"] == "reset@example.test"
    assert sent["otp"] == "482915"
    assert sent["purpose"] == "password_reset"
    assert sent["user_id"] == 81
    assert sent["expires_in_minutes"] == 10


def test_mobile_password_reset_rejects_after_five_incorrect_code_attempts(monkeypatch):
    from app.auth import mobile_password_reset
    from app.auth.otp_service import OTPService

    user = SimpleNamespace(
        id=82,
        public_id="password-reset-attempt-user",
        email="attempts@example.test",
        is_active=True,
        is_deleted=False,
    )
    invalidated = []
    deleted = []

    monkeypatch.setattr(mobile_password_reset, "_find_user", lambda identifier: user)
    monkeypatch.setattr(mobile_password_reset, "store_incr", lambda *args, **kwargs: 6)
    monkeypatch.setattr(mobile_password_reset, "store_delete", lambda key: deleted.append(key) or True)
    monkeypatch.setattr(
        OTPService,
        "invalidate_otp",
        staticmethod(lambda identifier, purpose: invalidated.append((identifier, purpose))),
    )
    monkeypatch.setattr(
        OTPService,
        "verify_otp",
        staticmethod(lambda **kwargs: (_ for _ in ()).throw(AssertionError("OTP must not be checked after lockout"))),
    )

    success, message = mobile_password_reset.confirm_mobile_password_reset(
        "attempts@example.test",
        "123456",
        "Strong#Reset2026",
    )

    assert success is False
    assert "Too many" in message
    assert invalidated == [("password-reset-attempt-user", "mobile_password_reset")]
    assert deleted == ["mobile-password-reset:attempts:password-reset-attempt-user"]


def test_mobile_password_reset_success_uses_canonical_reset_and_revokes_device_sessions(monkeypatch):
    from app.auth import mobile_password_reset, services, sessions, tokens
    from app.auth.otp_service import OTPService

    user = SimpleNamespace(
        id=83,
        public_id="password-reset-success-user",
        email="success@example.test",
        is_active=True,
        is_deleted=False,
    )
    captured = {}

    monkeypatch.setattr(mobile_password_reset, "_find_user", lambda identifier: user)
    monkeypatch.setattr(mobile_password_reset, "store_incr", lambda *args, **kwargs: 1)
    monkeypatch.setattr(mobile_password_reset, "store_delete", lambda key: True)
    monkeypatch.setattr(
        mobile_password_reset,
        "store_compare_and_delete",
        lambda key, expected_hash: key == "otp:password-reset-success-user:mobile_password_reset"
        and expected_hash == OTPService.hash_otp("193827"),
    )
    monkeypatch.setattr(tokens, "generate_reset_token", lambda public_id: "signed-reset-token")
    monkeypatch.setattr(
        services,
        "confirm_password_reset",
        lambda token, password: captured.update(token=token, password=password) or True,
    )
    monkeypatch.setattr(
        sessions,
        "revoke_all_device_sessions_for_user",
        lambda user_id, reason: captured.update(user_id=user_id, reason=reason),
    )

    success, message = mobile_password_reset.confirm_mobile_password_reset(
        "success@example.test",
        "193827",
        "Strong#Reset2026",
    )

    assert success is True
    assert "reset" in message.lower()
    assert captured == {
        "token": "signed-reset-token",
        "password": "Strong#Reset2026",
        "user_id": 83,
        "reason": "password_reset",
    }

def test_native_password_reset_request_delegates_without_disclosing_account_state(client, monkeypatch):
    from app.auth import mobile_password_reset

    captured = {}
    monkeypatch.setattr(
        mobile_password_reset,
        "request_mobile_password_reset",
        lambda identifier: captured.update(identifier=identifier) or True,
    )

    response = client.post(
        "/api/mobile/v1/auth/password-reset/request",
        json={"identifier": "member@example.test"},
    )

    assert response.status_code == 202
    assert response.get_json()["success"] is True
    assert "member@example.test" not in response.get_data(as_text=True)
    assert "If an active AFCON360 account" in response.get_json()["data"]["message"]
    assert captured["identifier"] == "member@example.test"


def test_native_password_reset_request_returns_same_response_when_service_fails(client, monkeypatch):
    from app.auth import mobile_password_reset

    monkeypatch.setattr(
        mobile_password_reset,
        "request_mobile_password_reset",
        lambda identifier: (_ for _ in ()).throw(RuntimeError("mail service unavailable")),
    )

    response = client.post(
        "/api/mobile/v1/auth/password-reset/request",
        json={"identifier": "unknown@example.test"},
    )

    assert response.status_code == 202
    assert response.get_json()["data"]["message"] == (
        "If an active AFCON360 account has a registered email address, a reset code has been sent."
    )


def test_native_password_reset_confirmation_validates_code_before_service(client, monkeypatch):
    from app.auth import mobile_password_reset

    monkeypatch.setattr(
        mobile_password_reset,
        "confirm_mobile_password_reset",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("service must not run for invalid code")),
    )

    response = client.post(
        "/api/mobile/v1/auth/password-reset/confirm",
        json={
            "identifier": "member@example.test",
            "code": "12ab56",
            "new_password": "StrongPassword#2026",
            "confirm_password": "StrongPassword#2026",
        },
    )

    assert response.status_code == 400
    assert response.get_json()["code"] == "password_reset_input_invalid"


def test_native_password_reset_confirmation_delegates_to_shared_service(client, monkeypatch):
    from app.auth import mobile_password_reset

    captured = {}

    def fake_confirm(**kwargs):
        captured.update(kwargs)
        return True, "Your password has been reset. Sign in with your new password."

    monkeypatch.setattr(mobile_password_reset, "confirm_mobile_password_reset", fake_confirm)

    response = client.post(
        "/api/mobile/v1/auth/password-reset/confirm",
        json={
            "identifier": "member@example.test",
            "code": "123456",
            "new_password": "StrongPassword#2026",
            "confirm_password": "StrongPassword#2026",
        },
    )

    assert response.status_code == 200
    assert response.get_json()["success"] is True
    assert captured == {
        "identifier": "member@example.test",
        "code": "123456",
        "new_password": "StrongPassword#2026",
    }
