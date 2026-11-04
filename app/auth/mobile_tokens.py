"""Opaque native access/refresh token handling.

Native credentials are random bearer secrets. Only SHA-256 digests are used
as Redis keys; durable device-session revocation remains in the existing
Identity sessions table. Redis is mandatory for this feature and fails closed.
"""
from __future__ import annotations

import hashlib
import json
import secrets
from datetime import datetime, timezone
from typing import Any

from flask import g, request

ACCESS_TTL_SECONDS = 10 * 60
REFRESH_TTL_SECONDS = 30 * 24 * 60 * 60
SESSION_REVOKE_TTL_SECONDS = 90 * 24 * 60 * 60


def _redis():
    from app.extensions import redis_client
    return redis_client.client


def _digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _token_key(kind: str, token: str) -> str:
    return "afcon360:mobile:%s:%s" % (kind, _digest(token))


def _session_key(session_id: str) -> str:
    return "afcon360:mobile:session-keys:%s" % session_id


def _revoked_key(session_id: str) -> str:
    return "afcon360:mobile:revoked-session:%s" % session_id


def _load_json(raw: Any) -> dict | None:
    if raw is None:
        return None
    try:
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        value = json.loads(raw)
        return value if isinstance(value, dict) else None
    except (UnicodeDecodeError, TypeError, ValueError):
        return None


def issue_mobile_tokens(
    *,
    user_public_id: str,
    session_id: str,
    server_session_id: str,
    client: str,
    device_id: str,
) -> dict:
    """Issue one short-lived access token and one rotating refresh token."""
    redis = _redis()
    access_token = secrets.token_urlsafe(48)
    refresh_token = secrets.token_urlsafe(64)
    now = int(datetime.now(timezone.utc).timestamp())
    common = {
        "user_public_id": str(user_public_id),
        "session_id": str(session_id),
        "server_session_id": str(server_session_id),
        "client": client,
        "device_id": device_id,
        "issued_at": now,
    }
    access_record = dict(common, token_type="access")
    refresh_record = dict(common, token_type="refresh")
    access_key = _token_key("access", access_token)
    refresh_key = _token_key("refresh", refresh_token)
    session_key = _session_key(session_id)

    pipe = redis.pipeline(transaction=True)
    pipe.setex(access_key, ACCESS_TTL_SECONDS, json.dumps(access_record, separators=(",", ":")))
    pipe.setex(refresh_key, REFRESH_TTL_SECONDS, json.dumps(refresh_record, separators=(",", ":")))
    pipe.sadd(session_key, access_key, refresh_key)
    pipe.expire(session_key, REFRESH_TTL_SECONDS)
    pipe.execute()

    return {
        "token_type": "Bearer",
        "access_token": access_token,
        "expires_in": ACCESS_TTL_SECONDS,
        "refresh_token": refresh_token,
        "refresh_expires_in": REFRESH_TTL_SECONDS,
    }


def _resolve_record(record: dict) -> dict | None:
    """Revalidate token against the canonical user, device and server sessions."""
    from app.identity.models.user import User, Session as DeviceSession
    from app.auth.sessions import ServerSession

    user_public_id = record.get("user_public_id")
    session_id = record.get("session_id")
    server_session_id = record.get("server_session_id")
    if not user_public_id or not session_id or not server_session_id:
        return None

    now = datetime.now(timezone.utc)
    redis = _redis()
    if redis.exists(_revoked_key(session_id)):
        return None

    device_session = DeviceSession.query.filter_by(
        session_id=session_id,
        revoked_at=None,
    ).first()
    if device_session is None:
        return None
    device_expiry = device_session.expires_at
    if device_expiry.tzinfo is None:
        device_expiry = device_expiry.replace(tzinfo=timezone.utc)
    if device_expiry <= now:
        return None

    server_session = ServerSession.query.filter_by(
        session_id=server_session_id,
        is_revoked=False,
    ).first()
    if server_session is None:
        return None
    server_expiry = server_session.expires_at
    if server_expiry.tzinfo is None:
        server_expiry = server_expiry.replace(tzinfo=timezone.utc)
    if server_expiry <= now:
        return None

    user = User.query.filter_by(public_id=user_public_id).first()
    if user is None or not getattr(user, "is_active", True) or getattr(user, "is_deleted", False):
        return None
    if int(device_session.user_id) != int(user.id):
        return None

    return {
        "user": user,
        "record": record,
        "device_session": device_session,
        "server_session": server_session,
    }


def load_mobile_bearer_context(req=None) -> dict | None:
    """Load and validate a bearer identity; never falls back to browser cookies."""
    req = req or request
    auth_header = (req.headers.get("Authorization") or "").strip()
    scheme, _, token = auth_header.partition(" ")
    if scheme.lower() != "bearer" or not token or len(token) > 256:
        return None

    token_hash = _digest(token)
    cached = getattr(g, "_afcon360_mobile_auth_context", None)
    if cached and cached.get("token_hash") == token_hash:
        return cached

    try:
        record = _load_json(_redis().get(_token_key("access", token)))
        if record is None or record.get("token_type") != "access":
            return None
        resolved = _resolve_record(record)
        if resolved is None:
            return None
        resolved["token_hash"] = token_hash
        g._afcon360_mobile_auth_context = resolved
        return resolved
    except Exception:
        # A native token must never authenticate when its revocation/session
        # authority is unavailable.
        return None


def require_mobile_context(expected_client: str | None = None) -> tuple[dict | None, tuple | None]:
    context = load_mobile_bearer_context(request)
    if context is None:
        from flask import jsonify
        return None, (jsonify({
            "success": False,
            "code": "mobile_auth_required",
            "message": "A valid AFCON360 mobile access token is required.",
        }), 401)
    if expected_client and context["record"].get("client") != expected_client:
        from flask import jsonify
        return None, (jsonify({
            "success": False,
            "code": "mobile_client_mismatch",
            "message": "This session is not authorized for this AFCON360 application.",
        }), 403)
    return context, None


def rotate_mobile_refresh_token(refresh_token: str, *, access_token: str, refresh_record: dict) -> int:
    """Atomically consume a refresh token once and store its replacement.

    Returns 1 for success, 0 for invalid token, -1 for replay, -2 for revoked
    session. The replay marker retains the session reference until the original
    refresh lifetime expires so replay can revoke the whole device session.
    """
    redis = _redis()
    old_key = _token_key("refresh", refresh_token)
    used_key = _token_key("refresh-used", refresh_token)
    new_key = _token_key("refresh", access_token)  # caller passes new refresh secret
    session_id = str(refresh_record.get("session_id") or "")
    revoked_key = _revoked_key(session_id)
    new_value = json.dumps(refresh_record, separators=(",", ":"))
    script = """
    if redis.call('EXISTS', KEYS[4]) == 1 then return -2 end
    local current = redis.call('GET', KEYS[1])
    if not current then
      if redis.call('EXISTS', KEYS[2]) == 1 then return -1 end
      return 0
    end
    redis.call('DEL', KEYS[1])
    redis.call('SET', KEYS[2], current, 'EX', ARGV[1])
    redis.call('SET', KEYS[3], ARGV[2], 'EX', ARGV[3])
    return 1
    """
    result = redis.eval(
        script,
        4,
        old_key,
        used_key,
        new_key,
        revoked_key,
        REFRESH_TTL_SECONDS,
        new_value,
        REFRESH_TTL_SECONDS,
    )
    try:
        return int(result)
    except (TypeError, ValueError):
        return 0


def store_rotated_access_token(access_token: str, record: dict) -> None:
    redis = _redis()
    access_key = _token_key("access", access_token)
    session_id = str(record["session_id"])
    pipe = redis.pipeline(transaction=True)
    pipe.setex(access_key, ACCESS_TTL_SECONDS, json.dumps(record, separators=(",", ":")))
    pipe.sadd(_session_key(session_id), access_key)
    pipe.expire(_session_key(session_id), REFRESH_TTL_SECONDS)
    pipe.execute()


def mark_mobile_session_revoked(session_id: str) -> None:
    """Invalidate all tokens for one existing Identity device session."""
    redis = _redis()
    session_key = _session_key(session_id)
    token_keys = redis.smembers(session_key) or set()
    pipe = redis.pipeline(transaction=True)
    pipe.setex(_revoked_key(session_id), SESSION_REVOKE_TTL_SECONDS, "1")
    for key in token_keys:
        pipe.delete(key)
    pipe.delete(session_key)
    pipe.execute()


def pop_mobile_mfa_challenge(challenge_token: str) -> dict | None:
    """Atomically consume a one-time MFA challenge."""
    redis = _redis()
    key = "afcon360:mobile:mfa:%s" % _digest(challenge_token)
    raw = redis.eval(
        "local value = redis.call('GET', KEYS[1]); if value then redis.call('DEL', KEYS[1]); end; return value",
        1,
        key,
    )
    return _load_json(raw)
