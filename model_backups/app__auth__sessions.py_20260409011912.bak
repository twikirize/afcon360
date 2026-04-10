# app/auth/sessions.py
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
    except Exception:
        db.session.rollback()
        # If storage fails, return an id anyway for client correlation (non-fatal)
    return sid

def revoke_session(session_id: str):
    s = ServerSession.query.filter_by(session_id=session_id, is_revoked=False).first()
    if not s:
        return False
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
