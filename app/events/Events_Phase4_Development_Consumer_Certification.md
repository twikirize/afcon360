# Phase 4 Development Consumer Certification

**Date:** 2026-08-18  
**Scope:** Repository consumer certification and trustworthy PostgreSQL
regression evidence  
**Status:** `NOT_READY` for compatibility removal; human review required

## Evidence boundary

The Events module is implemented, but AFCON360 remains in development and
broad external consumption is not established. This report therefore certifies
repository/module consumers only. It does not claim zero production usage or
infer production behavior from absent traffic.

No legacy field, fallback, schema element, data, migration, or creator-provenance
field was removed or renamed.

## PostgreSQL regression verification

- Command: the approved Events ownership, transfer, route, identity, metrics,
  registration/workflow, and payment-related test selection.
- Backend: configured PostgreSQL test database through `TestingConfig` and the
  shared migration-managed fixture.
- Result: exit code `0`; `28 passed`; no test failures or fixture errors.
- Database evidence: application initialization succeeded and the SQLAlchemy
  query `current_owner_id IS NULL AND organizer_id IS NOT NULL` returned
  `0` records. No data was changed.
- Warnings: `13` warnings, primarily SQLAlchemy `Query.get()` deprecations and
  one deliberate `organizer_id` permission-fallback deprecation warning.
- Application log: one payment-service `ERROR` log stated “registration
  unavailable” during a test that still passed. It is recorded here rather
  than treated as a hidden success; payment registration behavior needs a
  separate review if it is intended to be production-ready.

The Windows fixture blocker was corrected only by replacing the two Unicode
status glyphs printed by `tests/conftest.py:36,61` with Windows-safe ASCII
messages. Assertions, database checks, test selection, and persistence backend
were unchanged.

## Repository consumer classifications

| Code location / evidence | Observed use | Classification | Disposition |
|---|---|---|---|
| `app/core/model_registry.py:61-65`, `app/events/__init__.py:5-36` | Loads and registers Events models/blueprints | `REAL_DEVELOPMENT_CONSUMER` | `KEEP` |
| `app/events/routes.py:350-355` | Calls `EventService.get_events_by_organizer()` for the Events organizer page | `REAL_DEVELOPMENT_CONSUMER` | `KEEP`; service semantics are separately audited |
| `app/events/routes.py:378-385,460-468` | Accepts and logs client `organizer_id` input | `COMPATIBILITY_BRIDGE` | `KEEP` and observe; no external production traffic is established |
| `app/events/models.py:182-183,278,292-333` | Non-null User FK, public-contact relationship, constructor/default-owner compatibility | `LEGITIMATE_DOMAIN_SEMANTIC` plus `COMPATIBILITY_BRIDGE` | `RETAIN_COMPATIBILITY`; do not map contact to owner |
| `app/events/permissions.py:68-77,101-124` | Explicit canonical owner first; organizer fallback only for legacy records | `COMPATIBILITY_BRIDGE` | `RETAIN_COMPATIBILITY`; deliberate fallback test remains |
| `app/events/services.py` and `app/events/metrics_service.py` | Canonical owner/EventRole queries with retained organizer signatures/serialization | `REAL_DEVELOPMENT_CONSUMER` plus `COMPATIBILITY_BRIDGE` | `KEEP`; canonical internal paths retained |
| `app/events/routes_community_hosts.py` | Community-host authorization routes use centralized owner checks; no remaining organizer ownership use was found in the audited slice | `REAL_DEVELOPMENT_CONSUMER` | `KEEP` |
| `app/events/tasks.py`, `app/events/payment_service.py`, signal handlers, and notification integration | Events task/payment/signal/notification code is registered and exercised by the module/test suite | `REAL_DEVELOPMENT_CONSUMER` | `KEEP`; no organizer ownership reinterpretation found in this certification |
| `app/accommodation/*`, `app/transport/*`, `app/event_accommodation/*` | Repository search found event-related integration references, but no evidence in the reviewed matches that these modules consume `organizer_id` as ownership | `REAL_DEVELOPMENT_CONSUMER` where event integration is called; otherwise `DEAD_LEGACY_CODE` is not claimed | `KEEP`; semantic follow-up required for each integration caller |
| `tests/test_events_ownership_characterization.py`, `tests/test_event_transfer_lifecycle.py`, workflow/payment/registration fixtures | Constructs legacy and canonical Events to characterize behavior | `TEST_OR_CHARACTERIZATION` | `TEST-ONLY`; preserve deliberate legacy coverage until removal is approved |
| `app/events/Events_*` reports, ADRs, and documentation | Describes migration state and compatibility contracts | `TEST_OR_CHARACTERIZATION` / documentation evidence | `KEEP`; documentation is not runtime consumption |
| `static/js/**` event-related matches | Frontend contains generic event/dashboard/module behavior; no `organizer_id` API payload consumer was identified in the reviewed search output | `DEAD_LEGACY_CODE` is not established | `KEEP`; external/client usage remains unestablished |

## `organizer_id` evidence by semantic category

- **Public contact:** `app/events/models.py:182-183,278` declares the field
  non-null and documents it as the public-facing contact. This is a legitimate
  domain semantic until an evidence-backed replacement is approved.
- **Ownership fallback:** `app/events/permissions.py:68-77,101-124` uses it
  only when canonical owner fields are absent. The PostgreSQL candidate query
  found no current records in that state, but the deliberate legacy-record
  characterization remains valid evidence that the fallback is still needed
  for compatibility behavior.
- **Constructor/default initialization:** `app/events/models.py:292-333`
  retains the old input and derives defaults only when canonical values are
  absent. Test/fixture use is not evidence of a production caller.
- **API compatibility:** `app/events/routes.py:378-385` and the update branch
  observe incoming legacy payloads; serialization remains compatible. No
  production observation window exists, so zero test observations cannot be
  called zero external consumers.
- **Signatures/serialization:** retained parameters and serialized keys in
  Events services/metrics are compatibility boundaries, not proof of active
  external clients.
- **Contact route:** `contact_organizer()` in `app/events/routes.py:2485-2525`
  retains a defensive organizer fallback. Its contact usage was not separately
  instrumented; removal is `NOT_READY`.
- **Creator:** `created_by_type` and `created_by_entity_id` remain separate
  provenance fields and were untouched.

## Runtime and database observations

| Observation | Result | Qualification |
|---|---:|---|
| PostgreSQL regression tests | `28 passed` | Repository test evidence, not production traffic |
| Legacy API input in this run | `0` observed | No production observation window exists |
| Deliberate permission fallback | `1` warning | Compatibility characterization, not an external consumer |
| Missing canonical owner with organizer present | `0` database records | Read-only SQLAlchemy query; no backfill required |
| Contact fallback | Not separately measured | Must remain `NOT_READY` |

## Decisions and unresolved findings

- Ownership, operator, and context consumers are using the canonical paths
  verified by the current code and tests.
- `organizer_id` cannot be universally replaced with
  `current_owner_type/current_owner_id` because the model's current documented
  contract is public contact and the permission fallback protects legacy
  records.
- No repository evidence supports removing constructor compatibility,
  permission fallback, API compatibility, serialization/signature retention,
  or contact fallback in this phase.
- `created_by_type/entity_id` are outside this cleanup and remain untouched.
- External production traffic is unavailable or unestablished; no claim of
  zero production consumers is made.

## Human review gate

Phase 4 Development Consumer Certification is complete for this evidence
slice, but removal remains locked. Before any removal proposal, review the
consumer classifications, the passing PostgreSQL result, the payment-service
error log, and the unresolved public-contact contract. No schema/data change,
backfill, fallback removal, or creator-field change is authorized by this
report.