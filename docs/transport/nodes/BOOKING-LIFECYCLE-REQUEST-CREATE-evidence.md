# BOOKING-LIFECYCLE-REQUEST-CREATE — Evidence

## Node ID
BOOKING-LIFECYCLE-REQUEST-CREATE

## Objective
Rider on-demand hailing must create a `RideRequest` plus its initial
`SearchCycle` atomically, enforce idempotent replay on
(owner, idempotency_key), reject conflicting payloads without mutation,
roll back partial persistence, and never produce a premature `Booking`.

## Product Guarantee
A rider's request exists exactly once per idempotency key; a concurrent
or retried call can neither duplicate it nor silently replace it, and no
driver-facing or financial record (`Booking`) exists before acceptance.

## Source Code Proven

### Models (`app/transport/models.py`)
- `Booking.service_type` (line 1089):
  `PgEnum(ServiceTypeEnum, name="servicetype", create_type=False)`,
  nullable=False — class-attached canonical mapping.
- `Booking` conversion linkage (lines 1198-1201):
  `ride_request_id` / `search_cycle_id` FKs with explicit names
  `fk_transport_bookings_ride_request` /
  `fk_transport_bookings_search_cycle`, nullable, plus partial unique
  `ix_booking_ride_request` (line 1065-1066). Zero writers in app code.
- `RideRequest.service_type` (lines 1447-1450):
  `PgEnum(ServiceTypeEnum, name="servicetype", create_type=False)`,
  nullable=False — class-attached, parity with `Booking`. (Working-tree
  correction; see Change History.)
- `RideRequest` (line 1416): `uq_ride_request_owner_key` on
  (user_id, idempotency_key); `SearchCycle` (line 1479):
  `uq_search_cycle_number` / `uq_search_cycle_key`.
- Canonical enum (`app/utils/enums.py:30-38`): `class ServiceType(str, Enum)`,
  8 members, UPPER names / lowercase values
  (`ON_DEMAND = 'on_demand'`, etc.).

### Service (`app/transport/services/ride_request_service.py`)
- `create_request` (line 210): validate → estimate fare → fingerprint
  (`_trip_hash`, incl. `requested_currency` + pickup-time bucket) →
  replay-or-conflict check (lines 343-355) → add `RideRequest` + flush
  (lines 390-391) → add cycle-1 `SearchCycle` + flush (lines 400-401) →
  commit (line 402).
- `except IntegrityError` (lines 403-419): rollback, resolve to winner
  (replay) or raise `IdempotencyConflictError`. Never a duplicate.
- `except SQLAlchemyError` (lines 422-425): rollback + raise
  `ServiceUnavailableError`. No generic `except Exception`: programming
  errors propagate (fail-loud by design).
- `serialize_request` (lines 175-204): exposes `public_id` only; internal
  `id` never serialized.

### Endpoint (`app/transport/api/ride_request_routes.py`, 58 lines)
- `POST /api/transport/ride-requests`, gates: `login_required` +
  `require_profile_completion` + `require_kyc_tier(2)` (lines 30-34).
- Maps `IdempotencyConflictError → 409`, `ValidationError → 400`,
  success → 201 (200 on replay). `ServiceUnavailableError` is a plain
  `Exception` (`app/utils/exceptions.py:40`) → Flask catch-all 500.

### Tests (`tests/transport/test_ride_request_create.py`)
- `TestRequestCreate::test_valid_request_creates_one_request_and_one_cycle`
- `TestRequestCreate::test_zero_booking_rows_and_no_reference`
- `TestRequestCreate::test_identical_replay_resolves_to_same_request_and_cycle`
- `TestRequestCreate::test_key_reuse_with_different_trip_is_conflict_without_mutation`
- `TestRollbackAfterPartialFlush::test_cycle_failure_rolls_back_flushed_request`
- `TestCommitmentGates` (anonymous 401, ineligible-tier redirect),
  `TestCanonicalValidation` (invalid payloads, zero rows),
  `TestLegacyPathsUnchanged` (discovery open; fare served — deferred, failing).

## PostgreSQL Evidence (`afcon360_test`)

- `transport_bookings.service_type` and
  `transport_ride_requests.service_type` both bind type `servicetype`,
  OID 1321116; ordered labels
  `AIRPORT_ARRIVAL, AIRPORT_DEPARTURE, STADIUM_SHUTTLE, HOTEL_TRANSFER,
  CITY_TOUR, ON_DEMAND, SCHEDULED_ROUTE, CUSTOM_TOUR` — equal to the
  Python `.name` set, not the `.value` set.
- Direct cast probe (read-only SELECT): `'on_demand'::servicetype`
  → `invalid input value for enum servicetype: "on_demand"`;
  `'ON_DEMAND'::servicetype` → accepted. This was the exact flush
  failure mode of the earlier bare-`PgEnum` declaration (bound literal
  was lowercase `'on_demand'`), resolved by the class-attached mapping
  (binds member name `'ON_DEMAND'`).

## Test Evidence (PostgreSQL-backed)

```
pytest tests/transport/test_ride_request_create.py -q --tb=short
1 failed, 14 passed
```
- Sole failure: `test_canonical_fare_estimate_still_served` (anonymous
  fare 401) — separately deferred fare-workstream discrepancy, not a
  blocker for this node.
- Creation: 201 + response shape (no `booking_reference` /
  `assigned_driver` / internal ids) + live counts `(requests, cycles,
  bookings) == (1, 1, 0)`.
- Replay: second POST → 200, `replayed: true`, identical `request_id` +
  cycle, counts unchanged (1, 1, 0).
- Conflict: same key + different dropoff → 409 `idempotency_conflict`;
  stored snapshot latitude unchanged; counts (1, 1, 0).
- Rollback (fault injection): `SearchCycle.before_insert` listener gated
  on the test's `cycle_key` records non-None `ride_request_id` (proves
  the `RideRequest` flush ran first), then raises `SQLAlchemyError`;
  endpoint 500s; fresh-session queries show zero `RideRequest` for the
  key, zero `SearchCycle` for the cycle key, global `Booking` count
  unchanged, rider row intact; listener removed in `finally` + verified
  via `event.contains`.
- Gates: anonymous POST → 401 with zero rows; sub-tier-2 rider redirected
  with zero rows; invalid payloads → 400/422 with zero rows.

## Change History (this node, working tree)
- `app/transport/services/ride_request_service.py`: stale
  `Currency.enums` membership → `{m.value for m in Currency}`
  (session fix; `.enums` never existed on the `str, Enum` classes).
- `app/transport/models.py` 6-line diff (pre-existing in tree, preserved,
  authorship external): `RideRequest.service_type` bare `PgEnum` →
  class-attached `PgEnum(ServiceTypeEnum, …)`; Booking linkage FKs gained
  explicit constraint names matching the migration.
- `tests/transport/test_ride_request_create.py`: conftest-compliant
  `_login_as` + discovery URL corrections; new
  `TestRollbackAfterPartialFlush` class.

## Proven vs Not-Yet-Tested Failure Modes
- PROVEN: `SearchCycle` INSERT failure after successful `RideRequest`
  flush → service rollback, neither row persists.
- NOT tested: commit-time failure after both flushes; concurrent
  same-key race (`IntegrityError` winner-resolution path); cycle
  deadline expiry; retry opening cycle 2; driver-side failures.
- The `IntegrityError` race path (lines 403-419) is code-reviewed only.

## Gate
PASS — creation, replay, conflict-without-mutation, rollback, and
zero-premature-Booking proven against PostgreSQL; unrelated fare failure
kept separate.
