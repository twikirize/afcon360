"""
Global Audit Trail Model
Records every significant change across the system.
"""

from datetime import datetime
from app.extensions import db
from app.models.base import BaseModel

class ActivityLog(BaseModel):
    """
    Tracks 'Who did What to Whom'
    Includes support for showing Old vs New values
    """
    __tablename__ = 'activity_logs'

    # Actor (Who)
    actor_id = db.Column(db.BigInteger, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True, index=True)

    # Action (What)
    action = db.Column(db.String(50), nullable=False, index=True) # e.g., 'UPDATE', 'DELETE', 'LOGIN'

    # Resource (Whom)
    target_type = db.Column(db.String(50), nullable=False, index=True) # e.g., 'USER', 'BOOKING'
    target_id = db.Column(db.BigInteger, nullable=True, index=True)

    # Details (The Diff)
    changes = db.Column(db.JSON, nullable=True) # e.g., {"status": ["pending", "confirmed"]}

    # Metadata
    ip_address = db.Column(db.String(45))
    user_agent = db.Column(db.String(255))

    # Relationship
    actor = db.relationship('User', foreign_keys=[actor_id])

    @classmethod
    def log(cls, action, target, actor=None, changes=None, request=None):
        """Helper to create a log entry"""
        log_entry = cls(
            action=action,
            target_type=target.__class__.__name__.upper(),
            target_id=getattr(target, 'id', None),
            changes=changes,
            actor_id=getattr(actor, 'id', None)
        )

        if request:
            log_entry.ip_address = request.remote_addr
            log_entry.user_agent = request.headers.get('User-Agent')

        db.session.add(log_entry)
        # We don't commit here to allow the main transaction to control the flow
        return log_entry
