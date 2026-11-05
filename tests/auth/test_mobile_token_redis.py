import json
import os
import uuid

import redis

from app.auth import mobile_tokens


def _redis_client():
    url = os.environ.get("TEST_REDIS_URL", "redis://127.0.0.1:6379/15")
    client = redis.Redis.from_url(url, decode_responses=False)
    client.ping()
    return client


def test_issue_mobile_tokens_stores_only_digest_keyed_records(monkeypatch):
    client = _redis_client()
    suffix = uuid.uuid4().hex
    raw_access = "access-" + suffix
    raw_refresh = "refresh-" + suffix
    generated = iter((raw_access, raw_refresh))
    monkeypatch.setattr(mobile_tokens, "_redis", lambda: client)
    monkeypatch.setattr(
        mobile_tokens.secrets,
        "token_urlsafe",
        lambda length: next(generated),
    )

    try:
        credentials = mobile_tokens.issue_mobile_tokens(
            user_public_id="redis-test-user-" + suffix,
            session_id="redis-test-session-" + suffix,
            server_session_id="redis-test-server-session-" + suffix,
            client="user",
            device_id="user-device-" + suffix,
        )

        access_key = mobile_tokens._token_key("access", raw_access)
        refresh_key = mobile_tokens._token_key("refresh", raw_refresh)
        access_record = client.get(access_key)
        refresh_record = client.get(refresh_key)

        assert credentials["access_token"] == raw_access
        assert credentials["refresh_token"] == raw_refresh
        assert access_record is not None
        assert refresh_record is not None
        assert raw_access.encode() not in access_key.encode()
        assert raw_refresh.encode() not in refresh_key.encode()
        assert raw_access.encode() not in access_record
        assert raw_refresh.encode() not in refresh_record
        assert json.loads(access_record)["token_type"] == "access"
        assert json.loads(refresh_record)["token_type"] == "refresh"
        assert client.ttl(access_key) > 0
        assert client.ttl(refresh_key) > 0
    finally:
        client.delete(
            mobile_tokens._token_key("access", raw_access),
            mobile_tokens._token_key("refresh", raw_refresh),
            mobile_tokens._session_key("redis-test-session-" + suffix),
        )


def test_refresh_rotation_is_atomic_single_use_and_marks_replay(monkeypatch):
    client = _redis_client()
    suffix = uuid.uuid4().hex
    old_refresh = "old-refresh-" + suffix
    new_refresh = "new-refresh-" + suffix
    session_id = "redis-rotation-session-" + suffix
    old_record = {
        "user_public_id": "redis-user-" + suffix,
        "session_id": session_id,
        "server_session_id": "redis-server-session-" + suffix,
        "client": "user",
        "device_id": "redis-device-" + suffix,
        "token_type": "refresh",
        "issued_at": 1,
    }
    monkeypatch.setattr(mobile_tokens, "_redis", lambda: client)

    old_key = mobile_tokens._token_key("refresh", old_refresh)
    used_key = mobile_tokens._token_key("refresh-used", old_refresh)
    new_key = mobile_tokens._token_key("refresh", new_refresh)
    session_key = mobile_tokens._session_key(session_id)
    revoked_key = mobile_tokens._revoked_key(session_id)

    try:
        client.setex(old_key, mobile_tokens.REFRESH_TTL_SECONDS, json.dumps(old_record))
        result = mobile_tokens.rotate_mobile_refresh_token(
            old_refresh,
            new_refresh_token=new_refresh,
            refresh_record=dict(old_record, issued_at=2),
        )

        assert result == 1
        assert client.get(old_key) is None
        assert client.get(used_key) is not None
        assert client.get(new_key) is not None
        assert new_key.encode() in client.smembers(session_key)

        replay = mobile_tokens.rotate_mobile_refresh_token(
            old_refresh,
            new_refresh_token="third-refresh-" + suffix,
            refresh_record=dict(old_record, issued_at=3),
        )
        assert replay == -1
        assert client.exists(revoked_key) == 0
    finally:
        client.delete(old_key, used_key, new_key, session_key, revoked_key)


def test_revoking_mobile_session_deletes_all_registered_token_keys(monkeypatch):
    client = _redis_client()
    suffix = uuid.uuid4().hex
    session_id = "redis-revoke-session-" + suffix
    access_key = mobile_tokens._token_key("access", "revoke-access-" + suffix)
    refresh_key = mobile_tokens._token_key("refresh", "revoke-refresh-" + suffix)
    session_key = mobile_tokens._session_key(session_id)
    revoked_key = mobile_tokens._revoked_key(session_id)
    monkeypatch.setattr(mobile_tokens, "_redis", lambda: client)

    try:
        client.setex(access_key, mobile_tokens.ACCESS_TTL_SECONDS, "access-record")
        client.setex(refresh_key, mobile_tokens.REFRESH_TTL_SECONDS, "refresh-record")
        client.sadd(session_key, access_key, refresh_key)
        client.expire(session_key, mobile_tokens.REFRESH_TTL_SECONDS)

        mobile_tokens.mark_mobile_session_revoked(session_id)

        assert client.exists(revoked_key) == 1
        assert client.get(access_key) is None
        assert client.get(refresh_key) is None
        assert client.exists(session_key) == 0
    finally:
        client.delete(access_key, refresh_key, session_key, revoked_key)
