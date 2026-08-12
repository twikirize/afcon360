"""
Email verification functionality using OTP codes.

Used for *existing* accounts - resending a verification code, or verifying an
address changed after signup.

New sign-ups do not go through here: they use
``app.auth.pending_registration``, which withholds account creation until the
OTP proves the inbox is real, so unverified addresses never reach the database.
"""

from datetime import datetime, timezone
from typing import Tuple

from app.extensions import db
from app.auth.otp_service import OTPService
from app.identity.models.user import User

#: How long an email-verification OTP stays valid, in seconds.
EMAIL_OTP_TTL = 1800  # 30 minutes

_PURPOSE = "email_verification"


def send_verification_email(user: User) -> bool:
    """
    Generate and send a 6-digit OTP for email verification.

    Args:
        user: The user to send verification email to

    Returns:
        bool: True if the OTP was stored *and* delivered. Unlike the previous
        implementation, a failed send now reports False rather than pretending
        to have succeeded.
    """
    from flask import current_app

    try:
        identifier = user.email
        if not identifier:
            return False

        otp = OTPService.generate_otp(length=6)

        stored = OTPService.store_otp(
            identifier=identifier,
            otp=otp,
            purpose=_PURPOSE,
            ttl=EMAIL_OTP_TTL,
        )
        if not stored:
            current_app.logger.error(
                "Could not store email verification OTP for user %s", user.public_id
            )
            return False

        result = OTPService.send_email_otp_checked(
            email=user.email,
            otp=otp,
            purpose=_PURPOSE,
            user_id=user.id,
        )

        if not result.get("success"):
            # Don't leave an OTP the user can never receive.
            OTPService.invalidate_otp(identifier, _PURPOSE)
            current_app.logger.warning(
                "Verification email to %s failed: %s",
                user.public_id, result.get("error") or result.get("code"),
            )
            return False

        return True

    except Exception as e:
        current_app.logger.error(
            f"Failed to send verification email to user {user.public_id}: {e}"
        )
        return False


def verify_email_code(user_id: int, code: str) -> Tuple[bool, str]:
    """
    Verify the email verification OTP code.

    Args:
        user_id: The user's internal ID (BIGINT)
        code: The 6-digit OTP code to verify

    Returns:
        Tuple[bool, str]: (success, message)
    """
    from flask import current_app

    code = (code or "").strip()
    if not code.isdigit() or len(code) != 6:
        return False, "Please enter the 6-digit code from your email."

    try:
        user = db.session.get(User, user_id)
        if not user:
            return False, "User not found"

        identifier = user.email
        if not identifier:
            return False, "User email not found"

        success, message = OTPService.verify_otp(
            identifier=identifier,
            otp=code,
            purpose=_PURPOSE,
        )

        if not success:
            return False, message

        user.email_verified = True
        user.is_verified = True
        if hasattr(user, "email_verified_at") and not getattr(user, "email_verified_at", None):
            user.email_verified_at = datetime.now(timezone.utc)

        db.session.commit()

        return True, "Email verified successfully"

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Email verification failed for user {user_id}: {e}")
        return False, f"Verification failed: {str(e)}"
