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

## test_intention_creates_no_domain_resources — fragile global-count baseline on persistent test DB
- **Status:** Done
- **Resolved:** 2026-09-07
- **Raised:** 2026-09-07
- **Context:** `tests/test_provider_participation.py::test_intention_creates_no_domain_resources` asserts that declaring individual provider intentions creates no `Vehicle` rows by comparing a **per-user filtered count** (`Vehicle.query.filter_by(owner_type='user', owner_id=user.id)`) against the **global** `Vehicle.query.count()` baseline taken before (lines 335 vs 341). `afcon360_test` is persistent and reused across runs (conftest reuses when schema present; ~198 tables), so once ANY test in any prior run leaves a `Vehicle` row, `vehicles_before` (global) > 0 while the fresh user's filtered count is 0 → the test fails. Reproduces in isolation (`pytest tests/test_provider_participation.py::test_intention_creates_no_domain_resources` → FAILED). Confirmed UNRELATED to the host-onboarding KYC-gate change (no Vehicle writer touched).
- **What needs to happen:** Replace the global `Vehicle.query.count()` baseline with the same per-user filtered count captured before/after, e.g. `vehicles_before = Vehicle.query.filter_by(owner_type='user', owner_id=user.id).count()` and assert the filtered count unchanged. Keep the assertion's intent (intention creates no domain resources) — do not skip.
- **Owner/area:** tests / provider participation / transport
- **Links:** `tests/test_provider_participation.py:327-347`
- **Resolution (2026-09-07):** FIXED — baseline now captures the same per-user filtered count before/after (immune to other tests persisting `Vehicle` rows in the shared `afcon360_test` DB). Verified: `pytest tests/test_provider_participation.py -q` -> **24 passed**.

---

## Accommodation catalog lookup tables — migration + seed pending
- **Status:** Partial — code complete, migration + seed commands proposed for operator
- **Raised:** 2026-09-07
- **Context:** Refactored host listing forms AND booking policy page to read all option sets (property type, listing type, cancellation policy tier, booking mode, currency, advanced policy types, phases, no-show charge types) from new DB lookup tables instead of Python constants. New tables: `accommodation_property_types`, `accommodation_property_type_host_types`, `accommodation_property_type_listing_types`, `accommodation_listing_types`, `accommodation_policy_tiers`, `accommodation_booking_modes`, `accommodation_currencies`, `accommodation_cancellation_policy_types`, `accommodation_cancellation_phases`, `accommodation_no_show_charge_types`. Models, service, seeder, routes, templates, and fallback logic all implemented and verified (render tests PASS, landmine 0).
- **What needs to happen:** Operator runs the migration + seed sequence:
  ```
  python scripts/create_migration.py "accommodation catalog lookup tables"
  # review generated migration file
  flask db upgrade
  python scripts/seed_accommodation_catalogs.py
  ```
  CHECK constraints on `Property` remain unchanged (same value sets seeded), so no `sync_check_constraints.py` step needed.
- **Owner/area:** accommodation / migrations / database
- **Links:** `app/accommodation/models/catalog.py`, `app/accommodation/services/catalog_service.py`, `app/accommodation/catalog_data.py`, `scripts/seed_accommodation_catalogs.py`, `static/MOBILE_OPTIMIZATION.md` §0.2, §0.3

---

## Events deprecation regression blocked by Windows fixture encoding
- **Status:** RESOLVED
- **Raised:** 2026-08-17
- **Context:** The Phase 4 Events deprecation/observation suite cannot complete because `tests/conftest.py:36` prints a Unicode check mark to a `cp1252` stream, raising `UnicodeEncodeError` during the application fixture. The configured PostgreSQL database was reachable and reported 173 tables, but 27 downstream tests errored before exercising Events behavior.
- **What needs to happen:** Review the test-infrastructure output encoding and rerun the authorized PostgreSQL Events suite without weakening assertions, skipping tests, or hiding database failures. Keep `organizer_id` constructor and permission compatibility active until production-versus-test fallback usage is separately observed.
- **Owner/area:** Events + test infrastructure
- **Links:** `tests/conftest.py:36`, `app/events/Events_Phase4_Deprecation_Observation_Report.md`, `app/events/models.py`, `app/events/permissions.py`
- **Reconciliation (2026-09-05):** `tests/conftest.py` was rewritten; the Unicode check mark was removed (ASCII `[OK]` messages now). `pytest tests/test_events.py tests/test_event_workflow.py tests/test_events_user_workflows.py` -> 21 passed (0 failed). Encoding blocker no longer reproducible. RESOLVED by conftest rewrite.

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
- **Status:** Partial — import resolved; test-fixture defects remain (see Reconciliation)
- **Raised:** 2026-08-12
- **Context:** The broader transaction-recovery verification is implemented, but the affected accommodation suite cannot run to completion because the configured test database is missing `users.email_verified_at`, and `tests/test_accommodation_roomtype.py` imports `RoomType` from `app.accommodation.models.property` although the model is defined elsewhere.
- **What needs to happen:** Align the test database through the normal migration/setup process, correct the stale test import, then rerun the full accommodation suite and the global transaction-recovery tests.
- **Owner/area:** accommodation + test infrastructure
- **Links:** `app/identity/models/user.py`, `app/accommodation/models/room.py`, `tests/test_accommodation_roomtype.py`, `tests/test_accommodation_transaction_recovery.py`
- **Reconciliation (2026-09-05):** RoomType import already corrected (`tests/test_accommodation_roomtype.py` imports from `app.accommodation.models.room`). `tests/test_accommodation_transaction_recovery.py` passes. Remaining: `pytest tests/test_accommodation_roomtype.py` -> 2 failed (test-setup defects, not schema): `owner_org_id=123` FK violation `accommodation_properties_owner_org_id_fkey` (hardcoded org id not created); property `pending_review` booked-state assertion (`'Property is not available for booking' is None`). `pytest tests/test_booking_mode.py` -> 1 failed + 11 errors (`accommodation_properties.slug` NOT NULL fixture gap). Classified TEST/FIXTURE DEFECTS - STILL ACTIVE. Imports and schema resolved.
- **Reconciliation (2026-09-07):** listing_type schema sweep complete. Tests updated to post-refactor values (`hotel`+`private_room`, `house`+`entire_place`). Verified: `test_accommodation_roomtype.py` -> 2 passed, 1 pre-existing (bookable-Property fixture gap, `status="pending_review"` hardcoded in `HostService.create_property`); the one refactor regression found (`test_booking_mode.py::test_default_booking_mode_is_instant` CheckViolation from a `property_type="entire_place"` test-body literal) was FIXED and re-ran PASSING (1 failed, 2 passed). REMAINING FAILURES ARE PRE-EXISTING, NOT FROM THE SWEEP: (a) `test_booking_mode.py` 11 errors -> `TypeError: BookingService.create_booking() missing 1 required positional argument: 'host_user_id'` (signature at `booking_service.py:233` requires `host_user_id` positionally; tests never pass it — `booking_service.py` unmodified); (b) `test_stage4b6_org_write_gate.py` 4 failures -> `org_role is None` (org roles not provisioned/seeded — see "assign_org_role cannot persist org_owner" entry); (c) `test_onboarding_new.py` 9 failures (`TestHostOnboardingVerifiedFields` + `test_host_onboarding_no_longer_creates_property`) -> `302 expected, got 200` from verified-field reconcile ValueError — matches the documented onboarding family BACKLOG:638-644; the swept `property_type_map` lives in the legacy `save_as_intent_only=False` dead path and is provably unreachable in these tests (early return at `onboarding_routes.py:859-860`). Green: `test_stage4b2_capability_enforcement.py` 33 passed (exercises `host_create_listing` -> create_listing.html + form), `test_event_accommodation_assignment_flow.py` + `test_accommodation_home.py` + `test_provider_participation.py` all passed, boot `create_app` OK, all 8 swept templates Jinja-parse OK, no legacy `hotel_room`/`COMMUNITY_HOST` writes remain in app/tests/templates/static.

---

## PostgreSQL-only test contract blocked by stale schema
- **Status:** RESOLVED
- **Raised:** 2026-08-15
- **Context:** The repository now enforces PostgreSQL-only pytest execution, SQLAlchemy model/expression queries, exact `TEST_DATABASE_URL` targeting, the repository's single Alembic head, migrated schema, and fail-fast connectivity checks. The configured `afcon360_test` database currently reports Alembic revision `f2f97ca5a313` and is missing `users.email_verified_at`, `users.phone_verified_at`, and `users.activated_at`, so ORM persistence tests correctly fail before execution.
- **What needs to happen:** With `APP_ENV=testing` and `FLASK_ENV=testing`, an operator must review and run `& .venv\Scripts\python.exe -m flask --app 'app:create_app()' db upgrade` against `afcon360_test`, verify the three columns through the shared fixture, then rerun `pytest`; do not create tables, patch schema in fixtures, or use handwritten SQL.
- **Owner/area:** test infrastructure / database operations
- **Links:** `docs/POSTGRES_TESTING_CONTRACT.md`, `tests/postgres_contract.py`, `tests/conftest.py`, `migrations/env.py`, `migrations/versions/2499ed67dc8c_add_email_verified_at_and_phone_.py`, `test_raw_insert.py`, `test_user_raw.py`
- **Reconciliation (2026-09-05):** Schema is now current: `users.email_verified_at`, `users.phone_verified_at`, `users.activated_at` all present (`app/identity/models/user.py:93-95`). `tests/conftest.py` auto-bootstraps the test DB via `db.create_all()` + stamp head. Verified green coverage: events family 21 passed, guest/registration 20 passed, kyc_compliance 9 passed, org-role family 42 passed, stage4 28 passed, partner-gate subset 11 passed, transport_passengers 18 passed, wallet regression 41 passed. RESOLVED by conftest rewrite + schema-now-current.

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
- **Status:** RESOLVED
- **Raised:** 2026-08-11
- **Context:** `tests/test_kyc_compliance.py` cannot complete against the configured test database because the `users.email_verified_at` column expected by the current `User` model is absent; one unit test also creates a standalone Flask app without registering the project SQLAlchemy extension.
- **What needs to happen:** Align the test database schema with the current `User` model through the normal migration/setup process, then update the standalone unit test fixture to use the project application context and rerun the full KYC compliance suite.
- **Owner/area:** KYC + test infrastructure
- **Links:** `app/identity/models/user.py`, `app/auth/kyc_compliance.py`, `tests/test_kyc_compliance.py`
- **Reconciliation (2026-09-05):** `email_verified_at` present. `pytest tests/test_kyc_compliance.py` -> 9 passed (0 failed). KYC regulatory-limit suite `tests/test_kyc_limit_authorization.py` -> 15 passed. RESOLVED.

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
- **Status:** RESOLVED (schema present)
- **Raised:** 2026-08-18
- **Context:** Guest coordination now defines an account-independent `EventGuest`, nullable `EventRegistration.guest_id`, nullable `EventAssignment.guest_id`/`attendee_id`, and guest-centric coordination contracts. The configured database does not yet contain `event_guests`, so accountless persistence cannot be exercised until the schema is migrated.
- **What needs to happen:** Review model registration and constraints, create the approved short Alembic revision using the repository migration protocol, apply it under operator control, backfill registration guest links, and add PostgreSQL integration coverage for uniqueness, soft delete, and compatibility resolution. Do not modify wallet models.
- **Owner/area:** Events + database operations
- **Links:** `app/events/models.py`, `app/events/events.md`, `app/events/guest_coordination_service.py`, `tests/test_guest_coordination_contract.py`
- **Reconciliation (2026-09-05):** `event_guests` table confirmed present in test DB. `pytest tests/test_guest_assignment_account_optional.py tests/test_guest_coordination_contract.py tests/test_event_registration_availability.py` -> 20 passed. RESOLVED.

---

## Group checkout and booking notification migration
- **Status:** RESOLVED (schema + CHECK constraint synced)
- **Raised:** 2026-08-12
- **Context:** Checkout now persists `rooms_requested` and the notification model accepts `booking_pending`/`third_party_booking`/`accommodation_complaint_opened`. Migration `c0758a81e4b0` was generated and applied, creating `accommodation_booking_price_adjustments`. However, Alembic does **not** auto-detect PostgreSQL CHECK constraint changes, so the database `ck_notifications_type` constraint still lacks the new notification type values and will reject inserts until manually updated.
- **What needs to happen:**
  1. Add/review a normal Alembic migration to replace `ck_notifications_type` with the full allowed list including `booking_pending`, `third_party_booking`, `accommodation_complaint_opened`.
  2. Alternatively, remove the CHECK constraint in a reviewed migration and rely on application-level validation.
  3. Apply the migration through the normal operator workflow and verify complaint notifications insert successfully.
- **Owner/area:** accommodation + notifications / database
- **Links:** `app/accommodation/models/booking.py`, `app/accommodation/routes.py`, `app/notifications/models.py`, `migrations/versions/c0758a81e4b0_add_accommodation_complaint_opened_to_.py`
- **Reconciliation (2026-09-05):** DB `ck_notifications_type` now includes `booking_pending`, `third_party_booking`, and `accommodation_complaint_opened` (verified via `pg_get_constraintdef`). Notification TYPE constraint is in sync with the model enum. RESOLVED. (A separate, NEW T3 test defect was instead found in `tests/notifications/test_user_controls.py` — see Notification inbox controls entry.)

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
- **Status:** RESOLVED (test DB restored via conftest)
- **Raised:** 2026-08-19
- **Context:** The account-optional guest-assignment change set is implemented across `app/events/models.py:1088` (`EventAssignment.attendee_id` is `BigInteger`, `ForeignKey("users.id", ondelete="SET NULL")`, `nullable=True`, `index=True`), `app/events/guest_coordination_service.py:303` (registration_id resolution, no `REGISTRATION_IDENTITY_REQUIRED`, attendee_id may be None), `app/events/attendee_accounts.py`, `app/events/services.py`, `app/events/payment_service.py`, and `app/events/assignment.py`, plus the regression test `tests/test_guest_assignment_account_optional.py`. The model already declares `attendee_id` `nullable=True`/`index=True`, so no nullable migration is required — only the `ix_event_assignments_attendee_id` index delta, which is already present in the existing `ad665a64d4b4` migration. Tests cannot be executed because `afcon360_test` was dropped during troubleshooting and is currently empty; the base schema is not built by Alembic (the initial migration `ab6dd422c152` (`down_revision=None`) creates only 3 tables and ALTERs pre-existing base tables), so a from-scratch `flask db upgrade` cannot build it.
- **What needs to happen:**
  1. Restore `afcon360_test` from its snapshot/dump (human-owned — the base schema is not migration-built).
  2. With `APP_ENV=testing` + `FLASK_ENV=testing` and `DATABASE_URL`/`SQLALCHEMY_DATABASE_URI`/`DB_NAME` cleared, run `flask db current` then `flask db upgrade` to reach `(head)` (`1f2072788371`).
  3. Run `pytest tests/test_guest_assignment_account_optional.py tests/test_guest_coordination_contract.py`.
  - Migration/DB-restore application is human-owned; Kilo only proposes exact commands.
- **Owner/area:** events + test infrastructure / database operations
- **Links:** `app/events/models.py:1088`, `app/events/guest_coordination_service.py:303`, `app/events/attendee_accounts.py`, `app/events/services.py`, `app/events/payment_service.py`, `app/events/assignment.py`, `tests/test_guest_assignment_account_optional.py`, `tests/test_guest_coordination_contract.py`, `migrations/versions/ad665a64d4b4_account_optional_guest_coordination_.py`, `.kilicode/rules/postgres-test-db-rules.md`
- **Reconciliation (2026-09-05):** Test DB is now auto-built by `tests/conftest.py` (db.create_all + stamp head) — the previously empty `afcon360_test` is fully created; the `ab6dd422c152` baseline defect was retired (see "Missing baseline migration"). `pytest tests/test_guest_assignment_account_optional.py tests/test_guest_coordination_contract.py` -> 20 passed. RESOLVED.

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
- **Status:** RESOLVED (columns + CHECK present)
- **Raised:** 2026-08-15
- **Context:** Event registration availability now uses `events.registration_opens_at`, `events.registration_closes_at`, and the ordering check constraint `ck_event_registration_window_order`. Alembic generated revision `64561496dfcf` for the two timestamp columns, but it did not auto-generate the check constraint; the revision remains unapplied and requires review under the project migration protocol.
- **What needs to happen:** Review revision `64561496dfcf` and ensure `ck_event_registration_window_order` is represented in a reviewed migration; apply the approved migration through the production migration process; then rerun the Events registration and availability suites against a PostgreSQL-like database.
- **Owner/area:** events + database
- **Links:** `app/events/models.py`, `app/events/services.py`, `app/events/registration_availability.md`, `tests/test_event_registration_availability.py`
- **Reconciliation (2026-09-05):** `events.registration_opens_at`, `events.registration_closes_at`, and `ck_event_registration_window_order` all confirmed present in test DB. `pytest tests/test_event_registration_availability.py` -> passed (within the 20-pass guest/registration group). RESOLVED.

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
- **Status:** RESOLVED (schema) — NEW T3 test defect found on 2026-09-05
- **Raised:** 2026-08-14
- **Context:** The `/notifications` inbox now supports mark read, mark unread, mark/unmark important, open, and user-scoped soft-delete controls. The model adds `notifications.is_important`, but the configured database schema does not yet contain that column.
- **What needs to happen:** Review and apply the normal Alembic migration generated from the model change; do not run `flask db migrate` or `flask db upgrade` automatically. Then rerun `tests/notifications/test_user_controls.py` and the affected notification suite.
- **Owner/area:** notifications + database
- **Links:** `app/notifications/models.py`, `app/notifications/routes.py`, `app/notifications/services.py`, `templates/notifications/inbox.html`, `tests/notifications/test_user_controls.py`
- **Reconciliation (2026-09-05):** `notifications.is_important` column confirmed present in the live test schema (no migration pending). However `pytest tests/notifications/test_user_controls.py tests/test_kyc_compliance.py` -> 1 failed / 9 passed, and the remaining failure is now a NEW T3 test defect, NOT schema: the test hardcodes `user_id=1`, which does not exist in the fresh test DB, so inserts raise `notifications_user_id_fkey` FK violation. Classified ACTIVE - TEST DEFECT (fix: create a real user via fixture helpers, e.g. the `_make_user` pattern in `tests/wallet/test_payment_identity.py`).

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
- **Status:** RESOLVED
- **Raised:** 2026-08-14
- **Context:** The affected legacy Event workflow suite cannot collect because `tests/test_events.py` defines a module-scoped `app` fixture while `tests/conftest.py:db_session` is session-scoped and requests that fixture.
- **What needs to happen:** Align the fixture scopes or use the project application fixture, then rerun `tests/test_events.py`, `tests/test_event_workflow.py`, and `tests/test_events_user_workflows.py`.
- **Owner/area:** events + test infrastructure
- **Links:** `tests/conftest.py`, `tests/test_events.py`, `tests/test_event_workflow.py`, `tests/test_events_user_workflows.py`
- **Reconciliation (2026-09-05):** `tests/test_events.py` now uses the shared conftest `app`/`test_db` fixtures (no module-scoped `app` fixture). `pytest tests/test_events.py tests/test_event_workflow.py tests/test_events_user_workflows.py` -> 21 passed. RESOLVED.

---

## Regenerate check-constraint migration after model reconciliation
- **Status:** RESOLVED (2026-09-05)
- **Raised:** 2026-08-13
- **Context:** Model constraints were aligned with database-used values for inventory reasons, accommodation property type/status, and lowercase wallet ledger/transaction values. The existing draft migration `migrations/versions/1786629630_sync_check_constraints.py` was generated before that reconciliation and is stale.
- **What needs to happen:** The constraint migration `1786632360` has been applied. The synchronizer now classifies 63 equivalent representations correctly and reports only four unresolved checks (`users.ck_users_email_format`, `accommodation_property_booking_policies.ck_deposit_percentage_range`, `fraud_alerts.ck_fraud_alert_risk_score_range`, and `events.ck_system_owner_id_zero`). Review those four before generating any migration.
- **Owner/area:** database schema + accommodation + wallet
- **Links:** `app/accommodation/models/room.py`, `app/accommodation/models/property.py`, `app/wallet/models/ledger.py`, `app/wallet/models/transaction.py`, `scripts/sync_check_constraints.py`, `migrations/versions/1786629630_sync_check_constraints.py`
- **Reconciliation (2026-09-05):** `python scripts/sync_check_constraints.py --dry-run` now reports Missing/ADD = 0, DB-only/orphaned = 0, REPLACE = 1, representation-only = 81. The four previously unresolved checks (ck_users_email_format, ck_deposit_percentage_range, ck_fraud_alert_risk_score_range, ck_system_owner_id_zero) are now classified as representation-only (semantic-equivalent). The single REPLACE (`provider_participations.ck_provider_participations_single_subject`) is also representation-equivalent (XOR with different parenthesization), surfaced only because the test DB predates the 4B provider-capability work — expected to clear after a `scripts/setup_test_db_schema.py` rebuild; NOT drift, no migration required. RESOLVED.

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
- **Status:** ACTIVE - TEST DEFECT (unchanged); re-confirmed 2026-09-05
- **Raised:** 2026-09-01
- **Context:** `tests/test_payment_flow.py::TestPaymentFlow::{test_free_registration_no_payment, test_paid_registration_insufficient_funds, test_paid_registration_success}` fail with `AttributeError: module 'app.events.services' has no attribute '_legacy'` (the mocked target no longer exists; also `mock_wallet_service.withdraw` is not called). These are **pre-existing and unrelated** to the agent/payout recovery work — the whole suite passes `3 passed` minus exactly these 3.
- **What needs to happen:** Update the mock targets in `tests/test_payment_flow.py` to the current `app.events.services` API (remove stale `_legacy` patch, align `mock_wallet_service.withdraw` expectations). Verify against unaffected `tests/wallet` (33 passed) and `tests/test_agent_system_full.py` (2 passed).
- **Owner/area:** Tests / Events / Wallet
- **Links:** tests/test_payment_flow.py, app/events/services.py, app/wallet/services/*
- **Reconciliation (2026-09-05):** STILL ACTIVE - TEST DEFECT. Re-verified: `pytest tests/test_payment_flow.py` -> 3 failed, 3 passed. Identical 3 `TestPaymentFlow::*` tests fail (test_free_registration_no_payment, test_paid_registration_insufficient_funds, test_paid_registration_success). Root cause unchanged: stale `app.events.services._legacy` mock target in the test file; the code module no longer exposes `_legacy` and `mock_wallet_service.withdraw` is not called. Needs T3 repair updating mocks to the current events services API.

---

## Transport correction node follow-ups (dead services, pre-existing refs, schema sync)
- **Status:** PARTIAL - passenger suite green; audit_log/ValidationError TypeError + booking_mode still active
- **Raised:** 2026-09-02
- **Context:** The `TRANSPORT_MIN_CORRECTION` node (Transport passengers: booker ≠ payer ≠ passenger, accountless passengers, group/multi-vehicle assignment, claim-by-public-id, canonical vocabulary) is implemented and its own suite passes (`tests/test_transport_passengers.py`, 18 passed). The following were identified during that node as **pre-existing / out of scope** and intentionally left untouched (scope discipline, AGENTS.md §5).

  **Resolved (2026-09-02 LSP pass — genuine runtime defects fixed, no `type: ignore`):**
  - `app/transport/services/payment_service.py` — removed `start_span`/`span.set_status()`/`span.end()` (MonitorContext has no such methods); `ValidationError(details=/code=)` → message-only; `ServiceUnavailableError(code=)` → message-only; `audit_log(entity_type/entity_id/request_id=)` → `resource_type/resource_id` (+ `request_id` folded into details); `sanitize_input(payment_data)` → `dict(payment_data)` (was `AttributeError`); `validate_payment(...)['valid']/['errors']` → tuple unpacking (was `TypeError`).
  - `app/transport/services/matching_service.py` — `ValidationError(details=/code=)` → message-only; `booking.vehicle_class_preference` (L44/83/137) → `_booking_vehicle_class()` reading canonical `booking.booking_metadata['vehicle_class']`; `driver.vehicle_id` (attr does not exist) → `_driver_vehicle_id()` resolving via `current_assignment.vehicle_id` or first `owned_vehicles` id. (Runtime `AttributeError`s.)
  - `app/transport/services/promotion_service.py` — `ValidationError(details=/code=)` → message-only.
  - `app/transport/services/tracking_service.py` — `ValidationError(details=/code=)` → message-only; `_generate_route_polyline` returns `""` instead of `None` (declared `-> str`).
  - `app/utils/audit.py` — `user_id`/`resource_id` hints widened to `Optional[Union[str, int]]` (root cause: `DBAuditLog.user_id` is BigInteger, app/audit/models.py:26).
  - `app/transport/services/booking_service.py` — `_invalidate_listing_caches` now guards `cache.cache._client`/`scan_iter` (SimpleCache has neither).
  - `tests/test_transport_passengers.py` — `_user(..., email=)` param; instance `hasattr()` checks replace `__mapper__.columns`.

  **Still open (deferred):**
  1. `app/transport/routes.py` — `audit_log(... entity_type=..., entity_id=...)` calls (lines ~1115, 1201, 1230, 1284, 1313, 1623) hit a runtime `TypeError` because `AuditLog.log()` accepts `resource_type`/`resource_id`, not `entity_type`/`entity_id`. Affected endpoints will 500 when reached.
  2. `app/transport/services/provider_service.py` and `app/transport/services/settings_service.py` — same genuine defect class as the now-fixed services: `ValidationError(details=/code=;)`, `src.errors.ServiceUnavailableError(code=)`, `span.set_status()`, and audit `entity_type/entity_id` kwargs. Identified during the same LSP audit but outside the node's modified file set; must be fixed in a remediation node.
  3. `app/transport/services/payment_service.py`, `promotion_service.py`, `matching_service.py`, `tracking_service.py` are broadly "dead services" — decide on repair vs formal retirement (repair of the concrete broken refs is done; the retire/rewire decision remains).
  3. `app/transport/routes.py` — unresolved `app.schemas.transport` (L227/574/749), `BookingService.list_services`/`get_service`/`get_driver_bookings`, `Trip`/`DriverAvailability` imports, `DriverProfile.status` access, and `ValidationError.messages` accesses.
  4. `templates/admin/moderator/transport_vehicle_view.html:267` renders `history.driver_id` (history object, not a Booking).
  5. `tests/conftest.py` create_all bootstrap is gated on the `users` table existing; after this node's new table, a stale test DB must be dropped (or `scripts/setup_test_db_schema.py` run) before `pytest` — the setup script itself hangs in socketio Redis retry loops, so dropping `afcon360_test` via psycopg2 and letting conftest rebuild is the reliable path.
  6. `tests/test_booking_mode.py` (accommodation) fails with `accommodation_properties.slug` NOT NULL — pre-existing, unrelated to transport.
- **What needs to happen:** A dedicated transport remediation node to (a) normalize the remaining `audit_log` calls in `routes.py` (+ `provider_service.py`/`settings_service.py`) to `resource_type`/`resource_id`, (b) decide repair vs formal retirement of the dead transport services + `app.schemas.transport`/route stubs, (c) fix the vehicle-view driver_id template ref, and (d) address the test-infra socketio/setup-script hang. Migration head is `a3f7d1e5b2` (transport_passengers table; native `transport_passengers_status` enum) — user must run `flask db upgrade` before this is live outside the test DB.
- **Owner/area:** Transport + test infrastructure
- **Links:** app/transport/routes.py, app/transport/services/{payment,promotion,matching,tracking}_service.py, templates/admin/moderator/transport_vehicle_view.html, migrations/versions/a3f7d1e5b2_transport_passengers_table.py, tests/test_transport_passengers.py
- **Reconciliation (2026-09-05):** PARTIAL. Resolved: `pytest tests/test_transport_passengers.py` -> 18 passed. Still ACTIVE (unchanged, verified in current source): (1) `app/transport/routes.py` audit_log `entity_type=`/`entity_id=` calls at 1115/1201/1230/1284/1313 still mismatch `AuditLog.log()` `resource_type`/`resource_id` -> TypeError on those endpoints; (2) `provider_service.py`/`settings_service.py` still raise `ValidationError(message=..., details=..., code=...)` vs `app/utils/exceptions.py:ValidationError.__init__(message, field, value)` -> TypeError when those code paths execute; (3) `tests/test_booking_mode.py` accommodation still 1 failed + 11 errors (`accommodation_properties.slug` NOT NULL) - TEST/FIXTURE DEFECT; (4) socketio/setup-script hang and `app.schemas.transport` stubs remain unverified.



---

## Stage 4 onboarding: assign_org_role cannot persist org_owner (pre-existing RBAC FK mismatch)
- **Status:** RESOLVED (2026-09-05) - org-role provisioning architecture implemented
- **Raised:** 2026-09-02
- **Context:** Stage 4 organisation onboarding (Organisation Type + optional Provider Capabilities) commits the creator as org_owner via pp/auth/roles.py:assign_org_role (per the work-state contract). Evidence shows that function cannot persist org-owner in the current schema, and that this is a **pre-existing** defect, not introduced by Stage 4:
  - OrgUserRole.role_id is a FK to org_roles.id (pp/identity/models/organisation_member.py:185), and OrgUserRole.role relationship targets OrgRole (organisation_member.py:190).
  - But ssign_org_role resolves ole = _get_role(role_name, scope='org') from the global oles table and stores ole.id (a oles.id) into org_user_roles.role_id (pp/auth/roles.py:265,288).
  - The org_roles table (OrgRole model) is **never provisioned anywhere** in pp/ (no OrgRole(...) instantiation found), so there is no row whose id satisfies the FK.
  - Resulting runtime error during commit: ForeignKeyViolation: org_user_roles.role_id -> org_roles.id. Confirmed in the legacy registration service too (OrganizationRegistrationService.add_org_member at organization_registration.py:243-263 uses a *different* legacy OrgRole/org_role_id path in pp/identity/models/organisation.py).
  - Observation: there are at least two divergent org-role designs in the codebase (legacy organisation.py OrgRole/org_role_id on membership vs. organisation_member.py OrgRole/OrgUserRole), and pp/auth/roles.py:assign_org_role reconciles with neither.
- **What needs to happen:** An identity-domain decision (HIGH_RISK, �18.2/�17) on the org-owner assignment mechanism. Options: (a) fix ssign_org_role to create the org_roles row and reference org_roles.id correctly, (b) route Stage 4 through the legacy dd_org_member path, or (c) formalize one org-role design and remove the divergent one. Stage 4 code/tests are ready but blocked on this. The Stage 4 files already updated: pp/auth/onboarding_routes.py, 	emplates/onboarding/{choose_organisation,organisation_step1,organisation_step2}.html, 	ests/test_onboarding.py, 	ests/test_onboarding_stage4.py.
- **Owner/area:** Identity / RBAC (cross-cutting; needs identity ownership sign-off)
- **Links:** app/auth/roles.py:241-308, app/identity/models/organisation_member.py:170-262, app/identity/models/organisation.py (legacy OrgRole), app/identity/services/organization_registration.py:242-263, tests/test_onboarding_stage4.py
- **Reconciliation (2026-09-05):** RESOLVED by commit `60612b4` ("provider capability framework, org role provisioning, and onboarding stage 4b"). `assign_org_role` (`app/auth/roles.py:241`) now resolves per-organisation `OrgRole` instances (querying `org_roles` via `OrgRole.query.filter_by(...)`), so `OrgUserRole.role_id == OrgRole.id`. `app/auth/seed_roles.py` provisions `ORG_ROLE_TEMPLATES` (org_owner, org_admin, finance_manager, transport_manager, hr_manager, dispatcher, project_manager, org_member, org_guest). `org_roles` table exists and org-scope global roles seeded. Evidence: `pytest tests/test_onboarding_stage4.py` -> 28 passed; `pytest tests/test_assign_revoke_org_role.py tests/test_organisation_role_provisioning.py tests/test_org_permission_read_path.py` -> 42 passed. Decision option (a) [proper org_roles provisioning] was implemented.

---

## Stage 4: create_org_wallet stores org.id as AccountModel.user_id (FK to users) — broken by design
- **Status:** RESOLVED (2026-09-06) - `organisation_id` ownership reference implemented; migration pending user run
- **Raised:** 2026-09-04
- **Context:** `OrganizationRegistrationService.create_org_wallet(org)` (app/identity/services/organization_registration.py:331-350) builds `AccountModel(user_id=org.id, owner_type=AccountOwnerType.ORGANISATION, ...)`. `AccountModel.user_id` is `BigInteger, ForeignKey('users.id', ondelete='RESTRICT')` (app/wallet/models/ledger.py). `org.id` is the internal `organisations.id` — never a valid `users.id` — so a real wallet insert for an organisation always raises `ForeignKeyViolation: accounts_user_id_fkey`. Verified via `tests/test_org_creation_rbac_4b1.py::test_explicit_wallet_creation_works_later`; the test only passed in earlier runs when `org.id` coincidentally collided with a users.id persisted by a prior create_organization run (which commits users). This is a pre-existing wallet-architecture defect (org and user share one accounts table keyed by user_id), surfaced by the Stage 4 wallet-decoupling test.
- **What needs to happen:** Wallet-domain decision on how an organisation-owned account is keyed (e.g., an `organisation_id` FK/column on accounts, or an owner-resolution layer) so `create_org_wallet` can persist for orgs. Do NOT implement in Stage 4 — wallet is frozen (§18.1, §34). Either fix the account model/schema (ARCHITECTURAL/HIGH_RISK) or remove/reframe the wallet-decoupling "explicit wallet creation still works" test until the model supports org wallets.
- **Owner/area:** Wallet (frozen) + Identity boundary
- **Links:** app/identity/services/organization_registration.py:331-350, app/wallet/models/ledger.py (AccountModel.user_id FK users.id), tests/test_org_creation_rbac_4b1.py:455-483
- **Reconciliation (2026-09-05):** STILL BLOCKED (architectural). Re-verified: the 4 org-wallet tests still fail with `accounts_user_id_fkey` FK violation (`insert or update on table "accounts" violates foreign key constraint "accounts_user_id_fkey"`): `tests/wallet/test_payment_identity.py::TestAccountNumberGeneration::test_org_account_prefix` + `test_resolve_merchant_code_to_org`, and `tests/wallet/test_ledger_concurrency.py::TestWalletOwnershipTypes::test_organisation_wallet_ownership` + `test_user_and_org_wallets_separate`. `create_org_wallet` still writes `user_id=org.id` against `AccountModel.user_id` FK -> `users.id`. Decision still required: `organisation_id` account-ownership representation (or reframe the wallet-decoupling test). DO NOT weaken the FK or reshape ownership (frozen §18.1/§34). Platform escrow (`app/admin/owner/escrow_services.py`, `PLATFORM_ORG_ID` config) writes a real `users.id` and passes — proven pattern for future reference.
- **Forensics (2026-09-06, new node):** The 4 ownership CHECKs from the RESOLVED entry are present in the models (`app/wallet/models/ledger.py`, `payment_identity.py`) but the applied structural migration `ab251b47627d_...` did NOT include them, so **live `afcon360_prod` still has ZERO `ck_accounts_*` / `ck_payment_identities_*` constraints** (verified via pg_constraint). Additionally `accounts.owner_type` still carries the legacy server default `'USER'::account_owner_type_enum` inherited from the retired baseline `migrations/_retired_versions/ab6dd422c152_initial_schema.py:886` (model has only a Python-side `default=AccountOwnerType.USER`), so a raw/non-ORM INSERT omitting `owner_type` silently recreates uppercase `USER` (proven by insert-probe on the faithful replica `afcon360_migration_rehearsal`). Live distribution: `user` 12 / `platform` 5 / `USER` 4; `payment_identities` 0 rows. Root cause of why Alembic missed the CHECKs: **Alembic 1.17.2 has no check-constraint autogenerate comparator** (none in `alembic/autogenerate/compare.py`; no `comparators.py`) — empirical `compare_metadata` over the two tables emitted 29 diffs (server defaults, indexes, FKs) and **zero** check ops with all 4 checks absent; and `migrations/env.py` does not set `compare_server_default`, so the server-default drift is also invisible to autogenerate. **Deferred (per explicit rule): NO hand-written or edited migrations, NO `op.execute`, NO data UPDATE inside a migration.** Fix must be (a) an env.py autogenerate hook (`process_revision_directives` comparing `inspector.get_check_constraints()` vs target metadata, appending `ops.AddConstraintOp`) and optionally enabling `compare_server_default` (+ model `server_default` declaration), then generate ONLY via `flask db migrate -m "<desc>"` with the USER running `flask db upgrade`; (b) normalize the 4 uppercase `USER` rows to `user` via a separate one-time maintenance mechanism (NOT a migration) run before constraint application. Also: `migrations/versions/ab251b47627d_...` is **untracked in git** while already applied on prod — repo-hygiene item (should be committed once the head revision is final). Do NOT mix with 4B provider_participations / escrow / platform-account nodes (recorded separately).
- **Reconciliation (2026-09-06):** RESOLVED (approved §18 decision report; wallet-freeze exception for this change). Implemented `AccountModel.organisation_id` (BIGINT, FK → `organisations.id` ON DELETE RESTRICT, nullable) as the canonical organisational-ownership reference; `AccountModel.user_id` is now nullable (FK → `users.id` RESTRICT retained) and MUST be NULL for organisation-owned rows. Same applied to `PaymentIdentity.owner_id`/`organisation_id` (`payment_identities`). Guarded by CHECKs `ck_accounts_single_owner`, `ck_accounts_owner_type_consistent`, `ck_payment_identities_single_owner`, `ck_payment_identities_owner_type_consistent` (exact SQL in the model files), partial unique index `uq_accounts_org_owner_currency`, and indexes `ix_accounts_organisation_id` + `ix_payment_identity_org_owner`. All org ownership paths now route via `organisation_id`: `create_org_wallet` (organization_registration.py), `get_wallet_by_org_id` (wallet_service.py), wallet-status org branch, identity `org/<id>/wallet` lookup, payment-identity register/resolve/display-name, and `Organisation.accounts`/`primary_account` (organisation.py). Migration hand-written: `migrations/versions/20260906_0001_add_organisation_ownership_to_accounts.py` (down_revision `3a73c6e6cf29`; **USER MUST RUN `flask db upgrade`** — agent does not). Tests: the 4 org-wallet tests updated to `organisation_id` (+ assert `user_id`/`owner_id` is NULL), new deterministic `tests/wallet/test_ledger_concurrency.py::TestWalletOwnershipTypes::test_org_wallet_ownership_is_not_user_id_collision_dependent`; evidence: `pytest tests/wallet` -> 34 passed, 2 skipped; `pytest tests/test_org_creation_rbac_4b1.py` -> 13 passed. Deferred decisions: (1) legacy `user_id`-only organisation rows previous to this change are tolerated by the CHECK (`owner_type='organisation' AND user_id IS NOT NULL`) and left in place — a guarded data-repair backfill (NULL `user_id` / reconcile `organisation_id`) is pending on a dedicated node; (2) `scripts/setup_platform_escrow.py:143,149` still writes `user_id=org.id` for the platform organisation (same collision-prone pattern, setup-only path) — needs a follow-up fix node; (3) local non-daemon SocketIO publisher thread hangs create_app-based scripts (setup_test_db_schema.py / sync_check_constraints.py with TestingConfig) when Redis is down — use `DISABLE_REDIS=true` for read-only local runs.

---

## Pre-existing test_onboarding.py contract mismatches (partner gate + org entry)
- **Status:** RESOLVED (2026-09-05) - partner-gate subset passes; host step-2 family separate
- **Raised:** 2026-09-04
- **Context:** `tests/test_onboarding.py` (rewritten by earlier Stage 4 work) has 5 persistent failures unrelated to the 4B-1/RBAC deliverable: `TestPartnerGate::test_partner_gate_shows_two_paths`, `test_partner_gate_copy_is_partner_not_account_creation`, `test_partner_gate_accessible_after_profile_completed`, `TestOrganisationPaths::test_organisation_onboarding_entry_reachable`, `TestAdditivePartnership::test_gate_remains_accessible_after_profile_completed`. Root causes are route/contract mismatches, NOT the Stage 4 full_name/profile fix (all 5 failing tests only GET `/onboarding/choose*` or `/onboarding/organisation` and never reach step1 profile creation): (a) GET `/onboarding/organisation` 302-redirects to `/onboarding/choose/organisation` when no `org_type` is in session (onboarding_routes.py:437-440), but the test expects 200; (b) `Become a Partner` / `Individual Partner` copy not present on the pages the tests fetch. My session's edits (organisation_step1.html full_name field; `_get_or_create_profile` full_name default; `_commit_organisation_onboarding` profile full_name) do not affect the routes/templates under test.
- **What needs to happen:** An onboarding-domain decision: either (a) align `tests/test_onboarding.py` expectations with the real gated flow (type-first redirect, actual header/copy on `/onboarding/choose`), or (b) change the routes/templates to satisfy the tests (if the intended UX is direct access + a `Become a Partner` header). Confirm the intended copy string and whether direct `/onboarding/organisation` GET should stay type-gated.
- **Owner/area:** Onboarding (routes + templates) — separate from RBAC Stage 4
- **Links:** app/auth/onboarding_routes.py:395-440, tests/test_onboarding.py:211-269, templates/onboarding/choose.html
- **Reconciliation (2026-09-05):** RESOLVED (partner-gate subset). `pytest tests/test_onboarding.py -k "PartnerGate or OrganisationPaths or AdditivePartnership"` -> 11 passed (0 failed). The 5 historically-failing partner-gate/org-entry tests (test_partner_gate_shows_two_paths, test_partner_gate_copy_is_partner_not_account_creation, test_partner_gate_accessible_after_profile_completed, test_organisation_onboarding_entry_reachable, test_gate_remains_accessible_after_profile_completed) are no longer reproducible — onboarding routes/templates were aligned with the type-gated flow. NB: the separate host-onboarding step-2 family (4 failures x2 files) is tracked in its own entry below and remains open.

---

## Pre-existing host-onboarding step-2 test failures (DetachedInstanceError root cause)
- **Status:** Done
- **Resolved:** 2026-09-07
- **Raised:** 2026-09-05
- **Context:** 4 persistent failures in BOTH `tests/test_onboarding.py` and `tests/test_onboarding_new.py`, re-confirmed unchanged after the Property-separation flip (which only inverts `_commit_host_onboarding`'s default to save-intent-only): `test_verified_full_name_is_prefilled_and_not_overwritten` (DetachedInstanceError), `test_missing_full_name_can_be_requested_from_user` (NotNullViolation — test writes `full_name=None` into a NOT NULL column), `test_missing_country_can_be_requested` (expects raw `"Rwanda"` but `normalize_country` yields canonical `UG`/`RW`), `test_host_onboarding_commits_successfully_with_verified_full_name_preserved` (302 expected, got 200 — cascade of the DetachedInstanceError in `app/__init__.py` `inject_user_role_info` context processor after `db_transaction` commits and expires the Flask-Login `current_user`). None are caused by the intent/Property-separation work; confirmed identical in the untouched sibling file. `tests/test_accommodation_roomtype.py` also still fails (2 tests) due to a non-existent `owner_org_id=123` FK and property status `pending_review` (not bookable) — test-setup drift noted in the earlier "Accommodation test database and RoomType import drift" entry.
- **What needs to happen:** (a) Fix `current_user` session binding/refresh across `db_transaction` commits so the `inject_user_role_info` context processor does not hit a detached instance (auth/session lifecycle — HIGH_RISK, needs a dedicated node); (b) correct the three test bugs (don't write NULL full_name; assert on normalized country; assert 302-or-error accordingly). Property creation must remain in the Accommodation domain (`host_create_listing`), not back in `_commit_host_onboarding`.
- **Owner/area:** Auth session lifecycle + Onboarding tests (separate node)
- **Links:** app/auth/onboarding_routes.py:691-773, tests/test_onboarding.py:206-582, tests/test_onboarding_new.py:285-638, app/__init__.py:1246-1255, tests/test_accommodation_roomtype.py:55,122
- **Reconciliation (2026-09-05):** STILL ACTIVE - unchanged. Reproduced: `pytest tests/test_onboarding.py tests/test_onboarding_new.py` -> 8 failed, 48 passed (4 + 4, same 4 test names per file): `test_verified_full_name_is_prefilled_and_not_overwritten` (DetachedInstanceError from `inject_user_role_info` context processor after `db_transaction` commit expires Flask-Login `current_user`), `test_missing_full_name_can_be_requested_from_user` (NotNullViolation — test writes NULL into NOT NULL `user_profiles.full_name`), `test_missing_country_can_be_requested` (asserts raw 'Rwanda' but `normalize_country` yields canonical 'UG'), `test_host_onboarding_commits_successfully_with_verified_full_name_preserved` (302 expected, got 200 — cascade of the DetachedInstanceError). Next step: dedicated auth/session-lifecycle node to refresh `current_user` across `db_transaction` commits (HIGH_RISK), plus 3 test corrections. Property creation stays in Accommodation domain.
- **Reconciliation (2026-09-07):** RESOLVED. A read-only HTTP-layer probe corrected the root-cause attribution: the step-1 POST completed `_commit_host_onboarding` fine, then `switch_context(current_user, {"type": "accommodation_host", ...})` raised `ContextSwitchError` (a `ValueError`, `app/auth/context.py:600`) because `validate_context` returns `None` — the `accommodation_host` context descriptor only exists when `AccommodationIdentityService.can_host(user) == True` (`identity_service.py:28`), which requires `user.is_fully_verified()` (an approved `IndividualVerification` row, `user.py:369`) plus `profile.profile_completed`. Login-session users in tests (and the pre-KYC runtime case) have NO `IndividualVerification` row, so `can_host` is False → context unavailable → the route's `except ValueError` masked the failure as a 200 with a "requested context is invalid or not assigned" flash — the `302 expected, got 200` symptom. Authorized fix (KYC gate): step-1 POST now always commits the host profile + accommodation provider INTENT, then — if not `is_fully_verified()` — flashes info and redirects to the KYC domain flow (`kyc.upload`, `/kyc/verify/upload`); only verified individuals proceed to `switch_context` → `activate_individual_intention` → host dashboard (`onboarding_routes.py:751-788`). The missing-field test bugs were fixed earlier (no NULL `full_name`; normalized-country assertion), so the family's remaining failure was this one mechanism. Verified: `pytest tests/test_onboarding.py tests/test_onboarding_new.py -q` -> **62 passed** (verified-field completion, missing-field, KYC-gate, property non-creation, legacy flag). New regression test `test_unverified_host_onboarding_is_routed_to_kyc_gate` covers the gate (INTENT stays `INTENT`, no activation).

---

## Stage 4B provider architecture: OPC→PP consolidation (approved Option A, ADR-4A-001/010)
- **Status:** Partial — Stage 4B-1 done; 4B-4 forensics/dry-run done (zero-write); backfill execution pending user + real data
- **Raised:** 2026-09-05
- **Context:** Stage 4A decision report approved (STAGE_4A_UNIVERSAL_PROVIDER_ARCHITECTURE_DECISION_REPORT.md, verdict Option A): `provider_participations` (PP) is the single universal provider-participation table for BOTH subjects (user_id XOR organisation_id); `org_provider_capabilities` (OPC) is consolidated into it 1:1 and then retired. 4B-1 (dual-ID sanitization of `capability_to_dict` + Option A docstrings) is implemented. Remaining 4B work is deferred behind: (a) the user-executed OPC→PP data backfill (below); (b) a transport-specific HIGH_RISK checkpoint (G-2 broken `register_driver` call + F-2 missing provider/driver roles).
- **What needs to happen (order):**
  1. **OPC→PP data backfill (USER EXECUTES, per §20):** proposal below; 4B-3 org write re-point to PP must be sequenced AFTER backfill to avoid legacy-row visibility loss.
  2. 4B-3: re-point `_commit_organisation_onboarding` (app/auth/onboarding_routes.py:497+) and org capability routes/readers to PP rows; retire OPC service usage.
  3. 4B-2: individual capability API (G-3) once an eligibility-hook contract is defined (ADR-4A-006: activation must be eligibility-gated; PP service has no eligibility coupling, no individual suspend/revoke).
  4. 4B-5: transport split + G-2/F-2 fixes — HIGH_RISK, own checkpoint. G-2 confirmed: app/transport/routes.py:584 calls `register_driver(data, user_id=...)` but signature is `register_driver(self, user_id: int, driver_data, request_id=None)`; also fetches `.id` off the dict result.
  5. 4B-6: enforcement gap G-1 — apply `can_org_host` gate at org listing creation.
- **Migration proposal (user executes, do NOT run without explicit authorization):** OPC→PP backfill. Since PP rows are (subject, capability_code, status) and OPC org rows are structurally 1:1, propose an idempotent `flask db`/SQL backfill operator-owned via `scripts/` OR a raw SQL `INSERT ... ON CONFLICT DO NOTHING` mapped on (organisation_id→user_id NULL + capability_code). Verify with pre/post row counts and a NOT NULL `organisation_id` on OPC after cutover. Do NOT use `flask db migrate` as a workaround; no CHECK-constraint changes involved.
- **Stage 4B-4 forensics outcome (2026-09-05, READ-ONLY; see `scripts/stage4b4_opc_to_pp_forensics.py`):** configured dev DB `afcon360_prod` has `org_provider_capabilities`/`provider_participations` tables (exact DDL verified, incl. `ck_provider_participations_single_subject` and `uq_provider_participation_org_code`) with **0 rows in both** — backfill is currently a no-op. `afcon360_test` holds 180 OPC rows (159 live / 21 deleted) + 45 INDIVIDUAL PP rows; classified all zero orphans/invalids/duplicates/conflicts; 180 safe-to-copy; individual PP rows untouched by design. Test-DB data is ephemeral synthetic test data (rebuilt by conftest) and is NOT a migration target. When real OPC data accumulates, rerun the read-only forensics script, get human approval, then execute transactionally.
- **Owner/area:** Identity / provider architecture (implementer: 4B node) + migrations (operator)
- **Links:** app/identity/models/provider_participation.py, app/identity/models/organisation_provider_capability.py, app/identity/services/capability_service.py, app/identity/services/provider_participation_service.py, app/identity/routes.py, app/auth/onboarding_routes.py:497+, STAGE_4A_UNIVERSAL_PROVIDER_ARCHITECTURE_DECISION_REPORT.md

---

## Test-suite forensic audit — deferred stabilization work (see docs/TEST_SUITE_FORENSIC_AUDIT_REPORT.md)

- **Status:** OPEN - Stage 13 completed T3 repairs (item 2); org-wallet decision + harness isolation remain
- **Raised:** 2026-09-05
- **Context:** Full audit of the 89-failure baseline (`867 collected → 89 failed, 763 passed, 4 skipped, 11 errors`) classified every failure into production defects (2 total) vs test/harness defects (~3/4 of the red). The 2 production defects were APPROVED and FIXED: P0 `app/events/trust_service.py` missing `calculate_kyc_tier` module import (commit 2996d92) and P1 KYC template malformed Jinja comments `templates/kyc/index.html:18,77` (commit 9798d12). The three previously-untracked alembic migrations (20260902_2255, 9f75675b5e52, 3a73c6e6cf29) are now tracked (commit 7e34dec); DB is single-head at 3a73c6e6cf29 and CHECK-constraint sync shows no real drift (only representation-only parenthesization).
- **What needs to happen (implementation node, human-approved scope):**
  1. Wire auth/session `current_user` refresh across `db_transaction` commits (also the fix for the onboarding DetachedInstanceError). Verify `tests/test_trust_system.py` + KYC family stay green.
  2. T3 test repairs (tests are the wrong side — no product downgrades): kyc-limit UUID-family (`tests/wallet/test_authorization_limits.py`, `tests/test_kyc_limit_authorization.py` — patch `regulatory_volume_calculator.db` or inject calculator mock); `tests/wallet/test_payment_identity.py:112-115` hardcoded `user_id=1` → use `_make_user`; convert ad-hoc scripts `tests/test_owner_trust_integration.py` (returns early, hardcodes User 2, missing `db` import) and `tests/test_template_fix.py` (bare `template.render()` bypasses Flask context processors → `current_user` undefined; use `render_template` under `test_request_context`) to pytest-conformant tests or fold coverage into `test_trust_system.py`.
  3. Org-wallet ownership DECISION (NEEDS_DECISION): `create_org_wallet` (`app/identity/services/organization_registration.py:331-350`) sets `user_id=org.id` against `AccountModel.user_id` FK → `users.id` (ledger.py:209-214); no callers found; org wallet ownership model must be decided by identity spec (likely `organisation_id` on account), never silently reshaped.
  4. Harness isolation to kill T2 flakiness + T4/T5 pollution (production_console inactive-owner rows; attendee/accommodation id=4 orphan; DB reuse): prefer fixture reset per writing test; require DB rebuild `scripts/setup_test_db_schema.py` before final full-suite gate.
  5. Final gate: full `pytest` after `setup_test_db_schema.py`; remaining red must be ⊆ pre-existing onboarding family (BACKLOG.md:619-625) + any new flake; then update this entry per §11.
- **Owner/area:** Test harness + auth session lifecycle (implementation, human-gated) — NOT this audit node
- **Links:** docs/TEST_SUITE_FORENSIC_AUDIT_REPORT.md, app/events/trust_service.py, templates/kyc/index.html:18,77, app/wallet/services/regulatory_volume_calculator.py:122-138, app/wallet/services/kyc_limit_service.py:473-474, tests/wallet/test_payment_identity.py:112-115, tests/wallet/test_ledger_concurrency.py, app/identity/services/organization_registration.py:331-350, app/wallet/models/ledger.py:209-214
- **Reconciliation (2026-09-05):** Item 2 (T3 test repairs) COMPLETED in the Stage 13 node: `tests/test_kyc_limit_authorization.py` now patches `app.wallet.services.kyc_limit_service.RegulatoryVolumeCalculator` (calculator returns (allowed,current_volume,limit) tuples) -> 15 passed; `tests/wallet/test_payment_identity.py:112-115` now uses `_make_user(app, 14)` instead of hardcoded `user_id=1` -> passes; `tests/test_owner_trust_integration.py` + `tests/test_template_fix.py` rebuilt as pytest-conformant contracts (trust family -> 11 passed, 1 skipped). A genuine production template defect was found and FIXED during this work (user-approved): `templates/admin/trust_settings.html` extended `admin/dashboard.html` which never renders `admin_content`; corrected to extend `admin/admin.html`. Remaining OPEN: item 1 (auth `current_user` refresh across `db_transaction` commits — same root cause as host-onboarding DIE family, tracked in that entry), item 3 (org-wallet ownership decision — STILL BLOCKED, see Stage 4 create_org_wallet entry), items 4-5 (harness isolation + final gate).

---

## New (2026-09-05 BACKLOG reconciliation pass) — notifications test hardcodes user_id=1
- **Status:** ACTIVE - TEST DEFECT
- **Raised:** 2026-09-05
- **Context:** Re-verified during reconciliation: `tests/notifications/test_user_controls.py` inserts a `Notification` with hardcoded `user_id=1`; there is no `users` row with id 1 in the fresh test DB, so inserts raise `notifications_user_id_fkey` FK violation. `pytest tests/notifications/test_user_controls.py` -> 1 failed, 9 passed. `is_important` column and `ck_notifications_type` are present (schema side resolved); this is a test-harness defect.
- **What needs to happen:** T3 repair — create a real user through the shared fixtures (the `_make_user` pattern used in `tests/wallet/test_payment_identity.py:14`) and reference its id instead of hardcoding `user_id=1`.
- **Owner/area:** notifications + test infrastructure
- **Links:** tests/notifications/test_user_controls.py, app/notifications/models.py, tests/wallet/test_payment_identity.py:14

---

## New (2026-09-05 BACKLOG reconciliation pass) — trust_settings template production fix
- **Status:** RESOLVED (2026-09-05)
- **Raised:** 2026-09-05
- **Context:** Discovered during the Stage 13 T3 rebuild: `templates/admin/trust_settings.html` extended `admin/dashboard.html`, but `dashboard.html` does not render the `admin_content` block, so the trust/settings page rendered only the dashboard header/nav. It was the only admin template with that defect (the other 11 admin templates extend `admin/admin.html` which renders `admin_content`).
- **What needs to happen:** Change the template base to `admin/admin.html` (user-approved production fix). RESOLVED. Verified by the rebuilt `tests/test_template_fix.py` (renders via `render_template` under `test_request_context` and asserts response title) and the trust family: `pytest tests/test_owner_trust_integration.py tests/test_template_fix.py tests/test_kyc_limit_authorization.py tests/wallet/test_payment_identity.py` -> 41 passed.
- **Owner/area:** admin frontend
- **Links:** templates/admin/trust_settings.html, templates/admin/admin.html, templates/admin/dashboard.html, tests/test_template_fix.py

---

## New (2026-09-05 BACKLOG reconciliation pass) — CHECK-constraint sync: provider participations single-subject (representation-only)
- **Status:** OPEN - verification pending after next test-DB rebuild (representation-equivalent, NOT real drift)
- **Raised:** 2026-09-05
- **Context:** `python scripts/sync_check_constraints.py --dry-run` reports 1 REPLACE: `provider_participations.ck_provider_participations_single_subject`. Model text `((user_id IS NOT NULL AND organisation_id IS NULL) OR (user_id IS NULL AND organisation_id IS NOT NULL))` vs DB text `(((user_id IS NOT NULL) AND (organisation_id IS NULL)) OR (...))` — SEMANTIC-EQUIVALENT XOR with different parenthesization (representation-only per the sync tool's own classification rule). It surfaces because the test DB schema predates the 4B provider-capability work. All historical CHECK entries are now at 0 ADD / 0 orphaned / 0 real REPLACE.
- **What needs to happen:** Watch it clear after `python scripts/setup_test_db_schema.py` (test-only rebuild) or the next full pytest run; re-run `python scripts/sync_check_constraints.py --dry-run` to confirm. Do NOT generate a migration for a representation-only difference (§20.2). No user action required unless it persists after a rebuild.
- **Owner/area:** schema sync (test infrastructure)
- **Links:** scripts/sync_check_constraints.py, app/identity/models/provider_participation.py:105-109, BACKLOG "Regenerate check-constraint migration" entry

---

## Stage 4B organisation classification & eligibility reconciliation — IMPLEMENTED (Option C approved, 2026-09-05)
- **Status:** DONE (2026-09-05) — code-only; scope-limited; next gates 4B-5 (transport) / 4B-6 (G-1 org write-gate) still require explicit authorization
- **Raised:** 2026-09-05
- **Context:** Forensic investigation (`STAGE_4B_ORGANISATION_CLASSIFICATION_ELIGIBILITY_RECONCILIATION.md`) confirmed `Organisation.business_category` and `OrganizationType` are the same concept (native enum `org_business_category`); the test DB enum has 39 labels = model member names; and `can_org_host()` at `app/accommodation/services/identity_service.py:75` compared the enum member against the legacy strings `['service_provider','merchant']` — a confirmed production defect returning False for every organisation (category E). Human gate **APPROVED Option C**: classification is Identity-owned (canonical `OrganizationType`), domain eligibility is domain-owned (accommodation capability mapping), PP remains the universal capability authority.
- **What was implemented (code-only):** `can_org_host()` now (a) NULL-guards `business_category` (controlled ineligible, no AttributeError), then (b) checks canonical eligibility via `org.can_manage_accommodation()` → `get_capabilities().can_manage_accommodation` over `ORGANIZATION_CAPABILITIES` (eligible members: HOTEL, TOUR_OPERATOR, TRAVEL_AGENCY, EVENT_MANAGEMENT, SPORTS_TEAM, CORPORATE). All existing gates preserved (deleted/existence, active, verification `verified`, operational). Corrected the stale lowercase-`.value` comment at `app/auth/onboarding_routes.py:527-528` (member NAME is persisted). No new enum, no migration, no data transformation, no PP coupling, no `org_type`/`OrganizationType`/`can_host`/`auth/context.py` changes. Verified unchanged via post-implementation search of business_category / OrganizationType / can_org_host / service_provider / merchant / marketplace_seller / non_profit.
- **Tests:** new `tests/test_can_org_host.py` -> 45 passed (eligible→True for all 6 capable members; ineligible→False for all other members; verification/operational/inactive/deleted/NULL→False; legacy vocabulary not canonical). Regression -> 153 passed (`test_stage4b2_capability_enforcement.py`, `test_stage4b3_organisation_capabilities.py`, `test_capability_operations.py`, `test_provider_participation.py`, `test_onboarding_stage4.py`).
- **DB proof:** no migration created/applied (`git status` clean of `migrations/`). `afcon360_test` enum = 39 canonical labels, stored values canonical, zero legacy vocab. **New finding (pre-existing, NOT from this work):** dev DB `afcon360_prod` (default `APP_ENV=local`) has a stale `org_business_category` enum with only the 4 legacy lowercase labels (`merchant`, `service_provider`, `marketplace_seller`, `non_profit`); its `organisations` table is currently EMPTY (0 rows) so no data is at risk. Reconciling requires an approved enum expand-contract migration — USER/CONSTITUTION authority (§20); NOT attempted here. When orgs begin persisting on a local run, `db.create_all`/enum drift would surface `LookupError` on load; keep flagged until reconciled.
- **Deferred legacy debt (do NOT silently fix):** (a) `Organisation.get_capabilities()` NULL fallback references undefined `OrganizationType.MERCHANT` (`organisation.py:237-238`) — latent `AttributeError` only for unclassified orgs, NOT on the `can_org_host()` path; (b) `organization_registration.py:170` legacy free-text `org_type='merchant'` default (template/registration-only, not eligibility); (c) legacy vocabulary in `templates/org/settings_old.html` + `templates/admin/moderator/users.html` (template-only).
- **Links:** STAGE_4B_ORGANISATION_CLASSIFICATION_ELIGIBILITY_RECONCILIATION.md, app/accommodation/services/identity_service.py:54-83, app/identity/models/organisation.py:124-127,235-251, app/identity/models/organization_types.py:154,366-612, tests/test_can_org_host.py, tests/test_onboarding_stage4.py (onboarding persists canonical `business_category`).

---

## Stage 4B-5 Transport Provider Architecture — IMPLEMENTED (approved role=A, register_driver=B, vehicle=A, org=A)
- **Status:** DONE (2026-09-06) — code-only; no migration; regressions classified (see below)
- **Raised:** 2026-09-06
- **Context:** HIGH_RISK checkout previously gated at BACKLOG.md:655 (4B-5: transport split + G-2/F-2 fixes). Decision report `STAGE_4B5_TRANSPORT_PROVIDER_ARCHITECTURE_DECISION_REPORT.md` approved with: §8 role=A (remove `@role_required("provider")` from `become_driver`/`register_vehicle`/`vehicle_dashboard`; canonical gate = `module_enabled_required + login_required + require_profile_completion + require_kyc_tier(3)`), §9 register_driver=B (Resource-Free Provider Intention — `create_individual_intention(user, TRANSPORT)`; `DriverProfile` only after `validate_driver_eligibility`; Vehicle is a separate later operation), §10 vehicle=A (`owner_type='driver'`/`owner_id=driver.id`; `get_user_vehicles` via DriverProfile), §11 org=A (fail-closed `get_organisation_identity` + `can_manage_transport()` gate in `validate_organisation_eligibility`; org-driven Vehicle stays separate). Invariant upheld: TRANSPORT INTENT ≠ DriverProfile ≠ Vehicle.
- **Implemented:** `app/transport/routes.py` (3 guard removals, gate stacks confirmed), `app/transport/services/provider_service.py` (driver-ownership vehicle writes, DriverProfile-resolved `get_user_vehicles`, fail-closed org gates, message-only raises — the exception classes carry `(message, field, value)` with no `code`/`details` kwargs, so new gates raise the typed exception rather than `TypeError`), `app/auth/onboarding_routes.py` `_commit_driver_onboarding` (eligibility → duplicate guard → INTENT PP row → DriverProfile; Vehicle creation REMOVED). Host commit path untouched.
- **Tests:** new `tests/test_stage4b5_transport.py` -> **7 passed** (~17s): driver-wizard intent-only commit (no Vehicle created), duplicate-driver guard, `get_user_vehicles` via DriverProfile (ignores stale `owner_type='user'` row), empty-for-non-driver, org identity fail-closed without registry, RESTAURANT org ineligible / TRANSPORT_COMPANY eligible.
- **Regressions (mandated 10-file batch):** 219 passed, **8 failed — ALL `TestHostOnboardingVerifiedFields`** (4× `test_onboarding.py`, 4× `test_onboarding_new.py`). Reproduce in isolation (4/6 fail). Root causes: `DetachedInstanceError` on `current_user.is_active` after `db_transaction` commit (Flask-Login session detachment — identical to the known onboarding-family failure at BACKLOG.md:638-643), `NotNullViolation user_profiles.full_name` (test writes NULL), country `'UG'` vs raw `'Rwanda'` assertion, host commit 200 vs 302. Classification: **PRE-EXISTING / ENVIRONMENTAL** — host path untouched (diff confirms only `_commit_driver_onboarding`), failures identical to the known family, isolated reproduction excludes cross-test contamination. NOT remediated (no authorization; the fix is the same auth/session-lifecycle node tracked at BACKLOG.md:643/670).
- **Deferred (new, do NOT silently fix):** (a) `_commit_driver_onboarding` crashes on string `date_of_birth` — driver wizard `<input type=date>` sends an ISO string but `UserProfile.validate_date_of_birth` (`app/profile/models.py:280`) requires a `date` object (pre-existing latent defect surfaced by the new wizard test; test works around with a `date` object); (b) `get_capabilities()` `OrganizationType.MERCHANT` AttributeError now reachable via the §11 `can_manage_transport()` gate on unclassified orgs (pre-existing, organisation.py:237-238); (c) `register_vehicle` driver branch never passes `driver_id` → `current_driver_id` never set in `register_vehicle_internal` (uniform vehicle↔driver pointer alignment deferred); (d) 20 remaining broken-by-design `@role_required` sites incl. `driver_dashboard` (routes.py:698/:725) + `fixed_cost_reports` pyramid (`organisation_admin` :1108, admin ×16); (e) identity mock fallback `verified=True` (identity_service/registrar modules absent — pre-existing, not in scope); (f) full org-transport fleet/driver-management UI alignment.
- **DB proof:** no migration created/applied; `git status` shows the pre-existing worktree (stage-4A/4B-3/4B-4 files) with only `app/transport/routes.py`, `app/transport/services/provider_service.py`, `app/auth/onboarding_routes.py`, `tests/test_stage4b5_transport.py`, and the two decision reports added by this node.
- **Links:** STAGE_4B5_TRANSPORT_PROVIDER_ARCHITECTURE_DECISION_REPORT.md, app/transport/routes.py:595,777,886, app/transport/services/provider_service.py, app/auth/onboarding_routes.py:231-320, tests/test_stage4b5_transport.py, BACKLOG.md:655,638-643,643,670

---

## Stage 4B-6 Organisation Operational Write Gate (G-1) — IMPLEMENTED (approved minimal two-gate fix)
- **Status:** DONE (2026-09-06) — code-only; no migration; 6 mandated regressions + focused suite green
- **Raised:** 2026-09-06
- **Context:** Forensic phase confirmed the ONLY production organisation Property writer is `HostService.create_property` via `host_create_listing` (`app/accommodation/routes.py:4384`), and the org branch had NO `can_org_host()` gate and NO provider-participation check (G-1). The org branch was then unreachable (`get_host_identity` never returns `type=organisation`), so G-1 was a latent, non-exploitable gap; the fix closes it as ordered. Human gate **APPROVED** the minimal two-gate correction (no context.py/onboarding/schema changes).
- **What was implemented (code-only):** (1) `app/accommodation/routes.py` — org branch (4377-4402) now requires BOTH `AccommodationIdentityService.can_org_host(host_info["id"])` AND `is_capability_operational("organisation", host_info["id"], ACCOMMODATION)` before rendering the listing form; failure flashes and redirects to host dashboard (mirrors the individual branch). (2) `app/accommodation/services/host_service.py` — write-boundary invariant at the top of `create_property` (96-118): when `owner_org_id is not None`, raise `ValueError` unless `can_org_host()` AND ACCOMMODATION ACTIVATED (defense in depth; individual path untouched).
- **Tests:** new `tests/test_stage4b6_org_write_gate.py` -> **11 passed**: eligible+ACTIVATED → write succeeds; INTENT / DEACTIVATED / SUSPENDED / REVOKED / no-PP-row / ineligible+ACTIVATED → blocked (`ValueError`, org branch redirect); real activate→deactivate toggle; cross-organisation authority (Org A actor denied Org B write); route-level org branch allows activated / blocks intent (real `OrganisationMember`-backed context). `tests/test_accommodation_roomtype.py` corrected to a genuine eligible+ACTIVATED org (fabricated `owner_org_id=123` is now correctly rejected).
- **Regressions (mandated 6-file batch):** 160 passed (`test_stage4b2_capability_enforcement.py` 32, `test_stage4b3_organisation_capabilities.py` 17, `test_stage4b5_transport.py` 7, `test_capability_operations.py` 48, `test_provider_participation.py` 24, `test_onboarding_stage4.py` 32); startup import `python -c "from app import create_app"` exit 0.
- **Verification of no bypass org writers:** production `Property(` sites are individual-only (`routes_community_hosts.py:85`, `onboarding_routes.py:781`) or the gated `HostService.create_property` (host_service.py:128); `HostService.create_property`'s only in-app caller is routes.py:4409 behind the route two-gate. `scripts/verify_bookings.py:19` is a standalone dev script (not app runtime) that seeds a demo org property directly — non-reachable, non-authoritative, flagged not fixed.
- **Pre-existing (NOT from this work, do NOT silently fix):** `tests/test_accommodation_roomtype.py::test_available_units_and_booking_creation` fails on `Property is not available for booking` — the raw individual-host property never sets `status`/`is_verified` to bookable values so `can_be_booked()` is False; body byte-identical to HEAD, unaffected by the G-1 gate (ruled out via isolation + diff).
- **Deferred (new, do NOT silently fix):** (a) `scripts/verify_bookings.py` demo-seeds an org Property directly, bypassing the G-1 gate — dev/audit script only, align or gate when next touched; (b) the pre-existing booking-capability test defect above needs a proper bookable-Property fixture in `test_accommodation_roomtype.py`.
- **DB proof:** no migration created/applied; `git status` shows the pre-existing worktree plus this node's `tests/test_stage4b6_org_write_gate.py` (new) and edits to `app/accommodation/routes.py`, `app/accommodation/services/host_service.py`, `tests/test_accommodation_roomtype.py`.
- **Links:** STAGE_4B_ORGANISATION_CLASSIFICATION_ELIGIBILITY_RECONCILIATION.md, app/accommodation/routes.py:4350-4414, app/accommodation/services/host_service.py:80-120, app/accommodation/services/identity_service.py:55-84, app/identity/services/provider_participation_service.py:373, tests/test_stage4b6_org_write_gate.py, tests/test_accommodation_roomtype.py

---

## Stage 4B-7 Full Stage-4B Verification Gate - RESULT: PASS (with recorded legacy items)
- **Status:** DONE (2026-09-06) - forensics/verification only; no implementation, no migration, no reset/stash/revert; Stage 5 NOT started
- **Raised:** 2026-09-06
- **Context:** Full forensic gate verifying every Stage-4B invariant (OPC audit, PP model/service, capability API, write-gate matrix, context/authority boundaries, DB/migration state). All mandated Stage-4B suites pass individually (67 + 76 + 28). Full suite `pytest tests/` = **903 passed, 66 failed, 4 skipped, 11 errors** - failures classified as pre-existing (see below). Migration state clean: single head `1788711780`, `flask db current` = `1788711780 (head)`; `python scripts/sync_check_constraints.py --dry-run` -> **"No CHECK constraint migration required"** (0 ADD / 0 REPLACE / no orphans).
- **Bypass audit - transport REST API (NEW classification this node, do NOT silently fix):** `app/transport/api/` is live regardless of Module Toggle (`init_transport_module(app)` unconditionally called at `app/__init__.py:1039-1041`; blueprinted at `/api/transport` by `app/transport/api/__init__.py:24-39`, ~32 resources via `safe_add_resource`). The global `check_module_enabled` (`app/__init__.py:1989-2005`) keys off `path_parts[0] in ['tourism','transport','accommodation','tournament','wallet','events']`; `/api/transport/*` has `path_parts[0]=='api'`, so **NOT module-gated**. Three `@admin_required`-only (admin/super_admin/owner - no module guard, no eligibility check, no PP capability gate) direct-constructor POST endpoints: `app/transport/api/vehicle_routes.py:98-121` -> `Vehicle(**data)`; `app/transport/api/driver_routes.py:86-93` -> `DriverProfile(...)`; `app/transport/api/organisation_routes.py:88-110` -> `OrganisationTransportProfile(...)`. **Classification: PRE-EXISTING LEGACY ADMIN-PROVISIONING ENDPOINTS, NOT a Sec-13 violation.** Rationale (Sec-23): the Sec-13 hard requirement protects against a user with mere *provider intention* writing production operational resources; these endpoints require platform *admin authority* (a distinct, higher privilege, `@admin_required` = admin/super_admin/owner per `app/auth/decorators.py:29-30`), NOT provider intention - so the forbidden condition does not hold. They DO bypass the canonical eligibility+capability gate and the module toggle, so they are recorded as known legacy and deferred for gate-alignment/removal - NOT remediated (no authorization). 4B-5 report listed `organisation_routes.py:110` in its writer matrix but did not flag them; this node makes the classification explicit and durable. Sole "expanded finding"; non-blocking.
- **Verified PASS - all invariants hold:** (1) OPC audit - NO production OPC writers; only classify/legacy references; capability_service is a pure PP-delegating adapter. (2) PP model frozen per Stage-4A: single-subject XOR CHECK, String(20) not PG ENUM, unique (user_code)/(org_code), neutral (no KYC/KYB, no auto-activation, no domain-resource creation), REVOKED terminal, no internal-id leak in participation_to_dict. (3) Capability API all PP-backed; ACCOMMODATION individual activation gated on can_host; activation-eligibility gap (org/non-hosting capabilities) is the documented deferred decision (BACKLOG.md:651 / identity/routes.py:769-776), NOT a write-boundary defect. (4) Events: no PP coupling; only production domain `Event(` writer = role-gated `app/events/services.py:670`; other matches infrastructure. (5) Context: get_available_contexts/can_host/can_org_host derive from eligibility/assignments, not PP (app/auth/context.py:490-527; no PP refs inside). (6) KYC/KYB authorities unchanged (calculate_kyc_tier, OrganisationKYBService.compute_status); org creation != wallet creation; no capability activation creates a wallet. (7) Transport canonical path = module toggle + login + profile-completion + KYC tier 3 -> eligibility (fail-closed) -> intention PP row -> DriverProfile; Vehicle only via register_vehicle_internal after an existing driver profile. (8) Write-gate matrix (Property/DriverProfile/Vehicle/Event) all canonical; no production provider-intention bypass beyond the recorded admin-API legacy item.
- **Full-suite failure classification (ALL pre-existing; this baseline's additions green):** (1) `module 'app.events.services' has no attribute '_legacy'` (thread wakes after test DB teardown; benign). (2) test_notifications/test_models.py (5) - preference expectation drift. (3) test_kyc_limit_authorization - regulatory-vs-operational limits (BACKLOG:311-312). (4) attendance/guest/event-assignment tests - coordinator/bookable-property fixture drift. (5) test_registration_flow (concurrent/idempotency/waitlist) - orphaned dependency-row fixture. (6) test_payment_flow / test_payment_method_capabilities / test_booking_mode - payment/booking-code drift. (7) test_production_console - pre-existing owner-auth mismatch. (8) onboarding verified-fields (10) - known BACKLOG:638-643 family, NOT remediated. (9) test_database_contract (2 SQL-string scans) - lint-level. (10) test_accommodation_roomtype/booking_mode bookable-Property fixture gap (BACKLOG:745-746). (11) test_dead_letter_alert import error - pre-existing dangling import. None attributable to Stage-4B baseline work; NOT remediated.
- **DB / migration proof:** `flask db heads` -> `1788711780 (head)`; `flask db current` -> `1788711780 (head)`; single head, applied, no pending migration. `1788711780_sync_check_constraints.py` (down_revision `3a73c6e6cf29`) is the sanctioned wallet-ownership CHECK sync (ck_accounts_*, ck_payment_identities_*) from the 4B wallet-freeze reconciliation - generated by the sanctioned tool (Sec-20.2), not by this node. --dry-run confirms model metadata == live DB (0 drift). No new PG ENUM; constraints named ck_*.
- **Stage 5 readiness:** **READY** - all invariants proven; write-gate matrix holds; DB single-head/no-drift; mandated suites green; the sole new finding (transport REST admin API) is non-blocking legacy classified and deferred; deferred families documented. No migration or schema work needed before Event-to-Accommodation / Payment/Wallet / Escrow design.
- **Links:** STAGE_4A_UNIVERSAL_PROVIDER_ARCHITECTURE_DECISION_REPORT.md, STAGE_4B5_TRANSPORT_PROVIDER_ARCHITECTURE_DECISION_REPORT.md, STAGE_4B_ORGANISATION_CLASSIFICATION_ELIGIBILITY_RECONCILIATION.md, app/transport/api/vehicle_routes.py:98,121, app/transport/api/driver_routes.py:86,93, app/transport/api/organisation_routes.py:88,110, app/transport/api/__init__.py:24-39, app/transport/api/routes.py, app/__init__.py:1039-1041,1527-1536,1989-2005, app/auth/decorators.py:29-30, app/auth/context.py:490-527, app/events/services.py:670, app/transport/services/provider_service.py:550,731,755,803,838, app/identity/services/provider_participation_service.py:172-401, app/identity/routes.py:580-632,769-776,786-842, app/wallet/models/ledger.py, migrations/versions/1788711780_sync_check_constraints.py, tests/test_stage4b2_capability_enforcement.py, tests/test_stage4b3_organisation_capabilities.py, tests/test_stage4b5_transport.py, tests/test_stage4b6_org_write_gate.py, tests/test_capability_operations.py, tests/test_provider_participation.py, tests/test_onboarding_stage4.py, tests/test_can_org_host.py, BACKLOG.md:638-655,729,745

---

## Stage 5-1 Event-Accommodation Assignment Ownership Boundary - IMPLEMENTED (minimal contract fix + 10 negative tests)
- **Status:** DONE (2026-09-06) - code-only; no migration; single head 1788711780 unchanged
- **Raised:** 2026-09-06
- **Context:** Stage 5-1 required tracing one complete accommodation assignment and proving ownership boundaries (Events coordinates, Accommodation owns capacity/booking/inventory). Ground truth trace exposed a CONFIRMED ownership violation: `app/events/guest_coordination_service.py` imported `app.accommodation.models.guest_registration.GuestRegistration` and called `slot.remove(...)` directly during reassignment and cancellation, bypassing the `AccommodationCoordinationContract` docstring rule ("Events MUST NOT import accommodation models or write accommodation tables directly").
- **What was implemented (minimal, using the existing contract - no new architecture):** (1) `app/accommodation/services/coordination_contract.py` - added `AccommodationCoordinationContract.release_event_guest_slot(booking_reference, *, event_assignment_id, removed_by_user_id, reason) -> bool`: idempotent, finds the active slot by (booking_id, event_assignment_id), calls `slot.remove()`, flushes; raises `CoordinationContractError` MISSING_RELEASE_REASON / BOOKING_NOT_FOUND. (2) `app/events/guest_coordination_service.py` - removed the `GuestRegistration` import and direct `.remove()` calls; reassignment block (formerly ~596-602) now calls the contract with `reason="reassigned"`; cancellation block (formerly ~683-701) now calls the contract with `reason="assignment cancelled"`, stores `released_slot`, and re-applies through the contract after `NotificationService.send()` (mirrors the previous re-apply behavior, keeping the token/expiry clearing and notification flow intact). `EventAssignment.accommodation_booking_id` remains a bare `BigInteger` `CROSS_MODULE_REF` (no FK) - confirmed coordination record, not ownership.
- **Tests:** NEW `tests/test_assignment_ownership_boundary.py` -> **10 passed**: (1) assignment does not mutate booking capacity/status; (2) assignment creates no new AccommodationBooking; (3) `event_assignments.accommodation_booking_id` has zero FKs + `id_kind == IDKind.CROSS_MODULE_REF`; (4) booking of another event/owner rejected (`BOOKING_EVENT_MISMATCH`); (5) cancellation releases the slot through the contract (spy on `release_event_guest_slot`, old slot deactivated, no direct write); (6) Events module source has no `GuestRegistration()`/`slot.remove(`/guest_registration import; (7) no wallet account created; (8) no payment transaction created; (9) no ledger entries created; (10) full assign->reassign->cancel cycle leaves booking status untouched (state machine owned by accommodation). Existing coordination suites still green: `test_guest_coordination_accommodation.py` + `test_guest_assignment_account_optional.py` + `test_accommodation_lifecycle_verification.py` -> **49 passed**.
- **Pre-existing (do NOT silently fix):** `tests/test_event_accommodation_assignment_flow.py` -> 5 passed / **4 failed** (`test_normal_shared_booking_capacity`, `test_event_assignment_completion_at_capacity`, `test_reassignment_deactivates_old_slot`, `test_cancellation_frees_capacity`). Root cause CONFIRMED as B-class test-DB state pollution: the shared `afcon360_test` DB has a persisted `SystemConfig.MODULE_FLAGS` override `{"tourism": true, "transport": false, "accommodation": false}` (verified via temp diagnostic script `C:\Users\OBED\AppData\Local\Temp\opencode\check_module_flags.py` printing STORED/MERGED/APP-config). `app/middleware/reload_modules.py:7-14` (`@app.before_request` -> `ModuleToggleService.load_overrides_into_app()`) merges that override into `current_app.config["MODULE_FLAGS"]` at request/runtime, making `module_enabled("accommodation")` false and `GuestCoordinationService._module_available` raise `ACCOMMODATION_UNAVAILABLE`; event-routes `@module_enabled` aborts 404. Same 4 failed identically BEFORE the Stage 5-1 edit (4B-7 baseline family), and they fail even in isolation - proving this is DB state, not code. Remedy (operator action, NOT performed): either delete the stale `SystemConfig` MODULE_FLAGS row in `afcon360_test` or run `python scripts/setup_test_db_schema.py` to rebuild the test DB; the tests then pass (validated by the isolated green runs of the same service paths in the new + existing coordination suites).
- **Deferred (new):** (a) the persisted-MODULE_FLAGS test-DB pollution above MUST be cleared/rebuild documented as a required manual step before the next full-suite run claims a clean event-assignment family; (b) `tests/test_guest_coordination_accommodation.py::test_reassignment_deactivates_old_slot` still documents the old-slot-not-deactivated limitation in its docstring/commented assert while the stricter `test_event_accommodation_assignment_flow.py::test_reassignment_deactivates_old_slot` asserts it - the two files disagree; the service now deactivates via the contract, so the STRICTER test is authoritative and the coordination-file docstring/comment should be reconciled next time that file is touched.
- **DB proof:** no migration created/applied; `flask db heads` and `flask db current` both = `1788711780 (head)` (single head, unchanged). Schema untouched.
- **Links:** app/accommodation/services/coordination_contract.py:124-168, app/events/guest_coordination_service.py:580-605,686-702,745-755, app/events/models.py:1113-1138, app/utils/id_kinds.py:7, app/middleware/reload_modules.py:7-14, app/utils/module_toggle_service.py:41,80, app/config.py (TestingConfig MODULE_FLAGS all True), tests/test_assignment_ownership_boundary.py, tests/test_event_accommodation_assignment_flow.py (4 B-class flaky), tests/test_guest_coordination_accommodation.py (docstring/slot discrepancy), BACKLOG.md 4B-7 entry (failure family list)

## Stage 5-2 Event-Accommodation Assignment Operational Lifecycle - VERIFIED (runtime trace + test-env remediation + focused gap tests)
- **Status:** DONE (2026-09-07) - verifying/operational only; no implementation change, no migration created/applied; single additional focused test file added; AUTO-STOP honored (no Stage 5-3 / Transport / Payment / Wallet / Escrow work started)
- **Raised:** 2026-09-07
- **Context:** Stage 5-2 required verifying the complete Event -> Accommodation assignment workflow against the approved spec (foundational assumptions: explicit authorization; Accommodation contract points; Authenticated/confirmable + Owner-restricted; task-positive full lifecycle; task-negative edge cases; disjoint Event/Accommodation domains) using the Stage 5-1 ownership-boundary results as the base.
- **Runtime trace completed (evidence, no code change):** `GuestCoordinationService.assign_accommodation()` (app/events/guest_coordination_service.py:571-633) verified end-to-end along the 12-step chain: (1) authz `can_assign_accommodation` -> `has_guest_operation_permission(...,'accommodation.assign')` -> `EVENT_COORDINATION_FORBIDDEN`; (2) `_module_available('accommodation')` -> `ACCOMMODATION_UNAVAILABLE`; (3) registration lookup (confirmed, same event) -> `INVALID_EVENT_REGISTRATION` / `REGISTRATION_NOT_CONFIRMED`; (4) `_resolve_accommodation_booking` (`with_for_update`, ref or int-id, event-link/owner-link/context checks, status/date/room-active/capacity validation) -> `ACCOMMODATION_BOOKING_NOT_FOUND`, `INVALID_EVENT_RESOURCE`, `BOOKING_EVENT_MISMATCH`, `ACCOMMODATION_BOOKING_UNAVAILABLE`, `ACCOMMODATION_ROOM_UNAVAILABLE`, `ACCOMMODATION_CAPACITY_EXCEEDED`; (5) `_assignment` fetch-or-create; (6) idempotency no-op (same booking); (7) `_provider_allows_assignment` -> `ALLOCATION_REJECTED`; (8) set `assignment.accommodation_booking_id`; (9) reassignment -> `release_event_guest_slot` via contract (reason='reassigned'); (10) bridge `issue_accommodation_for_assignment` -> `ensure_event_guest_slot` (booking row lock + advisory xact lock + authoritative capacity count -> `ACCOMMODATION_BOOKING_FULL` / `BRIDGE_FAILED`) + `acc_link_token_hash` (expiry = max(event.end, booking.check_out)+7d) + best-effort email; (11) `_commit_assignment` -> status='active', domain event `EVENT_ACCOMMODATION_ASSIGNED`/`_CHANGED`, forensic audit (`COORDINATION_AUDIT_FAILED`), single `db.session.commit()` (atomic); (12) any `CoordinationError`/exception -> rollback, no partial state. Contracts confirm `AccommodationCoordinationContract` is the sole write boundary; `event_assignments.accommodation_booking_id` remains bare `BigInteger` CROSS_MODULE_REF. Route wiring: `app/events/routes_accommodation.py:160` (single) / `:242` (bulk); `app/events/assignment.py:504/:646`; `app/events/guest_management.py:849` group bulk assign -> `assign_accommodation` at `:885`.
- **Test-DB environment remediation (authorized by task §4, using §21.1 canonical paths):** (a) confirmed stale persisted `SystemConfig.MODULE_FLAGS` in `afcon360_test` per Stage 5-1 finding -> deleted the row (`clear_module_flags.py`); verified STORED=None / merged all-True, clean. (b) discovered second B-class issue: `tests/test_event_accommodation_assignment_flow.py` + `test_guest_coordination_accommodation.py` failing with `listing_type` column missing (27 setup errors) because conftest fast-path reuses an existing schema and the `listing_type` migration existed only for the dev DB; the mandated §21.1 rebuild script `scripts/setup_test_db_schema.py` HANGS on this machine (after dropping/recreating the test DB it stalls in the stamp/create path; 300s timeout) - recovery was plain `pytest`, whose conftest auto-bootstrapped the empty DB via `db.create_all()` + `stamp head` ($21.1), rebuilding the full schema from current models. KNOWN ISSUE to record: `scripts/setup_test_db_schema.py` not reliable in this environment (hang/deadlock); use the documented `pytest` conftest bootstrap or drop+create manually.
- **Tests (focused, after remediation):** mandated suite `test_event_accommodation_assignment_flow.py` + `test_guest_coordination_accommodation.py` + `test_assignment_ownership_boundary.py` + `test_guest_assignment_account_optional.py` -> **37 passed / 0 failed / 0 errors / 0 skipped** (was 10 passed / 27 errors under stale schema). NEW `tests/test_stage5b2_assignment_lifecycle.py` -> **9 passed** closing genuine coverage gaps with zero new architecture: INVALID_EVENT_REGISTRATION (unknown registration ref), ACCOMMODATION_BOOKING_NOT_FOUND (unknown booking ref), INVALID_EVENT_RESOURCE (blank booking ref), ACCOMMODATION_BOOKING_UNAVAILABLE (status='cancelled'), ACCOMMODATION_ROOM_UNAVAILABLE (room_type.is_active=False), ACCOMMODATION_CAPACITY_EXCEEDED (num_guests 3 > room max 2), BOOKING_EVENT_MISMATCH (cross-context booking tagged to another event, non-owner), ALLOCATION_REJECTED (provider duck-typed `can_assign_guest` veto), and positive owner-linked cross-context booking remains assignable (owner-linked path). Combined targeted run: **46 passed**. New file writes NO MODULE_FLAGS and full coverage scan confirms remaining codes already covered at unit level (incl. ACCOMMODATION_UNAVAILABLE at test_guest_coordination_contract.py:147-156, BOOKING_EVENT_MISMATCH ownership test, BULK via bulk routes).
- **DB proof:** no migration created/applied by this work. Working-tree migration files `f1fe91ef0ebf_add_listing_type_column_to_.py`, `1788711780_sync_check_constraints.py`, `1788729103_sync_check_constraints.py` are untracked pre-existing/environment drift (appeared during this session; not created by this agent). `flask db heads` / `flask db current` = `1788729103 (head)` on the dev DB. Test DB: `db.create_all()` schema (source of truth = models), `alembic_version` stamped `1788729103`, no MODULE_FLAGS rows, `listing_type` present.
- **Deferred (new):** (a) `scripts/setup_test_db_schema.py` hang on this machine should be diagnosed or replaced as the canonical rebuild path (§21.1) - recorded, NOT fixed (out of scope); (b) the pre-existing untracked migration family (f1fe91ef0ebf / 1788711780 / 1788729103) needs an operator decision (commit/retire) and is outside this task; (c) DATES_MISMATCH guard (`check_in` absent) is not integration-testable with current NOT NULL columns (defensive legacy-data path) - noted, no test added; (d) assertion-plugin/LSP noise in unrelated test files (is_active/is_verified column typing) is pre-existing, not addressed. Stage 5-1 deferred items (a)-(b) still stand.
- **Links:** app/events/guest_coordination_service.py:571-633 (assign), ~407-470 (_resolve_accommodation_booking; date/room/capacity checks ~442-467), app/events/routes_accommodation.py:160,242, app/events/assignment.py:504,646, app/events/guest_management.py:849,885, app/accommodation/services/coordination_contract.py (sole write boundary), app/accommodation/models/booking.py (status VARCHAR(50), check_in/check_out NOT NULL, no can_assign_guest attr), tests/test_stage5b2_assignment_lifecycle.py, tests/test_guest_coordination_accommodation.py (fixture pattern), tests/test_guest_coordination_contract.py:147-156, tests/conftest.py (auto-bootstrap), scripts/setup_test_db_schema.py (hang - deferred), AGENTS.md §15, §20, §21.1

---

## Stage 5-3 Event-Accommodation Reservation/Handoff Architecture - VERIFIED (discovery-first report + focused tests; no implementation, no new architecture)
- **Status:** DONE (2026-09-07) - investigation/report + focused test file only; NO app/implementation change; NO migration created/applied; AUTO-STOP honored (no Stage 5-4/5-5, Transport, Payment, Wallet, Escrow work started)
- **Raised:** 2026-09-07
- **Context:** Stage 5-3 required (per handoff) resolving the "reserve/hold/block capability" gap and verifying the Event -> Accommodation service handoff and the existing reservation architecture. Discovery produced a §19 investigation report (`STAGE_5_3_ACCOMMODATION_HANDOFF_VERIFICATION.md`, 10 items) reaching the verdict: the reserve -> hold/block -> guest-registration-link -> consume -> complete capability **ALREADY EXISTS** end-to-end; Event is already a thin consumer via `AccommodationCoordinationContract` (proven in Stage 5-1/5-2). No new booking entity, no new service, no architectural change required.
- **What was verified (10 §19 items, full evidence in the report):** (1) Normal booking flow exists (property -> room availability -> book -> confirm flow). (2) Availability/capacity = derived counting (`num_guests` vs `max_guests`), not an atomic decrement counter; temporary stock control via `InventoryBlock`/`RoomHold`; responses 403/409/400; rows preserved. (3) Group booking = `rooms_requested=N` + `group_booking_id`; no block-reservation entity (status, cancels, and `guest_count()` bound to `num_guests`). (4) Guest registration flow: capped multi-use `BookingRegistrationLink` + `/r/<token>` form (409 when full) + `/assignment/<token>` + `release_unmatched_guest`; 6 code contributors. (5) Consumption derived; slot capacity enforced by row-locked insert (`insert_with_lock`), link set to active-when-full; no separate counter columns. (6) Event-side integration owns NOTHING; `AccommodationCoordinationContract` (`ensure_event_guest_slot`, `release_event_guest_slot`) is the sole write boundary. (7) Event = thin consumer via `accommodation_bridge.py` + `GuestCoordinationService`; the bridge uses only `ensure_event_guest_slot` + `CoordinationContractError`; guests may be read as orphans (no `db.session.add` on accommodation models). (8) NO architectural shortfall - event flow is a relationship/coordination arrangement over existing accommodation state, already authorized (assignment approval confirmed) and runtime-trace-verified. (9) Minimal implementation = the report + focused tests (below) ONLY; no code change. (10) No migrations, no state-machine/policy-editor edits, no `EventAccommodationBooking` entity, no silent fixes of the pre-existing test defects.
- **6 failing tests classified (ALL pre-existing test-fixture/contract defects, NOT Stage 5-1/5-2 regressions; verified via `git log`: both the service `app/events/accommodation_booking_service.py` and the test file `tests/test_attendee_accommodation_booking.py` were last touched solely by commit `fbc7491`, shipped together; neither Stage touched them):** (1) `test_list_available_properties` - `assert 0 >= 1`: fixture creates NO RoomType, so the property is filtered out by `has_capacity`; ordering-dependent (passes in a combined run when another suite leaves a RoomType row behind). (2) `test_get_booking_requirements` - `KeyError: 'has_booking'`: the service returns `BookingPolicyEvaluator.get_booking_requirements(booking)` directly (keys `can_confirm`/`can_check_in`/`payment_policy`/`financial_summary`, never `has_booking`) while the test asserts a wrapped shape. (3) `test_cancel_attendee_booking` - `AttributeError: 'FixtureFunctionDefinition' object has no attribute 'id'`: fixture signature (line 423) is `(self, app, test_property, test_event, attendee_registration)` but the body (line 446) uses `test_organizer_user.id` without requesting that fixture. (4)-(6) `test_available_properties_api`, `test_book_accommodation_api`, `test_book_accommodation_pay_on_arrival_api` - 401 Unauthorized: tests set `session['user_id']` but routes use Flask-Login `@login_required` which reads `session['_user_id']`. Per §9/§34 these were DOCUMENTED, NOT silently fixed (no authorization).
- **Focused tests:** NEW `tests/test_stage5b3_handoff_architecture.py` -> **8 passed / 0 failed**: (1) `test_accommodation_slot_path_exists_without_event_wiring` - ordering/capacity/freeing logic works WITHOUT any event involvement (event-handoff path independence); (2) `test_event_handoff_creates_coordination_slot` - `ensure_event_guest_slot` + placeholder (room-form/link key fields) + new capacity; (3) `test_pool_consumption_decrements_available_capacity` - occupied-of-N pool 100->99->98, refills via slot removal; (4) `test_no_stock_request_rejected_by_accommodation_capability` - 0-stock / >max / already-at-capacity rejections (`= 0` -> `Room is not available`, >max -> `Capacity exceeded`, at-capacity -> `Room is full`); (5) `test_events_side_never_writes_accommodation_directly` (renamed from `..._imports...`) - source-strength ownership: `accommodation_bridge` + `guest_coordination_service` never import/construct `GuestRegistration`/`BookingRegistrationLink`, the bridge routes slot creation via `ensure_event_guest_slot`, and the coordination service releases via `release_event_guest_slot`; (6) `test_release_recovers_abandoned_slot_capacity` - release placeholder -> capacity restored; (7) `test_completion_resolves_same_slot_and_reference` - completion resolves and deactivates the same slot; (8) `test_ensure_event_guest_slot_idempotent` - second call returns reference key rather than duplicating capacity. Note: the final ownership assertion corrects the earlier intermediate form - the coordination service creates via `issue_accommodation_for_assignment` (bridge) and releases via `release_event_guest_slot` directly, so "every module contains `ensure_event_guest_slot`" was wrong; the corrected test asserts the create/release split. LSP diagnostics on the file (ColumnElement bool / None typing) are pre-existing static-analysis noise matching other test files, not runtime failures.
- **Verification (mandated proportions, exact counts):** new Stage 5-3 file **8 passed**; targeted Stage 5-1/5-2 + accommodation suites (`test_stage5b2_assignment_lifecycle.py`, `test_assignment_ownership_boundary.py`, `test_guest_coordination_accommodation.py`, `test_guest_assignment_account_optional.py`, `test_accommodation_lifecycle_verification.py`, `test_fix_accommodation_unit_availability.py`, `test_accommodation_capacity_rules.py`) -> combined **90 passed / 0 failed / 0 errors / 0 skipped**; `test_event_accommodation_assignment_flow.py` + `test_attendee_accommodation_booking.py` -> **19 passed, 6 failed** (the 6 failures are EXACTLY the pre-existing attendee-file defects classified above, unchanged); startup sanity `python -c "from app import create_app"` -> exit 0, `STARTUP_OK`. No migration created/applied; migration family (`f1fe91ef0ebf` / `1788711780` / `1788729103`) untouched as recorded in Stage 5-2.
- **Deferred (new, do NOT silently fix):** (a) the 6 pre-existing test defects in `tests/test_attendee_accommodation_booking.py` (classified above; would need fixture/RoomType creation + `_user_id` session + request-time booking-requirements shape + fixture-signature fix - a proper node, NOT part of this graph); (b) report item (4) notes the `/r/<token>` shared-link capacity edge (409 when full, link active-when-full) is already evidenced by existing tests (`test_event_accommodation_assignment_flow.py:194`, `:836`, `:902`) - no action; (c) stale comment in `guest_coordination_service.py` (lines ~596/694) still describes the pre-§18.1 contract approach - reconcile next touch (Stage 5-1 deferred (b) family). Stage 5-1/5-2 deferred items still stand (MODULE_FLAGS remediation validated in 5-2; `setup_test_db_schema.py` hang; migration-family operator decision; DATES_MISMATCH; coordination-file docstring/slot discrepancy).
- **DB proof:** no migration created/applied by this work; no `SystemConfig.MODULE_FLAGS` writes; schema untouched; migration head/current unchanged from Stage 5-2 (`1788729103` dev / `1788729103` test stamp, single head).
- **Links:** STAGE_5_3_ACCOMMODATION_HANDOFF_VERIFICATION.md (10-item report), app/events/accommodation_bridge.py (ensure-side), app/events/guest_coordination_service.py:207,409,591,687 (read-only AccommodationBooking), :600,697,750 (release_event_guest_slot), :168,:330 (events-side adds only), app/accommodation/services/coordination_contract.py, app/events/accommodation_booking_service.py (attendee self-service path - fbc7491), tests/test_stage5b3_handoff_architecture.py (8 passed), tests/test_attendee_accommodation_booking.py (6 pre-existing failures), tests/test_event_accommodation_assignment_flow.py:194,836,902, tests/test_guest_coordination_accommodation.py (fixture pattern), git fbc7491, AGENTS.md §6, §9, §15, §16, §19, §34, §38, §39

---

## Stage 5-4 Assignment ↔ Accommodation Booking Synchronization - VERIFIED WITH DEFECT FOUND (discovery/verification only; report + 2 proof tests; NO implementation, NO migration)
- **Status:** DONE (2026-09-07) - read-only audit + focused proof tests only; report produced; **verdict: DEFECT FOUND - implementation authorization required** (classification C); AUTO-STOP honored (no Stage 5-5, Transport, Stage 6, Payment, Wallet, Escrow work); AUTO-STOP honored after BACKLOG update.
- **Raised:** 2026-09-07
- **Context:** Stage 5-4 asked (discovery-only, Q1-Q8, 15-section report) whether Assignment ↔ Accommodation Booking synchronization is correctly achieved through the Event → Accommodation contract (or another mechanism) and to classify gaps A/B/C/D. Full evidence: `STAGE_5_4_ASSIGNMENT_BOOKING_SYNCHRONIZATION_AUDIT.md` (15 sections).
- **What was verified (Q1-Q8):** (Q1) Event→Booking pointer is durable and single-transaction: `assign_accommodation` sets `assignment.accommodation_booking_id`, bridge sets token hash + `ensure_event_guest_slot`, ONE commit at `_commit_assignment` (:567). (Q2) Chain reconstructible both ways: `GuestRegistration.event_assignment_id` is a REAL FK → `event_assignments.id` (ondelete SET NULL, guest_registration.py:81); completion route token→assignment→booking→slot. (Q3) Booking cancelled AFTER assignment does NOT propagate: `BookingService.cancel_booking` (:1589) releases dates/blocks, transitions CANCELLED (or REFUNDED for refundable pay_now), records policy snapshot — never touches EventAssignment/GuestRegistration, emits no event. (Q4) Not part of prompt; subsumed in Q3/Q5 (acceptance). (Q5) Reassignment is atomic with NO committed intermediate window: set new id → release old slot → ensure new slot → single commit; failure rolls back (proved). (Q6) Completion = `/assignment/<token>` resolves same slot but does NOT revalidate booking status (cancelled booking still completable). (Q7) Shared capacity is Accommodation-owned and derived (active_count vs allowed, row-locked insert); Event keeps only a dependency-free count; no-stock rejected by capability. (Q8) NO accommodation→event mechanism exists — `BookingStateMachine` has no emit hook; `app/accommodation` emits zero domain events; Events emits `EVENT_ACCOMMODATION_ASSIGNED/CHANGED` + `EVENT_COORDINATION_CANCELLED` (registry.py:114-118, policy.py:416-440).
- **Classification:** Gap A = N/A (sync exists). Gap B = YES (Accommodation-initiated cancellation not surfaced to Event). Gap C = YES (genuine defect): C1 stale EventAssignment + live `acc_link_token_hash` + active GuestRegistration slot after `BookingService.cancel_booking`; C2 unguarded completion (`assignment_completion` has no booking.status check); C3 read staleness (dashboard/assignment stats count `accommodation_booking_id IS NOT NULL` as assigned regardless of status; inventory filters but does not remediate); C4 secondary leak (attendee self-service `cancel_attendee_booking` clears the pointer but never releases the slot). Gap D = NOT required (consumer-side revalidation satisfies the requirement without new accommodation→event architecture).
- **Minimal recommended correction (NOT implemented - requires authorization):** (1) Event read paths treat booking outside {held, confirmed, pending, pending_approval} as "not assigned"; (2) `assignment_completion` revalidates booking status and fails closed; (3) Event-side call of `AccommodationCoordinationContract.release_event_guest_slot` + clear assignment/token on invalid-reference detection; (4) `cancel_attendee_booking` releases the slot via contract; (5) doc corrections (Stage 5-3 symbol, dead `_token_for_booking`). No schema, no migration, no accommodation→event dependency, no `EventAccommodationBooking`.
- **Focused tests:** NEW `tests/test_stage5b4_sync_synchronization.py` -> **2 passed / 0 failed**: (1) `test_reassignment_is_atomic_no_partial_committed_window` - monkeypatched bridge capacity failure after old-slot release; prove rollback leaves assignment on OLD booking, OLD slot active, NEW booking slotless (no visible unassigned window); (2) `test_booking_cancel_after_assignment_is_not_propagated_to_event` - `BookingService.cancel_booking` → refundable pay_now fixture ends REFUNDED (outside assignable set; NOTE: creation-path discovery: refundable+guaranteed pay_now → REFUNDED not CANCELLED); same booking is simultaneously rejected for NEW assignment (`ACCOMMODATION_BOOKING_UNAVAILABLE`) while the existing EventAssignment still references it, slot still active, token still live. LSP diagnostics on the file are pre-existing Column-type inference noise, not runtime failures.
- **Verification (mandated proportions, exact counts):** 9-file suite (`test_event_accommodation_assignment_flow.py`, `test_guest_coordination_accommodation.py`, `test_guest_coordination_contract.py`, `test_assignment_ownership_boundary.py`, `test_stage5b2_assignment_lifecycle.py`, `test_stage5b3_handoff_architecture.py`, **NEW** `test_stage5b4_sync_synchronization.py`, `test_accommodation_lifecycle_verification.py`, `test_guest_assignment_account_optional.py`) -> **93 passed / 0 failed / 0 errors / 0 skipped**; startup `python -c "from app import create_app"` -> exit 0, **STARTUP_OK**; migration head single **`1788729103`** (dev + test), unchanged.
- **Corrections recorded (discovery):** (1) `release_unmatched_guest` does NOT exist - actual roster removal is `RegistrationService.remove(row, ...)` → `GuestRegistration.remove()` (routes.py:2914; guest_registration.py:143 sets `is_active=False`) - Stage 5-3 report item (4) referenced a nonexistent symbol; (2) `_token_for_booking` in `accommodation_bridge.py:32` is dead code (defined, never called); (3) creation-path discovery: `BookingService.cancel_booking` routes a refundable guaranteed pay_now booking to REFUNDED, not CANCELLED.
- **Deferred (new, do NOT silently fix):** authorization required to implement the minimal correction in Section 13 of the report (C1-C4); Stage 5-3 deferred items still stand (6 pre-existing attendee-file defects, stale `guest_coordination_service.py` comments ~596/694, MODULE_FLAGS remediation, `setup_test_db_schema.py` hang, migration-family operator decision, DATES_MISMATCH, docstring/slot discrepancy).
- **DB proof:** no migration created/applied; no schema change; no `SystemConfig.MODULE_FLAGS` writes; migration head/current unchanged (`1788729103` dev / `1788729103` test).
- **Links:** STAGE_5_4_ASSIGNMENT_BOOKING_SYNCHRONIZATION_AUDIT.md (15-section report), app/events/guest_coordination_service.py:571-633 (assign), 668+ (cancel - full sync), app/events/accommodation_bridge.py:45 (link token + ensure; dead `_token_for_booking` :32), app/accommodation/services/coordination_contract.py (sole write boundary), app/events/accommodation_booking_service.py:288-314,469-507 (attendee path - clears pointer, leaks slot), app/accommodation/services/booking_service.py:1589-1770 (no event sync), app/accommodation/state_machine/booking_states.py (no emit hooks), app/accommodation/routes.py:2767 (completion - no status check), :3673 (guest_cancel_booking), app/events/services.py:566 (_cancel_event_accommodation_bookings), app/events/routes_accommodation.py:71-86 + app/events/assignment.py:308-314 (read staleness), app/notifications/events/registry.py:114-118 + policy.py:416-440 (events-side-only emission), tests/test_stage5b4_sync_synchronization.py (2 passed), AGENTS.md §6, §9, §17, §20, §34, §38, §39

---

## Stage 5-4 Correction (C1-C4) — IMPLEMENTED + VERIFIED (application-layer sync correction only; no migration, no new architecture)
- **Status:** DONE (2026-09-07) — resolves the "DEFECT FOUND" Stage 5-4 entry above; implementation authorized and completed; 4 new regression tests; 9-file focused suite 97 passed / 0 failed / 0 errors / 0 skipped.
- **Raised:** 2026-09-07
- **Context:** Authorized implementation of the minimal correction (report Section 13): (C1) stale EventAssignment + live `acc_link_token_hash` + active GuestRegistration slot after booking cancel; (C2) unguarded completion; (C3) read-path staleness (dashboard / assignment stats / attendee list); (C4) attendee self-service cancel leaks the slot.
- **What was implemented:** (C1/C3) New single source of truth `ACCOMMODATION_ASSIGNABLE_STATUSES = frozenset(("held","confirmed","pending","pending_approval"))` in `guest_coordination_service.py`; helpers `_accommodation_booking_assignable(booking)`, `_assignable_accommodation_booking_ids(bookings)`, `_accommodation_assignment_status(assignment)`; `_resolve_accommodation_booking`, dashboard rows, dashboard aggregate counts (with `unique_assignments` dedup by `assignment.id` — one assignment can appear under both `('registration', id)` and `('user', attendee_id)` keys), and guest_journey status all revalidate assignability; `assignment.py` stats `accommodation_assigned` count now JOINs `AccommodationBooking` filtered `is_deleted=False` + `status.in_(assignable)` and `list_attendees` skips stale accommodation-only assignments. (C2/C3) `assignment_completion` route (routes.py ~:2784) revalidates `not booking or booking.is_deleted or not assignable` → calls new idempotent `retire_invalid_accommodation_assignment(assignment, removed_by_user_id=None, reason="booking no longer assignable during assignment completion")` (releases slot via `AccommodationCoordinationContract.release_event_guest_slot`, skips only on `BOOKING_NOT_FOUND`/deleted booking, clears `accommodation_booking_id` + `acc_link_token_hash` + `acc_link_expires_at`, sets status `"active"` if transport else `"cancelled"`, sets `assigned_at`, single commit, returns False when nothing to do) → fail closed 404 expired. (C4) `cancel_attendee_booking` (accommodation_booking_service.py) — after `booking.cancel()` success: release slot via contract (skip only on `BOOKING_NOT_FOUND`), clear pointer + token hash/expiry, single commit, rollback on exception.
- **Tests:** `tests/test_stage5b4_sync_synchronization.py` grew from 2 → **6 passed / 0 failed**: kept the 2 originals (atomic reassignment; cancel-not-propagated gap doc) + NEW `test_c1_cancelled_booking_is_not_presented_as_active_assignment`, `test_c2_completion_route_fails_closed_for_cancelled_booking` (HTTP GET → 404 + retirement asserts; note: the client request tears the session down so the test captures primitive ids before the request and re-fetches rows after), `test_c3_retire_invalid_assignment_is_idempotent`, `test_c4_attendee_cancel_releases_slot_and_clears_pointer`. 9-file focused suite (Stage 5-1..5-4 + accommodation) → **97 passed / 0 failed / 0 errors / 0 skipped**.
- **Verification:** startup `python -c "from app import create_app"` → exit 0, `STARTUP_OK`; migration head single **`1788729103`** unchanged; no migration created/applied; no `SystemConfig.MODULE_FLAGS` writes; no schema change; no wallet/payment/escrow/transport work; AUTO-STOP honored after this record.
- **Deferred (remain open):** doc corrections from report Section 13 item (5): stale Stage 5-3 symbol/comments in `guest_coordination_service.py` (~596/694) and dead `_token_for_booking` (`accommodation_bridge.py:32`) — cosmetic, not touched (scope discipline). Prior Stage 5-1/5-3/5-4 deferred items still stand (6 pre-existing attendee-file defects, MODULE_FLAGS remediation, `setup_test_db_schema.py` hang, migration-family operator decision, DATES_MISMATCH, notifications legacy-type silent drop, Task 3/Task 4).
- **Links:** STAGE_5_4_ASSIGNMENT_BOOKING_SYNCHRONIZATION_AUDIT.md, app/events/guest_coordination_service.py (constant + 3 helpers; `_resolve_accommodation_booking`; dashboard dedup; `retire_invalid_accommodation_assignment`) , app/events/assignment.py (stats count + `list_attendees`), app/events/accommodation_booking_service.py (`cancel_attendee_booking`), app/accommodation/routes.py (completion guard), app/accommodation/services/coordination_contract.py (`release_event_guest_slot` — sole write boundary), tests/test_stage5b4_sync_synchronization.py (6 passed), AGENTS.md §5, §6, §17, §20, §34, §38, §39

---

## Stage 5-5 Cancellation / Reassignment Lifecycle — VERIFIED + 2 DEFECTS FIXED (minimal app-layer fixes only; no migration, no new architecture)
- **Status:** DONE (2026-09-07) — lifecycle matrix A–H verified against code; 2 genuine failure-path defects found and fixed; 10 new lifecycle/regression tests; 10-file focused Stage 5 suite → 107 passed / 0 failed / 0 errors / 0 skipped.
- **Raised:** 2026-09-07
- **Context:** Stage 5-5 closed the full cancellation/reassignment matrix (A coordinator cancel, B attendee cancel, C accommodation-side cancel not propagated, D repeated-cancel idempotency, E atomic reassignment, F cancel→reassign, G reassign→cancel, H cross-context rejection). Matrix A–H held in code via the Stage 5-4 primitives (contract slot release, single-commit pointer+token clear, fail-closed retire, event-side cancel). The inspection surfaced TWO unguarded `release_event_guest_slot` call sites related to a missing/deleted OLD booking.
- **What was fixed (both in `app/events/guest_coordination_service.py`):** (D1) coordinator `cancel()` at the accommodation branch — the old-booking slot release raised an unguarded `CoordinationContractError("BOOKING_NOT_FOUND")` when the booking had been soft-deleted, surfacing as an HTTP 500. Now wrapped: skip only `BOOKING_NOT_FOUND` (log + continue), re-raise others — matching the established skip pattern in `cancel_attendee_booking`/`retire_invalid_accommodation_assignment`. (D2) reassignment path — the old-booking slot release similarly raised `BOOKING_NOT_FOUND`, aborting an otherwise valid reassignment to a new booking with `COORDINATION_FAILED` (500). Now wrapped identically: skip only `BOOKING_NOT_FOUND` (log + continue) so the reassignment completes. Both changes are pure Python; `current_app` was already imported in the file. No schema, no migration, no MODULE_FLAGS, no architecture change.
- **Tests:** NEW `tests/test_stage5b5_cancellation_reassignment_lifecycle.py` → **10 passed / 0 failed**: A–H matrix (test_a…test_h) + 2 regression tests (`test_d1_coordinator_cancel_survives_deleted_old_booking`, `test_d2_reassignment_survives_deleted_old_booking`). Combined Stage 5 focus suite (test_assignment_ownership_boundary, test_stage5b2_assignment_lifecycle, test_stage5b3_handoff_architecture, test_guest_coordination_accommodation, test_guest_coordination_contract, test_accommodation_lifecycle_verification, test_guest_assignment_account_optional, test_event_accommodation_assignment_flow, test_stage5b4_sync_synchronization, test_stage5b5_cancellation_reassignment_lifecycle) → **107 passed / 0 failed / 0 errors / 0 skipped** (was 97 in 9 files at Stage 5-4; +10 from the new file).
- **Verification:** startup `python -c "from app import create_app"` → exit 0, `STARTUP_OK`; migration head single **`1788729103`** unchanged; `flask db current` = `1788729103 (head)`; no migration created/applied; no `MODULE_FLAGS` writes; no schema change; no wallet/payment/escrow/transport work; AUTO-STOP honored after this record.
- **Deferred (remain open):** all earlier Stage 5-1/5-3/5-4 deferred items stand (6 pre-existing attendee-file defects, MODULE_FLAGS remediation, `setup_test_db_schema.py` hang, migration-family operator decision, DATES_MISMATCH, notifications legacy-type silent drop, Task 3/Task 4, Stage 5-4 item (5) cosmetic doc corrections).
- **Links:** app/events/guest_coordination_service.py (cancel accommodation branch + reassign path slot-release guards), tests/test_stage5b5_cancellation_reassignment_lifecycle.py (10 passed), STAGE_5_4_ASSIGNMENT_BOOKING_SYNCHRONIZATION_AUDIT.md, AGENTS.md §5, §6, §17, §20, §34, §38, §39

---

## Stage 5-6 Full Stage 5 Verification Gate - COMPLETE (verification/audit only; no implementation, no migration) → RECOMMEND STAGE 5 CLOSED
- **Status:** DONE (2026-09-07) - read-only verification gate; verdict **PASS WITH DEFERRED ITEMS**; Stage 5 closure recommended; AUTO-STOP honored (no Transport, Payment, Wallet, Escrow, Stage 6 work)
- **Context:** Stage 5-6 re-verified all Stage 5 architectural invariants IN-1..INV-5 against current source (INV-1 domain ownership: event write surface = contract only; INV-2 capacity = Accommodation-owned `num_guests`/active-slot count, no event-side counter; INV-3 contract boundary: all event-side slot writes via `AccommodationCoordinationContract`, no direct `GuestRegistration` writes; INV-4 `accommodation_booking_id` = `BigInteger`, `info={"id_kind": IDKind.CROSS_MODULE_REF}`, no FK; INV-5 no `EventAccommodationBooking` anywhere), traced the full lifecycle, and re-ran all Stage 5 suites with exact counts.
- **Static architecture search (§14):** every Event-side accommodation import classified READ / CONTRACT OP / TEST / DOC / LEGACY. No architecture violation found. The sole legacy cross-module write is `app/events/services.py:2445 assign_service_to_attendee` (admin helper predating Stage 5; sets booking `event_id` + assignment pointer, no slot/capacity writes, not on the Stage 5 write surface) - classified legacy, non-blocking. `app/accommodation/listeners.py:14` is a log-only stub (no reverse sync). Reverse imports (accommodation→events) are read-only (`EventAssignment` token lookup) or the documented fail-closed `retire_invalid_accommodation_assignment` helper at `routes.py:2794`, which itself routes slot release back through the Accommodation-owned contract.
- **Tests - exact counts (shared test DB, sequential runs):** Stage 5-1 (`test_assignment_ownership_boundary`, `test_guest_coordination_contract`) → **16 passed**; Stage 5-2 (`test_stage5b2_assignment_lifecycle`, `test_guest_coordination_accommodation`) → **19 passed**; Stage 5-3 (`test_stage5b3_handoff_architecture`, `test_guest_assignment_account_optional`, `test_event_accommodation_assignment_flow`) → **25 passed**; Stage 5-4 (`test_stage5b4_sync_synchronization`) → **6 passed**; Stage 5-5 (`test_stage5b5_cancellation_reassignment_lifecycle`) → **10 passed**; cross-stage `test_accommodation_lifecycle_verification` → **31 passed**; combined 10-file Stage 5 focus suite → **107 passed / 0 failed / 0 errors / 0 skipped** (16+19+25+6+10+31 = 107 reconciled). Known pre-existing `test_attendee_accommodation_booking.py` → **6 failed / 10 passed** - all six are the pre-existing fixture/contract defects, unchanged, NOT Stage 5 regressions (explicitly preserved per §15).
- **Invariant/audit conclusions:** capacity integrity holds (`active_count ≤ booking.num_guests`, release once via `slot.remove()`, idempotent reassign/cancel, failed tx rollback); token integrity holds (raw token events-only, SHA-256 hash persisted, expiry + fail-closed 404/410, rotation on reassign, invalidation on cancel); transaction boundary holds (assign/cancel/retire/book each single-commit; rollback on every failure path); cross-context protection holds (event-scoped registration + permission checks + `BOOKING_EVENT_MISMATCH`).
- **Verification:** startup `python -c "from app import create_app"` → exit 0, `STARTUP_OK`; single Alembic head `1788729103`, DB at head, unchanged; no migration created/applied; no `MODULE_FLAGS` writes; no schema change; no implementation performed.
- **Deferred (remain open, unchanged, intentionally NOT absorbed into Stage 5):** 6 pre-existing attendee-file defects; MODULE_FLAGS test-DB remediation; `setup_test_db_schema.py` hang; migration-family operator decision; DATES_MISMATCH; notifications legacy-type silent drop; Task 3/Task 4; Stage 5-4 cosmetic doc corrections (`_token_for_booking` at `accommodation_bridge.py:32`, stale comments `guest_coordination_service.py` ~596/694); Stage 5-1 docstring/slot discrepancy reconciliation.
- **Links:** report "STAGE 5-6 FULL VERIFICATION REPORT" (produced in session), STAGE_5_4_ASSIGNMENT_BOOKING_SYNCHRONIZATION_AUDIT.md, app/accommodation/services/coordination_contract.py, app/events/guest_coordination_service.py, app/events/models.py:1135, tests/* (Stage 5 suite as listed above), BACKLOG.md Stage 5-1..5-5 entries, AGENTS.md §2.2 (AUDIT), §5, §8, §9, §17, §20, §21, §23, §38

---

## Legacy accommodation reminder notification types are silently dropped
- **Status:** Needs review
- **Raised:** 2026-09-07
- **Context:** While implementing the pre-arrival request reminder (AFCON360_OUTSTANDING_TASKS Task 5), discovery showed `app/tasks/accommodation_reminders.py` `_send_notification()` passes legacy type strings (`registration_reminder_72h`, etc.) to `NotificationService.send`. `Notification.type` is a String column with an enum-generated CHECK constraint `ck_notifications_type`; `NotificationType(value)` raises `ValueError`, and `NotificationService.send` swallows exceptions and returns `None` (services.py:424-427). Net effect: the legacy reminders NEVER create notifications (silent failure). The new Task 5 task avoids this by using the real enum value `NotificationType.BOOKING_UPDATE` with an explicit `module=NotificationModule.ACCOMMODATION`.
- **What needs to happen:** Either (a) add the missing values to `NotificationType` and run the §20.2 CHECK-constraint sync path (`python scripts/sync_check_constraints.py --accept-model-truth --message "..."` + `flask db upgrade` — operator-executed), or (b) rewrite legacy call sites to real enum values. Also consider making `NotificationService.send` surface invalid-type errors instead of failing silently.
- **Owner/area:** notifications + accommodation tasks
- **Links:** app/tasks/accommodation_reminders.py (_send_notification), app/notifications/services.py:424-427, app/notifications/models.py (NotificationType / ck_notifications_type), §20.2, §26

---

## Task 3 step 3 — route-level capacity regression test not added
- **Status:** Not started
- **Raised:** 2026-09-07
- **Context:** AFCON360_OUTSTANDING_TASKS Task 3 ("Capacity+copy already correct — verify only") step 3 of its Agent actions asked for a regression test that actually calls the `/events/<id>/accommodation/assign` route. The route was verified to delegate correctly to `SpecialRequestService`/capacity guards, but no route-level test was added.
- **What needs to happen:** Add a focused pytest that POSTs to the assign route (Flask-Login session `_user_id`, real user/property fixtures) and asserts over-capacity rejection + normal assignment.
- **Owner/area:** accommodation routes + tests
- **Links:** app/accommodation/routes.py (assign route), tests/test_event_accommodation_assignment_flow.py (fixture pattern), §21, §38

---

## Task 4 RoomHold design review — discrepancy found, untriaged
- **Status:** Needs review
- **Raised:** 2026-09-07
- **Context:** AFCON360_OUTSTANDING_TASKS Task 4 (design review of single/multi-unit holds) premised that "the search/detail flow calls create_hold() which writes to BlockedDate while RoomHold is never instantiated." The actual live code CONTRADICTS this: `AvailabilityService.create_hold()` (availability_service.py:401-509) DOES instantiate `RoomHold` (line 484) and uses `InventoryBlock` (room-type scoped) for multi-unit properties, falling back to property-wide `BlockedDate` only for single-unit. Per the task file's completion protocol, this was STOPPED and reported rather than forcing the written premise to fit.
- **What needs to happen:** A design session to decide whether the current inventory-hold behavior (BlockedDate for single-unit, InventoryBlock+RoomHold for multi-unit, TimedBed expiry via RoomHold/expiry rules) is the intended architecture, or whether the written task premise reflects a real gap that needs a separate spec. No code change.
- **Owner/area:** accommodation availability
- **Links:** app/accommodation/services/availability_service.py:401-509 (create_hold, RoomHold at :484), app/accommodation/models/availability.py:38 (BlockedDate), :93 (RoomHold), AFCON360_OUTSTANDING_TASKS.md Task 4

---

## Property `booking_mode` is never persisted by host create/edit flows
- **Status:** Not started
- **Raised:** 2026-09-07
- **Context:** Discovery during the `edit_listing.html` restyle (template-only change; documented in `static/MOBILE_OPTIMIZATION.md` §0.1 follow-up): both `create_listing.html` and `edit_listing.html` render `form.booking_mode` (`PropertyForm` at `app/accommodation/forms.py:234`, values `instant` / `host_approval`), and `booking_service.py:186` branches on `property.booking_mode == 'host_approval'` — but **nothing persists it**. `host_service.create_property()` (line ~161) and `update_property()` (line ~254) write `instant_book` only; the `booking_mode` column (`app/accommodation/models/property.py:219`, default `"instant"`) is never written by these flows. The edit route (`routes.py:4641` `form.process(...)`) does not pre-populate `booking_mode` either. Pre-existing (identical on create and edit, present before the restyle); template-only fix is NOT the right remediation.
- **What needs to happen:** Decide intended behavior — persist the form's `booking_mode` (writes in `create_property`/`update_property` + populate in `host_edit_listing`'s `form.process`) or drop the control — as a specification-required BEHAVIORAL change (§6). If persisting a new column value, confirm `booking_mode` is not enum/CHECK-constrained (String(20), no `ck_*` per current model) — a CHECK-constraint sync is only needed if a constraint is added.
- **Owner/area:** accommodation services + routes + forms
- **Links:** app/accommodation/forms.py:234, app/accommodation/models/property.py:219, app/accommodation/services/host_service.py (create ~161, update ~254), app/accommodation/routes.py:4641/4668, app/accommodation/services/booking_service.py:186, templates/accommodation/host/{create,edit}_listing.html, static/MOBILE_OPTIMIZATION.md §0.1

---

## Transport web "Bookings" list (`bookings_index`) has no data path
- **Status:** Not started
- **Raised:** 2026-09-08
- **Context:** Stage 5T-7 verification. `GET /transport/bookings` → `bookings_index` (`app/transport/routes.py:231`) renders `templates/transport/bookings/index.html` with NO `bookings`/`total`/`pages`/`page`/`status` context, so the (otherwise complete) template always shows the empty state. The template's data contract (`user_name`, `pickup_location_name`, `scheduled_pickup_time`, `driver_name`, `vehicle_plate`, `total_amount`) is produced by NO serializer/view-builder anywhere in the codebase (grep for `scheduled_pickup_time`/`pickup_location_name`/`vehicle_plate` in `app/` matches only the template), and the JS "Export" button targets `/api/transport/bookings/export`, which does NOT exist. `BookingService` has no user-scoped list method (only global `count_bookings`/`get_recent_bookings`).
- **What needs to happen:** (a) add an ownership-scoped booking list to `BookingService` (filter `user_id=current_user.id`, exclude deleted, support status filter + pagination), (b) build the view-keys the template expects or refactor the template to `to_dict()` keys, (c) implement or remove the export endpoint. Behavioral surface — verify against spec before implementing.
- **Owner/area:** transport routes + services + templates
- **Links:** app/transport/routes.py:231 (bookings_index), templates/transport/bookings/index.html, app/transport/services/booking_service.py (list/analytics, line 218+), app/transport/api/booking_routes.py (BookingListResource), static/js (export link)

---

## Transport web write-paths missing: driver create/update, booking assign, booking edit, incident/route edit
- **Status:** Not started
- **Raised:** 2026-09-08
- **Context:** Stage 5T-7 verification. The following web template links point at endpoints that do NOT exist (they resolve to `#` via `safe_url`); the API equivalents are admin-only (`transport_api.*`):
  - `transport.drivers_create` / `transport.driver_update` — `templates/transport/drivers/_form.html` (a full 156-line CRUD form) posts to these, but `drivers_new` (`routes.py:585`) and `drivers_edit` (`routes.py:670`) are GET-only. The working self-service driver path is `become_driver` (`/become-driver` GET+POST, routes.py:590).
  - `transport.booking_assign` — `bookings/index.html` + `bookings/show.html` "Assign" buttons; only `transport_api.booking_assignment` exists (admin/role-gated).
  - `transport.incident_edit` — `incidents/index.html`; no `incidents_edit` route (`incidents_new` and `incidents_investigate` exist).
  - `transport.route_edit` — `routes/index.html`; no `routes_edit` route (`routes_new`/`routes_schedule`/`routes_show` exist).
  - `transport.driver_history` — `drivers/show.html` "History" button; only `transport_api.driver_history` (admin). Owner-level booking cancel via web would 403 because `POST /api/transport/bookings/<id>/status` is `admin_required`.
- **What needs to happen:** Product/spec decision per item. If web create/update/cancel/assign are required for non-admin users, add routes + ownership checks (behavioral/HIGH_RISK — auth boundaries change), else remove/redirect the dead buttons. Do NOT auto-implement (spec §6 / §18.1-18.2 / §33).
- **Owner/area:** transport routes + templates (web) + auth policy
- **Links:** app/transport/routes.py (drivers_new:585, drivers_edit:670, become_driver:590, bookings_edit:330, incidents routes, routes_* routes), templates/transport/drivers/_form.html, templates/transport/bookings/{index,show}.html, templates/transport/incidents/index.html, templates/transport/routes/index.html, app/transport/api/booking_routes.py (BookingStatusResource/BookingAssignmentResource), §28 module guard, §33 role checks

---

## Pre-existing test error: `test_transport_stage5t4.py::test_t5t4_02_direct_organisation_transport_booking_works_without_events`
- **Status:** Not started
- **Raised:** 2026-09-08
- **Context:** Stage 5T-7 test run: 55 transport tests pass; this one errors at SETUP with `IntegrityError: null value in column "org_id" of relation "organisations" violates not-null constraint`. Every other `Organisation(...)` factory in the suite passes `org_id=str(uuid.uuid4())` explicitly; this fixture constructs `Organisation(org_type=..., country="UG", legal_name=..., ...)` without `org_id`, and the model does not auto-generate it in this path (persistent `afcon360_test` DB, tables count 198). Pre-existing bug in the (untracked) test fixture — NOT caused by Stage 5T-7 code/template changes; prod `OrganizationRegistrationService` always generates `org_id` via `generate_org_id()`.
- **What needs to happen:** Add `org_id=str(uuid.uuid4())` to the fixture's `Organisation(...)` constructor (mirror `test_org_creation_rbac_4b1.py` pattern). Test-only fix; re-run `pytest tests/ -k "transport"`.
- **Owner/area:** tests
- **Links:** tests/test_transport_stage5t4.py (organisation fixture), tests/test_org_creation_rbac_4b1.py:121 (generate_org_id contract), app/identity/models/organisation.py
