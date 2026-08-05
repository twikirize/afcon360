"""
AFCON360 Unified Notification Models

Consolidated from app/models/notification.py and app/notifications/models.py.
All notification models inherit from BaseModel with BIGINT internal IDs.
"""

from datetime import datetime, timezone
from sqlalchemy import Column, BigInteger, String, Boolean, DateTime, JSON, Text, Integer, Index, CheckConstraint
from sqlalchemy.orm import relationship
from app.extensions import db
from app.models.base import BaseModel
import enum


class NotificationType(str, enum.Enum):
    """Types of notifications across the system."""
    # Accommodation
    PROPERTY_SUBMITTED = "property_submitted"
    PROPERTY_APPROVED = "property_approved"
    PROPERTY_REJECTED = "property_rejected"
    PROPERTY_CHANGES_REQUESTED = "property_changes_requested"
    PROPERTY_SUSPENDED = "property_suspended"
    PROPERTY_REINSTATED = "property_reinstated"
    PROPERTY_ARCHIVED = "property_archived"
    PROPERTY_RESTORED = "property_restored"
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

    # System
    SYSTEM_ALERT = "system_alert"
    PLATFORM_ANNOUNCEMENT = "platform_announcement"

    # Internal Messaging
    INTERNAL_MESSAGE = "internal_message"
    INTERNAL_REPLY = "internal_reply"
    ADMIN_NOTIFICATION = "admin_notification"
    SIGNUP_NOTIFICATION = "signup_notification"
    TRANSACTION_NOTIFICATION = "transaction_notification"
    MESSAGE_NOTIFICATION = "message_notification"


class NotificationChannel(str, enum.Enum):
    """Delivery channels for notifications."""
    IN_APP = "in_app"
    EMAIL = "email"
    SMS = "sms"
    PUSH = "push"
    WEBHOOK = "webhook"


class NotificationStatus(str, enum.Enum):
    """Lifecycle status of a notification."""
    PENDING = "pending"
    SENT = "sent"
    DELIVERED = "delivered"
    FAILED = "failed"
    READ = "read"
    CANCELLED = "cancelled"


class Notification(BaseModel):
    """
    Centralized notification record.
    All notifications across all modules use this model.
    """
    __tablename__ = 'notifications'
    __table_args__ = (
        Index('idx_notifications_user_status', 'user_id', 'is_read'),
        Index('idx_notifications_user_type', 'user_id', 'type'),
        Index('idx_notifications_created_at', 'created_at'),
        Index('idx_notifications_status', 'status'),
        CheckConstraint(
            "status IN ('pending','sent','delivered','failed','read','cancelled')",
            name='ck_notifications_status',
        ),
        CheckConstraint(
            "channel IN ('in_app','email','sms','push','webhook')",
            name='ck_notifications_channel',
        ),
        CheckConstraint(
            "type IN ("
            "'property_submitted','property_approved','property_rejected',"
            "'property_changes_requested','property_suspended','property_reinstated',"
            "'property_archived','property_restored','booking_confirmed','booking_cancelled',"
            "'review_received','verification_email','password_reset','login_alert',"
            "'booking_update','driver_assigned','event_registered','event_reminder',"
            "'deposit_confirmed','withdrawal_completed','transaction_completed','payment_received',"
            "'system_alert','platform_announcement','internal_message','internal_reply',"
            "'admin_notification','signup_notification','transaction_notification','message_notification'"
            ")",
            name='ck_notifications_type',
        ),
    )

    user_id = Column(BigInteger, db.ForeignKey('users.id'), nullable=True, index=True)
    email = Column(String(120), nullable=True)
    phone = Column(String(32), nullable=True)
    type = Column(String(50), nullable=False, index=True, server_default='system_alert')
    channel = Column(String(16), nullable=False, server_default='in_app')
    template_id = Column(BigInteger, db.ForeignKey('notification_templates.id'), nullable=True)
    context = Column(JSON, nullable=True)
    subject = Column(String(255), nullable=True)
    body = Column(Text, nullable=False, server_default='')
    priority = Column(String(16), default='normal')
    status = Column(String(16), server_default='pending')
    scheduled_for = Column(DateTime, nullable=True)
    sent_at = Column(DateTime, nullable=True)
    delivered_at = Column(DateTime, nullable=True)
    attempts = Column(BigInteger, default=0)
    last_error = Column(Text, nullable=True)
    external_id = Column(String(128), nullable=True, index=True)
    parent_id = Column(BigInteger, db.ForeignKey('notifications.id'), nullable=True)
    is_read = Column(Boolean, default=False)
    read_at = Column(DateTime, nullable=True)
    error_message = Column(Text, nullable=True)
    link = Column(String(512), nullable=True)  # Deep link for in-app navigation
    # Dead-letter tracking
    dead_letter = Column(Boolean, default=False)
    last_attempt_at = Column(DateTime, nullable=True)

    # Relationships
    user = relationship('User', foreign_keys=[user_id], lazy='noload')
    template = relationship('NotificationTemplate', foreign_keys=[template_id], lazy='noload')
    parent = relationship('Notification', remote_side='Notification.id', lazy='noload')

    def mark_read(self):
        self.is_read = True
        self.read_at = datetime.now(timezone.utc)
        self.status = NotificationStatus.READ

    def mark_sent(self):
        self.status = NotificationStatus.SENT
        self.sent_at = datetime.now(timezone.utc)

    def mark_delivered(self):
        self.status = NotificationStatus.DELIVERED
        self.delivered_at = datetime.now(timezone.utc)

    def mark_failed(self, error: str):
        self.status = NotificationStatus.FAILED
        self.error_message = error
        self.last_error = error
        self.sent_at = datetime.now(timezone.utc)

    def increment_attempts(self):
        self.attempts = (self.attempts or 0) + 1

    def __repr__(self):
        return f'<Notification {self.id}: {self.type} for user {self.user_id}>'


class NotificationTemplate(BaseModel):
    """Reusable notification templates per type and channel."""
    __tablename__ = 'notification_templates'

    type = Column(String(64), nullable=False, index=True)
    channel = Column(String(32), nullable=False, index=True)
    subject = Column(String(255), nullable=True)
    body_template = Column(Text, nullable=False)
    html_template = Column(Text, nullable=True)
    default_priority = Column(String(16), default='medium')
    is_active = Column(Boolean, default=True)

    def render(self, context: dict) -> str:
        from app.notifications.template_loader import template_loader
        return template_loader.render_template(
            f"{self.channel}/{self.type}.{'html' if self.channel == 'email' else 'txt'}",
            context
        )

    def __repr__(self):
        return f'<NotificationTemplate {self.id}: {self.type}/{self.channel}>'


class UserNotificationPreference(BaseModel):
    """Per-user, per-type, per-channel notification preferences."""
    __tablename__ = 'user_notification_preferences'

    user_id = Column(BigInteger, db.ForeignKey('users.id'), nullable=False, index=True)
    notification_type = Column(String(64), nullable=False)
    channel = Column(String(32), nullable=False)
    enabled = Column(Boolean, default=True)

    __table_args__ = (
        Index('idx_unp_user_type_channel', 'user_id', 'notification_type', 'channel', unique=True),
    )

    def __repr__(self):
        return f'<UserNotificationPreference {self.id}: user={self.user_id} type={self.notification_type} channel={self.channel}>'


class NotificationLog(BaseModel):
    """Audit log for each notification delivery attempt."""
    __tablename__ = 'notification_logs'

    notification_id = Column(BigInteger, db.ForeignKey('notifications.id'), nullable=False, index=True)
    channel = Column(String(32), nullable=False)
    status = Column(String(16), nullable=False)
    response_code = Column(BigInteger, nullable=True)
    response_body = Column(Text, nullable=True)
    attempted_at = Column(DateTime, default=datetime.utcnow)

    notification = relationship('Notification', foreign_keys=[notification_id], lazy='noload')

    def __repr__(self):
        return f'<NotificationLog {self.id}: notification={self.notification_id} channel={self.channel} status={self.status}>'


class CommunicationSettings(BaseModel):
    """
    Per-channel communication provider settings (SMTP, SendGrid, Twilio, FCM, etc.).
    Managed by owner/super_admin from the admin console. Secrets are stored encrypted
    at rest via the app's ENCRYPTION_KEY (handled by credentials JSON column).
    """
    __tablename__ = 'communication_settings'
    __table_args__ = (
        Index('idx_comm_settings_key', 'key'),
        Index('idx_comm_settings_channel', 'channel'),
    )

    key = Column(String(64), nullable=False, unique=True, index=True)
    channel = Column(String(32), nullable=False, index=True)  # email, sms, push, webhook
    provider = Column(String(64), nullable=True)  # sendgrid, twilio, fcm, mailgun, whatsapp
    enabled = Column(Boolean, default=True, nullable=False)
    config = Column(JSON, nullable=True)  # provider config (api keys redacted in API)
    description = Column(Text, nullable=True)
    updated_by = Column(BigInteger, nullable=True)

    def __repr__(self):
        return f'<CommunicationSettings {self.key}: {self.channel}/{self.provider} enabled={self.enabled}>'


class NotificationAggregator(BaseModel):
    """
    External messaging aggregators / gateways (Twilio, SendGrid, Firebase, WhatsApp Business,
    future SAP integration, etc.). Aggregators are tried in priority order for a channel.
    """
    __tablename__ = 'notification_aggregators'
    __table_args__ = (
        Index('idx_agg_provider_type', 'provider_type'),
        Index('idx_agg_enabled', 'enabled'),
    )

    name = Column(String(64), nullable=False, unique=True, index=True)
    provider_type = Column(String(64), nullable=False)  # twilio, sendgrid, fcm, whatsapp, sap
    channels = Column(JSON, nullable=False, default=list)  # list of channels supported
    enabled = Column(Boolean, default=True, nullable=False)
    credentials = Column(JSON, nullable=True)  # secret credentials (encrypted at rest)
    webhook_url = Column(String(512), nullable=True)
    priority = Column(Integer, default=10)  # lower = tried first
    updated_by = Column(BigInteger, nullable=True)

    def __repr__(self):
        return f'<NotificationAggregator {self.name}: {self.provider_type} enabled={self.enabled}>'


class Message(BaseModel):
    """
    Internal messaging model for bidirectional communication.
    Supports inbound (user-to-admin, user-to-user) and outbound (admin-to-user, system-to-user) messages.
    """
    __tablename__ = 'messages'
    __table_args__ = (
        Index('idx_messages_sender', 'sender_id'),
        Index('idx_messages_recipient', 'recipient_id'),
        Index('idx_messages_conversation', 'sender_id', 'recipient_id'),
        Index('idx_messages_created_at', 'created_at'),
    )

    sender_id = Column(BigInteger, db.ForeignKey('users.id'), nullable=False, index=True)
    recipient_id = Column(BigInteger, db.ForeignKey('users.id'), nullable=False, index=True)
    subject = Column(String(255), nullable=True)
    body = Column(Text, nullable=False)
    message_type = Column(String(32), default='in_app')  # in_app, email, sms, push
    direction = Column(String(16), default='outbound')  # inbound, outbound, system
    parent_id = Column(BigInteger, db.ForeignKey('messages.id'), nullable=True)  # For threading
    is_read = Column(Boolean, default=False)
    read_at = Column(DateTime, nullable=True)
    archived = Column(Boolean, default=False)
    archived_at = Column(DateTime, nullable=True)
    priority = Column(String(16), default='normal')
    notification_id = Column(BigInteger, db.ForeignKey('notifications.id'), nullable=True)

    # Relationships
    sender = relationship('User', foreign_keys=[sender_id], lazy='noload', overlaps='recipient')
    recipient = relationship('User', foreign_keys=[recipient_id], lazy='noload', overlaps='sender')
    parent_message = relationship('Message', remote_side='Message.id', lazy='noload')
    notification = relationship('Notification', foreign_keys=[notification_id], lazy='noload')

    def mark_read(self):
        self.is_read = True
        self.read_at = datetime.now(timezone.utc)

    def archive(self):
        self.archived = True
        self.archived_at = datetime.now(timezone.utc)

    def __repr__(self):
        return f'<Message {self.id}: from={self.sender_id} to={self.recipient_id} type={self.direction}>'