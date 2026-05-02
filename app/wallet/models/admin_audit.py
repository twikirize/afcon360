"""
Admin Audit Log Model
Tracks all admin actions for compliance and accountability
"""

from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey, Index
from app.extensions import db


class AdminAuditLog(db.Model):
    """
    System-level audit log for admin actions.
    
    Tracks who approved what, when, and why for compliance requirements.
    """
    __tablename__ = 'admin_audit_logs'
    
    __table_args__ = (
        Index('ix_admin_audit_admin_id', 'admin_id'),
        Index('ix_admin_audit_action_type', 'action_type'),
        Index('ix_admin_audit_target_type', 'target_type'),
        Index('ix_admin_audit_created_at', 'created_at'),
    )
    
    id = Column(Integer, primary_key=True)
    
    # Who performed the action
    admin_id = Column(Integer, ForeignKey('users.id'), nullable=False, index=True)
    admin_name = Column(String(255), nullable=False)
    admin_role = Column(String(50), nullable=False)
    
    # What action was performed
    action_type = Column(String(50), nullable=False, index=True)  # e.g., 'approve', 'reject', 'configure', 'modify'
    action_category = Column(String(50), nullable=False)  # e.g., 'aggregator', 'fraud_detection', 'payment_gateway'
    
    # What was affected
    target_type = Column(String(50), nullable=False, index=True)  # e.g., 'aggregator', 'user', 'transaction'
    target_id = Column(String(255), nullable=True)
    target_name = Column(String(255), nullable=True)
    
    # Action details
    old_value = Column(Text, nullable=True)  # JSON string of previous state
    new_value = Column(Text, nullable=True)  # JSON string of new state
    
    # Reason and context
    reason = Column(Text, nullable=True)
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(Text, nullable=True)
    
    # Metadata
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    
    def to_dict(self):
        """Convert to dictionary for JSON serialization"""
        return {
            'id': self.id,
            'admin_id': self.admin_id,
            'admin_name': self.admin_name,
            'admin_role': self.admin_role,
            'action_type': self.action_type,
            'action_category': self.action_category,
            'target_type': self.target_type,
            'target_id': self.target_id,
            'target_name': self.target_name,
            'old_value': self.old_value,
            'new_value': self.new_value,
            'reason': self.reason,
            'ip_address': self.ip_address,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }
    
    def __repr__(self):
        return f"<AdminAuditLog {self.id}: {self.admin_name} - {self.action_type} on {self.target_type}>"
