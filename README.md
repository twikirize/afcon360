# AFCON360 — Integrated Tournament Management Platform

**Repository status:** Active development · **Updated:** 2026-11-06

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
- [Emergency: Owner MFA Lost](#emergency-owner-mfa-lost)
- [Production database cutover and recovery](#production-database-cutover-and-recovery--25-october-2026)
- [Documentation](#documentation)
- [Adding or activating a database enum](#adding-or-activating-a-database-enum)
- [Database migrations — architecture, how to use, and why](#database-migrations--architecture-how-to-use-and-why)
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
- All timestamps are timezone-aware UTC, end to end: every `DateTime` column
  must be declared `DateTime(timezone=True)`, comparisons must use aware values
  (`datetime.now(timezone.utc)`, never naive `datetime.now()`/`utcnow()`), and
  conversion to a user's timezone happens only at the presentation edge. The
  TZ-UNIFY chain (`c4b306c2ed73` → `fc87cdbd0e6a`) converted all legacy naive
  columns; those legacy values were `Africa/Nairobi` wall-clock, so never
  re-interpret them with new `AT TIME ZONE 'UTC'` conversions. See AGENTS.md §51.
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

## Emergency: Owner MFA Lost

> **Break-glass procedure — authorized operator use only.** Use this only when the Owner has lost the authenticator device and has no usable MFA recovery codes, and the supported account-recovery path is unavailable. This temporarily removes the Owner's registered MFA factors. It is not a routine login workaround.

Keep the global Owner MFA requirement enabled. Do not disable `REQUIRE_OWNER_MFA`, weaken the global security policy, reset the Owner's password, or clear account lockout fields as part of this procedure.

Before starting:

- Confirm that you are authorized to administer the production host and database. Record an incident/change reference and the reason for the emergency reset. Have a second authorized operator independently verify the target account and database when available.
- Confirm the normal app recovery options are unavailable. A still-valid backup code should be used through the supported login and authenticator-replacement flow instead of this database procedure.
- Confirm the production database and Docker container names. Do not run these commands against a local, test, restore-verification, or candidate database.

### 1. Create and check a protected database backup

Run on Server 1. This writes the archive outside the Git repository, restricts its file permissions, and checks that PostgreSQL can read the archive's table of contents:

```bash
sudo bash -euo pipefail -c '
umask 077
BACKUP_DIR=/opt/afcon360/backups
mkdir -p "$BACKUP_DIR"
BACKUP="$BACKUP_DIR/mfa_reset_$(date +%Y%m%d_%H%M%S).dump"
docker exec afcon360_db pg_dump -U afcon_prod -d afcon360_prod -Fc > "$BACKUP"
test -s "$BACKUP"
docker exec -i afcon360_db pg_restore -l < "$BACKUP" >/dev/null
printf "Readable MFA recovery archive: %s\n" "$BACKUP"
'
```

Do not continue unless the command exits successfully and prints the archive path. Keep the backup access-restricted and outside source control. `pg_restore -l` proves that the archive header and table-of-contents can be read; it is **not** a full restore test.

### 2. Inspect and positively identify the Owner account (read-only)

```bash
docker exec afcon360_db psql -X -v ON_ERROR_STOP=1 -U afcon_prod -d afcon360_prod -c "
SELECT current_database() AS database_name, current_user AS database_role;
SELECT id, username, mfa_enabled, failed_logins, locked_until
FROM users
WHERE id = 1;
"
```

Proceed only when:

- The database reported is exactly `afcon360_prod`.
- Exactly one user row is returned.
- The username and Owner role match the account whose MFA must be recovered.
- The row's internal `users.id` has been independently confirmed.

**The value `1` is the example target from this runbook, not a universal Owner ID.** If the verified Owner has a different internal ID, replace `1` with that confirmed ID in both statements in Step 3. Do not select an account merely because its ID is 1. If the identity or role is uncertain, stop.

Also inspect `failed_logins` and `locked_until`. This MFA procedure does not clear a password lockout or change the password; resolve any separate lockout through its approved process.

### 3. Clear the verified Owner's MFA factors

Only after the backup and identity checks pass, run the transaction below. Replace `1` in both places only if Step 2 proved a different internal Owner ID:

```bash
docker exec -i afcon360_db psql -X -v ON_ERROR_STOP=1 -U afcon_prod -d afcon360_prod <<'SQL'
BEGIN;
UPDATE users
SET mfa_enabled = false
WHERE id = 1
RETURNING id, mfa_enabled;

DELETE FROM mfa_secrets
WHERE user_id = 1;
COMMIT;
SQL
```

The delete removes the registered MFA factor records for that user, including the stored authenticator secret and backup codes. Confirm that the `UPDATE` returned the verified Owner row and review the `DELETE` row count. If the transaction reports an error or the output does not match the expected target, stop and investigate; do not repeat it blindly.

Direct SQL bypasses the application's MFA audit helper. Record the operator, approver (if available), UTC time, incident reference, verified database and account, backup filename, and affected row counts in the protected incident record. Never put passwords, TOTP secrets, or recovery codes in that record.

### 4. Sign in through a clean browser session

Open a private/incognito browser window and sign in with the Owner's existing password. Complete only the MFA re-enrolment flow. When the global Owner MFA requirement is enabled, the application may direct the Owner to the restricted MFA setup page before allowing normal access; complete that setup rather than weakening the global policy.

### 5. Re-enrol and verify MFA immediately

1. Register the new authenticator device through the application's MFA setup page.
2. Confirm the new authenticator with a current code; do not stop at merely displaying a QR code or secret.
3. Generate new recovery codes and store them in two separate, approved secure locations (for example, a password manager and an offline protected copy). Do not store them in email, chat, source control, or this README.
4. Sign out and perform a fresh login using the new authenticator code.
5. Confirm the Owner account reports MFA enabled and the application accepts the new factor. Record the successful verification in the incident record.

Do not leave the Owner account in a password-only state. If re-enrolment or verification fails, stop normal Owner work and continue through the approved incident-recovery process.

---

## Production Database Cutover and Recovery — 25 October 2026

Production was cut over to a new PostgreSQL database on 25 October 2026. This
section is the operational record: which database is production, where the
recovery archives are stored, what has been verified, and how to approach a
rollback. It is documentation only — it does not authorize a cutover, rollback,
migration, restore, or any other database operation.

### Current production database

| Item | Value |
|---|---|
| Database | `afcon360_prod` |
| Alembic revision | `1793013676` |
| Users | 109 |
| Transport bookings | 61 |
| Post-cutover checks | Confirmed the database name, revision, user count, booking count, and the presence of `ck_pickup_time_sane` |

M3 (26 October 2026) corrected and validated `ck_pickup_time_mode_aware`; production is at `1793013676`.

### Preserved previous production database (rollback resource)

| Item | Value |
|---|---|
| Database | `afcon360_prod_old` |
| Alembic revision | `df55cbe3f516` |
| Pre-rename checks | 109 users and 61 bookings |

This database is preserved as the rollback resource. It must not be dropped,
overwritten, upgraded, or repurposed.

### Other candidate databases

- `afcon360_h3_candidate_cutover_test` — the old Gate 4 candidate. It contains
  **test data** and must never be promoted to production.
- The clean candidate was upgraded and populated **before** it was renamed to
  `afcon360_prod`. The old Gate 4 candidate was not the source of the final
  promotion.

### Backup locations

Both archives are stored **outside the Git repository**, under the recorded
Windows development environment. These are machine-specific paths: they are not
portable and are not guaranteed to exist on another computer.

**Pre-cutover production backup**

```text
C:\Users\OBED\AppData\Local\AFCON360\rebuild-evidence\afcon360_prod_pre_cutover_20261025_160251.dump
```

- Created before the cutover on 25 October 2026.
- Size: 1,670,399 bytes.
- Previously reported as restore-verified.
- Treat this as the pre-cutover recovery archive.

**Post-cutover production backup**

```text
C:\Users\OBED\AppData\Local\AFCON360\rebuild-evidence\post_cutover_20261025_201202\afcon360_prod_post_cutover_20261025_201202.dump
```

- Created on 25 October 2026 at approximately 20:12.
- Size: 1,664,542 bytes; custom-format PostgreSQL archive.
- `pg_restore -l` successfully read its metadata and table-of-contents entries,
  so the archive is **readable**.
- A complete restore test has **not** yet been demonstrated.

Archive readability is not the same as successful restoration. The post-cutover
archive must not be described as restore-verified until a full restore has been
demonstrated.

### Verification status

Verified:

- Current database name, Alembic revision, user count, booking count, and
  `ck_pickup_time_sane` in `afcon360_prod` after cutover.
- Pre-rename user and booking counts recorded for `afcon360_prod_old`.
- Both archive files present at the paths above, with the recorded sizes.
- Post-cutover archive table of contents readable via `pg_restore -l`.

Still outstanding:

- A complete restore test of the post-cutover archive has not been demonstrated.
- No rollback rehearsal has been recorded against `afcon360_prod_old`.

### Rollback runbook — incident procedure, operator approval required

This is **not** an instruction to execute now. Rollback is an explicitly
authorized operational procedure: it requires a declared incident, approval from
the responsible operator, and satisfied precondition checks. Do not attempt a
rollback solely because of an unverified warning or a superficial mismatch —
investigate first and retain evidence.

1. Declare an incident and obtain approval from the responsible operator.
2. Stop the application and relevant background workers before switching
   databases.
3. Investigate whether any user transactions occurred after cutover. Preserve
   and reconcile those transactions before rolling back, so a rollback does not
   silently discard newer bookings or other writes.
4. Confirm the current database names, revisions, connectivity, and available
   backup files using read-only checks.
5. Preserve the new production-named database for investigation. If it must be
   renamed, select and verify an unused destination name first; never drop it as
   part of rollback.
6. Rename the preserved old production database back to `afcon360_prod` only
   after checking connection and naming conflicts.
7. Update the application's database configuration without exposing or
   documenting passwords. Treat `.env.local.pre_cutover` only as a
   configuration snapshot and re-check its database name before any rollback
   use.
8. Restart the application and verify the actual SQL connection, revision,
   essential record counts, login, My Trips, and relevant booking functionality.
9. Record the incident, decision, verification evidence, and any reconciled
   post-cutover transactions.

### Secrets and backup hygiene

- Never place database passwords, credential-bearing connection strings, or
  secret values in this README, the agent instructions, or the constitution.
- Do not copy database dump files into the repository, and never commit
  `.env.local`, `.env.local.pre_cutover`, or backup archives.

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

## Adding or activating a database enum

All PostgreSQL enum types are defined in **`app/utils/enums.py`** — this is the
single source of truth. Models import from there; nothing else defines enums.

### Three categories

1. **Category A — Real PG enum types** (managed here)
   - Defined as `PgEnum(..., name='pg_type_name', create_type=False)`
   - Corresponds to a real `CREATE TYPE` in PostgreSQL
   - **Action**: add to `app/utils/enums.py` ACTIVE section, import in model

2. **Category B — Python-only enums with CHECK constraints** (catalogued only)
   - Defined as `class Foo(str, Enum)` + `db.Column(String) + CheckConstraint`
   - **NO PG type exists** — converting requires schema migration
   - **Action**: leave in model; catalogue in `app/utils/enums.py` PLANNED section

3. **Category C — SQLEnum(PyEnum) with implicit PG name** (managed here)
   - `sqlalchemy.Enum(SomePyEnum)` without explicit `name=`
   - SQLAlchemy auto-creates PG type named after Python class (lowercased)
   - **Action**: verify actual PG name via `SELECT typname FROM pg_type...`,
     then add to ACTIVE section with explicit `name='...'`

### Workflow to add a NEW enum

There are two separate schema paths. Neither path is run as part of
Phase 1 source corrections.

**Path A — Alembic** (`flask db migrate -m "..."`) covers applicable
schema changes such as columns, types, indexes and foreign keys. Do not
assume Alembic autogenerate creates the CHECK constraints managed by the
sync tool (it does not reliably render them).

**Path B — CHECK synchronization**
(`python scripts/sync_check_constraints.py --accept-model-truth`)
synchronizes model-declared CHECK constraints. Only constraints whose name
begins with the tool's `MANAGED_PREFIX = "ck_"` are managed: unnamed
constraints and names with any other prefix are ignored by the tool. Every
model-declared CHECK constraint must therefore carry an explicit `ck_*`
name. The tool generates a migration file; it never applies one.

1. Decide category (A, B, or C — see above).
2. For new enum-like columns, use `String` + a named (`ck_*`) CHECK
   constraint by default (see `app/utils/enums.py` helpers).
3. For Path A changes, run `flask db migrate`, inspect the generated
   migration, then upgrade only after review.
4. For Path B changes, run the sync tool to generate the migration,
   review it, then upgrade only after review.

### Workflow to ACTIVATE a catalogued enum (DB hardening)

Enums marked `[PLANNED]` in `app/utils/enums.py` are catalogued but not yet
managed. To activate one:

1. Verify current PG type name via psql:
   ```sql
   SELECT typname FROM pg_type WHERE typname = 'your_enum_name';
   ```
2. Move definition from PLANNED section to its module's ACTIVE section.
   Preserve `name=` exactly.
3. Refactor model to import from `app.utils.enums`.
4. If new tables/columns were added, follow Path A; if CHECK constraints
   were added or changed, follow Path B. Review every generated migration
   before upgrading.
5. Commit module-by-module. Never batch-activate more than one module at a time.

### Enum policy

- Use String + named CHECK constraints for new enum-like columns by
  default.
- Preserve verified existing native PostgreSQL ENUM mappings as explicit
  legacy exceptions. Existing native PG ENUM columns do not need CHECK
  constraints merely because they represent enum-like values, and the CHECK
  sync tool applies to the String + CHECK pattern, not automatically to
  every enum-like column.
- Any legacy conversion is deferred to the separately authorized
enum-reconciliation roadmap.

### Current activation status (2026-10-11)

- **ACTIVE (Phase 0 — Transport)**: `ServiceType`, `BookingStatus`,
  `ComplianceStatus`, `PaymentStatus`, `VehicleClass`, `IncidentSeverity`,
  `Currency`, `ProviderType`, `VerificationTier`, `CompensationModel`,
  `ContractStatus`
- **PLANNED Category A/C**: Profile (4), Wallet (4), Events (1), Identity (16),
  Admin Compliance (6), Accommodation (12+), Audit (4)
- **CATALOGUED Category B**: Notifications (4), Audit (4), Events (4),
  Accommodation (20+), Profile (if any), Wallet (if any)

## Database migrations — architecture, time rules, and how to use

AFCON360 uses one consolidated V1 baseline followed by ordinary incremental Alembic migrations. New installations do not replay the retired H3-A migration history.

### The architecture

- **V1 baseline:** revision `h3b20261104`, file `migrations/versions/h3b20261104_consolidated_baseline.py`.
- **V1 is frozen explicit DDL:** it is reviewable static schema, not a runtime import of models and not `metadata.create_all()`.
- **Historical H3-A chain:** preserved under `migrations/_preserved_h3a_chain_20261104/versions/` for reference. It is not the active chain for fresh installs or new work.
- **V2 and later:** ordinary incremental Alembic revisions generated from the canonical SQLAlchemy model/source after review.
- **Verified V1 clean install (PostgreSQL 15.19):** 228 application tables, 49 enums, 0 naive timestamp columns, 993 timezone-aware timestamp columns, database timezone `UTC`.

A revision number alone does not prove schema parity. Verify the actual database catalog and target identity.

### Permanent timestamp rule: UTC

**UTC is AFCON360's permanent database and application storage standard. Africa/Nairobi is not the permanent database timezone.**

- All timestamp columns use timezone-aware types (`DateTime(timezone=True)` / PostgreSQL `TIMESTAMPTZ`).
- Store and compare aware UTC instants. Use `datetime.now(timezone.utc)`; never create naive application timestamps with `datetime.now()` or `datetime.utcnow()`.
- The tracked Docker Compose PostgreSQL service starts with `postgres -c timezone=UTC`, so fresh database sessions default to UTC on both the primary and production resource-overlay Compose configurations.
- `app/config.py` passes `-c timezone=UTC` to PostgreSQL for every SQLAlchemy connection. The Flask engine also checks each new PostgreSQL connection and fails closed if it is not UTC.
- Online Alembic migration/autogeneration connections independently assert UTC before schema inspection or migration work. This means `flask db migrate`, `flask db check` and `flask db upgrade` use the same enforced application engine; no timezone migration is needed.
- Standalone `psql`/libpq clients do not use the Flask engine options. They inherit the PostgreSQL server/database default; use `PGTZ=UTC` as an explicit client override when operating against a server whose UTC default has not yet been verified.
- Convert to a user's local timezone only at the presentation/scheduling boundary. Do not shift stored instants to local wall time.
- A naive external timestamp is not automatically UTC unless its input contract explicitly says so. Establish its source timezone before converting it to an aware UTC instant.

### Why historical conversion used Africa/Nairobi

The legacy application wrote aware UTC values into PostgreSQL columns that did not retain timezone information. The PostgreSQL session timezone was Africa/Nairobi, so PostgreSQL first represented the incoming instant as Nairobi wall time and then the naive column discarded the timezone.

For example, historical naive `15:00` with proven Nairobi provenance means:

- `15:00 Africa/Nairobi` (UTC+3)
- `12:00 UTC` (same real-world instant)

Interpreting that old `15:00` as UTC would move the event three hours later. The old TZ-UNIFY revisions therefore ran their plain `ALTER COLUMN TYPE TIMESTAMPTZ` conversions with `PGTZ=Africa/Nairobi`. That was a narrowly scoped historical data-interpretation requirement, not the desired permanent database setting.

**Do not use `PGTZ=Africa/Nairobi` for ordinary current migrations, application operation, or V1 installation.** The old TZ-UNIFY files are preserved historical source, not the active V1 chain.

### How to handle timestamps during a future migration

1. **No legacy naive data conversion:** keep the migration session at UTC. Use timezone-aware model/database types. Do not add a timezone conversion just because a migration touches a timestamp-related table.
2. **Legacy naive data must be converted:** identify the exact columns and prove their source timezone from migration history, writer code, logs or a controlled temporary-table probe. The database's current timezone does not establish the historical timezone.
3. **Known Nairobi wall time:** explicitly interpret the source as Nairobi time (for example, PostgreSQL `legacy_timestamp AT TIME ZONE 'Africa/Nairobi'`) while the destination database/session remains UTC. This produces a `TIMESTAMPTZ` instant.
4. **Different or mixed provenance:** use the proven IANA timezone per source. If provenance is unknown or mixed and cannot be separated, stop and report BLOCKED; do not guess or apply a blanket conversion.
5. **Already-aware source values:** preserve their existing instants. Do not shift them merely to change the displayed clock value.
6. **Before any authorized production operation:** rehearse on an isolated PostgreSQL clone; compare row counts, nulls and representative before/after instants; verify zero naive timestamp columns and UTC session timezone. Obtain the required human approval before any production migration or data change.

Never apply `AT TIME ZONE 'UTC'` to a value proven to be Nairobi wall time. That would treat the Nairobi clock reading as UTC and shift the actual instant by three hours.

**Important safeguard for legacy production transitions:** this Nairobi interpretation is not a blanket rule for every naive column in every historical database. Audit each source column against its writer code, migration history and applicable time period. A retired database's current `SHOW TimeZone` value does not establish how its naive values were originally written. Classify every source as proven Nairobi wall time, proven another IANA timezone, already-aware, or unknown/mixed. Unknown or mixed provenance is BLOCKED; do not guess or apply a database-wide conversion.

For a column proven to contain Nairobi wall time, make the interpretation explicit in the migration while the migration session remains UTC:

```sql
ALTER TABLE example
  ALTER COLUMN legacy_time TYPE TIMESTAMPTZ
  USING legacy_time AT TIME ZONE 'Africa/Nairobi';
```

This expression interprets the naive wall-clock value as Nairobi local time and produces the corresponding absolute instant. Use the proven IANA zone for other source data. Preserve already-aware values without shifting them. Do not set a new migration session to `Africa/Nairobi`; the old session-level setting belongs only to controlled reproduction of the preserved historical TZ-UNIFY chain, not new V1/V2+ migrations. Any data conversion requires a human-approved contract and an isolated rehearsal before production.

### How to use Alembic

```powershell
# Use the project's intended environment and an isolated PostgreSQL *_test database.
$env:APP_ENV = 'testing'
$env:FLASK_ENV = 'testing'
# Flask/SQLAlchemy and Alembic connections enforce UTC in source code.
# Set PGTZ=UTC only when a standalone psql/libpq command needs an explicit client override.

# Inspect the active chain and the actual connected database.
python -m flask db heads       # expect one active head
python -m flask db current     # verify the target revision
python -m flask db history     # inspect active history, not preserved archives
python -m flask db check       # models vs this database

# Ordinary schema change: agent proposes; owner reviews and runs.
# 1. Correct the canonical model/source.
# 2. Owner generates the migration:
python -m flask db migrate -m "description"

# 3. Review the generated file: all intended changes, no unrelated changes.
#    If autogeneration is incomplete, fix the source and regenerate.
#    Never hand-patch the generated migration.
# 4. After review and authorization, owner applies it:
python -m flask db upgrade

# Confirm the migration/application engine connection is still using UTC:
python -c "from app import create_app; from app.extensions import db; app=create_app(); ctx=app.app_context(); ctx.push(); conn=db.engine.connect(); print(conn.exec_driver_sql('SHOW TimeZone').scalar_one()); conn.close(); db.engine.dispose(); ctx.pop()"
```

Do not copy the illustrative connection probe into production without first confirming the application's configured target. Never expose credentials in commands or output.

### Fresh-install proof

For a migration release, use a disposable empty PostgreSQL database: install the V1 baseline, apply each approved incremental revision, verify one active head, run `flask db check`, and compare schema/catalog counts. For timestamp changes, record naive/aware column counts and prove that the actual instants are preserved. The verified V1 starting point is **0 naive / 993 aware**; intentional new timestamp columns must also be timezone-aware.

## Socket.IO Async Mode Decision

**Decision:** `threading` (default, enforced via `SOCKETIO_ASYNC_MODE` env var)

**Reasoning:**
- AFCON360 is a synchronous codebase; no monkey-patching is performed
- `gevent`/`eventlet` require monkey-patching `socket` for Redis message queue to work
- Without monkey-patching, `socketio.redis_manager.RedisManager.initialize()` raises `RuntimeError` and every `/socket.io/` connect returns 401
- Silent failures under load: cross-worker push never arrives (measured 58 ms local vs absent after 42 s cross-worker)

**Enforcement:** `app/extensions.py` reads `SOCKETIO_ASYNC_MODE` (default `threading`); `app.py` no longer passes `async_mode` to `build_ssl_context()`

**Migration path to gevent (four preconditions):**
1. Explicit owner authorization for monkey-patching
2. Verified gevent + Redis queue cross-worker delivery test (automated)
3. Gunicorn worker config aligned (sync vs gevent workers)
4. Connection ceiling monitoring in place

**Ceiling:** ~300–500 concurrent connections on `threading`

**Why not gevent:** Silent cross-worker push failures under load; no monkey-patching policy

---

## Known limitations

This is an active codebase, not a claim of production readiness. In particular,
`BACKLOG.md` records accommodation/KYC test-database drift, pending compliance
review of mid-stay cancellation policy, a notification check-constraint update,
backup migration follow-up, and planned read-replica/background-processing work.
Review those entries before release or operational changes.

## License

Proprietary — AFCON360 Platform.
