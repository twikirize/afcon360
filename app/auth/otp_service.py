"""
OTP (One-Time Password) service for secure authentication and verification.
"""
import secrets
import hashlib
import time
import logging
from typing import Optional, Tuple

from app.extensions import cache

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
    def _hash_otp(otp: str) -> str:
        """
        Create a secure hash of the OTP for storage.

        Args:
            otp: The plain OTP string

        Returns:
            SHA256 hash of the OTP
        """
        # Add a pepper to the hash (in production this should be from config)
        pepper = "otp_service_pepper"  # In production, use a secure secret from config
        data = f"{otp}:{pepper}"
        return hashlib.sha256(data.encode('utf-8')).hexdigest()

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

        # Store with TTL
        success = cache.set(cache_key, otp_hash, ex=ttl)

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
        stored_hash = cache.get(cache_key)

        if not stored_hash:
            return False, "OTP not found or expired"

        # Hash the provided OTP
        provided_hash = OTPService._hash_otp(otp)

        # Compare hashes (constant-time comparison for security)
        if secrets.compare_digest(stored_hash, provided_hash):
            # Delete the OTP after successful verification to prevent reuse
            cache.delete(cache_key)
            logger.debug(f"Verified OTP for {identifier} with purpose {purpose}")
            return True, "OTP verified successfully"
        else:
            logger.warning(f"Failed OTP verification for {identifier} with purpose {purpose}")
            return False, "Invalid OTP"

    @staticmethod
    def send_email_otp(email: str, otp: str, user_id: Optional[int] = None) -> bool:
        """
        Stub method for sending OTP via email (for development).

        In production, this should integrate with a real email service.

        Args:
            email: Recipient email address
            otp: The OTP to send
            user_id: Optional user ID for logging

        Returns:
            True (stub always succeeds in development)
        """
        # Log the OTP instead of actually sending email (for development)
        logger.info(
            f"[OTP EMAIL STUB] OTP for user_id={user_id}, email={email}: {otp}\n"
            f"In production, this would be sent via email service."
        )

        # In a real implementation, you would:
        # 1. Prepare email template with OTP
        # 2. Send via SMTP, SendGrid, AWS SES, etc.
        # 3. Handle errors and retries

        # For now, just return success
        return True

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
        return cache.ttl(cache_key) or 0


# Global instance for easy import
otp_service = OTPService()
