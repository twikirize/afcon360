# AFCON360 — Integrated Tournament Management Platform

**Repository status:** Active development · **Updated:** 2026-08-14

AFCON360 is a modular Flask platform for tournament operations, accommodation,
transport, events, identity/KYC, wallet transactions, notifications, media, and
administration. This README describes the repository as it exists today; it is
not a promise that every integration or production deployment is enabled in
every environment.

## Contents

- [Architecture](#architecture)
- [Modules](#modules)
- [Important invariants](#important-invariants)
- [Technology](#technology)
- [Local setup](#local-setup)
- [Running services](#running-services)
- [Testing and verification](#testing-and-verification)
- [Configuration](#configuration)
- [Documentation](#documentation)
- [Known limitations](#known-limitations)

## Architecture

The application uses Flask's application-factory pattern in `app/__init__.py`.
Blueprints are registered centrally while domain code remains grouped by
module. SQLAlchemy/Flask-Migrate manage persistence and Redis is used for
caching, sessions, rate limiting, and Celery transport where configured.

```text
Browser / API clients
        |
        v
Flask application factory
        |
        +-- Auth, identity, profile, KYC, RBAC
        +-- Events, accommodation, event accommodation, transport, tourism
        +-- Wallet APIs, payments, ledger, reconciliation
        +-- Notifications and domain-event backbone
        +-- Media, audit, compliance, admin, dashboards
        |
        +-- PostgreSQL (all application and test configurations)
        +-- Redis -> Celery workers and scheduled tasks
```

### Seamless cross-module guest experience

AFCON360 is intentionally modular: each domain remains independently usable,
with its own routes, services, data ownership, and operational rules. The
modules also compose through shared identity, event context, booking
references, notifications, and wallet/payment references, so a guest should
not need to log out or create a separate account when moving between services.

An event owner can use the event's attendee/guest context to coordinate the
connected experience: identify registered guests, arrange accommodation or
transport through the relevant module, and assign guests to rooms, properties,
vehicles, routes, or other approved travel arrangements. The event module
owns the event and attendee relationship; accommodation owns availability,
reservations, rooms, and stay assignments; transport owns journeys, vehicles,
drivers, and movement assignments; and wallet owns payment and ledger state.
These boundaries must remain explicit even when the user journey feels like a
single workflow.

The intended flow is:

1. An event owner views authorized event attendees using public identifiers and
   the event's access-control rules.
2. The owner initiates or links accommodation and transport arrangements for
   those guests through the appropriate domain workflows.
3. The accommodation module confirms availability and records where each guest
   will stay; the transport module records how each guest will move.
4. Payment requests use the wallet/payment integration without allowing event,
   accommodation, or transport code to create a competing ledger.
5. Notifications and dashboards present the resulting itinerary and status in
   one authenticated experience.

Cross-module implementations must preserve ownership, authorization,
idempotency, auditability, and failure isolation. A module must continue to
function when an optional integration is unavailable, and partial failures
must not silently create an accommodation, transport, or payment assignment.
Consult the relevant module specification before changing these contracts,
especially `app/accommodation/AFCON360_SEAMLESS_BOOKING_SPEC.md` for booking,
guest-roster, payment, and event-assignment behavior.

The formal Event Host guest-coordination contract is documented in
`app/events/events.md`. It defines the assignment state transitions,
event-scoped authority, public-reference API contract, capacity/eligibility
invariants, and controlled behavior when Accommodation or Transport is disabled.

### Financial ownership

The wallet is the canonical owner of money movement. Domain modules keep
context and references such as `wallet_txn_id` or
`wallet_transaction_id`; they must not create competing ledgers. Wallet changes
are high risk and must preserve double-entry, idempotency, rollback, and audit
requirements.

### Identity separation

Internal database IDs (`id`) are for foreign keys and joins only. Public URLs,
API responses, and sessions use `public_id`. Never expose a user's internal
numeric ID.

## Modules

| Module | Responsibility |
|---|---|
| `app/auth` | Login, registration, OTP, onboarding, sessions, password policy |
| `app/identity` | Users, organizations, roles, permissions, KYB and identity records |
| `app/profile` | User profile and verification-facing profile workflows |
| `app/kyc` | KYC tiers, documents, NIRA verification, upgrade workflows |
| `app/events` | Event lifecycle, registrations, ticketing, assignments, metrics |
| `app/accommodation` | Properties, rooms, availability, bookings, guest registration and reviews |
| `app/event_accommodation` | Event-linked accommodation and trust/discovery flows |
| `app/transport` | Drivers, vehicles, routes, incidents, bookings and analytics APIs |
| `app/wallet` | Accounts, transactions, ledger, payments, webhooks, FX, payouts and reconciliation |
| `app/notifications` | Email, SMS, push, in-app and webhook delivery plus event policies/outbox processing |
| `app/media` | Upload validation, local/OCI storage, media administration and processing tasks |
| `app/admin` | Owner/admin dashboards, moderation, support, compliance, settings and backups |
| `app/audit` / `app/compliance` | Forensic audit trails, risk and regulatory workflows |
| `app/tourism` / `app/tournament` | Tourism services and tournament scheduling/brackets |
| `app/fan` / `app/user` / `app/dashboard` | Fan, user and role-specific dashboard experiences |

Phone verification defaults to the account email as an OTP transport and can be
switched by the owner to a configured SMS provider from Authentication Settings.
The state machine, delivery boundary, and security invariants are defined in
`app/Documentation/AUTH_SYSTEM_ARCHITECTURE.md` under
“Temporary phone-verification transport contract”.

## Important invariants

- All new models inherit from `app.models.base.BaseModel` or an approved
  protected variant; do not change shared base classes without approval.
- Use `BigInteger` internal foreign keys and UUID/string public identifiers.
- Do not add PostgreSQL enum types; use validated strings and constraints.
- Preserve soft-delete filtering and audit sensitive actions.
- Preserve module guards on gated routes.
- Booking identity data may be completed after checkout; consult
  `app/accommodation/AFCON360_SEAMLESS_BOOKING_SPEC.md` before changing that flow.
- Every wallet operation requires idempotency and balanced ledger entries.
- Frontend behavior must comply with the CSP nonce policy; prefer external
  JavaScript modules over inline handlers/scripts.
- An active organisation context lands in that organisation's public workspace;
  the workspace can show its organisation-owned events, properties, and
  accommodation bookings without changing the user's identity or granting new
  permissions. The workspace presents the selected organisation role as the
  authority for its Operations and Bookings areas. See
  `app/Documentation/UNIFIED_IDENTITY_CONTEXT_SPEC.md`.

## Technology

- Python 3.10+; Flask 3.1.2; SQLAlchemy 2.0.44
- PostgreSQL is the only supported application and test database backend
- Alembic/Flask-Migrate for schema management
- Redis 7.x for cache, sessions, rate limits and Celery broker/backend
- Celery 5.4.0 for webhook, media, notification, accommodation and backup jobs
- Flask-Login, Flask-WTF/CSRF, Flask-Limiter, Argon2/passlib and Pydantic
- Bootstrap 5 with custom responsive CSS and Jinja templates
- Gunicorn and Docker Compose for Linux/container deployments
- Pytest and pytest-flask for automated tests

## Local setup

### Prerequisites

- Python 3.10 or newer
- PostgreSQL when using the PostgreSQL configuration
- Redis for sessions, rate limiting and background work, unless deliberately
  disabled for a limited local run

### Windows PowerShell

```powershell
py -3 -m venv .venv
& .venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item env.example .env
```

Fill in `.env` with real local values. Do not commit secrets. The application
supports layered environment files: `.env` plus `.env.local`, `.env.docker`, or
`.env.prod`, selected by `APP_ENV`.

Database migrations are intentionally not run automatically by agents. After
reviewing the migration state, an operator may run:

```powershell
$env:APP_ENV = "testing"
$env:FLASK_ENV = "testing"
& .venv\Scripts\python.exe -m flask --app 'app:create_app()' db current
& .venv\Scripts\python.exe -m flask --app 'app:create_app()' db heads
& .venv\Scripts\python.exe -m flask --app 'app:create_app()' db upgrade
```

Using the explicit factory keeps migration commands on the same dedicated
PostgreSQL test database selected by `TestingConfig`; agents and tests never
apply migrations automatically.

Use `flask db migrate` only as an explicitly reviewed developer operation, never
as an unattended workaround.

## Running services

### Flask development server

```powershell
$env:APP_ENV = "local"
$env:FLASK_ENV = "development"
flask run
```

The application entry points are the factory in `app.create_app` and the
repository's `app.py` launcher. Confirm the actual configured entry point when
using a custom environment.

### Celery

```powershell
celery -A app.celery_app worker --loglevel=info
celery -A app.celery_app beat --loglevel=info
```

On Windows the worker defaults to a threads pool; Linux defaults to prefork.
Override with `CELERY_WORKER_POOL` and `CELERY_WORKER_CONCURRENCY` when needed.
Running worker and beat together is for development only.

### Docker Compose

The current `docker-compose.yml` defines PostgreSQL 15, Redis 7, the Gunicorn
web service, Celery worker/beat services, and Nginx-related deployment support.
Use the non-destructive commands below after supplying the required environment
values:

```powershell
docker compose up -d
docker compose ps
docker compose logs -f web
```

Do not use `docker compose down -v` unless you intentionally want to remove
database and Redis volumes.

## Testing and verification

Run the relevant suite first, then broaden validation as appropriate:

Tests must run against a dedicated, migrated PostgreSQL database. SQLite,
embedded database fallbacks, raw SQL strings, and test-time schema creation or
repair are not supported. Set `TEST_DATABASE_URL` before running pytest; the
shared fixture fails fast if PostgreSQL is unavailable or the schema is stale.
The full contract is documented in `docs/POSTGRES_TESTING_CONTRACT.md`.
Direct SQL tests are not supported; use SQLAlchemy expressions to exercise
PostgreSQL behavior. Only source/parser/configuration checks may be database-free.

```powershell
pytest
pytest tests\notifications
pytest tests\test_accommodation_checkout_processes.py
```

For the project database verification script:

```powershell
& .venv\Scripts\python.exe verify_db.py
```

Success requires exit code `0` and `DB_VERIFY_OK`. Existing test infrastructure
and database-schema drift are tracked in `BACKLOG.md`; a failing test must not
be hidden with skip flags or weakened assertions.

Health endpoint: `GET /api/health/ping`.

## Configuration

Start from `env.example`. Common settings include:

- `APP_ENV`, `FLASK_ENV`, `DEBUG`, `LOG_LEVEL`
- `SECRET_KEY`, `ENCRYPTION_KEY`, `MFA_ENCRYPTION_KEY`
- `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASS`, `DATABASE_URL`
- `REDIS_URL`, `DISABLE_REDIS`, Celery broker/result settings
- Mail, SMS, payment-provider, S3/OCI, backup, monitoring and compliance keys
- `WALLET_ENABLED`, transaction limits, `AML_ENABLED`, `KYC_REQUIRED`, and
  `TRAVEL_RULE_ENABLED`

Use environment-specific files for deployment overrides. Never place provider
secrets, production passwords, or private keys in source control.

## Documentation

- `AGENTS.md` — authoritative engineering constraints for contributors/agents
- `DATABASE_SCALABILITY_ROADMAP.md` — schema and database scalability policy
- `app/Documentation/IDENTITY_POLICIES.md` — public/internal ID rules
- `app/Documentation/UNIFIED_IDENTITY_CONTEXT_SPEC.md` — unified identity and operating-context contract
- `app/Documentation/SYSTEM_OVERVIEW.md` — deeper system reference
- `app/accommodation/AFCON360_SEAMLESS_BOOKING_SPEC.md` — booking contract
- `static/MOBILE_OPTIMIZATION.md` — responsive UI change record
- `BACKLOG.md` — identified deferred, blocked and review-required work
- `Readme's/` and `docs/` — implementation reports and supporting documentation

## Known limitations

This is an active codebase, not a claim of production readiness. In particular,
`BACKLOG.md` records accommodation/KYC test-database drift, pending compliance
review of mid-stay cancellation policy, a notification check-constraint update,
backup migration follow-up, and planned read-replica/background-processing work.
Review those entries before release or operational changes.

## License

Proprietary — AFCON360 Platform.
