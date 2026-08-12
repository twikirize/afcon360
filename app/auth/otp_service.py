"""
OTP (One-Time Password) service for secure authentication and verification.
"""
import secrets
import hashlib
import hmac
import time
import logging
from typing import Any, Dict, Optional, Tuple

from app.auth.otp_store import (
    store_delete,
    store_get,
    store_set,
    store_ttl,
)

logger = logging.getLogger(__name__)


class OTPService:
    """
    Service for generating, storing, verifying, and sending OTPs.

    Features:
    - Secure random OTP generation using secrets module
    - Hashed storage in cache to prevent OTP leakage
    - Purpose-based verification to prevent OTP reuse across different flows
    - Configurable TTL (time-to-live) for OTP validity
    - Development-friendly email stub that logs OTPs
    """

    @staticmethod
    def generate_otp(length: int = 6) -> str:
        """
        Generate a secure numeric OTP.

        Args:
            length: Number of digits in the OTP (default: 6)

        Returns:
            Numeric string of the specified length
        """
        if length < 4:
            raise ValueError("OTP length must be at least 4 digits")

        # Generate cryptographically secure random digits
        digits = []
        for _ in range(length):
            # secrets.randbelow(10) gives 0-9 inclusive
            digits.append(str(secrets.randbelow(10)))

        return ''.join(digits)

    @staticmethod
    def _pepper() -> str:
        """
        Return the secret used to key OTP hashes.

        Prefers a dedicated ``OTP_PEPPER``, then falls back to the app's
        ``SECRET_KEY``. The literal default is only ever used when running
        outside an application context (e.g. isolated unit tests).
        """
        try:
            from flask import current_app
            if current_app:
                return (
                    current_app.config.get("OTP_PEPPER")
                    or current_app.config.get("SECRET_KEY")
                    or "otp_service_pepper"
                )
        except Exception:
            pass
        return "otp_service_pepper"

    @staticmethod
    def _hash_otp(otp: str) -> str:
        """
        Create a keyed hash of the OTP for storage.

        Uses HMAC-SHA256 with the application secret so a leaked cache dump
        cannot be brute-forced offline against a known constant.

        Args:
            otp: The plain OTP string

        Returns:
            Hex-encoded HMAC-SHA256 digest of the OTP
        """
        return hmac.new(
            OTPService._pepper().encode("utf-8"),
            otp.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    @staticmethod
    def hash_otp(otp: str) -> str:
        """Public wrapper around the internal OTP hashing routine."""
        return OTPService._hash_otp(otp)

    @staticmethod
    def verify_otp_hash(otp: str, expected_hash: str) -> bool:
        """Constant-time comparison of *otp* against a stored hash."""
        if not otp or not expected_hash:
            return False
        return hmac.compare_digest(OTPService._hash_otp(otp), expected_hash)

    @staticmethod
    def store_otp(identifier: str, otp: str, purpose: str, ttl: int = 300) -> bool:
        """
        Store a hashed OTP in cache for later verification.

        Args:
            identifier: Unique identifier (e.g., user_id, email, phone)
            otp: The plain OTP to store (will be hashed)
            purpose: Purpose of the OTP (e.g., 'email_verification', 'password_reset')
            ttl: Time-to-live in seconds (default: 300 = 5 minutes)

        Returns:
            True if stored successfully
        """
        if not identifier or not otp or not purpose:
            raise ValueError("identifier, otp, and purpose are required")

        # Create cache key
        cache_key = f"otp:{identifier}:{purpose}"

        # Hash the OTP before storage
        otp_hash = OTPService._hash_otp(otp)

        # Store with TTL (Redis-backed, with in-memory fallback)
        success = store_set(cache_key, otp_hash, ttl=ttl)

        if success:
            logger.debug(f"Stored OTP for {identifier} with purpose {purpose}, TTL: {ttl}s")
        else:
            logger.error(f"Failed to store OTP for {identifier} with purpose {purpose}")

        return success

    @staticmethod
    def verify_otp(identifier: str, otp: str, purpose: str) -> Tuple[bool, str]:
        """
        Verify an OTP against the stored hash.

        Args:
            identifier: Unique identifier (e.g., user_id, email, phone)
            otp: The OTP to verify
            purpose: Purpose of the OTP (must match the stored purpose)

        Returns:
            Tuple of (success: bool, message: str)
        """
        if not identifier or not otp or not purpose:
            return False, "Missing required parameters"

        cache_key = f"otp:{identifier}:{purpose}"

        # Retrieve stored hash
        stored_hash = store_get(cache_key)

        if not stored_hash:
            return False, "OTP not found or expired"

        # Compare hashes (constant-time comparison for security)
        if OTPService.verify_otp_hash(otp, stored_hash):
            # Delete the OTP after successful verification to prevent reuse
            store_delete(cache_key)
            logger.debug(f"Verified OTP for {identifier} with purpose {purpose}")
            return True, "OTP verified successfully"
        else:
            logger.warning(f"Failed OTP verification for {identifier} with purpose {purpose}")
            return False, "Invalid OTP"

    @staticmethod
    def _dev_fallback_allowed() -> bool:
        """
        True when an OTP may be logged instead of emailed.

        Only in non-production with no mail server configured, or when
        ``OTP_DEV_LOG_FALLBACK`` is explicitly enabled. Production never
        silently swallows a delivery failure.
        """
        try:
            from flask import current_app
            if not current_app:
                return True  # outside an app context (scripts/tests)

            if current_app.config.get("OTP_DEV_LOG_FALLBACK"):
                return True

            env = (current_app.config.get("ENV") or "").lower()
            is_prod = env == "production" or not current_app.config.get("DEBUG", False)
            mail_configured = bool(
                current_app.config.get("MAIL_SERVER")
                or current_app.config.get("SENDGRID_API_KEY")
            )
            return (not is_prod) and (not mail_configured)
        except Exception:
            return True

    @staticmethod
    def _is_permanent_failure(error_text: str) -> bool:
        """Heuristic: does this SMTP error indicate a bad address (5xx)?"""
        if not error_text:
            return False
        lowered = error_text.lower()
        permanent_markers = (
            "550", "551", "553", "554", "5.1.1", "5.1.10",
            "recipient address rejected", "user unknown", "no such user",
            "mailbox unavailable", "does not exist", "invalid recipient",
            "address rejected",
        )
        return any(marker in lowered for marker in permanent_markers)

    @staticmethod
    def send_email_otp_checked(
        email: str,
        otp: str,
        purpose: str = "email_verification",
        user_id: Optional[int] = None,
        max_retries: int = 3,
    ) -> Dict[str, Any]:
        """
        Send an OTP by email and report the *real* delivery outcome.

        Unlike :meth:`send_email_otp` (kept for backward compatibility), this
        never pretends a failed send succeeded. Behaviour:

        * Transient failures are retried with exponential backoff (1s, 2s, 4s).
        * Permanent failures (5xx / unknown recipient) fail fast, no retries.
        * In development with no mail server, the OTP is logged and the result
          is flagged ``dev_fallback`` so the caller can surface it.

        Returns a dict with ``success``, ``message``, ``code`` and
        ``dev_fallback``.
        """
        last_error = ""

        verification_link = "/"
        try:
            from flask import url_for
            link_map = {
                "signup_verification": "auth.verify_signup",
                "email_verification": "auth.verify_email_code",
                "phone_verification": "auth.verify_phone",
            }
            endpoint = link_map.get(purpose)
            if endpoint:
                verification_link = url_for(endpoint, _external=True)
        except Exception:
            verification_link = "/"

        for attempt in range(1, max_retries + 1):
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
                    user_id=user_id,
                    email=email,
                    type=NotificationType.VERIFICATION_EMAIL,
                    channel=NotificationChannel.EMAIL,
                    module=NotificationModule.ACCOUNT,
                    status=NotificationStatus.PENDING,
                    subject="AFCON360 Email Verification Code",
                    body=(
                        f"Your AFCON360 verification code is: {otp}\n"
                        f"Or click this link to verify: {verification_link}\n"
                        f"This code expires shortly. If you didn't request it, ignore this email."
                    ),
                    context={
                        'otp': otp,
                        'verification_code': otp,
                        'user_name': email.split('@')[0],
                        'verification_link': verification_link,
                    },
                    priority='high',
                    link=verification_link,
                )

                result = EmailHandler().deliver(
                    notification,
                    {'email': email, 'user_id': user_id},
                )

                if result.get('success'):
                    logger.info(f"[OTP EMAIL] Delivered verification code to {email}")
                    return {
                        "success": True,
                        "message": "Verification code sent.",
                        "code": "sent",
                        "dev_fallback": False,
                    }

                last_error = str(result.get('response_body') or 'unknown error')

                if OTPService._is_permanent_failure(last_error):
                    logger.warning(
                        f"[OTP EMAIL] Permanent delivery failure for {email}: {last_error}"
                    )
                    break

            except Exception as e:
                last_error = str(e)
                if OTPService._is_permanent_failure(last_error):
                    break

            if attempt < max_retries:
                backoff = 2 ** (attempt - 1)  # 1s, 2s, 4s
                logger.info(
                    f"[OTP EMAIL] Attempt {attempt}/{max_retries} failed for {email} "
                    f"({last_error}); retrying in {backoff}s"
                )
                time.sleep(backoff)

        # All attempts exhausted (or a permanent failure short-circuited).
        if OTPService._dev_fallback_allowed():
            logger.warning(
                f"[OTP EMAIL][DEV] Could not send to {email} ({last_error}). "
                f"OTP for local use: {otp}"
            )
            OTPService._log_dev_magic_link(email, otp, purpose)
            return {
                "success": True,
                "message": "Verification code generated (development mode - see server logs).",
                "code": "dev_fallback",
                "dev_fallback": True,
            }

        OTPService._alert_delivery_failure(email, last_error)

        if OTPService._is_permanent_failure(last_error):
            message = (
                "That email address was rejected by the mail server. "
                "Please check the spelling or use a different address."
            )
            code = "undeliverable"
        else:
            message = (
                "We're having trouble sending verification codes right now. "
                "Please try again in a couple of minutes."
            )
            code = "delivery_failed"

        logger.error(f"[OTP EMAIL] Giving up on {email}: {last_error}")
        return {
            "success": False,
            "message": message,
            "code": code,
            "dev_fallback": False,
            "error": last_error,
        }

    @staticmethod
    def _log_dev_magic_link(email: str, otp: str, purpose: str) -> None:
        """Log a one-click verification URL to speed up local development."""
        try:
            from flask import current_app, request

            if not current_app or not current_app.config.get("DEBUG", False):
                return

            try:
                base = request.host_url.rstrip("/")
            except Exception:
                base = "http://127.0.0.1:5000"

            logger.warning(
                "[DEV] OTP for %s: %s\n[DEV] Auto-verify: %s/verify-signup?code=%s",
                email, otp, base, otp,
            )
        except Exception:
            pass

    @staticmethod
    def _alert_delivery_failure(email: str, error: str) -> None:
        """
        Track OTP delivery failures and alert ops when the rate spikes.

        Increments a rolling counter; once failures cross the configured
        threshold inside the window, emit a single loud CRITICAL log (which
        existing log-based alerting can route to Slack/PagerDuty).
        """
        try:
            from app.auth.otp_store import store_incr

            window = 300  # 5 minutes
            failures = store_incr("otp:failures:email", ttl=window)
            threshold = 10

            try:
                from flask import current_app
                if current_app:
                    threshold = current_app.config.get("OTP_FAILURE_ALERT_THRESHOLD", 10)
            except Exception:
                pass

            if failures == threshold:
                logger.critical(
                    "OTP delivery failure spike: %d failures in the last %d seconds. "
                    "Check SMTP/SendGrid credentials and quota. Latest error: %s",
                    failures, window, error,
                )
        except Exception:
            pass

    @staticmethod
    def send_email_otp(email: str, otp: str, user_id: Optional[int] = None) -> bool:
        """
        Send the email-verification OTP to the recipient.

        .. deprecated::
            Prefer :meth:`send_email_otp_checked`, which reports genuine
            delivery status. This wrapper is retained for existing callers and
            now returns the real outcome instead of always ``True``.

        Args:
            email: Recipient email address
            otp: The OTP to send
            user_id: Optional internal user ID for logging/linking

        Returns:
            True if the message was delivered (or logged via the dev fallback).
        """
        result = OTPService.send_email_otp_checked(
            email=email,
            otp=otp,
            user_id=user_id,
        )
        return bool(result.get("success"))

    @staticmethod
    def invalidate_otp(identifier: str, purpose: str) -> bool:
        """
        Discard a stored OTP.

        Used when delivery fails, so a code the user can never receive is not
        left occupying the store until it expires.
        """
        if not identifier or not purpose:
            return False
        return store_delete(f"otp:{identifier}:{purpose}")

    @staticmethod
    def get_remaining_ttl(identifier: str, purpose: str) -> int:
        """
        Get remaining time-to-live for an OTP.

        Args:
            identifier: Unique identifier
            purpose: Purpose of the OTP

        Returns:
            Remaining TTL in seconds, or -2 if key doesn't exist, -1 if no expiry
        """
        cache_key = f"otp:{identifier}:{purpose}"
        return store_ttl(cache_key)

    @staticmethod
    def generate_sms_otp(length: int = 6) -> str:
        """Generate SMS OTP using generate_otp."""
        return OTPService.generate_otp(length)

    @staticmethod
    def send_sms_otp(phone: str, otp: str, internal_user_id: Optional[int] = None) -> Tuple[bool, Optional[str]]:
        """
        Store via store_otp(phone, otp, "sms_verification"), then send via app.notifications.sms_service.send_sms.
        Returns (success_bool, otp). If send_sms raises/returns non-success, return (False, None).
        """
        if not phone:
            return False, None
        stored = OTPService.store_otp(identifier=phone, otp=otp, purpose="sms_verification", ttl=300)
        if not stored:
            return False, None
        try:
            from app.notifications.sms_service import send_sms
            success = send_sms(phone, f"Your AFCON360 code: {otp}")
            if success:
                return True, otp
            else:
                OTPService.invalidate_otp(phone, "sms_verification")
                return False, None
        except Exception as e:
            logger.error(f"[SMS OTP] Failed to send SMS to {phone}: {e}")
            OTPService.invalidate_otp(phone, "sms_verification")
            return False, None

    @staticmethod
    def verify_sms_otp(phone: str, otp: str, internal_user_id: Optional[int] = None) -> bool:
        """
        Verify SMS OTP. Use identifier = internal_user_id if provided else phone.
        """
        identifier = str(internal_user_id) if internal_user_id is not None else phone
        if not identifier or not otp:
            return False
        return OTPService.verify_otp(identifier=identifier, otp=otp, purpose="sms_verification")


# Global instance for easy import
otp_service = OTPService()
