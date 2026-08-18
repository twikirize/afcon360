# Phase 4 Remaining Evidence Investigation

**Date:** 2026-08-18  
**Scope:** Contact fallback, payment registration log, and stale organizer ownership  
**Status:** Evidence-only; compatibility removal remains locked

## Evidence boundary

This investigation uses the current repository code, existing tests, and the
recorded PostgreSQL run. No production traffic is available, so repository
absence and test counts are not treated as proof of external usage. No code,
schema, data, migration, ownership, payment, or test changes were made.

## A. Contact fallback — `NOT_READY`

### Inspected code

- `app/events/routes.py:2485-2573`, `contact_organizer()`.
- `app/events/models.py:182-183,254-275,278`.
- Existing repository search for `contact_organizer`, `OrganizerMessage`, and
  contact-route tests.

### Exact code path

1. The route loads `Event` by internal `event_id` and persists an
   `OrganizerMessage` addressed to the event.
2. It chooses the email recipient with this current expression:
   `event.current_owner_id` when `current_owner_type == 'individual'`;
   otherwise `event.original_creator_id or event.organizer_id`.
3. It loads that user and sends the organizer notification when an email is
   available, then sends a confirmation to the requester.

`Event.organizer_id` is a non-null `User` foreign key and the model explicitly
documents the relationship as the public-facing contact. Therefore the final
fallback is executable runtime code and not dead documentation. The current
code does not establish a separate canonical contact field or prove that
`current_owner_id` is always the intended contact for organization-owned or
system-owned events.

### Existing test evidence

The repository search found no direct test for the
`/<event_id>/contact-organizer` route or for its recipient-selection branches.
The broader Events regression run therefore does not prove that the fallback
can be removed.

### Classification and disposition

`NOT_READY` / `RETAIN_COMPATIBILITY`.

The fallback is a legitimate defensive contact path supported by the current
non-null model contract. A separate contact-domain decision and branch-level
tests are required before changing it. No external consumer claim is made.

## B. Payment registration error — `EXPECTED`

### Inspected code and test

- `app/events/payment_service.py:97-177`, especially `:117-150`.
- `tests/test_events_user_workflows.py:372-392`.

### Exact code path

The test defines `fail_registration()` to raise
`RuntimeError("registration unavailable")` and monkeypatches the service's
`_create_registrations` method. During `process_ticket_purchase()`, the
registration call is inside a nested exception handler. The handler rolls back
the session, logs `Error creating registrations or reserving seats: registration
unavailable`, and returns a failed result containing the same error. The test
asserts that the result is unsuccessful and that no refund is attempted.

The recorded `ERROR` log is therefore produced by an intentional negative-path
test injection. The test passed because the expected failure and rollback path
were exercised; the log is not evidence of an unhandled production payment
failure. The log level may be noisy for an intentionally simulated failure,
but that is a logging-policy question, not an established functional defect.

### Classification and disposition

`EXPECTED` for this test execution. No payment behavior change is authorized
by this investigation. A separate payment/logging review would be required if
the project later decides expected negative-path logs should use another level.

## C. Stale organizer ownership after transfer — `PROVEN` by implementation,
with a test-coverage gap

### Inspected code and tests

- `app/events/permissions.py:100-124`, `_is_event_owner()`.
- `app/events/models.py:254-262`, canonical owner fields.
- `app/events/services.py:757-859`, transfer request and approval lifecycle.
- `tests/test_events_ownership_characterization.py:74-94`.
- `tests/test_event_transfer_lifecycle.py:62-129,131-147`.

### Exact code-path semantics

`_is_event_owner()` first calls `event.is_owned_by_user(user.id)` when that
model method is available. It then reads `current_owner_type` and
`current_owner_id`. If either canonical owner value is present, a non-match
returns `False` and the function does not call `_resolve_organiser_id()`.
Only when both canonical owner values are absent does it invoke the
`organizer_id` fallback.

`approve_event_transfer()` records the previous canonical owner in an
`EventTransferLog`, assigns the requested `current_owner_type` and
`current_owner_id`, and commits them in the same transaction. The transfer
code does not modify `organizer_id`.

Together, the implementation establishes the invariant that a stale
`organizer_id` cannot override a present canonical owner after transfer.
Existing tests verify current-owner precedence when organizer and current owner
differ, transfer approval and log contents, unauthorized transfer rejection,
and protection against ownership changes through ordinary update payloads.

### Coverage limitation

No existing test explicitly performs a transfer, leaves the old
`organizer_id` in place, then calls `_is_event_owner()` for the former owner and
asserts denial. The behavior is therefore `PROVEN` by the current predicate and
transfer assignment, but the specific end-to-end post-transfer regression
assertion is `NOT_PRESENT` and should be added only in a separately authorized
test-coverage node.

## Evidence summary

| Question | Classification | Current disposition |
|---|---|---|
| Contact fallback | `NOT_READY` | `RETAIN_COMPATIBILITY` |
| Payment registration log | `EXPECTED` | No behavior change; separate logging review only if authorized |
| Stale organizer after canonical transfer | `PROVEN` by code; explicit end-to-end test absent | Keep fallback for legacy records; add targeted coverage only under separate authorization |

## Recommended next graph node

Remain at the human review gate. Do not remove or rename `organizer_id`, the
constructor fallback, permission fallback, contact fallback, serialization or
signature compatibility, `created_by_type`, or `created_by_entity_id`.

The next authorized node, if approved, should be a narrowly scoped test-only
coverage node for the post-transfer stale-organizer invariant and the three
contact-recipient branches. No production behavior or schema change should be
bundled with it. The payment finding requires no implementation node from this
investigation.