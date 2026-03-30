# app/auth/services.py  — PATCHED
#
# Changes vs original:
#   [P0] request_password_reset: raw token REMOVED from audit emit
#        (raw token in ComplianceAuditLog is a critical data breach vector)
#   All other logic is unchanged.
# ============================================================================

from datetime import datetime, timedelta
from typing import Callable, Dict, List, Optional, Union
import hashlib
import uuid
from functools import wraps

from app.extensions import db
from app.identity.models.user import User, UserRole
from app.identity.models.roles_permission import Role
from app.identity.models.compliance_audit_log import ComplianceAuditLog
from app.profile.models import UserProfile
from app.auth.tokens import (
    generate_email_token,
    verify_email_token,
    generate_reset_token,
    verify_reset_token,
)
from app.auth.sessions import start_server_session, revoke_all_sessions_for_user
from app.auth.roles import DEFAULT_SCOPE

# ----------------------------
# Constants
# ----------------------------
PASSWORD_RESET_EXPIRY = 3600   # 1 hour
EMAIL_VERIFY_EXPIRY = 86400    # 24 hours

# ----------------------------
# Hook Registry
# ----------------------------
_hook_registry: Dict[str, List[Callable[[dict], None]]] = {}

def register_hook(event_name: str, fn: Callable[[dict], None]) -> None:
    _hook_registry.setdefault(event_name, []).append(fn)

def unregister_hook(event_name: str, fn: Callable[[dict], None]) -> None:
    if event_name in _hook_registry and fn in _hook_registry[event_name]:
        _hook_registry[event_name].remove(fn)

def _emit(event_name: str, payload: dict) -> None:
    """Emit an event and queue audit log"""
    enhanced_payload = {**payload, "event": event_name, "timestamp": datetime.utcnow().isoformat()}
    for hook in _hook_registry.get(event_name, []):
        try:
            hook(enhanced_payload)
        except Exception as e:
            print(f"⚠️ Hook error for {event_name}: {hook.__name__} - {e}")

    try:
        db.session.add(ComplianceAuditLog(
            event=event_name,
            user_id=payload.get("user_id"),
            details=enhanced_payload
        ))
    except Exception as e:
        print(f"⚠️ Failed to queue audit log for {event_name}: {e}")

# ----------------------------
# AuthResult Enum
# ----------------------------
class AuthResult:
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
    @wraps(func)
    def wrapper(identifier: str, password: str, ip=None, user_agent=None):
        result, payload = func(identifier, password, ip, user_agent)
        user_id = payload.get("user_id") if payload else None
        user_obj = payload.get("user") if payload else None

        if result == AuthResult.NOT_FOUND:
            _emit("user.failed_auth", {"identifier": identifier, "reason": "not_found"})
        elif result == AuthResult.INACTIVE:
            _emit("user.failed_auth", {"user_id": user_id, "reason": "inactive_or_deleted"})
        elif result == AuthResult.LOCKED:
            _emit("user.locked", {"user_id": user_id, "locked_until": _format_datetime(getattr(user_obj, "locked_until", None))})
        elif result == AuthResult.INVALID_CREDENTIALS:
            failed_count = getattr(user_obj, "failed_logins", None)
            _emit("user.failed_auth", {"user_id": user_id, "reason": "bad_password", "failed_count": failed_count})
            if _is_account_locked(user_obj):
                _emit("user.locked", {"user_id": user_id, "locked_until": _format_datetime(getattr(user_obj, "locked_until", None))})
        elif result == AuthResult.MFA_REQUIRED:
            _emit("user.mfa_required", {"user_id": user_id})
        elif result == AuthResult.SUCCESS:
            _emit("user.authenticated", {**_user_payload(user_obj), "server_session_id": payload.get("session_id"), "ip": ip})

        return result, payload
    return wrapper

# ----------------------------
# Private Helpers
# ----------------------------
def _is_account_locked(user: User) -> bool:
    locked_until = getattr(user, "locked_until", None)
    if hasattr(user, "is_locked"):
        try:
            return user.is_locked()
        except Exception:
            pass
    return bool(locked_until and datetime.utcnow() < locked_until)

def _record_failed_login_attempt(user: User) -> None:
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
    if hasattr(user, "reset_failed_login"):
        try:
            user.reset_failed_login(db.session)
            return
        except Exception:
            db.session.rollback()
    user.failed_logins = 0
    user.locked_until = None

def _user_payload(user: User) -> dict:
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
    return dt.isoformat() if dt else None

# ----------------------------
# User Registration
# ----------------------------
def register_user(username: str, password: str, email: Optional[str] = None, full_name: Optional[str] = None) -> User:
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
        default_role = Role.query.filter_by(name="fan", scope=DEFAULT_SCOPE).first()
        if default_role:
            db.session.add(UserRole(user_id=user.id, role_id=default_role.id))
        db.session.add(UserProfile(user=user, full_name=full_name or username, email=email))

        nonce = None
        if hasattr(user, "email_verify_nonce") and email:
            nonce = str(uuid.uuid4())
            user.email_verify_nonce = nonce

        token = generate_email_token(user.user_id, nonce=nonce) if email else None

        _emit("user.created", {**_user_payload(user), "verify_token": token, "email_provided": bool(email)})
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise

    return user

# ----------------------------
# Authentication
# ----------------------------
@auth_event_emitter
def authenticate_user(identifier: str, password: str, ip=None, user_agent=None) -> tuple[str, Optional[dict]]:
    user = User.query.filter((User.username == identifier) | (User.email == identifier)).first()
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
    data = verify_email_token(token, max_age=EMAIL_VERIFY_EXPIRY)
    if not data:
        return False
    user = User.query.filter_by(user_id=data["uid"]).first()
    if not user:
        return False

    if hasattr(user, "email_verify_nonce"):
        expected_nonce = getattr(user, "email_verify_nonce", None)
        if expected_nonce and data.get("nonce") != expected_nonce:
            return False

    if getattr(user, "is_verified", False) and getattr(user, "email_verified_at", None):
        return False

    user.is_verified = True
    if hasattr(user, "email_verified_at"):
        user.email_verified_at = datetime.utcnow()
    if hasattr(user, "email_verify_nonce"):
        user.email_verify_nonce = None

    _emit("user.verified", {"user_id": user.user_id, "verified": True, "email_verified_at": _format_datetime(user.email_verified_at)})
    db.session.commit()
    return True

# ----------------------------
# Password Reset
# ----------------------------
def request_password_reset(user: User) -> str:
    token = generate_reset_token(user.user_id)

    # FIX [P0]: raw token NEVER goes into the audit log.
    # Log only a short non-reversible hint for correlation if ever needed.
    token_hint = hashlib.sha256(token.encode()).hexdigest()[:12]
    _emit("password.reset.requested", {
        "user_id":    user.user_id,
        "token_hint": token_hint,   # safe: 12 hex chars of SHA-256, not usable
        # "token": token  ← REMOVED — was a critical data breach vector
    })

    db.session.commit()
    return token

def confirm_password_reset(token: str, new_password: str) -> bool:
    data = verify_reset_token(token, max_age=PASSWORD_RESET_EXPIRY)
    if not data:
        return False
    user = User.query.filter_by(user_id=data["uid"]).first()
    if not user:
        return False

    issued_at = data.get("iat")
    last_reset = getattr(user, "password_reset_at", None)
    if issued_at and last_reset and isinstance(last_reset, datetime) and issued_at < int(last_reset.timestamp()):
        return False

    user.set_password(new_password)
    if hasattr(user, "password_reset_at"):
        user.password_reset_at = datetime.utcnow()

    revoke_all_sessions_for_user(user.user_id)
    _emit("password.reset.completed", {"user_id": user.user_id})
    db.session.commit()
    return True

# ----------------------------
# Role Management
# ----------------------------
def assign_role(user_id: str, role_name: str, scope: str = DEFAULT_SCOPE, assigned_by_id: Optional[str] = None) -> bool:
    user = User.query.filter_by(user_id=user_id).first()
    role = Role.query.filter_by(name=role_name, scope=scope).first()
    if not user or not role:
        return False

    existing = UserRole.query.filter_by(user_id=user.id, role_id=role.id).first()
    if existing:
        return True

    db.session.add(UserRole(user_id=user.id, role_id=role.id, assigned_by=assigned_by_id))
    revoke_all_sessions_for_user(user.user_id)
    _emit("role.assigned", {"user_id": user.user_id, "role": role.name, "scope": role.scope, "role_id": role.id, "assigned_by": assigned_by_id})
    db.session.commit()
    return True

def remove_role(user_id: str, role_name: str, scope: str = DEFAULT_SCOPE, revoked_by_id: Optional[str] = None) -> bool:
    user = User.query.filter_by(user_id=user_id).first()
    role = Role.query.filter_by(name=role_name, scope=scope).first()
    if not user or not role:
        return False

    existing = UserRole.query.filter_by(user_id=user.id, role_id=role.id).first()
    if not existing:
        return True

    db.session.delete(existing)
    revoke_all_sessions_for_user(user.user_id)
    _emit("role.removed", {"user_id": user.user_id, "role": role.name, "scope": role.scope, "role_id": role.id, "revoked_by": revoked_by_id})
    db.session.commit()
    return True

# ----------------------------
# Admin User Management
# ----------------------------
def activate_user(user_id: str, active: bool = True, actor_id: Optional[str] = None) -> bool:
    user = User.query.filter_by(user_id=user_id).first()
    if not user:
        return False
    user.is_active = active
    _emit("user.activated" if active else "user.deactivated", {"user_id": user.user_id, "active": active, "actor_id": actor_id})
    db.session.commit()
    return True

def verify_user(user_id: str, verified: bool = True, actor_id: Optional[str] = None) -> bool:
    user = User.query.filter_by(user_id=user_id).first()
    if not user:
        return False
    user.is_verified = verified
    if verified and hasattr(user, "email_verified_at") and not user.email_verified_at:
        user.email_verified_at = datetime.utcnow()
    _emit("user.verified", {"user_id": user.user_id, "verified": verified, "actor_id": actor_id})
    db.session.commit()
    return True