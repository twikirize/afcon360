"""
Email verification functionality using OTP codes.

Used for *existing* accounts - resending a verification code, or verifying an
address changed after signup.

New sign-ups do not go through here: they use
``app.auth.pending_registration``, which withholds account creation until the
OTP proves the inbox is real, so unverified addresses never reach the database.
"""

from datetime import datetime, timezone
from typing import Tuple, cast

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
        identifier = str(user.email or "")
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
            email=identifier,
            otp=otp,
            purpose=_PURPOSE,
            user_id=cast(int, user.id),
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


def send_password_reset_email(user: User, token: str) -> bool:
    """
    Send the password-reset link to the user's email address.

    Returns True only when the mail server accepted the message, so callers
    never tell the user a link was sent when delivery actually failed.
    """
    from flask import current_app, url_for

    if user is None or not token:
        return False

    recipient = str(user.email or "")
    if not recipient:
        return False

    try:
        reset_link = url_for("auth.reset_password", token=token, _external=True)

        from app.notifications.models import (
            Notification,
            NotificationType,
            NotificationChannel,
            NotificationModule,
            NotificationStatus,
        )
        from app.notifications.channel_handlers.email import EmailHandler

        notification = Notification(
            user_id=cast(int, user.id),
            email=recipient,
            type=NotificationType.PASSWORD_RESET,
            channel=NotificationChannel.EMAIL,
            module=NotificationModule.ACCOUNT,
            status=NotificationStatus.PENDING,
            subject="Reset your AFCON360 password",
            body=(
                f"Use this link to reset your AFCON360 password: {reset_link}\n"
                "The link expires in 1 hour. If you did not request it, ignore this email."
            ),
            context={
                "user_name": user.display_name or user.username,
                "reset_link": reset_link,
                "expires_in_minutes": 60,
            },
            priority="high",
            link=reset_link,
        )
        db.session.add(notification)
        db.session.flush()

        result = EmailHandler().deliver(
            notification,
            {"email": recipient, "user_id": cast(int, user.id)},
        )
        if not result.get("success"):
            db.session.rollback()
            current_app.logger.warning(
                "Password reset email to %s failed: %s",
                user.public_id, result.get("response_body") or result.get("response_code"),
            )
            return False

        notification.mark_delivered()
        db.session.commit()
        return True

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(
            f"Failed to send password reset email to user {user.public_id}: {e}"
        )
        return False


def send_pin_reset_otp_email(user: User, otp: str) -> bool:
    """Send a transaction-PIN reset code to the user's verified email address.

    Returns True only when the mail server accepted the message, so the caller
    never tells the user a code was sent when delivery actually failed.
    """
    from flask import current_app

    if user is None or not otp:
        return False

    recipient = str(user.email or "")
    if not recipient or not getattr(user, "email_verified", False):
        return False

    try:
        from app.notifications.models import (
            Notification,
            NotificationType,
            NotificationChannel,
            NotificationModule,
            NotificationStatus,
        )
        from app.notifications.channel_handlers.email import EmailHandler

        notification = Notification(
            user_id=cast(int, user.id),
            email=recipient,
            type=NotificationType.VERIFICATION_EMAIL,
            channel=NotificationChannel.EMAIL,
            module=NotificationModule.ACCOUNT,
            status=NotificationStatus.PENDING,
            subject="Your AFCON360 wallet PIN reset code",
            body=(
                f"Your AFCON360 wallet PIN reset code is: {otp}\n"
                "It expires in 5 minutes. If you did not request it, ignore this "
                "email and your PIN stays unchanged."
            ),
            context={
                "user_name": user.display_name or user.username,
                "otp": otp,
                "verification_code": otp,
                "expires_in_minutes": 5,
            },
            priority="high",
        )
        db.session.add(notification)
        db.session.flush()

        result = EmailHandler().deliver(
            notification,
            {"email": recipient, "user_id": cast(int, user.id)},
        )
        if not result.get("success"):
            db.session.rollback()
            current_app.logger.warning(
                "Wallet PIN reset email to %s failed: %s",
                user.public_id,
                result.get("response_body") or result.get("response_code"),
            )
            return False

        notification.mark_delivered()
        db.session.commit()
        return True

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(
            f"Failed to send wallet PIN reset email to user {user.public_id}: {e}"
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

        identifier = str(user.email or "")
        if not identifier:
            return False, "User email not found"

        success, message = OTPService.verify_otp(
            identifier=identifier,
            otp=code,
            purpose=_PURPOSE,
        )

        if not success:
            return False, message

        setattr(user, "email_verified", True)
        setattr(user, "is_verified", True)
        if hasattr(user, "email_verified_at") and not getattr(user, "email_verified_at", None):
            setattr(user, "email_verified_at", datetime.now(timezone.utc))

        db.session.commit()

        return True, "Email verified successfully"

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Email verification failed for user {user_id}: {e}")
        return False, f"Verification failed: {str(e)}"
