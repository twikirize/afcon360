# BOOKING-LIFECYCLE-REQUEST-CREATE — Record

## Node ID
BOOKING-LIFECYCLE-REQUEST-CREATE

## Status
PASS

## Scope
Rider request-creation authority (`RideRequestService.create_request`),
`POST /api/transport/ride-requests` endpoint, `RideRequest` /
`SearchCycle` / `Booking`-linkage model declarations, and the focused
creation test module including the test-only rollback proof. Fare
estimation endpoint behaviour explicitly out of scope (deferred).

## Phase
IMPLEMENTATION

## Commit
none (working directory changes only)

## Register
unchanged (human step)

## Files Changed
- `app/transport/services/ride_request_service.py` (stale `Currency.enums`
  membership corrected to value-sets; session change)
- `app/transport/models.py` (+3 -3, pre-existing in tree, preserved:
  `RideRequest.service_type` class-attached to `ServiceTypeEnum`;
  Booking linkage FKs gained explicit constraint names)
- `tests/transport/test_ride_request_create.py` (conftest-compliant login
  helper; new `TestRollbackAfterPartialFlush` class)
- `docs/transport/nodes/BOOKING-LIFECYCLE-REQUEST-CREATE-evidence.md` (new)
- `docs/transport/nodes/BOOKING-LIFECYCLE-REQUEST-CREATE-record.md` (new)

## Behaviour
A valid authenticated tier-2 rider request atomically persists one
`RideRequest` and its initial `SearchCycle`; identical replay returns the
same `public_id`; same-key different-payload is rejected 409 without
mutation; a `SearchCycle` failure after the `RideRequest` flush rolls back
both rows; no `Booking` row is ever created by this path.

## Verification
- `pytest tests/transport/test_ride_request_create.py -q --tb=short`:
  **14 passed, 1 failed** on `afcon360_test`. Sole failure is the
  deferred anonymous-fare 401, not a blocker for this node.
- PostgreSQL type `servicetype` (OID 1321116) labels proven equal to the
  Python `.name` set; lowercase-value rejection proven verbatim
  (`invalid input value for enum servicetype: "on_demand"`).
- Rollback proven by fault injection through the real service error path
  (flush → injected `SQLAlchemyError` → rollback → zero surviving rows).

## Residual Risk
- Commit-time and concurrent same-key race paths are code-reviewed, not
  test-exercised.
- Cycle deadline expiry, retry-new-cycle, and driver-side failures are
  untested (next nodes).
- The 6-line `models.py` diff predates this session's authorship; enum
  workstream owns any further enum changes.

## Follow-ups
- Next node: `BOOKING-LIFECYCLE-OFFER-CREATE` (mapped, not implemented —
  see session report).
- Human rules on the deferred fare-estimation 401 in its own workstream.
- Human confirms PASS → updates register.

## Gate
PASS
