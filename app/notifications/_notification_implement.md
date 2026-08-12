n a large enterprise system such as a global booking, banking, airline, or marketplace platform, notifications are usually not implemented as send_email() calls scattered throughout the application.

They are normally treated as a platform-level event and communication system sitting between business domains and delivery channels.

For something like AFCON360, the architecture you are moving toward should eventually look conceptually like this:

                    ┌─────────────────────────────┐
                    │        BUSINESS DOMAINS     │
                    │                             │
                    │ Auth / Users                 │
                    │ KYC                         │
                    │ Accommodation               │
                    │ Bookings                    │
                    │ Payments / Wallet           │
                    │ Transport                   │
                    │ Tourism                     │
                    │ Admin                       │
                    └──────────────┬──────────────┘
                                   │
                                   │ DOMAIN EVENTS
                                   ▼
                    ┌─────────────────────────────┐
                    │       EVENT BUS / BROKER     │
                    │                             │
                    │ Redis Streams / RabbitMQ    │
                    │ Kafka at very large scale   │
                    └──────────────┬──────────────┘
                                   │
                 ┌─────────────────┼──────────────────┐
                 │                 │                  │
                 ▼                 ▼                  ▼
        ┌────────────────┐ ┌────────────────┐ ┌────────────────┐
        │ Notification   │ │ Audit / Event  │ │ Other Consumers│
        │ Orchestrator   │ │ Ledger         │ │ Analytics      │
        └───────┬────────┘ └────────────────┘ └────────────────┘
                │
                ▼
       ┌───────────────────────┐
       │ Notification Policy    │
       │ & Preference Engine    │
       └───────────┬───────────┘
                   │
          ┌────────┼─────────┐
          ▼        ▼         ▼
       In-App    Email      SMS
          │        │         │
          ▼        ▼         ▼
       Push     WhatsApp   Provider

The important insight is:

The business system produces facts. The notification system decides whether, when, how, and through which channel those facts should be communicated.

1. The key distinction: events ≠ notifications

This is one of the most important architectural concepts for your AFCON360 system.

Suppose a user registers.

The authentication service shouldn't necessarily do this:

create_user()

send_email()

send_sms()

create_notification()

send_push()

Instead:

user = create_user()

publish_event(
    "user.registered",
    user_id=user.id
)

The registration service is finished.

The event travels through the platform.

Then different systems react:

user.registered
       │
       ├──► Notification Service
       │       ├── email
       │       ├── in-app
       │       └── push
       │
       ├──► Audit Service
       │
       ├──► Analytics
       │
       ├──► Welcome/Campaign Service
       │
       └──► Risk/Fraud Service

This gives you loose coupling.

2. There are actually several kinds of "notifications"

This is where enterprise systems become more sophisticated.

You mentioned:

internal information exchange and outbound

Exactly.

I would divide AFCON360's communication architecture into four layers.

Layer A — Domain Events

Internal facts about what happened.

Examples:

user.registered
user.email_verified
user.account_created

kyc.submitted
kyc.review_started
kyc.approved
kyc.rejected

payment.initiated
payment.pending
payment.successful
payment.failed
payment.refunded

booking.created
booking.confirmed
booking.cancelled

hotel.approved
property.published

These are not notifications.

They are facts.

3. Layer B — Internal platform events

These are used for communication between AFCON360 services.

For example:

payment.successful
        │
        ├──► Wallet
        ├──► Booking
        ├──► Accounting
        ├──► Fraud
        ├──► Loyalty
        ├──► Notification
        └──► Audit

The payment service doesn't need to know all those consumers.

It simply says:

A payment successfully happened.

This is the beginning of event-driven architecture.

4. Layer C — User notifications

Now the Notification Service consumes those events.

For example:

payment.successful
        │
        ▼
Notification Orchestrator
        │
        ├── Is notification required?
        │
        ├── Who receives it?
        │
        ├── What template?
        │
        ├── Which language?
        │
        ├── Which channels?
        │
        ├── User preferences?
        │
        └── Priority?

It could produce:

IN-APP
"Payment of UGX 150,000 was successful."

EMAIL
"Your payment has been confirmed."

PUSH
"Payment successful."

SMS
"AFCON360: Payment of UGX 150,000 successful."

Notice that the payment service never had to implement those four channels.

5. Layer D — External integrations

Then you have the actual delivery infrastructure.

For example:

Notification Service
       │
       ├── Email Adapter
       │      └── SendGrid / Amazon SES / Brevo / etc.
       │
       ├── SMS Adapter
       │      └── Africa's Talking / Twilio / etc.
       │
       ├── Push Adapter
       │      └── Firebase
       │
       ├── WhatsApp Adapter
       │
       └── In-App Adapter

This is extremely important.

You don't want:

payment_service.py
    -> Twilio

You want:

Payment
   ↓
Event
   ↓
Notification
   ↓
SMS adapter
   ↓
SMS provider

That separation becomes extremely valuable as AFCON360 grows.

6. Now look at registration

Imagine:

POST /register

The Auth service performs:

Validate input
      ↓
Create user
      ↓
Create account
      ↓
Publish user.registered

Then:

                user.registered
                       │
          ┌────────────┼─────────────┐
          ▼            ▼             ▼
     Notification    Audit       Analytics
          │
          ▼
    Notification
     Orchestrator
          │
       ┌──┴────┐
       ▼       ▼
     Email    In-App

The user gets:

Welcome to AFCON360.

Meanwhile the audit system records:

USER_REGISTERED

And analytics records:

registration_completed

All from one event.

7. KYC becomes even more interesting

Suppose:

User submits KYC

The KYC service publishes:

kyc.submitted

Then:

kyc.submitted
      │
      ├──► Audit
      │
      ├──► Compliance
      │
      ├──► Risk Engine
      │
      ├──► KYC Processing
      │
      └──► Notification

Later:

kyc.approved

Notification system:

kyc.approved
      │
      ▼
Policy Engine
      │
      ├── In-app ✓
      ├── Email ✓
      ├── Push ✓
      └── SMS ?

Maybe SMS isn't necessary.

That's a policy decision, not a KYC responsibility.

8. Payments are even more critical

Suppose:

User pays UGX 500,000

You might have:

Payment Initiated
        │
        ▼
Payment Provider
        │
        ▼
Payment Pending
        │
        ▼
Webhook
        │
        ▼
Payment Verified
        │
        ▼
Payment Successful

The important event is:

payment.successful

That event could trigger:

                 payment.successful
                         │
       ┌─────────────────┼─────────────────┐
       │                 │                 │
       ▼                 ▼                 ▼
   Booking           Wallet            Notification
   Service           Service              │
       │                 │                ├── Email
       ▼                 ▼                ├── Push
   Confirmation       Ledger              └── In-App

And separately:

payment.successful
       │
       ├──► Accounting
       ├──► Fraud Detection
       ├──► Reporting
       └──► Audit

That is how you avoid creating a gigantic tightly coupled application.

9. Enterprise systems also distinguish commands from events

This distinction is crucial.

Command

Do this.

Example:

SendPaymentReceipt
Event

This happened.

Example:

payment.successful

So:

Payment Service
      │
      │ EVENT
      ▼
payment.successful
      │
      ▼
Notification Service
      │
      │ COMMAND
      ▼
SendEmail(payment_receipt)

This distinction becomes very useful once you have many services.

10. Notifications should have their own database

At your current stage, you can keep it inside your Flask application.

But conceptually, you should give it its own persistent models.

For example:

notifications
────────────────────────────
id
recipient_id
event_id
notification_type
title
body
priority
status
created_at
scheduled_at
sent_at
read_at

Then:

notification_deliveries
────────────────────────────
id
notification_id
channel
provider
status
attempts
provider_message_id
sent_at
failed_at
error

And:

notification_preferences
────────────────────────────
user_id
notification_type
email_enabled
sms_enabled
push_enabled
in_app_enabled

And importantly:

notification_events
────────────────────────────
event_id
event_type
aggregate_type
aggregate_id
payload
occurred_at
processed_at
11. You also need an audit/event ledger

This is different from notifications.

For example:

AUDIT EVENT

User: 12345
Action: KYC_APPROVED
Actor: compliance_user_77
Timestamp: ...
IP: ...
Metadata: ...

You don't want to infer your audit history from notifications.

Because a notification can fail.

For example:

KYC APPROVED
      │
      ├── Audit: SUCCESS
      │
      └── Notification:
             ├── Email SUCCESS
             ├── Push SUCCESS
             └── SMS FAILED

The KYC approval still happened.

The notification failure shouldn't change that fact.

12. Reliability is where enterprise architecture becomes serious

Imagine:

payment.successful

The notification server crashes.

You cannot lose the event.

Therefore you need durable messaging.

At increasing scales, you might see:

Small
Redis Streams
    ↓
Medium
RabbitMQ
    ↓
Large
Kafka

The technology isn't the important part.

The principle is:

Events must be durable and replayable.

13. The Outbox Pattern

This is particularly relevant to your AFCON360 Flask/PostgreSQL architecture.

Suppose you do:

payment.status = "successful"

publish_event("payment.successful")

What if:

DB COMMIT ✓
Event publish ✗

Now payment succeeded but nobody knows.

Or:

Event publish ✓
DB COMMIT ✗

Now the system announced something that never committed.

The Transactional Outbox Pattern solves this.

You do:

BEGIN TRANSACTION

UPDATE payments
SET status = 'successful'

INSERT INTO outbox_events (
    event_type,
    aggregate_id,
    payload
)

COMMIT

Both succeed or both fail.

Then a worker does:

Outbox
   ↓
Event Publisher
   ↓
Redis/RabbitMQ/Kafka

This is a major enterprise pattern.

14. Then you need retries

Suppose:

Email provider
      ↓
TIMEOUT

You shouldn't immediately mark:

notification = permanently_failed

Instead:

Attempt 1
   ↓
failed
   ↓
wait 10 sec
   ↓
Attempt 2
   ↓
failed
   ↓
wait 30 sec
   ↓
Attempt 3
   ↓
failed
   ↓
dead-letter queue

Something like:

RETRY POLICY

1 → 10 seconds
2 → 30 seconds
3 → 2 minutes
4 → 10 minutes
5 → 1 hour

Eventually:

Dead Letter Queue

for manual inspection/reprocessing.

15. Idempotency is absolutely critical

Suppose a payment event is accidentally delivered twice:

payment.successful
payment.successful

You must not send two receipts or create two bookings.

Therefore every event needs an ID:

event_id = 8f1c...

And consumers record:

processed_events

or use an idempotency key.

Then:

event_id 8f1c
    ↓
already processed?
    ↓
YES
    ↓
ignore

This is one of the things separating robust enterprise systems from fragile ones.

16. Notifications also need priority

Not every notification is equally important.

For example:

Critical
Payment failed
Security alert
Account compromised
KYC rejected
Booking cancelled
High
Payment successful
Booking confirmed
KYC approved
Normal
Welcome message
Reminder
Review request
Low
Marketing
Recommendations
Promotions

So you can have queues:

                    Notification
                         │
          ┌──────────────┼──────────────┐
          ▼              ▼              ▼
       CRITICAL        NORMAL        BULK
          │              │              │
       Worker          Worker         Worker

A marketing campaign should never block a payment failure notification.

17. There is also notification preference management

For example:

User preferences

Security alerts       → Email + SMS + Push
Payments              → Email + Push
Bookings              → Email + Push
Marketing             → Email
Promotions            → OFF

But some notifications should be mandatory.

For example:

Security alert
Payment receipt
Legal/compliance notification

The user may not be allowed to disable certain categories.

Therefore the policy engine needs to understand:

MANDATORY
OPTIONAL
MARKETING
18. Template management should also be centralized

Instead of:

body = f"Hello {user.name}, your booking..."

inside booking code, use templates.

For example:

notification_templates

template:
    booking.confirmed.email.en
    booking.confirmed.sms.en
    booking.confirmed.push.en

Then:

Event
 ↓
Template Resolver
 ↓
Language
 ↓
Channel
 ↓
Rendered message

Eventually:

booking.confirmed
      ↓
English?
      ↓
Email?
      ↓
booking.confirmed.email.en

You can later support:

en
sw
fr

which would be useful for a continental platform.

19. Internal notifications are also important

You mentioned internal information exchange.

Absolutely.

For example:

KYC rejected

User gets:

Your KYC verification requires additional information.

But internally:

KYC_REJECTED
      │
      ├──► Compliance dashboard
      ├──► Risk engine
      ├──► Audit
      └──► Support system

A staff member could receive:

KYC case #3842 requires manual review.

That's not necessarily an outbound notification.

It's an internal operational event.

20. This means AFCON360 should eventually have three major communication planes

I would structure your architecture conceptually as:

                 AFCON360 COMMUNICATION PLATFORM
                              │
          ┌───────────────────┼───────────────────┐
          │                   │                   │
          ▼                   ▼                   ▼
     EVENT PLATFORM      NOTIFICATION        AUDIT/EVENT
                         PLATFORM             LEDGER
          │                   │                   │
          │                   │                   │
          ▼                   ▼                   ▼
   Internal system       User-facing          Compliance/
   communication         communication        history

And then:

EVENT PLATFORM
     │
     ├── Redis Streams
     ├── RabbitMQ
     └── Kafka (future)
NOTIFICATION PLATFORM
     │
     ├── In-App
     ├── Email
     ├── SMS
     ├── Push
     ├── WhatsApp
     └── Webhooks
AUDIT PLATFORM
     │
     ├── Security events
     ├── Financial events
     ├── User actions
     ├── Admin actions
     └── Compliance events
21. And this is where your current notification service should evolve

From what we've been working on with your AFCON360 Unified Notification Service, I would not throw it away.

Instead, I would change its role.

Currently you're thinking of it as something like:

Notification Service
    ├── Email
    ├── SMS
    ├── Push
    └── In-App

That's a good beginning.

But the mature version should become:

                    ┌──────────────────────────┐
                    │       DOMAIN SERVICES    │
                    │                          │
                    │ Auth                     │
                    │ KYC                      │
                    │ Payments                 │
                    │ Booking                  │
                    │ Accommodation            │
                    │ Wallet                   │
                    └────────────┬─────────────┘
                                 │
                                 ▼
                       ┌──────────────────┐
                       │ DOMAIN EVENT API │
                       └────────┬─────────┘
                                │
                                ▼
                       ┌──────────────────┐
                       │ OUTBOX           │
                       │ PostgreSQL       │
                       └────────┬─────────┘
                                │
                                ▼
                       ┌──────────────────┐
                       │ EVENT BROKER     │
                       │ Redis Streams    │
                       └────────┬─────────┘
                                │
                    ┌───────────┴────────────┐
                    ▼                        ▼
          ┌──────────────────┐      ┌─────────────────┐
          │ NOTIFICATION     │      │ AUDIT / EVENT   │
          │ ORCHESTRATOR     │      │ CONSUMER        │
          └────────┬─────────┘      └─────────────────┘
                   │
                   ▼
          ┌──────────────────┐
          │ POLICY ENGINE    │
          └────────┬─────────┘
                   │
          ┌────────┼─────────┐
          ▼        ▼         ▼
        Email      SMS      Push
          │        │         │
          ▼        ▼         ▼
       Provider  Provider  Firebase
22. One event can create many consequences

This is the real power.

Imagine:

booking.confirmed

The platform might automatically produce:

                  booking.confirmed
                         │
        ┌────────────────┼─────────────────┐
        │                │                 │
        ▼                ▼                 ▼
 Notification          Audit           Analytics
        │
   ┌────┼─────┐
   ▼    ▼     ▼
 Push Email In-App
        │
        ▼
    Receipt

Meanwhile:

booking.confirmed
        │
        ├──► Hotel system
        ├──► Transport system
        ├──► Loyalty system
        ├──► Revenue accounting
        └──► Customer support

The booking service doesn't have to know that all of these systems exist.

That is decoupling.

23. The most important architectural rule

I would make this a formal AFCON360 architectural principle:

Business domains publish facts. They do not directly orchestrate cross-domain notifications or communication.

For example, don't do this:

def approve_kyc():
    approve()

    notification_service.send_email()
    notification_service.send_sms()
    notification_service.create_in_app()

    audit_service.record()
    analytics.track()

Instead:

def approve_kyc():

    approve()

    publish_event(
        "kyc.approved",
        aggregate_id=kyc.id,
        actor_id=current_user.id
    )

Then the platform takes over.

24. And eventually this becomes a platform capability

This is important for the architecture work we've been doing.

You don't want every AFCON360 module independently inventing:

notifications
events
audit
emails
SMS
retry
preferences
templates
webhooks

Instead:

AFCON360 PLATFORM SERVICES
│
├── Identity
├── Configuration
├── Event Bus
├── Notification
├── Audit
├── File Storage
├── Search
├── Payments
├── Observability
└── Feature Flags

Then your domains:

Accommodation
Transport
Tourism
Wallet
Bookings
KYC

consume those platform capabilities.

The architecture I would recommend for AFCON360 right now

Because you're still building the system and you're constrained by resources, don't jump straight to Kafka and dozens of microservices.

Use a staged architecture:

Stage 1 — Your current Flask monolith
Flask
 │
 ├── Domain Events
 ├── Notification Service
 ├── Audit Service
 ├── PostgreSQL
 ├── Redis
 └── Celery
Stage 2 — Event-driven modular monolith

Add:

PostgreSQL Outbox
        ↓
Redis Streams
        ↓
Celery Consumers

Now your modules communicate through events.

Stage 3 — Enterprise scale

When traffic and organizational complexity justify it:

Kafka
 ↓
Independent domain services
 ↓
Independent notification platform
 ↓
Dedicated audit/event infrastructure

That gives you an enterprise architecture without prematurely turning AFCON360 into 30 microservices.

And given the notification-service code you've been working on recently, I think the next architectural step should be to define AFCON360's canonical event model (event_id, event_type, aggregate_id, actor, correlation ID, causation ID, timestamp, payload, version) and the Outbox → Redis/Celery → Notification pipeline before adding more notification channels. That will give registration, KYC, payments, bookings, wallet activity, and accommodation a single backbone instead of each module developing its own notification logic.

look aht this progress what are we missing

AFCON360 Unified Notification System
Overview

The AFCON360 Notification System is a robust, multi-channel notification platform integrated into the AFCON360 management ecosystem. It provides centralized notification delivery across all modules including wallet, accommodation, transport, events, identity, and KYC.

Architecture
app/notifications/
├── __init__.py                    # Blueprint registration & service exports
├── models.py                      # SQLAlchemy models (Notification, Template, Preferences, Log,
│                                 #   CommunicationSettings, NotificationAggregator, Message)
├── services.py                    # Centralized NotificationService with cross-module integration
│                                 #   + delivery-zone policy (_resolve_delivery_zone)
├── tasks.py                       # Celery async workers & beat scheduler
├── preferences.py                 # User notification preference management
├── template_loader.py             # Jinja2 Environment loader for email/SMS/push templates
├── mock_data.py                   # Dev/test fixtures + seed_mock_notification_data()
├── utils.py                       # Rate limiting, exponential backoff, idempotency
├── channel_handlers/              # Pluggable handlers per channel (single email sender)
│   ├── __init__.py                # BaseChannelHandler ABC
│   ├── email.py                   # EmailHandler — THE ONLY mail.send() site
│   ├── sms.py                     # SMS (Twilio/Africa's Talking)
│   ├── push.py                    # Push (Firebase Cloud Messaging)
│   ├── in_app.py                  # In-app persistent inbox
│   └── webhook.py                 # HTTP JSON callback webhooks
├── integrations/                  # Aggregator dispatch (SendGrid/SMTP/Twilio/FCM/SAP)
├── signals.py / listeners.py      # Decoupled blinker signal -> notification dispatch
├── context.py / settings.py       # Request context helpers + comms settings
├── templates/                     # Email HTML, SMS txt, Push JSON templates
│   └── email/                     # <notification_type>.html — one per NotificationType (30/30 covered)
│       ├── default.html           # Generic fallback (renders title/message/link)
│       ├── booking_confirmed.html
│       ├── booking_cancelled.html
│       ├── payment_received.html
│       ├── deposit_confirmed.html
│       ├── withdrawal_completed.html
│       ├── transaction_completed.html
│       ├── event_registered.html
│       ├── event_reminder.html
│       ├── kyc_approved.html
│       ├── kyc_rejected.html
│       ├── verification_email.html
│       ├── password_reset.html
│       └── ... (one template per NotificationType value)
└── README.md                      # This file

Key Components
Models (models.py)
Notification — Central notification record with BIGINT internal ID, UUID external ID, type, channel, status, priority, scheduling, retry tracking, and deep links
NotificationType — Enum covering all notification types across accommodation, auth, transport, events, wallet, and system domains
NotificationChannel — Enum for delivery channels: in_app, email, sms, push, webhook
NotificationStatus — Enum for lifecycle: pending, sent, delivered, failed, read, cancelled
NotificationTemplate — Reusable templates per type and channel with Jinja2 rendering
UserNotificationPreference — Per-user, per-type, per-channel opt-in/opt-out preferences
NotificationLog — Audit log for each delivery attempt with response codes and bodies
Service (services.py)
NotificationService.send() — Core dispatch method with user preference checking, channel validation, and delivery tracking
NotificationService.send_multi_channel() — Simultaneous multi-channel delivery
NotificationService.send_wallet_notification() — Wallet transaction notifications with full context
NotificationService.send_booking_notification() — Accommodation booking notifications
NotificationService.send_transport_notification() — Transport booking notifications
NotificationService.send_event_notification() — Event registration notifications
NotificationService.send_review_notification() — Review received notifications
NotificationService.send_kyc_notification() — KYC verification notifications
NotificationService.send_organisation_notification() — Organisation update notifications
NotificationService.resend_failed() — Retry failed notifications with exponential backoff
Tasks (tasks.py)
send_notification_task — Async single notification delivery with retry logic
send_bulk_task — Concurrent bulk notification processing
schedule_reminders_task — Celery Beat: dispatches scheduled notifications
cleanup_old_notifications_task — Celery Beat: archives old logs and soft-deletes stale read notifications
resend_failed_task — Celery Beat: resends failed notifications
Channel Handlers (channel_handlers/)

Each handler implements BaseChannelHandler with validate_recipient() and deliver() methods:

EmailHandler — THE single email sender. Validates email format, renders templates/notifications/email/<type>.html via the Jinja Environment (works with or without a request context), and delivers via Flask-Mail/SMTP. This is the only mail.send() call in the codebase.
SmsHandler — Validates phone length, delivers via Twilio/Africa's Talking
PushHandler — Validates user_id, delivers via Firebase Cloud Messaging
InAppHandler — Validates user_id, stores in persistent inbox
WebhookHandler — Accepts all recipients, delivers HTTP JSON payload
Preferences (preferences.py)
PreferenceService.get_preferences() — Get all preferences for a user
PreferenceService.update_preference() — Create or update a preference
PreferenceService.is_allowed() — Check if notifications are allowed for a type/channel
PreferenceService.get_enabled_channels() — Get enabled channels for a notification type
PreferenceService.set_all_enabled() — Bulk enable/disable all preferences
Quick Start
Celery Workers

To start the Celery async worker:

celery -A app.celery_app worker --loglevel=info


To start Celery Beat scheduler for scheduled notifications & retry queue:

celery -A app.celery_app beat --loglevel=info

Triggering Notifications in Code
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

User Preferences
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

Reading Notifications
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

Cross-Module Integration

The notification system integrates with all AFCON360 modules:

Module	Integration Point	Notification Type
Wallet	NotificationService.send_wallet_notification()	TRANSACTION_COMPLETED, DEPOSIT_CONFIRMED, WITHDRAWAL_COMPLETED
Accommodation	NotificationService.send_booking_notification()	BOOKING_CONFIRMED, BOOKING_CANCELLED
Transport	NotificationService.send_transport_notification()	BOOKING_CONFIRMED, DRIVER_ASSIGNED, BOOKING_UPDATE
Events	NotificationService.send_event_notification()	EVENT_REGISTERED, EVENT_REMINDER
KYC	NotificationService.send_kyc_notification()	VERIFICATION_EMAIL
Accommodation Reviews	NotificationService.send_review_notification()	REVIEW_RECEIVED
Identity/Organisation	NotificationService.send_organisation_notification()	SYSTEM_ALERT
Backward Compatibility

Existing imports continue to work via re-exports:

from app.models.notification import Notification, NotificationType, NotificationChannel → re-exports from app.notifications.models
from app.services.notification_service import NotificationService → re-exports from app.notifications.services
API Endpoints

The notification blueprint (notifications_api, url prefix /api/notifications) exposes:

Inbox & Preferences
GET /api/notifications — List user notifications (filters: unread_only, type, limit, offset)
GET /api/notifications/unread-count — Unread badge count
GET /api/notifications/<id> — Notification detail
PATCH /api/notifications/<id>/read — Mark read
DELETE /api/notifications/<id> — Soft-delete (hide from inbox)
POST /api/notifications/read-all — Mark all read
GET /api/notifications/preferences — Get user preferences
PUT/POST /api/notifications/preferences — Bulk update preferences
POST /api/notifications/preferences/channel — Toggle an entire channel on/off
Internal Messaging
GET /api/notifications/messages — List inbox + sent
POST /api/notifications/messages — Send internal message (body: recipient_public_id, subject, body, message_type)
POST /api/notifications/messages/<id>/read — Mark message read
POST /api/notifications/messages/<id>/archive — Archive message
Admin Communication Settings (owner/super_admin/admin)
GET /api/notifications/admin/settings — List providers + aggregators (secrets redacted)
POST/PUT /api/notifications/admin/settings — Upsert provider setting (email/sms/push/webhook)
POST/PUT /api/notifications/admin/aggregators — Register external aggregator (Twilio, SendGrid, FCM, WhatsApp, SAP)
POST /api/notifications/admin/settings/<id>/toggle — Enable/disable a channel/provider
POST /api/notifications/admin/aggregators/<id>/test — Send a test message via an aggregator
GET /api/notifications/admin/dead-letter — Inspect failed (dead-letter) notifications
POST /api/notifications/admin/resend-failed — Retry all failed notifications
POST /api/notifications/admin/broadcast — Platform announcement to all/role-filtered users
Dashboard Integration
Context processor inject_notification_context injects notif_badges (unread notifications + messages) and recent_notifications into every template.
Notification bell UI: templates/components/notification_bell.html renders the badge + dropdown inbox. It is already wired into every shared base template, so all dashboards inherit it automatically:
Base template	Dashboards covered
templates/base.html	super_admin, admin, owner, auditor, support, moderator, event_manager, transport_admin, wallet_admin, accommodation_admin, tourism_admin, org_admin, org_member, fan, user, events, host (~30 pages)
templates/admin/compliance/base_compliance.html	compliance officer
templates/admin/moderator/base_moderator.html	moderator console
templates/wallet/base_wallet.html	wallet
templates/transport/base.html, transport/dashboard/base_dashboard.html	transport
templates/auditor/dashboard.html	standalone auditor page
To add the bell to a new standalone page:	
{% include 'components/notification_bell.html' %}

It renders nothing for anonymous users, needs no route changes (data comes from
the context processor), polls /api/notifications/unread-count every 60s, and is
safe to include more than once per page.
Role-Aware Operational Routing

Operational/admin alerts are not limited to owner/super_admin/admin. Every
domain also notifies the specialist role that owns that dashboard, so an event
manager sees event activity, a wallet admin sees large transactions, etc.

NotificationService.DOMAIN_ROLE_MAP:

domain=	Roles notified (in addition to owner/super_admin/admin)
accommodation	accommodation_admin, moderator
transport	transport_admin
events	event_manager
wallet	wallet_admin, compliance_officer
tourism	tourism_admin
kyc / identity	compliance_officer, auditor
account	support
moderation	moderator

Usage — pass domain= and the correct roles are resolved automatically:

cls._notify_admins(
    notification_type=NotificationType.EVENT_REGISTERED,
    title="New Event Registration",
    message="A new registration was received.",
    link="/events/admin/dashboard",
    channels=['in_app'],
    domain='events',          # → owner, super_admin, admin, event_manager
)


To target an arbitrary role set directly:

NotificationService.notify_roles(
    roles=['wallet_admin', 'compliance_officer'],
    notification_type=NotificationType.SYSTEM_ALERT,
    title="Reconciliation break",
    message="Ledger mismatch detected.",
    link="/admin/wallet/reconciliation",
)


notify_roles() de-duplicates users holding several matching roles and skips
inactive accounts.

Lifecycle Coverage (Signals)

Decoupled blinker signals (app/notifications/signals.py) fire from domain services; listeners (app/notifications/listeners.py) dispatch notifications. Covers the full user journey:

Lifecycle Event	Signal	Notification
Account created	user_signed_up	Signup welcome (user) + admin alert
KYC submitted / approved / rejected	kyc_*	KYC status (user) + admin alert
Wallet created	wallet_created	Wallet-ready notice
Wallet transaction	wallet_transaction	Multi-channel payment receipt + admin alert (large tx)
Property submitted / approved / rejected / suspended	property_*	Host notice + admin alert
Booking confirmed / cancelled / checked-in / checked-out	booking_*	Guest + host notifications
Event registered	event_registered (reuses events module signal)	Event confirmation + QR reference
Transport booking created / driver assigned	transport_*	Customer + driver notifications
Internal message	message_sent	In-app inbox + message notification

Direct hooks also fire from auth/services.register_user, wallet_service.create_wallet,
accommodation/routes moderation actions, kyc/services.approve_kyc/reject_kyc,
accommodation/services.booking_service.confirm_booking, and
transport/services.booking_service.create_booking.

Aggregators & Future-Proofing

NotificationAggregator registers external gateways with priority ordering. Supported provider_type:

twilio (SMS + WhatsApp)
sendgrid / smtp / mailgun / ses (email)
fcm / apns (push)
generic / sap (webhook / SAP Event Mesh — future integration)

Dispatch logic in app/notifications/integrations/__init__.py routes each channel to the correct
client (Twilio SDK, Flask-Mail, FCM, requests webhook). Secrets stored encrypted at rest via
CommunicationSettingsService._encrypt_config (uses app.utils.crypto).

Backward Compatibility

Existing imports continue to work via re-exports:

from app.models.notification import Notification, ... → re-exports from app.notifications.models (now includes CommunicationSettings, NotificationAggregator, Message)
from app.services.notification_service import NotificationService → re-exports from app.notifications.services
Testing

Notification tests live in the main test suite (tests/notifications/) so they are captured by
the shared tests/conftest.py fixtures (app, client, db_session). Run them with:

# Requires a populated test database first:
python scripts/setup_test_db_schema.py

# Run notification tests
pytest tests/notifications/ -v

# Run the whole suite
pytest tests/

Development Fixtures (mock_data.py)

app/notifications/mock_data.py provides realistic fixtures for local dev and
tests, ported from the legacy app/src/data/mockData.ts. Two kinds:

Domain fixtures (plain dicts only). Users, wallets, events, registrations,
properties, property bookings, vehicles, transport bookings, KYC submissions.
These describe entities that already have real SQLAlchemy models elsewhere
(app.identity.models.user.User, app.wallet.models.transaction.TransactionModel,
app.accommodation.models.*, app.events.models.*, app.transport.models.*,
app.kyc.models.KycRecord). They are NOT duplicated as models here — the
dicts are reference data for building test contexts.
Notification fixtures (mappable to real models). Notification templates
(seeded from defaultTemplates), preferences, notifications, and delivery
logs.
API
get_mock_data() — returns a deep copy of every fixture group (dry run).
get_mock_user(identifier) / get_mock_wallet(user_id) — look up domain fixtures.
render_mock_template(template_str, context) — renders {{ placeholder }} tokens
via the shared Jinja Environment (missing keys → empty string).
seed_mock_notification_data(db_session, user_id=..., include_templates=True, include_preferences=True, include_notifications=True, commit=True) — persists
notification templates/preferences/notifications/logs. With db_session=None it
returns the raw dicts (dry run, nothing written).
clear_mock_notification_data(db_session, user_id=None) — removes seeded rows.
Example
from app.notifications.mock_data import seed_mock_notification_data, clear_mock_notification_data

# Dry run (no DB writes) — just get the dicts
fixtures = seed_mock_notification_data()

# Persist realistic notification data for a real user
summary = seed_mock_notification_data(db_session, user_id=user.id)
print(summary)  # {'templates': 9, 'preferences': 8, 'notifications': 4, 'logs': 3, 'objects': {...}}

# Tear down
clear_mock_notification_data(db_session, user_id=user.id)


The module is exported from the package __init__:
from app.notifications import seed_mock_notification_data.

Templates

Notification email templates live at templates/notifications/email/, named
exactly after the NotificationType value (e.g. booking_confirmed.html,
payment_received.html, event_reminder.html). There is one template per
notification type (30/30 covered).

Rendering (important): EmailHandler renders templates through the Jinja
Environment exposed by template_loader (template_loader.env.get_template( "email/<type>.html").render(...)), NOT flask.render_template. This is
deliberate — flask.render_template requires an active request context, which
is absent in standalone scripts, Celery tasks, and signal listeners, causing a
silent fallback to plain text. The Environment approach renders branded HTML
everywhere.

Rules:

If email/<type>.html exists, it is rendered with the context
title, message, notification, data, link, user_id.
If it is missing, email/default.html (which renders title/message/link)
is used as the generic branded fallback.
If both are missing (shouldn't happen — coverage is 100%), the plain-text
notification.body is sent.

SMS/push templates (when used) live under templates/notifications/sms/ and
templates/notifications/push/. template_loader.py resolves these paths
automatically; no per-module templates directory is used.

Adding a template

When you add a NotificationType, also add templates/notifications/email/<type>.html.
Copy default.html and replace the <h2>/<p> copy. Keep the branded
border-top: 5px solid #008751 header style for visual consistency.

Migration Notes

New tables required:

notification_templates — Reusable notification templates
user_notification_preferences — Per-user notification preferences
notification_logs — Delivery attempt audit log
communication_settings — Provider/channel configuration (email/sms/push/webhook)
notification_aggregators — External messaging gateways (Twilio, SendGrid, FCM, SAP, etc.)
messages — Internal bidirectional messaging

Proposed migration commands (run manually — never auto-migrated):

flask db migrate -m "add notification templates, preferences, communication settings, aggregators, messages"
flask db upgrade

Architecture Decision Record (ADR) — Central Notification System

Audience: the next engineer. This section explains why the notification
subsystem is built the way it is and how to extend it without reintroducing
duplicated email-sending code.

1. Centralized vs Decentralized — Decision: CENTRALIZED

AFCON360 uses a single, centralized notification system. Every module
(wallet, accommodation, transport, events, identity, KYC, admin, auth, messaging)
MUST route its outbound communication through NotificationService and the
pluggable channel handlers under app/notifications/channel_handlers/.

Why not decentralized? Decentralization would mean each module owning its own
SMTP client, template set, retry logic, and provider config. That causes:

Duplicated Flask-Mail / mail.send code in 5+ places (we found and removed
exactly this: auth/otp_service.py, admin/owner/rate_limit_notifications.py,
events/routes.py, events/tasks.py, notifications/integrations/__init__.py,
and a dead _send_email in notifications/services.py).
Inconsistent delivery, retries, templating, and audit logging.
No single place to enforce policy (preferences, external-vs-internal zone).

The single email sender is EmailHandler (channel_handlers/email.py).
It is the ONLY module that imports flask_mail.Message and calls mail.send().
Grepping the codebase for mail.send( should return exactly one hit (in
EmailHandler). Every other sender delegates to it.

2. The "Two Zones" Model — Internal vs External

A core principle: the platform is the source of truth for in-system messaging,
but users also live in the external world (Gmail, Yahoo, SMS, push).

Zone	Channel	Cost / Reach	Example
Internal	in_app	Free, persisted to DB inbox	Booking shows in user's AFCON360 inbox
External	email, sms, push, webhook	Hits a real provider	Same booking also lands in user's Gmail/Yahoo

Dual delivery is a first-class requirement. When a user books a hotel (or
any confirmation flow), they receive the SAME message in BOTH their in-app inbox
AND their real external mailbox (Gmail/Yahoo/etc). This is enforced by the
delivery-zone policy below.

3. Delivery-Zone Policy (NotificationService._resolve_delivery_zone)

This is the brain that decides which channels actually fire. Rules, in order:

in_app is always honoured for a known internal user. A user always sees
the message inside the system.
External channels (email/sms/push) fire for an internal user when ANY of:
the recipient is external (no user_id) — e.g. a signup/OTP email to an
address that is not yet a user;
the user has explicitly opted in to that channel for that notification
type (UserNotificationPreference);
the caller lists the external channel alongside in_app (dual-delivery
intent), OR passes force_external=True.
webhook is treated as always-external (3rd-party subscriber integration).

Result: flows like booking/wallet/transaction confirmations that call
NotificationService.send(..., channels=['email', 'in_app'], ...) automatically
deliver to BOTH the in-app inbox and the user's real mailbox. Purely internal
chatter (e.g. an admin-only alert with no opt-in) stays in-app unless opted in.

How to call it
from app.notifications.services import NotificationService
from app.notifications.models import NotificationType

# Dual delivery (in-app inbox + real Gmail/Yahoo) — booking/wallet confirmations
NotificationService.send(
    user_id=user.id,
    notification_type=NotificationType.BOOKING_CONFIRMED,
    title="Booking Confirmed",
    message="Your Ggaba penthouse is confirmed.",
    channels=['email', 'in_app'],   # external + in_app => dual delivery
    link="/accommodation/bookings/bk_001",
    priority='high',
)

# External-only (no user yet) — signup / OTP verification
NotificationService.send(
    user_id=None,
    notification_type=NotificationType.VERIFICATION_EMAIL,
    title="Verify your email",
    message="Your code is 123456",
    channels=['email'],
    email="prospect@example.com",
)

# Internal-only (default) — stays in the platform inbox
NotificationService.send(
    user_id=user.id,
    notification_type=NotificationType.SYSTEM_ALERT,
    title="Heads up",
    message="Routine maintenance tonight.",
    channels=['in_app'],
)

4. Single-Handler Routing — How It Was Implemented

Before this ADR, email was sent from at least six places. The consolidation:

Before (duplicated)	After (single handler)
auth/otp_service.send_email_otp re-implemented Flask-Mail	delegates to EmailHandler().deliver(...)
admin/owner/rate_limit_notifications._send_email used mail.send	builds a transient Notification, calls EmailHandler().deliver(...)
events/routes.py used mail.send for organizer + confirmation	calls EmailHandler().deliver(...) with rendered HTML
events/tasks.py used mail.send for registration emails	calls EmailHandler().deliver(...)
notifications/integrations._dispatch_email used mail.send	calls EmailHandler().deliver(...) (preserves per-aggregator SMTP override)
notifications/services._send_email (dead) re-implemented Flask-Mail	now delegates to EmailHandler

EmailHandler.deliver(notification, recipient) contract (DO NOT bypass it):

recipient is a dict {'email': ..., 'phone': ..., 'user_id': ...}.
Returns {'success': bool, 'external_id': str, 'response_code': int, 'response_body': str}.
Renders templates/notifications/email/<type>.html via the Jinja Environment
(NOT flask.render_template, which needs a request context). Falls back to
email/default.html if the type template is missing; if even that is absent,
sends the plain-text notification.body.
Uses flask_mail + the configured MAIL_* env vars (Gmail SMTP today;
SendGrid/Mailgun/SES via NotificationAggregator later).
5. Extension Guide (do NOT create new mail.send sites)

To add a new notification:

Add the NotificationType value in models.py (and its CHECK constraint
entry) if it's a new type.
Add a template under templates/notifications/email/ (optional but
preferred) or rely on body.
Call NotificationService.send(...) from the originating module.
If you need to send email from a non-notification module (e.g. a one-off admin
alert), construct a Notification and call EmailHandler().deliver(...).
Never import flask_mail.Message / mail.send directly.

To add a new channel (e.g. WhatsApp):

Subclass BaseChannelHandler in channel_handlers/, implement
validate_recipient + deliver, register it in EmailHandler's sibling
__init__.py and in NotificationService.HANDLERS.
Add the channel to NotificationChannel and the relevant CHECK constraints.
6. Preferences, Audit, Retry
Preferences: PreferenceService.is_allowed(user_id, type, channels) is the
gate checked before delivery. Users opt in/out per type+channel.
Audit: every delivery attempt writes a NotificationLog row
(notification_logs) with response_code/response_body.
Retry: NotificationService.resend_failed() + Celery resend_failed_task
retry failed notifications with exponential backoff (see utils.calculate_backoff).
Aggregators: NotificationAggregator registers external gateways with
priority ordering; integrations/__init__.py routes each channel to the right
client. Secrets are encrypted at rest.
7. Anti-Patterns (forbidden)
❌ Direct from flask_mail import Message; mail.send(msg) outside
channel_handlers/email.py.
❌ Module-local SMTP/templating logic.
❌ Treating every internal event as an external email (use the delivery-zone
policy instead).
✅ One entry point: NotificationService.send. One sender: EmailHandler.
8. CRITICAL BOUNDARY RULE — Form Validation vs System Notifications
The single most common way the notification pipeline gets polluted is confusing
Flask flash() (ephemeral UI feedback) with the AFCON360 Notification System (the
bell-icon inbox). Both use the word "notification", but they are disjoint:
| Category | Trigger | Storage | Where it appears |
|----------|---------|---------|------------------|
| 1. Request Validation (ephemeral) | Missing required field, bad file type, weak password | NO DB row — Flask flash() or template context | Inline under the field or a single dismissible alert on submit; cleared next render |
| 2. Event-Driven Notification (persistent) | KYC submitted/approved/rejected, payment successful, booking confirmed | Notification model via NotificationService / emit_event | Bell icon inbox + email/push/sms |
Rules:
- Validation errors MUST NOT be routed through NotificationService or emit_event.
  They are not facts about the world; they are a rejected request.
- After a redirect, validation errors are flashed ONCE. Never re-flash on GET
  renders — that is what causes the "error stacked 6+ times" bug.
- Use app.utils.flash_helpers.flash_form_error(msg) (always 'danger') or
  flash_form_errors(form) so categories are consistent across every template.
  The shared macro (templates/macros/flash_messages.html) maps 'error'->'danger'
  and only whitelists success/warning/danger/info; always pass a valid category.
- System events fire ONLY after a successful state change. Example (correct):
  record = KycService.submit_kyc(...)        # state change
  emit_event(EventType.KYC_SUBMITTED, ...)   # -> NotificationConsumer -> inbox
- Access-denied and field-validation messages are Category 1 (flash), NOT
  Category 2. Only the resulting "your document was approved" is Category 2.

Yes. Looking at what you have already built, you are much further along than a typical notification module. You have most of the delivery platform already.

But there is an important distinction:

You have built a strong Notification/Communication Service. You have not yet fully built the Enterprise Event/Communication Backbone that feeds it.

That is the main gap.

1. Where you are now

I'd rate the current architecture roughly like this:

Capability	Current state	Assessment
Central notification service	✅	Strong
Multi-channel delivery	✅	Strong
In-app inbox	✅	Strong
Email	✅	Strong
SMS	✅	Strong
Push	✅	Strong
Webhooks	✅	Strong
Templates	✅	Strong
User preferences	✅	Strong
Provider abstraction	✅	Strong
Provider failover/priority	✅	Good
Retry/backoff	✅	Good
Dead-letter handling	✅	Good
Scheduled notifications	✅	Good
Role-aware routing	✅	Very good
Internal messaging	✅	Good
Admin controls	✅	Good
Cross-module hooks	✅	Good
Audit delivery logs	✅	Good
Idempotency	⚠️	Present at notification level, but needs event-level design
Domain event bus	❌	Missing
Durable event persistence/outbox	❌	Missing
Event schema/versioning	❌	Missing
Correlation/causation IDs	❌	Missing
Event consumer registry	❌	Missing
Event replay	❌	Missing
Event ordering guarantees	❌	Missing
Transactional event publishing	❌	Missing
Event-level DLQ	⚠️	You have notification DLQ, not necessarily event DLQ
Distributed tracing	⚠️	Needs formalization
Notification orchestration	⚠️	Present, but still largely service-driven
Compliance/audit event ledger	⚠️	Notification logs are not enough
Outbound webhook/event subscriptions	⚠️	Handler exists; subscription/event contract needs expansion

So I would not rebuild your notification system.

I would build the missing layer underneath it.

2. The biggest thing missing: an Event Backbone

Right now your architecture is approximately:

Accommodation ─────┐
Wallet ────────────┤
KYC ───────────────┤
Transport ─────────┤
Events ────────────┤
Identity ──────────┤
                   ▼
          NotificationService
                   │
          ┌────────┼────────┐
          ▼        ▼        ▼
        Email     SMS      In-App

That's good.

But enterprise architecture should become:

                     DOMAIN SERVICES
                          │
        ┌─────────────────┼─────────────────┐
        ▼                 ▼                 ▼
   Accommodation        Wallet             KYC
        │                 │                 │
        └─────────────────┼─────────────────┘
                          ▼
                  ┌───────────────┐
                  │ DOMAIN EVENTS │
                  └───────┬───────┘
                          ▼
                  ┌───────────────┐
                  │    OUTBOX     │
                  └───────┬───────┘
                          ▼
                  ┌───────────────┐
                  │  EVENT BUS    │
                  │ Redis Streams │
                  └───────┬───────┘
                          │
             ┌────────────┼─────────────┐
             ▼            ▼             ▼
       Notification      Audit       Analytics
       Consumer         Consumer     Consumer
             │
             ▼
       NotificationService
             │
       ┌─────┼─────┬─────┐
       ▼     ▼     ▼     ▼
      App   Email  SMS   Push

That is the major architectural evolution I would make next.

3. Your Blinker signals are useful — but they are not the enterprise event bus

You currently have:

signals.py
listeners.py

and:

user_signed_up
kyc_approved
wallet_transaction
booking_confirmed
...

This is a good decoupling mechanism inside the Flask application.

But there is a fundamental limitation:

Blinker is in-process.

If the process dies:

Domain
  ↓
Blinker signal
  ↓
process crashes

the event can disappear.

There is no durable record saying:

payment.successful happened but the notification consumer never processed it.

So I would keep Blinker for now, but introduce a durable event layer.

4. You need an Event model

This is probably the single most important missing model.

Something conceptually like:

domain_events
────────────────────────────────────────
id
event_id
event_type
event_version

aggregate_type
aggregate_id

actor_type
actor_id

correlation_id
causation_id

occurred_at

payload

status
published_at
processed_at

created_at

For example:

{
  "event_id": "evt_8c71...",
  "event_type": "payment.successful",
  "event_version": 1,
  "aggregate_type": "payment",
  "aggregate_id": "pay_123",
  "actor_id": "usr_456",
  "correlation_id": "cor_789",
  "causation_id": "evt_previous",
  "occurred_at": "2026-08-08T..."
}

That becomes your internal language between modules.

5. You need the Outbox Pattern

This is the other major missing piece.

Suppose your payment code does:

payment.status = "successful"

emit_signal("payment_successful")

You have a race condition.

What if:

DB transaction commits
        ↓
process crashes
        ↓
signal never processed

Payment exists.

Notification doesn't.

Instead:

BEGIN
   │
   ├── update payment
   │
   └── insert domain event into outbox
   │
COMMIT

Then:

PostgreSQL Outbox
       ↓
Celery/Redis publisher
       ↓
Redis Streams
       ↓
Consumers

Now the event cannot simply vanish between the database operation and event publication.

6. Your NotificationLog is not an Event Ledger

This distinction is very important.

You currently have:

Notification
NotificationLog

Those answer:

Did we attempt to communicate something?

They don't necessarily answer:

What happened inside the AFCON360 platform?

For example:

payment.successful

might produce:

Audit Event
Wallet update
Accounting entry
Booking confirmation
Notification
Analytics event

If the email fails:

Email → FAILED

the payment event remains:

payment.successful → COMPLETED

Therefore you need two concepts:

Domain/Event Ledger
"What happened?"
Notification Ledger
"How did we communicate it?"

Don't merge them.

7. You need correlation IDs

This is something I'd add before going much further.

Imagine a hotel booking:

Registration
    ↓
Login
    ↓
KYC
    ↓
Payment
    ↓
Booking
    ↓
Confirmation

You want to trace the entire chain:

correlation_id = COR-123456

Then:

payment.initiated
payment.successful
booking.created
booking.confirmed
notification.created
email.sent
push.sent

can all be connected.

For a production incident, you can ask:

"Show me everything that happened for transaction X."

And retrieve the complete chain.

8. You also need causation_id

This goes one step further.

Suppose:

payment.successful

causes:

booking.confirmed

Then:

booking.confirmed.causation_id
      =
payment.successful.event_id

So you get:

payment.successful
       │
       └──── caused ────► booking.confirmed
                              │
                              └──► notification.created

This is incredibly useful for debugging complex workflows.

9. Your NotificationType enum is doing too much

You currently have things like:

BOOKING_CONFIRMED
PAYMENT_RECEIVED
KYC_APPROVED
EVENT_REGISTERED
...

That's fine for notification types.

But don't let this become your enterprise event taxonomy.

You need two separate concepts:

Domain Events
payment.successful
payment.failed
kyc.approved
kyc.rejected
booking.created
booking.confirmed
Notification Types
PAYMENT_RECEIVED
KYC_APPROVED
BOOKING_CONFIRMED

One event may produce:

payment.successful
    │
    ├── notification: PAYMENT_RECEIVED
    ├── audit event
    ├── accounting event
    └── loyalty event

That separation will save you a lot of pain later.

10. Your send_*() methods are another area I'd eventually reduce

You currently have:

send_wallet_notification()
send_booking_notification()
send_transport_notification()
send_event_notification()
send_review_notification()
send_kyc_notification()
send_organisation_notification()

These are useful right now, especially for backward compatibility.

But the mature architecture should move toward:

Domain Event
     ↓
Notification Policy
     ↓
Notification
     ↓
Channel

Rather than:

Wallet
   ↓
send_wallet_notification()

Booking
   ↓
send_booking_notification()

KYC
   ↓
send_kyc_notification()

Eventually the Notification Service shouldn't need to know every business domain's implementation details.

11. You need a Notification Policy Engine

You already have the beginning of one:

_resolve_delivery_zone()
PreferenceService
DOMAIN_ROLE_MAP

That's good.

But eventually formalize:

Notification Policy

For example:

EVENT:
payment.successful

RECIPIENT:
payment owner

DEFAULT:
in_app + email

OPTIONAL:
push

MANDATORY:
receipt

ROLE ALERT:
wallet_admin

THRESHOLD:
if amount > X → compliance_officer

PRIORITY:
high

Then:

payment.successful
       ↓
Policy Engine
       ↓
┌───────────────────────────┐
│ User                      │
│ in-app + email + push     │
│                           │
│ Wallet Admin              │
│ in-app                    │
│                           │
│ Compliance                │
│ only if threshold met     │
└───────────────────────────┘

That is much more powerful than embedding routing logic in individual services.

12. Your role-aware routing is actually ahead of many systems

This part:

accommodation → accommodation_admin
transport → transport_admin
events → event_manager
wallet → wallet_admin + compliance
kyc → compliance + auditor

is a good foundation.

But I would eventually move this out of hardcoded:

DOMAIN_ROLE_MAP

and toward a configurable policy/routing system.

Because eventually you'll need:

EVENT
ROLE
SEVERITY
REGION
ORGANISATION
PROPERTY
THRESHOLD

For example:

wallet.large_transaction
       │
       ├── wallet_admin
       ├── compliance
       ├── auditor
       └── owner

but:

wallet.normal_transaction
       │
       └── wallet_admin
13. You are also missing event subscriptions

You already have:

NotificationAggregator

but that is primarily about delivery providers.

You eventually need another concept:

EventSubscription

For example:

event_subscriptions

id
subscriber
event_type
endpoint
secret
status
version
created_at

Then external partners could subscribe:

booking.confirmed
payment.successful
property.approved

and AFCON360 sends them:

{
  "event": "booking.confirmed",
  "version": 1,
  "event_id": "...",
  "timestamp": "...",
  "data": {}
}

That turns AFCON360 into a platform rather than merely an application.

14. Webhooks need their own reliability model

Your WebhookHandler is good, but external webhooks need:

retry
signature
timestamp
idempotency
delivery ID
timeout
dead-letter
replay
subscription management

For example:

POST partner.com/webhook

X-AFCON360-Event-ID
X-AFCON360-Signature
X-AFCON360-Timestamp

And:

Webhook Delivery
      │
      ├── attempt 1 → failed
      ├── attempt 2 → failed
      ├── attempt 3 → success
      │
      └── delivery history

This should eventually be separate from normal user notifications.

15. You need event versioning

This will matter enormously later.

Today:

{
  "amount": 100000
}

Next year:

{
  "amount": 100000,
  "currency": "UGX",
  "fee": 500,
  "net_amount": 99500
}

Don't break old consumers.

Therefore:

payment.successful.v1
payment.successful.v2

or:

event_type = payment.successful
event_version = 2

I strongly prefer the second.

16. You need replay

Imagine your analytics consumer was down for two hours.

With durable events:

Event Store
     │
     ├── Event 101
     ├── Event 102
     ├── Event 103
     └── Event 104

You can replay:

Event 101 → analytics
Event 102 → analytics
Event 103 → analytics
Event 104 → analytics

without sending duplicate user emails.

That's why event processing and notification delivery must be separate concepts.

17. You need an event-level DLQ

You already have:

/admin/dead-letter

for notifications.

Good.

But you'll eventually want:

Event Dead Letter Queue

separate from:

Notification Dead Letter Queue

Because:

payment.successful

failing to reach the notification consumer is different from:

email delivery failed

These are two different failure domains.

18. Your internal Message system should remain separate

This is another thing I would preserve.

You have:

messages

and:

notifications

Don't merge them.

A message means:

Person/system intentionally communicated with another person.

A notification means:

The system informed someone that something happened.

For example:

Notification:
"Your booking has been confirmed."

Message:
"Hello John, please contact the hotel about your special request."

Different semantics.

19. You also need security events

Your current system covers business activity very well.

But enterprise platforms also produce:

login.success
login.failed
password.changed
password.reset
mfa.enabled
mfa.failed
session.revoked
device.registered
api_key.created
api_key.revoked
admin.login
admin.action
permission.changed
role.changed

These should feed the audit/security event system, and some should feed NotificationService.

For example:

password.changed
      │
      ├── Audit
      └── Notification
             ├── Email
             └── In-App
20. You need a proper audit event model

Your notification log is not sufficient for compliance.

I'd eventually have:

audit_events

id
event_id
actor_id
actor_type

action
resource_type
resource_id

before_state
after_state

ip_address
user_agent

correlation_id
timestamp

Then something like:

KYC APPROVED
──────────────────────────
Actor: compliance officer
Subject: user_8271
Resource: KYC-19282
Time: ...
Correlation: COR-123

This becomes extremely important when AFCON360 handles financial transactions.

21. You are also missing observability around the entire pipeline

You have delivery logs.

You should eventually be able to see:

Correlation ID: COR-123

payment.successful          ✓
booking.confirmed           ✓
notification.created        ✓
email queued                ✓
email provider accepted     ✓
email delivered             ?
push queued                 ✓
push delivered              ✓

This means adding:

metrics
structured logs
tracing
correlation IDs
latency measurements
failure rates
queue depth
provider health

Your admin dashboard could eventually show:

NOTIFICATION HEALTH

Email
██████████ 99.2%

SMS
█████████░ 96.8%

Push
██████████ 99.8%

Queue
142 pending

Dead Letter
7

Failed last hour
3
22. Your provider architecture is good, but secrets/config need one more boundary

You've already done:

CommunicationSettings
NotificationAggregator
encrypted config

Good.

But don't let arbitrary application code retrieve decrypted provider credentials.

The eventual pattern should be:

NotificationService
       ↓
Provider Registry
       ↓
Provider Adapter
       ↓
Credential Resolver
       ↓
Secret

And ideally credentials eventually move to a proper secret manager when you leave your current development/free-tier environment.

23. There is one subtle issue with your "always in-app" rule

You currently say:

in_app is always honoured for a known internal user.

That's a good product decision.

But don't confuse:

notification created

with:

notification delivered

For in-app:

notification persisted ✓

is basically delivery to the platform inbox.

For email:

queued
accepted
delivered
bounced
failed

are different states.

Your current status model:

pending
sent
delivered
failed
read
cancelled

is a good beginning, but eventually notification-level status and channel-delivery status should be separated.

For example:

Notification
    │
    ├── InAppDelivery → READ
    ├── EmailDelivery → DELIVERED
    └── PushDelivery  → FAILED

This is much cleaner than one notification having one global status.

24. The architecture I would freeze now

I would not add more notification features yet.

I would freeze your current system as:

Communication Layer
app/notifications/

Then add a new platform-level layer:

app/events/
├── __init__.py
├── models.py
├── schemas.py
├── publisher.py
├── consumer.py
├── registry.py
├── outbox.py
├── tasks.py
├── replay.py
└── exceptions.py

And:

app/audit/
├── models.py
├── service.py
├── events.py
└── tasks.py

Conceptually:

                   AFCON360 PLATFORM
                         │
        ┌────────────────┼─────────────────┐
        │                │                 │
        ▼                ▼                 ▼
      EVENTS          AUDIT          NOTIFICATIONS
        │                                  │
        │                                  │
        ▼                                  ▼
     OUTBOX                           POLICY ENGINE
        │                                  │
        ▼                                  ▼
  REDIS STREAMS                       CHANNELS
        │                         ┌────┬────┬────┐
        ├──► Audit               App Email SMS Push
        ├──► Analytics
        ├──► Notification
        ├──► Fraud
        └──► Future services
25. The complete AFCON360 lifecycle would then look like this

Take KYC approval.

Business operation
Compliance Officer
       ↓
KYC Service
       ↓
KYC status = APPROVED
Same DB transaction
KYC update
    +
domain_event
Event publication
Outbox
   ↓
Redis Streams
   ↓
kyc.approved
Consumers
                  kyc.approved
                       │
        ┌──────────────┼──────────────┐
        ▼              ▼              ▼
   Notification       Audit        Analytics
        │
        ▼
   Policy Engine
        │
    ┌───┼────┐
    ▼   ▼    ▼
   App Email Push
Result
USER
✓ KYC approved in account
✓ In-app notification
✓ Email

COMPLIANCE
✓ Audit record

ANALYTICS
✓ KYC approval event

SYSTEM
✓ Event retained
✓ Correlation ID
✓ Delivery logs
✓ Retry if necessary

That is now approaching a genuine enterprise platform.

26. So, what are you actually missing?

If I reduce everything above to the critical missing pieces, I would put them in this order:

🔴 P0 — Must build before calling the architecture enterprise-grade
Canonical Domain Event model
Transactional Outbox
Durable Event Bus — Redis Streams is enough for your current stage
Event IDs
Correlation IDs
Causation IDs
Event versioning
Event-level idempotency
Separate Domain Event Ledger from Notification Logs
🟠 P1 — Build immediately after
Event consumers
Event DLQ
Event replay
Notification Policy Engine
Separate notification/channel delivery records
Security events
Proper audit event ledger
Structured observability/tracing
🟡 P2 — Later
External event subscriptions
Signed webhooks
Partner developer API
Advanced provider failover
Regional routing
Kafka when scale actually requires it
And one very important conclusion

Your existing NotificationService is not the part I would replace.

In fact, a lot of the work you've done—centralized EmailHandler, channel handlers, preferences, templates, retries, aggregators, role routing, dead-letter notifications, internal messages, admin controls, and the delivery-zone policy—is exactly the communication layer we want.

The architectural mistake would be to keep adding more and more business hooks directly into it.

The next step is to put this in front of it:

             BEFORE

Domain ───────► NotificationService


             TARGET

Domain
  │
  ▼
Domain Event
  │
  ▼
Transactional Outbox
  │
  ▼
Redis Streams
  │
  ├────────► Audit
  ├────────► Analytics
  ├────────► Fraud
  ├────────► Future Services
  │
  └────────► NotificationService
                    │
                    ▼
              Policy Engine
                    │
          ┌─────────┼─────────┐
          ▼         ▼         ▼
        In-App    Email      SMS/Push

That is the gap between the very good notification subsystem you have now and the enterprise-grade communication architecture we were discussing.

And because you're already using PostgreSQL + Redis + Celery, you don't need to introduce Kafka, microservices, or another expensive infrastructure layer right now. The next architectural milestone should be Event Model → Outbox → Redis Streams → Consumers, while keeping your existing notification system intact.