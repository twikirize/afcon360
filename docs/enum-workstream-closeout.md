# Enum Reconciliation Workstream — Closeout Handover

**Status:** Complete through Phase 4, commit `174b625`.

## What was done

**Phase 1 — `76a518b` (safe corrections):**
- Canonical `AuditLog` import in `app/audit/comprehensive_audit.py`
  (was importing from `app/models/audit.py`, which only declares
  `ActivityLog`).
- Restored `Organisation.default_users` relationship (inverse of
  `User.default_org`), plus three sibling inverses dropped by the same
  commit (`controllers`, `custom_roles`, `provider_capabilities`).
- Corrected `OrgChangeSource.check_constraint()` to target the real
  `source` column; fixed the `OrganisationVerification.status`
  constraint site.
- Removed phantom `ensure_all_enums()` startup documentation from
  `README.md`; documented the two schema paths (Alembic vs CHECK sync).
- Strengthened `tests/test_enums.py` with AST detectors + fixtures.

**Phase 4 — `174b625` (43-column restoration):**
- Restored 43 model columns from `String(N)` / `_enum_col(...)` to
  native PostgreSQL ENUM references (`PgEnum(..., create_type=False)`,
  `values_callable` on the 20 value-based columns).
- Removed 28 model-only enum CHECK declarations (none was installed in
  either database; verified).
- Preserved all 17 unrelated CHECK constraints.
- R1 call-site fixes (moderator routes, provider/availability services,
  driver routes, four audit writers) using central enum members.
- R5 imports (`PgEnum` per file; orphaned `_enum_col` helper removed).
- Focused regression tests added (`tests/test_audit_enum_writers.py`);
  `tests/test_check_constraints.py` updated to the restored contract.
- Focused set: 34 tests passed.

## Architectural decision and boundary

- The 43 in-scope existing columns **retain their native PostgreSQL
  ENUM types**. The mismatch was model-side only; both databases already
  carried the intended native types, so no text-to-enum conversion,
  `USING` expression, data backfill, or schema migration was required
  for these 43 columns.
- The source-only restoration required no migration for those columns.
- Full ENUM-to-VARCHAR conversion remains a **separate, deferred
  project** requiring explicit authorization. It was not implemented.
- The possible future review window is 2–5 years from 19 October 2026
  (review window: 19 October 2028 – 19 October 2031). This is a review
  window, not an implementation schedule or authorization.
- The decision to preserve these 43 existing native ENUM columns does not, by itself, establish a blanket storage rule for every future column. This closeout does not independently authorize universal String + CHECK storage or blanket introduction of new native enums. For any authorized new schema design, follow the permanent rule in root `AGENTS.md` §48 and its synchronized agent-rule mirror; this closeout must not contradict that governing rule.

## Baseline state after Phase 4

Per the Phase 4 verification report (previously reported verification,
not newly reverified in this documentation task):

- Accepted baseline commit: `174b625`.
- Last reported Alembic current/head: `850c17ca4f2c` (single head).
- Last reported `flask db check`: 32 pending operations = 6
  `modify_type` (5 wallet + 1 business_category) + 26 additive
  (RideRequest feature: 3 tables, 2 booking columns, 19 indexes, 2 FKs).
- Focused regression tests: 34 passed.
- `AGENTS.md` (+101) and `BACKLOG.md` (+14) had pre-existing
  working-tree changes not included in commit `174b625`.

## Remaining work — outside the closed Phase 4 scope

### ENUM-PHASE-4W

Wallet enum repair: local `WindowMode` shadow class in
`app/wallet/models/regulatory_volume.py`, five wallet-column
restorations, four CHECK expressions targeting a nonexistent column,
nested `Status` class, shared helper hardcoding the `window_mode`
identifier. See `BACKLOG.md`.

### RIDEREQUEST-MIGRATION

Separate migration for 26 additive operations: `transport_ride_requests`,
`transport_search_cycles`, `transport_offer_attempts`,
`transport_bookings.ride_request_id`, `transport_bookings.search_cycle_id`,
19 indexes, 2 FKs. See `BACKLOG.md`.

### BUSINESS-CATEGORY-DRIFT

`afcon360_prod` carries 4 `org_business_category` labels;
`afcon360_test` carries 39. Environment drift requiring an explicit
decision. See `BACKLOG.md`.

### ENUM-R2

Auditor template-less routes (`app/admin/auditor/routes.py`, reported
lines 93–94, 121–122, 176) use string filters against name-based enums.
Revive with a validated contract or remove. See `BACKLOG.md`.

### ENUM-R3

Marketplace boundary filters (`marketplace_service.py`, reported lines
637, 650, 764) assume lowercase input. Document the boundary contract or
normalize at entry. See `BACKLOG.md`.

### AGENTS.md provenance

Unexplained +101 working-tree addition (§48). Separate unresolved
governance item; see closeout report.

**Do not reopen Phase 4 without new evidence.**
