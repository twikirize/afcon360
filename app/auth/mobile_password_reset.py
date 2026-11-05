"""Native email-code password reset using AFCON360's shared auth records."""

from __future__ import annotations

import logging

from sqlalchemy import func, or_

from app.auth.otp_store import store_delete, store_incr
from app.extensions import db

logger = logging.getLogger(__name__)

PASSWORD_RESET_OTP_TTL_SECONDS = 10 * 60
PASSWORD_RESET_OTP_PURPOSE = "mobile_password_reset"
PASSWORD_RESET_MAX_ATTEMPTS = 5


def _find_user(identifier: str):
    from app.identity.models.user import User

    normalized = (identifier or "").strip().lower()
    if not normalized:
        return None
    return User.query.filter(
        or_(
            func.lower(User.username) == normalized,
            func.lower(User.email) == normalized,
        )
    ).first()


def request_mobile_password_reset(identifier: str) -> bool:
    """Send a generic, short-lived password-reset code without account disclosure."""
    user = _find_user(identifier)
    if (
        user is None
        or not getattr(user, "is_active", True)
        or getattr(user, "is_deleted", False)
        or not getattr(user, "email", None)
    ):
        return False

    from app.auth.otp_service import OTPService

    otp = OTPService.generate_otp(length=6)
    otp_identifier = str(user.public_id)
    stored = OTPService.store_otp(
        identifier=otp_identifier,
        otp=otp,
        purpose=PASSWORD_RESET_OTP_PURPOSE,
        ttl=PASSWORD_RESET_OTP_TTL_SECONDS,
    )
    if not stored:
        logger.error("Could not store password-reset OTP for user %s", user.public_id)
        return False

    result = OTPService.send_email_otp_checked(
        email=user.email,
        otp=otp,
        purpose="password_reset",
        user_id=user.id,
        expires_in_minutes=10,
    )
    if not result.get("success"):
        OTPService.invalidate_otp(otp_identifier, PASSWORD_RESET_OTP_PURPOSE)
        logger.warning(
            "Password-reset code delivery failed for user %s: %s",
            user.public_id,
            result.get("code") or "delivery_failed",
        )
        return False
    return True


def confirm_mobile_password_reset(
    identifier: str,
    code: str,
    new_password: str,
) -> tuple[bool, str]:
    """Verify one OTP, change the password and invalidate every existing session."""
    user = _find_user(identifier)
    if (
        user is None
        or not getattr(user, "is_active", True)
        or getattr(user, "is_deleted", False)
        or not getattr(user, "email", None)
    ):
        return False, "The code is invalid or expired. Request a new code."

    from app.auth.validators import validate_password_strength

    valid, message = validate_password_strength(new_password)
    if not valid:
        return False, message

    from app.auth.otp_service import OTPService

    otp_identifier = str(user.public_id)
    attempt_key = f"mobile-password-reset:attempts:{otp_identifier}"
    attempts = store_incr(attempt_key, ttl=PASSWORD_RESET_OTP_TTL_SECONDS)
    if attempts > PASSWORD_RESET_MAX_ATTEMPTS:
        OTPService.invalidate_otp(otp_identifier, PASSWORD_RESET_OTP_PURPOSE)
        store_delete(attempt_key)
        return False, "Too many incorrect codes. Request a new code."

    verified, _message = OTPService.verify_otp(
        identifier=otp_identifier,
        otp=(code or "").strip(),
        purpose=PASSWORD_RESET_OTP_PURPOSE,
    )
    if not verified:
        return False, "The code is invalid or expired. Check it and try again."

    store_delete(attempt_key)

    # Reuse the canonical signed-token password-change service so password
    # timestamping, audit events and server-session revocation stay central.
    from app.auth.tokens import generate_reset_token
    from app.auth.services import confirm_password_reset

    reset_token = generate_reset_token(str(user.public_id))
    if not confirm_password_reset(reset_token, new_password):
        db.session.rollback()
        return False, "AFCON360 could not complete the password reset. Request a new code."

    # Native device sessions also have Identity Session rows. ServerSession
    # revocation above already makes native bearer tokens fail closed; revoke
    # device rows as well for accurate device-security state and audit.
    try:
        from app.auth.sessions import revoke_all_device_sessions_for_user
        revoke_all_device_sessions_for_user(user.id, reason="password_reset")
    except Exception:
        logger.exception(
            "Password changed and server sessions revoked, but device-session cleanup failed for %s",
            user.public_id,
        )

    return True, "Your password has been reset. Sign in with your new password."
