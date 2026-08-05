# AFCON360 Unified Notification System

## Overview

The AFCON360 Notification System is a robust, multi-channel notification platform integrated into the AFCON360 management ecosystem. It provides centralized notification delivery across all modules including wallet, accommodation, transport, events, identity, and KYC.

## Architecture

```
app/notifications/
├── __init__.py                    # Blueprint registration & service exports
├── models.py                      # SQLAlchemy models (Notification, Template, Preferences, Log)
├── services.py                    # Centralized NotificationService with cross-module integration
├── tasks.py                       # Celery async workers & beat scheduler
├── preferences.py                 # User notification preference management
├── template_loader.py             # Jinja2 template loader for email/SMS/push
├── utils.py                       # Rate limiting, exponential backoff, idempotency
├── channel_handlers/              # Pluggable handlers per channel
│   ├── __init__.py                # BaseChannelHandler ABC
│   ├── email.py                   # Email (SendGrid/SMTP)
│   ├── sms.py                     # SMS (Twilio/Africa's Talking)
│   ├── push.py                    # Push (Firebase Cloud Messaging)
│   ├── in_app.py                  # In-app persistent inbox
│   └── webhook.py                 # HTTP JSON callback webhooks
├── templates/                     # Email HTML, SMS txt, Push JSON templates
│   ├── email/
│   │   ├── booking_confirmation.html
│   │   └── payment_receipt.html
│   ├── sms/
│   │   └── booking_confirmation.txt
│   └── push/
│       └── booking_confirmation.json
├── tests/                         # Test suite
│   ├── __init__.py
│   ├── test_models.py
│   ├── test_services.py
│   ├── test_channel_handlers.py
│   └── test_integration.py
└── README.md                      # This file
```

## Key Components

### Models (`models.py`)
- **`Notification`** — Central notification record with BIGINT internal ID, UUID external ID, type, channel, status, priority, scheduling, retry tracking, and deep links
- **`NotificationType`** — Enum covering all notification types across accommodation, auth, transport, events, wallet, and system domains
- **`NotificationChannel`** — Enum for delivery channels: in_app, email, sms, push, webhook
- **`NotificationStatus`** — Enum for lifecycle: pending, sent, delivered, failed, read, cancelled
- **`NotificationTemplate`** — Reusable templates per type and channel with Jinja2 rendering
- **`UserNotificationPreference`** — Per-user, per-type, per-channel opt-in/opt-out preferences
- **`NotificationLog`** — Audit log for each delivery attempt with response codes and bodies

### Service (`services.py`)
- **`NotificationService.send()`** — Core dispatch method with user preference checking, channel validation, and delivery tracking
- **`NotificationService.send_multi_channel()`** — Simultaneous multi-channel delivery
- **`NotificationService.send_wallet_notification()`** — Wallet transaction notifications with full context
- **`NotificationService.send_booking_notification()`** — Accommodation booking notifications
- **`NotificationService.send_transport_notification()`** — Transport booking notifications
- **`NotificationService.send_event_notification()`** — Event registration notifications
- **`NotificationService.send_review_notification()`** — Review received notifications
- **`NotificationService.send_kyc_notification()`** — KYC verification notifications
- **`NotificationService.send_organisation_notification()`** — Organisation update notifications
- **`NotificationService.resend_failed()`** — Retry failed notifications with exponential backoff

### Tasks (`tasks.py`)
- **`send_notification_task`** — Async single notification delivery with retry logic
- **`send_bulk_task`** — Concurrent bulk notification processing
- **`schedule_reminders_task`** — Celery Beat: dispatches scheduled notifications
- **`cleanup_old_notifications_task`** — Celery Beat: archives old logs and soft-deletes stale read notifications
- **`resend_failed_task`** — Celery Beat: resends failed notifications

### Channel Handlers (`channel_handlers/`)
Each handler implements `BaseChannelHandler` with `validate_recipient()` and `deliver()` methods:
- **EmailHandler** — Validates email format, delivers via SendGrid/SMTP
- **SmsHandler** — Validates phone length, delivers via Twilio/Africa's Talking
- **PushHandler** — Validates user_id, delivers via Firebase Cloud Messaging
- **InAppHandler** — Validates user_id, stores in persistent inbox
- **WebhookHandler** — Accepts all recipients, delivers HTTP JSON payload

### Preferences (`preferences.py`)
- **`PreferenceService.get_preferences()`** — Get all preferences for a user
- **`PreferenceService.update_preference()`** — Create or update a preference
- **`PreferenceService.is_allowed()`** — Check if notifications are allowed for a type/channel
- **`PreferenceService.get_enabled_channels()`** — Get enabled channels for a notification type
- **`PreferenceService.set_all_enabled()`** — Bulk enable/disable all preferences

## Quick Start

### Celery Workers

To start the Celery async worker:
```bash
celery -A app.celery_app worker --loglevel=info
```

To start Celery Beat scheduler for scheduled notifications & retry queue:
```bash
celery -A app.celery_app beat --loglevel=info
```

### Triggering Notifications in Code

```python
from app.notifications.services import NotificationService
from app.notifications.models import NotificationType

# Single notification dispatch
NotificationService.send(
    user_id=user.id,
    notification_type=NotificationType.BOOKING_CONFIRMED,
    title="Booking Confirmed",
    message="Your reservation has been confirmed.",
    data={'booking_reference': 'BR-001', 'total_ugx': 150000},
    channels=['email', 'in_app'],
    link="/accommodation/bookings/book_abc123",
    priority='high',
)

# Multi-channel dispatch (Email + SMS + In-App)
NotificationService.send_multi_channel(
    user_id=user.id,
    notification_type=NotificationType.PAYMENT_RECEIVED,
    title="Payment Received",
    message="UGX 100000 has been credited to your wallet.",
    data={'amount': 100000, 'currency': 'UGX', 'tx_ref': 'TX999'},
    channels=['email', 'sms', 'in_app'],
    priority='high',
)

# Wallet notification with full transaction context
NotificationService.send_wallet_notification(
    user_id=user.id,
    transaction=tx,
    channel='email',
)

# Booking notification with full context
NotificationService.send_booking_notification(
    user_id=user.id,
    booking=booking,
    notification_type='confirmed',
    channel='email',
)
```

### User Preferences

```python
from app.notifications.preferences import PreferenceService

# Disable email notifications for booking confirmations
PreferenceService.update_preference(
    user_id=user.id,
    notification_type='booking_confirmed',
    channel='email',
    enabled=False,
)

# Check if user allows a notification
allowed = PreferenceService.is_allowed(
    user_id=user.id,
    notification_type='booking_confirmed',
    channels=['email', 'sms'],
)

# Get all enabled channels for a notification type
channels = PreferenceService.get_enabled_channels(
    user_id=user.id,
    notification_type='booking_confirmed',
)
```

### Reading Notifications

```python
from app.notifications.services import NotificationService

# Get unread count
unread = NotificationService.get_unread_count(user_id=user.id)

# Get user notifications
notifications = NotificationService.get_user_notifications(
    user_id=user.id,
    limit=20,
    unread_only=True,
)

# Mark as read
NotificationService.mark_read(notification_id=1, user_id=user.id)

# Mark all as read
count = NotificationService.mark_all_read(user_id=user.id)
```

## Cross-Module Integration

The notification system integrates with all AFCON360 modules:

| Module | Integration Point | Notification Type |
|--------|------------------|-------------------|
| **Wallet** | `NotificationService.send_wallet_notification()` | `TRANSACTION_COMPLETED`, `DEPOSIT_CONFIRMED`, `WITHDRAWAL_COMPLETED` |
| **Accommodation** | `NotificationService.send_booking_notification()` | `BOOKING_CONFIRMED`, `BOOKING_CANCELLED` |
| **Transport** | `NotificationService.send_transport_notification()` | `BOOKING_CONFIRMED`, `DRIVER_ASSIGNED`, `BOOKING_UPDATE` |
| **Events** | `NotificationService.send_event_notification()` | `EVENT_REGISTERED`, `EVENT_REMINDER` |
| **KYC** | `NotificationService.send_kyc_notification()` | `VERIFICATION_EMAIL` |
| **Accommodation Reviews** | `NotificationService.send_review_notification()` | `REVIEW_RECEIVED` |
| **Identity/Organisation** | `NotificationService.send_organisation_notification()` | `SYSTEM_ALERT` |

## Backward Compatibility

Existing imports continue to work via re-exports:
- `from app.models.notification import Notification, NotificationType, NotificationChannel` → re-exports from `app.notifications.models`
- `from app.services.notification_service import NotificationService` → re-exports from `app.notifications.services`

## API Endpoints

The notification blueprint (`notifications_api`, url prefix `/api/notifications`) exposes:

### Inbox & Preferences
- `GET /api/notifications` — List user notifications (filters: `unread_only`, `type`, `limit`, `offset`)
- `GET /api/notifications/unread-count` — Unread badge count
- `GET /api/notifications/<id>` — Notification detail
- `PATCH /api/notifications/<id>/read` — Mark read
- `DELETE /api/notifications/<id>` — Soft-delete (hide from inbox)
- `POST /api/notifications/read-all` — Mark all read
- `GET /api/notifications/preferences` — Get user preferences
- `PUT/POST /api/notifications/preferences` — Bulk update preferences
- `POST /api/notifications/preferences/channel` — Toggle an entire channel on/off

### Internal Messaging
- `GET /api/notifications/messages` — List inbox + sent
- `POST /api/notifications/messages` — Send internal message (body: `recipient_public_id`, `subject`, `body`, `message_type`)
- `POST /api/notifications/messages/<id>/read` — Mark message read
- `POST /api/notifications/messages/<id>/archive` — Archive message

### Admin Communication Settings (owner/super_admin/admin)
- `GET /api/notifications/admin/settings` — List providers + aggregators (secrets redacted)
- `POST/PUT /api/notifications/admin/settings` — Upsert provider setting (email/sms/push/webhook)
- `POST/PUT /api/notifications/admin/aggregators` — Register external aggregator (Twilio, SendGrid, FCM, WhatsApp, SAP)
- `POST /api/notifications/admin/settings/<id>/toggle` — Enable/disable a channel/provider
- `POST /api/notifications/admin/aggregators/<id>/test` — Send a test message via an aggregator
- `GET /api/notifications/admin/dead-letter` — Inspect failed (dead-letter) notifications
- `POST /api/notifications/admin/resend-failed` — Retry all failed notifications
- `POST /api/notifications/admin/broadcast` — Platform announcement to all/role-filtered users

### Dashboard Integration
- Context processor `inject_notification_context` injects `notif_badges` (unread notifications + messages) and `recent_notifications` into every template.

## Lifecycle Coverage (Signals)

Decoupled blinker signals (`app/notifications/signals.py`) fire from domain services; listeners (`app/notifications/listeners.py`) dispatch notifications. Covers the full user journey:

| Lifecycle Event | Signal | Notification |
|-----------------|--------|--------------|
| Account created | `user_signed_up` | Signup welcome (user) + admin alert |
| KYC submitted / approved / rejected | `kyc_*` | KYC status (user) + admin alert |
| Wallet created | `wallet_created` | Wallet-ready notice |
| Wallet transaction | `wallet_transaction` | Multi-channel payment receipt + admin alert (large tx) |
| Property submitted / approved / rejected / suspended | `property_*` | Host notice + admin alert |
| Booking confirmed / cancelled / checked-in / checked-out | `booking_*` | Guest + host notifications |
| Event registered | `event_registered` (reuses events module signal) | Event confirmation + QR reference |
| Transport booking created / driver assigned | `transport_*` | Customer + driver notifications |
| Internal message | `message_sent` | In-app inbox + message notification |

Direct hooks also fire from `auth/services.register_user`, `wallet_service.create_wallet`,
`accommodation/routes` moderation actions, `kyc/services.approve_kyc/reject_kyc`,
`accommodation/services.booking_service.confirm_booking`, and
`transport/services.booking_service.create_booking`.

## Aggregators & Future-Proofing

`NotificationAggregator` registers external gateways with priority ordering. Supported `provider_type`:
- `twilio` (SMS + WhatsApp)
- `sendgrid` / `smtp` / `mailgun` / `ses` (email)
- `fcm` / `apns` (push)
- `generic` / `sap` (webhook / SAP Event Mesh — future integration)

Dispatch logic in `app/notifications/integrations/__init__.py` routes each channel to the correct
client (Twilio SDK, Flask-Mail, FCM, requests webhook). Secrets stored encrypted at rest via
`CommunicationSettingsService._encrypt_config` (uses `app.utils.crypto`).

## Backward Compatibility

Existing imports continue to work via re-exports:
- `from app.models.notification import Notification, ...` → re-exports from `app.notifications.models` (now includes `CommunicationSettings`, `NotificationAggregator`, `Message`)
- `from app.services.notification_service import NotificationService` → re-exports from `app.notifications.services`

## Testing

Notification tests live in the **main test suite** (`tests/notifications/`) so they are captured by
the shared `tests/conftest.py` fixtures (`app`, `client`, `db_session`). Run them with:

```bash
# Requires a populated test database first:
python scripts/setup_test_db_schema.py

# Run notification tests
pytest tests/notifications/ -v

# Run the whole suite
pytest tests/
```

## Templates

Notification email/SMS/push templates live in the **main templates folder** at
`templates/notifications/` (subfolders `email/`, `sms/`, `push/`). `template_loader.py`
resolves this path automatically; no per-module templates directory is used.

## Migration Notes

New tables required:
- `notification_templates` — Reusable notification templates
- `user_notification_preferences` — Per-user notification preferences
- `notification_logs` — Delivery attempt audit log
- `communication_settings` — Provider/channel configuration (email/sms/push/webhook)
- `notification_aggregators` — External messaging gateways (Twilio, SendGrid, FCM, SAP, etc.)
- `messages` — Internal bidirectional messaging

Proposed migration commands (run manually — never auto-migrated):
```bash
flask db migrate -m "add notification templates, preferences, communication settings, aggregators, messages"
flask db upgrade
```