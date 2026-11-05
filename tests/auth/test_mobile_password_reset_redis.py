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
