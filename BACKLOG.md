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
