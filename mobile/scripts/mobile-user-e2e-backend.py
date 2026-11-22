#!/usr/bin/env python3
"""Test-only AFCON360 backend for disposable Android end-to-end CI.

This script uses only the workflow's ephemeral PostgreSQL and Redis services.
It never targets the public AFCON360 deployment.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(
    os.environ.get(
        "AFCON360_E2E_BACKEND_ROOT",
        str(Path(__file__).resolve().parents[2]),
    )
).resolve()
if not ROOT.is_dir():
    raise RuntimeError("The isolated E2E backend root does not exist.")
sys.path.insert(0, str(ROOT))

EVIDENCE = Path(os.environ.get("AFCON360_E2E_EVIDENCE_DIR", "mobile-e2e-evidence"))
REQUEST_LOG = Path(os.environ.get("AFCON360_E2E_REQUEST_LOG", str(EVIDENCE / "backend-requests.tsv")))
LOGOUT_TARGET = Path(os.environ.get("AFCON360_E2E_LOGOUT_TARGET", "/tmp/afcon360-user-e2e-logout-target.json"))
USERNAME = os.environ.get("AFCON360_E2E_USERNAME", "native_e2e_user")
EMAIL = os.environ.get("AFCON360_E2E_EMAIL", "native-e2e@afcon360.test")
PASSWORD = os.environ.get("AFCON360_E2E_PASSWORD", "NativeE2ePassword2026")


def build_app():
    from app import create_app
    from app.config import TestingConfig
    from flask import g, request

    app = create_app(config_object=TestingConfig)
    app.config.update(
        TESTING=False, DEBUG=False, WTF_CSRF_ENABLED=False, RATELIMIT_ENABLED=False,
        SERVER_NAME=None, PREFERRED_URL_SCHEME="http", SESSION_TYPE="simple",
    )

    @app.after_request
    def record_e2e_request(response):
        # Record method/path/status only. Never record credentials, bodies,
        # cookies, bearer tokens, query-string values, or personal data.
        EVIDENCE.mkdir(parents=True, exist_ok=True)
        with REQUEST_LOG.open("a", encoding="utf-8") as handle:
            handle.write(f"{response.status_code}\t{request.method}\t{request.path}\n")

        # Capture only the session IDs resolved from the logout bearer token.
        # Never write access tokens, refresh tokens, headers, or request bodies.
        if (
            response.status_code == 200
            and request.method == "POST"
            and request.path == "/api/mobile/v1/auth/logout"
        ):
            context = getattr(g, "_afcon360_mobile_auth_context", None)
            record = context.get("record") if isinstance(context, dict) else None
            if isinstance(record, dict):
                LOGOUT_TARGET.parent.mkdir(parents=True, exist_ok=True)
                LOGOUT_TARGET.write_text(
                    json.dumps(
                        {
                            "session_id": str(record.get("session_id") or ""),
                            "server_session_id": str(record.get("server_session_id") or ""),
                            "user_public_id": str(record.get("user_public_id") or ""),
                        },
                        separators=(",", ":"),
                    ),
                    encoding="utf-8",
                )
        return response

    return app


def seed_user(app) -> None:
    from app.extensions import db
    from app.identity.models.user import User

    with app.app_context():
        existing = User.query.filter(
            (User.username == USERNAME) | (User.email == EMAIL)
        ).first()
        if existing is not None:
            raise RuntimeError("The disposable CI database unexpectedly already contains the E2E user.")

        user = User(
            username=USERNAME, email=EMAIL, is_verified=True, email_verified=True,
            is_active=True, is_deleted=False, mfa_enabled=False,
        )
        user.set_password(PASSWORD)
        db.session.add(user)
        db.session.commit()
        print("MOBILE_E2E_SYNTHETIC_USER_SEEDED", flush=True)



def prebuild_checks(app) -> None:
    """Test mobile auth, protected reads and logout without an APK or emulator."""
    from app.auth.mobile_tokens import _load_json, _revoked_key, _token_key
    from app.auth.sessions import ServerSession
    from app.extensions import db, redis_client
    from app.identity.models.user import User, Session as DeviceSession

    evidence = {
        "result": "failed",
        "checks": {},
        "api_statuses": {},
        "production_backend_used": False,
        "money_moved": False,
        "bookings_created": False,
    }
    failures: list[str] = []

    def check(name: str, passed: bool, detail: str | None = None) -> None:
        evidence["checks"][name] = "PASS" if passed else "FAIL"
        if detail:
            evidence["checks"][name] += f" ({detail})"
        if not passed:
            failures.append(name)

    with app.app_context():
        user = User.query.filter_by(username=USERNAME, email=EMAIL).one_or_none()
        if user is None:
            raise AssertionError("The disposable synthetic E2E user was not seeded.")

    client = app.test_client()
    login_response = client.post(
        "/api/mobile/v1/auth/login",
        json={
            "identifier": USERNAME,
            "password": PASSWORD,
            "client": "user",
            "device_id": "afcon360-prebuild-user-device",
            "device_name": "AFCON360 pre-build integration test",
        },
    )
    login_payload = login_response.get_json(silent=True) or {}
    login_data = login_payload.get("data") if isinstance(login_payload, dict) else None
    access_token = login_data.get("access_token") if isinstance(login_data, dict) else None

    check(
        "native password login",
        login_response.status_code == 200 and bool(access_token),
        f"HTTP {login_response.status_code}; code={login_payload.get('code', 'none')}",
    )
    if not access_token:
        EVIDENCE.mkdir(parents=True, exist_ok=True)
        (EVIDENCE / "prebuild-backend-report.json").write_text(
            json.dumps(evidence, indent=2) + "\n",
            encoding="utf-8",
        )
        raise AssertionError("Pre-build native login failed; APK build remains blocked.")

    headers = {"Authorization": f"Bearer {access_token}"}
    access_key = _token_key("access", access_token)
    with app.app_context():
        token_record = _load_json(redis_client.client.get(access_key))
        valid_record = bool(
            token_record
            and token_record.get("token_type") == "access"
            and token_record.get("session_id")
            and token_record.get("server_session_id")
        )
        check("Redis bearer record links both session authorities", valid_record)
        if not valid_record:
            raise AssertionError("The bearer token does not map to both session authorities.")

        device_session_id = str(token_record["session_id"])
        server_session_id = str(token_record["server_session_id"])
        device_session = DeviceSession.query.filter_by(
            session_id=device_session_id,
            user_id=user.id,
        ).one_or_none()
        server_session = ServerSession.query.filter_by(
            session_id=server_session_id,
            user_id=str(user.public_id),
        ).one_or_none()
        check(
            "device and server sessions active before logout",
            bool(
                device_session
                and device_session.revoked_at is None
                and server_session
                and not server_session.is_revoked
            ),
        )

    api_paths = [
        ("native identity", "/api/mobile/v1/auth/me"),
        ("Activity read", "/api/mobile/v1/activity"),
        ("Wallet balance read", "/api/mobile/v1/wallet"),
        ("Wallet transaction history", "/api/mobile/v1/wallet/transactions"),
        ("Wallet PIN status", "/api/mobile/v1/wallet/pin"),
        ("Accommodation discovery", "/api/mobile/v1/accommodation/properties"),
        ("Accommodation booking history", "/api/mobile/v1/accommodation/bookings"),
        ("Events discovery", "/api/mobile/v1/events"),
        ("Event registration history", "/api/mobile/v1/events/registrations"),
    ]
    for label, path in api_paths:
        response = client.get(path, headers=headers)
        evidence["api_statuses"][label] = response.status_code
        check(label, response.status_code == 200, f"HTTP {response.status_code}")

    logout_response = client.post("/api/mobile/v1/auth/logout", headers=headers)
    logout_payload = logout_response.get_json(silent=True) or {}
    logout_data = logout_payload.get("data") if isinstance(logout_payload, dict) else None
    check(
        "logout endpoint confirms device revocation",
        logout_response.status_code == 200
        and isinstance(logout_data, dict)
        and logout_data.get("revoked") is True,
        f"HTTP {logout_response.status_code}",
    )

    with app.app_context():
        revoked_device = DeviceSession.query.filter_by(
            session_id=device_session_id,
            user_id=user.id,
        ).one_or_none()
        revoked_server = ServerSession.query.filter_by(
            session_id=server_session_id,
            user_id=str(user.public_id),
        ).one_or_none()
        check(
            "exact device session revoked in PostgreSQL",
            bool(revoked_device and revoked_device.revoked_at is not None),
        )
        check(
            "exact server session revoked in PostgreSQL",
            bool(revoked_server and revoked_server.is_revoked),
        )
        check(
            "exact mobile session revoked in Redis",
            bool(redis_client.client.exists(_revoked_key(device_session_id))),
        )
        check(
            "logged-out access token deleted from Redis",
            not bool(redis_client.client.exists(access_key)),
        )

    after_logout = client.get("/api/mobile/v1/auth/me", headers=headers)
    check(
        "logged-out bearer token rejected",
        after_logout.status_code == 401,
        f"HTTP {after_logout.status_code}",
    )

    evidence["result"] = "failed" if failures else "passed"
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    (EVIDENCE / "prebuild-backend-report.json").write_text(
        json.dumps(evidence, indent=2) + "\n",
        encoding="utf-8",
    )
    for name, result in evidence["checks"].items():
        print(f"{result}: {name}", flush=True)
    for name, status in evidence["api_statuses"].items():
        print(f"API {status}: {name}", flush=True)
    if failures:
        raise AssertionError("Pre-build backend checks failed: " + ", ".join(failures))
    print(
        "USER_PREBUILD_BACKEND_PASS: login, protected reads, exact PostgreSQL/Redis "
        "session revocation, and rejection of the logged-out bearer token.",
        flush=True,
    )


def assert_evidence(app) -> None:
    from app.auth.sessions import ServerSession
    from app.auth.mobile_tokens import _revoked_key
    from app.extensions import db, redis_client
    from app.identity.models.user import User, Session as DeviceSession

    if not REQUEST_LOG.is_file():
        raise AssertionError("The Android app did not reach the disposable backend; request audit is missing.")

    records = []
    for line in REQUEST_LOG.read_text(encoding="utf-8").splitlines():
        parts = line.split("\t")
        if len(parts) == 3:
            status, method, path = parts
            records.append((int(status), method, path))

    def count_ok(method: str, path: str) -> int:
        return sum(status == 200 and actual_method == method and actual_path == path
                   for status, actual_method, actual_path in records)

    def attempted(method: str, path: str) -> bool:
        return any(actual_method == method and actual_path == path
                   for _, actual_method, actual_path in records)

    progress = {"completed_stages": []}
    progress_path = EVIDENCE / "journey-progress.json"
    if progress_path.is_file():
        try:
            progress = json.loads(progress_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            progress = {"completed_stages": []}
    stages = set(progress.get("completed_stages", []))
    restore_started = "session_restore_started" in stages
    activity_started = "activity_navigation_started" in stages
    wallet_started = "wallet_navigation_started" in stages
    logout_started = "logout_started" in stages or attempted(
        "POST", "/api/mobile/v1/auth/logout"
    )
    logout_succeeded = count_ok("POST", "/api/mobile/v1/auth/logout") >= 1

    checks = {
        "successful password login": "PASS" if count_ok("POST", "/api/mobile/v1/auth/login") >= 1 else "FAIL",
        "identity endpoint after initial login": "PASS" if count_ok("GET", "/api/mobile/v1/auth/me") >= 1 else "FAIL",
        "identity endpoint after app relaunch": (
            ("PASS" if count_ok("GET", "/api/mobile/v1/auth/me") >= 2 else "FAIL")
            if restore_started else "NOT_EXERCISED"
        ),
        "protected Activity read": (
            "PASS" if count_ok("GET", "/api/mobile/v1/activity") >= 1
            else "FAIL" if activity_started else "NOT_EXERCISED"
        ),
        "Wallet balance read": (
            "PASS" if count_ok("GET", "/api/mobile/v1/wallet") >= 1
            else "FAIL" if wallet_started else "NOT_EXERCISED"
        ),
        "Wallet transaction-history read": (
            "PASS" if count_ok("GET", "/api/mobile/v1/wallet/transactions") >= 1
            else "FAIL" if wallet_started else "NOT_EXERCISED"
        ),
        "Wallet PIN-status read": (
            "PASS" if count_ok("GET", "/api/mobile/v1/wallet/pin") >= 1
            else "FAIL" if wallet_started else "NOT_EXERCISED"
        ),
        "server-side logout": (
            ("PASS" if logout_succeeded else "FAIL")
            if logout_started else "NOT_EXERCISED"
        ),
    }

    with app.app_context():
        user = User.query.filter_by(username=USERNAME, email=EMAIL).one_or_none()
        if user is None:
            raise AssertionError("The synthetic E2E user disappeared from the disposable database.")

        if logout_succeeded:
            try:
                target = json.loads(LOGOUT_TARGET.read_text(encoding="utf-8"))
            except (OSError, ValueError, TypeError):
                target = {}
            target_device_id = str(target.get("session_id") or "")
            target_server_id = str(target.get("server_session_id") or "")
            target_user_id = str(target.get("user_public_id") or "")
            target_matches_user = target_user_id == str(user.public_id)
            device_session = (
                DeviceSession.query.filter_by(
                    session_id=target_device_id,
                    user_id=user.id,
                ).one_or_none()
                if target_device_id and target_matches_user else None
            )
            server_session = (
                ServerSession.query.filter_by(
                    session_id=target_server_id,
                    user_id=str(user.public_id),
                ).one_or_none()
                if target_server_id and target_matches_user else None
            )
            checks["logout target correlated to synthetic user"] = (
                "PASS" if target_device_id and target_server_id and target_matches_user else "FAIL"
            )
            checks["server session revoked on logout"] = (
                "PASS" if server_session and server_session.is_revoked else "FAIL"
            )
            checks["device session revoked on logout"] = (
                "PASS" if device_session and device_session.revoked_at is not None else "FAIL"
            )
            checks["Redis mobile session revoked on logout"] = (
                "PASS" if target_device_id and bool(
                    redis_client.client.exists(_revoked_key(target_device_id))
                ) else "FAIL"
            )
        else:
            checks["server session revoked on logout"] = "NOT_EXERCISED"
            checks["device session revoked on logout"] = "NOT_EXERCISED"
            checks["Redis mobile session revoked on logout"] = "NOT_EXERCISED"

        service_api_requests = {}
        for name, method, path, required_stage in (
            ("Accommodation property discovery", "GET", "/api/mobile/v1/accommodation/properties", "stays_screen"),
            ("Accommodation booking history", "GET", "/api/mobile/v1/accommodation/bookings", "stays_screen"),
            ("Events discovery", "GET", "/api/mobile/v1/events", "events_screen"),
            ("Event registration history", "GET", "/api/mobile/v1/events/registrations", "events_screen"),
        ):
            statuses = [
                status for status, actual_method, actual_path in records
                if actual_method == method and actual_path == path
            ]
            service_api_requests[name] = statuses or ["not-requested"]
            if statuses:
                checks[f"native service API: {name}"] = (
                    "PASS" if all(status == 200 for status in statuses) else "FAIL"
                )
            elif required_stage in stages:
                checks[f"native service API: {name}"] = "FAIL"
            else:
                checks[f"native service API: {name}"] = "NOT_EXERCISED"

        db.session.rollback()

    result = (
        "failed" if "FAIL" in checks.values()
        else "incomplete" if "NOT_EXERCISED" in checks.values()
        else "passed"
    )
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    report = {
        "result": result,
        "synthetic_user": USERNAME,
        "checks": checks,
        "journey_progress": progress,
        "native_service_api_requests": service_api_requests,
        "backend_request_audit": [
            {"status": status, "method": method, "path": path}
            for status, method, path in records
        ],
        "production_backend_used": False,
        "money_moved": False,
        "bookings_created": False,
    }
    (EVIDENCE / "backend-e2e-report.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )

    for label, status in checks.items():
        print(f"{status}: {label}", flush=True)

    for label, statuses in service_api_requests.items():
        status = checks[f"native service API: {label}"]
        print(f"{status}: {label}: {statuses}", flush=True)

    failures = [label for label, status in checks.items() if status == "FAIL"]
    if failures:
        raise AssertionError("Backend checks that were actually exercised failed: " + ", ".join(failures))

def main() -> None:
    command = sys.argv[1] if len(sys.argv) > 1 else "serve"
    app = build_app()

    if command == "seed":
        seed_user(app)
    elif command == "serve":
        EVIDENCE.mkdir(parents=True, exist_ok=True)
        if REQUEST_LOG.exists():
            REQUEST_LOG.unlink()
        if LOGOUT_TARGET.exists():
            LOGOUT_TARGET.unlink()
        print("MOBILE_E2E_BACKEND_STARTING on 0.0.0.0:5000", flush=True)
        app.run(host="0.0.0.0", port=5000, debug=False, use_reloader=False, threaded=True)
    elif command == "prebuild":
        if REQUEST_LOG.exists():
            REQUEST_LOG.unlink()
        if LOGOUT_TARGET.exists():
            LOGOUT_TARGET.unlink()
        prebuild_checks(app)
    elif command == "assert":
        assert_evidence(app)
    else:
        raise SystemExit("Usage: mobile-user-e2e-backend.py [seed|prebuild|serve|assert]")


if __name__ == "__main__":
    main()
