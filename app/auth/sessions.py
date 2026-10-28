# app/auth/sessions.py
# Note: This file doesn't contain "KYC data injection error" or "Audit summary injection error"
# This file doesn't contain "KYC data injection error" or "Audit summary injection error"
from datetime import datetime, timezone, timedelta
import uuid
import hashlib
from app.extensions import db
from app.models.base import BaseModel

class ServerSession(BaseModel):
    __tablename__ = "server_sessions"
    session_id = db.Column(db.String(128), unique=True, nullable=False, index=True)
    user_id = db.Column(db.String(64), nullable=False, index=True)  # public user_id (UUID/ULID)
    ip_address = db.Column(db.String(45), nullable=True)
    user_agent = db.Column(db.String(255), nullable=True)
    expires_at = db.Column(db.DateTime(timezone=True), nullable=False)
    is_revoked = db.Column(db.Boolean, default=False, nullable=False)

def start_server_session(public_user_id: str, ip: str | None, ua: str | None, ttl_hours: int = 12) -> str:
    sid = str(uuid.uuid4())
    ss = ServerSession(
        session_id=sid,
        user_id=public_user_id,
        ip_address=ip,
        user_agent=ua,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=ttl_hours),
    )
    try:
        db.session.add(ss)
        db.session.commit()

        # Audit session creation
        from app.audit.comprehensive_audit import AuditService
        try:
            # Need to get internal user ID from public ID
            from app.identity.models.user import User
            user = User.query.filter_by(public_id=public_user_id).first()
            if user:
                AuditService.security(
                    event_type="session_created",
                    severity="INFO",
                    description=f"New session created for user {public_user_id}",
                    user_id=user.id,
                    ip_address=ip,
                    user_agent=ua,
                    extra_data={
                        "session_id": sid,
                        "ttl_hours": ttl_hours,
                        "expires_at": ss.expires_at.isoformat()
                    }
                )
        except Exception as audit_error:
            # Don't fail session creation if audit fails
            import logging
            logging.error(f"Failed to audit session creation: {audit_error}")

    except Exception:
        db.session.rollback()
        # If storage fails, return an id anyway for client correlation (non-fatal)
    return sid

def revoke_session(session_id: str, revoked_by_user_id: int = None):
    s = ServerSession.query.filter_by(session_id=session_id, is_revoked=False).first()
    if not s:
        return False

    # Audit before revocation
    from app.audit.comprehensive_audit import AuditService
    from flask import request

    try:
        # Need to get internal user ID from public ID
        from app.identity.models.user import User
        user = User.query.filter_by(public_id=s.user_id).first()
        if user:
            AuditService.security(
                event_type="session_revoked",
                severity="INFO",
                description=f"Session revoked for user {s.user_id}",
                user_id=user.id,
                ip_address=request.remote_addr if request else None,
                user_agent=request.user_agent.string if request and request.user_agent else None,
                extra_data={
                    "session_id": session_id,
                    "revoked_by": revoked_by_user_id,
                    "was_active": not s.is_revoked,
                    "expires_at": s.expires_at.isoformat() if s.expires_at else None
                }
            )
    except Exception as audit_error:
        import logging
        logging.error(f"Failed to audit session revocation: {audit_error}")

    s.is_revoked = True
    try:
        db.session.commit()
        return True
    except Exception:
        db.session.rollback()
        raise

def revoke_all_sessions_for_user(public_user_id: str):
    q = ServerSession.query.filter_by(user_id=public_user_id, is_revoked=False)
    try:
        for s in q.all():
            s.is_revoked = True
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise


def _device_fingerprint(user_agent: str | None) -> str:
    """Generate a stable device fingerprint from user agent."""
    if not user_agent:
        return "unknown"
    return hashlib.sha256(user_agent.encode()).hexdigest()[:32]


def start_device_session(user, ip: str | None, ua: str | None, ttl_days: int = 30) -> str | None:
    """Create a device session (Session model) for long-lived login tracking.
    Returns the session_id on success, None on failure (non-fatal)."""
    from app.identity.models.user import Session as DeviceSession
    
    sid = str(uuid.uuid4())
    fingerprint = _device_fingerprint(ua)
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(days=ttl_days)
    # Absolute cap: 90 days from creation
    absolute_cap = now + timedelta(days=90)
    if expires_at > absolute_cap:
        expires_at = absolute_cap
    
    ds = DeviceSession(
        session_id=sid,
        user_id=user.id,  # internal BIGINT FK
        device_id=fingerprint,
        ip=ip,
        user_agent=ua[:512] if ua else None,
        expires_at=expires_at,
        revoked_at=None,
        revoked_reason=None,
    )
    try:
        db.session.add(ds)
        db.session.commit()

        # Check if this is a new device (first time seeing this fingerprint for this user)
        existing = DeviceSession.query.filter_by(user_id=user.id, device_id=fingerprint).filter(
            DeviceSession.session_id != sid
        ).first()
        is_new_device = existing is None

        # Audit session creation
        from app.audit.comprehensive_audit import AuditService
        try:
            AuditService.security(
                event_type="device_session_created",
                severity="INFO",
                description=f"New device session for user {user.public_id}",
                user_id=user.id,
                ip_address=ip,
                user_agent=ua,
                extra_data={
                    "session_id": sid,
                    "device_fingerprint": fingerprint,
                    "ttl_days": ttl_days,
                    "expires_at": ds.expires_at.isoformat(),
                    "is_new_device": is_new_device,
                }
            )
            # If new device, also fire a "new_signin" event for email notification
            if is_new_device:
                AuditService.security(
                    event_type="new_signin",
                    severity="INFO",
                    description=f"New device sign-in for user {user.public_id}",
                    user_id=user.id,
                    ip_address=ip,
                    user_agent=ua,
                    extra_data={
                        "session_id": sid,
                        "device_fingerprint": fingerprint,
                    }
                )
        except Exception as audit_error:
            import logging
            logging.error(f"Failed to audit device session creation: {audit_error}")

        return sid
    except Exception:
        db.session.rollback()
        import logging
        logging.error(f"Failed to create device session for user {user.public_id}")
        return None


def revoke_device_session(session_id: str, user_id: int = None, reason: str = "logout"):
    """Revoke a specific device session (Session model)."""
    from app.identity.models.user import Session as DeviceSession
    from app.audit.comprehensive_audit import AuditService
    from flask import request
    
    q = DeviceSession.query.filter_by(session_id=session_id, revoked_at=None)
    if user_id:
        q = q.filter_by(user_id=user_id)
    ds = q.first()
    if not ds:
        return False
    
    try:
        AuditService.security(
            event_type="device_session_revoked",
            severity="INFO",
            description=f"Device session revoked ({reason})",
            user_id=ds.user_id,
            ip_address=request.remote_addr if request else None,
            user_agent=request.user_agent.string if request and request.user_agent else None,
            extra_data={
                "session_id": session_id,
                "reason": reason,
            }
        )
    except Exception as audit_error:
        import logging
        logging.error(f"Failed to audit device session revocation: {audit_error}")
    
    ds.revoked_at = datetime.now(timezone.utc)
    ds.revoked_reason = reason
    try:
        db.session.commit()
        return True
    except Exception:
        db.session.rollback()
        raise


def revoke_all_device_sessions_for_user(user_id: int, reason: str = "revoke_all"):
    """Revoke all active device sessions for a user (sign out everywhere)."""
    from app.identity.models.user import Session as DeviceSession
    from app.audit.comprehensive_audit import AuditService
    from flask import request
    
    now = datetime.now(timezone.utc)
    sessions = DeviceSession.query.filter_by(user_id=user_id, revoked_at=None).all()
    
    try:
        for ds in sessions:
            ds.revoked_at = now
            ds.revoked_reason = reason
        db.session.commit()
        
        if sessions:
            AuditService.security(
                event_type="all_device_sessions_revoked",
                severity="WARNING",
                description=f"All device sessions revoked for user {user_id}",
                user_id=user_id,
                ip_address=request.remote_addr if request else None,
                user_agent=request.user_agent.string if request and request.user_agent else None,
                extra_data={
                    "count": len(sessions),
                    "reason": reason,
                }
            )
        return len(sessions)
    except Exception:
        db.session.rollback()
        raise


def touch_device_session(session_id: str) -> bool:
    """Sliding expiry: extend expires_at up to 90-day absolute cap from creation.
    Called on authenticated requests (throttled ~1/hour). Returns True if updated."""
    from app.identity.models.user import Session as DeviceSession
    
    ds = DeviceSession.query.filter_by(session_id=session_id, revoked_at=None).first()
    if not ds:
        return False
    
    now = datetime.now(timezone.utc)
    # Only extend if we're within 24h of expiry (throttle: avoid writing every request)
    # Actually check updated_at: only touch if last touch was >1 hour ago
    last_touch = ds.updated_at if ds.updated_at else ds.created_at
    if (now - last_touch).total_seconds() < 3600:
        return False
    
    # New expiry: now + 30 days, capped at 90 days from creation
    new_expiry = now + timedelta(days=30)
    absolute_cap = ds.created_at + timedelta(days=90)
    if new_expiry > absolute_cap:
        new_expiry = absolute_cap
    
    if new_expiry <= ds.expires_at:
        return False  # no extension needed
    
    ds.expires_at = new_expiry
    # updated_at auto-updates via BaseModel.onupdate
    try:
        db.session.commit()
        return True
    except Exception:
        db.session.rollback()
        return False
