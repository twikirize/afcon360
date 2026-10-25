# AFCON360 Runtime Timezone Adoption Audit

**Status:** In progress — source fixes are partial; full application/database adoption is not verified.  
**Working branch:** `work/global-timezone-standard-20261025`  
**Safety:** This audit describes source evidence only. It does not authorize a migration, database write, merge, or deployment.

## Runtime paths tightened in this branch

| Path | Finding addressed | Current contract |
|---|---|---|
| `app/production_console/streaming.py` and `templates/owner/production_console.html` | New console events exposed an ISO timestamp but the UI preferred a time-only UTC string without its timezone. | New events carry offset-qualified UTC timestamps; the browser localizes only a timestamp whose timezone is explicit. A legacy value without an offset is shown as unknown (`TZ?`), not guessed. |
| `app/__init__.py`, `app.py`, `app/notifications/events/stream_consumer.py`, `app/production_console/streaming.py`, and `app/utils/time.py` | Default/standalone logging entry points could use host-local `asctime` output or leave preconfigured handlers unchanged. | The shared UTC ISO formatter is applied to preconfigured root stream handlers, the app factory, stream consumer, and production console; the root bootstrap entry point uses an explicit UTC formatter before importing Flask. Other custom handlers and external process supervisors still require review. |
| `app/geo/history.py` | History query bounds previously treated naive values as UTC. | Bounds now pass through `parse_datetime_to_utc`; callers must send an offset-qualified instant. |
| `app/geo/activity.py` | Activity/demand windows previously attached UTC to naive values. | Both bounds now pass through the shared parser and normalize to UTC. |
| `app/geo/validation.py` | Location payload timestamps could be parsed without a timezone; freshness checking then attached UTC. | Payload timestamps require an explicit offset and normalize to UTC. A manually supplied naive point timestamp is not considered fresh. |
| `app/geo/realtime.py` | An explicit naive reference clock could be silently labelled UTC, and untrusted realtime event timestamps were not fully parsed. | An explicitly supplied reference clock must be timezone-aware; malformed or timezone-naive `observed_at` payloads are discarded. |

These are source changes and regression tests. A browser session and live authenticated console response have not been inspected in this audit, so runtime behavior must still be verified in a controlled non-production environment.

## Runtime and domain paths still open

| Path | Evidence found | Required decision before closing |
|---|---|---|
| `app/accommodation/services/abuse_prevention_service.py` | Three methods use naive `datetime.now()` values against booking expiry/creation timestamps. | Coordinate aware UTC clock changes with the actual PostgreSQL column types and the schema cutover; add hold-limit and rate-limit regression tests. Do not change the application clock in isolation while the target schema is still naive. |
| `app/profile/routes.py` | Active-session lookup falls back from aware UTC to naive local time; `_now_matching` selects a clock type based on the stored value. | Decide legacy-row treatment; eliminate mixed-type fallback in a coordinated migration and test active-session, password-expiry, and PIN-lock behavior. |
| `app/auth/session_management.py` | Session ISO strings are parsed and subtracted from aware UTC now. Values without an offset can raise a naive/aware comparison error. | Define handling for legacy session strings (fail closed versus one-time compatibility conversion), test both offset-qualified and naive strings, and keep authentication expiry fail-safe. |
| `app/admin/owner/decorators.py` | A naive password-confirmation timestamp causes a type mismatch; current exception handling removes the confirmation and redirects to re-authentication. | Preserve fail-closed behavior and test the legacy case while confirming all newly written confirmation timestamps include an offset. |
| `app/accommodation/models/booking.py` | The registration-deadline property labels a naive value as UTC using `replace(tzinfo=timezone.utc)`. | Prove historical writer semantics or handle the legacy value explicitly; do not infer UTC solely because the model declaration is timezone-aware. |
| `app/accommodation/services/booking_registration_link_service.py` | A date-only check-in is converted to midnight UTC to make a registration-link expiry instant. | Confirm the intended business rule: expiry at start of the calendar date, venue-local start of date, or another deadline. Date-only values must not be treated as globally interchangeable instants without that decision. |
| `app/transport/services/booking_service.py` | Naive legacy `pickup_time` input is interpreted in configured `_APP_TZ`. | This is an existing compatibility behavior, not proof of a global timezone. Preserve it until the transport API migration and ownership contract explicitly decide how legacy clients are handled; add tests for explicit offsets and naive legacy input. |
| Other app-specific handlers, jobs, workers and integration points | Source search found additional date parsing, custom logging, and legacy datetime paths beyond the focused fixes above. | Complete a systematic inventory and owner-by-owner regression pass; do not infer that the shared helper is adopted just because it exists. |

## Database and migration gates

See [`TIMESTAMP_SEMANTICS_REGISTER.md`](TIMESTAMP_SEMANTICS_REGISTER.md) for the source-supported early classifications, current Alembic graph evidence, and per-column conversion dispositions. The classification register does not replace a read-only physical inventory or row-history review for each database.

1. **Reconcile the active baseline with each database.** The tracked source declares `h3a20261020` (root, `down_revision=None`) → `c076b257b11d` → `1792869659` → `tza20261025`. Therefore `tza20261025` has the code-declared parent expected by this branch; do not rewrite it to `df55cbe3f516`. But `df55cbe3f516` is tracked under `migrations/_retired_versions/`, not the active graph. The `h3a20261020_static_baseline.py` file is physically in `migrations/versions/` despite a stale docstring claiming it is isolated and not active. The source-only graph is connected, but a database at `df55cbe3f516` is not at a tracked active revision. Reconcile this with the approved H3 cutover record and physical schema before any migration work.
2. Run `scripts/audit_naive_timestamp_columns.py` as a read-only catalog inventory against an explicitly named disposable/non-production database. The script inventories column types and approximate row counts; it does not inspect row values or prove their original timezone.
3. Trace the historical writer and intended semantics for every naive timestamp column. Separate absolute instants from date-only fields and venue-local recurring schedules. The migration now has separate exact inventories for UTC instants and intentional wall-clock columns; only the UTC inventory is converted. Both inventories are empty. Every discovered naive column must be assigned exactly one evidence-backed classification; unknown columns or overlapping entries block the migration. Any intentionally local field must retain a matching `timezone=False` model declaration.
4. Change writers, readers, API validation, jobs, comparisons, and serializers as a compatible unit. Run relevant PostgreSQL tests against a populated disposable clone after the exact model/schema parity is known.
5. Populate `APPROVED_LEGACY_UTC_COLUMNS` and `APPROVED_LEGACY_WALL_CLOCK_COLUMNS` only after reviewed evidence for that exact database. Both allowlists are intentionally empty. The environment flag is an attestation, not evidence.
6. Test lock duration, table rewrite behavior, backup restoration, rollback/recovery procedure, and per-database schema parity. The migration's downgrade intentionally refuses to guess.

## Current disposition

- UTC primitives, PostgreSQL session UTC setting, broad model declarations, a guarded migration with separate UTC/wall-clock inventories, console formatting, a source-only migration-lineage auditor, and a focused GEO parser pass are present on the draft branch.
- The source lineage is structurally `h3a20261020` → `c076b257b11d` → `1792869659` → `tza20261025`, but `h3a20261020` is physically in the active migration directory with `down_revision=None` despite a stale docstring saying it is isolated. The recorded `df55cbe3f516` database checkpoint is in the retired-version directory, so the target's active-chain compatibility is unresolved and remains a hard gate.
- The evidence-based early classification is in `docs/architecture/TIMESTAMP_SEMANTICS_REGISTER.md`; both migration allowlists remain empty. No column is yet approved for conversion.
- Unit/source-contract workflow success is not proof of application-wide adoption, browser behavior, populated-data migration safety, or database parity.
- No production database was changed and no migration was run by this source work.
- Keep the pull request draft/open until the remaining runtime audit, migration lineage, populated-clone tests, and recovery gates are closed.
