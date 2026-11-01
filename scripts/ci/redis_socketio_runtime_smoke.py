"""CI-only live Redis integration smoke test.

This script runs in its own Python process, outside pytest's conftest.py,
because the normal test suite deliberately disables Redis at import time.
It verifies the production-style Redis wiring without touching real accounts
or sending financial tasks.
"""
from __future__ import annotations

import os
import sys
import time
import uuid
from pathlib import Path

# Python starts this script with scripts/ci as sys.path[0]. The application
# package lives at the repository root, so add that root explicitly before
# importing AFCON360 modules.
REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

# These variables are set by the dedicated GitHub Actions step. Keep an
# explicit guard here so this script can never silently test a memory fallback.
os.environ["DISABLE_REDIS"] = "0"

from flask import jsonify, request, session

from app import REDIS_AVAILABLE, create_app
from app.config import Config
from app.extensions import limiter, redis_client, socketio


def fail(message: str) -> None:
    raise RuntimeError(f"REDIS_RUNTIME_SMOKE_FAILED: {message}")


def main() -> int:
    if not REDIS_AVAILABLE:
        fail("Redis client was disabled or redis-py is unavailable")

    redis_url = os.getenv("REDIS_URL")
    database_url = os.getenv("DATABASE_URL")
    if not redis_url or not database_url:
        fail("REDIS_URL and DATABASE_URL must be configured")

    app = create_app(Config)
    app.config.update(
        TESTING=True,
        REDIS_REQUIRED=True,
        SESSION_COOKIE_SECURE=False,
    )

    # 1. Shared Redis client and health/readiness dependency.
    redis_client.ping()
    probe_key = f"afcon360:ci:redis-smoke:{uuid.uuid4().hex}"
    redis_client.set(probe_key, "ok", ex=30)
    if redis_client.get(probe_key) != b"ok":
        fail("Redis set/get round trip failed")
    redis_client.delete(probe_key)

    with app.test_client() as client:
        readiness = client.get("/api/health/ready")
        if readiness.status_code != 200:
            fail(f"readiness endpoint returned {readiness.status_code}")

        # 2. Server-side session persistence. This route exists only in this
        # one-off CI process and is never part of the deployed application.
        def session_probe():
            requested = request.args.get("set")
            if requested:
                session["redis_runtime_smoke"] = requested
            return jsonify({"value": session.get("redis_runtime_smoke")})

        app.add_url_rule(
            "/__ci/redis-session-probe",
            endpoint="ci_redis_session_probe",
            view_func=session_probe,
            methods=["GET"],
        )

        expected = uuid.uuid4().hex
        first = client.get("/__ci/redis-session-probe", query_string={"set": expected})
        second = client.get("/__ci/redis-session-probe")
        if first.status_code != 200 or second.status_code != 200:
            fail("Redis session probe route failed")
        if second.get_json().get("value") != expected:
            fail("server-side session did not persist across requests")
        if "redis" not in type(app.session_interface).__name__.lower():
            fail(
                "Flask-Session did not select a Redis session interface: "
                f"{type(app.session_interface).__name__}"
            )

        # 3. Shared rate-limit storage. The third request must be rejected by
        # the configured backend, not by an in-memory test stub.
        def limited_probe():
            return jsonify({"ok": True})

        limited_probe = limiter.limit("2 per minute")(limited_probe)
        app.add_url_rule(
            "/__ci/redis-rate-limit-probe",
            endpoint="ci_redis_rate_limit_probe",
            view_func=limited_probe,
            methods=["GET"],
        )
        statuses = [
            client.get("/__ci/redis-rate-limit-probe").status_code
            for _ in range(3)
        ]
        if statuses != [200, 200, 429]:
            fail(f"Redis-backed rate-limit behavior unexpected: {statuses}")
        if app.config.get("RATELIMIT_STORAGE_URI") != redis_url:
            fail("Flask-Limiter is not configured to use the Redis URL")

    # 4. Socket.IO must use the Redis message queue manager, not the
    # single-process in-memory manager.
    manager = getattr(getattr(socketio, "server", None), "manager", None)
    if manager is None or "redis" not in type(manager).__name__.lower():
        fail(
            "Socket.IO did not initialize a Redis manager: "
            f"{type(manager).__name__ if manager is not None else 'missing'}"
        )

    # Attach a second, independent Socket.IO server to the same Redis
    # channel. An emit from the application server must reach this peer via
    # Redis pub/sub rather than an in-memory local manager.
    from flask import Flask
    from flask_socketio import SocketIO as PeerSocketIO

    channel = getattr(manager, "channel", "flask-socketio")
    peer_app = Flask("afcon360_ci_socketio_peer")
    peer_app.config["SECRET_KEY"] = os.getenv("SECRET_KEY")
    peer_socketio = PeerSocketIO(
        peer_app,
        async_mode="threading",
        message_queue=redis_url,
        channel=channel,
    )
    peer_manager = getattr(getattr(peer_socketio, "server", None), "manager", None)
    if peer_manager is None or "redis" not in type(peer_manager).__name__.lower():
        fail("independent Socket.IO peer did not initialize a Redis manager")

    peer_client = peer_socketio.test_client(peer_app)
    if not peer_client.is_connected():
        fail("independent Socket.IO peer could not connect")
    event_nonce = uuid.uuid4().hex
    socketio.emit(
        "afcon360_ci_redis_probe",
        {"nonce": event_nonce},
        namespace="/",
    )

    deadline = time.monotonic() + 5
    received = []
    while time.monotonic() < deadline:
        received.extend(peer_client.get_received())
        if any(
            item.get("name") == "afcon360_ci_redis_probe"
            and (item.get("args") or [{}])[0].get("nonce") == event_nonce
            for item in received
        ):
            break
        time.sleep(0.05)

    if not any(
        item.get("name") == "afcon360_ci_redis_probe"
        and (item.get("args") or [{}])[0].get("nonce") == event_nonce
        for item in received
    ):
        fail("Socket.IO event did not fan out to the independent Redis-backed peer")
    peer_client.disconnect()

    # 5. Celery must establish a real connection to the configured Redis
    # broker. Do not enqueue or execute a wallet/payment task in this smoke test.
    from app.celery_app import make_celery

    celery_app = make_celery(app)
    with celery_app.connection_for_write() as connection:
        connection.ensure_connection(max_retries=1)

    print("REDIS_CLIENT_PING=PASS")
    print("READINESS_DATABASE_AND_REDIS=PASS")
    print("FLASK_SESSION_REDIS_PERSISTENCE=PASS")
    print("FLASK_LIMITER_REDIS_STORAGE=PASS")
    print("SOCKETIO_REDIS_CROSS_INSTANCE_FANOUT=PASS")
    print("CELERY_REDIS_BROKER_CONNECTION=PASS")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        raise
