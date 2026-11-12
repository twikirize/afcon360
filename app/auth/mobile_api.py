"""Versioned bearer-only API for native AFCON360 clients."""
from __future__ import annotations

import hashlib
import json
import logging
import secrets
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from functools import wraps

from flask import Blueprint, current_app, g, jsonify, request, url_for
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


def _mobile_password_reset_rate_key():
    data = request.get_json(silent=True) or {}
    identifier = str(data.get("identifier") or "").strip().lower()
    digest = hashlib.sha256(identifier.encode("utf-8")).hexdigest()
    return f"{get_remote_address()}:{digest}"


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




def _start_native_sms_mfa(user):
    """Send a hashed, short-lived sign-in OTP to the user's verified phone.

    Native SMS MFA is enabled only when the account has a verified E.164 phone
    number and an owner-configured real SMS provider. It never falls back to
    console logging or an unverified contact address.
    """
    from app.auth.otp_service import OTPService

    user_id = str(user.id)
    OTPService.invalidate_otp(user_id, "2fa_login")

    phone = str(getattr(user, "phone", "") or "").strip()
    if not bool(getattr(user, "phone_verified", False)):
        return None, ("sms_mfa_phone_unverified", "Verify your phone number before using SMS sign-in.", 403)
    if not phone.startswith("+") or not phone[1:].isdigit() or not 8 <= len(phone[1:]) <= 15:
        return None, ("sms_mfa_phone_invalid", "Your verified phone number must be stored in international format. Update it in AFCON360 account settings.", 422)

    try:
        redis = _redis()
        throttle_key = "afcon360:mobile:sms-mfa-send:" + hashlib.sha256(
            str(user.public_id).encode("utf-8")
        ).hexdigest()
        if not redis.set(throttle_key, "1", ex=60, nx=True):
            return None, ("sms_mfa_rate_limited", "A sign-in code was requested recently. Wait a minute before trying again.", 429)

        from app.auth.config_model import AuthConfiguration
        from app.notifications.sms_service import SMSService

        auth_config = AuthConfiguration.get_config()
        provider = auth_config.get_sms_provider_for_phone(phone) if auth_config else None
        if provider not in {"twilio", "africa_talking", "africas_talking"}:
            return None, ("sms_mfa_unavailable", "SMS sign-in is not configured for your verified phone number. Use your authenticator app or contact AFCON360 support.", 503)

        code = OTPService.generate_otp(length=6)
        if not OTPService.store_otp(user_id, code, purpose="2fa_login", ttl=300):
            return None, ("sms_mfa_unavailable", "AFCON360 could not prepare a secure sign-in code. Try again.", 503)

        delivery = SMSService(provider=provider, auth_config=auth_config).send_message(
            phone_number=phone,
            message=f"Your AFCON360 sign-in code is {code}. It expires in 5 minutes. Do not share it.",
        )
        if not isinstance(delivery, dict) or not bool(delivery.get("success")):
            OTPService.invalidate_otp(user_id, "2fa_login")
            logger.warning("Native SMS MFA delivery failed for user %s", user.public_id)
            return None, ("sms_mfa_delivery_failed", "AFCON360 could not deliver your sign-in code. Check your phone connection or try again later.", 503)

        hint = f"{phone[:4]}••••{phone[-2:]}"
        return hint, None
    except Exception:
        OTPService.invalidate_otp(user_id, "2fa_login")
        logger.exception("Native SMS MFA could not be started for user %s", getattr(user, "public_id", "unknown"))
        return None, ("sms_mfa_unavailable", "SMS sign-in is temporarily unavailable. Please try again later.", 503)


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
            # Flask-Login normally prefers a browser session cookie over a
            # request_loader identity. A native caller must be authenticated
            # as exactly the bearer-token owner even if it also sends a stale
            # or foreign browser cookie. Pin current_user for this request.
            g._login_user = context["user"]
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
        sms_phone_hint = None
        if mfa_type == "sms":
            sms_phone_hint, sms_error = _start_native_sms_mfa(user)
            if sms_error:
                code, message, status = sms_error
                return _error(code, message, status)
        elif mfa_type != "totp":
            return _error(
                "mfa_method_unsupported",
                "This account uses an MFA method that is not supported by native sign-in yet. Use an authenticator app or contact AFCON360 support.",
                422,
            )

        challenge = secrets.token_urlsafe(40)
        challenge_record = {
            "user_public_id": str(user.public_id),
            "client": client,
            "device_id": device_id,
            "device_name": device_name,
            "mfa_type": mfa_type,
            "sms_phone_hint": sms_phone_hint,
            "created_at": int(datetime.now(timezone.utc).timestamp()),
        }
        try:
            _redis().setex(
                "afcon360:mobile:mfa:" + hashlib.sha256(challenge.encode()).hexdigest(),
                300,
                json.dumps(challenge_record, separators=(",", ":")),
            )
        except Exception:
            if mfa_type == "sms":
                from app.auth.otp_service import OTPService
                OTPService.invalidate_otp(str(user.id), "2fa_login")
            logger.exception("Could not store native MFA challenge")
            return _error("auth_service_unavailable", "Sign-in is temporarily unavailable. Try again.", 503)

        response = {
            "success": True,
            "mfa_required": True,
            "challenge_token": challenge,
            "mfa_type": mfa_type,
            "expires_in": 300,
        }
        if sms_phone_hint:
            response["destination_hint"] = sms_phone_hint
        return jsonify(response), 202

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


@mobile_api_bp.post("/auth/register")
@limiter.limit("10 per minute", key_func=get_remote_address)
def mobile_register():
    """Create an AFCON360 User account using the canonical web registration services.

    The native client never stores a password server-side. If the owner policy
    requires email verification, only the existing pending-registration OTP
    service may create the account after a valid code is submitted.
    """
    data = request.get_json(silent=True) or {}
    username = str(data.get("username") or "").strip()
    email = str(data.get("email") or "").strip()
    password = data.get("password")
    full_name = str(data.get("full_name") or "").strip()[:120] or None

    if not username or not email or not isinstance(password, str) or not password:
        return _error("registration_fields_required", "Enter a username, email address and password.", 400)
    if len(username) > 64 or len(email) > 255 or len(password) > 128:
        return _error("registration_input_too_long", "One or more registration fields exceed the allowed length.", 400)

    from app.auth.registration_policy import email_password_signup_allowed, email_verification_required
    if not email_password_signup_allowed():
        return _error("signup_disabled", "Email and password registration is currently unavailable. Please contact AFCON360 support.", 403)

    from app.auth.validators import validate_registration
    valid, message = validate_registration(username, password, email)
    if not valid:
        return _error("registration_invalid", message or "Check your registration details and try again.", 400)

    user_agent = request.headers.get("User-Agent", "AFCON360 Native")
    if email_verification_required():
        from app.auth.pending_registration import start_pending_registration
        result = start_pending_registration(
            username=username,
            password=password,
            email=email,
            full_name=full_name,
            ip=request.remote_addr,
            user_agent=user_agent,
        )
        if not result.success:
            if result.retry_after:
                status = 429
            elif result.code in {"email_exists", "username_exists"}:
                status = 409
            else:
                status = 400
            response, _ = _error(
                result.code or "registration_unavailable",
                result.message or "We could not start account verification. Please try again.",
                status,
            )
            if result.retry_after:
                response.headers["Retry-After"] = str(max(1, int(result.retry_after)))
            return response, status

        # The opaque token is a short-lived capability for this single
        # registration. The client keeps it in memory only; never return
        # the password hash, OTP, or any debug delivery code.
        return jsonify({
            "success": True,
            "registration_pending": True,
            "data": {
                "registration_token": result.token,
                "email": result.email,
                "expires_in": int(current_app.config.get("SIGNUP_OTP_TTL", 600)),
                "message": result.message,
            },
        }), 202

    from app.auth.services import register_user
    try:
        user = register_user(
            username=username,
            password=password,
            email=email,
            full_name=full_name,
            ip_address=request.remote_addr,
            user_agent=user_agent,
        )
    except ValueError as exc:
        db.session.rollback()
        return _error("registration_conflict", str(exc), 409)
    except Exception:
        db.session.rollback()
        logger.exception("Native account registration failed")
        return _error("registration_unavailable", "AFCON360 could not create your account right now. Please try again.", 503)

    return jsonify({
        "success": True,
        "registration_pending": False,
        "data": {
            "username": user.username,
            "email": user.email,
            "message": "Your account has been created. You can now sign in.",
        },
    }), 201


@mobile_api_bp.post("/auth/register/verify")
@limiter.limit("10 per minute", key_func=get_remote_address)
def mobile_register_verify():
    data = request.get_json(silent=True) or {}
    token = str(data.get("registration_token") or "").strip()
    code = str(data.get("code") or "").strip()
    if not token or len(token) > 256 or not code or len(code) > 6:
        return _error("registration_verification_invalid", "Enter the 6-digit code sent to your email.", 400)

    from app.auth.pending_registration import verify_pending_registration
    result = verify_pending_registration(
        token,
        code,
        ip=request.remote_addr,
        user_agent=request.headers.get("User-Agent", "AFCON360 Native"),
    )
    if not result.success:
        status = {
            "expired": 410,
            "too_many_attempts": 429,
            "creation_failed": 503,
            "creation_rejected": 409,
        }.get(result.code, 400)
        return jsonify({
            "success": False,
            "code": result.code or "registration_verification_failed",
            "message": result.message or "We could not verify that code.",
            "remaining_attempts": result.remaining_attempts,
        }), status

    return jsonify({
        "success": True,
        "data": {
            "message": result.message or "Your email is verified. You can now sign in.",
            "already_existed": bool(result.already_existed),
        },
    }), 200


@mobile_api_bp.post("/auth/register/resend")
@limiter.limit("5 per hour", key_func=get_remote_address)
def mobile_register_resend():
    data = request.get_json(silent=True) or {}
    token = str(data.get("registration_token") or "").strip()
    if not token or len(token) > 256:
        return _error("registration_token_invalid", "Your verification session has expired. Please start again.", 400)

    from app.auth.pending_registration import restart_pending_registration
    result = restart_pending_registration(token=token, ip=request.remote_addr)
    if not result.success:
        status = 410 if result.code == "expired" else (429 if result.retry_after else 400)
        response, _ = _error(
            result.code or "registration_resend_failed",
            result.message or "We could not resend the verification code.",
            status,
        )
        if result.retry_after:
            response.headers["Retry-After"] = str(max(1, int(result.retry_after)))
        return response, status

    return jsonify({
        "success": True,
        "data": {"message": result.message or "A new verification code has been sent."},
    }), 200


@mobile_api_bp.post("/auth/password-reset/request")
@limiter.limit("10 per hour", key_func=get_remote_address)
def mobile_password_reset_request():
    """Start an enumeration-safe email-code reset for an existing account."""
    data = request.get_json(silent=True) or {}
    identifier = str(
        data.get("identifier") or data.get("username") or data.get("email") or ""
    ).strip()[:255]

    # Never reveal whether an account exists or whether its mail address is
    # deliverable. The service logs delivery problems without returning PII.
    if identifier:
        try:
            from app.auth.mobile_password_reset import request_mobile_password_reset
            request_mobile_password_reset(identifier)
        except Exception:
            logger.exception("Native password-reset request could not be processed")

    return jsonify({
        "success": True,
        "data": {
            "message": (
                "If an active AFCON360 account has a registered email address, "
                "a reset code has been sent."
            ),
            "expires_in": 600,
        },
    }), 202


@mobile_api_bp.post("/auth/password-reset/confirm")
@limiter.limit("5 per hour", key_func=_mobile_password_reset_rate_key)
def mobile_password_reset_confirm():
    """Consume one email OTP, set the new password and revoke prior sessions."""
    data = request.get_json(silent=True) or {}
    identifier = str(data.get("identifier") or "").strip()[:255]
    code = str(data.get("code") or "").strip()
    new_password = data.get("new_password")
    confirm_password = data.get("confirm_password")

    if not identifier or not code.isdigit() or len(code) != 6:
        return _error(
            "password_reset_input_invalid",
            "Enter your username or email and the 6-digit code sent to your email.",
            400,
        )
    if not isinstance(new_password, str) or not new_password or len(new_password) > 128:
        return _error("password_reset_password_invalid", "Enter a valid new password.", 400)
    if new_password != confirm_password:
        return _error("password_reset_password_mismatch", "The passwords do not match.", 400)

    try:
        from app.auth.mobile_password_reset import confirm_mobile_password_reset
        success, message = confirm_mobile_password_reset(
            identifier=identifier,
            code=code,
            new_password=new_password,
        )
    except Exception:
        db.session.rollback()
        logger.exception("Native password-reset confirmation failed unexpectedly")
        return _error(
            "password_reset_unavailable",
            "AFCON360 could not complete the password reset. Request a new code or try again.",
            503,
        )

    if not success:
        return _error("password_reset_rejected", message, 400)

    return jsonify({
        "success": True,
        "data": {"message": message},
    }), 200


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
    if not challenge_data or challenge_data.get("mfa_type") not in {"totp", "sms"}:
        return _error("invalid_mfa_challenge", "This sign-in challenge has expired or was already used.", 401)

    from app.identity.models.user import User
    user = User.query.filter_by(public_id=challenge_data.get("user_public_id")).first()
    if user is None:
        return _error("invalid_mfa_challenge", "This sign-in challenge is no longer valid.", 401)
    eligible = _verify_login_eligibility(user, challenge_data.get("client"))
    if eligible:
        return eligible

    mfa_type = challenge_data.get("mfa_type")
    if mfa_type == "totp":
        from app.auth.routes import _verify_mfa_token
        if not _verify_mfa_token(user, code, backup_code=(len(code) == 8)):
            return _error("mfa_verification_failed", "The authenticator code is invalid or has expired.", 401)
    elif mfa_type == "sms":
        from app.auth.otp_service import otp_service
        verified, _message = otp_service.verify_otp(
            str(user.id),
            code,
            purpose="2fa_login",
        )
        if not verified:
            return _error("mfa_verification_failed", "The SMS code is invalid or has expired. Start sign-in again to request a new code.", 401)
    else:
        return _error("mfa_method_unsupported", "This sign-in method is not supported by the native app.", 422)

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


@mobile_api_bp.post("/transport/bookings")
@limiter.limit("5 per minute", key_func=get_remote_address)
@_bearer_required("user")
def mobile_create_transport_booking():
    """Create legacy Booking-first rides through the same service as the website.

    The request-first lifecycle is reserved for instant on-demand rides.
    Scheduled pickups and non-on-demand services (for example airport
    transfers) use BookingService, matching transport.book_transport.
    """
    from app.profile.models import get_profile_by_user
    from app.auth.kyc_compliance import calculate_kyc_tier
    from app.transport.services.payment_methods import (
        get_available_transport_payment_methods,
    )
    from app.transport.services.booking_service import get_booking_service
    from app.transport.models import BookingStatus
    from app.utils.exceptions import ValidationError, ServiceUnavailableError

    user = g._afcon360_mobile_auth_context["user"]
    data = request.get_json(silent=True) or {}
    pickup = data.get("pickup")
    dropoff = data.get("dropoff")
    if not isinstance(pickup, dict) or not isinstance(dropoff, dict):
        return _error(
            "booking_locations_incomplete",
            "A resolved pickup and destination are required.",
            400,
        )

    service_type = str(data.get("service_type") or "").strip().lower()
    booking_mode = str(data.get("booking_mode") or "").strip().lower()
    if service_type == "on_demand" and booking_mode == "instant":
        return _error(
            "use_ride_request",
            "Instant Quick Rides must use the ride-request matching flow.",
            409,
        )
    if not service_type or booking_mode not in {"instant", "scheduled"}:
        return _error(
            "booking_details_incomplete",
            "A valid service type and booking mode are required.",
            400,
        )
    if booking_mode == "scheduled" and not data.get("pickup_time"):
        return _error(
            "scheduled_pickup_time_required",
            "Choose a pickup date and time for a scheduled ride.",
            400,
        )

    # Apply the same profile and Tier-2 KYC gates as the website booking route.
    try:
        profile = get_profile_by_user(user)
        if profile is None or not bool(getattr(profile, "profile_completed", False)):
            return _error(
                "profile_completion_required",
                "Complete your AFCON360 profile before booking transport.",
                403,
            )
        kyc_info = calculate_kyc_tier(user.id)
        if int(kyc_info.get("tier", 0)) < 2:
            return jsonify({
                "success": False,
                "code": "kyc_upgrade_required",
                "message": "Complete the required identity verification before booking transport.",
                "data": {
                    "required_tier": 2,
                    "current_tier": int(kyc_info.get("tier", 0)),
                    "missing_requirements": kyc_info.get("missing_requirements", []),
                },
            }), 403
    except Exception:
        db.session.rollback()
        logger.exception("Native Booking-first transport eligibility check failed")
        return _error(
            "booking_gate_unavailable",
            "AFCON360 could not verify booking eligibility.",
            503,
        )

    selected_payment_method = str(data.get("payment_method") or "").strip().lower()
    try:
        available_methods = get_available_transport_payment_methods(user.id)
    except Exception:
        logger.exception("Could not resolve native transport payment choices")
        return _error(
            "payment_methods_unavailable",
            "AFCON360 could not load available payment methods.",
            503,
        )
    selected_method_info = next(
        (
            method for method in available_methods
            if str(method.get("code") or "").strip().lower() == selected_payment_method
            and method.get("enabled", True)
        ),
        None,
    )
    if not selected_payment_method or selected_method_info is None:
        return _error(
            "payment_method_unavailable",
            "Choose an available payment method before requesting the ride.",
            400,
        )
    if str(selected_method_info.get("status") or "").strip().lower() != "ready":
        return _error(
            "payment_method_not_ready",
            "The selected payment method is not ready. Complete its setup or choose another method.",
            409,
        )

    # Adapt the native resolved-place contract to BookingService's existing
    # website form contract. BookingService remains the validation, pricing,
    # timezone, persistence and idempotency authority.
    booking_data = {
        "provider_type": "individual_driver",
        "service_type": service_type,
        "currency": str(data.get("currency") or "USD").strip().upper(),
        "idempotency_key": data.get("idempotency_key"),
        "passenger_count": data.get("passenger_count") or 1,
        "luggage_count": data.get("luggage_count") or 0,
        "pickup_location": str(
            pickup.get("address") or pickup.get("label") or ""
        ).strip(),
        "dropoff_location": str(
            dropoff.get("address") or dropoff.get("label") or ""
        ).strip(),
        # BookingService fingerprints the normalized address fields as part
        # of its website idempotency contract. Supply both these fields and
        # the website-compatible location fields used for canonical snapshots.
        "pickup_address": str(
            pickup.get("address") or pickup.get("label") or ""
        ).strip(),
        "dropoff_address": str(
            dropoff.get("address") or dropoff.get("label") or ""
        ).strip(),
        "pickup_latitude": pickup.get("latitude"),
        "pickup_longitude": pickup.get("longitude"),
        "dropoff_latitude": dropoff.get("latitude"),
        "dropoff_longitude": dropoff.get("longitude"),
        "pickup_source": data.get("pickup_source"),
        "dropoff_source": data.get("dropoff_source"),
        "pickup_geocode": data.get("pickup_geocode"),
        "dropoff_geocode": data.get("dropoff_geocode"),
        "vehicle_class": data.get("vehicle_class") or "comfort",
        "booking_mode": booking_mode,
        "pickup_time": data.get("pickup_time") if booking_mode == "scheduled" else "",
        "payment_method": selected_payment_method,
        "fare_quote_token": data.get("fare_quote_token"),
        "confirmed_fare_amount": data.get("confirmed_fare_amount"),
    }

    try:
        result = get_booking_service().create_booking(user.id, booking_data)
    except ValidationError as exc:
        return _error("booking_rejected", exc.message, 400)
    except ServiceUnavailableError:
        return _error(
            "booking_unavailable",
            "Transport booking is temporarily unavailable. Your payment has not been taken.",
            503,
        )
    except Exception:
        db.session.rollback()
        logger.exception("Native Booking-first transport creation failed")
        return _error(
            "booking_unavailable",
            "Transport booking is temporarily unavailable. Your payment has not been taken.",
            503,
        )

    booking_result = result.get("data") or {}
    reference = booking_result.get("booking_reference")
    booking_id = booking_result.get("booking_id")
    if not reference or not booking_id:
        logger.error("BookingService returned an incomplete native booking result")
        return _error(
            "booking_reference_unavailable",
            "AFCON360 could not confirm the booking reference. Check Activity before retrying.",
            503,
        )

    # Mirror transport.book_transport: immediate cash rides are confirmed and
    # offered to matching now; scheduled rides are held for the scheduled
    # release worker, and Wallet-backed rides wait for their payment lifecycle.
    dispatch_pending = False
    if selected_payment_method == "cash" and booking_mode != "scheduled":
        try:
            get_booking_service().transition_status(
                booking_id,
                BookingStatus.CONFIRMED,
                reason="cash_confirm",
                initiated_by="rider",
                actor=user,
            )
            from app.transport.services.matching_service import MatchingService
            MatchingService.discover_and_offer(booking_id)
        except Exception:
            dispatch_pending = True
            db.session.rollback()
            logger.exception(
                "Native Booking-first ride %s persisted; matching was deferred",
                reference,
            )

    status_value = booking_result.get("status")
    status_value = getattr(status_value, "value", status_value)
    return jsonify({
        "success": True,
        "data": {
            "booking_id": booking_id,
            "booking_reference": reference,
            "booking_mode": booking_mode,
            "pickup_time": booking_result.get("pickup_time"),
            "status": str(status_value) if status_value is not None else None,
            "idempotent_replay": bool(booking_result.get("idempotent_replay")),
        },
        "booking_reference": reference,
        "booking_kind": "booking",
        "dispatch_pending": dispatch_pending,
    }), (200 if booking_result.get("idempotent_replay") else 201)


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

    def _enum_value(value):
        return getattr(value, "value", value)

    def _numeric_text(value):
        return str(value) if value is not None else None

    try:
        readiness = can_go_live(profile).to_dict()
    except Exception:
        logger.exception("Driver readiness check unavailable")
        readiness = {"ready": False, "checks": []}

    # Assignment and ownership are different facts. This is only the
    # currently assigned vehicle's safe display projection; it does not
    # expose registration/licence documents or vehicle ownership controls.
    assigned_vehicle = None
    try:
        vehicle = profile.current_vehicle
        if vehicle is not None and not bool(getattr(vehicle, "is_deleted", False)):
            assigned_vehicle = {
                "make": getattr(vehicle, "make", None),
                "model": getattr(vehicle, "model", None),
                "year": getattr(vehicle, "year", None),
                "license_plate": getattr(vehicle, "license_plate", None),
                "vehicle_class": _enum_value(getattr(vehicle, "vehicle_class", None)),
                "passenger_capacity": getattr(vehicle, "passenger_capacity", None),
            }
    except Exception:
        logger.exception("Assigned Driver vehicle summary unavailable")

    return jsonify({
        "success": True,
        "data": {
            "driver_code": profile.driver_code,
            "verification_tier": str(_enum_value(profile.verification_tier)),
            "compliance_status": str(_enum_value(profile.compliance_status)),
            "is_online": bool(profile.is_online),
            "is_available": bool(profile.is_available),
            "go_live": readiness,
            "operational_preferences": {
                "service_types": list(profile.service_types or []),
                "vehicle_classes": list(profile.vehicle_classes or []),
                "operational_zones": list(profile.operational_zones or []),
                "max_passenger_capacity": profile.max_passenger_capacity,
                "max_luggage_capacity": profile.max_luggage_capacity,
                "auto_accept_bookings": bool(profile.auto_accept_bookings),
                "max_concurrent_bookings": profile.max_concurrent_bookings,
            },
            "compliance": {
                "license_verified": bool(profile.license_verified),
                "license_expiry": profile.license_expiry.isoformat() if profile.license_expiry else None,
                "background_check_status": profile.background_check_status,
                "police_clearance_verified": bool(profile.police_clearance_verified),
                "next_training_due": profile.next_training_due.isoformat() if profile.next_training_due else None,
                "requires_retraining": bool(profile.requires_retraining),
            },
            "performance": {
                "reliability_score": getattr(profile, "reliability_score", None),
                "safety_score": getattr(profile, "safety_score", None),
                "acceptance_rate": _numeric_text(getattr(profile, "acceptance_rate", None)),
                "cancellation_rate": _numeric_text(getattr(profile, "cancellation_rate", None)),
                "total_trips": getattr(profile, "total_trips", None),
                "completed_trips": getattr(profile, "completed_trips", None),
                "total_duration_minutes": getattr(profile, "total_duration_minutes", None),
                "total_distance_km": _numeric_text(getattr(profile, "total_distance_km", None)),
                "average_rating": _numeric_text(getattr(profile, "average_rating", None)),
                "total_ratings": getattr(profile, "total_ratings", None),
            },
            "assigned_vehicle": assigned_vehicle,
        },
    }), 200


@mobile_api_bp.get("/driver/assignments")
@_bearer_required("driver")
def mobile_driver_assignments():
    """Self-scoped Driver assignment, owned-vehicle and scheduled-route view."""
    from datetime import timedelta
    from app.transport.models import (
        DriverVehicleHistory,
        ScheduledRoute,
        Vehicle,
    )
    from app.transport.services.provider_service import get_provider_service

    profile, error, status = _current_driver()
    if error:
        return jsonify(error), status

    def _enum_value(value):
        return getattr(value, "value", value)

    def _vehicle_view(vehicle, *, include_edit_fields=False):
        if vehicle is None or bool(getattr(vehicle, "is_deleted", False)):
            return None
        result = {
            "public_id": str(vehicle.public_id),
            "make": vehicle.make,
            "model": vehicle.model,
            "year": vehicle.year,
            "license_plate": vehicle.license_plate,
            "vehicle_class": _enum_value(vehicle.vehicle_class),
            "status": str(_enum_value(vehicle.status)),
            "is_available": bool(vehicle.is_available),
            "passenger_capacity": vehicle.passenger_capacity,
            "safety_features": list(vehicle.safety_features or []),
        }
        # Registration/VIN/specification details are returned only for
        # vehicles owned by this authenticated user, never for fleet
        # vehicles merely assigned to the Driver.
        if include_edit_fields:
            result.update({
                "registration_number": vehicle.registration_number,
                "color": vehicle.color,
                "vin_number": vehicle.vin_number,
                "vehicle_type": vehicle.vehicle_type,
                "luggage_capacity": vehicle.luggage_capacity,
            })
        return result

    assigned = profile.current_vehicle
    owned = get_provider_service().get_user_vehicles(profile.user_id) or []
    current_id = getattr(assigned, "id", None)
    switchable = [
        vehicle for vehicle in owned
        if vehicle.id != current_id
        and str(_enum_value(vehicle.status)).lower() == "active"
        and bool(getattr(vehicle, "is_available", True))
        and not bool(getattr(vehicle, "is_deleted", False))
    ]

    cutoff = datetime.now(timezone.utc) - timedelta(days=90)
    history_rows = (
        DriverVehicleHistory.query
        .filter(
            DriverVehicleHistory.driver_id == profile.id,
            DriverVehicleHistory.is_deleted.is_(False),
            DriverVehicleHistory.started_at >= cutoff,
        )
        .order_by(DriverVehicleHistory.started_at.desc())
        .limit(20)
        .all()
    )
    history = [
        {
            "license_plate": row.vehicle.license_plate if row.vehicle else "Vehicle",
            "assignment_reason": row.assignment_reason,
            "was_breakdown": bool(row.was_breakdown),
            "started_at": row.started_at.isoformat() if row.started_at else None,
            "ended_at": row.ended_at.isoformat() if row.ended_at else None,
        }
        for row in history_rows
    ]

    scheduled_rows = (
        ScheduledRoute.query
        .filter(
            ScheduledRoute.current_driver_id == profile.id,
            ScheduledRoute.is_active.is_(True),
            ScheduledRoute.is_cancelled.is_(False),
        )
        .order_by(ScheduledRoute.next_departure.asc())
        .limit(10)
        .all()
    )
    scheduled = [
        {
            "name": row.name,
            "route_code": row.route_code,
            "route_type": row.route_type,
            "primary_zone": row.primary_zone,
            "next_departure": row.next_departure.isoformat() if row.next_departure else None,
            "available_seats": row.available_seats,
            "vehicle_capacity": row.vehicle_capacity,
            "price_per_seat": str(row.price_per_seat) if row.price_per_seat is not None else None,
            "is_free": bool(row.is_free),
        }
        for row in scheduled_rows
    ]

    return jsonify({
        "success": True,
        "data": {
            "assigned_vehicle": _vehicle_view(assigned),
            "owned_vehicles": [
                view for view in (
                    _vehicle_view(vehicle, include_edit_fields=True)
                    for vehicle in owned
                )
                if view is not None
            ],
            "switchable_vehicles": [
                view for view in (_vehicle_view(vehicle) for vehicle in switchable)
                if view is not None
            ],
            "vehicle_history": history,
            "scheduled_routes": scheduled,
            "history_window_days": 90,
        },
    }), 200


@mobile_api_bp.post("/driver/vehicles/switch")
@_bearer_required("driver")
def mobile_driver_switch_vehicle():
    """Switch only to an active vehicle owned by this authenticated Driver."""
    from app.transport.models import Vehicle, assign_driver_to_vehicle
    from app.transport.services.go_live_service import can_go_live

    profile, error, status = _current_driver()
    if error:
        return jsonify(error), status
    user = g._afcon360_mobile_auth_context["user"]
    data = request.get_json(silent=True) or {}
    vehicle_public_id = str(data.get("vehicle_public_id") or "").strip()
    if not vehicle_public_id:
        return _error("vehicle_public_id_required", "Choose a vehicle to assign.", 400)

    vehicle = Vehicle.query.filter_by(
        public_id=vehicle_public_id,
        is_deleted=False,
    ).first()
    if vehicle is None:
        return _error("vehicle_not_found", "That vehicle could not be found.", 404)

    checklist = can_go_live(profile)
    blocked = next((item for item in checklist.checks if item.key == "blocked"), None)
    if blocked is not None and not blocked.ok:
        return jsonify({
            "success": False,
            "error": "blocked driver cannot switch vehicles",
            "go_live": checklist.to_dict(),
        }), 403

    owns = (
        (vehicle.owner_type == "driver" and int(vehicle.owner_id) == int(profile.id))
        or (vehicle.owner_type == "user" and int(vehicle.owner_id) == int(user.id))
    )
    if not owns:
        return _error("vehicle_not_owned", "You may only switch to a vehicle you own.", 403)
    if str(getattr(vehicle.status, "value", vehicle.status)).lower() != "active":
        return _error("vehicle_not_active", "This vehicle is not active.", 422)
    if bool(vehicle.is_deleted):
        return _error("vehicle_not_found", "That vehicle could not be found.", 404)

    current = profile.current_vehicle
    reason = str(data.get("reason") or "shift_start").strip()[:50]
    notes = str(data.get("notes") or "").strip()[:500] or None
    if current is not None and current.id == vehicle.id:
        return jsonify({
            "success": True,
            "data": {
                "unchanged": True,
                "assigned_vehicle": {
                    "make": vehicle.make,
                    "model": vehicle.model,
                    "year": vehicle.year,
                    "license_plate": vehicle.license_plate,
                },
                "reason": reason,
            },
        }), 200

    try:
        assign_driver_to_vehicle(
            profile,
            vehicle,
            reason=reason,
            authorized_by=user,
            notes=notes,
        )
        db.session.refresh(profile)
        assigned = profile.current_vehicle
        return jsonify({
            "success": True,
            "data": {
                "unchanged": False,
                "assigned_vehicle": {
                    "make": assigned.make,
                    "model": assigned.model,
                    "year": assigned.year,
                    "license_plate": assigned.license_plate,
                } if assigned else None,
                "reason": reason,
            },
        }), 200
    except Exception:
        db.session.rollback()
        logger.exception("Native Driver vehicle switch failed")
        return _error("vehicle_switch_failed", "AFCON360 could not switch this vehicle.", 503)


@mobile_api_bp.post("/driver/vehicles")
@_bearer_required("driver")
def mobile_driver_register_vehicle():
    """Register a vehicle owned by the authenticated Driver, with website KYC tier gate."""
    profile, error, status = _current_driver()
    if error:
        return jsonify(error), status
    user = g._afcon360_mobile_auth_context["user"]

    try:
        from app.auth.kyc_compliance import calculate_kyc_tier
        kyc = calculate_kyc_tier(int(user.id))
    except Exception:
        logger.exception("Native Driver vehicle registration KYC check unavailable")
        return _error("kyc_check_unavailable", "KYC status could not be verified. Try again later.", 503)
    if int(kyc.get("tier", 0)) < 3:
        return jsonify({
            "success": False,
            "code": "kyc_tier_required",
            "error": "Vehicle registration requires KYC tier 3.",
            "required_tier": 3,
            "current_tier": kyc.get("tier", 0),
        }), 403

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return _error("vehicle_payload_required", "Vehicle details are required.", 400)
    allowed = {
        "license_plate", "registration_number", "make", "model", "year",
        "color", "vin_number", "vehicle_type", "vehicle_class",
        "passenger_capacity", "luggage_capacity",
    }
    payload = {key: data[key] for key in allowed if key in data}
    try:
        from app.transport.services.provider_service import get_provider_service
        result = get_provider_service().register_vehicle(
            owner_type="driver",
            owner_id=int(profile.id),
            vehicle_data=payload,
            request_id=request.headers.get("Idempotency-Key"),
        )
        from app.transport.models import Vehicle
        vehicle_id = result.get("data", {}).get("vehicle_id")
        vehicle = db.session.get(Vehicle, vehicle_id) if vehicle_id else None
        if vehicle is None:
            return _error("vehicle_registration_incomplete", "Vehicle registration could not be confirmed.", 503)
        return jsonify({
            "success": True,
            "message": result.get("message") or "Vehicle registration submitted.",
            "data": {"public_id": str(vehicle.public_id)},
        }), 201
    except Exception as exc:
        db.session.rollback()
        logger.info("Native Driver vehicle registration rejected: %s", exc)
        return _error("vehicle_registration_rejected", str(exc), 400)


@mobile_api_bp.put("/driver/vehicles/<string:vehicle_public_id>")
@_bearer_required("driver")
def mobile_driver_update_vehicle(vehicle_public_id):
    """Update only editable specification fields of a vehicle owned by this Driver."""
    from app.transport.models import Vehicle
    from app.transport.services.provider_service import get_provider_service

    profile, error, status = _current_driver()
    if error:
        return jsonify(error), status
    user = g._afcon360_mobile_auth_context["user"]
    vehicle = Vehicle.query.filter_by(
        public_id=vehicle_public_id,
        is_deleted=False,
    ).first()
    if vehicle is None:
        return _error("vehicle_not_found", "That vehicle could not be found.", 404)
    owns = (
        (vehicle.owner_type == "driver" and int(vehicle.owner_id) == int(profile.id))
        or (vehicle.owner_type == "user" and int(vehicle.owner_id) == int(user.id))
    )
    if not owns:
        return _error("vehicle_not_owned", "You may only edit a vehicle you own.", 403)

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return _error("vehicle_payload_required", "Vehicle details are required.", 400)
    allowed = {
        "license_plate", "registration_number", "make", "model", "year",
        "color", "vin_number", "vehicle_type", "vehicle_class",
        "passenger_capacity", "luggage_capacity", "luggage_space_cubic_meters",
    }
    payload = {key: data[key] for key in allowed if key in data}
    try:
        result = get_provider_service().update_vehicle(int(vehicle.id), payload)
        return jsonify({
            "success": True,
            "message": result.get("message") or "Vehicle details updated.",
        }), 200
    except Exception as exc:
        db.session.rollback()
        logger.info("Native Driver vehicle update rejected: %s", exc)
        return _error("vehicle_update_rejected", str(exc), 400)


@mobile_api_bp.get("/driver/marketplace/vehicles")
@_bearer_required("driver")
def mobile_driver_marketplace_vehicles():
    """List active public vehicle listings using a narrow, driver-safe projection."""
    from sqlalchemy.orm import joinedload
    from app.transport.models import (
        DriverVehicleApplication,
        MarketplaceListingStatus,
        Vehicle,
        VehicleMarketplaceListing,
    )

    profile, error, status = _current_driver()
    if error:
        return jsonify(error), status
    user = g._afcon360_mobile_auth_context["user"]

    query = (
        VehicleMarketplaceListing.query
        .options(joinedload(VehicleMarketplaceListing.vehicle))
        .join(Vehicle, Vehicle.id == VehicleMarketplaceListing.vehicle_id)
        .filter(
            VehicleMarketplaceListing.is_deleted.is_(False),
            VehicleMarketplaceListing.listing_status == MarketplaceListingStatus.ACTIVE,
            VehicleMarketplaceListing.visibility == "public",
            VehicleMarketplaceListing.owner_id != user.id,
            Vehicle.is_deleted.is_(False),
            Vehicle.status == "active",
            Vehicle.is_available.is_(True),
            Vehicle.is_reserved.is_(False),
        )
        .order_by(VehicleMarketplaceListing.listed_at.desc())
        .limit(50)
    )
    rows = query.all()
    applications = {
        int(row.listing_id)
        for row in DriverVehicleApplication.query.filter_by(
            driver_id=profile.id,
            is_deleted=False,
        ).all()
    }
    items = []
    for listing in rows:
        vehicle = listing.vehicle
        if vehicle is None:
            continue
        owner_type = str(vehicle.owner_type or "").lower()
        owner_label = (
            "Organisation" if owner_type == "organisation"
            else "Driver owner" if owner_type == "driver"
            else "Private owner"
        )
        model = getattr(listing.compensation_model, "value", listing.compensation_model)
        if model == "revenue_split":
            compensation = f"{float(listing.driver_revenue_share_pct):g}% revenue share"
        elif model == "fixed_rental":
            amount = float(listing.fixed_rental_amount or 0)
            frequency = listing.rental_frequency or ""
            compensation = f"Fixed rental {amount:,.0f}{' / ' + frequency if frequency else ''}"
        elif model == "hybrid":
            compensation = f"{float(listing.driver_revenue_share_pct):g}% revenue share"
        else:
            compensation = "Compensation per agreement"
        items.append({
            "listing_public_id": str(listing.public_id),
            "vehicle_public_id": str(vehicle.public_id),
            "title": listing.title or f"{vehicle.make} {vehicle.model}",
            "make": vehicle.make,
            "model": vehicle.model,
            "year": vehicle.year,
            "description": listing.description or "",
            "vehicle_class": str(getattr(vehicle.vehicle_class, "value", vehicle.vehicle_class)),
            "passenger_capacity": vehicle.passenger_capacity,
            "owner_type": owner_label,
            "compensation": compensation,
            "application_deadline": listing.application_deadline.isoformat() if listing.application_deadline else None,
            "already_applied": int(listing.id) in applications,
        })
    return jsonify({"success": True, "data": {"items": items, "count": len(items)}}), 200


@mobile_api_bp.post("/driver/marketplace/vehicles/<string:listing_public_id>/apply")
@_bearer_required("driver")
def mobile_driver_apply_vehicle_marketplace(listing_public_id):
    """Apply to a public listing as the authenticated Driver; never accepts a Driver ID."""
    from app.transport.models import (
        MarketplaceListingStatus,
        VehicleMarketplaceListing,
    )
    from app.transport.services.marketplace_service import get_marketplace_service

    profile, error, status = _current_driver()
    if error:
        return jsonify(error), status
    user = g._afcon360_mobile_auth_context["user"]
    listing = VehicleMarketplaceListing.query.filter_by(
        public_id=listing_public_id,
        is_deleted=False,
        listing_status=MarketplaceListingStatus.ACTIVE,
        visibility="public",
    ).first()
    if listing is None:
        return _error("marketplace_listing_not_found", "That vehicle listing is not available.", 404)

    # The marketplace list intentionally excludes the Driver's own
    # listings. Enforce the same boundary on direct application requests too.
    if int(listing.owner_id) == int(user.id):
        return _error("own_marketplace_listing", "You cannot apply to your own vehicle listing.", 403)

    vehicle = listing.vehicle
    if (
        vehicle is None
        or vehicle.is_deleted
        or str(getattr(vehicle.status, "value", vehicle.status)).lower() != "active"
        or not vehicle.is_available
        or vehicle.is_reserved
    ):
        return _error("marketplace_vehicle_unavailable", "That vehicle is no longer available.", 409)
    data = request.get_json(silent=True) or {}
    safe_application = {
        "cover_letter": str(data.get("cover_letter") or "")[:5000],
        "proposed_schedule": data.get("proposed_schedule") if isinstance(data.get("proposed_schedule"), dict) else {},
        "proposed_hours_per_week": data.get("proposed_hours_per_week"),
        "expected_earnings": data.get("expected_earnings"),
        "references": data.get("references") if isinstance(data.get("references"), list) else [],
    }
    try:
        application = get_marketplace_service().submit_application(
            int(user.id),
            int(listing.id),
            safe_application,
        )
        return jsonify({
            "success": True,
            "data": {
                "status": str(getattr(application.status, "value", application.status)),
                "listing_public_id": str(listing.public_id),
            },
        }), 201
    except ValueError as exc:
        db.session.rollback()
        return _error("marketplace_application_rejected", str(exc), 400)
    except Exception:
        db.session.rollback()
        logger.exception("Native Driver vehicle marketplace application failed")
        return _error("marketplace_application_unavailable", "The application service is unavailable.", 503)


def _driver_notification_ref(user_id: int, notification_id: int) -> str:
    """Opaque, user-bound reference for a Notification without a public UUID."""
    import base64
    import hmac

    secret = current_app.secret_key
    if isinstance(secret, str):
        secret = secret.encode("utf-8")
    payload = f"{int(user_id)}:{int(notification_id)}"
    signature = hmac.new(secret, payload.encode("utf-8"), hashlib.sha256).hexdigest()
    return base64.urlsafe_b64encode(
        f"{int(notification_id)}:{signature}".encode("ascii")
    ).decode("ascii").rstrip("=")


def _resolve_driver_notification_ref(value: str, user_id: int):
    """Verify an opaque notification reference and return its internal row id."""
    import base64
    import hmac

    try:
        padding = "=" * (-len(value) % 4)
        decoded = base64.urlsafe_b64decode((value + padding).encode("ascii")).decode("ascii")
        raw_id, supplied_signature = decoded.split(":", 1)
        notification_id = int(raw_id)
        if notification_id <= 0:
            return None
        secret = current_app.secret_key
        if isinstance(secret, str):
            secret = secret.encode("utf-8")
        payload = f"{int(user_id)}:{notification_id}"
        expected = hmac.new(secret, payload.encode("utf-8"), hashlib.sha256).hexdigest()
        return notification_id if hmac.compare_digest(supplied_signature, expected) else None
    except (TypeError, ValueError, UnicodeDecodeError):
        return None


@mobile_api_bp.get("/driver/map-config")
@_bearer_required("driver")
def mobile_driver_map_config():
    """Return only the public GEO tile renderer configuration to a Driver."""
    from app.geo.config import load_geo_config
    from app.geo.map_renderer import PUBLIC_MAP_CONFIG_KEYS, build_public_map_config

    built_config = build_public_map_config(load_geo_config())
    config = {
        key: built_config[key]
        for key in PUBLIC_MAP_CONFIG_KEYS
        if key in built_config
    }
    template = str(config.get("tile_url_template") or "")
    # React Native's raster tile renderer accepts {z}/{x}/{y}. Resolve the
    # harmless OSM subdomain token server-side; never return any credentials.
    config["tile_url_template"] = template.replace("{s}", "a")
    response = jsonify({"success": True, "data": config})
    response.headers["Cache-Control"] = "private, max-age=300"
    return response, 200


@mobile_api_bp.get("/driver/demand/cells")
@_bearer_required("driver")
def mobile_driver_demand_cells():
    """Native bearer adapter for the shared, aggregate-only demand service."""
    profile, error, status = _current_driver()
    if error:
        return jsonify(error), status

    from app.transport.services.driver_demand_service import get_driver_demand_cells

    response = jsonify(get_driver_demand_cells(profile))
    response.headers["Cache-Control"] = "private, no-store, max-age=0"
    response.headers["Vary"] = "Authorization"
    return response, 200



@mobile_api_bp.get("/driver/notifications")
@_bearer_required("driver")
def mobile_driver_notifications():
    """Bearer inbox limited to this user and the Transport module."""
    from app.notifications.models import Notification

    profile, error, status = _current_driver()
    if error:
        return jsonify(error), status
    user = g._afcon360_mobile_auth_context["user"]

    try:
        limit = min(max(int(request.args.get("limit", 30)), 1), 50)
        offset = max(int(request.args.get("offset", 0)), 0)
    except (TypeError, ValueError):
        return _error("invalid_pagination", "Use a positive limit and non-negative offset.", 400)

    query = Notification.query.filter(
        Notification.user_id == user.id,
        Notification.module == "transport",
        Notification.is_deleted.is_(False),
    )
    total = query.count()
    unread_count = query.filter(Notification.is_read.is_(False)).count()
    rows = (
        query.order_by(Notification.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    items = [
        {
            "notification_ref": _driver_notification_ref(int(user.id), int(row.id)),
            "type": row.type,
            "module": row.module,
            "subject": row.subject,
            "body": (row.body or "")[:1600],
            "priority": row.priority,
            "status": str(getattr(row.status, "value", row.status)),
            "is_read": bool(row.is_read),
            "is_important": bool(row.is_important),
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "read_at": row.read_at.isoformat() if row.read_at else None,
        }
        for row in rows
    ]
    response = jsonify({
        "success": True,
        "data": {
            "items": items,
            "count": len(items),
            "total": total,
            "unread_count": unread_count,
            "limit": limit,
            "offset": offset,
        },
    })
    response.headers["Cache-Control"] = "private, no-store, max-age=0"
    response.headers["Vary"] = "Authorization"
    return response, 200


@mobile_api_bp.post("/driver/notifications/<string:notification_ref>/read")
@_bearer_required("driver")
def mobile_driver_notification_read(notification_ref):
    """Mark one Transport notification read using its public identifier."""
    from app.notifications.models import Notification

    profile, error, status = _current_driver()
    if error:
        return jsonify(error), status
    user = g._afcon360_mobile_auth_context["user"]
    notification_id = _resolve_driver_notification_ref(notification_ref, int(user.id))
    if notification_id is None:
        return _error("notification_not_found", "This Transport notification was not found.", 404)
    notification = Notification.query.filter(
        Notification.id == notification_id,
        Notification.user_id == user.id,
        Notification.module == "transport",
        Notification.is_deleted.is_(False),
    ).first()
    if notification is None:
        return _error("notification_not_found", "This Transport notification was not found.", 404)
    notification.mark_read()
    db.session.commit()
    remaining = Notification.query.filter(
        Notification.user_id == user.id,
        Notification.module == "transport",
        Notification.is_read.is_(False),
        Notification.is_deleted.is_(False),
    ).count()
    return jsonify({"success": True, "data": {"unread_count": remaining}}), 200


@mobile_api_bp.post("/driver/notifications/read-all")
@_bearer_required("driver")
def mobile_driver_notifications_read_all():
    """Mark only this Driver user's Transport notifications as read."""
    from app.notifications.models import Notification

    profile, error, status = _current_driver()
    if error:
        return jsonify(error), status
    user = g._afcon360_mobile_auth_context["user"]
    rows = Notification.query.filter(
        Notification.user_id == user.id,
        Notification.module == "transport",
        Notification.is_read.is_(False),
        Notification.is_deleted.is_(False),
    ).all()
    for row in rows:
        row.mark_read()
    if rows:
        db.session.commit()
    return jsonify({"success": True, "data": {"marked": len(rows), "unread_count": 0}}), 200


@mobile_api_bp.get("/driver/incidents")
@_bearer_required("driver")
def mobile_driver_incidents():
    """List only incidents this authenticated Driver personally reported."""
    from app.transport.models import TransportIncident

    profile, error, status = _current_driver()
    if error:
        return jsonify(error), status
    user = g._afcon360_mobile_auth_context["user"]
    try:
        limit = min(max(int(request.args.get("limit", 20)), 1), 50)
    except (TypeError, ValueError):
        return _error("invalid_limit", "Limit must be between 1 and 50.", 400)

    rows = (
        TransportIncident.query
        .filter(
            TransportIncident.reported_by == "driver",
            TransportIncident.reported_by_id == user.id,
            TransportIncident.driver_id == profile.id,
            TransportIncident.is_deleted.is_(False),
        )
        .order_by(TransportIncident.created_at.desc())
        .limit(limit)
        .all()
    )
    items = [
        {
            "incident_reference": row.incident_reference,
            "incident_type": row.incident_type,
            "incident_category": row.incident_category,
            "severity": str(getattr(row.severity, "value", row.severity)),
            "title": row.title,
            "description": row.description,
            "occurred_at": row.occurred_at.isoformat() if row.occurred_at else None,
            "status": row.status,
            "priority": row.priority,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }
        for row in rows
    ]
    response = jsonify({"success": True, "data": {"items": items, "count": len(items)}})
    response.headers["Cache-Control"] = "private, no-store, max-age=0"
    response.headers["Vary"] = "Authorization"
    return response, 200


@mobile_api_bp.post("/driver/incidents")
@limiter.limit("10 per hour")
@_bearer_required("driver")
def mobile_driver_report_incident():
    """Report an incident as the authenticated Driver; caller cannot choose identity."""
    from datetime import datetime
    from math import isfinite
    from app.transport.models import Booking, TransportIncident
    from app.utils.enums import IncidentSeverity

    profile, error, status = _current_driver()
    if error:
        return jsonify(error), status
    user = g._afcon360_mobile_auth_context["user"]
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return _error("incident_payload_required", "Incident details are required.", 400)

    incident_type = str(data.get("incident_type") or "").strip()[:50]
    title = str(data.get("title") or "").strip()[:200]
    description = str(data.get("description") or "").strip()[:5000]
    severity_value = str(data.get("severity") or "").strip().lower()
    occurred_value = data.get("occurred_at")
    if not incident_type or not title or not description or not occurred_value:
        return _error(
            "incident_fields_required",
            "Incident type, title, description and occurrence time are required.",
            400,
        )
    try:
        severity = IncidentSeverity(severity_value)
    except ValueError:
        return _error("invalid_incident_severity", "Choose a valid incident severity.", 400)

    if not isinstance(occurred_value, str):
        return _error("invalid_occurred_at", "Use an ISO-8601 time with an explicit timezone.", 400)
    try:
        occurred_at = datetime.fromisoformat(occurred_value.replace("Z", "+00:00"))
    except ValueError:
        return _error("invalid_occurred_at", "Use an ISO-8601 time with an explicit timezone.", 400)
    if occurred_at.tzinfo is None or occurred_at.utcoffset() is None:
        return _error("timezone_required", "Incident time must include a timezone offset.", 400)
    occurred_at = occurred_at.astimezone(timezone.utc)

    booking_id = None
    vehicle_id = None
    booking_reference = str(data.get("booking_reference") or "").strip()
    if booking_reference:
        booking = Booking.query.filter_by(
            booking_reference=booking_reference,
            is_deleted=False,
        ).first()
        if booking is None:
            return _error("booking_not_found", "The referenced trip was not found.", 404)
        metadata = booking.booking_metadata or {}
        belongs_to_driver = (
            booking.assigned_driver_id == profile.id
            or str(metadata.get("completed_by_driver_profile_id") or "") == str(profile.id)
        )
        if not belongs_to_driver:
            return _error("booking_not_owned", "You may report only on a trip assigned to you.", 403)
        booking_id = booking.id
        vehicle_id = booking.assigned_vehicle_id

    location = data.get("location")
    safe_location = None
    if location is not None:
        if not isinstance(location, dict):
            return _error("invalid_incident_location", "Location must contain coordinates.", 400)
        try:
            lat_raw, lon_raw = location.get("latitude"), location.get("longitude")
            if isinstance(lat_raw, bool) or isinstance(lon_raw, bool):
                raise ValueError
            latitude, longitude = float(lat_raw), float(lon_raw)
            if not isfinite(latitude) or not isfinite(longitude):
                raise ValueError
            if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
                raise ValueError
        except (TypeError, ValueError):
            return _error("invalid_incident_location", "Location coordinates are invalid.", 400)
        safe_location = {
            "latitude": latitude,
            "longitude": longitude,
            "address": str(location.get("address") or "")[:500],
        }

    if vehicle_id is None:
        current_vehicle = profile.current_vehicle
        vehicle_id = getattr(current_vehicle, "id", None)

    category = str(data.get("incident_category") or "safety").strip().lower()[:50]
    incident = TransportIncident(
        incident_type=incident_type,
        incident_category=category,
        severity=severity,
        title=title,
        description=description,
        occurred_at=occurred_at,
        reported_by="driver",
        reported_by_id=user.id,
        reported_via="driver_mobile",
        user_id=user.id,
        driver_id=profile.id,
        booking_id=booking_id,
        vehicle_id=vehicle_id,
        location=safe_location,
        photos=[],
        videos=[],
        status="reported",
        priority="high" if severity in (IncidentSeverity.HIGH, IncidentSeverity.CRITICAL) else "medium",
    )
    try:
        incident.generate_reference()
        db.session.add(incident)
        db.session.commit()
    except Exception:
        db.session.rollback()
        logger.exception("Native Driver incident report failed")
        return _error("incident_report_failed", "AFCON360 could not save the incident report.", 503)

    return jsonify({
        "success": True,
        "data": {
            "incident_reference": incident.incident_reference,
            "status": incident.status,
            "severity": str(getattr(incident.severity, "value", incident.severity)),
        },
    }), 201


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
    from app.utils.enums import BookingStatus, PaymentStatus
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

    def _point(value, fallback_text=None):
        if not isinstance(value, dict):
            return {"address": fallback_text} if fallback_text else None
        return {
            "latitude": value.get("latitude"),
            "longitude": value.get("longitude"),
            "address": value.get("address") or value.get("display_name") or fallback_text,
        }

    # Reuse BookingService's canonical trip projection for booking mode,
    # pickup timezone display and no-show grace eligibility. The mobile API
    # then selects only the fields needed by the Driver client.
    from app.transport.services.booking_service import get_booking_service
    trip_facts = get_booking_service()._driver_trip_row(booking)
    status_value = str(getattr(booking.status, "value", booking.status))
    can_cancel = status_value in {
        BookingStatus.ASSIGNED.value,
        BookingStatus.DRIVER_EN_ROUTE.value,
        BookingStatus.PICKUP_ARRIVED.value,
    }

    raw_schedule = trip_facts.get("pickup_schedule")
    pickup_schedule = None
    if isinstance(raw_schedule, dict):
        pickup_schedule = {
            key: raw_schedule[key]
            for key in (
                "utc_datetime",
                "local_datetime",
                "timezone_name",
                "utc_offset",
                "display_timezone_derived",
            )
            if key in raw_schedule
        }

    return jsonify({
        "success": True,
        "data": {
            "booking_reference": booking.booking_reference,
            "status": status_value,
            "booking_mode": trip_facts.get("booking_mode"),
            "pickup": _point(
                booking.pickup_location,
                getattr(booking, "pickup_location_text", None),
            ),
            "dropoff": _point(
                booking.dropoff_location,
                getattr(booking, "dropoff_location_text", None),
            ),
            "pickup_time": booking.pickup_time.isoformat() if booking.pickup_time else None,
            "pickup_schedule": pickup_schedule,
            "passenger_count": booking.passenger_count,
            "payment_method": booking.payment_method,
            "payment_status": str(getattr(booking.payment_status, "value", booking.payment_status)),
            "fare_amount": str(booking.final_price or booking.total_amount or 0),
            "currency": str(getattr(booking.currency, "value", booking.currency)),
            "can_cancel": can_cancel,
            "can_mark_no_show": bool(trip_facts.get("can_mark_no_show", False)),
        },
    }), 200


@mobile_api_bp.get("/driver/trips")
@_bearer_required("driver")
def mobile_driver_trips():
    """Read the authenticated driver's upcoming, recent or combined trip cards.

    The all scope merges the two existing self-scoped BookingService
    projections, deduplicates by booking reference, and keeps a bounded result.
    The route deliberately returns
    a small driver-facing projection. Passenger identities/contact details,
    internal row IDs, and the booking metadata blob never cross this boundary.
    """
    profile, error, status = _current_driver()
    if error:
        return jsonify(error), status

    scope = str(request.args.get("scope") or "recent").strip().lower()
    if scope not in {"upcoming", "recent", "all"}:
        return _error(
            "driver_trip_scope_invalid",
            "Choose upcoming, recent or all trips.",
            400,
        )

    raw_limit = request.args.get("limit", "10")
    try:
        limit = int(raw_limit)
    except (TypeError, ValueError):
        return _error("driver_trip_limit_invalid", "Trip limit must be a whole number from 1 to 20.", 400)
    if not 1 <= limit <= 20:
        return _error("driver_trip_limit_invalid", "Trip limit must be between 1 and 20.", 400)

    from app.transport.services.booking_service import BookingService

    service = BookingService()
    if scope == "upcoming":
        rows = service.get_driver_upcoming_bookings(profile.user_id, limit=limit)
    elif scope == "recent":
        rows = service.get_driver_recent_bookings(profile.user_id, limit=limit)
    else:
        # Reuse the website-owned query services, then combine their narrow
        # projections. A booking can appear in both sets during a status
        # transition; its public booking reference is the deduplication key.
        upcoming_rows = service.get_driver_upcoming_bookings(profile.user_id, limit=limit)
        recent_rows = service.get_driver_recent_bookings(profile.user_id, limit=limit)
        by_reference = {}
        for row in (recent_rows or []) + (upcoming_rows or []):
            if isinstance(row, dict) and row.get("booking_reference"):
                by_reference[str(row["booking_reference"])] = row

        def _trip_sort_timestamp(row):
            value = row.get("pickup_time") or row.get("created_at")
            if isinstance(value, str):
                try:
                    value = datetime.fromisoformat(value.replace("Z", "+00:00"))
                except ValueError:
                    value = None
            if not isinstance(value, datetime):
                return float("-inf")
            if value.tzinfo is None:
                value = value.replace(tzinfo=timezone.utc)
            return value.timestamp()

        rows = sorted(
            by_reference.values(),
            key=_trip_sort_timestamp,
            reverse=True,
        )[:limit]

    def _plain(value):
        return getattr(value, "value", value)

    def _iso(value):
        if hasattr(value, "isoformat"):
            return value.isoformat()
        return value if isinstance(value, str) else None

    def _amount(value):
        return str(value) if value is not None else None

    items = []
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        status_value = _plain(row.get("status"))
        currency_value = _plain(row.get("currency"))
        fare_value = row.get("final_price")
        if fare_value is None:
            fare_value = row.get("total_amount")

        schedule = row.get("pickup_schedule")
        if isinstance(schedule, dict):
            schedule = {
                key: schedule[key]
                for key in (
                    "utc_datetime",
                    "local_datetime",
                    "timezone_name",
                    "utc_offset",
                    "display_timezone_derived",
                )
                if key in schedule
            }
        else:
            schedule = None

        items.append({
            "booking_reference": row.get("booking_reference"),
            "status": str(status_value) if status_value is not None else "unknown",
            "booking_mode": row.get("booking_mode"),
            "pickup_time": _iso(row.get("pickup_time")),
            "pickup_schedule": schedule,
            "pickup": {
                "address": row.get("pickup_location_text") or "Pickup details unavailable",
            },
            "dropoff": {
                "address": row.get("dropoff_location_text") or "Destination details unavailable",
            },
            "passenger_count": row.get("passenger_count"),
            "fare_amount": _amount(fare_value),
            "currency": str(currency_value) if currency_value is not None else None,
            "payment_method": row.get("payment_method"),
            "payment_status": str(_plain(row.get("payment_status")))
            if row.get("payment_status") is not None else None,
            "can_mark_no_show": bool(row.get("can_mark_no_show", False)),
            "created_at": _iso(row.get("created_at")),
            "completed_at": _iso(row.get("completed_at")),
        })

    return jsonify({
        "success": True,
        "data": {
            "scope": scope,
            "items": items,
            "count": len(items),
            "limit": limit,
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




# ---------------------------------------------------------------------------
# Native Events and Tickets APIs
# ---------------------------------------------------------------------------

def _native_events_user():
    return g._afcon360_mobile_auth_context["user"]


@mobile_api_bp.get("/events")
@limiter.limit("30 per minute", key_func=get_remote_address)
@_bearer_required("user")
def mobile_events_list():
    from app.events.native_event_service import NativeEventService
    try:
        result = NativeEventService.list_events(
            query=request.args.get("q"),
            city=request.args.get("city"),
            country=request.args.get("country"),
            category=request.args.get("category"),
            limit=request.args.get("limit", 20, type=int),
            offset=request.args.get("offset", 0, type=int),
        )
        return jsonify({"success": True, "data": result}), 200
    except Exception:
        db.session.rollback()
        logger.exception("Native event discovery failed")
        return _error("events_unavailable", "Events are temporarily unavailable.", 503)


@mobile_api_bp.get("/events/registrations")
@limiter.limit("30 per minute", key_func=get_remote_address)
@_bearer_required("user")
def mobile_event_registrations():
    from app.events.native_event_service import NativeEventService
    try:
        result = NativeEventService.list_registrations(
            _native_events_user(),
            limit=request.args.get("limit", 20, type=int),
            offset=request.args.get("offset", 0, type=int),
        )
        return jsonify({"success": True, "data": result}), 200
    except Exception:
        db.session.rollback()
        logger.exception("Native event ticket history failed")
        return _error("event_tickets_unavailable", "Your event tickets could not be loaded.", 503)


@mobile_api_bp.get("/events/registrations/<string:registration_reference>")
@limiter.limit("30 per minute", key_func=get_remote_address)
@_bearer_required("user")
def mobile_event_registration(registration_reference):
    from app.events.native_event_service import NativeEventError, NativeEventService
    try:
        result = NativeEventService.get_registration(_native_events_user(), registration_reference)
        return jsonify({"success": True, "data": result}), 200
    except NativeEventError as exc:
        return _error(exc.code, exc.message, exc.status_code)
    except Exception:
        db.session.rollback()
        logger.exception("Native event ticket detail failed")
        return _error("event_ticket_unavailable", "This ticket could not be loaded.", 503)


@mobile_api_bp.get("/events/<string:event_public_id>")
@limiter.limit("30 per minute", key_func=get_remote_address)
@_bearer_required("user")
def mobile_event_detail(event_public_id):
    from app.events.native_event_service import NativeEventError, NativeEventService
    try:
        result = NativeEventService.get_event(event_public_id)
        return jsonify({"success": True, "data": result}), 200
    except NativeEventError as exc:
        return _error(exc.code, exc.message, exc.status_code)
    except Exception:
        db.session.rollback()
        logger.exception("Native event detail failed")
        return _error("event_detail_unavailable", "This event could not be loaded.", 503)


@mobile_api_bp.post("/events/<string:event_public_id>/registrations")
@limiter.limit("5 per minute", key_func=get_remote_address)
@_bearer_required("user")
def mobile_event_register_free_ticket(event_public_id):
    from app.events.native_event_service import NativeEventError, NativeEventService
    data = request.get_json(silent=True) or {}
    token = str(data.get("ticket_token") or "")
    if not token:
        return _error("ticket_selection_required", "Select a ticket type before registering.", 400)
    try:
        result = NativeEventService.register_free_ticket(
            _native_events_user(),
            event_public_id=event_public_id,
            ticket_token=token,
        )
        return jsonify({"success": True, "data": result}), 201
    except NativeEventError as exc:
        return _error(exc.code, exc.message, exc.status_code)
    except Exception:
        db.session.rollback()
        logger.exception("Native event free-ticket registration failed")
        return _error("event_registration_unavailable", "AFCON360 could not complete this registration. Check your tickets before trying again.", 503)


# ---------------------------------------------------------------------------
# Native Accommodation APIs
# ---------------------------------------------------------------------------

def _native_accommodation_user():
    return g._afcon360_mobile_auth_context["user"]


@mobile_api_bp.get("/accommodation/properties")
@limiter.limit("30 per minute", key_func=get_remote_address)
@_bearer_required("user")
def mobile_accommodation_properties():
    from app.accommodation.services.native_booking_service import NativeAccommodationService
    try:
        result = NativeAccommodationService.list_properties(
            query=request.args.get("q"),
            city=request.args.get("city"),
            country=request.args.get("country"),
            limit=request.args.get("limit", 20, type=int),
            offset=request.args.get("offset", 0, type=int),
        )
        return jsonify({"success": True, "data": result}), 200
    except Exception:
        db.session.rollback()
        logger.exception("Native accommodation property search failed")
        return _error("accommodation_search_unavailable", "Accommodation search is temporarily unavailable.", 503)


@mobile_api_bp.get("/accommodation/properties/<string:property_public_id>")
@limiter.limit("30 per minute", key_func=get_remote_address)
@_bearer_required("user")
def mobile_accommodation_property(property_public_id):
    from app.accommodation.services.native_booking_service import (
        NativeAccommodationError,
        NativeAccommodationService,
    )
    try:
        result = NativeAccommodationService.get_property(property_public_id)
        return jsonify({"success": True, "data": result}), 200
    except NativeAccommodationError as exc:
        return _error(exc.code, exc.message, exc.status_code)
    except Exception:
        db.session.rollback()
        logger.exception("Native accommodation property detail failed")
        return _error("accommodation_detail_unavailable", "This property could not be loaded right now.", 503)


@mobile_api_bp.post("/accommodation/quotes")
@limiter.limit("10 per minute", key_func=get_remote_address)
@_bearer_required("user")
def mobile_accommodation_quote():
    from app.accommodation.services.native_booking_service import (
        NativeAccommodationError,
        NativeAccommodationService,
    )
    data = request.get_json(silent=True) or {}
    required = ("property_public_id", "check_in", "check_out", "num_guests")
    if any(data.get(name) in (None, "") for name in required):
        return _error("booking_quote_fields_required", "Property, check-in, check-out and guest count are required.", 400)
    try:
        result = NativeAccommodationService.quote_booking(
            _native_accommodation_user(),
            property_public_id=data.get("property_public_id"),
            check_in_value=data.get("check_in"),
            check_out_value=data.get("check_out"),
            num_guests=data.get("num_guests"),
            rooms_requested=data.get("rooms_requested", 1),
            room_type_token=data.get("room_type_token"),
        )
        return jsonify({"success": True, "data": result}), 200
    except NativeAccommodationError as exc:
        return _error(exc.code, exc.message, exc.status_code)
    except Exception:
        db.session.rollback()
        logger.exception("Native accommodation quote failed")
        return _error("booking_quote_unavailable", "AFCON360 could not prepare this booking quote.", 503)


@mobile_api_bp.post("/accommodation/bookings")
@limiter.limit("5 per minute", key_func=get_remote_address)
@_bearer_required("user")
def mobile_accommodation_create_booking():
    from app.accommodation.services.native_booking_service import (
        NativeAccommodationError,
        NativeAccommodationService,
    )
    data = request.get_json(silent=True) or {}
    quote_token = str(data.get("quote_token") or "")
    pin = str(data.get("pin") or "")
    if not quote_token or not pin:
        return _error("booking_confirmation_required", "A valid booking quote and your transaction PIN are required.", 400)
    try:
        result = NativeAccommodationService.confirm_wallet_booking(
            _native_accommodation_user(),
            quote_token=quote_token,
            pin=pin,
            ip_address=request.remote_addr,
            user_agent=request.headers.get("User-Agent"),
            special_requests=data.get("special_requests"),
        )
        return jsonify({"success": True, "data": result}), 201
    except NativeAccommodationError as exc:
        return _error(exc.code, exc.message, exc.status_code)
    except Exception:
        db.session.rollback()
        logger.exception("Native accommodation booking confirmation failed")
        return _error(
            "booking_confirmation_unavailable",
            "AFCON360 could not confirm this booking. Check your booking history before trying again.",
            503,
        )


@mobile_api_bp.get("/accommodation/bookings")
@limiter.limit("30 per minute", key_func=get_remote_address)
@_bearer_required("user")
def mobile_accommodation_bookings():
    from app.accommodation.services.native_booking_service import NativeAccommodationService
    try:
        result = NativeAccommodationService.list_bookings(
            _native_accommodation_user(),
            limit=request.args.get("limit", 20, type=int),
            offset=request.args.get("offset", 0, type=int),
        )
        return jsonify({"success": True, "data": result}), 200
    except Exception:
        db.session.rollback()
        logger.exception("Native accommodation booking history failed")
        return _error("booking_history_unavailable", "Your accommodation bookings could not be loaded.", 503)


@mobile_api_bp.get("/accommodation/bookings/<string:booking_reference>")
@limiter.limit("30 per minute", key_func=get_remote_address)
@_bearer_required("user")
def mobile_accommodation_booking(booking_reference):
    from app.accommodation.services.native_booking_service import (
        NativeAccommodationError,
        NativeAccommodationService,
    )
    try:
        result = NativeAccommodationService.get_booking(_native_accommodation_user(), booking_reference)
        return jsonify({"success": True, "data": result}), 200
    except NativeAccommodationError as exc:
        return _error(exc.code, exc.message, exc.status_code)
    except Exception:
        db.session.rollback()
        logger.exception("Native accommodation booking detail failed")
        return _error("booking_detail_unavailable", "This booking could not be loaded.", 503)


@mobile_api_bp.post("/accommodation/bookings/<string:booking_reference>/cancel")
@limiter.limit("5 per minute", key_func=get_remote_address)
@_bearer_required("user")
def mobile_accommodation_cancel_booking(booking_reference):
    from app.accommodation.services.native_booking_service import (
        NativeAccommodationError,
        NativeAccommodationService,
    )
    data = request.get_json(silent=True) or {}
    idempotency_key = str(request.headers.get("Idempotency-Key") or data.get("idempotency_key") or "").strip()
    if len(idempotency_key) < 8 or len(idempotency_key) > 128:
        return _error("idempotency_key_required", "A unique cancellation request key is required.", 400)
    try:
        result = NativeAccommodationService.cancel_booking(
            _native_accommodation_user(),
            booking_reference,
            reason=data.get("reason"),
            ip_address=request.remote_addr,
            user_agent=request.headers.get("User-Agent"),
            idempotency_key=idempotency_key,
        )
        return jsonify({"success": True, "data": result}), 200
    except NativeAccommodationError as exc:
        return _error(exc.code, exc.message, exc.status_code)
    except Exception:
        db.session.rollback()
        logger.exception("Native accommodation cancellation failed")
        return _error("booking_cancellation_unavailable", "AFCON360 could not complete this cancellation.", 503)



# ---------------------------------------------------------------------------
# Native Wallet APIs
# ---------------------------------------------------------------------------

def _native_wallet_user():
    return g._afcon360_mobile_auth_context["user"]


def _native_wallet_mask_identity(identity_type, normalized):
    if identity_type == "PHONE":
        digits = "".join(ch for ch in str(normalized) if ch.isdigit())
        return f"+{digits[:3]} *** ***{digits[-3:]}" if len(digits) >= 9 else "••••"
    if identity_type == "EMAIL" and "@" in str(normalized):
        local, domain = str(normalized).split("@", 1)
        return f"{local[:1]}***@{domain}" if local else f"***@{domain}"
    value = str(normalized)
    return value[:3] + "••••" if len(value) > 3 else "••••"


def _resolve_native_wallet_recipient(identifier, sender_currency=None):
    from app.identity.models.user import User
    from app.wallet.models.payment_identity import PaymentIdentityModel
    from app.wallet.models.ledger import AccountModel

    raw = str(identifier or "").strip()
    if not raw or len(raw) > 320:
        return None, None, None, ("recipient_identifier_invalid", "Enter a valid AFCON360 ID, verified phone number or verified email.", 400)

    from app.wallet.services.payment_identity_service import (
        detect_identity_type,
        normalize_identity,
    )
    identity_type = detect_identity_type(raw)
    if identity_type is None:
        return None, None, None, ("recipient_not_found", "AFCON360 could not resolve that payment identity.", 404)

    try:
        normalized = normalize_identity(identity_type, raw)
    except (ValueError, TypeError):
        return None, None, None, ("recipient_not_found", "AFCON360 could not resolve that payment identity.", 404)

    identity = PaymentIdentityModel.query.filter_by(
        identity_type=identity_type,
        normalized_value=normalized,
        is_active=True,
        is_verified=True,
    ).first()
    if identity is None or identity.owner_type != "user" or not identity.owner_id:
        return None, None, None, ("recipient_not_found", "No verified AFCON360 user payment identity was found.", 404)

    recipient = db.session.get(User, identity.owner_id)
    if recipient is None or not getattr(recipient, "is_active", False) or getattr(recipient, "is_deleted", False):
        return None, None, None, ("recipient_unavailable", "That AFCON360 account is not available to receive transfers.", 404)

    sender = _native_wallet_user()
    if int(recipient.id) == int(sender.id):
        return None, None, None, ("self_transfer_not_allowed", "You cannot send money to your own wallet.", 400)

    account = None
    if identity.account_id:
        account = db.session.get(AccountModel, identity.account_id)
        if (
            account is None
            or account.owner_type != "user"
            or int(account.user_id or 0) != int(recipient.id)
        ):
            account = None
    else:
        candidates = AccountModel.query.filter_by(
            user_id=recipient.id,
            owner_type="user",
            status="active",
            is_frozen=False,
        ).order_by(AccountModel.currency.asc()).all()
        if sender_currency:
            same_currency = [item for item in candidates if str(item.currency).upper() == str(sender_currency).upper()]
        else:
            same_currency = []
        if len(same_currency) == 1:
            account = same_currency[0]
        elif len(candidates) == 1:
            account = candidates[0]
        elif not candidates:
            return None, None, None, ("recipient_wallet_not_found", "That user has no active wallet to receive a transfer.", 404)
        else:
            currencies = sorted({str(item.currency).upper() for item in candidates})
            return None, None, None, ("recipient_currency_ambiguous", "The recipient has more than one wallet currency. Select a recipient wallet currency before continuing.", 409, currencies)

    if account is None or account.status != "active" or account.is_frozen:
        return None, None, None, ("recipient_wallet_unavailable", "That user's destination wallet is unavailable.", 409)
    return identity, recipient, account, None


@mobile_api_bp.get("/wallet")
@_bearer_required("user")
def mobile_wallet_summary():
    """Return ledger-derived balances for the authenticated user's active wallets."""
    from app.wallet.models.ledger import AccountModel
    from app.wallet.repositories.ledger_repository import LedgerRepository

    user = _native_wallet_user()
    accounts = AccountModel.query.filter_by(
        user_id=user.id,
        owner_type="user",
    ).order_by(AccountModel.currency.asc()).all()
    ledger = LedgerRepository()
    data = []
    for account in accounts:
        data.append({
            "currency": str(account.currency).upper(),
            "balance": str(ledger.get_balance(account.id, account.currency)),
            "is_frozen": bool(account.is_frozen) or account.status != "active",
            "status": str(account.status),
        })
    return jsonify({
        "success": True,
        "data": {"exists": bool(data), "accounts": data},
    }), 200


@mobile_api_bp.get("/wallet/transactions")
@_bearer_required("user")
def mobile_wallet_transactions():
    """Return only the authenticated user's transaction history, with safe fields."""
    from sqlalchemy import or_
    from app.wallet.models.transaction import TransactionModel

    user = _native_wallet_user()
    limit = request.args.get("limit", default=30, type=int)
    offset = request.args.get("offset", default=0, type=int)
    tx_type = str(request.args.get("type") or "").strip().lower()
    allowed_types = {"deposit", "withdraw", "transfer", "refund", "fee", "adjustment"}
    if limit < 1 or offset < 0:
        return _error("pagination_invalid", "Use a positive limit and a non-negative offset.", 400)
    limit = min(limit, 100)
    if tx_type and tx_type not in allowed_types:
        return _error("transaction_type_invalid", "The selected transaction type is not supported.", 400)

    query = TransactionModel.query.filter(or_(
        TransactionModel.user_id == user.id,
        TransactionModel.recipient_user_id == user.id,
    ))
    if tx_type:
        query = query.filter(TransactionModel.tx_type == tx_type)
    total = query.count()
    rows = query.order_by(
        TransactionModel.created_at.desc(),
        TransactionModel.id.desc(),
    ).offset(offset).limit(limit).all()

    items = []
    for row in rows:
        items.append({
            "reference": str(row.id),
            "type": str(getattr(row.tx_type, "value", row.tx_type)),
            "direction": "received" if row.recipient_user_id == user.id else "sent",
            "amount": str(row.amount),
            "currency": str(row.currency),
            "status": str(getattr(row.status, "value", row.status)),
            "created_at": row.created_at.isoformat() if row.created_at else None,
        })
    return jsonify({
        "success": True,
        "data": {
            "items": items,
            "total": total,
            "limit": limit,
            "offset": offset,
            "has_more": offset + limit < total,
        },
    }), 200


@mobile_api_bp.get("/wallet/pin")
@_bearer_required("user")
def mobile_wallet_pin_status():
    user = _native_wallet_user()
    locked_until = user.transaction_pin_locked_until
    if locked_until and locked_until.tzinfo is None:
        locked_until = locked_until.replace(tzinfo=timezone.utc)
    return jsonify({
        "success": True,
        "data": {
            "pin_set": bool(user.transaction_pin_hash),
            "locked": bool(locked_until and locked_until > datetime.now(timezone.utc)),
        },
    }), 200


@mobile_api_bp.post("/wallet/pin")
@limiter.limit("8 per minute", key_func=get_remote_address)
@_bearer_required("user")
def mobile_wallet_pin_set():
    from app.identity.models.user import User

    data = request.get_json(silent=True) or {}
    pin = str(data.get("pin") or "")
    confirm_pin = str(data.get("confirm_pin") or "")
    if not pin or not confirm_pin or pin != confirm_pin:
        return _error("pin_confirmation_invalid", "Enter the same new PIN twice.", 400)
    if not pin.isdigit() or len(pin) not in (4, 5, 6):
        return _error("pin_format_invalid", "Your transaction PIN must contain 4–6 digits.", 400)

    current = _native_wallet_user()
    try:
        user = db.session.query(User).filter_by(id=current.id).with_for_update().one_or_none()
        if user is None or not getattr(user, "is_active", False) or getattr(user, "is_deleted", False):
            return _error("account_unavailable", "This AFCON360 account is not available.", 403)

        now = datetime.now(timezone.utc)
        locked_until = user.transaction_pin_locked_until
        if locked_until and locked_until.tzinfo is None:
            locked_until = locked_until.replace(tzinfo=timezone.utc)
        if locked_until and locked_until > now:
            db.session.rollback()
            return _error("pin_locked", "Your current PIN is locked. Try again after the lockout expires.", 423)

        if user.transaction_pin_hash:
            current_pin = str(data.get("current_pin") or "")
            if not current_pin or not user.verify_transaction_pin(current_pin, session=db.session):
                db.session.commit()  # persist failed-attempt counters
                return _error("current_pin_invalid", "Your current transaction PIN is incorrect or locked.", 403)
        else:
            password = str(data.get("password") or "")
            if not password or not user.verify_password(password):
                db.session.rollback()
                return _error("password_reauthentication_required", "Enter your account password to set your first transaction PIN.", 403)

        user.set_transaction_pin(pin, session=db.session)
        db.session.commit()
    except Exception:
        db.session.rollback()
        logger.exception("Native wallet PIN update failed")
        return _error("pin_update_unavailable", "AFCON360 could not securely update your PIN. Please try again.", 503)

    return jsonify({"success": True, "data": {"pin_set": True}}), 200


@mobile_api_bp.post("/wallet/recipients/resolve")
@limiter.limit("20 per minute", key_func=get_remote_address)
@_bearer_required("user")
def mobile_wallet_recipient_resolve():
    data = request.get_json(silent=True) or {}
    currency = str(data.get("currency") or "").strip().upper()
    if len(currency) != 3:
        return _error("currency_invalid", "Choose a valid three-letter wallet currency.", 400)
    identity, recipient, account, error = _resolve_native_wallet_recipient(
        data.get("identifier"), sender_currency=currency
    )
    if error:
        code, message, status, *details = error
        payload = {"success": False, "code": code, "message": message}
        if details:
            payload["data"] = {"available_currencies": details[0]}
        return jsonify(payload), status
    return jsonify({
        "success": True,
        "data": {
            "display_name": getattr(recipient, "display_name", None) or "AFCON360 member",
            "masked_identifier": _native_wallet_mask_identity(identity.identity_type, identity.normalized_value),
            "recipient_currency": str(account.currency).upper(),
        },
    }), 200


@mobile_api_bp.post("/wallet/transfers")
@limiter.limit("8 per minute", key_func=get_remote_address)
@_bearer_required("user")
def mobile_wallet_transfer():
    from decimal import InvalidOperation
    from app.wallet.models.ledger import AccountModel
    from app.wallet.exceptions import (
        DuplicateTransactionError,
        InsufficientBalanceError,
        LimitExceededError,
        TransactionPINError,
        UnsupportedCurrencyError,
        WalletFrozenError,
        WalletNotFoundError,
        ComplianceBlockError,
    )
    from app.wallet.services.wallet_service import WalletService

    data = request.get_json(silent=True) or {}
    user = _native_wallet_user()
    identifier = data.get("identifier")
    currency = str(data.get("currency") or "").strip().upper()
    note = str(data.get("note") or "").strip()
    pin = str(data.get("pin") or "")
    idempotency_key = str(
        request.headers.get("Idempotency-Key")
        or request.headers.get("X-Idempotency-Key")
        or data.get("idempotency_key")
        or ""
    ).strip()

    if len(currency) != 3:
        return _error("currency_invalid", "Choose a valid three-letter wallet currency.", 400)
    if not idempotency_key or len(idempotency_key) < 8 or len(idempotency_key) > 128:
        return _error("idempotency_key_required", "A unique transfer request key is required.", 400)
    if len(note) > 140:
        return _error("transfer_note_invalid", "The transfer note must be 140 characters or fewer.", 400)
    if not pin or not pin.isdigit() or len(pin) not in (4, 5, 6):
        return _error("transaction_pin_required", "Enter your 4–6 digit transaction PIN.", 403)

    try:
        amount = Decimal(str(data.get("amount")))
        if not amount.is_finite() or amount <= 0 or amount.as_tuple().exponent < -2:
            raise InvalidOperation
    except (InvalidOperation, TypeError, ValueError):
        return _error("amount_invalid", "Enter a valid positive amount with no more than two decimal places.", 400)

    sender_account = AccountModel.query.filter_by(
        user_id=user.id,
        owner_type="user",
        currency=currency,
    ).first()
    if sender_account is None or sender_account.status != "active":
        return _error("wallet_not_found", "You do not have an active wallet in that currency.", 404)
    if sender_account.is_frozen:
        return _error("wallet_frozen", "Your wallet is restricted. Contact AFCON360 support.", 403)
    if not user.transaction_pin_hash:
        return _error("transaction_pin_not_set", "Set your transaction PIN before sending money.", 403)

    identity, recipient, recipient_account, recipient_error = _resolve_native_wallet_recipient(
        identifier, sender_currency=currency
    )
    if recipient_error:
        code, message, status, *details = recipient_error
        payload = {"success": False, "code": code, "message": message}
        if details:
            payload["data"] = {"available_currencies": details[0]}
        return jsonify(payload), status
    if str(recipient_account.currency).upper() != currency:
        return jsonify({
            "success": False,
            "code": "recipient_currency_mismatch",
            "message": "Your wallet and the recipient wallet use different currencies. AFCON360 must show you a confirmed conversion quote before this transfer can proceed.",
            "data": {
                "send_currency": currency,
                "recipient_currency": str(recipient_account.currency).upper(),
            },
        }), 409

    try:
        result = WalletService().transfer(
            from_account_id=str(sender_account.id),
            to_account_id=str(recipient_account.id),
            amount=amount,
            currency=currency,
            client_request_id=idempotency_key,
            note=note or None,
            metadata={"source": "native_mobile"},
            pin=pin,
        )
    except TransactionPINError as exc:
        return _error("transaction_pin_invalid", str(exc), 403)
    except InsufficientBalanceError as exc:
        return _error("insufficient_balance", str(exc), 402)
    except DuplicateTransactionError:
        return _error("idempotency_conflict", "That transfer request key has already been used. Refresh your transaction history before retrying.", 409)
    except WalletFrozenError:
        return _error("wallet_frozen", "The sender or recipient wallet is restricted.", 403)
    except LimitExceededError as exc:
        return _error("wallet_limit_exceeded", str(exc), 429)
    except UnsupportedCurrencyError:
        return _error("currency_unsupported", "This wallet currency is not currently supported for transfers.", 400)
    except ComplianceBlockError as exc:
        return _error("compliance_blocked", str(exc), 403)
    except PermissionError:
        return _error("wallet_transfer_forbidden", "AFCON360 could not authorize this wallet transfer.", 403)
    except ValueError as exc:
        return _error("transfer_invalid", str(exc), 400)
    except Exception:
        db.session.rollback()
        logger.exception("Native wallet transfer failed for user %s", user.public_id)
        return _error("wallet_transfer_unavailable", "AFCON360 could not complete this transfer. Check your transaction history before retrying.", 503)

    return jsonify({
        "success": True,
        "data": {
            "reference": str(result.get("transaction_id")),
            "amount": str(result.get("amount", amount)),
            "currency": str(result.get("currency", currency)),
            "received_amount": str(result.get("amount", amount)),
            "received_currency": currency,
            "recipient_display_name": getattr(recipient, "display_name", None) or "AFCON360 member",
            "new_balance": str(result.get("new_balance_from")),
            "already_processed": bool(result.get("already_processed", False)),
        },
    }), 200



# ---------------------------------------------------------------------------
# Native provider-backed wallet deposits
# ---------------------------------------------------------------------------

def _native_deposit_reference(user, idempotency_key: str) -> str:
    source = f"{user.public_id}:{idempotency_key}".encode("utf-8")
    return "NATDEP-" + hashlib.sha256(source).hexdigest()[:32].upper()


def _native_deposit_intent(reference: str, user):
    from app.wallet.services.deposit_intent import get_deposit_intent

    intent = get_deposit_intent(reference)
    if not intent or int(intent.get("user_id") or 0) != int(user.id):
        return None
    return intent


@mobile_api_bp.post("/wallet/deposits")
@limiter.limit("4 per minute", key_func=get_remote_address)
@_bearer_required("user")
def mobile_wallet_deposit_start():
    """Start a Flutterwave checkout; ledger credit waits for provider verification."""
    from app.extensions import redis_client
    from app.wallet.models.ledger import AccountModel
    from app.wallet.services.deposit_intent import get_deposit_intent
    from app.wallet.payments.flutterwave import FlutterwaveService

    user = _native_wallet_user()
    data = request.get_json(silent=True) or {}
    currency = str(data.get("currency") or "").strip().upper()
    payment_method = str(data.get("payment_method") or "mobilemoney").strip().lower()
    idempotency_key = str(
        request.headers.get("Idempotency-Key")
        or request.headers.get("X-Idempotency-Key")
        or data.get("idempotency_key")
        or ""
    ).strip()

    if not currency or len(currency) != 3:
        return _error("currency_invalid", "Choose a valid three-letter wallet currency.", 400)
    if payment_method not in {"mobilemoney", "card", "banktransfer", "ussd"}:
        return _error("payment_method_invalid", "Choose a supported Flutterwave payment method.", 400)
    if not idempotency_key or len(idempotency_key) < 8 or len(idempotency_key) > 128:
        return _error("idempotency_key_required", "A unique deposit request key is required.", 400)

    try:
        amount = Decimal(str(data.get("amount")))
        if not amount.is_finite() or amount <= 0 or amount.as_tuple().exponent < -2:
            raise ValueError("invalid amount")
    except (InvalidOperation, TypeError, ValueError):
        return _error("amount_invalid", "Enter a positive amount with no more than two decimal places.", 400)

    account = AccountModel.query.filter_by(
        user_id=user.id,
        owner_type="user",
        currency=currency,
    ).first()
    if account is None or str(account.status).lower() != "active":
        return _error("wallet_not_found", "Create or activate a wallet in this currency before depositing.", 404)
    if bool(account.is_frozen):
        return _error("wallet_frozen", "Your wallet is restricted. Contact AFCON360 support.", 403)

    reference = _native_deposit_reference(user, idempotency_key)
    try:
        existing = get_deposit_intent(reference)
    except Exception:
        logger.exception("Native wallet deposit intent store unavailable")
        return _error("deposit_service_unavailable", "AFCON360 could not securely start a deposit. Please try again.", 503)

    if existing:
        if (
            int(existing.get("user_id") or 0) != int(user.id)
            or str(existing.get("account_id")) != str(account.id)
            or str(existing.get("currency") or "").upper() != currency
            or Decimal(str(existing.get("amount") or "0")) != amount
        ):
            return _error("idempotency_conflict", "That deposit request key was already used for different payment details.", 409)
        state = str(existing.get("status") or "pending").lower()
        if state == "completed":
            return jsonify({
                "success": True,
                "data": {
                    "reference": reference,
                    "status": "completed",
                    "amount": str(amount),
                    "currency": currency,
                },
            }), 200
        if state == "pending" and existing.get("authorization_url"):
            return jsonify({
                "success": True,
                "data": {
                    "reference": reference,
                    "status": "pending",
                    "amount": str(amount),
                    "currency": currency,
                    "payment_provider": "flutterwave",
                    "authorization_url": existing["authorization_url"],
                    "message": "Continue with the existing Flutterwave checkout.",
                },
            }), 200
        if state == "failed":
            return _error("deposit_request_failed", "This deposit request failed. Start a new request with a new idempotency key.", 409)
        return _error("deposit_request_pending", "This deposit request is still being prepared. Check its status before starting another.", 409)

    # Prevent concurrent native retries from creating multiple hosted checkouts.
    lock_key = f"wallet:native-deposit:init:{reference}"
    lock_token = secrets.token_urlsafe(24)
    try:
        if not redis_client or not redis_client.set(lock_key, lock_token, ex=60, nx=True):
            return _error("deposit_request_in_progress", "This deposit request is already being prepared. Please check its status.", 409)
    except Exception:
        logger.exception("Native wallet deposit idempotency lock unavailable")
        return _error("deposit_service_unavailable", "AFCON360 could not securely start a deposit. Please try again.", 503)

    try:
        # Persist the owner/account/amount reference before contacting Flutterwave.
        # If the provider accepts the request but the HTTP response is lost, the
        # callback or an explicit status refresh can still reconcile this intent.
        from app.wallet.services.deposit_intent import save_deposit_intent, mark_deposit_intent_status
        save_deposit_intent(reference, {
            "account_id": str(account.id),
            "user_id": int(user.id),
            "amount": str(amount),
            "currency": currency,
            "source": "flutterwave",
            "payment_method": payment_method,
            "reference": reference,
            "status": "pending",
            "initiation_state": "started",
        })

        redirect_url = url_for("wallet.flutterwave_deposit_callback", _external=True)
        result = FlutterwaveService().initiate_deposit(
            user_id=int(user.id),
            account_id=str(account.id),
            amount=amount,
            currency=currency,
            payment_method=payment_method,
            redirect_url=redirect_url,
            idempotency_key=reference,
        )
        intent = get_deposit_intent(reference)
        if not intent:
            logger.error("Flutterwave native reference %s lost its pre-created deposit intent", reference)
            return _error("deposit_state_unavailable", "AFCON360 could not verify the pending payment record. Contact support before retrying.", 503)

        authorization_url = (intent or {}).get("authorization_url") or result.get("authorization_url")
        if not result.get("success") or result.get("status") != "pending" or not authorization_url:
            # The provider request may have reached Flutterwave even if the client
            # saw a timeout or malformed response. Keep the intent pending so a
            # provider callback or explicit refresh can reconcile the reference.
            mark_deposit_intent_status(reference, "pending")
            logger.warning("Flutterwave native deposit initiation is awaiting reconciliation for user %s", user.public_id)
            return jsonify({
                "success": True,
                "data": {
                    "reference": reference,
                    "status": "pending",
                    "amount": str(amount),
                    "currency": currency,
                    "payment_provider": "flutterwave",
                    "authorization_url": None,
                    "message": "AFCON360 is checking the provider response. Refresh this deposit status before starting another payment.",
                },
            }), 202

        return jsonify({
            "success": True,
            "data": {
                "reference": reference,
                "status": "pending",
                "amount": str(amount),
                "currency": currency,
                "payment_provider": "flutterwave",
                "authorization_url": authorization_url,
                "message": "Complete the payment in Flutterwave. Your Wallet is credited only after provider confirmation.",
            },
        }), 201
    except Exception:
        logger.exception("Native wallet deposit initiation failed for user %s", user.public_id)
        return _error("deposit_initiation_failed", "AFCON360 could not start this deposit. Please try again later.", 503)
    finally:
        # Compare-and-delete so an expired lock acquired by a later request is
        # never deleted by this request.
        try:
            redis_client.eval(
                "if redis.call('get', KEYS[1]) == ARGV[1] then return redis.call('del', KEYS[1]) else return 0 end",
                1,
                lock_key,
                lock_token,
            )
        except Exception:
            logger.warning("Native wallet deposit lock cleanup deferred to its TTL", exc_info=True)


@mobile_api_bp.get("/wallet/deposits/<string:reference>")
@_bearer_required("user")
def mobile_wallet_deposit_status(reference):
    user = _native_wallet_user()
    intent = _native_deposit_intent(reference, user)
    if intent is None:
        return _error("deposit_not_found", "No deposit request was found for this AFCON360 account.", 404)
    return jsonify({
        "success": True,
        "data": {
            "reference": reference,
            "status": str(intent.get("status") or "pending").lower(),
            "amount": str(intent.get("amount")),
            "currency": str(intent.get("currency") or "").upper(),
            "payment_provider": str(intent.get("source") or ""),
        },
    }), 200


@mobile_api_bp.post("/wallet/deposits/<string:reference>/refresh")
@limiter.limit("10 per minute", key_func=get_remote_address)
@_bearer_required("user")
def mobile_wallet_deposit_refresh(reference):
    user = _native_wallet_user()
    intent = _native_deposit_intent(reference, user)
    if intent is None:
        return _error("deposit_not_found", "No deposit request was found for this AFCON360 account.", 404)
    if str(intent.get("source") or "").lower() != "flutterwave":
        return _error("deposit_provider_unsupported", "This deposit provider cannot be refreshed through this native endpoint.", 422)

    from app.wallet.payments.flutterwave import FlutterwaveService
    result = FlutterwaveService().verify_and_credit(reference)
    status = str(result.get("status") or ("completed" if result.get("success") else "pending")).lower()
    if status == "completed":
        return jsonify({
            "success": True,
            "data": {
                "reference": reference,
                "status": "completed",
                "amount": str(intent.get("amount")),
                "currency": str(intent.get("currency") or "").upper(),
            },
        }), 200
    if status == "failed":
        return _error("deposit_failed", "Flutterwave did not complete this payment. Start a new deposit when ready.", 409)
    return jsonify({
        "success": True,
        "data": {
            "reference": reference,
            "status": "pending",
            "amount": str(intent.get("amount")),
            "currency": str(intent.get("currency") or "").upper(),
            "message": "The payment provider has not confirmed this deposit yet.",
        },
    }), 202


@mobile_api_bp.get("/driver/earnings")
@_bearer_required("driver")
def mobile_driver_earnings():
    from app.transport.models import Booking
    from app.utils.enums import BookingStatus, PaymentStatus
    from decimal import Decimal
    from sqlalchemy import and_, func, or_
    profile, error, status = _current_driver()
    if error:
        return jsonify(error), status
    rate = profile.commission_rate
    try:
        rate_pct = float(rate) if rate is not None else 15.0
    except (TypeError, ValueError):
        rate_pct = 15.0
    rate_pct = min(100.0, max(0.0, rate_pct))

    # AssignmentService.release clears assigned_driver_id on completion.
    # The canonical website earnings service therefore attributes completed
    # work through either the live FK or the immutable completion profile
    # recorded in booking_metadata. Keep native totals on that same contract.
    driver_attribution = or_(
        Booking.assigned_driver_id == profile.id,
        and_(
            Booking.booking_metadata.has_key("completed_by_driver_profile_id"),
            Booking.booking_metadata["completed_by_driver_profile_id"].astext == str(profile.id),
        ),
    )
    rows = (
        db.session.query(Booking.currency, func.sum(Booking.final_price))
        .filter(
            driver_attribution,
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
