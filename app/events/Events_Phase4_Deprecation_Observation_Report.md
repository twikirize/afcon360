# Phase 4 Deprecation and Observation Report

**Date:** 2026-08-17  
**Scope:** Phase 4 Step 5 deprecation and observation only  
**Outcome:** `NOT_READY` for compatibility removal; retain all bridges

## Evidence boundary

The existing Events code, PostgreSQL state, and observable execution output are
the sources of truth. This report does not infer production usage from source
references or from a green test result. No field, fallback, migration, schema,
data, or creator-provenance behavior was removed.

## Code-backed classifications

| Path | Location | Semantic category | Current behavior | Disposition |
|---|---|---|---|---|
| Public contact | `app/events/models.py:182-183,278` | Contact | `organizer_id` is a non-null `User` FK and `organizer` relationship; the model documents it as the public-facing contact. | `RETAIN_COMPATIBILITY` |
| Constructor input | `app/events/models.py:293-300` | Constructor compatibility | Accepts `organizer_id`; emits a deprecation warning only when no explicit `current_owner_id` is supplied, then preserves normal construction. | `DEPRECATED_AND_OBSERVED` |
| Default ownership | `app/events/models.py:312-331` | Legacy owner fallback / creator initialization | `_set_default_owner()` derives an individual owner and creator entity from `organizer_id` only when canonical values are absent. | `RETAIN_COMPATIBILITY` |
| Permission fallback | `app/events/permissions.py:64-76,100-124` | Owner fallback | `_is_event_owner()` checks explicit ownership first and invokes `_resolve_organiser_id()` only when both canonical owner fields are absent. | `DEPRECATED_AND_OBSERVED` |
| Event creation | `app/events/services.py:629-652` | Constructor/contact compatibility | New events set canonical owner and creator fields explicitly while still supplying `organizer_id` to satisfy the required contact field. | `RETAIN_COMPATIBILITY` |
| API observability | `app/events/routes.py:378-385` and update route legacy branch | API compatibility | Logs client payloads containing `organizer_id`; no removal or reinterpretation occurs. | `DEPRECATED_AND_OBSERVED` |
| API serialization | `app/events/routes.py:2041-2042` and serialization callers | Serialization compatibility | Existing responses retain organizer contact output for clients. | `RETAIN_COMPATIBILITY` |
| Service serialization/signature | `app/events/services.py` and `app/events/metrics_service.py` | Signature/serialization compatibility | Parameters and serialized keys retain `organizer_id` while internal ownership/operator queries use canonical fields and `EventRole`. | `RETAIN_COMPATIBILITY` |
| Contact route | `app/events/routes.py:2485-2525` | Primary contact | `contact_organizer()` prefers individual canonical owner, then original creator for non-individual ownership, and finally `organizer_id`. | `NOT_READY` |
| Creator provenance | `created_by_type`, `created_by_entity_id` | Creator | Polymorphic creator provenance remains distinct from ownership and is outside this cleanup. | `RETAIN_COMPATIBILITY` |

## Runtime evidence

Counts are separated by observation source and must not be treated as
production-usage proof:

| Category | Observed count | Source/qualification |
|---|---:|---|
| Legacy API input | `0` in the preceding recorded observation | Route logging in `app/events/routes.py`; this is not a permanent zero-consumer proof without a production observation window. |
| Constructor fallback | `0` in the preceding recorded 52-test report | Warning is emitted only when canonical owner input is absent; current source still retains the fallback. |
| Permission fallback | `1` in the preceding recorded 52-test report | Deliberate legacy-record compatibility test; it proves the fallback remains exercised. |
| Deliberate compatibility fixtures | Present | Test files construct events with `organizer_id`, including `tests/test_events_ownership_characterization.py` and workflow/payment/registration fixtures. |
| Contact fallback | Not independently measured | The route contains a defensive fallback; no instrumentation currently distinguishes contact fallback from ordinary contact delivery. |

The latest attempted PostgreSQL regression command could not provide a valid
regression result. It collected 28 tests, one passed, and 27 errored during the
application fixture because `tests/conftest.py:36` printed `✅` to a Windows
`cp1252` stream, raising `UnicodeEncodeError`. The output also reported that
the database had 173 tables, but the fixture error prevented downstream tests
from running. This is an environment/verification block, not evidence that the
Events behavior passed or failed.

## Remaining references

Remaining `organizer_id` references are not one undifferentiated consumer set:

- Model column, relationship, and public-contact contract.
- Constructor and default-owner compatibility.
- Canonical-owner-first permission fallback for legacy records.
- API serialization and retained service signatures.
- Primary-contact defensive fallback.
- Deliberate test and fixture inputs.
- Documentation and audit references.

The code search therefore does not establish zero active consumers. The
permission fallback has an explicitly observed deliberate test use, and the
contact contract is still represented by a non-null model column.

## Removal decision per path

- **Permission fallback:** `NOT_READY`; retain until all legacy records have a
  proven canonical owner and the deliberate compatibility case has an approved
  replacement and regression coverage.
- **Constructor compatibility:** `NOT_READY`; retain until production callers
  and deliberate fixtures are separately classified and the required contact
  field contract is resolved.
- **API input compatibility:** `DEPRECATED_AND_OBSERVED`; retain logging and
  compatibility during an actual production observation window.
- **Serialization/signature compatibility:** `RETAIN_COMPATIBILITY`; removal
  requires client/version evidence and a staged contract change.
- **Primary-contact fallback:** `NOT_READY`; `organizer_id` remains the model's
  documented public-facing contact and no evidence-backed replacement is
  approved.
- **Creator polymorphism:** `RETAIN_COMPATIBILITY`; requires a separate
  platform-wide creator review.

## Required next gate

Before any Phase 4 Step 6 removal work, the project needs:

1. A Windows-safe rerun of the affected PostgreSQL suite with the fixture
   encoding error resolved through test-infrastructure review, not by weakening
   assertions or hiding database failures.
2. A real observation window for legacy API inputs.
3. Separate production-versus-test counts for constructor and permission
   fallback calls.
4. A decision on whether the public-facing contact represented by
   `organizer_id` is retained or receives an approved replacement.
5. Human approval for any narrowly scoped compatibility removal.

No database backfill is authorized by this report, and
`created_by_type`/`created_by_entity_id` remain untouched.