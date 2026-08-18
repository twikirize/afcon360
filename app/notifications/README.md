# AFCON360 Unified Notification & Communication Platform

## Overview

The AFCON360 Notification System is a robust, multi-channel **communication
platform** integrated into the AFCON360 management ecosystem. It provides
centralized notification delivery across all modules including wallet,
accommodation, transport, events, identity, and KYC.

## Database and test contract

Notification tests use the shared fixtures with a dedicated, migrated
PostgreSQL database configured by `TEST_DATABASE_URL`. SQLAlchemy models and
expressions are required; SQLite fallbacks, handwritten SQL strings, and
test-time schema DDL are unsupported. See
`docs/POSTGRES_TESTING_CONTRACT.md`.

As of the latest milestone it is no longer *only* a delivery service. It now has
two layers:

| Layer | Location | Responsibility |
|-------|----------|----------------|
| **Event backbone** (new) | `app/notifications/events/` | *What happened.* Durable domain events, transactional outbox, Redis Streams bus, consumers, audit/analytics/webhook fan-out, replay. |
| **Delivery layer** (existing) | `app/notifications/` | *How we communicate it.* Policy → channels → providers, preferences, templates, retries, inbox. |

> **Why the backbone lives under `app/notifications/events/` and not `app/events/`:**
> `app/events/` is already the AFCON **events business domain** (matches,
> tickets, registrations). Creating a second top-level `app/events` would shadow
> it. Communication (events + notifications) is one platform capability, so the
> backbone is nested here.

## Architecture

```
app/notifications/
├── __init__.py                    # Blueprint registration & service/event exports
├── models.py                      # Notification, Template, Preferences, Log,
│                                  #   NotificationDelivery (per-channel state),
│                                  #   CommunicationSettings, Aggregator, Message
├── services.py                    # Centralized NotificationService
│                                  #   + delivery-zone policy (_resolve_delivery_zone)
├── tasks.py                       # Celery async workers & beat scheduler
├── preferences.py                 # User notification preference management
├── template_loader.py             # Jinja2 Environment loader
├── mock_data.py                   # Dev/test fixtures
├── utils.py                       # Rate limiting, exponential backoff, idempotency
├── channel_handlers/              # Pluggable handlers per channel
│   ├── email.py                   # EmailHandler — THE ONLY mail.send() site
│   ├── sms.py / push.py / in_app.py / webhook.py
├── integrations/                  # Aggregator dispatch (SendGrid/SMTP/Twilio/FCM/SAP)
├── signals.py / listeners.py      # Blinker signals (in-process, legacy path)
├── context.py / settings.py       # Request context helpers + comms settings
│
└── events/                        # ── PLATFORM EVENT BACKBONE (new) ──
    ├── __init__.py                # Public API surface
    ├── models.py                  # DomainEvent, OutboxEvent, ProcessedEvent,
    │                              #   EventSubscription, WebhookDelivery
    ├── schemas.py                 # EventEnvelope — the canonical wire format
    ├── registry.py                # EventType catalogue + contracts/versioning
    ├── context.py                 # correlation_id / causation_id propagation
    ├── publisher.py               # emit_event() — transactional outbox writer
    ├── outbox.py                  # OutboxRelay — outbox → bus, backoff, DLQ
    ├── bus.py                     # EventBus — Redis Streams + consumer groups
    ├── consumers.py               # Notification/Audit/Analytics/Webhook consumers
    ├── policy.py                  # NotificationPolicy + PolicyEngine
    ├── replay.py                  # EventReplayer — targeted, idempotency-aware
    ├── webhooks.py                # Signed partner webhook dispatcher
    ├── routes.py                  # /api/events admin + observability API
    ├── tasks.py                   # Celery: relay / consume / dispatch / cleanup
    └── exceptions.py              # Retryable vs Permanent classification
```

---

# PART 1 — The Event Backbone (what was just added)

## The core architectural rule

> **Business domains publish FACTS. They do not orchestrate communication.**

Before:

```python
def approve_kyc(kyc):
    kyc.status = 'approved'
    notification_service.send_email(...)
    notification_service.send_sms(...)
    audit_service.record(...)
    analytics.track(...)
    db.session.commit()
```

After:

```python
from app.notifications.events import emit_event, EventType

def approve_kyc(kyc):
    kyc.status = 'approved'
    emit_event(
        EventType.KYC_APPROVED,
        payload={'user_id': kyc.user_id, 'kyc_id': kyc.id},
        aggregate_type='kyc', aggregate_id=str(kyc.id),
    )
    db.session.commit()      # ← event + business change commit ATOMICALLY
```

The KYC service is done. The platform then fans out to notification, audit,
analytics and partner webhooks — none of which KYC needs to know about.

## Pipeline

```
Domain service
   │  emit_event(...)          same DB transaction
   ▼
domain_events  +  outbox_events        (COMMIT together — no dual-write race)
   │
   │  OutboxRelay  (Celery, every 10s)
   ▼
Redis Streams  (afcon360:events:*  +  :all firehose)
   │
   │  consume task (Celery, every 15s, consumer groups + XACK)
   ▼
ConsumerRegistry ──┬── NotificationConsumer → PolicyEngine → NotificationService → channels
                   ├── AuditConsumer        → audit_logs
                   ├── AnalyticsConsumer    → structured metrics
                   └── WebhookConsumer      → webhook_deliveries → signed partner POST
```

## Why the transactional outbox

`emit_event()` **does not commit and does not touch Redis.** It `flush()`es two
rows into the caller's session, so:

```
BEGIN
  UPDATE payments SET status='successful'
  INSERT INTO domain_events (...)
  INSERT INTO outbox_events (...)
COMMIT
```

* Business change rolls back → **no phantom event** is announced.
* Process dies right after COMMIT → the outbox row **survives**, and the relay
  publishes it on the next tick.

This closes the "DB committed but publish failed / publish succeeded but DB
rolled back" race that plain in-process signals cannot solve.

## Event vs Notification — a deliberate separation

| Concept | Example | Meaning |
|---------|---------|---------|
| **Domain event** | `payment.successful` | A *fact*. Immutable. May have many consequences. |
| **Notification type** | `PAYMENT_RECEIVED` | One *communication artefact* produced from that fact. |

`NotificationType` is **not** the event taxonomy. One event can produce a
notification, an audit record, an analytics point and a partner webhook — or
none at all. `security.login_failed` is audited but never emailed.

Likewise, `domain_events` (what happened) is separate from `notification_logs`
(how we tried to tell someone). **A bounced email must never rewrite the fact
that a payment succeeded.**

## Canonical event envelope

```json
{
  "event_id":       "evt_8c71...",
  "event_type":     "payment.successful",
  "event_version":  1,
  "aggregate_type": "payment",
  "aggregate_id":   "pay_123",
  "actor_type":     "user",
  "actor_id":       "456",
  "correlation_id": "cor_789",
  "causation_id":   "evt_previous",
  "occurred_at":    "2026-08-08T01:11:10+00:00",
  "payload":        { "...": "..." },
  "metadata":       { "...": "..." }
}
```

* **`event_id`** — stable idempotency key (`evt_<hex>`).
* **`event_version`** — payload contract version, so adding a field never breaks
  an old consumer.
* **`correlation_id`** — one whole user journey (registration → login → KYC →
  payment → booking → confirmation).
* **`causation_id`** — the event that directly caused this one, giving a causal
  tree rather than a flat log.

> **Note on ID format:** these are prefixed (`evt_`/`cor_`/`whd_`), not UUIDs, so
> they are self-describing in logs and partner payloads. They are registered in
> `BaseModel.NON_FK_STRING_IDS` so `IDGuard` allows them.

## Tracing a journey

```python
from app.notifications.events import EventReplayer

EventReplayer().trace('cor_789')
# [ {event_type: 'payment.successful',  causation_id: None},
#   {event_type: 'booking.confirmed',   causation_id: 'evt_8c71...'},
#   ... ]
```

Or over HTTP: `GET /api/events/trace/cor_789`.

## Event-level idempotency

Every consumer records `(consumer, event_id)` in `processed_events` before
handling. Redelivery — from a crash, a retry, or a replay — is a **no-op**:

```
1st dispatch → [('analytics', 'success')]
2nd dispatch → [('analytics', 'duplicate')]   ← suppressed, no second receipt
```

This is what makes at-least-once delivery safe.

## Retry, DLQ and replay

Backoff ladder (outbox and partner webhooks): **10s → 30s → 2m → 10m → 1h**,
then dead-letter.

Two **separate** dead-letter queues, because they are different failure domains:

| DLQ | Question it answers | Endpoint |
|-----|---------------------|----------|
| Notification DLQ | "The email bounced." | `/api/notifications/admin/dead-letter` |
| **Event DLQ** (new) | "The notification consumer never saw `payment.successful`." | `/api/events/dead-letter` |

Replay is **targeted and idempotency-aware** — you can re-feed a consumer that
was down for two hours *without re-emailing users*:

```python
EventReplayer().replay(only=['analytics'], reset_consumer=True, since=two_hours_ago)
```

The API additionally refuses to reset the `notification` consumer unless you
pass `"confirm_resend": true`, since that *would* re-send real messages.

## Notification Policy Engine

Declarative routing replaces hardcoded per-domain `send_*()` logic. One table
answers: is a notification required, who receives it, which channels, can the
user opt out, and does a threshold escalate it.

**Delivery classes** (governance):

| Class | Behaviour |
|-------|-----------|
| `MANDATORY` | Security / payment receipts / legal. **Cannot be disabled**; forces external delivery. |
| `OPTIONAL` | Respects `UserNotificationPreference`. |
| `MARKETING` | Requires explicit opt-in. |

**Audiences** (targeting): `SUBJECT`, `ROLES`, `ACTOR`, `CUSTOM`.

Threshold escalation in action — the *same* event behaves differently by amount:

```python
# UGX 5,000  → user receipt only
# UGX 5,000,000 → user receipt + wallet_admin/compliance_officer/auditor alert
```

Adding a policy:

```python
from app.notifications.events import NotificationPolicy, policy_engine, EventType, DeliveryClass

policy_engine.register(NotificationPolicy(
    event_type=EventType.PAYMENT_FAILED,
    notification_type='system_alert',
    title='Payment failed',
    message='Your payment of {currency} {amount} could not be completed.',
    channels=['in_app', 'email'],
    delivery_class=DeliveryClass.MANDATORY,
    module='wallet',
))
```

## Per-channel delivery records

`NotificationDelivery` fixes the "one notification, one global status" problem:

```
Notification
  ├── in_app delivery → READ
  ├── email delivery  → DELIVERED
  └── push delivery   → FAILED
```

Statuses: `queued → sending → accepted → delivered` plus `bounced`, `failed`,
`suppressed`, `read`. *Accepted by the provider* is explicitly **not**
*delivered*. `NotificationLog` remains the append-only per-attempt audit trail;
`NotificationDelivery` is the current authoritative state per channel.

## Partner event subscriptions (signed webhooks)

External partners subscribe to **externally-visible** events only (KYC and
security events are deliberately **not** exposed):

```
POST /api/events/subscriptions
{ "subscriber": "PartnerX", "endpoint": "https://partner.example/hooks",
  "event_types": ["booking.*", "payment.successful"] }
```

The signing secret is returned **once**. Every delivery is signed:

```
X-AFCON360-Event-Id     evt_...
X-AFCON360-Delivery-Id  whd_...
X-AFCON360-Event-Type   booking.confirmed
X-AFCON360-Timestamp    1754...
X-AFCON360-Signature    sha256=<HMAC-SHA256 over "{timestamp}.{body}">
```

The timestamp is part of the signed material, which defeats replay attacks. A
**circuit breaker** auto-pauses a subscription after 20 consecutive failures so
one dead partner cannot degrade the queue.

## Event backbone API (`/api/events`, owner/super_admin/admin)

| Endpoint | Purpose |
|----------|---------|
| `GET /api/events/health` | Bus status, stream length, queue depth, DLQ counts, failures/hour |
| `GET /api/events/registry` | Event catalogue + the notification policies each event drives |
| `GET /api/events` | Browse the ledger (filter by type/status/aggregate/correlation) |
| `GET /api/events/<event_id>` | Full event + per-consumer outcomes |
| `GET /api/events/trace/<correlation_id>` | Reconstruct one complete journey |
| `GET /api/events/dead-letter` | Event-level DLQ + stuck events |
| `POST /api/events/dead-letter/<event_id>/requeue` | Requeue a dead-lettered event |
| `POST /api/events/replay` | Targeted replay (`dry_run` defaults to **true**) |
| `GET/POST /api/events/subscriptions` | Manage partner subscriptions |
| `POST /api/events/subscriptions/<id>/status` | Activate/pause/disable + reset breaker |
| `GET /api/events/deliveries` | Partner webhook delivery history |
| `POST /api/events/deliveries/<delivery_id>/replay` | Requeue a failed partner delivery |

## Celery tasks & beat schedule

Registered in `app/celery_app.py` (`include` + `beat_schedule`):

| Task | Schedule | Purpose |
|------|----------|---------|
| `events.relay_outbox` | 10s | Outbox → Redis Streams |
| `events.consume` | 15s | Streams → consumers (with stale-message reclaim) |
| `events.dispatch_webhooks` | 30s | Queued partner webhooks → HTTPS |
| `events.retry_dead_letters` | 15m | Requeue transport-level DLQ rows |
| `events.health_snapshot` | 5m | Pipeline health metrics |
| `events.cleanup_ledger` | 24h | Retention pruning (ledger 365d, working tables 30d) |

Three decoupled loops, so a slow consumer never blocks publication and a dead
partner never blocks user notifications.

## Graceful degradation

* **Redis down** → events still commit safely to the outbox; the relay retries.
* **Event staging fails** → `emit_event` logs and returns `None`; it **never**
  raises into business code. Telemetry failure must not roll back a real booking.
* **One consumer crashes** → the others still run; only the failing one retries.
* **Event tables missing** → the `app.notifications` package still imports
  (`_EVENTS_AVAILABLE = False`) rather than breaking the whole app at boot.

## New tables

| Table | Purpose |
|-------|---------|
| `domain_events` | Durable event ledger — *what happened* |
| `outbox_events` | Transactional outbox staging queue |
| `processed_events` | Event-level idempotency `(consumer, event_id)` |
| `event_subscriptions` | External partner subscriptions |
| `webhook_deliveries` | Partner delivery attempts + DLQ |
| `notification_deliveries` | Per-channel delivery state |

**Migrations are never auto-generated or auto-run in this project.** Create them
manually when you are ready:

```bash
flask db migrate -m "add event backbone: domain_events, outbox_events, processed_events, event_subscriptions, webhook_deliveries, notification_deliveries"
flask db upgrade
```

> ⚠️ **Known pre-existing schema drift (unrelated to the event backbone):** the
> `notifications.module` column exists in `models.py` but not in the current
> database, which makes 21 tests in `tests/notifications/test_models.py` fail
> with `column notifications.module does not exist`. This predates the backbone
> work (verified by stashing). The same migration run will resolve it.

## Testing the backbone

```bash
pytest tests/notifications/test_events.py -v     # 24 passed, 2 skipped
```

Envelope, registry, policy and signing tests are DB-free so they run fast and
stay green regardless of schema state. Persistence tests skip cleanly when the
event tables are absent.

## Migration path for domain services

The existing blinker signals still work and nothing was removed. Migrate
incrementally — replace a `signal.send(...)` with `emit_event(...)` one domain at
a time:

```python
# before
booking_confirmed.send(self, booking=booking)

# after
emit_event(
    EventType.BOOKING_CONFIRMED,
    payload={'user_id': booking.user_id,
             'booking_reference': booking.booking_reference,
             'module': 'accommodation'},
    aggregate_type='booking', aggregate_id=booking.booking_reference,
)
```

Signals are in-process and vanish if the process dies; events are durable and
replayable. New code should prefer `emit_event`.

---

# PART 2 — The Delivery Layer (existing)

## Key Components

### Models (`models.py`)
- **`Notification`** — Central notification record with BIGINT internal ID, UUID external ID, type, channel, status, priority, scheduling, retry tracking, and deep links
- **`NotificationType`** — Enum covering all notification types across accommodation, auth, transport, events, wallet, and system domains
- **`NotificationChannel`** — Enum for delivery channels: in_app, email, sms, push, webhook
- **`NotificationStatus`** — Enum for lifecycle: pending, sent, delivered, failed, read, cancelled
- **`NotificationTemplate`** — Reusable templates per type and channel with Jinja2 rendering
- **`UserNotificationPreference`** — Per-user, per-type, per-channel opt-in/opt-out preferences
- **`NotificationLog`** — Append-only audit log for each delivery attempt with response codes and bodies
- **`NotificationDelivery`** — *(new)* Current per-channel delivery state (`queued/sending/accepted/delivered/bounced/failed/suppressed/read`), provider + `provider_message_id`, retry budget, and the originating `correlation_id`

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
- **EmailHandler** — THE single email sender. Validates email format, renders `templates/notifications/email/<type>.html` via the Jinja `Environment` (works with or without a request context), and delivers via Flask-Mail/SMTP. This is the **only** `mail.send()` call in the codebase.
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
- **Notification bell UI:** `templates/components/notification_bell.html` renders the badge + dropdown inbox. It is already wired into every shared base template, so all dashboards inherit it automatically:

  | Base template | Dashboards covered |
  |---------------|--------------------|
  | `templates/base.html` | super_admin, admin, owner, auditor, support, moderator, event_manager, transport_admin, wallet_admin, accommodation_admin, tourism_admin, org_admin, org_member, fan, user, events, host (~30 pages) |
  | `templates/admin/compliance/base_compliance.html` | compliance officer |
  | `templates/admin/moderator/base_moderator.html` | moderator console |
  | `templates/wallet/base_wallet.html` | wallet |
  | `templates/transport/base.html`, `transport/dashboard/base_dashboard.html` | transport |
  | `templates/auditor/dashboard.html` | standalone auditor page |

  To add the bell to a new standalone page:
  ```jinja
  {% include 'components/notification_bell.html' %}
  ```
  It renders nothing for anonymous users, needs no route changes (data comes from
  the context processor), polls `/api/notifications/unread-count` every 60s, and is
  safe to include more than once per page.

## Role-Aware Operational Routing

Operational/admin alerts are **not** limited to `owner/super_admin/admin`. Every
domain also notifies the specialist role that owns that dashboard, so an event
manager sees event activity, a wallet admin sees large transactions, etc.

`NotificationService.DOMAIN_ROLE_MAP`:

| `domain=` | Roles notified (in addition to owner/super_admin/admin) |
|-----------|----------------------------------------------------------|
| `accommodation` | `accommodation_admin`, `moderator` |
| `transport` | `transport_admin` |
| `events` | `event_manager` |
| `wallet` | `wallet_admin`, `compliance_officer` |
| `tourism` | `tourism_admin` |
| `kyc` / `identity` | `compliance_officer`, `auditor` |
| `account` | `support` |
| `moderation` | `moderator` |

Usage — pass `domain=` and the correct roles are resolved automatically:

```python
cls._notify_admins(
    notification_type=NotificationType.EVENT_REGISTERED,
    title="New Event Registration",
    message="A new registration was received.",
    link="/events/admin/dashboard",
    channels=['in_app'],
    domain='events',          # → owner, super_admin, admin, event_manager
)
```

To target an arbitrary role set directly:

```python
NotificationService.notify_roles(
    roles=['wallet_admin', 'compliance_officer'],
    notification_type=NotificationType.SYSTEM_ALERT,
    title="Reconciliation break",
    message="Ledger mismatch detected.",
    link="/admin/wallet/reconciliation",
)
```

`notify_roles()` de-duplicates users holding several matching roles and skips
inactive accounts.

## Lifecycle Coverage (Signals)

> **Status:** signals remain fully supported, but they are the **legacy
> in-process path**. Blinker signals vanish if the process dies — there is no
> durable record that `payment.successful` happened but was never processed.
> New code should call `emit_event(...)` (see Part 1) which is durable,
> replayable and traceable. Migrate existing signals incrementally.

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

## Development Fixtures (`mock_data.py`)

`app/notifications/mock_data.py` provides realistic fixtures for local dev and
tests, ported from the legacy `app/src/data/mockData.ts`. Two kinds:

1. **Domain fixtures (plain dicts only).** Users, wallets, events, registrations,
   properties, property bookings, vehicles, transport bookings, KYC submissions.
   These describe entities that already have real SQLAlchemy models elsewhere
   (`app.identity.models.user.User`, `app.wallet.models.transaction.TransactionModel`,
   `app.accommodation.models.*`, `app.events.models.*`, `app.transport.models.*`,
   `app.kyc.models.KycRecord`). They are **NOT** duplicated as models here — the
   dicts are reference data for building test contexts.
2. **Notification fixtures (mappable to real models).** Notification templates
   (seeded from `defaultTemplates`), preferences, notifications, and delivery
   logs.

### API
- `get_mock_data()` — returns a deep copy of every fixture group (dry run).
- `get_mock_user(identifier)` / `get_mock_wallet(user_id)` — look up domain fixtures.
- `render_mock_template(template_str, context)` — renders `{{ placeholder }}` tokens
  via the shared Jinja `Environment` (missing keys → empty string).
- `seed_mock_notification_data(db_session, user_id=..., include_templates=True,
  include_preferences=True, include_notifications=True, commit=True)` — persists
  notification templates/preferences/notifications/logs. With `db_session=None` it
  returns the raw dicts (dry run, nothing written).
- `clear_mock_notification_data(db_session, user_id=None)` — removes seeded rows.

### Example
```python
from app.notifications.mock_data import seed_mock_notification_data, clear_mock_notification_data

# Dry run (no DB writes) — just get the dicts
fixtures = seed_mock_notification_data()

# Persist realistic notification data for a real user
summary = seed_mock_notification_data(db_session, user_id=user.id)
print(summary)  # {'templates': 9, 'preferences': 8, 'notifications': 4, 'logs': 3, 'objects': {...}}

# Tear down
clear_mock_notification_data(db_session, user_id=user.id)
```

The module is exported from the package `__init__`:
`from app.notifications import seed_mock_notification_data`.

## Templates

Notification email templates live at `templates/notifications/email/`, named
**exactly after the `NotificationType` value** (e.g. `booking_confirmed.html`,
`payment_received.html`, `event_reminder.html`). There is **one template per
notification type (30/30 covered)**.

**Rendering (important):** `EmailHandler` renders templates through the Jinja
`Environment` exposed by `template_loader` (`template_loader.env.get_template(
"email/<type>.html").render(...)`), NOT `flask.render_template`. This is
deliberate — `flask.render_template` requires an active *request* context, which
is absent in standalone scripts, Celery tasks, and signal listeners, causing a
silent fallback to plain text. The `Environment` approach renders branded HTML
everywhere.

Rules:
1. If `email/<type>.html` exists, it is rendered with the context
   `title`, `message`, `notification`, `data`, `link`, `user_id`.
2. If it is missing, `email/default.html` (which renders `title`/`message`/`link`)
   is used as the generic branded fallback.
3. If both are missing (shouldn't happen — coverage is 100%), the plain-text
   `notification.body` is sent.

SMS/push templates (when used) live under `templates/notifications/sms/` and
`templates/notifications/push/`. `template_loader.py` resolves these paths
automatically; no per-module templates directory is used.

### Adding a template
When you add a `NotificationType`, also add `templates/notifications/email/<type>.html`.
Copy `default.html` and replace the `<h2>`/`<p>` copy. Keep the branded
`border-top: 5px solid #008751` header style for visual consistency.

## Migration Notes

Tables required by the delivery layer:
- `notification_templates` — Reusable notification templates
- `user_notification_preferences` — Per-user notification preferences
- `notification_logs` — Delivery attempt audit log (append-only)
- `notification_deliveries` — **(new)** Per-channel delivery state
- `communication_settings` — Provider/channel configuration (email/sms/push/webhook)
- `notification_aggregators` — External messaging gateways (Twilio, SendGrid, FCM, SAP, etc.)
- `messages` — Internal bidirectional messaging

Tables required by the event backbone:
- `domain_events` — **(new)** Durable event ledger
- `outbox_events` — **(new)** Transactional outbox
- `processed_events` — **(new)** Event-level idempotency
- `event_subscriptions` — **(new)** Partner event subscriptions
- `webhook_deliveries` — **(new)** Signed partner delivery attempts

Proposed migration commands (run manually — never auto-migrated):
```bash
flask db migrate -m "notification deliveries + event backbone (ledger, outbox, idempotency, subscriptions, webhook deliveries)"
flask db upgrade
```

---

# Architecture Decision Record (ADR) — Central Notification System

> **Audience:** the next engineer. This section explains *why* the notification
> subsystem is built the way it is and *how* to extend it without reintroducing
> duplicated email-sending code.

## 1. Centralized vs Decentralized — Decision: CENTRALIZED

AFCON360 uses a **single, centralized notification system**. Every module
(wallet, accommodation, transport, events, identity, KYC, admin, auth, messaging)
MUST route its outbound communication through `NotificationService` and the
pluggable channel handlers under `app/notifications/channel_handlers/`.

**Why not decentralized?** Decentralization would mean each module owning its own
SMTP client, template set, retry logic, and provider config. That causes:
- Duplicated Flask-Mail / `mail.send` code in 5+ places (we found and removed
  exactly this: `auth/otp_service.py`, `admin/owner/rate_limit_notifications.py`,
  `events/routes.py`, `events/tasks.py`, `notifications/integrations/__init__.py`,
  and a dead `_send_email` in `notifications/services.py`).
- Inconsistent delivery, retries, templating, and audit logging.
- No single place to enforce policy (preferences, external-vs-internal zone).

**The single email sender is `EmailHandler`** (`channel_handlers/email.py`).
It is the ONLY module that imports `flask_mail.Message` and calls `mail.send()`.
Grepping the codebase for `mail.send(` should return exactly one hit (in
`EmailHandler`). Every other sender delegates to it.

## 2. The "Two Zones" Model — Internal vs External

A core principle: **the platform is the source of truth for in-system messaging,
but users also live in the external world (Gmail, Yahoo, SMS, push).**

| Zone | Channel | Cost / Reach | Example |
|------|---------|-------------|---------|
| **Internal** | `in_app` | Free, persisted to DB inbox | Booking shows in user's AFCON360 inbox |
| **External** | `email`, `sms`, `push`, `webhook` | Hits a real provider | Same booking also lands in user's Gmail/Yahoo |

**Dual delivery is a first-class requirement.** When a user books a hotel (or
any confirmation flow), they receive the SAME message in BOTH their in-app inbox
AND their real external mailbox (Gmail/Yahoo/etc). This is enforced by the
delivery-zone policy below.

## 3. Delivery-Zone Policy (`NotificationService._resolve_delivery_zone`)

This is the brain that decides which channels actually fire. Rules, in order:

1. `in_app` is **always** honoured for a known internal user. A user always sees
   the message inside the system.
2. External channels (`email`/`sms`/`push`) fire for an internal user when ANY of:
   - the recipient is **external** (no `user_id`) — e.g. a signup/OTP email to an
     address that is not yet a user;
   - the user has **explicitly opted in** to that channel for that notification
     type (`UserNotificationPreference`);
   - the caller lists the external channel **alongside `in_app`** (dual-delivery
     intent), OR passes `force_external=True`.
3. `webhook` is treated as always-external (3rd-party subscriber integration).

**Result:** flows like booking/wallet/transaction confirmations that call
`NotificationService.send(..., channels=['email', 'in_app'], ...)` automatically
deliver to BOTH the in-app inbox and the user's real mailbox. Purely internal
chatter (e.g. an admin-only alert with no opt-in) stays in-app unless opted in.

### How to call it
```python
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
```

## 4. Single-Handler Routing — How It Was Implemented

Before this ADR, email was sent from at least six places. The consolidation:

| Before (duplicated) | After (single handler) |
|---------------------|------------------------|
| `auth/otp_service.send_email_otp` re-implemented Flask-Mail | delegates to `EmailHandler().deliver(...)` |
| `admin/owner/rate_limit_notifications._send_email` used `mail.send` | builds a transient `Notification`, calls `EmailHandler().deliver(...)` |
| `events/routes.py` used `mail.send` for organizer + confirmation | calls `EmailHandler().deliver(...)` with rendered HTML |
| `events/tasks.py` used `mail.send` for registration emails | calls `EmailHandler().deliver(...)` |
| `notifications/integrations._dispatch_email` used `mail.send` | calls `EmailHandler().deliver(...)` (preserves per-aggregator SMTP override) |
| `notifications/services._send_email` (dead) re-implemented Flask-Mail | now delegates to `EmailHandler` |

**`EmailHandler.deliver(notification, recipient)` contract** (DO NOT bypass it):
- `recipient` is a dict `{'email': ..., 'phone': ..., 'user_id': ...}`.
- Returns `{'success': bool, 'external_id': str, 'response_code': int, 'response_body': str}`.
- Renders `templates/notifications/email/<type>.html` via the Jinja `Environment`
  (NOT `flask.render_template`, which needs a request context). Falls back to
  `email/default.html` if the type template is missing; if even that is absent,
  sends the plain-text `notification.body`.
- Uses `flask_mail` + the configured `MAIL_*` env vars (Gmail SMTP today;
  SendGrid/Mailgun/SES via `NotificationAggregator` later).

## 5. Extension Guide (do NOT create new `mail.send` sites)

To add a new notification:
1. Add the `NotificationType` value in `models.py` (and its `CHECK` constraint
   entry) if it's a new type.
2. Add a template under `templates/notifications/email/` (optional but
   preferred) or rely on `body`.
3. Call `NotificationService.send(...)` from the originating module.
4. If you need to send email from a non-notification module (e.g. a one-off admin
   alert), construct a `Notification` and call `EmailHandler().deliver(...)`.
   **Never** import `flask_mail.Message` / `mail.send` directly.

To add a new channel (e.g. WhatsApp):
1. Subclass `BaseChannelHandler` in `channel_handlers/`, implement
   `validate_recipient` + `deliver`, register it in `EmailHandler`'s sibling
   `__init__.py` and in `NotificationService.HANDLERS`.
2. Add the channel to `NotificationChannel` and the relevant `CHECK` constraints.

## 6. Preferences, Audit, Retry

- **Preferences:** `PreferenceService.is_allowed(user_id, type, channels)` is the
  gate checked before delivery. Users opt in/out per type+channel.
- **Audit:** every delivery attempt writes a `NotificationLog` row
  (`notification_logs`) with `response_code`/`response_body`.
- **Retry:** `NotificationService.resend_failed()` + Celery `resend_failed_task`
  retry failed notifications with exponential backoff (see `utils.calculate_backoff`).
- **Aggregators:** `NotificationAggregator` registers external gateways with
  priority ordering; `integrations/__init__.py` routes each channel to the right
  client. Secrets are encrypted at rest.

## 7. Anti-Patterns (forbidden)

- ❌ Direct `from flask_mail import Message; mail.send(msg)` outside
  `channel_handlers/email.py`.
- ❌ Module-local SMTP/templating logic.
- ❌ Treating every internal event as an external email (use the delivery-zone
  policy instead).
- ✅ One entry point: `NotificationService.send`. One sender: `EmailHandler`.

## 8. Event Backbone Decisions (added in the latest milestone)

### 8.1 Backbone location — `app/notifications/events/`, NOT `app/events/`

`app/events/` is the AFCON **events business domain** (matches, tickets,
registrations, `events.expire_pending_registrations`). A second top-level
`app/events` would shadow it and break imports. Communication (events +
notifications) is a single platform capability, so the backbone is nested
inside the notifications package rather than scattered across the tree.

### 8.2 Facts vs communication — the load-bearing rule

Domain services publish facts via `emit_event`. They do **not** call
`send_email`, `send_sms`, or decide who should be told. The
`NotificationConsumer` + `PolicyEngine` own that decision. This is what stops
the notification service from accumulating a hardcoded `send_*()` method per
business domain forever.

### 8.3 Transactional outbox over direct publish

`emit_event()` deliberately **does not commit and does not touch Redis**. It
flushes the ledger + outbox rows into the caller's transaction. A relay worker
is the only publisher. This is the only way to make "DB write and event publish"
atomic without distributed transactions.

### 8.4 Two ledgers, never merged

`domain_events` answers *what happened*. `notification_logs` /
`notification_deliveries` answer *how we tried to tell someone*. A bounced email
must never rewrite the fact that a payment succeeded. Same reasoning drives the
two separate dead-letter queues.

### 8.5 At-least-once + idempotency, not exactly-once

Exactly-once delivery is not achievable across a network. Instead the backbone
guarantees at-least-once (Redis consumer groups + explicit `XACK`, outbox
retries) and makes duplicates harmless via `processed_events`. That is why
replay is safe.

### 8.6 Mandatory delivery class

Users may silence marketing, but not security alerts, payment receipts or legal
notices. `DeliveryClass.MANDATORY` bypasses the external opt-in requirement so
those always reach the real mailbox — encoded in policy, not scattered through
`if` statements.

### 8.7 Prefixed IDs, not UUIDs

`evt_`/`cor_`/`whd_` prefixes make an identifier self-describing in logs and in
partner payloads, which matters more for distributed tracing than UUID
formatting. These columns are registered in `BaseModel.NON_FK_STRING_IDS` so
`IDGuard` permits them.

### 8.8 Telemetry must never break business operations

`emit_event` catches everything and returns `None` on failure. A logging/eventing
problem must never roll back a real booking or payment. Same principle:
`app.notifications` still imports when the event tables are missing
(`_EVENTS_AVAILABLE = False`).

### 8.9 What is deliberately NOT built

Per the staged plan, Kafka, microservice extraction and a dedicated event
database are **out of scope**. PostgreSQL + Redis Streams + Celery are already
in the stack and are sufficient at this scale. `EventBus` is a narrow interface
so swapping in Kafka later is a single-file change.

## 9. Roadmap status against the original spec

| Priority | Capability | Status |
|----------|-----------|--------|
| 🔴 P0 | Canonical domain event model | ✅ `DomainEvent` + `EventEnvelope` |
| 🔴 P0 | Transactional outbox | ✅ `OutboxEvent` + `OutboxRelay` |
| 🔴 P0 | Durable event bus (Redis Streams) | ✅ `EventBus` (consumer groups, XACK, autoclaim) |
| 🔴 P0 | Event IDs / correlation / causation | ✅ `context.py` + contextvars + request middleware |
| 🔴 P0 | Event versioning | ✅ `event_version` + registry contracts |
| 🔴 P0 | Event-level idempotency | ✅ `ProcessedEvent` |
| 🔴 P0 | Ledger separate from notification logs | ✅ `domain_events` vs `notification_logs` |
| 🟠 P1 | Event consumers | ✅ notification / audit / analytics / webhook |
| 🟠 P1 | Event DLQ (separate from notification DLQ) | ✅ `/api/events/dead-letter` |
| 🟠 P1 | Event replay | ✅ `EventReplayer` (targeted + idempotency-aware) |
| 🟠 P1 | Notification Policy Engine | ✅ `policy.py` (audience, class, thresholds) |
| 🟠 P1 | Per-channel delivery records | ✅ `NotificationDelivery` |
| 🟠 P1 | Security events | ✅ 17 `security.*` event types registered |
| 🟠 P1 | Audit event ledger | ✅ `AuditConsumer` → `audit_logs` |
| 🟠 P1 | Observability / tracing | ✅ `/api/events/health`, `/trace/<id>`, health snapshot task |
| 🟡 P2 | External event subscriptions | ✅ `EventSubscription` + `/api/events/subscriptions` |
| 🟡 P2 | Signed webhooks | ✅ HMAC-SHA256, timestamp-bound, circuit breaker |
| 🟡 P2 | Advanced provider failover | ➖ Existing aggregator priority ordering retained |
| 🟡 P2 | Kafka | ➖ Intentionally deferred — not justified at current scale |

**Remaining operational step:** run the migration (see *Migration Notes*) to
create the six new tables and resolve the pre-existing `notifications.module`
drift.
