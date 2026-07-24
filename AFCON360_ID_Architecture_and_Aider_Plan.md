# AFCON360_PROD — ID Architecture Fix & Aider Execution Plan

**Context:** modules (accommodation, transport, events, wallet, etc.) are intentionally
independent — they cooperate (transport → event → accommodation → wallet payment) but
no module's failure or unavailability should freeze another. This plan takes that as a
hard constraint, not a suggestion, and designs around it rather than around "add more
foreign keys."

**Guiding rule used throughout:**
- **Foundational tables** (`users`, `organisations`, `accounts`) get real DB foreign keys.
  Every module already requires these to exist to function — there's no independence to
  protect by leaving them unconstrained. This is where `accounts.user_id` and
  `transport_vehicles.owner_id` belong.
- **Peer-module references** (`event_id` in accommodation/transport bookings, a future
  `trip_id` referenced from outside transport) get **no DB-level FK, ever** — but they
  also don't get *zero* validation. They get a format-level sanity check at write time and
  an async reconciliation job that reports drift without blocking anything.

This is a reclassification, not a rewrite. No existing working code changes behavior on
day one — Phase 1 is pure metadata (`info={...}` tags), which is inert until Phase 2
starts reading it.

---

## Phase 1 — Single source of truth for ID classification (no behavior change)

**Objective:** Replace three scattered lists (`BaseModel.NON_FK_STRING_IDS`,
`IDGuard.STRING_FK_EXCEPTIONS`, `IDGuard.ADDITIONAL_FK_FIELDS`) with one classification
that lives on the column itself, so every future `_id`/`_by` column (e.g. a `trip_id` in
transport) is self-documenting at the point it's defined instead of requiring an edit to
a file three modules away.

**Aider task 1.1 — Add the classification module**
```
Create app/utils/id_kinds.py with an IDKind enum (INTERNAL_FK, CROSS_MODULE_REF,
EXTERNAL_STRING_ID, PUBLIC_ID) and an id_kind_of(column) helper that reads
column.info.get('id_kind'), defaulting to INTERNAL_FK for BigInteger/Integer columns
and EXTERNAL_STRING_ID for String/Text columns with no explicit tag. This must not
change behavior for any column that isn't explicitly tagged yet.
```
- Files affected: new file only.
- Migration required: no.
- Tests required: unit test for `id_kind_of` covering tagged and untagged columns of
  each SQLAlchemy type.
- Rollback: delete the file, nothing else references it yet.
- Verification: `pytest tests/test_id_kinds.py` (new, small).

**Aider task 1.2 — Tag the known cases**
```
Add info={"id_kind": IDKind.EXTERNAL_STRING_ID} to: AccommodationBooking.wallet_txn_id,
AccommodationBooking.context_id, AccommodationBooking.group_booking_id, and every other
column currently listed in BaseModel.NON_FK_STRING_IDS (session_id, public_id — actually
PUBLIC_ID kind, key_id, device_id, resource_id).
Add info={"id_kind": IDKind.PUBLIC_ID} specifically to User.public_id and any column
matching IDGuard.STRING_FK_EXCEPTIONS (UserProfile.user_id).
Add info={"id_kind": IDKind.CROSS_MODULE_REF} to AccommodationBooking.event_id,
AccommodationBooking.event_participation_id, TransportBooking.event_id,
TransportBooking.event_participation_id, and EventAssignment's four booking-reference
columns. Do not remove the old lists yet — this task only adds metadata.
```
- Files affected: `booking.py`, `transport/models.py`, `events/models.py` (wherever
  `EventAssignment` lives), `identity/models/user.py`.
- Migration required: no — `info={}` is Python-side metadata, not a DB change.
- Tests required: existing test suite should pass unchanged (nothing reads `info` yet).
- Rollback: revert the diff, no data involved.
- Verification: full existing test suite green, plus a grep confirming every entry in
  the three old lists now has a matching `info=` tag somewhere.

---

## Phase 2 — Wire the new classification in, remove the old lists

**Aider task 2.1 — Update `BaseModel.__setattr__`**
```
Update app/models/base.py: replace the NON_FK_STRING_IDS set and the if/else branching
in __setattr__ with a single call to id_kind_of(column), branching into
IDGuard.check_external_ref (new, for EXTERNAL_STRING_ID — light length/charset sanity,
no UUID/int requirement), IDGuard.check_public_id (for PUBLIC_ID), a new
IDGuard.check_soft_reference (for CROSS_MODULE_REF — confirm positive int or non-empty
string, no live cross-module DB lookup), or IDGuard.check_fk_assignment (INTERNAL_FK,
unchanged from today). Delete NON_FK_STRING_IDS entirely once this is in place.
```
- Files affected: `app/models/base.py`.
- Migration required: no.
- Tests required: `test_idguard.py`, plus a targeted test asserting
  `booking.wallet_txn_id = "some-external-ref-123"` no longer raises and
  `booking.event_id = 42` (an int) is accepted without a live DB lookup happening.
- Rollback: git revert this single commit — Phase 1's tags are inert either way.
- Verification: `pytest tests/test_idguard.py tests/test_db_public_id.py`, then a
  smoke test of accommodation checkout end-to-end in staging.

**Aider task 2.2 — Add the two new IDGuard checks**
```
Add IDGuard.check_external_ref(value, source): reject only if value is None-unsafe
(already handled upstream), not a string, or longer than 512 chars. No format
assumption beyond that — these are opaque external identifiers.
Add IDGuard.check_soft_reference(value, source): accept a positive int OR a non-empty
string; log (don't raise) if it's neither, since a bad value here should never block a
write — that's what the reconciliation job in Phase 3 is for.
```
- Files affected: `app/utils/id_guard.py`.
- Tests required: unit tests for both new methods, edge cases (None, empty string,
  negative int, zero).
- Rollback: trivial, additive-only change.
- Verification: unit tests green.

**Aider task 2.3 — Retire the unused landmine**
```
Confirm guard_fk_assignment (id_guard.py) and IDGuard.STRING_FK_EXCEPTIONS /
ADDITIONAL_FK_FIELDS are not applied anywhere in the codebase
(grep -rn "guard_fk_assignment" app/). If unused, mark guard_fk_assignment as
deprecated with a docstring pointing to the new column.info system, or delete it.
Do not delete STRING_FK_EXCEPTIONS itself yet if IDGuard.check_public_id still reads
it — merge its one entry (UserProfile.user_id) into the info={} tag from task 1.2
instead, then remove the dict.
```
- **This is the fix for the specific regression risk found in review**: a decorator
  that, if ever wired up later, would have broken `wallet_txn_id` assignment in
  production because it didn't know about `BaseModel`'s exemption list. After this task,
  that landmine no longer exists — there's one registry, and everything reads it.
- Tests required: `grep` step above should return zero results before merging.
- Rollback: trivial.
- Verification: `grep -rn "guard_fk_assignment\|STRING_FK_EXCEPTIONS\|ADDITIONAL_FK_FIELDS" app/` returns nothing outside `id_guard.py` itself.

---

## Phase 3 — Soft-reference reconciliation (the "not a landmine" guarantee)

**Aider task 3.1 — Extend the existing reconciliation task**
```
Extend app/tasks/reconcile.py (it already exists — do not create a new file) with a
periodic Celery job that, for every column tagged IDKind.CROSS_MODULE_REF across all
models, checks whether the referenced row still plausibly exists in the target module's
table (a simple existence SELECT against that module's own table, wrapped in try/except
so a down or disabled module fails this one check silently rather than raising). Emit a
report (log line or a row in a small reconciliation_findings table) listing orphaned
cross-module references. Never raise, never block, never touch the write path.
```
- Files affected: `app/tasks/reconcile.py`, Celery beat schedule config.
- Migration required: only if you choose to store findings in a table rather than logs
  (optional, can start log-only).
- Tests required: unit test with one module "down" (simulated) confirming the job
  completes without error and simply logs "skipped."
- Rollback: this is a read-only reporting job — disable the periodic schedule to fully
  revert, no data risk.
- Verification: run the job manually against staging, confirm output is sane and the
  job completes even with one target table renamed/dropped temporarily (simulating
  module unavailability).

---

## Phase 4 — DB integrity items, now correctly scoped

With the module-isolation principle applied, several items from the original schema
audit split cleanly:

**SAFE — same-tier / foundational, fix now:**
- `accounts.user_id` → add FK to `users.id` (accounts can't exist without a user in any
  module's world)
- `transport_vehicles.owner_id` → add FK to `users.id`
- Drop duplicate FKs: `driver_profiles.user_id` (listed twice), `transport_bookings.assigned_driver_id` (listed twice)
- Audit-log actor FKs (`api_audit_logs.initiated_by`, `financial_audit_logs.*`, etc.) →
  all reference `users.id`, foundational, safe to add

**NOT BUGS — leave alone, now that the principle is explicit:**
- `accommodation_bookings.event_id` / `event_participation_id`
- `transport_bookings.event_id` / `event_participation_id`
- `event_assignments`'s four booking-reference columns
- All 22 polymorphic `*_type`/`*_id` pairs that cross module boundaries — these were
  never going to be enforceable at the DB level under a module-isolation design, so stop
  treating them as an open remediation item and instead make sure each one is tagged
  `CROSS_MODULE_REF` (Phase 1) and covered by reconciliation (Phase 3)

**REQUIRES A DECISION — one specific outlier:**
- `accommodation_inventory_blocks.reason` currently uses a native Postgres ENUM
  (`inventory_block_reason_enum`), the only column in the schema that does. Either (a)
  convert it to match the rest of the system — `String` + `CHECK` constraint, using
  `scripts/migrate_enums_to_strings.py` which already exists and does exactly this
  expand-contract pattern, or (b) explicitly decide this one field's value set is closed
  and rarely changes, and keep it native. Either is fine; leaving it undecided is the
  only wrong answer, since it's a live inconsistency with the "Python Enums + String
  storage" rule stated in `booking.py`'s own docstring.

**DANGEROUS — unchanged from the original roadmap, do last:**
- `auth_configurations` secrets migration
- Any `users` table structural change
- Password/PIN hashing verification

---

## What this plan deliberately does NOT do

- No table splitting / normalization of the wide tables (`transport_bookings` at 99
  columns, etc.) — still out of scope until integrity items are settled, per the
  original roadmap.
- No change to how modules call each other's services — this is purely about the data
  layer's tolerance for a peer module being unavailable, not the service layer.
- No removal of any existing working validation — Phase 1 is additive, Phase 2 swaps
  implementation while preserving behavior for every case that already worked, Phase 3
  is a new read-only job, Phase 4 only touches foundational-table FKs that were always
  supposed to exist.

Each Aider task above is independently revertible and independently testable — you can
stop after any phase and the system is in a strictly better state than before it, never
a half-migrated one.
