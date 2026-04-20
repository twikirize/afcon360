# app/auth/services.py — FIXED AUDIT LOGGING
#
# Changes:
#   [FIX] Replaced ComplianceAuditLog with AuditLog in _emit()
#   [FIX] Added proper field mapping for AuditLog schema
#   [KEEP] All P0 security fixes (password reset token handling)
#   [FIX] Export revoke_session from sessions.py
# ============================================================================

from datetime import datetime, timedelta, timezone
from typing import Callable, Dict, List, Optional, Tuple, Any
import hashlib
import secrets
import uuid
from functools import wraps

from app.extensions import db, cache
from app.identity.models.user import User, UserRole
from app.identity.models.roles_permission import Role, get_or_create_role
from app.audit.user import AuditLog  # FIXED: Use correct audit model
from app.audit.forensic_audit import ForensicAuditService
from app.profile.models import UserProfile
from app.auth.tokens import (
    generate_email_token,
    verify_email_token,
    generate_reset_token,
    verify_reset_token,
)
from app.auth.sessions import start_server_session, revoke_all_sessions_for_user, revoke_session
from app.auth.roles import DEFAULT_SCOPE
from app.auth.otp_service import otp_service

# ----------------------------
# Constants
# ----------------------------
PASSWORD_RESET_EXPIRY = 3600  # 1 hour
EMAIL_VERIFY_EXPIRY = 86400  # 24 hours

# ----------------------------
# Hook Registry
# ----------------------------
_hook_registry: Dict[str, List[Callable[[dict], None]]] = {}


def register_hook(event_name: str, fn: Callable[[dict], None]) -> None:
    """Register a callback to be invoked when an event is emitted."""
    _hook_registry.setdefault(event_name, []).append(fn)


def unregister_hook(event_name: str, fn: Callable[[dict], None]) -> None:
    """Remove a previously registered hook."""
    if event_name in _hook_registry and fn in _hook_registry[event_name]:
        _hook_registry[event_name].remove(fn)


def _emit(event_name: str, payload: dict) -> None:
    """
    Emit an event and queue audit log.

    FIXED: Now uses AuditLog instead of ComplianceAuditLog
    - General auth events → AuditLog (user actions)
    - Compliance decisions → ComplianceAuditLog (handled separately)
    """
    enhanced_payload = {
        **payload,
        "event": event_name,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

    # Execute registered hooks
    for hook in _hook_registry.get(event_name, []):
        try:
            hook(enhanced_payload)
        except Exception as e:
            print(f"⚠️ Hook error for {event_name}: {hook.__name__} - {e}")

    # FIXED: Use correct audit log model with proper field mapping
    # NOTE: AuditLog.user_id is a BigInteger FK to users.id (integer PK).
    # payload["user_id"] is the public UUID string — we must use payload["id"] instead,
    # which is the integer PK set by _user_payload() and auth_event_emitter.
    try:
        AuditLog.log(
            user_id=payload.get("id"),  # integer PK, not UUID string
            action=event_name,
            resource_type=payload.get("resource_type"),  # e.g., "user", "role"
            resource_id=payload.get("resource_id"),
            meta=enhanced_payload,
            ip_address=payload.get("ip"),
            user_agent=payload.get("user_agent"),
            db_session=db.session  # Pass session but don't commit
        )
    except Exception as e:
        print(f"⚠️ Failed to create audit log entry for {event_name}: {e}")


# ----------------------------
# AuthResult Enum
# ----------------------------
class AuthResult:
    """Authentication result status codes."""
    SUCCESS = "success"
    NOT_FOUND = "not_found"
    INACTIVE = "inactive"
    LOCKED = "locked"
    INVALID_CREDENTIALS = "invalid_credentials"
    MFA_REQUIRED = "mfa_required"


# ----------------------------
# Decorators
# ----------------------------
def auth_event_emitter(func):
    """
    Decorator to emit audit events for authentication attempts.
    Handles success, failure, and security events (lockouts, MFA).
    """

    @wraps(func)
    def wrapper(identifier: str, password: str, ip=None, user_agent=None):
        result, payload = func(identifier, password, ip, user_agent)
        user_id = payload.get("user_id") if payload else None
        user_obj = payload.get("user") if payload else None

        # Build base audit context
        # "id" is the integer PK used by AuditLog FK; "user_id" is the public UUID.
        audit_context = {
            "user_id": user_id,
            "id": user_obj.id if user_obj else None,  # integer PK for AuditLog FK
            "ip": ip,
            "user_agent": user_agent,
            "resource_type": "user",
            "resource_id": user_id
        }

        if result == AuthResult.NOT_FOUND:
            _emit("user.failed_auth", {
                **audit_context,
                "identifier": identifier,
                "reason": "not_found"
            })
        elif result == AuthResult.INACTIVE:
            _emit("user.failed_auth", {
                **audit_context,
                "reason": "inactive_or_deleted"
            })
        elif result == AuthResult.LOCKED:
            _emit("user.locked", {
                **audit_context,
                "locked_until": _format_datetime(getattr(user_obj, "locked_until", None))
            })
        elif result == AuthResult.INVALID_CREDENTIALS:
            failed_count = getattr(user_obj, "failed_logins", None)
            _emit("user.failed_auth", {
                **audit_context,
                "reason": "bad_password",
                "failed_count": failed_count
            })
            if _is_account_locked(user_obj):
                _emit("user.locked", {
                    **audit_context,
                    "locked_until": _format_datetime(getattr(user_obj, "locked_until", None))
                })
        elif result == AuthResult.MFA_REQUIRED:
            _emit("user.mfa_required", audit_context)
        elif result == AuthResult.SUCCESS:
            _emit("user.authenticated", {
                **audit_context,
                **_user_payload(user_obj),
                "server_session_id": payload.get("session_id")
            })

        return result, payload

    return wrapper


# ----------------------------
# Private Helpers
# ----------------------------
def _is_account_locked(user: User) -> bool:
    """Check if user account is currently locked."""
    locked_until = getattr(user, "locked_until", None)
    if hasattr(user, "is_locked"):
        try:
            return user.is_locked()
        except Exception:
            pass
    return bool(locked_until and datetime.now(timezone.utc) < locked_until)


def _record_failed_login_attempt(user: User) -> None:
    """Record a failed login attempt and lock account if threshold exceeded."""
    if hasattr(user, "record_failed_login"):
        try:
            user.record_failed_login(db.session)
            return
        except Exception:
            db.session.rollback()

    user.failed_logins = (getattr(user, "failed_logins", 0) or 0) + 1
    if user.failed_logins >= 5:
        user.locked_until = datetime.now(timezone.utc) + timedelta(minutes=15)


def _reset_failed_login_counter(user: User) -> None:
    """Reset failed login counter on successful authentication."""
    if hasattr(user, "reset_failed_login"):
        try:
            user.reset_failed_login(db.session)
            return
        except Exception:
            db.session.rollback()

    user.failed_logins = 0
    user.locked_until = None


def _user_payload(user: User) -> dict:
    """Extract safe user data for audit logs."""
    return {
        "user_id": user.public_id,
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "is_active": getattr(user, "is_active", True),
        "is_verified": getattr(user, "is_verified", False),
        "created_at": _format_datetime(getattr(user, "created_at", None))
    }


def _format_datetime(dt: Optional[datetime]) -> Optional[str]:
    """Format datetime to ISO 8601 string."""
    return dt.isoformat() if dt else None


# ----------------------------
# User Registration
# ----------------------------
def register_user(
        username: str,
        password: str,
        email: Optional[str] = None,
        full_name: Optional[str] = None,
        security_question: Optional[str] = None,
        security_answer: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None
) -> User:
    """
    Register a new user with email verification or security question.

    Emits: user.created
    """
    # Log attempt
    audit_id = ForensicAuditService.log_attempt(
        entity_type="user",
        entity_id=str(uuid.uuid4()),
        action="register",
        user_id=None,  # No user yet
        details={
            "username": username,
            "email": email,
            "has_security_question": security_question is not None
        },
        ip_address=ip_address,
        user_agent=user_agent
    )

    # Check for existing username
    if User.query.filter_by(username=username).first():
        ForensicAuditService.log_blocked(
            entity_type="user",
            entity_id=str(uuid.uuid4()),
            action="register",
            user_id=None,
            reason="Username already exists",
            attempted_value=username,
            ip_address=ip_address,
            user_agent=user_agent
        )
        raise ValueError(f"Username '{username}' already exists")

    # Check for existing email if provided
    if email and User.query.filter_by(email=email).first():
        ForensicAuditService.log_blocked(
            entity_type="user",
            entity_id=str(uuid.uuid4()),
            action="register",
            user_id=None,
            reason="Email already exists",
            attempted_value=email,
            ip_address=ip_address,
            user_agent=user_agent
        )
        raise ValueError(f"Email '{email}' already exists")

    # Validate security question/answer when no email is provided
    if not email:
        if not security_question or not security_answer:
            ForensicAuditService.log_blocked(
                entity_type="user",
                entity_id=str(uuid.uuid4()),
                action="register",
                user_id=None,
                reason="Security question and answer required when email is not provided",
                attempted_value=None,
                ip_address=ip_address,
                user_agent=user_agent
            )
            raise ValueError("Security question and answer are required when email is not provided")

    # Generate recovery code if no email
    recovery_code = None
    hashed_security_answer = None
    if not email and security_answer:
        # Generate recovery code
        recovery_code = secrets.token_urlsafe(16)
        # Hash the security answer
        hashed_security_answer = hashlib.sha256(security_answer.encode()).hexdigest()

    public_id = str(uuid.uuid4())
    user = User(public_id=public_id, username=username, email=email)
    user.set_password(password)

    # Set verification and active status
    if email:
        user.is_verified = False
    else:
        user.is_verified = True
        # Store security question and hashed answer
        # Assuming the User model has these fields
        if hasattr(user, 'security_question'):
            user.security_question = security_question
        if hasattr(user, 'security_answer_hash'):
            user.security_answer_hash = hashed_security_answer
        if hasattr(user, 'recovery_code_hash') and recovery_code:
            # Hash the recovery code for storage
            recovery_code_hash = hashlib.sha256(recovery_code.encode()).hexdigest()
            user.recovery_code_hash = recovery_code_hash

    # Always set is_active=True
    user.is_active = True

    try:
        db.session.add(user)
        db.session.flush()

        # Assign default 'user' role (not 'fan')
        # Use get_or_create_role to ensure it exists
        default_role = get_or_create_role(
            name="user",
            scope=DEFAULT_SCOPE,
            description="Default role for registered users",
            level=6,  # Same level as 'fan' was supposed to be
            commit=False  # We'll commit later with the transaction
        )
        # Assign the role to the user
        user_role = UserRole(user_id=user.id, role_id=default_role.id)
        db.session.add(user_role)

        # Create profile with profile_completed=False
        db.session.add(UserProfile(
            user=user,
            full_name=full_name or username,
            email=email,
            profile_completed=False
        ))

        # Generate email verification token if email is provided
        nonce = None
        if hasattr(user, "email_verify_nonce") and email:
            nonce = str(uuid.uuid4())
            user.email_verify_nonce = nonce

        token = generate_email_token(user.public_id, nonce=nonce) if email else None

        # Prepare audit payload
        audit_payload = {
            **_user_payload(user),
            "verify_token": token,
            "email_provided": bool(email),
            "has_security_question": security_question is not None,
            "resource_type": "user",
            "resource_id": user.public_id
        }

        # If recovery code was generated, attach it to user object for one-time display
        if recovery_code:
            user._recovery_code = recovery_code
            # Don't include the actual recovery code in audit logs for security
            audit_payload["recovery_code_generated"] = True

        _emit("user.created", audit_payload)

        db.session.commit()

        # Log completion
        ForensicAuditService.log_completion(
            audit_id=audit_id,
            status="completed",
            result_details={
                "user_id": user.public_id,
                "username": username,
                "email_provided": bool(email),
                "is_verified": user.is_verified,
                "is_active": user.is_active
            }
        )
    except Exception as e:
        db.session.rollback()
        ForensicAuditService.log_completion(
            audit_id=audit_id,
            status="failed",
            result_details={"error": str(e)}
        )
        raise

    return user


# ----------------------------
# Authentication
# ----------------------------
@auth_event_emitter
def authenticate_user(
        identifier: str,
        password: str,
        ip=None,
        user_agent=None
) -> tuple[str, Optional[dict]]:
    """
    Authenticate user by username/email and password.

    Returns: (AuthResult status, payload dict)
    Emits: user.authenticated, user.failed_auth, user.locked
    """
    user = User.query.filter(
        (User.username == identifier) | (User.email == identifier)
    ).first()

    if not user:
        return AuthResult.NOT_FOUND, None

    if not getattr(user, "is_active", True) or getattr(user, "is_deleted", False):
        return AuthResult.INACTIVE, None

    if _is_account_locked(user):
        return AuthResult.LOCKED, {"user": user, "user_id": user.public_id}

    if not user.verify_password(password):
        _record_failed_login_attempt(user)
        db.session.commit()
        return AuthResult.INVALID_CREDENTIALS, {"user": user, "user_id": user.public_id}

    _reset_failed_login_counter(user)
    user.last_login = datetime.now(timezone.utc)

    # Check if MFA is enabled for the user
    requires_mfa = user.mfa_enabled

    if requires_mfa:
        # Get user's MFA method
        mfa_method = otp_service.get_user_mfa_method(user.id)

        if mfa_method == "totp":
            # For TOTP, we don't need to generate/send OTP here
            # The client should prompt for TOTP code
            _emit("user.mfa_required", {
                "user_id": user.public_id,
                "id": user.id,
                "mfa_method": mfa_method,
                "resource_type": "user",
                "resource_id": user.public_id
            })

            db.session.commit()
            return AuthResult.MFA_REQUIRED, {
                "user": user,
                "user_id": user.public_id,
                "mfa_type": mfa_method,
                "message": "TOTP authentication required"
            }
        else:
            # For SMS or other methods, generate and send OTP
            otp = otp_service.generate_sms_otp()
            # TODO: Get user's phone number from profile
            # For now, store OTP
            otp_service.store_otp(str(user.id), otp, purpose="2fa_login")

            # Log 2FA requirement
            _emit("user.mfa_required", {
                "user_id": user.public_id,
                "id": user.id,
                "mfa_method": mfa_method or "sms",
                "resource_type": "user",
                "resource_id": user.public_id
            })

            db.session.commit()
            return AuthResult.MFA_REQUIRED, {
                "user": user,
                "user_id": user.public_id,
                "mfa_type": mfa_method or "sms",
                "message": "OTP authentication required"
            }

    session_id = start_server_session(user.public_id, ip, user_agent)
    db.session.commit()

    return AuthResult.SUCCESS, {"user": user, "session_id": session_id}


# ----------------------------
# Email Verification
# ----------------------------
def verify_email(token: str) -> bool:
    """
    Verify user's email address using token.

    Emits: user.verified
    """
    data = verify_email_token(token, max_age=EMAIL_VERIFY_EXPIRY)
    if not data:
        return False

    user = User.query.filter_by(public_id=data["uid"]).first()
    if not user:
        return False

    # Check nonce if present
    if hasattr(user, "email_verify_nonce"):
        expected_nonce = getattr(user, "email_verify_nonce", None)
        if expected_nonce and data.get("nonce") != expected_nonce:
            return False

    # Already verified
    if getattr(user, "is_verified", False) and getattr(user, "email_verified_at", None):
        return False

    user.is_verified = True
    if hasattr(user, "email_verified_at"):
        user.email_verified_at = datetime.now(timezone.utc)
    if hasattr(user, "email_verify_nonce"):
        user.email_verify_nonce = None

    _emit("user.verified", {
        "user_id": user.public_id,
        "verified": True,
        "email_verified_at": _format_datetime(user.email_verified_at),
        "resource_type": "user",
        "resource_id": user.public_id
    })

    db.session.commit()
    return True


# ----------------------------
# Password Reset
# ----------------------------
def request_password_reset(user: User) -> str:
    """
    Generate password reset token for user.

    SECURITY: Token is NOT stored in audit log (only hash hint).
    Emits: password.reset.requested
    """
    token = generate_reset_token(user.public_id)

    # SECURITY: Log only hash hint, never the raw token
    token_hint = hashlib.sha256(token.encode()).hexdigest()[:12]

    _emit("password.reset.requested", {
        "user_id": user.public_id,
        "token_hint": token_hint,  # Safe: 12 hex chars of SHA-256
        "resource_type": "user",
        "resource_id": user.public_id
    })

    db.session.commit()
    return token


def confirm_password_reset(token: str, new_password: str) -> bool:
    """
    Complete password reset using valid token.

    Emits: password.reset.completed
    """
    data = verify_reset_token(token, max_age=PASSWORD_RESET_EXPIRY)
    if not data:
        return False

    user = User.query.filter_by(public_id=data["uid"]).first()
    if not user:
        return False

    # Check if token was issued before last reset
    issued_at = data.get("iat")
    last_reset = getattr(user, "password_reset_at", None)
    if issued_at and last_reset and isinstance(last_reset, datetime):
        if issued_at < int(last_reset.timestamp()):
            return False

    user.set_password(new_password)
    if hasattr(user, "password_reset_at"):
        user.password_reset_at = datetime.now(timezone.utc)

    # Revoke all sessions on password change
    revoke_all_sessions_for_user(user.public_id)

    _emit("password.reset.completed", {
        "user_id": user.public_id,
        "resource_type": "user",
        "resource_id": user.public_id
    })

    db.session.commit()
    return True


# ----------------------------
# Role Management
# ----------------------------
def assign_role(
        user_id: str,
        role_name: str,
        scope: str = DEFAULT_SCOPE,
        assigned_by_id: Optional[str] = None
) -> bool:
    """
    Assign a role to a user.

    Emits: role.assigned
    """
    user = User.query.filter_by(public_id=user_id).first()
    role = Role.query.filter_by(name=role_name, scope=scope).first()

    if not user or not role:
        return False

    existing = UserRole.query.filter_by(user_id=user.id, role_id=role.id).first()
    if existing:
        return True

    # Convert assigned_by_id from public UUID to internal ID if provided
    assigned_by_internal_id = None
    if assigned_by_id:
        assigned_by_user = User.query.filter_by(public_id=assigned_by_id).first()
        if assigned_by_user:
            assigned_by_internal_id = assigned_by_user.id

    db.session.add(UserRole(user_id=user.id, role_id=role.id, assigned_by=assigned_by_internal_id))

    # Revoke sessions to force re-authorization with new role
    revoke_all_sessions_for_user(user.public_id)

    _emit("role.assigned", {
        "user_id": user.public_id,
        "role": role.name,
        "scope": role.scope,
        "role_id": role.id,
        "assigned_by": assigned_by_id,
        "resource_type": "user_role",
        "resource_id": user.public_id
    })

    db.session.commit()
    return True


def remove_role(
        user_id: str,
        role_name: str,
        scope: str = DEFAULT_SCOPE,
        revoked_by_id: Optional[str] = None
) -> bool:
    """
    Remove a role from a user.

    Emits: role.removed
    """
    user = User.query.filter_by(public_id=user_id).first()
    role = Role.query.filter_by(name=role_name, scope=scope).first()

    if not user or not role:
        return False

    existing = UserRole.query.filter_by(user_id=user.id, role_id=role.id).first()
    if not existing:
        return True

    db.session.delete(existing)

    # Revoke sessions to force re-authorization
    revoke_all_sessions_for_user(user.public_id)

    _emit("role.removed", {
        "user_id": user.public_id,
        "role": role.name,
        "scope": role.scope,
        "role_id": role.id,
        "revoked_by": revoked_by_id,
        "resource_type": "user_role",
        "resource_id": user.public_id
    })

    db.session.commit()
    return True


# ----------------------------
# 2FA/OTP Verification
# ----------------------------
def verify_2fa_otp(user_id: str, otp: str, ip: Optional[str] = None,
                   user_agent: Optional[str] = None) -> Tuple[bool, Optional[dict]]:
    """
    Verify 2FA OTP for a user.

    Returns: (success, payload dict)
    """
    from app.identity.models.user import User

    user = User.query.filter_by(public_id=user_id).first()
    if not user:
        return False, {"error": "User not found"}

    # Check if MFA is enabled
    if not user.mfa_enabled:
        # MFA not enabled, treat as successful
        session_id = start_server_session(user.public_id, ip, user_agent)
        return True, {
            "user": user,
            "session_id": session_id,
            "message": "MFA not enabled for user"
        }

    # Get user's MFA method
    mfa_method = otp_service.get_user_mfa_method(user.id)

    if mfa_method == "totp":
        # Verify TOTP
        success = otp_service.verify_user_2fa(user.id, otp)
        if not success:
            # Audit failed TOTP attempt
            _emit("user.mfa_failed", {
                "user_id": user.public_id,
                "id": user.id,
                "ip": ip,
                "user_agent": user_agent,
                "reason": "Invalid TOTP code",
                "mfa_method": "totp",
                "resource_type": "user",
                "resource_id": user.public_id
            })

            return False, {
                "error": "Invalid TOTP code",
                "remaining_attempts": None  # TOTP doesn't have attempt limits in this implementation
            }
    else:
        # Verify stored OTP (for SMS/email)
        success, result = otp_service.verify_stored_otp(
            identifier=str(user.id),
            otp=otp,
            purpose="2fa_login"
        )

        if not success:
            # Audit failed OTP attempt
            _emit("user.mfa_failed", {
                "user_id": user.public_id,
                "id": user.id,
                "ip": ip,
                "user_agent": user_agent,
                "reason": result.get("error", "Invalid OTP"),
                "mfa_method": mfa_method or "sms",
                "resource_type": "user",
                "resource_id": user.public_id
            })

            return False, {
                "error": result.get("error", "Invalid OTP"),
                "remaining_attempts": result.get("remaining", 0)
            }

    # Start server session
    session_id = start_server_session(user.public_id, ip, user_agent)

    # Audit successful 2FA verification
    _emit("user.mfa_verified", {
        "user_id": user.public_id,
        "id": user.id,
        "ip": ip,
        "user_agent": user_agent,
        "mfa_method": mfa_method or "sms",
        "resource_type": "user",
        "resource_id": user.public_id
    })

    return True, {
        "user": user,
        "session_id": session_id,
        "message": "2FA verification successful"
    }

# ----------------------------
# 2FA Management
# ----------------------------
def setup_2fa(user_id: str) -> Dict[str, Any]:
    """Setup 2FA for a user"""
    from app.identity.models.user import User

    user = User.query.filter_by(public_id=user_id).first()
    if not user:
        raise ValueError("User not found")

    return otp_service.setup_user_2fa(user.id, user.email or user.username)

def verify_2fa_setup(user_id: str, otp: str) -> Tuple[bool, str]:
    """Verify and enable 2FA setup"""
    from app.identity.models.user import User

    user = User.query.filter_by(public_id=user_id).first()
    if not user:
        return False, "User not found"

    return otp_service.verify_and_enable_2fa(user.id, otp)

def disable_2fa(user_id: str, reason: str = "user_requested") -> bool:
    """Disable 2FA for a user"""
    from app.identity.models.user import User

    user = User.query.filter_by(public_id=user_id).first()
    if not user:
        return False

    return otp_service.disable_user_2fa(user.id, reason)

# ----------------------------
# MFA Status Check
# ----------------------------
def is_mfa_enabled(user_id: str) -> bool:
    """Check if MFA is enabled for a user"""
    from app.identity.models.user import User

    user = User.query.filter_by(public_id=user_id).first()
    if not user:
        return False

    return user.mfa_enabled

def get_mfa_method(user_id: str) -> Optional[str]:
    """Get the MFA method for a user"""
    from app.identity.models.user import User

    user = User.query.filter_by(public_id=user_id).first()
    if not user:
        return None

    return otp_service.get_user_mfa_method(user.id)

# ----------------------------
# OTP Generation and Sending
# ----------------------------
def send_sms_otp(phone_number: str, purpose: str = "verification",
                 user_id: Optional[str] = None) -> Tuple[bool, Optional[str]]:
    """
    Send OTP via SMS.

    Returns: (success, otp_code)
    """
    from app.identity.models.user import User

    internal_user_id = None
    if user_id:
        user = User.query.filter_by(public_id=user_id).first()
        if user:
            internal_user_id = user.id

    otp = otp_service.generate_sms_otp()

    # Store OTP for verification
    identifier = phone_number
    if internal_user_id:
        identifier = str(internal_user_id)

    stored = otp_service.store_otp(identifier, otp, purpose)
    if not stored:
        return False, None

    # Send SMS
    sent = otp_service.send_sms_otp(phone_number, otp, internal_user_id)
    if not sent:
        return False, None

    return True, otp

def send_email_otp(email: str, purpose: str = "verification",
                   user_id: Optional[str] = None) -> Tuple[bool, Optional[str]]:
    """
    Send OTP via email.

    Returns: (success, otp_code)
    """
    from app.identity.models.user import User

    internal_user_id = None
    if user_id:
        user = User.query.filter_by(public_id=user_id).first()
        if user:
            internal_user_id = user.id

    otp = otp_service.generate_email_otp()

    # Store OTP for verification
    identifier = email
    if internal_user_id:
        identifier = str(internal_user_id)

    stored = otp_service.store_otp(identifier, otp, purpose)
    if not stored:
        return False, None

    # Send email
    sent = otp_service.send_email_otp(email, otp, internal_user_id)
    if not sent:
        return False, None

    return True, otp

def verify_otp(identifier: str, otp: str, purpose: str = "verification") -> Tuple[bool, Dict[str, Any]]:
    """
    Verify OTP for any purpose.

    Returns: (success, result_data)
    """
    return otp_service.verify_stored_otp(identifier, otp, purpose)

# ----------------------------
# Backup Codes Management
# ----------------------------
def generate_backup_codes(user_id: str) -> Tuple[List[str], bool]:
    """Generate backup codes for 2FA recovery"""
    from app.identity.models.user import User

    user = User.query.filter_by(public_id=user_id).first()
    if not user:
        return [], False

    return otp_service.regenerate_backup_codes(user.id)

def verify_backup_code(user_id: str, code: str) -> bool:
    """Verify a backup code for 2FA recovery"""
    from app.identity.models.user import User

    user = User.query.filter_by(public_id=user_id).first()
    if not user:
        return False

    return otp_service.verify_backup_code_for_user(user.id, code)

def has_backup_codes(user_id: str) -> bool:
    """Check if user has backup codes available"""
    from app.identity.models.user import User

    user = User.query.filter_by(public_id=user_id).first()
    if not user:
        return False

    return otp_service.has_backup_codes(user.id)

# ----------------------------
# Password Recovery without Email
# ----------------------------
def initiate_password_recovery(username: str) -> Tuple[bool, Optional[dict]]:
    """
    Initiate password recovery for users without email.
    Returns: (success, user_data dict with security question if available)
    """
    user = User.query.filter_by(username=username).first()

    if not user:
        return False, None

    # Check if user has security question setup
    if not user.security_question or not user.security_answer_hash:
        return False, {"error": "No security question configured for this account"}

    # Check if user has email (should use email-based recovery instead)
    if user.email:
        return False, {"error": "Please use email-based password recovery"}

    return True, {
        "user_id": user.public_id,
        "username": user.username,
        "security_question": user.security_question
    }

def verify_security_answer_and_reset_password(
    username: str,
    answer: str,
    new_password: str
) -> Tuple[bool, Optional[str]]:
    """
    Verify security answer and reset password for users without email.
    Returns: (success, error_message)
    """
    user = User.query.filter_by(username=username).first()

    if not user:
        return False, "User not found"

    # Verify security answer
    if not user.verify_security_answer(answer):
        return False, "Incorrect security answer"

    # Reset password
    user.set_password(new_password)

    # Revoke all sessions on password change
    from app.auth.sessions import revoke_all_sessions_for_user
    revoke_all_sessions_for_user(user.public_id)

    # Emit audit event
    _emit("password.recovered_via_security_question", {
        "user_id": user.public_id,
        "resource_type": "user",
        "resource_id": user.public_id
    })

    db.session.commit()
    return True, None

# ----------------------------
# Admin User Management
# ----------------------------
def activate_user(user_id: str, active: bool = True, actor_id: Optional[str] = None) -> bool:
    """
    Activate or deactivate a user account.

    Emits: user.activated or user.deactivated
    """
    user = User.query.filter_by(public_id=user_id).first()
    if not user:
        return False

    user.is_active = active

    event_name = "user.activated" if active else "user.deactivated"
    _emit(event_name, {
        "user_id": user.public_id,
        "active": active,
        "actor_id": actor_id,
        "resource_type": "user",
        "resource_id": user.public_id
    })

    db.session.commit()
    return True


def verify_user(user_id: str, verified: bool = True, actor_id: Optional[str] = None) -> bool:
    """
    Manually verify a user (admin action).

    Emits: user.verified
    """
    user = User.query.filter_by(public_id=user_id).first()
    if not user:
        return False

    user.is_verified = verified
    if verified and hasattr(user, "email_verified_at") and not user.email_verified_at:
        user.email_verified_at = datetime.now(timezone.utc)

    _emit("user.verified", {
        "user_id": user.public_id,
        "verified": verified,
        "actor_id": actor_id,
        "resource_type": "user",
        "resource_id": user.public_id
    })

    db.session.commit()
    return True
