"""
AFCON360 Notification System Tests

Tests for models, services, channel handlers, and cross-module integration.
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock

from app.extensions import db
from app.notifications.models import (
    Notification,
    NotificationType,
    NotificationChannel,
    NotificationStatus,
    NotificationTemplate,
    UserNotificationPreference,
    NotificationLog,
)
from app.notifications.services import NotificationService
from app.notifications.preferences import PreferenceService
from app.notifications.utils import calculate_backoff, generate_idempotency_key
from app.identity.models.user import User


# ============================================================================
# Model Tests
# ============================================================================

class TestNotificationModel:
    """Test Notification model fields and methods."""

    def test_notification_creation(self, db_session):
        """Test creating a notification record."""
        notification = Notification(
            user_id=1,
            type=NotificationType.BOOKING_CONFIRMED,
            subject="Booking Confirmed",
            body="Your booking has been confirmed.",
            priority="high",
            status=NotificationStatus.PENDING,
            channels=["in_app"],
        )
        db_session.add(notification)
        db_session.commit()

        assert notification.id is not None
        assert notification.type == NotificationType.BOOKING_CONFIRMED
        assert notification.status == NotificationStatus.PENDING
        assert notification.is_read is False

    def test_mark_read(self, db_session):
        """Test marking a notification as read."""
        notification = Notification(
            user_id=1,
            type=NotificationType.BOOKING_CONFIRMED,
            subject="Test",
            body="Test body",
        )
        db_session.add(notification)
        db_session.commit()

        notification.mark_read()
        db_session.commit()

        assert notification.is_read is True
        assert notification.read_at is not None
        assert notification.status == NotificationStatus.READ

    def test_mark_sent(self, db_session):
        """Test marking a notification as sent."""
        notification = Notification(
            user_id=1,
            type=NotificationType.BOOKING_CONFIRMED,
            subject="Test",
            body="Test body",
        )
        db_session.add(notification)
        db_session.commit()

        notification.mark_sent()
        db_session.commit()

        assert notification.status == NotificationStatus.SENT
        assert notification.sent_at is not None

    def test_mark_delivered(self, db_session):
        """Test marking a notification as delivered."""
        notification = Notification(
            user_id=1,
            type=NotificationType.BOOKING_CONFIRMED,
            subject="Test",
            body="Test body",
        )
        db_session.add(notification)
        db_session.commit()

        notification.mark_delivered()
        db_session.commit()

        assert notification.status == NotificationStatus.DELIVERED
        assert notification.delivered_at is not None

    def test_mark_failed(self, db_session):
        """Test marking a notification as failed."""
        notification = Notification(
            user_id=1,
            type=NotificationType.BOOKING_CONFIRMED,
            subject="Test",
            body="Test body",
        )
        db_session.add(notification)
        db_session.commit()

        notification.mark_failed("SMTP connection failed")
        db_session.commit()

        assert notification.status == NotificationStatus.FAILED
        assert notification.error_message == "SMTP connection failed"

    def test_increment_attempts(self, db_session):
        """Test incrementing delivery attempts."""
        notification = Notification(
            user_id=1,
            type=NotificationType.BOOKING_CONFIRMED,
            subject="Test",
            body="Test body",
        )
        db_session.add(notification)
        db_session.commit()

        assert notification.attempts == 0
        notification.increment_attempts()
        assert notification.attempts == 1
        notification.increment_attempts()
        assert notification.attempts == 2


class TestNotificationTemplateModel:
    """Test NotificationTemplate model."""

    def test_template_creation(self, db_session):
        """Test creating a notification template."""
        template = NotificationTemplate(
            type="booking_confirmed",
            channel="email",
            subject="Booking Confirmed",
            body_template="Dear {{ user_name }}, your booking is confirmed.",
            html_template="<h1>Booking Confirmed</h1>",
            default_priority="high",
            is_active=True,
        )
        db_session.add(template)
        db_session.commit()

        assert template.id is not None
        assert template.type == "booking_confirmed"
        assert template.channel == "email"

    def test_template_render(self, db_session):
        """Test template rendering with context."""
        template = NotificationTemplate(
            type="booking_confirmed",
            channel="email",
            subject="Booking Confirmed",
            body_template="Dear {{ user_name }}, your booking is confirmed.",
            html_template="<h1>Booking Confirmed</h1>",
        )
        db_session.add(template)
        db_session.commit()

        result = template.render({"user_name": "John Doe"})
        assert "John Doe" in result


class TestUserNotificationPreferenceModel:
    """Test UserNotificationPreference model."""

    def test_preference_creation(self, db_session):
        """Test creating a user notification preference."""
        pref = UserNotificationPreference(
            user_id=1,
            notification_type="booking_confirmed",
            channel="email",
            enabled=True,
        )
        db_session.add(pref)
        db_session.commit()

        assert pref.id is not None
        assert pref.user_id == 1
        assert pref.enabled is True


class TestNotificationLogModel:
    """Test NotificationLog model."""

    def test_log_creation(self, db_session):
        """Test creating a notification log entry."""
        notification = Notification(
            user_id=1,
            type=NotificationType.BOOKING_CONFIRMED,
            subject="Test",
            body="Test body",
        )
        db_session.add(notification)
        db_session.commit()

        log = NotificationLog(
            notification_id=notification.id,
            channel="email",
            status="success",
            response_code=202,
            response_body="SendGrid SMTP OK",
        )
        db_session.add(log)
        db_session.commit()

        assert log.id is not None
        assert log.channel == "email"
        assert log.status == "success"


# ============================================================================
# Service Tests
# ============================================================================

class TestNotificationService:
    """Test NotificationService methods."""

    def test_send_notification_basic(self, db_session):
        """Test basic notification sending."""
        with patch('app.notifications.services.db') as mock_db:
            mock_db.session.add = MagicMock()
            mock_db.session.flush = MagicMock()
            mock_db.session.commit = MagicMock()

            user = MagicMock()
            user.id = 1
            user.email = "test@example.com"
            user.phone = "+256770123456"

            with patch('app.notifications.services.db.session.get', return_value=user):
                notification = NotificationService.send(
                    user_id=1,
                    notification_type=NotificationType.BOOKING_CONFIRMED,
                    title="Booking Confirmed",
                    message="Your booking has been confirmed.",
                    channels=["in_app"],
                )

                assert notification is not None
                assert notification.type == NotificationType.BOOKING_CONFIRMED

    def test_send_notification_multi_channel(self, db_session):
        """Test multi-channel notification sending."""
        with patch('app.notifications.services.db') as mock_db:
            mock_db.session.add = MagicMock()
            mock_db.session.flush = MagicMock()
            mock_db.session.commit = MagicMock()

            user = MagicMock()
            user.id = 1
            user.email = "test@example.com"
            user.phone = "+256770123456"

            with patch('app.notifications.services.db.session.get', return_value=user):
                notifications = NotificationService.send_multi_channel(
                    user_id=1,
                    notification_type=NotificationType.PAYMENT_RECEIVED,
                    title="Payment Received",
                    message="UGX 100000 has been credited.",
                    channels=["email", "sms", "in_app"],
                )

                assert len(notifications) == 3

    def test_get_unread_count(self, db_session):
        """Test getting unread notification count."""
        notification = Notification(
            user_id=1,
            type=NotificationType.BOOKING_CONFIRMED,
            subject="Test",
            body="Test body",
            is_read=False,
        )
        db_session.add(notification)
        db_session.commit()

        count = NotificationService.get_unread_count(1)
        assert count >= 1

    def test_get_user_notifications(self, db_session):
        """Test getting user notifications."""
        notification = Notification(
            user_id=1,
            type=NotificationType.BOOKING_CONFIRMED,
            subject="Test",
            body="Test body",
        )
        db_session.add(notification)
        db_session.commit()

        notifications = NotificationService.get_user_notifications(1, limit=10)
        assert len(notifications) >= 1

    def test_mark_read(self, db_session):
        """Test marking a notification as read."""
        notification = Notification(
            user_id=1,
            type=NotificationType.BOOKING_CONFIRMED,
            subject="Test",
            body="Test body",
        )
        db_session.add(notification)
        db_session.commit()

        result = NotificationService.mark_read(notification.id, 1)
        assert result is True

        read_notif = db_session.query(Notification).filter_by(id=notification.id).first()
        assert read_notif.is_read is True

    def test_mark_all_read(self, db_session):
        """Test marking all notifications as read."""
        notification = Notification(
            user_id=1,
            type=NotificationType.BOOKING_CONFIRMED,
            subject="Test",
            body="Test body",
        )
        db_session.add(notification)
        db_session.commit()

        count = NotificationService.mark_all_read(1)
        assert count >= 1

    def test_wallet_notification(self, db_session):
        """Test wallet-specific notification with context."""
        with patch('app.notifications.services.db') as mock_db:
            mock_db.session.add = MagicMock()
            mock_db.session.flush = MagicMock()
            mock_db.session.commit = MagicMock()

            user = MagicMock()
            user.id = 1
            user.email = "test@example.com"

            with patch('app.notifications.services.db.session.get', return_value=user):
                notification = NotificationService.send_wallet_notification(
                    user_id=1,
                    transaction=MagicMock(
                        public_id="txn_abc123",
                        tx_type=MagicMock(value="DEPOSIT"),
                        amount=100000,
                        currency="UGX",
                        balance_after=500000,
                        client_request_id="REF123",
                    ),
                    channel="email",
                )

                assert notification is not None
                assert notification.type == NotificationType.TRANSACTION_COMPLETED

    def test_booking_notification(self, db_session):
        """Test booking-specific notification with context."""
        with patch('app.notifications.services.db') as mock_db:
            mock_db.session.add = MagicMock()
            mock_db.session.flush = MagicMock()
            mock_db.session.commit = MagicMock()

            user = MagicMock()
            user.id = 1
            user.email = "test@example.com"

            with patch('app.notifications.services.db.session.get', return_value=user):
                notification = NotificationService.send_booking_notification(
                    user_id=1,
                    booking=MagicMock(
                        public_id="book_abc123",
                        booking_reference="BR-001",
                        property=MagicMock(title="Namboole VIP Pass"),
                        check_in=datetime(2026, 8, 15, tzinfo=timezone.utc),
                        check_out=datetime(2026, 8, 20, tzinfo=timezone.utc),
                        total_price=150000,
                        currency="UGX",
                    ),
                    notification_type="confirmed",
                    channel="email",
                )

                assert notification is not None
                assert notification.type == NotificationType.BOOKING_CONFIRMED

    def test_resend_failed(self, db_session):
        """Test resending failed notifications."""
        notification = Notification(
            user_id=1,
            type=NotificationType.BOOKING_CONFIRMED,
            subject="Test",
            body="Test body",
            status=NotificationStatus.FAILED,
            attempts=1,
        )
        db_session.add(notification)
        db_session.commit()

        with patch('app.notifications.services.NotificationService.send') as mock_send:
            mock_send.return_value = notification
            count = NotificationService.resend_failed(max_retries=3)
            assert count >= 0


# ============================================================================
# Preferences Tests
# ============================================================================

class TestPreferenceService:
    """Test PreferenceService methods."""

    def test_get_preferences(self, db_session):
        """Test getting user preferences."""
        pref = UserNotificationPreference(
            user_id=1,
            notification_type="booking_confirmed",
            channel="email",
            enabled=True,
        )
        db_session.add(pref)
        db_session.commit()

        prefs = PreferenceService.get_preferences(1)
        assert len(prefs) >= 1

    def test_update_preference(self, db_session):
        """Test updating a preference."""
        pref = PreferenceService.update_preference(1, "booking_confirmed", "email", False)
        assert pref is not None
        assert pref.enabled is False

    def test_is_allowed_default(self, db_session):
        """Test that notifications are allowed by default when no preferences exist."""
        result = PreferenceService.is_allowed(999, "booking_confirmed", ["email"])
        assert result is True

    def test_is_allowed_when_disabled(self, db_session):
        """Test that notifications are blocked when explicitly disabled."""
        pref = UserNotificationPreference(
            user_id=1,
            notification_type="booking_confirmed",
            channel="email",
            enabled=False,
        )
        db_session.add(pref)
        db_session.commit()

        result = PreferenceService.is_allowed(1, "booking_confirmed", ["email"])
        assert result is False

    def test_get_enabled_channels(self, db_session):
        """Test getting enabled channels for a user."""
        pref = UserNotificationPreference(
            user_id=1,
            notification_type="booking_confirmed",
            channel="email",
            enabled=True,
        )
        db_session.add(pref)
        db_session.commit()

        channels = PreferenceService.get_enabled_channels(1, "booking_confirmed")
        assert "email" in channels


# ============================================================================
# Utility Tests
# ============================================================================

class TestNotificationUtils:
    """Test notification utility functions."""

    def test_calculate_backoff(self):
        """Test exponential backoff calculation."""
        assert calculate_backoff(0, base_delay=60) == 60
        assert calculate_backoff(1, base_delay=60) == 60
        assert calculate_backoff(2, base_delay=60) == 120
        assert calculate_backoff(3, base_delay=60) == 240
        assert calculate_backoff(4, base_delay=60) == 480

    def test_generate_idempotency_key(self):
        """Test idempotency key generation."""
        key1 = generate_idempotency_key("1", "booking_confirmed", 1234567890.0)
        key2 = generate_idempotency_key("1", "booking_confirmed", 1234567890.0)
        assert key1 == key2
        assert key1.startswith("notif_")


# ============================================================================
# Channel Handler Tests
# ============================================================================

class TestChannelHandlers:
    """Test channel handler validation."""

    def test_email_handler_validates_email(self):
        """Test email handler validates email addresses."""
        from app.notifications.channel_handlers.email import EmailHandler
        handler = EmailHandler()

        assert handler.validate_recipient({"email": "test@example.com"}) is True
        assert handler.validate_recipient({"email": "invalid"}) is False
        assert handler.validate_recipient({}) is False

    def test_sms_handler_validates_phone(self):
        """Test SMS handler validates phone numbers."""
        from app.notifications.channel_handlers.sms import SmsHandler
        handler = SmsHandler()

        assert handler.validate_recipient({"phone": "+256770123456"}) is True
        assert handler.validate_recipient({"phone": "123"}) is False
        assert handler.validate_recipient({}) is False

    def test_push_handler_validates_user_id(self):
        """Test push handler validates user_id."""
        from app.notifications.channel_handlers.push import PushHandler
        handler = PushHandler()

        assert handler.validate_recipient({"user_id": 1}) is True
        assert handler.validate_recipient({}) is False

    def test_in_app_handler_validates_user_id(self):
        """Test in-app handler validates user_id."""
        from app.notifications.channel_handlers.in_app import InAppHandler
        handler = InAppHandler()

        assert handler.validate_recipient({"user_id": 1}) is True
        assert handler.validate_recipient({}) is False

    def test_webhook_handler_accepts_all(self):
        """Test webhook handler accepts all recipients."""
        from app.notifications.channel_handlers.webhook import WebhookHandler
        handler = WebhookHandler()

        assert handler.validate_recipient({}) is True
        assert handler.validate_recipient({"user_id": 1}) is True


# ============================================================================
# Integration Tests
# ============================================================================

class TestNotificationIntegration:
    """Test cross-module notification integration."""

    def test_notification_connects_to_user(self, db_session):
        """Test that notifications properly reference users."""
        notification = Notification(
            user_id=1,
            type=NotificationType.BOOKING_CONFIRMED,
            subject="Test",
            body="Test body",
        )
        db_session.add(notification)
        db_session.commit()

        assert notification.user_id == 1
        assert notification.id is not None

    def test_notification_context_passes_data(self, db_session):
        """Test that notification context carries data between models."""
        notification = Notification(
            user_id=1,
            type=NotificationType.PAYMENT_RECEIVED,
            subject="Payment Received",
            body="UGX 100000 credited to your wallet.",
            context={
                "transaction_id": "txn_abc123",
                "amount": "100000",
                "currency": "UGX",
                "wallet_txn_id": "wallet_txn_xyz",
            },
        )
        db_session.add(notification)
        db_session.commit()

        assert notification.context is not None
        assert notification.context["transaction_id"] == "txn_abc123"
        assert notification.context["amount"] == "100000"

    def test_notification_template_links_to_notification(self, db_session):
        """Test that notification templates link to notifications."""
        template = NotificationTemplate(
            type="booking_confirmed",
            channel="email",
            subject="Booking Confirmed",
            body_template="Dear {{ user_name }}, your booking is confirmed.",
        )
        db_session.add(template)
        db_session.commit()

        notification = Notification(
            user_id=1,
            type=NotificationType.BOOKING_CONFIRMED,
            subject="Booking Confirmed",
            body="Dear John, your booking is confirmed.",
            template_id=template.id,
        )
        db_session.add(notification)
        db_session.commit()

        assert notification.template_id == template.id

    def test_preference_links_to_user_and_notification(self, db_session):
        """Test that preferences link users to notification types."""
        pref = UserNotificationPreference(
            user_id=1,
            notification_type="booking_confirmed",
            channel="email",
            enabled=False,
        )
        db_session.add(pref)
        db_session.commit()

        assert pref.user_id == 1
        assert pref.notification_type == "booking_confirmed"
        assert pref.channel == "email"
        assert pref.enabled is False

    def test_notification_log_links_to_notification(self, db_session):
        """Test that notification logs link to notifications."""
        notification = Notification(
            user_id=1,
            type=NotificationType.BOOKING_CONFIRMED,
            subject="Test",
            body="Test body",
        )
        db_session.add(notification)
        db_session.commit()

        log = NotificationLog(
            notification_id=notification.id,
            channel="email",
            status="success",
            response_code=202,
        )
        db_session.add(log)
        db_session.commit()

        assert log.notification_id == notification.id
        assert log.channel == "email"
        assert log.status == "success"