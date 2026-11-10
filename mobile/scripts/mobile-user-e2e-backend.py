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
USERNAME = os.environ.get("AFCON360_E2E_USERNAME", "native_e2e_user")
EMAIL = os.environ.get("AFCON360_E2E_EMAIL", "native-e2e@afcon360.test")
PASSWORD = os.environ.get("AFCON360_E2E_PASSWORD", "NativeE2ePassword2026")


def build_app():
    from app import create_app
    from app.config import TestingConfig
    from flask import request

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
        "protected Activity read": "PASS" if count_ok("GET", "/api/mobile/v1/activity") >= 1 else "FAIL",
        "Wallet balance read": "PASS" if count_ok("GET", "/api/mobile/v1/wallet") >= 1 else "FAIL",
        "Wallet transaction-history read": "PASS" if count_ok("GET", "/api/mobile/v1/wallet/transactions") >= 1 else "FAIL",
        "Wallet PIN-status read": "PASS" if count_ok("GET", "/api/mobile/v1/wallet/pin") >= 1 else "FAIL",
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
            server_sessions = ServerSession.query.filter_by(user_id=user.public_id).all()
            device_sessions = DeviceSession.query.filter_by(user_id=user.id).all()
            checks["server session revoked on logout"] = (
                "PASS" if server_sessions and all(row.is_revoked for row in server_sessions) else "FAIL"
            )
            checks["device session revoked on logout"] = (
                "PASS" if device_sessions and all(row.revoked_at is not None for row in device_sessions) else "FAIL"
            )
            checks["Redis mobile session revoked on logout"] = (
                "PASS" if device_sessions and all(
                    bool(redis_client.client.exists(_revoked_key(row.session_id)))
                    for row in device_sessions
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
        print("MOBILE_E2E_BACKEND_STARTING on 0.0.0.0:5000", flush=True)
        app.run(host="0.0.0.0", port=5000, debug=False, use_reloader=False, threaded=True)
    elif command == "assert":
        assert_evidence(app)
    else:
        raise SystemExit("Usage: mobile-user-e2e-backend.py [seed|serve|assert]")


if __name__ == "__main__":
    main()
