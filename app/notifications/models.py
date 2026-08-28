"""
AFCON360 Unified Notification Models

Consolidated from app/models/notification.py and app/notifications/models.py.
All notification models inherit from BaseModel with BIGINT internal IDs.
"""

from datetime import datetime, timezone
from sqlalchemy import Column, BigInteger, String, Boolean, DateTime, JSON, Text, Integer, Index, CheckConstraint
from sqlalchemy.orm import relationship, validates
from app.extensions import db
from app.models.base import BaseModel
import enum


def _notification_type_check() -> str:
    """Generate CHECK constraint SQL from NotificationType enum."""
    values = ",".join(f"'{v.value}'" for v in NotificationType)
    return f"type IN ({values})"


def _notification_channel_check() -> str:
    """Generate CHECK constraint SQL from NotificationChannel enum."""
    values = ",".join(f"'{v.value}'" for v in NotificationChannel)
    return f"channel IN ({values})"


def _notification_module_check() -> str:
    """Generate CHECK constraint SQL from NotificationModule enum."""
    values = ",".join(f"'{v.value}'" for v in NotificationModule)
    return f"module IN ({values})"


def _notification_status_check() -> str:
    """Generate CHECK constraint SQL from NotificationStatus enum."""
    values = ",".join(f"'{v.value}'" for v in NotificationStatus)
    return f"status IN ({values})"


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
    BOOKING_PENDING = "booking_pending"
    BOOKING_THIRD_PARTY = "third_party_booking"
    BOOKING_CANCELLED = "booking_cancelled"
    BOOKING_PENDING_APPROVAL = "booking_pending_approval"
    BOOKING_APPROVED = "booking_approved"
    BOOKING_REJECTED = "booking_rejected"
    BOOKING_PAYMENT_RECEIVED_PENDING_APPROVAL = "booking_payment_received_pending_approval"
    REVIEW_RECEIVED = "review_received"
    ACCOMMODATION_COMPLAINT_OPENED = "accommodation_complaint_opened"
    BOOKING_EXPIRED = "booking_expired"
    BOOKING_NO_SHOW = "booking_no_show"
    EVENT_ACCOMMODATION_ASSIGNED = "event_accommodation_assigned"
    EVENT_ACCOMMODATION_CANCELLED = "event_accommodation_cancelled"

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
    EVENT_STAFF_ADDED = "event_staff_added"
    EVENT_STAFF_REMOVED = "event_staff_removed"
    EVENT_STAFF_UPDATED = "event_staff_updated"

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

    # Compliance case lifecycle
    COMPLIANCE_CASE_CREATED = "compliance_case_created"
    COMPLIANCE_CASE_ASSIGNED = "compliance_case_assigned"
    COMPLIANCE_CASE_UPDATED = "compliance_case_updated"
    COMPLIANCE_CASE_ESCALATED = "compliance_case_escalated"
    COMPLIANCE_CASE_RESOLVED = "compliance_case_resolved"


class NotificationChannel(str, enum.Enum):
    """Delivery channels for notifications."""
    IN_APP = "in_app"
    EMAIL = "email"
    SMS = "sms"
    PUSH = "push"
    WEBHOOK = "webhook"


class NotificationModule(str, enum.Enum):
    """
    Originating module for a notification.

    AFCON360 is a multi-module ecosystem: accommodation, transport, events,
    wallet and tourism are independent businesses with different customers and
    different activities, even though they share one notification system.

    The `type` alone is NOT enough to tell them apart — `booking_confirmed` is
    emitted by accommodation, transport AND tourism. This field is what lets a
    dashboard show only its own module's activity, and lets the UI badge each
    item with the business it came from.
    """
    ACCOMMODATION = "accommodation"
    TRANSPORT = "transport"
    EVENTS = "events"
    WALLET = "wallet"
    TOURISM = "tourism"
    TOURNAMENT = "tournament"
    IDENTITY = "identity"
    KYC = "kyc"
    ACCOUNT = "account"        # auth / signup / profile / sessions
    MESSAGING = "messaging"    # internal user-to-user messages
    COMPLIANCE = "compliance"  # compliance case lifecycle (KYC/KYB/AML/DSR reviews)
    SYSTEM = "system"          # platform-wide announcements, admin alerts


# Human-facing labels + accent colours per module, used by the notification
# bell so a user can tell a hotel booking from a bus booking at a glance.
MODULE_LABELS = {
    NotificationModule.ACCOMMODATION.value: "Accommodation",
    NotificationModule.TRANSPORT.value:     "Transport",
    NotificationModule.EVENTS.value:        "Events",
    NotificationModule.WALLET.value:        "Wallet",
    NotificationModule.TOURISM.value:       "Tourism",
    NotificationModule.TOURNAMENT.value:    "Tournament",
    NotificationModule.IDENTITY.value:      "Identity",
    NotificationModule.KYC.value:           "KYC",
    NotificationModule.COMPLIANCE.value:    "Compliance",
    NotificationModule.ACCOUNT.value:       "Account",
    NotificationModule.MESSAGING.value:     "Messages",
    NotificationModule.SYSTEM.value:        "System",
}

MODULE_ICONS = {
    NotificationModule.ACCOMMODATION.value: "bi-house-door",
    NotificationModule.TRANSPORT.value:     "bi-bus-front",
    NotificationModule.EVENTS.value:        "bi-calendar-event",
    NotificationModule.WALLET.value:        "bi-wallet2",
    NotificationModule.TOURISM.value:       "bi-globe-americas",
    NotificationModule.TOURNAMENT.value:    "bi-trophy",
    NotificationModule.IDENTITY.value:      "bi-person-vcard",
    NotificationModule.KYC.value:           "bi-shield-check",
    NotificationModule.COMPLIANCE.value:    "bi-clipboard-check",
    NotificationModule.ACCOUNT.value:       "bi-person-circle",
    NotificationModule.MESSAGING.value:     "bi-chat-dots",
    NotificationModule.SYSTEM.value:        "bi-megaphone",
}

MODULE_COLORS = {
    NotificationModule.ACCOMMODATION.value: "#4a9d7f",
    NotificationModule.TRANSPORT.value:     "#4a7fb5",
    NotificationModule.EVENTS.value:        "#c9772e",
    NotificationModule.WALLET.value:        "#d4af37",
    NotificationModule.TOURISM.value:       "#8a63b8",
    NotificationModule.TOURNAMENT.value:    "#b5504a",
    NotificationModule.IDENTITY.value:      "#5a8fa8",
    NotificationModule.KYC.value:           "#5a8fa8",
    NotificationModule.COMPLIANCE.value:    "#b5504a",
    NotificationModule.ACCOUNT.value:       "#7a8290",
    NotificationModule.MESSAGING.value:     "#6b8fb5",
    NotificationModule.SYSTEM.value:        "#7a8290",
}


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
        # Per-module dashboard queries: "unread transport notifications for me"
        Index('idx_notifications_user_module', 'user_id', 'module', 'is_read'),
        CheckConstraint(
            _notification_status_check(),
            name='ck_notifications_status',
        ),
        CheckConstraint(
            _notification_channel_check(),
            name='ck_notifications_channel',
        ),
        CheckConstraint(
            _notification_module_check(),
            name='ck_notifications_module',
        ),
        CheckConstraint(
            _notification_type_check(),
            name='ck_notifications_type',
        ),
    )

    user_id = Column(BigInteger, db.ForeignKey('users.id'), nullable=True, index=True)
    email = Column(String(120), nullable=True)
    phone = Column(String(32), nullable=True)
    type = Column(String(50), nullable=False, index=True, server_default='system_alert')
    # Originating business module. `type` is ambiguous across modules
    # (booking_confirmed is emitted by accommodation, transport and tourism),
    # so this is the field dashboards filter on.
    module = Column(String(32), nullable=False, index=True, server_default='system')
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
    is_important = Column(Boolean, default=False, nullable=False, index=True, server_default='false')
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

    def mark_unread(self):
        self.is_read = False
        self.read_at = None
        if self.status == NotificationStatus.READ:
            self.status = NotificationStatus.DELIVERED

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

    # -- Module presentation helpers (used by the notification bell) --------

    @property
    def module_label(self) -> str:
        """Human-facing module name, e.g. 'Transport'."""
        return MODULE_LABELS.get(self.module, 'System')

    @property
    def module_icon(self) -> str:
        """Bootstrap icon class for the originating module."""
        return MODULE_ICONS.get(self.module, 'bi-bell')

    @property
    def module_color(self) -> str:
        """Accent colour so each module is visually distinct in the inbox."""
        return MODULE_COLORS.get(self.module, '#7a8290')

    def __repr__(self):
        return f'<Notification {self.id}: {self.module}/{self.type} for user {self.user_id}>'

    # -- Application-level enforcement ---------------------------------------
    # The CHECK constraints on `notifications` are only a DB backstop. We
    # enforce the allowed vocabularies here in Flask so a bad value (e.g. a typo
    # like 'emial') raises immediately on assignment, regardless of which code
    # path constructs the record — and so it is caught even before a fresh
    # `db.create_all()` / migration has applied the constraints.
    @validates('type')
    def _validate_type(self, key, value):
        if value is None:
            raise ValueError("Notification.type must not be None")
        return NotificationType(value).value

    @validates('channel')
    def _validate_channel(self, key, value):
        if value is None:
            raise ValueError("Notification.channel must not be None")
        return NotificationChannel(value).value

    @validates('module')
    def _validate_module(self, key, value):
        if value is None:
            raise ValueError("Notification.module must not be None")
        return NotificationModule(value).value

    @validates('status')
    def _validate_status(self, key, value):
        if value is None:
            raise ValueError("Notification.status must not be None")
        return NotificationStatus(value).value


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


class DeliveryStatus(str, enum.Enum):
    """
    Per-channel delivery lifecycle.

    Distinct from `NotificationStatus`: a Notification is one logical message,
    but each channel has its own independent fate. "Queued" and "accepted by the
    provider" are NOT "delivered", and a bounced email must not be conflated
    with a failed push.
    """
    QUEUED = "queued"          # created, not yet handed to a provider
    SENDING = "sending"        # handler is executing
    ACCEPTED = "accepted"      # provider took it (SMTP 250 / FCM ack)
    DELIVERED = "delivered"    # confirmed reaching the recipient
    BOUNCED = "bounced"        # hard rejection from the destination
    FAILED = "failed"          # transport error
    SUPPRESSED = "suppressed"  # blocked by preference/policy — never attempted
    READ = "read"              # recipient opened it (in-app / tracked email)


class NotificationDelivery(BaseModel):
    """
    Per-channel delivery record for a single Notification.

    Solves the "one notification, one global status" problem: a notification
    fanned out to email + push + in_app now tracks three independent outcomes::

        Notification
            |-- InAppDelivery  -> READ
            |-- EmailDelivery  -> DELIVERED
            +-- PushDelivery   -> FAILED

    `NotificationLog` remains the append-only per-attempt audit trail; this is
    the current authoritative state per channel.
    """

    __tablename__ = 'notification_deliveries'
    __table_args__ = (
        Index('idx_notif_deliveries_notification', 'notification_id'),
        Index('idx_notif_deliveries_status', 'status'),
        Index('idx_notif_deliveries_channel_status', 'channel', 'status'),
        Index('idx_notif_deliveries_retry', 'status', 'next_retry_at'),
        CheckConstraint(
            "channel IN ('in_app','email','sms','push','webhook')",
            name='ck_notif_deliveries_channel',
        ),
        CheckConstraint(
            "status IN ('queued','sending','accepted','delivered','bounced',"
            "'failed','suppressed','read')",
            name='ck_notif_deliveries_status',
        ),
    )

    notification_id = Column(
        BigInteger, db.ForeignKey('notifications.id'), nullable=False, index=True
    )
    channel = Column(String(16), nullable=False, index=True)
    status = Column(String(16), nullable=False, default=DeliveryStatus.QUEUED.value, index=True)

    # Which gateway actually carried it (sendgrid, twilio, fcm, smtp...).
    provider = Column(String(64), nullable=True)
    # Provider-side id, used to reconcile async delivery webhooks back to us.
    provider_message_id = Column(String(255), nullable=True, index=True)

    recipient = Column(String(255), nullable=True)
    attempts = Column(Integer, nullable=False, default=0)
    max_attempts = Column(Integer, nullable=False, default=5)
    next_retry_at = Column(DateTime, nullable=True)

    response_code = Column(Integer, nullable=True)
    error = Column(Text, nullable=True)

    queued_at = Column(DateTime, nullable=True, default=lambda: datetime.now(timezone.utc))
    sent_at = Column(DateTime, nullable=True)
    delivered_at = Column(DateTime, nullable=True)
    read_at = Column(DateTime, nullable=True)

    # Correlation id of the originating domain event, so a delivery can be
    # traced back through the whole journey during an incident.
    correlation_id = Column(String(64), nullable=True, index=True)

    notification = relationship('Notification', foreign_keys=[notification_id], lazy='noload')

    def mark_accepted(self, provider_message_id: str = None, provider: str = None):
        self.status = DeliveryStatus.ACCEPTED.value
        self.sent_at = datetime.now(timezone.utc)
        if provider_message_id:
            self.provider_message_id = provider_message_id
        if provider:
            self.provider = provider

    def mark_delivered(self):
        self.status = DeliveryStatus.DELIVERED.value
        self.delivered_at = datetime.now(timezone.utc)

    def mark_failed(self, error: str, response_code: int = None):
        self.status = DeliveryStatus.FAILED.value
        self.error = (error or '')[:2000]
        self.response_code = response_code

    def mark_suppressed(self, reason: str):
        self.status = DeliveryStatus.SUPPRESSED.value
        self.error = (reason or '')[:2000]

    def __repr__(self):
        return (
            f'<NotificationDelivery {self.id}: notification={self.notification_id} '
            f'{self.channel}/{self.status}>'
        )

    # -- Application-level enforcement (see Notification._validate_* notes) --
    @validates('channel')
    def _validate_channel(self, key, value):
        if value is None:
            raise ValueError("NotificationDelivery.channel must not be None")
        return NotificationChannel(value).value

    @validates('status')
    def _validate_status(self, key, value):
        if value is None:
            raise ValueError("NotificationDelivery.status must not be None")
        return DeliveryStatus(value).value


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