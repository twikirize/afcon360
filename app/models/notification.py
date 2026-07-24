from sqlalchemy import Column, BigInteger, String, Boolean, DateTime, JSON, Text, Enum as SQLEnum
from sqlalchemy.orm import relationship
from app.models.base import BaseModel
from app.extensions import db
import enum
from datetime import datetime, timezone


class NotificationType(enum.Enum):
    """Types of notifications across the system."""
    # Accommodation
    PROPERTY_SUBMITTED = "property_submitted"
    PROPERTY_APPROVED = "property_approved"
    PROPERTY_REJECTED = "property_rejected"
    PROPERTY_CHANGES_REQUESTED = "property_changes_requested"
    PROPERTY_SUSPENDED = "property_suspended"
    PROPERTY_REINSTATED = "property_reinstated"
    BOOKING_CONFIRMED = "booking_confirmed"
    BOOKING_CANCELLED = "booking_cancelled"
    REVIEW_RECEIVED = "review_received"
    
    # Auth
    VERIFICATION_EMAIL = "verification_email"
    PASSWORD_RESET = "password_reset"
    LOGIN_ALERT = "login_alert"
    
    # Transport
    BOOKING_UPDATE = "booking_update"
    DRIVER_ASSIGNED = "driver_assigned"
    
    # Events
    EVENT_REGISTERED = "event_registered"
    EVENT_REMINDER = "event_reminder"
    
    # Wallet
    DEPOSIT_CONFIRMED = "deposit_confirmed"
    WITHDRAWAL_COMPLETED = "withdrawal_completed"
    TRANSACTION_COMPLETED = "transaction_completed"
    PAYMENT_RECEIVED = "payment_received"


class NotificationChannel(enum.Enum):
    """Delivery channels for notifications."""
    IN_APP = "in_app"
    EMAIL = "email"
    SMS = "sms"
    PUSH = "push"


class Notification(BaseModel):
    """
    Centralized notification record.
    All notifications across all modules use this model.
    """
    __tablename__ = 'notifications'
    __table_args__ = (
        db.Index('idx_notifications_user_status', 'user_id', 'is_read'),
        db.Index('idx_notifications_user_type', 'user_id', 'type'),
        db.Index('idx_notifications_created_at', 'created_at'),
    )

    user_id = Column(BigInteger, db.ForeignKey('users.id'), nullable=False, index=True)
    type = Column(SQLEnum(NotificationType), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    message = Column(Text, nullable=False)
    data = Column(JSON, default={})
    link = Column(String(500), nullable=True)
    priority = Column(String(20), default='normal')  # high, normal, low
    status = Column(String(20), default='pending')  # pending, sent, failed, delivered
    channels = Column(JSON, default=['in_app'])  # List of channels to send to
    is_read = Column(Boolean, default=False, index=True)
    read_at = Column(DateTime, nullable=True)
    sent_at = Column(DateTime, nullable=True)
    delivered_at = Column(DateTime, nullable=True)
    error_message = Column(Text, nullable=True)
    
    # Relationships
    user = relationship('User', foreign_keys=[user_id])
    
    def mark_read(self):
        """Mark notification as read."""
        self.is_read = True
        self.read_at = datetime.now(timezone.utc)
    
    def mark_sent(self):
        """Mark notification as sent."""
        self.status = 'sent'
        self.sent_at = datetime.now(timezone.utc)
    
    def mark_delivered(self):
        """Mark notification as delivered."""
        self.status = 'delivered'
        self.delivered_at = datetime.now(timezone.utc)
    
    def mark_failed(self, error: str):
        """Mark notification as failed."""
        self.status = 'failed'
        self.error_message = error
        self.sent_at = datetime.now(timezone.utc)
    
    def __repr__(self):
        return f'<Notification {self.id}: {self.type.value} for user {self.user_id}>'
