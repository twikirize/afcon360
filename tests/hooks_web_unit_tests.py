# tests/run_hooks_tests.py
import sys
import os

# Add the project root to path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__) + '/..'))

from types import SimpleNamespace
from unittest.mock import MagicMock, patch
import logging

# Disable logging during tests
logging.disable(logging.CRITICAL)


def test_alert_owner_dead_letter():
    """Test that _alert_owner_dead_letter sends SMS, email, and increments Redis."""
    from app.tasks.webhook_processor import _alert_owner_dead_letter

    # Prepare a fake owner user object
    fake_owner = SimpleNamespace(
        id=123,
        phone="+256700000000",
        phone_verified=True,
        email="owner@example.com",
        email_verified=True,
    )

    # Mock the send_sms function
    send_sms_mock = MagicMock()

    # Mock the NotificationService.send_email method
    send_email_mock = MagicMock()

    # Mock Redis incr
    redis_incr_mock = MagicMock()

    # Setup the query chain to return our fake_owner
    with patch('app.tasks.webhook_processor.MAX_ATTEMPTS', 3), \
            patch('app.extensions.redis_client.incr', redis_incr_mock), \
            patch('app.services.sms_service.send_sms', send_sms_mock), \
            patch('app.transport.services.notification_service.NotificationService.send_email', send_email_mock):
        # Create fake event
        event = SimpleNamespace(
            id=99,
            provider="flutterwave",
            event_type="charge.completed"
        )

        # Need to mock the database query to return our owner
        with patch('app.tasks.webhook_processor.db.session.query') as mock_query:
            mock_query.return_value.join.return_value.filter.return_value.order_by.return_value.first.return_value = fake_owner

            # Call the function
            _alert_owner_dead_letter(event)

    # Verify the calls
    assert send_sms_mock.called, "send_sms should be called"
    assert send_email_mock.called, "send_email should be called"
    assert redis_incr_mock.called, "redis.incr should be called"

    # Verify the correct arguments
    send_sms_mock.assert_called_once_with(
        "+256700000000",
        "AFCON360 ALERT: Webhook event 99 (flutterwave/charge.completed) has failed 3 times and is now in dead_letter. Manual review required at /admin/webhooks/failed"
    )

    send_email_mock.assert_called_once()

    print("✅ test_alert_owner_dead_letter passed!")


def test_alert_owner_dead_letter_sms_only():
    """Test when user only has phone verified."""
    from app.tasks.webhook_processor import _alert_owner_dead_letter

    fake_owner = SimpleNamespace(
        id=123,
        phone="+256700000000",
        phone_verified=True,
        email="owner@example.com",
        email_verified=False,
    )

    send_sms_mock = MagicMock()
    send_email_mock = MagicMock()
    redis_incr_mock = MagicMock()

    with patch('app.tasks.webhook_processor.MAX_ATTEMPTS', 3), \
            patch('app.extensions.redis_client.incr', redis_incr_mock), \
            patch('app.services.sms_service.send_sms', send_sms_mock), \
            patch('app.transport.services.notification_service.NotificationService.send_email', send_email_mock):
        event = SimpleNamespace(id=99, provider="flutterwave", event_type="charge.completed")

        with patch('app.tasks.webhook_processor.db.session.query') as mock_query:
            mock_query.return_value.join.return_value.filter.return_value.order_by.return_value.first.return_value = fake_owner
            _alert_owner_dead_letter(event)

    assert send_sms_mock.called, "SMS should be sent when phone is verified"
    assert not send_email_mock.called, "Email should not be sent when email not verified"
    assert redis_incr_mock.called, "Redis should still increment"
    print("✅ test_alert_owner_dead_letter_sms_only passed!")


def test_alert_owner_dead_letter_email_only():
    """Test when user only has email verified."""
    from app.tasks.webhook_processor import _alert_owner_dead_letter

    fake_owner = SimpleNamespace(
        id=123,
        phone="+256700000000",
        phone_verified=False,
        email="owner@example.com",
        email_verified=True,
    )

    send_sms_mock = MagicMock()
    send_email_mock = MagicMock()
    redis_incr_mock = MagicMock()

    with patch('app.tasks.webhook_processor.MAX_ATTEMPTS', 3), \
            patch('app.extensions.redis_client.incr', redis_incr_mock), \
            patch('app.services.sms_service.send_sms', send_sms_mock), \
            patch('app.transport.services.notification_service.NotificationService.send_email', send_email_mock):
        event = SimpleNamespace(id=99, provider="flutterwave", event_type="charge.completed")

        with patch('app.tasks.webhook_processor.db.session.query') as mock_query:
            mock_query.return_value.join.return_value.filter.return_value.order_by.return_value.first.return_value = fake_owner
            _alert_owner_dead_letter(event)

    assert not send_sms_mock.called, "SMS should not be sent when phone not verified"
    assert send_email_mock.called, "Email should be sent when email is verified"
    assert redis_incr_mock.called, "Redis should still increment"
    print("✅ test_alert_owner_dead_letter_email_only passed!")


def test_alert_owner_dead_letter_no_owner():
    """Test when no owner/super_admin user exists."""
    from app.tasks.webhook_processor import _alert_owner_dead_letter

    send_sms_mock = MagicMock()
    send_email_mock = MagicMock()
    redis_incr_mock = MagicMock()

    with patch('app.tasks.webhook_processor.MAX_ATTEMPTS', 3), \
            patch('app.extensions.redis_client.incr', redis_incr_mock), \
            patch('app.services.sms_service.send_sms', send_sms_mock), \
            patch('app.transport.services.notification_service.NotificationService.send_email', send_email_mock):
        event = SimpleNamespace(id=99, provider="flutterwave", event_type="charge.completed")

        with patch('app.tasks.webhook_processor.db.session.query') as mock_query:
            mock_query.return_value.join.return_value.filter.return_value.order_by.return_value.first.return_value = None
            _alert_owner_dead_letter(event)

    assert not send_sms_mock.called, "SMS should not be sent when no owner"
    assert not send_email_mock.called, "Email should not be sent when no owner"
    assert redis_incr_mock.called, "Redis should still increment"
    print("✅ test_alert_owner_dead_letter_no_owner passed!")


def test_alert_owner_dead_letter_fallback_query():
    """Test the fallback query path when DB session fails."""
    from app.tasks.webhook_processor import _alert_owner_dead_letter

    fake_owner = SimpleNamespace(
        id=123,
        phone="+256700000000",
        phone_verified=True,
        email="owner@example.com",
        email_verified=True,
        is_super_admin=lambda: True
    )

    send_sms_mock = MagicMock()
    send_email_mock = MagicMock()
    redis_incr_mock = MagicMock()

    with patch('app.tasks.webhook_processor.MAX_ATTEMPTS', 3), \
            patch('app.extensions.redis_client.incr', redis_incr_mock), \
            patch('app.services.sms_service.send_sms', send_sms_mock), \
            patch('app.transport.services.notification_service.NotificationService.send_email', send_email_mock):
        event = SimpleNamespace(id=99, provider="flutterwave", event_type="charge.completed")

        # Make the DB session query fail
        with patch('app.tasks.webhook_processor.db.session.query', side_effect=Exception("DB error")):
            # Mock the fallback User.query.all()
            with patch('app.identity.models.user.User.query.all', return_value=[fake_owner]):
                _alert_owner_dead_letter(event)

    assert send_sms_mock.called, "SMS should be sent via fallback query"
    assert send_email_mock.called, "Email should be sent via fallback query"
    assert redis_incr_mock.called, "Redis should still increment"
    print("✅ test_alert_owner_dead_letter_fallback_query passed!")


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print(" RUNNING UNIT TESTS FOR _alert_owner_dead_letter ".center(60, "="))
    print("=" * 60 + "\n")

    # Create the missing send_sms function if needed
    import app.services.sms_service

    if not hasattr(app.services.sms_service, 'send_sms'):
        print("⚠️  Warning: send_sms function not found in sms_service.py")
        print("   The test will mock it, but the production code will fail!")
        print("   Consider adding this function to sms_service.py:\n")
        print("   def send_sms(phone_number, message):")
        print("       service = SMSService()")
        print("       return service._provider_instance.send_sms(phone_number, message)\n")

    test_alert_owner_dead_letter()
    test_alert_owner_dead_letter_sms_only()
    test_alert_owner_dead_letter_email_only()
    test_alert_owner_dead_letter_no_owner()
    test_alert_owner_dead_letter_fallback_query()

    print("\n" + "=" * 60)
    print(" ALL TESTS PASSED! ".center(60, "="))
    print("=" * 60)