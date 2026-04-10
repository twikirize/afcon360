# app/auth/services.py — FIXED AUDIT LOGGING
#
# Changes:
#   [FIX] Replaced ComplianceAuditLog with AuditLog in _emit()
#   [FIX] Added proper field mapping for AuditLog schema
#   [KEEP] All P0 security fixes (password reset token handling)
#   [FIX] Export revoke_session from sessions.py
# ============================================================================

from datetime import datetime, timedelta
from typing import Callable, Dict, List, Optional
import hashlib
import uuid
from functools import wraps

from app.extensions import db
from app.identity.models.user import User, UserRole
from app.identity.models.roles_permission import Role
from app.audit.user import AuditLog  # FIXED: Use correct audit model
from app.profile.models import UserProfile
from app.auth.tokens import (
    generate_email_token,
    verify_email_token,
    generate_reset_token,
    verify_reset_token,
)
from app.auth.sessions import start_server_session, revoke_all_sessions_for_user, revoke_session
from app.auth.roles import DEFAULT_SCOPE

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
        "timestamp": datetime.utcnow().isoformat()
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
    return bool(locked_until and datetime.utcnow() < locked_until)


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
        user.locked_until = datetime.utcnow() + timedelta(minutes=15)


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
        "user_id": user.user_id,
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
        full_name: Optional[str] = None
) -> User:
    """
    Register a new user with email verification.

    Emits: user.created
    """
    if User.query.filter_by(username=username).first():
        raise ValueError(f"Username '{username}' already exists")
    if email and User.query.filter_by(email=email).first():
        raise ValueError(f"Email '{email}' already exists")

    public_id = str(uuid.uuid4())
    user = User(user_id=public_id, username=username, email=email)
    user.set_password(password)

    try:
        db.session.add(user)
        db.session.flush()

        # Assign default role
        default_role = Role.query.filter_by(name="fan", scope=DEFAULT_SCOPE).first()
        if default_role:
            db.session.add(UserRole(user_id=user.id, role_id=default_role.id))

        # Create profile
        db.session.add(UserProfile(user=user, full_name=full_name or username, email=email))

        # Generate email verification token
        nonce = None
        if hasattr(user, "email_verify_nonce") and email:
            nonce = str(uuid.uuid4())
            user.email_verify_nonce = nonce

        token = generate_email_token(user.user_id, nonce=nonce) if email else None

        _emit("user.created", {
            **_user_payload(user),
            "verify_token": token,
            "email_provided": bool(email),
            "resource_type": "user",
            "resource_id": user.user_id
        })

        db.session.commit()
    except Exception:
        db.session.rollback()
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
        return AuthResult.LOCKED, {"user": user, "user_id": user.user_id}

    if not user.verify_password(password):
        _record_failed_login_attempt(user)
        db.session.commit()
        return AuthResult.INVALID_CREDENTIALS, {"user": user, "user_id": user.user_id}

    _reset_failed_login_counter(user)
    user.last_login = datetime.utcnow()

    requires_mfa = getattr(user, "requires_mfa", lambda: False)()
    if requires_mfa:
        db.session.commit()
        return AuthResult.MFA_REQUIRED, {"user": user, "user_id": user.user_id}

    session_id = start_server_session(user.user_id, ip, user_agent)
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

    user = User.query.filter_by(user_id=data["uid"]).first()
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
        user.email_verified_at = datetime.utcnow()
    if hasattr(user, "email_verify_nonce"):
        user.email_verify_nonce = None

    _emit("user.verified", {
        "user_id": user.user_id,
        "verified": True,
        "email_verified_at": _format_datetime(user.email_verified_at),
        "resource_type": "user",
        "resource_id": user.user_id
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
    token = generate_reset_token(user.user_id)

    # SECURITY: Log only hash hint, never the raw token
    token_hint = hashlib.sha256(token.encode()).hexdigest()[:12]

    _emit("password.reset.requested", {
        "user_id": user.user_id,
        "token_hint": token_hint,  # Safe: 12 hex chars of SHA-256
        "resource_type": "user",
        "resource_id": user.user_id
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

    user = User.query.filter_by(user_id=data["uid"]).first()
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
        user.password_reset_at = datetime.utcnow()

    # Revoke all sessions on password change
    revoke_all_sessions_for_user(user.user_id)

    _emit("password.reset.completed", {
        "user_id": user.user_id,
        "resource_type": "user",
        "resource_id": user.user_id
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
    user = User.query.filter_by(user_id=user_id).first()
    role = Role.query.filter_by(name=role_name, scope=scope).first()

    if not user or not role:
        return False

    existing = UserRole.query.filter_by(user_id=user.id, role_id=role.id).first()
    if existing:
        return True

    db.session.add(UserRole(user_id=user.id, role_id=role.id, assigned_by=assigned_by_id))

    # Revoke sessions to force re-authorization with new role
    revoke_all_sessions_for_user(user.user_id)

    _emit("role.assigned", {
        "user_id": user.user_id,
        "role": role.name,
        "scope": role.scope,
        "role_id": role.id,
        "assigned_by": assigned_by_id,
        "resource_type": "user_role",
        "resource_id": user.user_id
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
    user = User.query.filter_by(user_id=user_id).first()
    role = Role.query.filter_by(name=role_name, scope=scope).first()

    if not user or not role:
        return False

    existing = UserRole.query.filter_by(user_id=user.id, role_id=role.id).first()
    if not existing:
        return True

    db.session.delete(existing)

    # Revoke sessions to force re-authorization
    revoke_all_sessions_for_user(user.user_id)

    _emit("role.removed", {
        "user_id": user.user_id,
        "role": role.name,
        "scope": role.scope,
        "role_id": role.id,
        "revoked_by": revoked_by_id,
        "resource_type": "user_role",
        "resource_id": user.user_id
    })

    db.session.commit()
    return True


# ----------------------------
# Admin User Management
# ----------------------------
def activate_user(user_id: str, active: bool = True, actor_id: Optional[str] = None) -> bool:
    """
    Activate or deactivate a user account.

    Emits: user.activated or user.deactivated
    """
    user = User.query.filter_by(user_id=user_id).first()
    if not user:
        return False

    user.is_active = active

    event_name = "user.activated" if active else "user.deactivated"
    _emit(event_name, {
        "user_id": user.user_id,
        "active": active,
        "actor_id": actor_id,
        "resource_type": "user",
        "resource_id": user.user_id
    })

    db.session.commit()
    return True


def verify_user(user_id: str, verified: bool = True, actor_id: Optional[str] = None) -> bool:
    """
    Manually verify a user (admin action).

    Emits: user.verified
    """
    user = User.query.filter_by(user_id=user_id).first()
    if not user:
        return False

    user.is_verified = verified
    if verified and hasattr(user, "email_verified_at") and not user.email_verified_at:
        user.email_verified_at = datetime.utcnow()

    _emit("user.verified", {
        "user_id": user.user_id,
        "verified": verified,
        "actor_id": actor_id,
        "resource_type": "user",
        "resource_id": user.user_id
    })

    db.session.commit()
    return True
