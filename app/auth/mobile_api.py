"""Versioned bearer-only API for native AFCON360 clients."""
from __future__ import annotations

import json
import logging
import secrets
from datetime import datetime, timezone
from decimal import Decimal
from functools import wraps

from flask import Blueprint, current_app, g, jsonify, request
from flask_limiter.util import get_remote_address

from app.extensions import db, limiter
from app.auth.mobile_tokens import (
    ACCESS_TTL_SECONDS,
    REFRESH_TTL_SECONDS,
    _load_json,
    _redis,
    _resolve_record,
    _token_key,
    issue_mobile_tokens,
    load_mobile_bearer_context,
    mark_mobile_session_revoked,
    pop_mobile_mfa_challenge,
    require_mobile_context,
    rotate_mobile_refresh_token,
    store_rotated_access_token,
)

logger = logging.getLogger(__name__)
mobile_api_bp = Blueprint("mobile_api", __name__, url_prefix="/api/mobile/v1")


def _error(code: str, message: str, status: int):
    return jsonify({"success": False, "code": code, "message": message}), status


def _device_fields(data: dict) -> tuple[str, str]:
    device_id = str(data.get("device_id") or "").strip()
    device_name = " ".join(str(data.get("device_name") or "AFCON360 mobile device").split())[:80]
    if not device_id or len(device_id) < 8 or len(device_id) > 128:
        raise ValueError("device_id must be a stable installation identifier (8–128 characters)")
    return device_id, device_name


def _validate_mobile_client(value: str) -> str:
    client = str(value or "").strip().lower()
    if client not in {"user", "driver"}:
        raise ValueError("client must be 'user' or 'driver'")
    return client


def _verify_login_eligibility(user, client: str):
    if not getattr(user, "is_active", True) or getattr(user, "is_deleted", False):
        return _error("account_inactive", "This AFCON360 account is not active.", 403)

    if current_app.config.get("REQUIRE_EMAIL_VERIFICATION", False):
        if not bool(getattr(user, "email_verified", False) or getattr(user, "is_verified", False)):
            return _error("email_verification_required", "Verify your email address before signing in to the mobile app.", 403)

    if client == "driver":
        from app.transport.models import DriverProfile
        profile = DriverProfile.query.filter_by(user_id=user.id, is_deleted=False).first()
        if profile is None:
            return _error("driver_profile_required", "This account does not have an AFCON360 Driver profile.", 403)

    if getattr(user, "is_app_owner", lambda: False)():
        from app.auth.security_policy import owner_mfa_required
        if owner_mfa_required():
            from app.identity.models.user import MFASecret
            enrolled = MFASecret.query.filter_by(
                user_id=user.id, mfa_type="totp", is_active=True
            ).first()
            if enrolled is None:
                return _error(
                    "owner_mfa_enrollment_required",
                    "This privileged account must enroll and verify an authenticator before mobile sign-in.",
                    403,
                )
    return None


def _active_server_session(session_id: str):
    from app.auth.sessions import ServerSession
    now = datetime.now(timezone.utc)
    row = ServerSession.query.filter_by(session_id=session_id, is_revoked=False).first()
    if row is None:
        return False
    expiry = row.expires_at
    if expiry.tzinfo is None:
        expiry = expiry.replace(tzinfo=timezone.utc)
    return expiry > now


def _complete_native_login(user, client: str, device_id: str, device_name: str, server_session_id: str):
    from app.auth.sessions import start_device_session, revoke_session
    from app.identity.models.user import Session as DeviceSession

    if not _active_server_session(server_session_id):
        return _error(
            "session_storage_unavailable",
            "AFCON360 could not establish a secure sign-in session. Please try again.",
            503,
        )

    device_session_id = start_device_session(
        user,
        request.remote_addr,
        request.headers.get("User-Agent", "AFCON360 Native"),
        device_id=device_id,
        device_name=device_name,
    )
    if not device_session_id:
        try:
            revoke_session(server_session_id)
        except Exception:
            logger.exception("Could not revoke server session after device-session failure")
        return _error("session_storage_unavailable", "AFCON360 could not register this device session.", 503)

    try:
        credentials = issue_mobile_tokens(
            user_public_id=user.public_id,
            session_id=device_session_id,
            server_session_id=server_session_id,
            client=client,
            device_id=device_id,
        )
        stored = DeviceSession.query.filter_by(
            session_id=device_session_id,
            user_id=user.id,
            revoked_at=None,
        ).first()
        if stored is None:
            raise RuntimeError("Device session was not persisted")
        # The existing ServerSession is the durable revocation record used by
        # Auth. Its expiry must cover the Identity device-session lifetime or
        # native refresh would be cut off by the shorter browser default (12h).
        from app.auth.sessions import ServerSession
        server_record = ServerSession.query.filter_by(
            session_id=server_session_id,
            user_id=str(user.public_id),
            is_revoked=False,
        ).first()
        if server_record is None:
            raise RuntimeError("Native server session was not persisted")
        server_record.expires_at = stored.expires_at
        db.session.commit()
    except Exception:
        logger.exception("Native token issuance failed")
        try:
            from app.auth.sessions import revoke_device_session, revoke_session
            revoke_device_session(device_session_id, user_id=user.id, reason="mobile_token_issue_failed")
            revoke_session(server_session_id)
            mark_mobile_session_revoked(device_session_id)
        except Exception:
            logger.exception("Native session cleanup failed")
        return _error("session_storage_unavailable", "AFCON360 could not issue secure mobile credentials.", 503)

    return jsonify({
        "success": True,
        "data": {
            **credentials,
            "user": {
                "public_id": str(user.public_id),
                "username": user.username,
                "display_name": getattr(user, "display_name", None),
                "email": user.email,
                "client": client,
            },
        },
    }), 200


def _bearer_required(expected_client: str | None = None):
    def decorate(fn):
        @wraps(fn)
        def wrapped(*args, **kwargs):
            context, error = require_mobile_context(expected_client)
            if error:
                return error
            g._afcon360_mobile_auth_context = context
            return fn(*args, **kwargs)
        return wrapped
    return decorate


@mobile_api_bp.post("/auth/login")
@limiter.limit("5 per minute", key_func=get_remote_address)
def mobile_login():
    data = request.get_json(silent=True) or {}
    identifier = str(data.get("identifier") or data.get("username") or data.get("email") or "").strip()[:255]
    password = data.get("password")
    try:
        client = _validate_mobile_client(data.get("client"))
        device_id, device_name = _device_fields(data)
    except ValueError as exc:
        return _error("invalid_request", str(exc), 400)

    if not identifier or not isinstance(password, str) or not password or len(password) > 128:
        return _error("invalid_credentials", "Enter your AFCON360 username/email and password.", 400)

    from app.auth.services import authenticate_user, AuthResult
    result, payload = authenticate_user(
        identifier=identifier,
        password=password,
        ip=request.remote_addr,
        user_agent=request.headers.get("User-Agent", "AFCON360 Native"),
    )
    if result == AuthResult.MFA_REQUIRED:
        user = payload.get("user")
        if user is None:
            return _error("invalid_credentials", "Invalid username/email or password.", 401)
        eligible = _verify_login_eligibility(user, client)
        if eligible:
            return eligible
        mfa_type = str(payload.get("mfa_type") or "").lower()
        if mfa_type != "totp":
            return _error(
                "mfa_method_unsupported",
                "This account uses an MFA method that is not supported by native sign-in yet. Use the AFCON360 website to update its authenticator method.",
                422,
            )
        challenge = secrets.token_urlsafe(40)
        challenge_record = {
            "user_public_id": str(user.public_id),
            "client": client,
            "device_id": device_id,
            "device_name": device_name,
            "mfa_type": "totp",
            "created_at": int(datetime.now(timezone.utc).timestamp()),
        }
        _redis().setex(
            "afcon360:mobile:mfa:" + __import__("hashlib").sha256(challenge.encode()).hexdigest(),
            300,
            json.dumps(challenge_record, separators=(",", ":")),
        )
        return jsonify({
            "success": True,
            "mfa_required": True,
            "challenge_token": challenge,
            "mfa_type": "totp",
            "expires_in": 300,
        }), 202

    if result != AuthResult.SUCCESS or not payload or not payload.get("user"):
        code = "account_locked" if result == AuthResult.LOCKED else "invalid_credentials"
        status = 423 if result == AuthResult.LOCKED else 401
        return _error(code, "Invalid username/email or password, or the account is temporarily unavailable.", status)

    user = payload["user"]
    eligible = _verify_login_eligibility(user, client)
    if eligible:
        try:
            from app.auth.sessions import revoke_session
            revoke_session(payload.get("session_id"))
        except Exception:
            logger.exception("Could not revoke blocked native login's provisional server session")
        return eligible

    # Mirror the web flow's enforced-owner-MFA reconciliation: if an owner
    # already has TOTP but the mfa_enabled flag is stale, fix the flag, revoke
    # the provisional session and require a fresh password + TOTP challenge.
    if getattr(user, "is_app_owner", lambda: False)():
        from app.auth.security_policy import owner_mfa_required
        if owner_mfa_required() and not getattr(user, "mfa_enabled", False):
            user.mfa_enabled = True
            db.session.commit()
            try:
                from app.auth.sessions import revoke_session
                revoke_session(payload.get("session_id"))
            except Exception:
                logger.exception("Could not revoke stale owner session after MFA reconciliation")
            return _error(
                "mfa_reauthentication_required",
                "Authenticator enrollment is confirmed. Sign in again and enter the current TOTP code.",
                401,
            )

    return _complete_native_login(
        user,
        client,
        device_id,
        device_name,
        str(payload.get("session_id") or ""),
    )


@mobile_api_bp.post("/auth/mfa/verify")
@limiter.limit("5 per minute", key_func=get_remote_address)
def mobile_mfa_verify():
    data = request.get_json(silent=True) or {}
    challenge = str(data.get("challenge_token") or "").strip()
    code = str(data.get("code") or "").strip()
    if not challenge or len(challenge) > 256 or not code or len(code) > 16:
        return _error("invalid_mfa_challenge", "Enter the current authenticator code.", 400)

    try:
        challenge_data = pop_mobile_mfa_challenge(challenge)
    except Exception:
        logger.exception("Native MFA challenge store unavailable")
        return _error("auth_service_unavailable", "Sign-in is temporarily unavailable. Try again.", 503)
    if not challenge_data or challenge_data.get("mfa_type") != "totp":
        return _error("invalid_mfa_challenge", "This sign-in challenge has expired or was already used.", 401)

    from app.identity.models.user import User
    user = User.query.filter_by(public_id=challenge_data.get("user_public_id")).first()
    if user is None:
        return _error("invalid_mfa_challenge", "This sign-in challenge is no longer valid.", 401)
    eligible = _verify_login_eligibility(user, challenge_data.get("client"))
    if eligible:
        return eligible

    from app.auth.routes import _verify_mfa_token
    if not _verify_mfa_token(user, code, backup_code=(len(code) == 8)):
        return _error("mfa_verification_failed", "The authenticator code is invalid or has expired.", 401)

    from app.auth.sessions import start_server_session
    server_session_id = start_server_session(
        str(user.public_id),
        request.remote_addr,
        request.headers.get("User-Agent", "AFCON360 Native"),
    )
    if not _active_server_session(server_session_id):
        return _error("session_storage_unavailable", "AFCON360 could not establish a secure session.", 503)

    return _complete_native_login(
        user,
        challenge_data["client"],
        challenge_data["device_id"],
        challenge_data["device_name"],
        server_session_id,
    )


@mobile_api_bp.post("/auth/refresh")
@limiter.limit("20 per minute", key_func=get_remote_address)
def mobile_refresh():
    data = request.get_json(silent=True) or {}
    old_refresh = str(data.get("refresh_token") or "").strip()
    if not old_refresh or len(old_refresh) > 256:
        return _error("refresh_invalid", "A valid refresh credential is required.", 401)
    try:
        redis = _redis()
        old_record = _load_json(redis.get(_token_key("refresh", old_refresh)))
        if old_record is None or old_record.get("token_type") != "refresh":
            used_record = _load_json(redis.get(_token_key("refresh-used", old_refresh)))
            if used_record:
                from app.auth.sessions import revoke_device_session, revoke_session
                session_id = str(used_record.get("session_id") or "")
                server_id = str(used_record.get("server_session_id") or "")
                if session_id:
                    try:
                        revoke_device_session(session_id, reason="refresh_token_reuse")
                        mark_mobile_session_revoked(session_id)
                    except Exception:
                        logger.exception("Failed to revoke device session after refresh-token replay")
                if server_id:
                    try:
                        revoke_session(server_id)
                    except Exception:
                        logger.exception("Failed to revoke server session after refresh-token replay")
                return _error("refresh_reuse_detected", "This device session was revoked because an old refresh token was reused. Sign in again.", 401)
            return _error("refresh_invalid", "The refresh credential is invalid or expired.", 401)

        resolved = _resolve_record(old_record)
        if resolved is None:
            return _error("refresh_invalid", "The device session is expired or has been revoked.", 401)

        # Extend the existing Identity device session using its canonical
        # sliding-expiry/90-day-cap policy, then keep ServerSession aligned.
        from app.auth.sessions import ServerSession, touch_device_session
        from app.identity.models.user import Session as DeviceSession
        touch_device_session(str(old_record.get("session_id")))
        device_record = DeviceSession.query.filter_by(
            session_id=str(old_record.get("session_id")),
            user_id=resolved["user"].id,
            revoked_at=None,
        ).first()
        server_record = ServerSession.query.filter_by(
            session_id=str(old_record.get("server_session_id")),
            user_id=str(resolved["user"].public_id),
            is_revoked=False,
        ).first()
        if device_record is None or server_record is None:
            return _error("refresh_invalid", "The device session is expired or has been revoked.", 401)
        if server_record.expires_at != device_record.expires_at:
            server_record.expires_at = device_record.expires_at
            db.session.commit()

        new_access = secrets.token_urlsafe(48)
        new_refresh = secrets.token_urlsafe(64)
        new_record = dict(old_record, token_type="refresh", issued_at=int(datetime.now(timezone.utc).timestamp()))
        new_access_record = dict(old_record, token_type="access", issued_at=int(datetime.now(timezone.utc).timestamp()))
        rotation_status = rotate_mobile_refresh_token(
            old_refresh,
            new_refresh_token=new_refresh,
            refresh_record=new_record,
        )
        if rotation_status == -1:
            from app.auth.sessions import revoke_device_session, revoke_session
            session_id = str(old_record.get("session_id") or "")
            server_id = str(old_record.get("server_session_id") or "")
            try:
                revoke_device_session(session_id, reason="refresh_token_reuse")
                mark_mobile_session_revoked(session_id)
            except Exception:
                logger.exception("Failed to revoke device session after racing refresh replay")
            try:
                revoke_session(server_id)
            except Exception:
                logger.exception("Failed to revoke server session after racing refresh replay")
            return _error("refresh_reuse_detected", "This device session was revoked because an old refresh token was reused. Sign in again.", 401)
        if rotation_status != 1:
            return _error("refresh_invalid", "The refresh credential is invalid, expired or revoked.", 401)

        store_rotated_access_token(new_access, new_access_record)
        return jsonify({
            "success": True,
            "data": {
                "token_type": "Bearer",
                "access_token": new_access,
                "expires_in": ACCESS_TTL_SECONDS,
                "refresh_token": new_refresh,
                "refresh_expires_in": REFRESH_TTL_SECONDS,
            },
        }), 200
    except Exception:
        logger.exception("Native refresh failed")
        return _error("auth_service_unavailable", "AFCON360 could not refresh this session. Try again.", 503)


@mobile_api_bp.post("/auth/logout")
@_bearer_required()
def mobile_logout():
    context = g._afcon360_mobile_auth_context
    user = context["user"]
    record = context["record"]
    session_id = str(record["session_id"])
    server_id = str(record["server_session_id"])
    from app.auth.sessions import revoke_device_session, revoke_session

    try:
        revoked = revoke_device_session(
            session_id,
            user_id=user.id,
            reason="mobile_logout",
        )
        try:
            revoke_session(server_id, revoked_by_user_id=user.id)
        except Exception:
            logger.exception("Could not revoke native login's server-session audit record")
        mark_mobile_session_revoked(session_id)
    except Exception:
        logger.exception("Native device logout failed")
        return _error("logout_failed", "AFCON360 could not revoke this device session. Please retry.", 503)
    return jsonify({"success": True, "data": {"revoked": bool(revoked)}}), 200


@mobile_api_bp.post("/auth/account-deletion")
@_bearer_required()
def mobile_account_deletion():
    """In-app account deletion backed by the shared account-closure service."""
    data = request.get_json(silent=True) or {}
    user = g._afcon360_mobile_auth_context["user"]
    try:
        from app.auth.account_deletion_service import (
            AccountDeletionError,
            request_account_deletion,
        )
        result = request_account_deletion(
            user=user,
            password=data.get("password"),
            confirmation=data.get("confirmation"),
            mfa_code=str(data.get("mfa_code") or "").strip(),
            ip_address=request.remote_addr,
            user_agent=request.headers.get("User-Agent"),
        )
    except AccountDeletionError as exc:
        return _error(exc.code, exc.message, exc.status_code)
    except Exception:
        db.session.rollback()
        logger.exception("Native account deletion service failed unexpectedly")
        return _error(
            "account_deletion_failed",
            "AFCON360 could not complete the account deletion request. Please contact support.",
            503,
        )
    return jsonify({"success": True, "data": result}), 200


@mobile_api_bp.get("/auth/me")
@_bearer_required()
def mobile_me():
    context = g._afcon360_mobile_auth_context
    user = context["user"]
    from app.auth.context import get_available_contexts
    contexts = []
    try:
        for item in get_available_contexts(user):
            contexts.append({
                "type": item.type.value,
                "public_id": item.public_id,
                "label": item.label,
                "role": item.role,
            })
    except Exception:
        logger.exception("Could not resolve mobile Identity contexts")
        return _error("identity_unavailable", "AFCON360 could not resolve your current account access.", 503)
    return jsonify({
        "success": True,
        "data": {
            "public_id": str(user.public_id),
            "username": user.username,
            "display_name": getattr(user, "display_name", None),
            "email": user.email,
            "email_verified": bool(getattr(user, "email_verified", False) or getattr(user, "is_verified", False)),
            "mfa_enabled": bool(getattr(user, "mfa_enabled", False)),
            "client": context["record"].get("client"),
            "contexts": contexts,
        },
    }), 200


@mobile_api_bp.post("/transport/ride-options")
@limiter.limit("30 per minute", key_func=get_remote_address)
@_bearer_required("user")
def mobile_ride_options():
    """Use the canonical quote-only Transport resource; no matching is started."""
    from app.transport.api.ride_options_routes import RideOptionsResource
    return RideOptionsResource().post()


@mobile_api_bp.post("/transport/payment-methods/options")
@_bearer_required("user")
def mobile_payment_method_options():
    data = request.get_json(silent=True) or {}
    currency = str(data.get("currency") or "").strip().upper()
    amount = data.get("amount")
    if not currency or amount is None:
        return _error("payment_options_incomplete", "A fare currency and amount are required.", 400)
    try:
        from app.transport.services.payment_methods import get_available_transport_payment_methods
        methods = get_available_transport_payment_methods(
            user_id=g._afcon360_mobile_auth_context["user"].id,
            currency_code=currency,
            amount=amount,
            payment_timing="pay_on_completion",
        )
    except Exception:
        logger.exception("Could not resolve Wallet-certified native payment methods")
        return _error("payment_methods_unavailable", "AFCON360 could not load available payment methods.", 503)
    return jsonify({
        "success": True,
        "data": {
            "currency": currency,
            "payment_methods": methods,
        },
    }), 200


@mobile_api_bp.get("/activity")
@_bearer_required("user")
def mobile_user_activity():
    from app.transport.models import Booking, RideRequest, SearchCycle
    from app.transport.services.ride_request_service import serialize_request
    user = g._afcon360_mobile_auth_context["user"]
    rows = (
        RideRequest.query
        .filter_by(user_id=user.id, is_deleted=False)
        .order_by(RideRequest.created_at.desc())
        .limit(30)
        .all()
    )
    items = []
    for ride_request in rows:
        cycle = (
            SearchCycle.query
            .filter_by(ride_request_id=ride_request.id, is_deleted=False)
            .order_by(SearchCycle.cycle_number.desc())
            .first()
        )
        if cycle is None:
            continue
        item = serialize_request(ride_request, cycle)
        item["booking_reference"] = ride_request.public_id
        item["converted"] = ride_request.status == "converted"
        item["terminal_reason"] = cycle.terminal_reason
        if item["converted"]:
            booking = Booking.query.filter_by(
                ride_request_id=ride_request.id,
                is_deleted=False,
            ).first()
            if booking is not None:
                item["booking_status"] = str(getattr(booking.status, "value", booking.status))
                driver = booking.driver
                driver_user = getattr(driver, "user", None) if driver else None
                item["driver"] = ({
                    "display_name": getattr(driver_user, "display_name", None) or driver.driver_code,
                    "rating": float(driver.average_rating or 0),
                } if driver else None)
                vehicle = booking.vehicle
                item["vehicle"] = ({
                    "make": vehicle.make,
                    "model": vehicle.model,
                    "license_plate": vehicle.license_plate,
                } if vehicle else None)
                item["payment"] = {
                    "method": booking.payment_method,
                    "status": str(getattr(booking.payment_status, "value", booking.payment_status)),
                }
        items.append(item)
    return jsonify({"success": True, "data": {"items": items}}), 200


@mobile_api_bp.post("/transport/ride-requests")
@_bearer_required("user")
def mobile_create_ride_request():
    """Native rider command: same quote, invoice, idempotency and dispatch authority."""
    from app.auth.decorators import require_profile_completion
    from app.auth.kyc_compliance import require_kyc_tier
    from app.transport.services.ride_request_service import (
        IdempotencyConflictError,
        RideRequestService,
        serialize_request,
    )
    from app.utils.exceptions import ValidationError, ServiceUnavailableError

    data = request.get_json(silent=True) or {}
    # The native contract uses explicit resolved route objects and the
    # server-signed quote; it deliberately accepts no client fare calculation.
    required = ("pickup", "dropoff", "fare_quote_token", "confirmed_fare_amount", "payment_method", "idempotency_key")
    if any(data.get(field) is None for field in required):
        return _error("ride_request_incomplete", "Pickup, destination, signed fare, payment choice and idempotency key are required.", 400)

    # Native requests do not have a browser session flag. Re-check the
    # canonical Profile and KYC records directly and return JSON gate errors.
    from flask_login import current_user
    from app.profile.models import get_profile_by_user
    from app.auth.kyc_compliance import calculate_kyc_tier
    user = current_user
    try:
        profile = get_profile_by_user(user)
        if profile is None or not bool(getattr(profile, "profile_completed", False)):
            return _error(
                "profile_completion_required",
                "Complete your AFCON360 profile before requesting a ride.",
                403,
            )
        kyc_info = calculate_kyc_tier(user.id)
        if int(kyc_info.get("tier", 0)) < 2:
            return jsonify({
                "success": False,
                "code": "kyc_upgrade_required",
                "message": "Complete the required identity verification before requesting a ride.",
                "data": {
                    "required_tier": 2,
                    "current_tier": int(kyc_info.get("tier", 0)),
                    "missing_requirements": kyc_info.get("missing_requirements", []),
                },
            }), 403
    except Exception:
        db.session.rollback()
        logger.exception("Native ride commitment gate failed closed")
        return _error("booking_gate_unavailable", "AFCON360 could not verify booking eligibility.", 503)

    try:
        result = RideRequestService.create_request(user.id, data)
    except IdempotencyConflictError as exc:
        return _error("idempotency_conflict", exc.message, 409)
    except ValidationError as exc:
        return _error("ride_request_rejected", exc.message, 400)
    except ServiceUnavailableError:
        return _error("ride_request_unavailable", "Ride request service is temporarily unavailable.", 503)
    except Exception:
        db.session.rollback()
        logger.exception("Native ride-request creation failed")
        return _error("ride_request_unavailable", "Ride request service is temporarily unavailable.", 503)

    ride_request = result["request"]
    cycle = result["cycle"]
    replayed = bool(result.get("replayed"))
    dispatch_pending = False
    if not replayed:
        try:
            from app.transport.services.ride_request_dispatch_service import RideRequestDispatchService
            RideRequestDispatchService.start_search(ride_request.public_id)
        except Exception:
            dispatch_pending = True
            logger.exception("Native ride request %s persisted; dispatch deferred to recovery", ride_request.public_id)

    return jsonify({
        "success": True,
        "data": serialize_request(ride_request, cycle),
        "booking_reference": ride_request.public_id,
        "replayed": replayed,
        "dispatch_pending": dispatch_pending,
    }), (200 if replayed else 201)


@mobile_api_bp.get("/transport/ride-requests/<string:request_public_id>")
@_bearer_required("user")
def mobile_get_ride_request(request_public_id):
    from app.transport.api.ride_request_routes import RideRequestDetailResource
    return RideRequestDetailResource().get(request_public_id)


@mobile_api_bp.get("/transport/bookings/<string:booking_reference>")
@_bearer_required("user")
def mobile_get_booking(booking_reference):
    from app.transport.api.booking_routes import BookingDetailResource
    return BookingDetailResource().get(booking_reference)


@mobile_api_bp.post("/transport/rides/<string:booking_reference>/payment/settle-wallet")
@_bearer_required("user")
def mobile_settle_wallet(booking_reference):
    from app.transport.api.booking_routes import RiderWalletSettlementResource
    return RiderWalletSettlementResource().post(booking_reference)


def _current_driver():
    from app.transport.api.driver_routes import _current_driver_profile
    return _current_driver_profile()


@mobile_api_bp.get("/driver/me")
@_bearer_required("driver")
def mobile_driver_me():
    profile, error, status = _current_driver()
    if error:
        return jsonify(error), status
    from app.transport.services.go_live_service import can_go_live
    try:
        checklist = can_go_live(profile)
        readiness = checklist.to_dict()
    except Exception:
        logger.exception("Driver readiness check unavailable")
        readiness = {"ready": False, "items": []}
    return jsonify({
        "success": True,
        "data": {
            "driver_code": profile.driver_code,
            "verification_tier": str(getattr(profile.verification_tier, "value", profile.verification_tier)),
            "compliance_status": str(getattr(profile.compliance_status, "value", profile.compliance_status)),
            "is_online": bool(profile.is_online),
            "is_available": bool(profile.is_available),
            "go_live": readiness,
        },
    }), 200


@mobile_api_bp.get("/driver/offers")
@_bearer_required("driver")
def mobile_driver_offers():
    from app.transport.api.driver_routes import DriverOfferListResource
    return DriverOfferListResource().get()


@mobile_api_bp.post("/driver/offers/<string:booking_reference>/accept")
@_bearer_required("driver")
def mobile_driver_accept_offer(booking_reference):
    from app.transport.api.driver_routes import DriverOfferAcceptResource
    return DriverOfferAcceptResource().post(booking_reference)


@mobile_api_bp.post("/driver/offers/<string:booking_reference>/decline")
@_bearer_required("driver")
def mobile_driver_decline_offer(booking_reference):
    from app.transport.api.driver_routes import DriverOfferDeclineResource
    return DriverOfferDeclineResource().post(booking_reference)


@mobile_api_bp.post("/driver/status")
@_bearer_required("driver")
def mobile_driver_status():
    profile, error, status = _current_driver()
    if error:
        return jsonify(error), status
    from app.transport.api.driver_routes import DriverStatusResource
    return DriverStatusResource().post(profile.id)


@mobile_api_bp.post("/driver/location")
@_bearer_required("driver")
def mobile_driver_location():
    profile, error, status = _current_driver()
    if error:
        return jsonify(error), status
    from app.transport.api.driver_routes import DriverLocationResource
    return DriverLocationResource().post(profile.id)


@mobile_api_bp.get("/driver/trips/active")
@_bearer_required("driver")
def mobile_driver_active_trip():
    from app.transport.models import Booking
    from app.utils.enums import BookingStatus
    profile, error, status = _current_driver()
    if error:
        return jsonify(error), status
    from sqlalchemy import and_, or_
    active_statuses = [
        BookingStatus.ASSIGNED,
        BookingStatus.DRIVER_EN_ROUTE,
        BookingStatus.PICKUP_ARRIVED,
        BookingStatus.IN_PROGRESS,
    ]
    # Completing a trip releases the vehicle/dispatch assignment. Keep a
    # cash-paid trip visible only to the driver who actually completed it
    # until Wallet records the explicit cash receipt; completion alone is not
    # proof that the rider handed over cash.
    completed_cash_receipt = and_(
        Booking.status == BookingStatus.COMPLETED,
        Booking.payment_method == "cash",
        Booking.payment_status == PaymentStatus.PENDING,
        Booking.booking_metadata["completed_by_driver_profile_id"].astext == str(profile.id),
    )
    booking = Booking.query.filter(
        Booking.is_deleted.is_(False),
        or_(
            and_(
                Booking.assigned_driver_id == profile.id,
                Booking.status.in_(active_statuses),
            ),
            completed_cash_receipt,
        ),
    ).order_by(Booking.updated_at.desc()).first()
    if booking is None:
        return jsonify({"success": True, "data": None}), 200

    def _point(value):
        if not isinstance(value, dict):
            return None
        return {
            "latitude": value.get("latitude"),
            "longitude": value.get("longitude"),
            "address": value.get("address") or value.get("display_name"),
        }
    return jsonify({
        "success": True,
        "data": {
            "booking_reference": booking.booking_reference,
            "status": str(getattr(booking.status, "value", booking.status)),
            "pickup": _point(booking.pickup_location),
            "dropoff": _point(booking.dropoff_location),
            "pickup_time": booking.pickup_time.isoformat() if booking.pickup_time else None,
            "passenger_count": booking.passenger_count,
            "payment_method": booking.payment_method,
            "payment_status": str(getattr(booking.payment_status, "value", booking.payment_status)),
            "fare_amount": str(booking.final_price or booking.total_amount or 0),
            "currency": str(getattr(booking.currency, "value", booking.currency)),
        },
    }), 200


@mobile_api_bp.post("/driver/trips/<string:booking_reference>/status")
@_bearer_required("driver")
def mobile_driver_trip_status(booking_reference):
    from app.transport.api.driver_routes import DriverTripReferenceResource
    return DriverTripReferenceResource().post(booking_reference)


@mobile_api_bp.post("/driver/trips/<string:booking_reference>/payment/confirm-cash")
@_bearer_required("driver")
def mobile_driver_cash_receipt(booking_reference):
    from app.transport.api.driver_routes import DriverTripPaymentResource
    return DriverTripPaymentResource().post(booking_reference)


@mobile_api_bp.get("/driver/earnings")
@_bearer_required("driver")
def mobile_driver_earnings():
    from app.transport.models import Booking
    from app.utils.enums import BookingStatus, PaymentStatus
    from decimal import Decimal
    from sqlalchemy import func
    profile, error, status = _current_driver()
    if error:
        return jsonify(error), status
    rate = profile.commission_rate
    try:
        rate_pct = float(rate) if rate is not None else 15.0
    except (TypeError, ValueError):
        rate_pct = 15.0
    rate_pct = min(100.0, max(0.0, rate_pct))
    rows = (
        db.session.query(Booking.currency, func.sum(Booking.final_price))
        .filter(
            Booking.assigned_driver_id == profile.id,
            Booking.status == BookingStatus.COMPLETED,
            Booking.payment_status == PaymentStatus.CAPTURED,
            Booking.is_deleted.is_(False),
        )
        .group_by(Booking.currency)
        .all()
    )
    earnings = []
    for currency, gross in rows:
        code = str(getattr(currency, "value", currency))
        gross_amount = Decimal(str(gross or 0))
        net_amount = (gross_amount * (Decimal("1") - Decimal(str(rate_pct)) / Decimal("100"))).quantize(Decimal("0.01"))
        earnings.append({
            "currency": code,
            "gross_captured": str(gross_amount.quantize(Decimal("0.01"))),
            "driver_earnings": str(net_amount),
            "platform_commission_rate": str(rate_pct),
        })
    return jsonify({"success": True, "data": {"by_currency": earnings}}), 200
