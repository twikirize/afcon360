# AFCON360 — Deferred Work Backlog

**Purpose:** A single source of truth for work that is **identified but NOT completed in the current session** yet still needs to live in the system. Any agent (Code/Ask/Debug mode) must record such items here so they are not lost between sessions.

**Rule (mandatory for all agents):** If you identify, discuss, or partially implement something that cannot/should not be finished today (blocked, out of scope, needs review, needs migration, needs another team's sign-off, etc.), create an entry below before ending your turn. Do not let deferred work disappear into chat history.

**Entry format:**
```
## <Short Title>
- Status: Not started | Partial | Blocked | Needs review
- Raised: <YYYY-MM-DD>
- Context: <why it matters / what was discussed>
- What needs to happen: <concrete next steps>
- Owner/area: <module or team>
- Links: <related files, routes, models, PRs>
```

---

## Events deprecation regression blocked by Windows fixture encoding
- **Status:** Blocked
- **Raised:** 2026-08-17
- **Context:** The Phase 4 Events deprecation/observation suite cannot complete because `tests/conftest.py:36` prints a Unicode check mark to a `cp1252` stream, raising `UnicodeEncodeError` during the application fixture. The configured PostgreSQL database was reachable and reported 173 tables, but 27 downstream tests errored before exercising Events behavior.
- **What needs to happen:** Review the test-infrastructure output encoding and rerun the authorized PostgreSQL Events suite without weakening assertions, skipping tests, or hiding database failures. Keep `organizer_id` constructor and permission compatibility active until production-versus-test fallback usage is separately observed.
- **Owner/area:** Events + test infrastructure
- **Links:** `tests/conftest.py:36`, `app/events/Events_Phase4_Deprecation_Observation_Report.md`, `app/events/models.py`, `app/events/permissions.py`

---

## Missing baseline migration — DB cannot be built via `flask db upgrade`
- **Status:** Done
- **Resolved:** 2026-08-20
- **Context:** `ab6dd422c152_initial_schema` (down_revision=None) was the effective root of the migration graph but never created `users`, `events`, `accounts`, `transactions`, or `accommodation_properties`, so `flask db upgrade` failed against an empty database in ANY environment.
- **Resolution:** Retired `ab6dd422c152_initial_schema` to `migrations/_retired_versions/` and added `migrations/versions/8a0deccce6f6_initial_full_schema_baseline.py` — a single root migration (`down_revision=None`) that builds the entire schema from current models via `db.metadata.create_all()` (handles FK ordering/circular deps). Verified: `flask db upgrade` from an EMPTY database now builds all 182 tables incl. `users`/`events`/`accounts`/`transactions`/`accommodation_properties`, stamped at head `8a0deccce6f6`. The test env keeps its `db.create_all()` + `stamp head` bootstrap (identical schema).
- **Owner/area:** migrations / database
- **Links:** `migrations/versions/8a0deccce6f6_initial_full_schema_baseline.py`, `migrations/_retired_versions/ab6dd422c152_initial_schema.py`, `tests/conftest.py`, `scripts/setup_test_db_schema.py`, `AGENTS.md` §20, §21.1

---

## Accommodation test database and RoomType import drift
- **Status:** Blocked
- **Raised:** 2026-08-12
- **Context:** The broader transaction-recovery verification is implemented, but the affected accommodation suite cannot run to completion because the configured test database is missing `users.email_verified_at`, and `tests/test_accommodation_roomtype.py` imports `RoomType` from `app.accommodation.models.property` although the model is defined elsewhere.
- **What needs to happen:** Align the test database through the normal migration/setup process, correct the stale test import, then rerun the full accommodation suite and the global transaction-recovery tests.
- **Owner/area:** accommodation + test infrastructure
- **Links:** `app/identity/models/user.py`, `app/accommodation/models/room.py`, `tests/test_accommodation_roomtype.py`, `tests/test_accommodation_transaction_recovery.py`

---

## PostgreSQL-only test contract blocked by stale schema
- **Status:** Blocked
- **Raised:** 2026-08-15
- **Context:** The repository now enforces PostgreSQL-only pytest execution, SQLAlchemy model/expression queries, exact `TEST_DATABASE_URL` targeting, the repository's single Alembic head, migrated schema, and fail-fast connectivity checks. The configured `afcon360_test` database currently reports Alembic revision `f2f97ca5a313` and is missing `users.email_verified_at`, `users.phone_verified_at`, and `users.activated_at`, so ORM persistence tests correctly fail before execution.
- **What needs to happen:** With `APP_ENV=testing` and `FLASK_ENV=testing`, an operator must review and run `& .venv\Scripts\python.exe -m flask --app 'app:create_app()' db upgrade` against `afcon360_test`, verify the three columns through the shared fixture, then rerun `pytest`; do not create tables, patch schema in fixtures, or use handwritten SQL.
- **Owner/area:** test infrastructure / database operations
- **Links:** `docs/POSTGRES_TESTING_CONTRACT.md`, `tests/postgres_contract.py`, `tests/conftest.py`, `migrations/env.py`, `migrations/versions/2499ed67dc8c_add_email_verified_at_and_phone_.py`, `test_raw_insert.py`, `test_user_raw.py`

---

## Database Reliability & Read-Replica Offload for Analytics
- **Status:** Not started
- **Raised:** 2026-08-11
- **Context:** Database reliability hardening is completed with engine timeouts (`lock_timeout`, `statement_timeout`, `idle_in_transaction_session_timeout`) and connection pool calibration (`pool_size=10`, `max_overflow=15`). Heavy compliance and admin dashboard count/analytics queries (`get_case_statistics`, bulk reports) remain on the primary database instance and should be routed to a read replica as scaling exceeds 1M+ daily operations.
- **What needs to happen:**
  - Configure PostgreSQL read replica endpoint in production environment variables.
  - Implement SQLAlchemy bind/replica routing for heavy read-only dashboard queries and count summaries.
  - Fully offload raw media storage saves, virus scanning, and content moderation (`upload_photo`) into Celery background tasks with early pending row commit.
  - Move compliance notification event fan-outs (`notify_compliance_case_event`) into dedicated Celery background tasks.
- **Owner/area:** infrastructure + database / admin
- **Links:** `app/config.py`, `db_system_hardening.md`, `app/media/service.py`, `app/admin/compliance/services.py`

---

## KYC compliance test database schema drift
- **Status:** Blocked
- **Raised:** 2026-08-11
- **Context:** `tests/test_kyc_compliance.py` cannot complete against the configured test database because the `users.email_verified_at` column expected by the current `User` model is absent; one unit test also creates a standalone Flask app without registering the project SQLAlchemy extension.
- **What needs to happen:** Align the test database schema with the current `User` model through the normal migration/setup process, then update the standalone unit test fixture to use the project application context and rerun the full KYC compliance suite.
- **Owner/area:** KYC + test infrastructure
- **Links:** `app/identity/models/user.py`, `app/auth/kyc_compliance.py`, `tests/test_kyc_compliance.py`

---

## Cancellation refund / fine policy for mid-stay (post check-in) cancellations
- **Status:** Partial — logic implemented + enforced, pending finance/compliance sign-off
- **Raised:** 2026-08-09
- **Context:** Hosts needed to cancel a booking that is already `checked_in` (guest breached T&Cs, guest uncomfortable, early departure, etc.). The lifecycle now allows `CHECKED_IN → CANCELLED`. As of 2026-08-09 the refund engine is centralised in `AccommodationBooking.get_cancellation_quote()`, which resolves the effective policy (booking `policy_snapshot` → `PropertyBookingPolicy` row → legacy `Property.cancellation_policy`), computes the refundable base (pro-rated remaining nights for mid-stay, full total pre-check-in) and returns an **explicit `fine` line item** (= base − refund). `BookingService.cancel_booking()` persists that outcome into `booking.policy_snapshot['cancellation_outcome']` and the host cancel route surfaces the fine in the flash message.
- **Mid-stay tiers currently enforced:** flexible = full remaining, moderate = full remaining, strict = 50% of remaining, super_strict = 25% of remaining, non_refundable = 0. Zero refund once `check_out` has passed.
- **What needs to happen:**
  - Finance/compliance review + sign-off of the mid-stay tiers above (code is the current source of truth).
  - Decide whether the recorded `fine` should become a real ledger/wallet line item (currently audit-only in `policy_snapshot`) rather than just the withheld refund.
  - Verify the actual money movement/reversal path for a mid-stay cancel (host payout was already released at check-in).
- **Owner/area:** accommodation + compliance/finance
- **Links:** `app/accommodation/models/booking.py` (`get_cancellation_quote`, `_cancellation_policy_context`, `_apply_policy_tiers`, `can_cancel`), `app/accommodation/services/booking_service.py` (`cancel_booking`), `app/accommodation/state_machine/booking_states.py` (`VALID_TRANSITIONS`), `app/accommodation/routes.py` (`host_cancel_booking`), `templates/accommodation/host/booking_detail.html` (Cancel action).

---

## `PropertyBookingPolicy` import bugs (admin dashboard stats + check-in readiness)
- **Status:** Done (2026-08-09)
- **Raised:** 2026-08-09
- **Context:** Two instances of the same class of bug: `app/admin/routes.py` imported `PropertyBookingPolicy` from `app.accommodation.models.property` (wrong module → `ImportError`, admin dashboard stats silently failed and the request fell through to a flash/redirect that produced the repeating "Admin access required." flashes), and `AccommodationBooking.is_ready_for_checkin` referenced `PropertyBookingPolicy` with **no import at all** (`NameError` swallowed by a bare `except`, so `require_guest_identity` was never enforced).
- **Fix applied:** both now import from `app.accommodation.models.booking_policy`.
- **Owner/area:** admin + accommodation
- **Links:** `app/admin/routes.py:189`, `app/accommodation/models/booking.py` (`is_ready_for_checkin`).


---

## Owner Database Backup & Restore Dashboard — IMPLEMENTED
- **Status:** Done (Resolved 2026-08-11)
- **Raised:** 2026-08-11
- **Context:** A coaching/runbook guide claimed Owners could trigger backups, schedule them, and restore via the owner dashboard. Verification showed the old `app/backup/backup_service.py` was non-functional (missing `schedule` dep + missing `Column/String/Integer/Text/JSON` imports) and wired to no routes. Implemented a real, robust system.
- **Implemented:**
  - `app/backup/backup_service.py` rewritten: `BackupRecord(BaseModel)` (soft-delete, `public_id` UUID), robust `pg_dump`/`psql` via `subprocess` with `PGPASSWORD` env + timeout, SHA-256 checksum verify, gzip, retention cleanup. No `schedule` dependency.
  - `app/tasks/backup_tasks.py` + `celery_app.py` beat entry `backup.scheduled_run` (hourly due-check, honors `BACKUP_ENABLED`/`BACKUP_FREQUENCY`/`BACKUP_INCLUDE_FILES`/`BACKUP_INCLUDE_CONFIG` SystemConfig).
  - `app/admin/owner/backup_routes.py` (`owner_backup` blueprint on `owner_bp`): `/admin/owner/backups` list+create+scheduler settings, download, restore (typed "RESTORE DATABASE" confirm), delete — all owner-guarded + `audit_owner_action`.
  - `templates/owner/backups.html` (mobile-responsive) + link added to `danger_zone.html`.
- **Remaining (owner action):** generate + apply the Alembic migration for `backup_records` (proposed in the implementation report).
- **Owner/area:** admin / owner + backup
- **Links:** `app/backup/backup_service.py`, `app/backup/__init__.py`, `app/tasks/backup_tasks.py`, `app/celery_app.py`, `app/admin/owner/backup_routes.py`, `templates/owner/backups.html`.

---

## Event guest identity schema migration
- **Status:** Needs review
- **Raised:** 2026-08-18
- **Context:** Guest coordination now defines an account-independent `EventGuest`, nullable `EventRegistration.guest_id`, nullable `EventAssignment.guest_id`/`attendee_id`, and guest-centric coordination contracts. The configured database does not yet contain `event_guests`, so accountless persistence cannot be exercised until the schema is migrated.
- **What needs to happen:** Review model registration and constraints, create the approved short Alembic revision using the repository migration protocol, apply it under operator control, backfill registration guest links, and add PostgreSQL integration coverage for uniqueness, soft delete, and compatibility resolution. Do not modify wallet models.
- **Owner/area:** Events + database operations
- **Links:** `app/events/models.py`, `app/events/events.md`, `app/events/guest_coordination_service.py`, `tests/test_guest_coordination_contract.py`

---

## Group checkout and booking notification migration
- **Status:** Partial — migration applied for new table; notification type CHECK constraint still needs manual update
- **Raised:** 2026-08-12
- **Context:** Checkout now persists `rooms_requested` and the notification model accepts `booking_pending`/`third_party_booking`/`accommodation_complaint_opened`. Migration `c0758a81e4b0` was generated and applied, creating `accommodation_booking_price_adjustments`. However, Alembic does **not** auto-detect PostgreSQL CHECK constraint changes, so the database `ck_notifications_type` constraint still lacks the new notification type values and will reject inserts until manually updated.
- **What needs to happen:**
  1. Add/review a normal Alembic migration to replace `ck_notifications_type` with the full allowed list including `booking_pending`, `third_party_booking`, `accommodation_complaint_opened`.
  2. Alternatively, remove the CHECK constraint in a reviewed migration and rely on application-level validation.
  3. Apply the migration through the normal operator workflow and verify complaint notifications insert successfully.
- **Owner/area:** accommodation + notifications / database
- **Links:** `app/accommodation/models/booking.py`, `app/accommodation/routes.py`, `app/notifications/models.py`, `migrations/versions/c0758a81e4b0_add_accommodation_complaint_opened_to_.py`

---

## Context-specific permissions and role policy
- **Status:** Not started
- **Raised:** 2026-08-14
- **Context:** Context switching now selects and navigates to personal, organization, event, driver, accommodation-host, and platform workspaces. The current change intentionally preserves existing authorization decorators while the product direction is to let one user operate under multiple hats without relying on a single global role.
- **What needs to happen:** Define the authority matrix for each context, make protected workspace decorators evaluate the active context plus current domain ownership, replace legacy role-name checks that do not understand `UserRole` records, and add negative tests for cross-context access and stale/revoked assignments.
- **Owner/area:** auth/identity + events + transport + accommodation + admin
- **Links:** `app/auth/context.py`, `app/auth/decorators.py`, `app/transport/routes.py`, `app/events/permissions.py`, `app/accommodation/routes.py`, `app/Documentation/UNIFIED_IDENTITY_CONTEXT_SPEC.md`

## Organisation booking operations
- **Status:** Not started
- **Raised:** 2026-08-14
- **Context:** Organisation contexts now list organisation-owned events, properties, and accommodation bookings. The first slice is intentionally read-only so context selection cannot silently grant booking authority.
- **What needs to happen:** Define and implement the organisation booking authority matrix for approval, amendment, cancellation, check-in, check-out, refunds, and guest-data access, with idempotency, audit, and negative cross-organisation tests.
- **Owner/area:** identity + accommodation + compliance
- **Links:** `app/identity/routes.py`, `templates/org/bookings.html`, `app/accommodation/AFCON360_SEAMLESS_BOOKING_SPEC.md`

## Replace temporary phone OTP email transport with Twilio SMS
- **Status:** Partial — owner-controlled transport switch implemented
- **Raised:** 2026-08-14
- **Context:** Phone verification defaults to email, and the owner can now switch the next OTP requests between email and configured SMS from `/admin/owner/owner/settings/auth`. SMS fails closed and invalidates the OTP when no provider is ready, preserving the verified-state machine.
- **What needs to happen:** Configure and test production Twilio or Africa's Talking credentials, perform a real provider delivery smoke test, and enable SMS only after provider success and operational/compliance approval.
- **Owner/area:** auth + infrastructure
- **Links:** `app/auth/phone_verification.py`, `app/auth/otp_service.py`, `app/auth/routes.py`, `app/Documentation/AUTH_SYSTEM_ARCHITECTURE.md`

---

## Account-optional event guest assignment: test DB restore + test execution blocked
- **Status:** Blocked
- **Raised:** 2026-08-19
- **Context:** The account-optional guest-assignment change set is implemented across `app/events/models.py:1088` (`EventAssignment.attendee_id` is `BigInteger`, `ForeignKey("users.id", ondelete="SET NULL")`, `nullable=True`, `index=True`), `app/events/guest_coordination_service.py:303` (registration_id resolution, no `REGISTRATION_IDENTITY_REQUIRED`, attendee_id may be None), `app/events/attendee_accounts.py`, `app/events/services.py`, `app/events/payment_service.py`, and `app/events/assignment.py`, plus the regression test `tests/test_guest_assignment_account_optional.py`. The model already declares `attendee_id` `nullable=True`/`index=True`, so no nullable migration is required — only the `ix_event_assignments_attendee_id` index delta, which is already present in the existing `ad665a64d4b4` migration. Tests cannot be executed because `afcon360_test` was dropped during troubleshooting and is currently empty; the base schema is not built by Alembic (the initial migration `ab6dd422c152` (`down_revision=None`) creates only 3 tables and ALTERs pre-existing base tables), so a from-scratch `flask db upgrade` cannot build it.
- **What needs to happen:**
  1. Restore `afcon360_test` from its snapshot/dump (human-owned — the base schema is not migration-built).
  2. With `APP_ENV=testing` + `FLASK_ENV=testing` and `DATABASE_URL`/`SQLALCHEMY_DATABASE_URI`/`DB_NAME` cleared, run `flask db current` then `flask db upgrade` to reach `(head)` (`1f2072788371`).
  3. Run `pytest tests/test_guest_assignment_account_optional.py tests/test_guest_coordination_contract.py`.
  - Migration/DB-restore application is human-owned; Kilo only proposes exact commands.
- **Owner/area:** events + test infrastructure / database operations
- **Links:** `app/events/models.py:1088`, `app/events/guest_coordination_service.py:303`, `app/events/attendee_accounts.py`, `app/events/services.py`, `app/events/payment_service.py`, `app/events/assignment.py`, `tests/test_guest_assignment_account_optional.py`, `tests/test_guest_coordination_contract.py`, `migrations/versions/ad665a64d4b4_account_optional_guest_coordination_.py`, `.kilicode/rules/postgres-test-db-rules.md`

---

## PostgreSQL test-database targeting guidance (Kilo rule)
- **Status:** Done (Resolved 2026-08-19)
- **Raised:** 2026-08-19
- **Context:** Kilo sessions risked targeting `afcon360_prod` because `.env`'s `DB_NAME=afcon360_prod` and `DATABASE_URL` override `TestingConfig`, and `flask` is not on PATH. Captured the verified targeting procedure in a durable, auto-loaded Kilo rule.
- **What needs to happen:** None — rule written.
- **Owner/area:** test infrastructure
- **Links:** `.kilicode/rules/postgres-test-db-rules.md`, `app/config.py:421-442`, `migrations/env.py:56-85`

<!-- New deferred items go above this line. -->

## Event settings enforcement and persistence safety
- **Status:** Not started
- **Raised:** 2026-08-18
- **Context:** Review of `app/events/settings_model.py` found the file safe for the current Events authority-contract correction: it defines platform-wide defaults and does not use `organizer_id`, authorize individual events, or mutate canonical event ownership. Several follow-up gaps remain around enforcing those defaults and safely persisting cached settings.
- **What needs to happen:**
  - Enforce `allow_organiser_cancel` in `can_cancel_event()` and `allow_organiser_delete` in `can_soft_delete_event()`.
  - Enforce `max_capacity_limit` and `max_ticket_types_per_event` in `EventService.create_event()` and related ticket configuration paths.
  - Make cached `EventSettings.get()` results update the attached database row, or invalidate/reload the cache before writes.
  - Preserve native boolean/integer types during cache serialization and safely handle any stringified datetime values.
  - Ensure the settings mutation route requires `is_system_admin(current_user)` and audit-log the platform-level change.
- **Owner/area:** events + platform administration
- **Links:** `app/events/settings_model.py`, `app/events/permissions.py`, `app/events/services.py`, `app/events/routes.py`, `app/owner/routes/settings.py`

## Event registration availability schema migration
- **Status:** Blocked — migration generated, review/application pending
- **Raised:** 2026-08-15
- **Context:** Event registration availability now uses `events.registration_opens_at`, `events.registration_closes_at`, and the ordering check constraint `ck_event_registration_window_order`. Alembic generated revision `64561496dfcf` for the two timestamp columns, but it did not auto-generate the check constraint; the revision remains unapplied and requires review under the project migration protocol.
- **What needs to happen:** Review revision `64561496dfcf` and ensure `ck_event_registration_window_order` is represented in a reviewed migration; apply the approved migration through the production migration process; then rerun the Events registration and availability suites against a PostgreSQL-like database.
- **Owner/area:** events + database
- **Links:** `app/events/models.py`, `app/events/services.py`, `app/events/registration_availability.md`, `tests/test_event_registration_availability.py`

---

## Individual TIN policy administration surface
- **Status:** Partial — application toggle implemented, admin surface pending
- **Raised:** 2026-08-14
- **Context:** Individual TIN is now optional by default through the `kyc_require_tin` owner/Super-Admin toggle (seeded in `app/kyc_config_schema.py` and persisted in `system_configs`); organisation KYB still retains its separate TIN-certificate requirement. All KYC tunables (document toggles, tier limits, screening flags, activity tiers, reporting thresholds) are now configurable from the Wallet Capabilities → KYC Requirement Configuration page and applied across the codebase via `app/kyc_config_schema.py`.
- **What needs to happen:** Add an owner/compliance-controlled configuration entry with audit logging, safe defaults, effective-date handling, and tests for both toggle states before enabling it in production.
- **Owner/area:** KYC + compliance configuration
- **Links:** `app/auth/kyc_compliance.py`, `app/admin/owner/`, `app/models/system_config.py`, `app/Documentation/PROFILE_KYC_SYSTEM.md`

---

## Notification inbox controls schema migration
- **Status:** Blocked — application change complete, migration pending
- **Raised:** 2026-08-14
- **Context:** The `/notifications` inbox now supports mark read, mark unread, mark/unmark important, open, and user-scoped soft-delete controls. The model adds `notifications.is_important`, but the configured database schema does not yet contain that column.
- **What needs to happen:** Review and apply the normal Alembic migration generated from the model change; do not run `flask db migrate` or `flask db upgrade` automatically. Then rerun `tests/notifications/test_user_controls.py` and the affected notification suite.
- **Owner/area:** notifications + database
- **Links:** `app/notifications/models.py`, `app/notifications/routes.py`, `app/notifications/services.py`, `templates/notifications/inbox.html`, `tests/notifications/test_user_controls.py`

---

## Event guest coordination owning-module integration
- **Status:** Done (Resolved 2026-08-14)
- **Raised:** 2026-08-14
- **Context:** Event-scoped coordination is complete across the existing Event, Accommodation, Transport, Identity/Auth, Notification, and template boundaries. The service validates event-scoped existing bookings, dates, occupancy/capacity, driver/vehicle eligibility, module availability, authorization, transactional outbox staging, cancellation/reassignment, and bulk results without creating parallel inventory.
- **What needs to happen:** No remaining implementation work for this coordination slice; apply the normal production migration process only if future model changes require it.
- **Owner/area:** events + accommodation + transport + notifications
- **Links:** `app/events/services/guest_coordination_service.py`, `app/events/assignment.py`, `app/events/permissions.py`, `templates/events/admin/attendees_list.html`, `.junie/plans/implement-event-guest-coordination.md`

---

## Event workflow fixture scope mismatch
- **Status:** Blocked
- **Raised:** 2026-08-14
- **Context:** The affected legacy Event workflow suite cannot collect because `tests/test_events.py` defines a module-scoped `app` fixture while `tests/conftest.py:db_session` is session-scoped and requests that fixture.
- **What needs to happen:** Align the fixture scopes or use the project application fixture, then rerun `tests/test_events.py`, `tests/test_event_workflow.py`, and `tests/test_events_user_workflows.py`.
- **Owner/area:** events + test infrastructure
- **Links:** `tests/conftest.py`, `tests/test_events.py`, `tests/test_event_workflow.py`, `tests/test_events_user_workflows.py`

---

## Regenerate check-constraint migration after model reconciliation
- **Status:** Partial — migration applied; four comparisons need policy/normalizer review
- **Raised:** 2026-08-13
- **Context:** Model constraints were aligned with database-used values for inventory reasons, accommodation property type/status, and lowercase wallet ledger/transaction values. The existing draft migration `migrations/versions/1786629630_sync_check_constraints.py` was generated before that reconciliation and is stale.
- **What needs to happen:** The constraint migration `1786632360` has been applied. The synchronizer now classifies 63 equivalent representations correctly and reports only four unresolved checks (`users.ck_users_email_format`, `accommodation_property_booking_policies.ck_deposit_percentage_range`, `fraud_alerts.ck_fraud_alert_risk_score_range`, and `events.ck_system_owner_id_zero`). Review those four before generating any migration.
- **Owner/area:** database schema + accommodation + wallet
- **Links:** `app/accommodation/models/room.py`, `app/accommodation/models/property.py`, `app/wallet/models/ledger.py`, `app/wallet/models/transaction.py`, `scripts/sync_check_constraints.py`, `migrations/versions/1786629630_sync_check_constraints.py`

---

## Room-Type-Specific Property Galleries
- **Status:** Not started
- **Raised:** 2026-08-12
- **Context:** Property-level media now supports categories such as bedroom and bathroom, but hosts may eventually need separate galleries attached to each `RoomType` (for example, “Deluxe room” photos distinct from the property exterior and shared facilities).
- **What needs to happen:** Give room types a stable public media entity identifier, add host UI and authorization for room-specific uploads/reordering/deletion, and render each room gallery beside its booking option. Keep property-level media for exterior, shared areas, amenities, and other common spaces.
- **Owner/area:** accommodation media + room types

---

## Reversible attendee registration suspension (Suspend/Reinstate)
- **Status:** Not started — needs spec + migration authorization
- **Raised:** 2026-08-19
- **Context:** The Organizer Hub now unifies all attendees across managed events with Check-in / Cancel / Assign actions, but there is no reversible "suspend" state. `EventRegistration` (`app/events/models.py:657-662`) defines only `pending_payment`, `confirmed`, `cancelled`, `checked_in`, `no_show`, `expired` — no `suspended`. The only remove-access path is `EventService.cancel_registration` (`app/events/services.py:2237-2262`), which is terminal (frees a seat, no un-cancel), blocks checked-in attendees, and captures no reason, no audit entry, and no refund handling. An attendee who must be pulled (misconduct, fraud, TOS/security flag) currently can only be hard-cancelled or left untouched.
- **What needs to happen:**
  - Approve a spec for the suspend/reinstate lifecycle (status set, reason, actor, reversibility, check-in enforcement, capacity/assignment release, refund policy).
  - Migration (HIGH_RISK per AGENTS.md §19–20, §34): add `STATUS_SUSPENDED = "suspended"` plus `suspended_at`, `suspended_by_id`, `suspended_reason` columns to `EventRegistration` (mirror existing `Event.is_suspended` fields at `models.py:204-205`).
  - `EventService.suspend_registration(ref, actor, reason)` + `reinstate_registration(ref, actor)` restoring prior status (e.g. `confirmed`).
  - Extend `check_in_attendee` / `check_in_attendee_by_ref` (`services.py:1489-1493`) to reject `suspended` like `cancelled`.
  - Gated by `can_manage_registration`; forensic audit (AGENTS.md §29) on every suspend/reinstate.
  - Hub UI: Suspend / Reinstate buttons in the attendee table + reason modal.
  - Do NOT auto-refund — releasing assigned accommodation/transport capacity that implies a refund is a separate HIGH_RISK finance decision (wallet double-entry), requires finance/compliance review.
- **Owner/area:** Events + identity/permissions + finance/compliance (for refund policy)
- **Links:** `app/events/models.py:657-662`, `app/events/models.py:204-205`, `app/events/services.py:2237-2262`, `app/events/services.py:1455-1514`, `app/events/permissions.py` (`can_manage_registration`), `templates/events/events_hub.html` (attendee table actions), AGENTS.md §6, §19, §20, §29, §34
- **Links:** `app/accommodation/models/room.py`, `app/accommodation/services/media_service.py`, `app/media/routes.py`, `templates/accommodation/host/edit_listing.html`, `templates/accommodation/guest/detail.html`

---

## KYC/KYB authorization � regulatory vs operational daily/monthly limit fusion (Agent 2 finding)
- **Status:** Partial - regulatory daily/monthly now ENFORCED in WalletService hot path (Agent 3, ledger-derived volume via KYCLimitService.check_regulatory_cumulative_limits); operational ceilings remain; canonical volume-source decision = ledger-derived for authorization, stored account.daily_volume/monthly_volume display-only. See Future Architecture sec 2/9/10.
- **Raised:** 2026-08-28
- **Context:** Frozen architecture states KYC owns regulatory limits, Wallet owns operational ceilings, and the effective applicable limit uses restrictive precedence (min). Today the effective per-transaction limit correctly applies restricted precedence (regulatory per-txn vs action-specific WalletSystemConfig ceiling). However, the daily/monthly regulatory KYC limits (kyc_config_schema `kyc_tier_{t}_daily_limit` / `monthly_limit`) are NOT enforced inside `WalletService.deposit/withdraw/transfer`. The transaction hot path enforces daily via Flask config `WALLET_DAILY_LIMIT_HOME/LOCAL` (`WalletService._check_daily_limit`) and monthly via per-account `AccountModel.monthly_volume_limit` (`WalletService._check_monthly_limit`). Separately, `KYCLimitService.check_volume_limits` enforces the regulatory daily/monthly limit against the stored `account.daily_volume`/`monthly_volume` columns, but only in the web-form route (`app/wallet/routes.py:782`), not in the API/admin/payment-gateway paths that call `WalletService` directly. Two distinct volume sources are also used: stored `account.daily_volume` (incremented by `account_repo.update_volume`) vs ledger-derived volume (`ledger_repo.get_daily_volume`).
- **What needs to happen:** Decide the single canonical volume source and fuse regulatory+operational daily/monthly with restrictive precedence in the `WalletService` transaction path (or formally declare operational-only as the intended design and deprecate the regulatory KYC daily/monthly columns for transaction authorization). Avoid double-counting across the two volume mechanisms. This is an ARCHITECTURE DECISION, not a local fix.
- **Owner/area:** Wallet + KYC/Compliance
- **Links:** `app/wallet/services/wallet_service.py:119-194`, `app/wallet/services/kyc_limit_service.py:259-312`, `app/wallet/routes.py:782`, `app/kyc_config_schema.py`, `app/wallet/models/ledger.py` (`daily_volume`, `monthly_volume_limit`), AGENTS.md A18.1, A17

## KYC/KYB authorization � AML threshold ownership conflict (Agent 2 finding)
- **Status:** Not started � needs architecture decision
- **Raised:** 2026-08-28
- **Context:** Two competing AML threshold authorities exist: (1) `kyc_config_schema.get_thresholds()` returns `aml_review`=5,000,000 and `fia_report`=20,000,000 (owner-configurable, used by `check_transaction_allowed`/`flag_for_aml_review`/`report_to_fia` in `app/auth/kyc_compliance.py`); (2) `WalletSystemConfig.aml_threshold` (default 10,000) is persisted and editable in the admin UI but is NOT referenced anywhere in the authorization/compliance path; (3) `ComplianceEngine`/`AMLTransactionMonitor` hard-codes `DAILY_REPORTING_THRESHOLD = 10000`. These three values can disagree and create contradictory behavior. Per AGENTS.md the two systems must not be silently merged.
- **What needs to happen:** Decide the single authoritative AML threshold owner. Either wire `WalletSystemConfig.aml_threshold` into the compliance path (and remove the hard-coded 10000) or formally deprecate `WalletSystemConfig.aml_threshold` as dead config. Do NOT silently merge the two systems.   [Agent 3, 2026-08-28: confirmed WalletSystemConfig.aml_threshold is DEAD/unused; authoritative = kyc_config_schema.get_thresholds(); documented in Future Architecture sec 3. No production change made; removing dead config needs a migration (owner action).]
- **Owner/area:** Wallet + Compliance
- **Links:** `app/kyc_config_schema.py:373-378`, `app/wallet/models/config.py:293` (`aml_threshold`), `app/wallet/services/compliance_engine.py:196,311`, `app/auth/kyc_compliance.py:494-500`, AGENTS.md A18.1, A29

## KYC/KYB authorization � broken `WalletService.create_wallet` / `get_wallet_limits` (Agent 2 finding)
- **Status:** Not started � out of scope (dead/broken code, not in hot path)
- **Raised:** 2026-08-28
- **Context:** `WalletService.create_wallet()` imports a non-existent module `app.wallet.models.wallet` (no `Wallet`/`WalletAuditLog` model exists; ledger-based `AccountModel` is the real account entity). `get_wallet_limits()` returns `max_transfer_amount` for `daily_limit`/`monthly_limit`, conflating per-transaction and cumulative ceilings. `create_wallet` is currently not called anywhere in the app, so this is dead code, but it must not be re-activated without fixing the model reference and the ceiling semantics. Do NOT invent a `WalletLimit` model.
- **What needs to happen:** If wallet-creation limits are needed, derive them from `WalletSystemConfig` action-specific ceilings and KYC regulatory limits; use `AccountModel` (not a `Wallet` model) for persistence. Otherwise leave as-is and document.
- **Owner/area:** Wallet
- **Links:** `app/wallet/services/wallet_service.py:270-317`, `app/wallet/models/__init__.py`, AGENTS.md A18.1, A34

## KYC/KYB authorization � individual PEP/sanctions screening lifecycle (Agent 2 finding)
- **Status:** Deferred (per frozen spec) � MISSING ARCHITECTURAL COMPONENTS for individuals
- **Raised:** 2026-08-28
- **Context:** Organisation KYB supports sanctions screening state via `OrganisationKYBCheck(check_type="sanctions")` (state persistence exists; provider integration deferred). Individuals have NO PEP/sanctions model fields; `check_pep_status()`/`check_sanctions_list()` in `app/auth/kyc_compliance.py` return `"NOT_SCREENED"`. No periodic re-screening mechanism exists for either owner type. External screening must remain OUTSIDE the transaction authorization hot path (frozen spec).
- **What needs to happen:** When separately authorized, add individual PEP/sanctions screening state persistence, a re-screening scheduler, and a compliance-review hook. Do NOT add screening provider calls to the transaction path.
- **Owner/area:** Identity + Compliance
- **Links:** `app/identity/models/kyb.py`, `app/auth/kyc_compliance.py:685-727`, `app/identity/services/organisation_kyb_service.py:40,94-95`, AGENTS.md A18.2, A29

---

# Future Financial Compliance & Authorization Architecture (Agent 3 -- 2026-08-28)

Consolidated design target derived from the Agent-2 KYC/KYB authorization findings and the frozen
architecture invariants (AGENTS.md A17, A18.1, A18.2, A29). Each subsection names the current gap,
the proposed design, and the ownership boundary. NOT yet implemented unless noted.

## 1. Jurisdiction Policy Engine
- Current: per-tier limits/activity constants live in app/kyc_config_schema.py; ComplianceEngine /
  AMLTransactionMonitor hard-code DAILY_REPORTING_THRESHOLD = 10000.
- Target: a jurisdiction-keyed policy store (owner-configurable) so AML/regulatory thresholds and
  activity tiers are selected by jurisdiction rather than a single global constant set.
- Owner: KYC/Compliance + Config. Must NOT introduce PostgreSQL ENUM types (AGENTS.md A14).

## 2. Regulatory vs Operational Limits (restrictive precedence)
- Regulatory (KYC, jurisdiction) and operational (Wallet) ceilings are SEPARATE sources.
- Effective per-transaction = min(regulatory per-txn, action-specific WalletSystemConfig ceiling)
  -- already implemented in KYCLimitService.check_transaction_allowed.
- Effective daily/monthly = min(regulatory daily/monthly, operational daily/monthly).
  - Regulatory daily/monthly: ENFORCED (Agent 3) via KYCLimitService.check_regulatory_cumulative_limits
    in WalletService.deposit/withdraw/transfer, using ledger-derived volume.
  - Operational ceilings: Flask config WALLET_DAILY_LIMIT_HOME/LOCAL (WalletService._check_daily_limit)
    and AccountModel.monthly_volume_limit (WalletService._check_monthly_limit).
- Do NOT clamp regulatory by operational or vice versa (explicit Task A decision).

## 3. AML Architecture Separation
- Authoritative AML/monitoring thresholds: kyc_config_schema.get_thresholds() (aml_review=5,000,000,
  fia_report=20,000,000) -- owner-configurable; consumed by app/auth/kyc_compliance.py.
- WalletSystemConfig.aml_threshold (default 10,000) is DEAD/unused -- must be deprecated (needs a
  migration to remove the column; out of Agent 3 scope).
- ComplianceEngine.DAILY_REPORTING_THRESHOLD = 10000 is SEPARATE regulatory reporting, not AML screening.
- Decision required: single authoritative AML owner; do NOT silently merge the two systems (AGENTS.md A18.1).

## 4. Risk-Based Monitoring
- Risk score per transaction/account derived from policy-engine thresholds; separate from the binary
  authorization pass/fail. Surfaces for compliance review, not for blocking the hot path.

## 5. PEP/Sanctions Lifecycle
- Organisation: OrganisationKYBCheck(check_type=sanctions) state persistence exists; provider
  integration deferred.
- Individual: NO persistence; check_pep_status()/check_sanctions_list() return NOT_SCREENED.
- External screening MUST remain OUTSIDE the transaction authorization hot path (frozen spec).

## 6. Individual Screening Persistence
- Add PEP/sanctions state fields to the individual identity models, mirroring the organisation pattern
  (app/identity/models/kyb.py). Currently MISSING for individuals.

## 7. Re-Screening
- Periodic Celery job keyed by last_screened_at + risk band, for BOTH individual and organisation
  owners; triggers a compliance-review hook on change.

## 8. Compliance Review Workflow
- Flag -> review -> decision, with forensic audit (AGENTS.md A29): correlation id, actor, status,
  risk, request context. Owner-reviewed states; no silent auto-clear.

## 9. Canonical Transaction Volume Source
- CHOSEN (Agent 3): ledger-derived volume (LedgerRepository.get_daily_volume / get_monthly_volume,
  DEBITS, rolling windows) is the authoritative source for cumulative regulatory limits.
- Stored AccountModel.daily_volume / monthly_volume are retained for DISPLAY ONLY and are NOT
  authoritative for authorization. This divergence is intentional and documented here.

## 10. Operational Daily/Monthly Ceilings
- Flask config WALLET_DAILY_LIMIT_HOME / WALLET_DAILY_LIMIT_LOCAL (deposit/withdraw) and
  AccountModel.monthly_volume_limit (transfer/monthly) remain the operational ceilings.
- They are enforced independently of, and not clamped by, the regulatory cumulative limits.

## 11. Authorization Decision Engine
- Single entrypoint: KYCLimitService.check_transaction_allowed (individual) +
  KYCLimitService._check_org_transaction_allowed (org via OrganisationKYBService.compute_status).
- Returns a dict: allowed, reason, limit_type, kyc_level, aml_flag.
- WalletService._check_kyc_limits enforces regulatory cumulative limits and delegates operational
  ceilings to the existing _check_daily_limit / _check_monthly_limit.
- FROZEN (unchanged): AccountOwnerType, AccountModel.owner_type, wallet ownership FKs,
  User.kyc_level schema, Organisation.verification_status semantics, no new Wallet model,
  no migrations in Agent 3 scope.

---

## KYC/KYB authorization -- Agent 3 bounded remediation (2026-08-28)
- Status: Partial -- Task A implemented + tested; Task B documented (needs decision); Task C tests fixed; stale test scaffold classified
- Raised: 2026-08-28
- Context: Bounded remediation of the Agent-2 KYC/KYB authorization findings, constrained by the frozen wallet-ownership architecture.
- What was done (Task A): KYCLimitService.check_regulatory_cumulative_limits(account_id, currency, amount, kyc_level) added -- uses ledger-derived volume (rolling daily/monthly), no commit in hot path, tier-5 unbounded, skips when no account. WalletService._check_kyc_limits now accepts account_id and raises LimitExceededError (limit_type kyc_daily/kyc_monthly); wired into deposit/withdraw/transfer. Regulatory daily/monthly are NOT clamped by operational ceilings.
- Verification (Task A): 13 new tests in tests/test_kyc_limit_authorization.py PASS (daily enforced, daily within-limit, monthly enforced, daily NOT clamped by operational ceiling, missing-account skip, tier-5 unbounded, WalletService raises on cumulative daily).
- Task B (AML conflict): Analyzed; documented above (AML Architecture Separation). No production change. WalletSystemConfig.aml_threshold is dead; authoritative = kyc_config_schema.get_thresholds(). Removing dead config needs a migration (owner action).
- Task C (regressions in kyc_compliance.py): Determined NONE -- calculate_kyc_tier is correct/canonical. Only the STALE test mocks were broken: tests/test_kyc_compliance.py patched app.auth.kyc_compliance.KycRecord (not a module attribute) -> fixed to app.kyc.models.KycRecord; 9/9 now pass.
- Stale test scaffold: tests/test_wallet_authorization_limits.py (519 lines) was a pre-existing broken scaffold. It patched module-level symbols (calculate_kyc_tier, OrganisationKYBService, LedgerRepository, KycRecord) that the implementation imports INSIDE methods, and had API mismatches (per_transaction key, expects 10000 daily, assumed _check_daily_limit enforced regulatory KYC). RESOLVED 2026-08-28: repaired to 34/34 passing after fixing mock targets, the org/account mock shape, tier-0 handling, and aligning with the real architecture (operational daily ceiling in _check_daily_limit; regulatory cumulative in _check_kyc_limits via check_regulatory_cumulative_limits). The broader authorization suite (test_wallet_authorization_limits + test_kyc_limit_authorization + test_kyc_compliance) is now 58/58 green.
- Dead/broken code confirmed: WalletService.create_wallet() / get_wallet_limits() import non-existent app.wallet.models.wallet and conflate per-transaction/cumulative ceilings. Dead (not in hot path). Documented; not reactivated. get_effective_cumulative_limit referenced at wallet_service.py:148,190 does not exist (same dead path).
- Owner/area: Wallet + KYC/Compliance
- Links: app/wallet/services/kyc_limit_service.py, app/wallet/services/wallet_service.py, tests/test_kyc_limit_authorization.py, tests/test_kyc_compliance.py, tests/test_wallet_authorization_limits.py, app/kyc_config_schema.py, app/wallet/models/config.py, app/auth/kyc_compliance.py, AGENTS.md A18.1, A17, A29, A34

---

## 4. Operational Daily/Monthly Wallet Configuration (deferred from audit)
- **Status:** Open (decision required)
- **Raised:** 2026-08-28
- **Context:** The wallet currently enforces operational per-transaction ceilings via `WalletSystemConfig.max_deposit/withdrawal/transfer_amount` and an operational daily ceiling via Flask config `WALLET_DAILY_LIMIT_HOME`/`WALLET_DAILY_LIMIT_LOCAL`. There is NO operational *monthly* ceiling and no owner UI to review/override the effective (regulatory-min-operational) daily/monthly bound.
- **What needs to happen:** Decide whether owners should be able to lower (never raise above regulatory) the operational daily/monthly ceilings through `WalletSystemConfig`, and whether an operational monthly ceiling should be introduced. Requires an approved spec + migration (constitution A19.2/A20 — owner/operator action). Do NOT modify wallet models without authorization.
- **Owner/area:** Wallet + Owner/Compliance

## 5. Authorization Volume Performance (deferred from audit)
- **Status:** Open (monitor)
- **Raised:** 2026-08-28
- **Context:** `WalletService._check_kyc_limits` now calls `KYCLimitService.check_regulatory_cumulative_limits` on every deposit/withdraw/transfer. That helper computes ledger-derived rolling daily/monthly volume via `LedgerRepository.get_daily_volume`/`get_monthly_volume` (DB aggregations) plus `calculate_kyc_tier`. Under high authorization throughput this adds DB load per transaction.
- **What needs to happen:** Confirm via load testing that the per-transaction volume aggregation is acceptable; if not, introduce a cached/denormalized rolling counter or materialized summary with a bounded refresh, behind the existing `WalletService` path (no model/migration change without approval). The helper performs no `commit`, so it is safe to call inside the atomic hot path.
- **Owner/area:** Wallet performance
- **Links:** app/wallet/services/kyc_limit_service.py (`check_regulatory_cumulative_limits`), app/wallet/repositories/ledger_repository.py (`get_daily_volume`/`get_monthly_volume`), app/wallet/services/wallet_service.py (`_check_kyc_limits`)

---

## 6. Owner-Configurable Operational Daily/Monthly Ceilings in WalletSystemConfig (deferred from this pass)
- **Status:** Open (decision required)
- **Raised:** 2026-08-29
- **Context:** The wallet currently enforces operational per-transaction ceilings via `WalletSystemConfig.max_deposit/withdrawal/transfer_amount` and an operational daily ceiling via Flask config `WALLET_DAILY_LIMIT_HOME`/`WALLET_DAILY_LIMIT_LOCAL`. There is NO operational *monthly* ceiling in `WalletSystemConfig` and no owner UI to review/override the effective (regulatory-min-operational) daily/monthly bound through the database-backed config.
- **What needs to happen:** Decide whether owners should be able to lower (never raise above regulatory) the operational daily/monthly ceilings through `WalletSystemConfig`, and whether an operational monthly ceiling should be introduced. Requires an approved spec + migration (constitution A19.2/A20 — owner/operator action). Do NOT modify wallet models without authorization.
- **Owner/area:** Wallet + Owner/Compliance

---

## 7. Request-Scoped Memoization for `calculate_kyc_tier` (deferred from this pass)
- **Status:** Open (performance optimization)
- **Raised:** 2026-08-29
- **Context:** `calculate_kyc_tier(user_id)` is called multiple times per request (by `WalletService._check_kyc_limits`, `KYCLimitService.get_user_kyc_level`, `WalletStatusService.get_wallet_status`, etc.). Each call executes the full KYC pipeline (DB queries, document scope aggregation). Under load this is repeated per transaction.
- **What needs to happen:** Add request-scoped memoization (e.g., `flask.g._kyc_tier_cache[user_id]`) to avoid redundant KYC queries within a single request. Must be safe for the authorization semantics (no stale tier within a request).
- **Owner/area:** Wallet + Auth performance
- **Links:** app/auth/kyc_compliance.py (`calculate_kyc_tier`), app/wallet/services/kyc_limit_service.py (`get_user_kyc_level`), app/wallet/services/wallet_service.py (`_check_kyc_limits`), app/wallet/services/wallet_status_service.py (`get_wallet_status`)

---

## 8. Frontend KYC/KYB Status Synchronization (deferred from this pass)
- **Status:** Partial (dashboard updated; other pages may need review)
- **Raised:** 2026-08-29
- **Context:** The wallet dashboard now displays effective limits from `KYCLimitService.get_transaction_limits`. The deposit page uses `limits.per_transaction.deposit` for per-transaction limit validation. Other wallet pages (withdraw, send, settings) may still use stale logic or not display effective limits.
- **What needs to happen:** Audit all wallet frontend pages (withdraw, send, transactions, settings) to ensure they display effective limits from the backend (`get_transaction_limits` or equivalent) and do not independently calculate authorization rules.
- **Owner/area:** Wallet frontend
- **Links:** templates/wallet/deposit.html, templates/wallet/withdraw.html, templates/wallet/send.html, templates/wallet/wallet_dashboard.html

---

## F3 — Ledger Volume Semantics for Regulatory Cumulative Limits
- **Status:** Open (decision required)
- **Raised:** 2026-08-29
- **Context:** `LedgerRepository.get_daily_volume` and `get_monthly_volume` compute volume as SUM of DEBIT entries over rolling 24h/30d windows. This is the authoritative source for regulatory KYC daily/monthly cumulative limits. However, the semantics have unresolved questions:
  1. Rolling window (24h/30d) vs calendar day/month — regulatory limits are typically calendar-based.
  2. No filter by transaction status — includes entries from COMPLETED transactions only (since failed txns roll back), but if a transaction fails after ledger post but before status update, the debit would count.
  3. No exclusion of refund/reversal CREDIT entries from the DEBIT sum — refunds are CREDIT entries so they don't affect DEBIT volume, but a reversal posted as a DEBIT would incorrectly increase volume.
  4. No exclusion of internal/platform account DEBITs — platform accounts may have different regulatory treatment.
  5. Currency isolation is per-account (correct).
- **What needs to happen:** Product/compliance decision on intended semantics. If calendar-based windows are required, migrate to calendar-day/month aggregation. If status filtering is needed, join to TransactionModel.status. If reversal handling is needed, add reversal flag to ledger entries. Requires approved spec + potential migration (constitution A19.2/A20).
- **Owner/area:** Wallet + Compliance
- **Links:** app/wallet/repositories/ledger_repository.py (`get_daily_volume`/`get_monthly_volume`), app/wallet/services/kyc_limit_service.py (`check_regulatory_cumulative_limits`), app/wallet/services/wallet_service.py (`_check_kyc_limits`), tests/test_kyc_limit_authorization.py (regulatory cumulative tests)

---

## D1 — Org Admin page action routes missing (removed dead controls)
- **Status:** Not started
- **Raised:** 2026-08-30
- **Context:** Fixing production-console error #2 (`'Organisation' object has no attribute 'owner'`) in `manage_orgs()` revealed the org list page was a stub. It referenced four backend endpoints that do not exist: `admin.transfer_org_owner`, `admin.deactivate_org`, `admin.activate_org`, `admin.view_org_audit`. The route only queries orgs; no action handlers exist. To make the page render (clearing "Error loading organisations"), the four dead, route-less controls were removed and replaced with a "Actions pending backend routes" placeholder. The `owner`->`primary_contact_user`, `name`->`legal_name`, `members`->`users`, `roles`->`custom_roles` attribute fixes and stat-card bindings were applied.
- **What needs to happen:** Implement a dedicated node for org-admin actions. `transfer_org_ownership` service already exists at `app/auth/services/org.py` and can back `transfer_org_owner`. Ownership transfer is HIGH sensitivity (constitution 18.2) and requires audit logging + authorization (owner/super_admin). Activate/Deactivate should toggle `is_active` with audit. Audit Logs needs a real endpoint (org-scoped forensic audit). Add CSRF-protected routes + tests.
- **Owner/area:** Admin module
- **Links:** app/admin/routes.py (`manage_orgs`), templates/admin/manage_orgs.html, app/auth/services/org.py (`transfer_org_ownership`), app/auth/ownership.py (`transfer_ownership`)

---

## D2 — `org_members.html` owner reference + member loop
- **Status:** Partial
- **Raised:** 2026-08-30
- **Context:** Orphaned template (no route currently renders it). Its `org.owner.username` was fixed to `org.primary_contact_user.username`. The member loop still iterates `org.members` (Organisation has no `members`; members live in `org.users` as `OrganisationMember` join rows exposing `.user`). If this page is ever wired up, fix the loop to iterate `org.users` and render `member.user.*` fields.
- **Owner/area:** Admin module
- **Links:** templates/admin/org_members.html, app/identity/models/organisation.py (`Organisation.users`), app/identity/models/organisation.py (`OrganisationMember`)

---

## D3 — Nigeria mobile-money API keys never wired into Owner settings
- **Status:** Not started
- **Raised:** 2026-08-30
- **Context:** `MobileMoneyService._mtn_nigeria_deposit` / `_airtel_nigeria_deposit` read `current_app.config["MTN_NG_API_KEY"]` / `AIRTEL_NG_API_KEY`, but `app/owner/routes/settings.py` only wires `mtn_ug_api_key`, `airtel_ug_api_key`, and `mpesa_api_key`. NG operators therefore hit a missing-config failure (now surfaced cleanly via `_require_api_key`). Uganda + M-Pesa are configurable; NG is not.
- **What needs to happen:** Add `mtn_ng_api_key` / `airtel_ng_api_key` fields to the Owner wallet settings form + persistence (`settings.py` save/load and `templates/owner/wallet_settings.html`), consistent with the existing UG fields, so NG mobile-money deposits can be configured. Verify against `PaymentMethodConfig` NG entries (`mobile_money_mtn_ng`, `mobile_money_airtel_ng`).
- **Owner/area:** Wallet / Owner settings
- **Links:** app/wallet/payments/mobile_money.py:375,402, app/owner/routes/settings.py:318-320, templates/owner/wallet_settings.html:427-437, app/wallet/models/payment_method.py:192,209

---

## Agent System — external integrations & deep KYB deferred (Phase 2 follow-ups)
- **Status:** Partial (core engine built; provider/external pieces deferred)
- **Raised:** 2026-08-30
- **Context:** The full agent subsystem is now implemented in `app/wallet`: onboarding (tiered KYC/KYB: wallet_admin → compliance_officer → super_admin/owner), float + float ledger, cash-in, refunds, statements, per-agent reconciliation, and a completed payout flow (request/approve/reject/pay that settles commissions). It is gated by the existing owner "Agents" toggle (`WalletSystemConfig.agents_enabled`). The following remain intentionally separate authorized nodes because they require real provider credentials, financial rules, and compliance sign-off.
- **What needs to happen (deferred nodes):**
  1. Real document uploads for onboarding (currently stores document *references*; needs a secure doc store).
  2. Automated KYB verdict wired to `OrganisationKYBCheck` / real `Organisation` entities for org agents (Phase 2 stores KYB data for human review).
  3. Automated sanctions/PEP screening provider integration.
  4. External provider agent onboarding + ongoing monitoring/SAR (MTN/Flutterwave/bank agent portals).
  5. Real payout disbursement to agent bank/mobile-money (Phase 2 records internal settlement only; `PayoutService.pay` is a stub for external disbursement).
- **Owner/area:** Wallet / Compliance / KYC
- **Links:** app/wallet/services/agent_onboarding_service.py, agent_float_service.py, agent_refund_service.py, agent_statement_service.py, agent_reconciliation_service.py, payout_service.py, app/wallet/models/agent_float.py, app/wallet/routes.py (wallet.agent_* , wallet.admin_agent_*), templates/wallet/agent_*.html
- **Migration:** New tables `agent_float_ledgers`, `agent_onboardings`, `agent_onboarding_approvals`, `agent_commissions`, `payout_requests` and `users.is_agent`/`users.agent_code` columns require a user-run migration before going live.

---

## LSP legacy `Column()` typing noise — Phase 2Mapped/mapped_column migration is the only cure
- **Status:** Not started
- **Raised:** 2026-09-01
- **Context:** Pyright 1.1.413 (via `npx`) reports project-wide `reportAttributeAccessIssue` / `reportReturnType` / `reportArgumentType` noise on any model using the legacy SQLAlchemy 1.x `Column(...)` class-attribute style (e.g. `app/models/base.py`, `app/identity/models/user.py`, `app/wallet/models/*`, and the recovered agent services). The noise comes from pyright inferring instance attributes as `Column[T]` instead of `T`. **Empirically verified (isolated repro):** `sqlalchemy2-stubs` does NOT heal this — it only relabels `Column[bool]`→`Column[Boolean]` — and it is a **discontinued** package that even breaks `mapped_column`. `typeCheckingMode: "standard"` alone also does not help. The only real cure is migrating models to SQLAlchemy 2.0 `Mapped[...]` / `mapped_column(...)` style, which reduces columns to native Python types (repro showed only 1 *genuine* error vs 2 false ones for an identical model).
- **What needs to happen:** Long-term convention — migrate a model's columns to `Mapped`/`mapped_column` **only while the model is already being touched for other work** (do not do a bulk migration). Re-run `npx pyright` on `tests/test_agent_system_full.py`, `app/wallet/repositories/commission_repository.py`, `app/wallet/services/agent_float_service.py` to confirm the systemic noise clears. Do NOT install `sqlalchemy2-stubs` (discontinued, blocks `mapped_column`). This is the agreed Phase 2C plan (Phase 1A abandoned by user decision 2026-09-01).
- **Owner/area:** Wallet models + project-wide models
- **Links:** app/models/base.py, app/identity/models/user.py, app/wallet/models/*, tests/test_agent_system_full.py, app/wallet/repositories/commission_repository.py, app/wallet/services/agent_float_service.py, pyrightconfig.json
- **Note:** `commission_repository.py` duplicate `get_by_ref`/`mark_paid` removed and `mark_paid` signature fixed to `paid_by: Optional[int] = None` (Phase 1B, done 2026-09-01) — the remaining reported errors there are all systemic `Column()` noise, not genuine.

---

## test_payment_flow.py — 3 pre-existing failures (stale `app.events.services._legacy` mock target)
- **Status:** Not started
- **Raised:** 2026-09-01
- **Context:** `tests/test_payment_flow.py::TestPaymentFlow::{test_free_registration_no_payment, test_paid_registration_insufficient_funds, test_paid_registration_success}` fail with `AttributeError: module 'app.events.services' has no attribute '_legacy'` (the mocked target no longer exists; also `mock_wallet_service.withdraw` is not called). These are **pre-existing and unrelated** to the agent/payout recovery work — the whole suite passes `3 passed` minus exactly these 3.
- **What needs to happen:** Update the mock targets in `tests/test_payment_flow.py` to the current `app.events.services` API (remove stale `_legacy` patch, align `mock_wallet_service.withdraw` expectations). Verify against unaffected `tests/wallet` (33 passed) and `tests/test_agent_system_full.py` (2 passed).
- **Owner/area:** Tests / Events / Wallet
- **Links:** tests/test_payment_flow.py, app/events/services.py, app/wallet/services/*

