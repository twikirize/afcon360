#!/usr/bin/env python3
"""Disposable-CI backend and evidence recorder for the AFCON360 Driver APK.

Only the workflow's ephemeral PostgreSQL/Redis services are used. No production
account, database, booking, payment, vehicle assignment or driver status change
is created by this test.
"""
from __future__ import annotations

import json
import os
import sys
import uuid
import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
# The APK source and the backend candidate are intentionally separate pull
# requests. In the authenticated E2E job, load Flask/app models from the
# consolidated backend candidate while keeping this test harness from PR #73.
BACKEND_ROOT = Path(
    os.environ.get("AFCON360_DRIVER_E2E_BACKEND_ROOT", str(ROOT))
).resolve()
if not (BACKEND_ROOT / "app" / "__init__.py").is_file():
    raise RuntimeError(
        f"Driver E2E backend checkout is incomplete: expected {BACKEND_ROOT / 'app' / '__init__.py'}"
    )

# Flask's env/config loading and Alembic must run from the same checkout that
# was migrated. Otherwise a test launched from the native PR root may resolve
# different app code or search the wrong .env files/database defaults.
os.chdir(BACKEND_ROOT)
sys.path.insert(0, str(BACKEND_ROOT))
if str(ROOT) in sys.path:
    sys.path.remove(str(ROOT))

EVIDENCE = Path(os.environ.get("AFCON360_DRIVER_E2E_EVIDENCE_DIR", "driver-e2e-evidence"))
if not EVIDENCE.is_absolute():
    EVIDENCE = (ROOT / EVIDENCE).resolve()
REQUEST_LOG = Path(os.environ.get(
    "AFCON360_DRIVER_E2E_REQUEST_LOG",
    str(EVIDENCE / "backend-requests.tsv"),
))
DRIVER_USERNAME = os.environ.get("AFCON360_DRIVER_E2E_USERNAME", "native_e2e_driver")
DRIVER_EMAIL = os.environ.get("AFCON360_DRIVER_E2E_EMAIL", "native-driver-e2e@afcon360.test")
DRIVER_PASSWORD = os.environ.get("AFCON360_DRIVER_E2E_PASSWORD", "DriverE2ePassword2026")
NON_DRIVER_USERNAME = os.environ.get("AFCON360_NON_DRIVER_E2E_USERNAME", "native_e2e_customer")
NON_DRIVER_EMAIL = os.environ.get("AFCON360_NON_DRIVER_E2E_EMAIL", "native-customer-e2e@afcon360.test")
NON_DRIVER_PASSWORD = os.environ.get("AFCON360_NON_DRIVER_E2E_PASSWORD", "CustomerE2ePassword2026")
DRIVER_CODE = "E2E-DRV01"
BACKEND_PREFLIGHT_USER_AGENT = "AFCON360 Driver E2E backend preflight"


def build_app():
    import app as backend_app
    from app import create_app
    from app.config import TestingConfig
    from flask import request

    loaded_app = Path(backend_app.__file__).resolve()
    expected_app = (BACKEND_ROOT / "app" / "__init__.py").resolve()
    if loaded_app != expected_app:
        raise RuntimeError(
            f"Driver E2E loaded Flask app from {loaded_app}, expected backend candidate {expected_app}"
        )
    app = create_app(config_object=TestingConfig)
    app.config.update(
        TESTING=False,
        DEBUG=False,
        WTF_CSRF_ENABLED=False,
        RATELIMIT_ENABLED=False,
        SERVER_NAME=None,
        PREFERRED_URL_SCHEME="http",
        SESSION_TYPE="simple",
    )

    @app.after_request
    def record_e2e_request(response):
        # Method/path/status only. Never record credentials, bodies, headers,
        # cookies, bearer tokens, query values or personal data.
        EVIDENCE.mkdir(parents=True, exist_ok=True)
        # The backend-only offers preflight has its own sanitized response summary.
        # Keep it out of the APK request audit so it cannot satisfy client-journey
        # login, identity-read or logout evidence.
        is_backend_preflight = request.headers.get("User-Agent") == BACKEND_PREFLIGHT_USER_AGENT
        if not is_backend_preflight:
            with REQUEST_LOG.open("a", encoding="utf-8") as handle:
                handle.write(f"{response.status_code}\t{request.method}\t{request.path}\n")

            # Record only the machine-readable error code for failed login
            # attempts. Never persist the submitted identifier, password,
            # response message, token, headers, cookies or request body.
            if request.path == "/api/mobile/v1/auth/login" and response.status_code >= 400:
                payload = response.get_json(silent=True) or {}
                code = str(payload.get("code") or "missing_error_code")
                if not code.replace("_", "").replace("-", "").isalnum():
                    code = "invalid_error_code"
                submitted = str((request.get_json(silent=True) or {}).get("identifier") or "").strip().lower()
                expected = str(DRIVER_USERNAME or "").strip().lower()
                matches_expected = bool(submitted) and submitted == expected
                resolved_profile = False
                try:
                    from sqlalchemy import func, or_
                    from app.identity.models.user import User
                    from app.transport.models import DriverProfile
                    identity = User.query.filter(
                        or_(func.lower(User.username) == submitted, func.lower(User.email) == submitted)
                    ).first() if submitted else None
                    if identity is not None:
                        resolved_profile = DriverProfile.query.filter_by(
                            user_id=identity.id, is_deleted=False
                        ).first() is not None
                except Exception:
                    resolved_profile = False
                # Store only booleans and the public error code, never the submitted identifier/password.
                with (EVIDENCE / "auth-failures.tsv").open("a", encoding="utf-8") as handle:
                    handle.write(f"{response.status_code}\t{code}\t{str(matches_expected).lower()}\t{str(resolved_profile).lower()}\n")

        # Keep a deliberately narrow, non-identifying projection of the
        # server-owned Driver API response for audit evidence.
        if request.path == "/api/mobile/v1/driver/me" and response.status_code == 200:
            payload = response.get_json(silent=True) or {}
            data = payload.get("data") if isinstance(payload, dict) else {}
            go_live = data.get("go_live") if isinstance(data, dict) else {}
            checks = go_live.get("checks") if isinstance(go_live, dict) else []
            summary = {
                "driver_code": data.get("driver_code") if isinstance(data, dict) else None,
                "compliance_status": data.get("compliance_status") if isinstance(data, dict) else None,
                "is_online": data.get("is_online") if isinstance(data, dict) else None,
                "is_available": data.get("is_available") if isinstance(data, dict) else None,
                "go_live_ready": go_live.get("ready") if isinstance(go_live, dict) else None,
                "required_checks": [
                    {"key": item.get("key"), "ok": item.get("ok"), "required": item.get("required")}
                    for item in checks if isinstance(item, dict) and item.get("required")
                ] if isinstance(checks, list) else [],
            }
            (EVIDENCE / "driver-profile-summary.json").write_text(
                json.dumps(summary, indent=2) + "\n", encoding="utf-8"
            )
        elif request.path == "/api/mobile/v1/driver/offers" and response.status_code == 200:
            payload = response.get_json(silent=True) or {}
            data = payload.get("data") if isinstance(payload, dict) else {}
            offers = data.get("offers") if isinstance(data, dict) else None
            summary = {
                "http_status": response.status_code,
                "offers_count": len(offers) if isinstance(offers, list) else None,
                "offers_list_valid": isinstance(offers, list),
            }
            (EVIDENCE / "driver-offers-summary.json").write_text(
                json.dumps(summary, indent=2) + "\n", encoding="utf-8"
            )
        elif request.path == "/api/mobile/v1/driver/trips/active" and response.status_code == 200:
            payload = response.get_json(silent=True) or {}
            summary = {"active_trip_present": bool(payload.get("data")) if isinstance(payload, dict) else None}
            (EVIDENCE / "driver-active-trip-summary.json").write_text(
                json.dumps(summary, indent=2) + "\n", encoding="utf-8"
            )
        elif request.path == "/api/mobile/v1/driver/earnings" and response.status_code == 200:
            payload = response.get_json(silent=True) or {}
            data = payload.get("data") if isinstance(payload, dict) else {}
            rows = data.get("by_currency") if isinstance(data, dict) else None
            summary = {"currency_groups": len(rows) if isinstance(rows, list) else None}
            (EVIDENCE / "driver-earnings-summary.json").write_text(
                json.dumps(summary, indent=2) + "\n", encoding="utf-8"
            )
        return response

    return app


def _create_user(*, username: str, email: str, password: str):
    from app.identity.models.user import User

    user = User(
        username=username,
        email=email,
        is_verified=True,
        email_verified=True,
        is_active=True,
        is_deleted=False,
        mfa_enabled=False,
    )
    user.set_password(password)
    return user


def seed_test_accounts(app) -> None:
    from app.extensions import db
    from app.identity.models.user import User
    from app.transport.models import ComplianceStatus, DriverProfile, VerificationTier

    with app.app_context():
        for username, email in (
            (DRIVER_USERNAME, DRIVER_EMAIL),
            (NON_DRIVER_USERNAME, NON_DRIVER_EMAIL),
        ):
            existing = User.query.filter(
                (User.username == username) | (User.email == email)
            ).first()
            if existing is not None:
                raise RuntimeError(
                    "The fresh disposable CI database unexpectedly already contains "
                    f"the synthetic identity {username!r}."
                )

        driver_user = _create_user(
            username=DRIVER_USERNAME, email=DRIVER_EMAIL, password=DRIVER_PASSWORD
        )
        customer_user = _create_user(
            username=NON_DRIVER_USERNAME, email=NON_DRIVER_EMAIL, password=NON_DRIVER_PASSWORD
        )
        db.session.add_all([driver_user, customer_user])
        db.session.flush()

        # This is intentionally a real but not-yet-approved driver profile.
        # It permits entry to the Driver workspace, while the canonical
        # can_go_live() service must keep the account offline until KYC,
        # approval, licence and (on-demand) vehicle gates are met.
        driver = DriverProfile(
            user_id=driver_user.id,
            driver_code=DRIVER_CODE,
            verification_tier=VerificationTier.PENDING,
            compliance_status=ComplianceStatus.PENDING_REVIEW,
            is_active=True,
            is_deleted=False,
            is_online=False,
            is_available=False,
            max_passenger_capacity=4,
            vehicle_classes=["comfort"],
            service_types=["on_demand"],
        )
        db.session.add(driver)
        db.session.commit()

        # Assert the exact non-deleted-profile lookup used by the production login guard.
        persisted = DriverProfile.query.filter_by(
            user_id=driver_user.id, is_deleted=False
        ).one_or_none()
        if persisted is None:
            raise AssertionError("The synthetic Driver profile was not persisted as a non-deleted row.")


        print("DRIVER_E2E_SYNTHETIC_DRIVER_AND_NON_DRIVER_SEEDED", flush=True)


def verify_driver_only_login_guard(app) -> None:
    """A normal customer account must not be able to sign in as Driver."""
    # This is an intentional negative backend preflight, not an APK request.
    # Keep it out of the authenticated-client request audit.
    headers = {"User-Agent": BACKEND_PREFLIGHT_USER_AGENT}
    with app.test_client() as client:
        response = client.post(
            "/api/mobile/v1/auth/login",
            headers=headers,
            json={
                "identifier": NON_DRIVER_USERNAME,
                "password": NON_DRIVER_PASSWORD,
                "client": "driver",
                "device_id": "driver-e2e-negative-boundary",
                "device_name": "AFCON360 Driver E2E boundary check",
            },
        )
        payload = response.get_json(silent=True) or {}
        denied = response.status_code == 403 and payload.get("code") == "driver_profile_required"
        if not denied:
            raise AssertionError(
                "A non-driver account was not rejected by the authoritative Driver login guard: "
                f"HTTP {response.status_code}, code={payload.get('code')!r}."
            )
        # Non-identifying evidence only; never persist the customer username or password.
        (EVIDENCE / "driver-login-boundary-summary.json").write_text(
            json.dumps({
                "http_status": response.status_code,
                "error_code": payload.get("code"),
                "customer_rejected": True,
            }, indent=2) + "\\n",
            encoding="utf-8",
        )
        print("PASS: customer-only identity rejected by Driver sign-in guard", flush=True)


def verify_offline_driver_offers_api(app) -> None:
    """Prove the protected offers contract without polling offers while Driver is offline.

    The synthetic Driver is deliberately pending approval and offline. The native
    app must not poll dispatch offers in that state, so this isolated backend
    preflight verifies the bearer-protected read directly and revokes its own
    temporary session before the Android journey begins.
    """
    headers = {"User-Agent": BACKEND_PREFLIGHT_USER_AGENT}
    with app.test_client() as client:
        login = client.post(
            "/api/mobile/v1/auth/login",
            headers=headers,
            json={
                "identifier": DRIVER_USERNAME,
                "password": DRIVER_PASSWORD,
                "client": "driver",
                "device_id": "driver-e2e-offers-probe-device",
                "device_name": "AFCON360 Driver E2E offers contract probe",
            },
        )
        login_payload = login.get_json(silent=True) or {}
        login_data = login_payload.get("data") if isinstance(login_payload, dict) else {}
        access_token = login_data.get("access_token") if isinstance(login_data, dict) else None
        if login.status_code != 200 or not access_token:
            raise AssertionError(
                "The backend-only Driver offers preflight could not establish a bearer session: "
                f"HTTP {login.status_code}, code={login_payload.get('code')!r}."
            )

        bearer_headers = {
            **headers,
            "Authorization": f"Bearer {access_token}",
        }
        response = client.get(
            "/api/mobile/v1/driver/offers",
            headers=bearer_headers,
        )
        payload = response.get_json(silent=True) or {}
        data = payload.get("data") if isinstance(payload, dict) else {}
        offers = data.get("offers") if isinstance(data, dict) else None
        if response.status_code != 200 or not isinstance(offers, list) or offers:
            raise AssertionError(
                "The authenticated pending/offline Driver offers endpoint did not return an empty list: "
                f"HTTP {response.status_code}, offers_is_list={isinstance(offers, list)}, "
                f"offers_count={len(offers) if isinstance(offers, list) else 'invalid'}."
            )

        logout = client.post(
            "/api/mobile/v1/auth/logout",
            headers=bearer_headers,
        )
        logout_payload = logout.get_json(silent=True) or {}
        logout_data = logout_payload.get("data") if isinstance(logout_payload, dict) else {}
        if logout.status_code != 200 or not (isinstance(logout_data, dict) and logout_data.get("revoked") is True):
            raise AssertionError(
                "The backend-only Driver offers preflight did not revoke its temporary session: "
                f"HTTP {logout.status_code}."
            )

    print("PASS: authenticated offline Driver offers API returns an empty list", flush=True)
    print("PASS: backend-only Driver offers preflight session revoked", flush=True)


def assert_evidence(app) -> None:
    from app.auth.mobile_tokens import _revoked_key
    from app.auth.sessions import ServerSession
    from app.extensions import db, redis_client
    from app.identity.models.user import User, Session as DeviceSession
    from app.transport.models import Booking, DriverProfile

    if not REQUEST_LOG.is_file():
        raise AssertionError("The Driver APK did not reach the disposable backend; request audit is missing.")

    records = []
    for line in REQUEST_LOG.read_text(encoding="utf-8").splitlines():
        parts = line.split("\t")
        if len(parts) == 3:
            status, method, path = parts
            records.append((int(status), method, path))

    def count_ok(method: str, path: str) -> int:
        return sum(
            status == 200 and actual_method == method and actual_path == path
            for status, actual_method, actual_path in records
        )

    boundary_summary_path = EVIDENCE / "driver-login-boundary-summary.json"
    boundary_summary = (
        json.loads(boundary_summary_path.read_text(encoding="utf-8"))
        if boundary_summary_path.is_file() else {}
    )
    customer_login_rejected = (
        boundary_summary.get("customer_rejected") is True
        and boundary_summary.get("http_status") == 403
        and boundary_summary.get("error_code") == "driver_profile_required"
    )
    driver_summary_path = EVIDENCE / "driver-profile-summary.json"
    offers_summary_path = EVIDENCE / "driver-offers-summary.json"
    trip_summary_path = EVIDENCE / "driver-active-trip-summary.json"
    earnings_summary_path = EVIDENCE / "driver-earnings-summary.json"

    summaries_present = all(
        path.is_file() for path in (
            driver_summary_path, offers_summary_path, trip_summary_path, earnings_summary_path
        )
    )
    profile_summary = json.loads(driver_summary_path.read_text(encoding="utf-8")) if driver_summary_path.is_file() else {}
    offers_summary = json.loads(offers_summary_path.read_text(encoding="utf-8")) if offers_summary_path.is_file() else {}
    trip_summary = json.loads(trip_summary_path.read_text(encoding="utf-8")) if trip_summary_path.is_file() else {}
    earnings_summary = json.loads(earnings_summary_path.read_text(encoding="utf-8")) if earnings_summary_path.is_file() else {}

    required = {
        "customer-only account rejected by Driver login guard": customer_login_rejected,
        "successful Driver password login": count_ok("POST", "/api/mobile/v1/auth/login") >= 1,
        "identity read on sign-in and after process restart": count_ok("GET", "/api/mobile/v1/auth/me") >= 2,
        "Driver profile/readiness API": count_ok("GET", "/api/mobile/v1/driver/me") >= 2,
        "Driver offers API": (
            offers_summary.get("http_status") == 200
            and offers_summary.get("offers_list_valid") is True
        ),
        "active-trip API": count_ok("GET", "/api/mobile/v1/driver/trips/active") >= 1,
        "Driver earnings API": count_ok("GET", "/api/mobile/v1/driver/earnings") >= 1,
        "Driver map configuration API": count_ok("GET", "/api/mobile/v1/driver/map-config") >= 1,
        "Driver demand heatmap API": count_ok("GET", "/api/mobile/v1/driver/demand/cells") >= 1,
        "Driver trip-history API": count_ok("GET", "/api/mobile/v1/driver/trips") >= 1,
        "Driver assignments API": count_ok("GET", "/api/mobile/v1/driver/assignments") >= 1,
        "Driver vehicle marketplace API": count_ok("GET", "/api/mobile/v1/driver/marketplace/vehicles") >= 1,
        "Driver notifications inbox API": count_ok("GET", "/api/mobile/v1/driver/notifications") >= 1,
        "Driver incident history API": count_ok("GET", "/api/mobile/v1/driver/incidents") >= 1,
        "server-side logout": count_ok("POST", "/api/mobile/v1/auth/logout") >= 1,
        "sanitized Driver API response evidence": summaries_present,
        "pending Driver remains not ready and offline": (
            profile_summary.get("driver_code") == DRIVER_CODE
            and profile_summary.get("compliance_status") == "pending_review"
            and profile_summary.get("is_online") is False
            and profile_summary.get("is_available") is False
            and profile_summary.get("go_live_ready") is False
        ),
        "new Driver has no offers": offers_summary.get("offers_count") == 0,
        "new Driver has no active trip": trip_summary.get("active_trip_present") is False,
        "new Driver has no captured earnings": earnings_summary.get("currency_groups") == 0,
    }

    with app.app_context():
        user = User.query.filter_by(username=DRIVER_USERNAME, email=DRIVER_EMAIL).one_or_none()
        if user is None:
            raise AssertionError("The synthetic Driver identity disappeared from the disposable database.")
        profile = DriverProfile.query.filter_by(user_id=user.id, driver_code=DRIVER_CODE).one_or_none()
        if profile is None:
            raise AssertionError("The synthetic Driver profile disappeared from the disposable database.")

        server_sessions = ServerSession.query.filter_by(user_id=user.public_id).all()
        device_sessions = DeviceSession.query.filter_by(user_id=user.id).all()
        required["server session revoked on logout"] = (
            bool(server_sessions) and all(row.is_revoked for row in server_sessions)
        )
        required["device session revoked on logout"] = (
            bool(device_sessions) and all(row.revoked_at is not None for row in device_sessions)
        )
        required["Redis mobile session revoked on logout"] = (
            bool(device_sessions) and all(
                bool(redis_client.client.exists(_revoked_key(row.session_id)))
                for row in device_sessions
            )
        )
        required["no Driver status/location/dispatch writes"] = not any(
            method == "POST" and path.startswith("/api/mobile/v1/driver/")
            for _status, method, path in records
        )
        required["no booking assigned to synthetic Driver"] = (
            Booking.query.filter_by(assigned_driver_id=profile.id, is_deleted=False).count() == 0
        )
        required["Driver profile left offline"] = (
            profile.is_online is False and profile.is_available is False
        )
        db.session.rollback()

    EVIDENCE.mkdir(parents=True, exist_ok=True)
    auth_failure_path = EVIDENCE / "auth-failures.tsv"
    auth_failure_codes = []
    if auth_failure_path.is_file():
        for line in auth_failure_path.read_text(encoding="utf-8").splitlines():
            parts = line.split("\t")
            if len(parts) >= 2 and parts[0].isdigit():
                item = {"status": int(parts[0]), "code": parts[1]}
                if len(parts) >= 4:
                    item["identifier_matches_expected_driver"] = parts[2] == "true"
                    item["resolved_identity_has_driver_profile"] = parts[3] == "true"
                auth_failure_codes.append(item)
    report = {
        "result": "passed" if all(required.values()) else "failed",
        "sanitized_login_failures": auth_failure_codes,
        "synthetic_driver": DRIVER_USERNAME,
        "driver_code": DRIVER_CODE,
        "checks": required,
        "backend_request_audit": [
            {"status": status, "method": method, "path": path}
            for status, method, path in records
        ],
        "production_backend_used": False,
        "production_database_used": False,
        "bookings_created": False,
        "money_moved": False,
        "driver_status_changed": False,
        "driver_location_published": False,
        "dispatch_actions_performed": False,
    }
    (EVIDENCE / "backend-e2e-report.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )

    for label, passed in required.items():
        print(f"{'PASS' if passed else 'FAIL'}: {label}", flush=True)

    if not all(required.values()):
        missing = [label for label, passed in required.items() if not passed]
        raise AssertionError("Driver authenticated journey did not prove: " + ", ".join(missing))


def main() -> None:
    command = sys.argv[1] if len(sys.argv) > 1 else "serve"
    app = build_app()

    if command == "seed":
        seed_test_accounts(app)
        verify_driver_only_login_guard(app)
        verify_offline_driver_offers_api(app)
    elif command == "serve":
        EVIDENCE.mkdir(parents=True, exist_ok=True)
        print("DRIVER_E2E_BACKEND_STARTING on 0.0.0.0:5000", flush=True)
        app.run(host="0.0.0.0", port=5000, debug=False, use_reloader=False, threaded=True)
    elif command == "assert":
        assert_evidence(app)
    else:
        raise SystemExit("Usage: mobile-driver-e2e-backend.py [seed|serve|assert]")


if __name__ == "__main__":
    main()
