# app/auth/sessions.py
# Note: This file doesn't contain "KYC data injection error" or "Audit summary injection error"
# This file doesn't contain "KYC data injection error" or "Audit summary injection error"
from datetime import datetime, timedelta
import uuid
from app.extensions import db
from app.models.base import BaseModel

class ServerSession(BaseModel):
    __tablename__ = "server_sessions"
    session_id = db.Column(db.String(128), unique=True, nullable=False, index=True)
    user_id = db.Column(db.String(64), nullable=False, index=True)  # public user_id (UUID/ULID)
    ip_address = db.Column(db.String(45), nullable=True)
    user_agent = db.Column(db.String(255), nullable=True)
    expires_at = db.Column(db.DateTime, nullable=False)
    is_revoked = db.Column(db.Boolean, default=False, nullable=False)

def start_server_session(public_user_id: str, ip: str | None, ua: str | None, ttl_hours: int = 12) -> str:
    sid = str(uuid.uuid4())
    ss = ServerSession(
        session_id=sid,
        user_id=public_user_id,
        ip_address=ip,
        user_agent=ua,
        expires_at=datetime.utcnow() + timedelta(hours=ttl_hours),
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
