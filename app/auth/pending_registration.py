"""
Pending-registration service: prove the inbox *before* creating the account.

Flow
----
1. ``start_pending_registration()`` validates the email, enforces rate limits,
   hashes the password, stores the payload in Redis under a random token, and
   emails a 6-digit OTP. **No database row is created.**
2. ``verify_pending_registration()`` checks the OTP (with an attempt cage),
   then atomically creates the ``User`` inside a transaction that tolerates
   concurrent duplicates.
3. Unverified signups simply expire out of Redis - fake addresses never touch
   the ``users`` table nor consume its unique index.

Protections
-----------
* Attempt cage - 5 wrong OTPs destroys the payload (kills brute force).
* Dual rate limiting - per normalised email and per client IP.
* Rolling TTL - active users get a grace extension up to a hard ceiling.
* Race-safe creation - locking + ``IntegrityError`` handling means parallel
  verifications converge on one account instead of erroring.
"""

from __future__ import annotations

import hashlib
import logging
import secrets
import time
import uuid
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

from werkzeug.security import generate_password_hash

from app.auth.otp_store import (
    store_delete,
    store_expire,
    store_get,
    store_incr,
    store_set,
    store_ttl,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tunables (overridable via Flask config)
# ---------------------------------------------------------------------------

DEFAULT_OTP_TTL = 600              # 10 minutes
DEFAULT_MAX_LIFETIME = 900         # 15 minute hard ceiling for TTL extensions
DEFAULT_KEEPALIVE_EXTENSION = 120  # +2 minutes per heartbeat
DEFAULT_MAX_ATTEMPTS = 5
DEFAULT_EMAIL_RATE_LIMIT = 3       # sends per window, per email
DEFAULT_IP_RATE_LIMIT = 10         # sends per window, per IP
DEFAULT_RATE_WINDOW = 900          # 15 minutes

_PENDING_PREFIX = "pending_signup:"
_EMAIL_INDEX_PREFIX = "pending_signup_email:"
_EMAIL_RATE_PREFIX = "rate:signup:email:"
_IP_RATE_PREFIX = "rate:signup:ip:"


def _cfg(key: str, default):
    try:
        from flask import current_app
        if current_app:
            return current_app.config.get(key, default)
    except Exception:
        pass
    return default


def _otp_ttl() -> int:
    return int(_cfg("SIGNUP_OTP_TTL", DEFAULT_OTP_TTL))


def _max_lifetime() -> int:
    return int(_cfg("SIGNUP_OTP_MAX_LIFETIME", DEFAULT_MAX_LIFETIME))


def _max_attempts() -> int:
    return int(_cfg("SIGNUP_OTP_MAX_ATTEMPTS", DEFAULT_MAX_ATTEMPTS))


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

@dataclass
class PendingResult:
    """Outcome of starting or resending a pending registration."""

    success: bool
    token: Optional[str] = None
    message: str = ""
    code: Optional[str] = None
    suggestion: Optional[str] = None
    retry_after: Optional[int] = None
    email: Optional[str] = None
    #: Dev-only: the OTP, surfaced when the log-only fallback is active.
    debug_otp: Optional[str] = None


@dataclass
class VerifyResult:
    """Outcome of verifying a pending registration's OTP."""

    success: bool
    user: Any = None
    message: str = ""
    code: Optional[str] = None
    remaining_attempts: Optional[int] = None
    already_existed: bool = False


# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------

def _rate_limit_check(email: str, ip: Optional[str]) -> Optional[PendingResult]:
    """
    Enforce per-email and per-IP send limits.

    Returns a failing :class:`PendingResult` when a limit is exceeded, else
    ``None``. Counters are incremented as a side effect.
    """
    window = int(_cfg("SIGNUP_RATE_WINDOW", DEFAULT_RATE_WINDOW))
    email_limit = int(_cfg("SIGNUP_EMAIL_RATE_LIMIT", DEFAULT_EMAIL_RATE_LIMIT))
    ip_limit = int(_cfg("SIGNUP_IP_RATE_LIMIT", DEFAULT_IP_RATE_LIMIT))

    email_key = f"{_EMAIL_RATE_PREFIX}{hashlib.sha256(email.encode()).hexdigest()}"
    count = store_incr(email_key, ttl=window)
    if count > email_limit:
        retry_after = max(store_ttl(email_key), 0)
        logger.warning("Signup OTP rate limit hit for email hash %s", email_key[-12:])
        return PendingResult(
            False,
            message=(
                "Too many verification codes requested for this email. "
                f"Please try again in {max(1, retry_after // 60)} minute(s)."
            ),
            code="rate_limited_email",
            retry_after=retry_after,
        )

    if ip:
        ip_key = f"{_IP_RATE_PREFIX}{ip}"
        ip_count = store_incr(ip_key, ttl=window)
        if ip_count > ip_limit:
            retry_after = max(store_ttl(ip_key), 0)
            logger.warning("Signup OTP rate limit hit for IP %s", ip)
            return PendingResult(
                False,
                message=(
                    "Too many sign-up attempts from this network. "
                    f"Please try again in {max(1, retry_after // 60)} minute(s)."
                ),
                code="rate_limited_ip",
                retry_after=retry_after,
            )

    return None


# ---------------------------------------------------------------------------
# Uniqueness pre-check
# ---------------------------------------------------------------------------

def _email_taken(normalized_email: str) -> bool:
    from app.identity.models.user import User
    return User.query.filter_by(email=normalized_email).first() is not None


def _username_taken(username: str) -> bool:
    from app.identity.models.user import User
    return User.query.filter_by(username=username).first() is not None


# ---------------------------------------------------------------------------
# Start / resend
# ---------------------------------------------------------------------------

def start_pending_registration(
    *,
    username: str,
    password: str,
    email: str,
    full_name: Optional[str] = None,
    ip: Optional[str] = None,
    user_agent: Optional[str] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> PendingResult:
    """
    Validate the signup, stash it in Redis, and send a verification OTP.

    No ``User`` row is created here. On success the returned
    :class:`PendingResult` carries the opaque ``token`` the caller must keep
    (in the session) to complete verification.
    """
    from app.auth.email_validation import validate_email_address

    # --- 1. Email validation (syntax, role, disposable, MX) ---------------
    validation = validate_email_address(email)
    if not validation.is_valid:
        return PendingResult(
            False,
            message=validation.message,
            code=validation.code,
            suggestion=validation.suggestion,
        )

    normalized_email = validation.normalized

    # --- 2. Uniqueness (friendly pre-check; DB constraint is the backstop) -
    if _email_taken(normalized_email):
        return PendingResult(
            False,
            message="An account with this email already exists. Please log in or reset your password.",
            code="email_exists",
            email=normalized_email,
        )

    if _username_taken(username):
        return PendingResult(
            False,
            message=f"The username '{username}' is already taken.",
            code="username_exists",
        )

    # --- 3. Rate limiting --------------------------------------------------
    limited = _rate_limit_check(normalized_email, ip)
    if limited:
        limited.email = normalized_email
        return limited

    # --- 4. Build and store the pending payload ---------------------------
    from app.auth.otp_service import OTPService

    otp = OTPService.generate_otp(length=6)
    token = secrets.token_urlsafe(32)
    now = time.time()
    ttl = _otp_ttl()

    payload = {
        "username": username,
        "email": normalized_email,
        "email_as_entered": email.strip(),
        "phone": extra.get("phone") if extra else None,
        "password_hash": generate_password_hash(password),
        "full_name": full_name or username,
        "otp_hash": OTPService.hash_otp(otp),
        "channel": "email",
        "attempts": 0,
        "created_at": now,
        "expires_at": now + ttl,
        "hard_expires_at": now + _max_lifetime(),
        "ip": ip,
        "user_agent": user_agent,
        "mx_unverified": validation.mx_unverified,
        "extra": extra or {},
    }

    if not store_set(f"{_PENDING_PREFIX}{token}", payload, ttl=ttl):
        logger.error("Failed to persist pending registration for %s", normalized_email)
        return PendingResult(
            False,
            message="We couldn't start verification right now. Please try again.",
            code="store_failure",
        )

    # Index by email so a resend can find (and replace) the existing payload.
    store_set(
        f"{_EMAIL_INDEX_PREFIX}{hashlib.sha256(normalized_email.encode()).hexdigest()}",
        token,
        ttl=ttl,
    )

    # --- 5. Deliver the OTP ------------------------------------------------
    delivery = OTPService.send_email_otp_checked(
        email=normalized_email,
        otp=otp,
        purpose="signup_verification",
    )

    if not delivery.get("success"):
        # Don't leave an unusable payload behind - the user cannot verify it.
        store_delete(f"{_PENDING_PREFIX}{token}")
        return PendingResult(
            False,
            message=delivery.get("message")
            or "We couldn't send the verification code. Please check the address and try again.",
            code=delivery.get("code", "delivery_failed"),
            email=normalized_email,
        )

    logger.info("Pending registration started for %s (token %s...)", normalized_email, token[:8])

    return PendingResult(
        True,
        token=token,
        email=normalized_email,
        message=f"We've sent a 6-digit verification code to {normalized_email}.",
        debug_otp=otp if delivery.get("dev_fallback") else None,
    )


def resend_pending_otp(token: str, ip: Optional[str] = None) -> PendingResult:
    """
    Issue a fresh OTP for an existing pending registration.

    Used by the "silent resync" path: when a code expires, the browser replays
    the stored signup data instead of making the user retype the form.
    """
    payload = store_get(f"{_PENDING_PREFIX}{token}")
    if not payload:
        return PendingResult(
            False,
            message="Your verification session has expired. Please sign up again.",
            code="expired",
        )

    email = payload.get("email")

    limited = _rate_limit_check(email, ip)
    if limited:
        limited.email = email
        return limited

    from app.auth.otp_service import OTPService

    otp = OTPService.generate_otp(length=6)
    ttl = _otp_ttl()
    now = time.time()

    payload["otp_hash"] = OTPService.hash_otp(otp)
    payload["attempts"] = 0  # fresh code, fresh attempt budget
    payload["expires_at"] = now + ttl
    payload["hard_expires_at"] = max(
        payload.get("hard_expires_at", now + _max_lifetime()),
        now + ttl,
    )
    store_set(f"{_PENDING_PREFIX}{token}", payload, ttl=ttl)

    delivery = OTPService.send_email_otp_checked(
        email=email,
        otp=otp,
        purpose="signup_verification",
    )
    if not delivery.get("success"):
        return PendingResult(
            False,
            message=delivery.get("message") or "We couldn't resend the code. Please try again shortly.",
            code=delivery.get("code", "delivery_failed"),
            email=email,
        )

    return PendingResult(
        True,
        token=token,
        email=email,
        message=f"A new verification code has been sent to {email}.",
        debug_otp=otp if delivery.get("dev_fallback") else None,
    )


def restart_pending_registration(
    *,
    token: Optional[str],
    ip: Optional[str] = None,
) -> PendingResult:
    """Resend for *token*, mapping a missing payload to a clear error."""
    if not token:
        return PendingResult(
            False,
            message="Your verification session has expired. Please sign up again.",
            code="expired",
        )
    return resend_pending_otp(token, ip=ip)


# ---------------------------------------------------------------------------
# Keep-alive (rolling TTL)
# ---------------------------------------------------------------------------

def touch_pending_registration(token: str) -> Tuple[bool, int]:
    """
    Extend a pending registration while the user is actively verifying.

    Adds ``SIGNUP_OTP_KEEPALIVE`` seconds, never exceeding the hard lifetime
    ceiling set when the signup began. Returns ``(extended, seconds_left)``.
    """
    key = f"{_PENDING_PREFIX}{token}"
    payload = store_get(key)
    if not payload:
        return False, 0

    now = time.time()
    hard_deadline = payload.get("hard_expires_at", now)
    if now >= hard_deadline:
        return False, max(0, store_ttl(key))

    extension = int(_cfg("SIGNUP_OTP_KEEPALIVE", DEFAULT_KEEPALIVE_EXTENSION))
    new_expiry = min(now + extension, hard_deadline)
    new_ttl = int(new_expiry - now)
    if new_ttl <= 0:
        return False, 0

    payload["expires_at"] = new_expiry
    store_set(key, payload, ttl=new_ttl)
    store_expire(key, new_ttl)
    return True, new_ttl


def get_pending_registration(token: str) -> Optional[Dict[str, Any]]:
    """Return the stored payload for *token* without exposing secrets."""
    payload = store_get(f"{_PENDING_PREFIX}{token}")
    if not payload:
        return None
    safe = dict(payload)
    safe.pop("password_hash", None)
    safe.pop("otp_hash", None)
    return safe


def discard_pending_registration(token: str) -> bool:
    """Delete a pending registration (user cancelled or completed)."""
    return store_delete(f"{_PENDING_PREFIX}{token}")


# ---------------------------------------------------------------------------
# Verify + create
# ---------------------------------------------------------------------------

def verify_pending_registration(
    token: str,
    otp: str,
    *,
    channel: str = "email",
    ip: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> VerifyResult:
    """
    Verify *otp* and, on success, atomically create the verified ``User``.

    Enforces the attempt cage: after ``SIGNUP_OTP_MAX_ATTEMPTS`` wrong codes
    the payload is destroyed and the user must start over.
    """
    from app.auth.otp_service import OTPService

    key = f"{_PENDING_PREFIX}{token}"
    payload = store_get(key)

    if not payload:
        return VerifyResult(
            False,
            message="Your verification code has expired. Please request a new one.",
            code="expired",
        )

    otp = (otp or "").strip()
    if not otp.isdigit() or len(otp) != 6:
        return VerifyResult(
            False,
            message="Please enter the 6-digit code from your email.",
            code="malformed",
            remaining_attempts=_max_attempts() - int(payload.get("attempts", 0)),
        )

    # --- Attempt cage ------------------------------------------------------
    if not OTPService.verify_otp_hash(otp, payload.get("otp_hash", "")):
        attempts = int(payload.get("attempts", 0)) + 1
        max_attempts = _max_attempts()

        if attempts >= max_attempts:
            store_delete(key)
            logger.warning(
                "Pending registration destroyed after %d failed OTP attempts (%s)",
                attempts,
                payload.get("email"),
            )
            return VerifyResult(
                False,
                message="Too many failed attempts. Please request a new verification code.",
                code="too_many_attempts",
                remaining_attempts=0,
            )

        payload["attempts"] = attempts
        remaining_ttl = max(store_ttl(key), 1)
        store_set(key, payload, ttl=remaining_ttl)

        remaining = max_attempts - attempts
        return VerifyResult(
            False,
            message=f"That code is incorrect. {remaining} attempt(s) remaining.",
            code="invalid_otp",
            remaining_attempts=remaining,
        )

    # --- OTP correct: create the account ----------------------------------
    # Store channel in payload if passed or read from payload
    resolved_channel = channel or payload.get("channel", "email")
    payload["resolved_channel"] = resolved_channel

    try:
        user, already_existed = _create_verified_user(payload, ip=ip, user_agent=user_agent)
    except ValueError as e:
        return VerifyResult(False, message=str(e), code="creation_rejected")
    except Exception as e:
        logger.exception("Failed to create user after OTP verification: %s", e)
        return VerifyResult(
            False,
            message="We verified your email but couldn't finish creating your account. Please try again.",
            code="creation_failed",
        )

    store_delete(key)
    store_delete(
        f"{_EMAIL_INDEX_PREFIX}{hashlib.sha256(payload['email'].encode()).hexdigest()}"
    )

    return VerifyResult(
        True,
        user=user,
        message="Email verified. Your account is ready.",
        already_existed=already_existed,
    )


def _create_verified_user(
    payload: Dict[str, Any],
    *,
    ip: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> Tuple[Any, bool]:
    """
    Create the verified ``User`` atomically.

    Race-safe: concurrent verifications of the same email converge on the
    existing row instead of raising, because the unique constraint on
    ``users.email`` is caught and treated as success.

    Returns ``(user, already_existed)``.
    """
    from sqlalchemy.exc import IntegrityError

    from app.extensions import db
    from app.identity.models.user import User, UserRole
    from app.identity.models.roles_permission import get_or_create_role
    from app.auth.roles import DEFAULT_SCOPE
    from app.profile.models import UserProfile

    email = payload["email"]
    username = payload["username"]

    # Fast path: another request already completed this verification.
    existing = User.query.filter_by(email=email).first()
    if existing:
        return existing, True

    try:
        user = User(
            public_id=str(uuid.uuid4()),
            username=username,
            email=email,
        )
        # Password was hashed at signup time; assign directly so we never hold
        # the plaintext in Redis.
        user.password_hash = payload["password_hash"]
        user.is_active = True
        
        resolved_channel = payload.get("resolved_channel", "email")
        from datetime import datetime, timezone
        now_utc = datetime.now(timezone.utc)

        if resolved_channel == "email":
            user.is_verified = True
            user.email_verified = True
            if hasattr(user, "email_verified_at"):
                user.email_verified_at = now_utc
        elif resolved_channel in ("sms", "whatsapp"):
            user.phone_verified = True
            if payload.get("phone"):
                user.phone = payload.get("phone")
            if hasattr(user, "phone_verified_at"):
                user.phone_verified_at = now_utc
        
        if hasattr(user, "activated_at"):
            user.activated_at = now_utc

        db.session.add(user)
        db.session.flush()

        default_role = get_or_create_role(
            name="user",
            scope=DEFAULT_SCOPE,
            description="Default role for registered users",
            level=6,
            commit=False,
        )
        db.session.add(UserRole(user_id=user.id, role_id=default_role.id))

        db.session.add(
            UserProfile(
                # UserProfile.user_id is a FK to users.public_id (a string),
                # not the integer PK - set it explicitly so the NOT NULL
                # constraint is satisfied on flush.
                user_id=user.public_id,
                full_name=payload.get("full_name") or username,
                email=email,
                profile_completed=False,
            )
        )

        db.session.commit()

    except IntegrityError:
        # Lost a race against a parallel verification (or a duplicate
        # username). Roll back and resolve to the winning row if there is one.
        db.session.rollback()
        winner = User.query.filter_by(email=email).first()
        if winner:
            logger.info("Concurrent verification detected for %s; using existing account", email)
            return winner, True
        raise ValueError(
            "That username or email was just taken. Please choose another."
        )

    logger.info("Created verified user %s (%s)", user.public_id, email)

    # Post-commit side effects must never fail the registration.
    try:
        from app.auth.services import _emit, _user_payload

        _emit(
            "user.created",
            {
                **_user_payload(user),
                "email_verified": True,
                "verification_method": "signup_otp",
                "ip": ip,
                "user_agent": user_agent,
                "resource_type": "user",
                "resource_id": user.public_id,
            },
        )
        db.session.commit()
    except Exception as e:
        logger.warning("Audit emit failed for new user %s: %s", user.public_id, e)
        db.session.rollback()

    try:
        from app.notifications.services import NotificationService

        NotificationService.send_signup_notification(
            user_id=user.id,
            user_data={"username": username, "email": email, "role": "user"},
        )
    except Exception as e:
        logger.warning("Signup notification failed for %s: %s", email, e)

    return user, False


def start_channel_verification(user_id: int, channel: str) -> Tuple[bool, str, Optional[str]]:
    """
    Start post-activation channel verification for already-active users:
    stores OTP via the right method, returns (success, message, debug_otp).
    """
    from app.identity.models.user import User
    from app.auth.otp_service import OTPService

    user = User.query.get(user_id)
    if not user:
        return False, "User not found.", None

    if channel == "email":
        if not user.email:
            return False, "No email address on file.", None
        otp = OTPService.generate_otp(length=6)
        stored = OTPService.store_otp(identifier=str(user.id), otp=otp, purpose="channel_verify_email", ttl=600)
        if not stored:
            return False, "Failed to store verification code.", None
        delivery = OTPService.send_email_otp_checked(email=user.email, otp=otp, user_id=user.id)
        if not delivery.get("success"):
            return False, delivery.get("message", "Failed to send email OTP."), None
        return True, f"Verification code sent to {user.email}.", (otp if delivery.get("dev_fallback") else None)

    elif channel in ("sms", "whatsapp"):
        if not user.phone:
            return False, "No phone number on file. Please update your profile with a phone number.", None
        otp = OTPService.generate_sms_otp(length=6)
        success, _ = OTPService.send_sms_otp(phone=user.phone, otp=otp, internal_user_id=user.id)
        if not success:
            return False, f"Failed to send {channel} OTP. Please check your phone number.", None
        return True, f"Verification code sent via {channel} to {user.phone}.", otp

    return False, "Invalid verification channel.", None


def verify_channel_otp(user_id: int, channel: str, otp: str) -> Tuple[bool, str]:
    """
    Verify channel OTP for already-active users: sets correct timestamp + is_active=True if still false.
    """
    from app.identity.models.user import User
    from app.auth.otp_service import OTPService
    from app.extensions import db

    user = User.query.get(user_id)
    if not user:
        return False, "User not found."

    otp = (otp or "").strip()
    if not otp.isdigit() or len(otp) != 6:
        return False, "Please enter a valid 6-digit code."

    purpose = "channel_verify_email" if channel == "email" else "sms_verification"
    identifier = str(user.id) if channel == "email" else (str(user.id) if channel in ("sms", "whatsapp") else user.phone)

    # Note: verify_sms_otp uses internal_user_id when provided, verify_otp uses identifier
    if channel == "email":
        valid = OTPService.verify_otp(identifier=str(user.id), otp=otp, purpose=purpose)
    else:
        valid = OTPService.verify_sms_otp(phone=user.phone, otp=otp, internal_user_id=user.id)

    if not valid:
        return False, "Invalid or expired verification code."

    from datetime import datetime, timezone
    now_utc = datetime.now(timezone.utc)

    user.is_active = True
    if not user.activated_at:
        user.activated_at = now_utc

    if channel == "email":
        user.is_verified = True
        user.email_verified = True
        user.email_verified_at = now_utc
    elif channel in ("sms", "whatsapp"):
        user.phone_verified = True
        user.phone_verified_at = now_utc

    db.session.commit()
    return True, "Account successfully verified."
