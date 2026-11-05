import json
import os
import uuid
from concurrent.futures import ThreadPoolExecutor

import redis

from app.auth import otp_store


def _redis_client():
    url = os.environ.get("TEST_REDIS_URL", "redis://127.0.0.1:6379/15")
    client = redis.Redis.from_url(url, decode_responses=False)
    client.ping()
    return client


def test_password_reset_otp_compare_and_delete_preserves_code_on_wrong_attempt(monkeypatch):
    client = _redis_client()
    key = "otp:mobile-reset:" + uuid.uuid4().hex
    expected_hash = "hmac-sha256-test-hash"
    monkeypatch.setattr(otp_store, "_redis", lambda: client)

    try:
        client.set(key, json.dumps(expected_hash), ex=600)

        assert otp_store.store_compare_and_delete(key, "wrong-hash") is False
        assert client.get(key) == json.dumps(expected_hash).encode("utf-8")

        assert otp_store.store_compare_and_delete(key, expected_hash) is True
        assert client.get(key) is None
        assert otp_store.store_compare_and_delete(key, expected_hash) is False
    finally:
        client.delete(key)


def test_password_reset_otp_can_only_be_consumed_once_under_concurrency(monkeypatch):
    client = _redis_client()
    key = "otp:mobile-reset-concurrent:" + uuid.uuid4().hex
    expected_hash = "single-use-hmac-" + uuid.uuid4().hex
    monkeypatch.setattr(otp_store, "_redis", lambda: client)

    try:
        client.set(key, json.dumps(expected_hash), ex=600)

        with ThreadPoolExecutor(max_workers=12) as pool:
            outcomes = list(pool.map(
                lambda _: otp_store.store_compare_and_delete(key, expected_hash),
                range(24),
            ))

        assert sum(outcomes) == 1
        assert client.get(key) is None
    finally:
        client.delete(key)

def test_mobile_password_reset_service_consumes_real_redis_code_and_revokes_sessions(monkeypatch):
    from types import SimpleNamespace

    from app.auth import mobile_password_reset, otp_store, services, sessions, tokens
    from app.auth.otp_service import OTPService

    client = _redis_client()
    suffix = uuid.uuid4().hex
    public_id = "redis-reset-user-" + suffix
    identifier = "reset-" + suffix + "@example.test"
    code = "193827"
    otp_key = f"otp:{public_id}:mobile_password_reset"
    attempt_key = f"mobile-password-reset:attempts:{public_id}"
    captured = {}

    user = SimpleNamespace(
        id=83,
        public_id=public_id,
        email=identifier,
        is_active=True,
        is_deleted=False,
    )

    monkeypatch.setattr(otp_store, "_redis", lambda: client)
    monkeypatch.setattr(mobile_password_reset, "_find_user", lambda value: user if value == identifier else None)
    monkeypatch.setattr(tokens, "generate_reset_token", lambda value: "signed-reset-token")

    def confirm(token, password):
        captured.update(token=token, password=password)
        return True

    monkeypatch.setattr(services, "confirm_password_reset", confirm)
    monkeypatch.setattr(
        sessions,
        "revoke_all_device_sessions_for_user",
        lambda user_id, reason: captured.update(user_id=user_id, reason=reason),
    )

    try:
        stored = OTPService.store_otp(
            identifier=public_id,
            otp=code,
            purpose="mobile_password_reset",
            ttl=600,
        )
        assert stored is True
        assert client.get(otp_key) is not None

        success, message = mobile_password_reset.confirm_mobile_password_reset(
            identifier,
            code,
            "Strong#Reset2026",
        )

        assert success is True
        assert "reset" in message.lower()
        assert client.get(otp_key) is None
        assert client.get(attempt_key) is None
        assert captured == {
            "token": "signed-reset-token",
            "password": "Strong#Reset2026",
            "user_id": user.id,
            "reason": "password_reset",
        }
    finally:
        client.delete(otp_key, attempt_key)
