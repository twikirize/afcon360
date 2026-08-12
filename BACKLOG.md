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

<!-- New deferred items go above this line. -->
