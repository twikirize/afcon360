"""
Email verification functionality using OTP codes.
"""

from typing import Tuple
from app.extensions import db
from app.auth.otp_service import OTPService
from app.identity.models.user import User

def send_verification_email(user: User) -> bool:
    """
    Generate and send a 6-digit OTP for email verification.

    Args:
        user: The user to send verification email to

    Returns:
        bool: True if OTP was generated and sent successfully
    """
    try:
        # Generate a 6-digit OTP
        otp = OTPService.generate_otp(length=6)

        # Store the OTP with purpose 'email_verification' and TTL of 30 minutes (1800 seconds)
        # Use user's email as identifier
        identifier = user.email
        if not identifier:
            return False

        stored = OTPService.store_otp(
            identifier=identifier,
            otp=otp,
            purpose='email_verification',
            ttl=1800  # 30 minutes
        )

        if not stored:
            return False

        # Send the OTP via email
        success = OTPService.send_email_otp(
            email=user.email,
            otp=otp,
            user_id=user.id
        )

        return success
    except Exception as e:
        # Log the error
        from flask import current_app
        current_app.logger.error(f"Failed to send verification email to user {user.id}: {e}")
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
    try:
        # Get the user to find their email
        user = User.query.get(user_id)
        if not user:
            return False, "User not found"

        # Use email as identifier
        identifier = user.email
        if not identifier:
            return False, "User email not found"

        # Verify the OTP
        success, message = OTPService.verify_otp(
            identifier=identifier,
            otp=code,
            purpose='email_verification'
        )

        if not success:
            return False, message

        # Update verification status
        # Check if the user model has email_verified field
        if hasattr(user, 'email_verified'):
            user.email_verified = True
        # Also set is_verified if the field exists
        if hasattr(user, 'is_verified'):
            user.is_verified = True

        db.session.commit()

        return True, "Email verified successfully"

    except Exception as e:
        db.session.rollback()
        from flask import current_app
        current_app.logger.error(f"Email verification failed for user {user_id}: {e}")
        return False, f"Verification failed: {str(e)}"
