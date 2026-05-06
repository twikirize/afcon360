# app/admin/models/emergency_access.py
"""
Emergency Access Model for critical incidents.

Provides "break glass" emergency access with mandatory approval,
ticket numbers, and time limits for critical situations.
"""

from datetime import datetime, timezone, timedelta
from sqlalchemy import (
    Column, BigInteger, String, Text, DateTime, Boolean, 
    ForeignKey, Index
)
from sqlalchemy.orm import relationship
from app.extensions import db
from app.models.base import BaseModel


class EmergencyAccess(BaseModel):
    """
    Emergency access grant for critical incidents.
    
    Facebook-style "break glass" procedure for critical situations
    requiring immediate access with proper audit trail.
    """
    __tablename__ = "emergency_access"
    __table_args__ = (
        Index("ix_emergency_access_granted_to", "granted_to"),
        Index("ix_emergency_access_expires_at", "expires_at"),
        Index("ix_emergency_access_active", "is_active"),
    )

    # Who gets emergency access
    granted_to = Column(
        BigInteger, 
        ForeignKey("users.id", ondelete="CASCADE"), 
        nullable=False, 
        index=True
    )
    
    # Who granted it (must be owner or secops)
    granted_by = Column(
        BigInteger, 
        ForeignKey("users.id", ondelete="SET NULL"), 
        nullable=True
    )
    
    # Security operations approval (second person required for high-risk access)
    approved_by_secops = Column(
        BigInteger, 
        ForeignKey("users.id", ondelete="SET NULL"), 
        nullable=True
    )
    
    # Required fields for audit compliance
    reason = Column(Text, nullable=False)  # Detailed reason required
    jira_ticket = Column(String(100), nullable=False)  # Ticket number required
    incident_type = Column(String(50), nullable=False)  # "security", "outage", "compliance"
    
    # Access scope and limits
    access_level = Column(String(50), nullable=False, default="read_only")  # "read_only", "full", "limited"
    allowed_actions = Column(db.JSON, nullable=True)  # Specific actions allowed
    
    # Time controls (strictly enforced)
    expires_at = Column(DateTime, nullable=False, index=True)  # Max 4 hours
    started_at = Column(DateTime, nullable=True)  # When access was first used
    ended_at = Column(DateTime, nullable=True)  # When access ended (auto or manual)
    
    # Status tracking
    is_active = Column(Boolean, default=True, nullable=False, index=True)
    is_used = Column(Boolean, default=False, nullable=False)  # Track if access was used
    
    # Relationships
    granted_user = relationship("User", foreign_keys=[granted_to])
    granter = relationship("User", foreign_keys=[granted_by])
    secops_approver = relationship("User", foreign_keys=[approved_by_secops])
    
    def __init__(self, **kwargs):
        # Set default expiration (4 hours max) if not provided
        if 'expires_at' not in kwargs:
            kwargs['expires_at'] = datetime.now(timezone.utc) + timedelta(hours=4)
        super().__init__(**kwargs)
    
    @classmethod
    def create_emergency_access(
        cls,
        granted_to_user_id: int,
        granted_by_user_id: int,
        reason: str,
        jira_ticket: str,
        incident_type: str = "security",
        access_level: str = "read_only",
        allowed_actions: list = None,
        duration_hours: int = 4,
        secops_approval_user_id: int = None
    ):
        """
        Create emergency access with proper validation.
        
        Args:
            granted_to_user_id: User who receives emergency access
            granted_by_user_id: User granting access (must be owner/secops)
            reason: Detailed reason for emergency access
            jira_ticket: Ticket reference number
            incident_type: Type of incident
            access_level: Level of access granted
            allowed_actions: Specific actions allowed (if limited)
            duration_hours: Duration in hours (max 4)
            secops_approval_user_id: Secondary approval for high-risk access
        
        Returns:
            EmergencyAccess instance
        """
        # Validate required fields
        if not reason or len(reason.strip()) < 20:
            raise ValueError("Reason must be at least 20 characters")
        
        if not jira_ticket or len(jira_ticket.strip()) < 3:
            raise ValueError("JIRA ticket number is required")
        
        if duration_hours > 4:
            raise ValueError("Emergency access cannot exceed 4 hours")
        
        # High-risk access requires secondary approval
        if access_level in ["full", "admin"] and not secops_approval_user_id:
            raise ValueError(f"Access level '{access_level}' requires security operations approval")
        
        emergency_access = cls(
            granted_to=granted_to_user_id,
            granted_by=granted_by_user_id,
            approved_by_secops=secops_approval_user_id,
            reason=reason.strip(),
            jira_ticket=jira_ticket.strip(),
            incident_type=incident_type,
            access_level=access_level,
            allowed_actions=allowed_actions,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=duration_hours)
        )
        
        return emergency_access
    
    def is_valid(self) -> bool:
        """Check if emergency access is currently valid."""
        if not self.is_active:
            return False
        
        if datetime.now(timezone.utc) > self.expires_at:
            return False
        
        return True
    
    def can_perform_action(self, action: str) -> bool:
        """Check if specific action is allowed."""
        if not self.is_valid():
            return False
        
        # Mark as used when first action is performed
        if not self.is_used:
            self.is_used = True
            if not self.started_at:
                self.started_at = datetime.now(timezone.utc)
        
        # Check action permissions
        if self.access_level == "full":
            return True
        elif self.access_level == "read_only":
            read_only_actions = ["view", "read", "list", "search", "audit"]
            return any(action.lower().startswith(ro) for ro in read_only_actions)
        elif self.access_level == "limited" and self.allowed_actions:
            return action in self.allowed_actions
        
        return False
    
    def revoke(self, revoked_by_user_id: int = None, reason: str = None):
        """Revoke emergency access immediately."""
        self.is_active = False
        self.ended_at = datetime.now(timezone.utc)
        
        # Log revocation
        from app.audit.comprehensive_audit import AuditService
        try:
            AuditService.data_change(
                entity_type="emergency_access",
                entity_id=self.id,
                operation="revoke",
                old_value={"is_active": True},
                new_value={
                    "is_active": False,
                    "ended_at": self.ended_at.isoformat(),
                    "revoke_reason": reason
                },
                changed_by=revoked_by_user_id,
                extra_data={
                    "emergency_access_id": self.id,
                    "granted_to": self.granted_to,
                    "jira_ticket": self.jira_ticket
                }
            )
        except Exception as e:
            import logging
            logging.error(f"Failed to audit emergency access revocation: {e}")
    
    def auto_expire_check(self):
        """Check if access should be auto-expired and update accordingly."""
        if datetime.now(timezone.utc) > self.expires_at and self.is_active:
            self.revoke(reason="Auto-expired")
    
    @classmethod
    def get_active_emergency_access(cls, user_id: int) -> list["EmergencyAccess"]:
        """Get all active emergency access for a user."""
        return cls.query.filter(
            cls.granted_to == user_id,
            cls.is_active == True,
            cls.expires_at > datetime.now(timezone.utc)
        ).all()
    
    @classmethod
    def cleanup_expired_access(cls):
        """Clean up expired emergency access records."""
        expired = cls.query.filter(
            cls.expires_at < datetime.now(timezone.utc),
            cls.is_active == True
        ).all()
        
        for access in expired:
            access.revoke(reason="Auto-cleanup expired")
        
        return len(expired)


# Add relationship to User model
def add_user_emergency_relationship():
    """Add emergency access relationship to User model."""
    from app.identity.models.user import User
    
    if not hasattr(User, 'emergency_access_granted'):
        User.emergency_access_granted = relationship(
            "EmergencyAccess",
            foreign_keys=[EmergencyAccess.granted_to],
            back_populates="granted_user",
            cascade="all, delete-orphan"
        )
