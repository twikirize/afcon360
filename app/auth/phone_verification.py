"""Phone verification orchestration with owner-selectable delivery transport."""

from datetime import datetime, timezone
from typing import Any, Dict, Tuple

from app.auth.otp_service import OTPService
from app.auth.config_model import AuthConfiguration
from app.extensions import db
from app.notifications.sms_service import SMSService


PHONE_VERIFICATION_PURPOSE = "phone_verification"
PHONE_VERIFICATION_TTL = 300


class PhoneVerificationService:
    """Coordinate phone verification independently of its delivery transport."""

    @staticmethod
    def request_code(user, profile, phone_number: str) -> Dict[str, Any]:
        """Generate and deliver a phone OTP through the configured transport."""
        email = (getattr(user, "email", "") or "").strip()
        phone_number = (phone_number or "").strip()

        if not phone_number:
            return {
                "success": False,
                "code": "missing_phone",
                "message": "Please provide a phone number.",
            }
        if not email:
            return {
                "success": False,
                "code": "missing_email",
                "message": "No email address found on your account.",
            }

        profile_changed = profile is not None and phone_number != getattr(profile, "phone_number", None)
        user_changed = phone_number != getattr(user, "phone", None)
        if profile_changed or user_changed:
            try:
                if profile_changed:
                    profile.phone_number = phone_number
                if user_changed:
                    user.phone = phone_number
                db.session.commit()
            except Exception:
                db.session.rollback()
                return {
                    "success": False,
                    "code": "profile_update_failed",
                    "message": "Unable to save your phone number. Please try again.",
                }

        otp = OTPService.generate_otp(length=6)
        if not OTPService.store_otp(
            identifier=email,
            otp=otp,
            purpose=PHONE_VERIFICATION_PURPOSE,
            ttl=PHONE_VERIFICATION_TTL,
        ):
            return {
                "success": False,
                "code": "storage_failed",
                "message": "Failed to generate verification code. Please try again.",
            }

        try:
            config = AuthConfiguration.get_config()
            transport = config.get_phone_verification_transport()
        except Exception:
            config = None
            transport = "email"

        if transport == "sms":
            result = PhoneVerificationService._send_sms_code(
                config=config,
                phone_number=phone_number,
                otp=otp,
            )
        else:
            result = OTPService.send_email_otp_checked(
                email=email,
                otp=otp,
                purpose=PHONE_VERIFICATION_PURPOSE,
                user_id=getattr(user, "id", None),
            )
            result["transport"] = "email"

        if not result.get("success"):
            OTPService.invalidate_otp(email, PHONE_VERIFICATION_PURPOSE)
        return result

    @staticmethod
    def _send_sms_code(config, phone_number: str, otp: str) -> Dict[str, Any]:
        """Send an OTP through a configured provider, never through console fallback."""
        if config is None:
            return {
                "success": False,
                "code": "sms_unavailable",
                "message": "SMS verification is not configured. Select email or configure an SMS provider.",
                "transport": "sms",
            }

        try:
            provider = config.get_sms_provider_for_phone(phone_number)
            if not provider:
                return {
                    "success": False,
                    "code": "sms_unavailable",
                    "message": "SMS verification is not available because no SMS provider is configured.",
                    "transport": "sms",
                }

            result = SMSService(provider=provider, auth_config=config).send_message(
                phone_number=phone_number,
                message=f"Your AFCON360 phone verification code is: {otp}",
            )
            result["transport"] = "sms"
            return result
        except Exception:
            return {
                "success": False,
                "code": "sms_delivery_failed",
                "message": "SMS delivery failed. Select email or check the SMS provider settings.",
                "transport": "sms",
            }

    @staticmethod
    def verify_code(user, profile, code: str) -> Tuple[bool, str]:
        """Consume a valid phone OTP and update both identity verification flags."""
        email = (getattr(user, "email", "") or "").strip()
        code = (code or "").strip()
        if not email or not code:
            return False, "Missing required parameters"

        success, message = OTPService.verify_otp(
            identifier=email,
            otp=code,
            purpose=PHONE_VERIFICATION_PURPOSE,
        )
        if not success:
            return False, message

        try:
            now = datetime.now(timezone.utc)
            user.phone_verified = True
            user.phone_verified_at = now
            if profile is not None:
                profile.phone_verified = True
            db.session.commit()
        except Exception:
            db.session.rollback()
            return False, "Unable to save phone verification. Please try again."

        return True, message