# BOOKING-LIFECYCLE-OFFER-CREATE — Contract

**Previous node:** `BOOKING-LIFECYCLE-REQUEST-CREATE` — PASS
(record: `docs/transport/nodes/BOOKING-LIFECYCLE-REQUEST-CREATE-record.md`)
**Phase:** CONTRACT (review gate; implementation not started)

## 1. Objective

Create durable, sequential driver offers for a `RideRequest`'s active
`SearchCycle` by persisting normalized `OfferAttempt` rows — one
actionable offer at a time, 15-second response deadline, distinct
decline/timeout facts — without creating any `Booking` and without
altering the legacy Booking-anchored dispatch path.

## 2. Source-evidence map (current HEAD `5ef3014`)

### 2.1 Models — schema is ready, writers are missing

- `SearchCycle` (`app/transport/models.py:1479-1529`): statuses
  `searching | converting | completed | expired | cancelled` (`:1512`);
  `deadline`, `completed_at`, `terminal_reason` (`no_supply |
  all_rejected`, `:1518`); `cycle_metadata` JSONB (`:1520`); one-active-
  cycle partial index `uq_search_cycle_active` (`:1494-1499`); terminal
  cycles never reopen, explicit retry mints a new cycle (`:1480-1484`).
- `OfferAttempt` (`:1532-1589`): `cycle_id/driver_id/vehicle_id` (`:1569-
  1571`), `attempt_number` + `candidate_rank` (`:1573-1574`), status
  vocabulary `queued | offered | accepting | declined | timed_out |
  skipped | claim_failed | won | withdrawn` (`:1576-1578`),
  `offered_at/response_deadline/responded_at` (`:1579-1581`),
  `outcome_detail` JSONB (`:1584`); `uq_offer_attempt_number`
  (`:1542`); one-actionable partial index
  `uq_offer_attempt_actionable` on `(cycle_id)` where status in
  `(offered, accepting)` (`:1546-1551`); cycle FK cascades (`:1552-1556`).
- **Verified gap:** zero app-code readers/writers of `OfferAttempt`
  (only `models.py` + `model_registry.py:120` reference it); zero
  writers of `Booking.ride_request_id` (`models.py:1201`).

### 2.2 Legacy matching/offers — Booking-anchored, Redis-backed, unchanged

- Pool: `ProviderService.get_available_drivers(zone, vehicle_class,
  limit=10)` via `_ranked_candidates` (`matching_service.py:68-83`);
  zone from `_pickup_zone(booking)` (`:21`).
- Ranker: `_rank_drivers_for_booking(drivers, booking)` (`:355-435`) —
  freshness/canonical-location gate (`:368-383`), proximity 30/20/10
  (`:387-400`), vehicle-class 25/15 (`:402-409`), rating ×4 (`:412`),
  acceptance ×15 (`:415`), service-type experience +10 (`:417-420`),
  minimum score 40 (`:429`), descending sort (`:434`). Touches `booking`
  in exactly three places: `pickup_location`, vehicle-class metadata +
  `passenger_count`, `service_type.value`.
- Fan-out dispatch: `discover_and_offer(booking_id)` (`:163-247`) offers
  up to `MATCHING_POOL_SIZE = 5` (`:47`); accepted-CAS guard (`:210-219`).
- Offer store: `OfferService.create_offer` (`offer_service.py:191-241`)
  writes Redis hashes, TTL default 300s (`:37`, `TRANSPORT_OFFER_TTL_
  SECONDS`, `_ttl` at `:182-184`); TTL expiry is silent
  (`sweep_expired`, safety-netted by `dispatch_recovery`,
  `app/tasks/transport_recovery.py:82-146`).
- Accept: Lua CAS offered→accepted (`offer_service.py:755-808`,
  `offer_expired`/`offer_conflict`) → driver endpoint
  (`api/driver_routes.py:440-491`) → `AssignmentService.claim`
  (`assignment_service.py:109-183`, guarded UPDATEs, single transaction)
  — **claim is the ownership authority; offer is the pace gate**.
- Decline: Lua withdraw + ledger + best-effort terminal check
  (`offer_service.py:811-859`).
- Terminals: `check_matching_outcome(booking_id)` (`matching_service.py:
  271`) idempotent NO_MATCH close (`no_supply`/`all_rejected`).
- Constants: `MATCHING_WINDOW_SECONDS = 180`, `OFFER_TIMEOUT_SECONDS =
  25` (`matching_service.py:44-48`, MATCH-01-owned).

### 2.3 Reuse seam (no legacy change)

The ranker needs only snapshot primitives — pickup-location dict,
vehicle-class string, passenger count, service-type value string.
A cycle-snapshot adapter SHALL supply these explicitly; the ranker's
signature and the legacy Booking flow MUST NOT change. Ranker input
shape (dicts with `driver_id/vehicle_id/current_location/
location_updated_at/vehicle_classes/average_rating/acceptance_rate/
service_types`) is owned by `ProviderService.get_available_drivers`
and is consumed unchanged.

## 3. Contract decisions

### 3.1 Authority and isolation
- **PostgreSQL rows are authoritative** (`RideRequest`, `SearchCycle`,
  `OfferAttempt`). Redis may carry delivery/notification ONLY, keyed by
  attempt `public_id`/`cycle_key` — never by `booking_ref` (avoids
  colliding with the legacy fan-out namespace). On disagreement, PG
  wins; recovery reconciles Redis from PG, never the reverse.
- Legacy Booking dispatch (`discover_and_offer`, `OfferService` Redis
  offers, driver `<booking_reference>` endpoints, recovery beats)
  continues unchanged. The new path MUST NOT call
  `discover_and_offer` (multi-driver fan-out) for request cycles.

### 3.2 Candidate selection and durable progression
- At first-offer time, snapshot the ranked pool into
  `SearchCycle.cycle_metadata["ranked_pool"]`:
  `[{driver_id, vehicle_id, rank, score}]`. Resume-after-restart reads
  this snapshot plus existing attempts — no recomputation dependency,
  no schema change (fields exist: `:1520`, `:1574`).
- Each attempt records `candidate_rank` from the snapshot.

### 3.3 Sequential offers and 15-second deadline
- Exactly one actionable attempt per cycle, enforced by
  `uq_offer_attempt_actionable` (offered | accepting).
- `response_deadline = offered_at + 15 seconds`, persisted on the row
  at offer time. (Reconciles: legacy 300s TTL / 180s window / 25s
  MATCH-01 constant govern the Booking path only.)
- State transitions (all compatible with model vocab + constraints):
  `queued → offered → accepting → won` (conversion, later node) |
  `offered → declined` (explicit) | `offered → timed_out` (deadline
  passed; recorded as timeout, never rewritten as decline) |
  `offered → withdrawn` (rider cancel/supersede) |
  `offered → skipped` (candidate invalid mid-flight) |
  `accepting → claim_failed` (lost race at conversion).
- Terminal attempt states: declined, timed_out, won, claim_failed,
  withdrawn, skipped. Terminal rows are never resurrected; next driver
  uses the next `attempt_number`.
- Duplicate/late responses: guarded single-row UPDATE conditional on
  expected status (`WHERE status='offered'` / `'accepting'`); a late
  accept on a timed_out/declined row is rejected as conflict and MUST
  NOT advance the cycle (no double-advance).

### 3.4 Progression, recovery, terminals
- On `declined`/`timed_out`/`skipped`: create the next attempt for the
  next snapshot rank (same cycle, `attempt_number` + 1).
- Crash recovery is idempotent by row state: `queued` without delivery
  fact → redeliver; `offered` past deadline without terminal row →
  mark `timed_out`, advance; `accepting` without conversion → verify,
  then advance or convert exactly once.
- `no_supply`: zero ranked candidates at offer time → cycle `expired`,
  `terminal_reason='no_supply'`. `all_rejected`: pool exhausted
  (declined/timed_out/skipped covering all ranks) → cycle `expired`,
  `terminal_reason='all_rejected'`. Mirrors the Booking-path terminal
  vocabulary; cycle stays terminal (model docstring `:1480-1484`).
- Rider retry is explicit only (new cycle, new `cycle_number` +
  `cycle_key`); no silent auto-retry.

### 3.5 Booking invariant
- Request creation, ranking, snapshotting, offer creation, delivery,
  decline, timeout, and progression MUST NOT write any `Booking` row.
  Acceptance-to-Booking conversion is a separately gated node; this
  contract describes only the boundary (`accepting` is the handoff
  state; `won` is set by the conversion node).

## 4. Implementation scope split

**First node (OFFER-CREATE, narrow):** create the FIRST durable
`OfferAttempt` for the top-ranked eligible driver of cycle 1 —
snapshot pool to `cycle_metadata`, INSERT attempt (`offered` with
`offered_at` + 15s `response_deadline`), single-driver delivery
handoff that cannot fan out. Pass criteria: PG-proven attempt row,
correct deadline, one-actionable holds under duplicate create calls,
zero Bookings.
**Next node (OFFER-PROGRESS):** decline/timeout recording, next-driver
advancement, `no_supply`/`all_rejected` terminals, explicit retry new
cycle, crash-recovery proofs.

## 5. Proposed test cases (OFFER-CREATE)
1. Valid cycle → 201-equivalent service call persists exactly one
   `offered` attempt with `response_deadline − offered_at == 15s`.
2. Same cycle duplicate create → same attempt (idempotent, still one row).
3. Zero eligible drivers → no attempt, cycle `expired/no_supply`.
4. Attempt rows reference snapshot ranks; `cycle_metadata.ranked_pool`
   round-trips.
5. Full create flow adds zero `Booking` rows (global + per-user counts).
6. Second actionable attempt for the same cycle is rejected by
   `uq_offer_attempt_actionable`.

## 6. Resolved decisions (contract review)

### D1 — CLOSED: 15-second deadline, legacy constants untouched
- The new lifecycle deadline is **15 seconds from offer activation**,
  where the activation event is the commit of the attempt row with
  status `offered` (see D3). `response_deadline = offered_at + 15s`,
  both persisted on the row.
- Verified non-inheritance (`OFFER_TIMEOUT_SECONDS` /
  `TRANSPORT_OFFER_TTL_SECONDS` live in exactly three places, none
  reachable from request-cycle code):
  `app/config.py:217` (env-backed default `"25"`),
  `app/transport/services/matching_service.py:44-48` (class constant +
  comment), `app/transport/services/offer_service.py:182-184` (reads
  the config key, 300s fallback). The new service SHALL define its own
  `OFFER_RESPONSE_SECONDS = 15` and MUST NOT read either legacy
  constant/key. Legacy Booking matching (180s window, 25s TTL, 300s
  fallback) continues unchanged.

### D2 — RESOLVED: no suitable attempt path exists; response API splits out
Traced delivery/response surface (all Booking-reference-anchored):
- Driver PWA polls `GET /api/transport/drivers/me/offers`
  (`static/js/modules/transport/driver_offer_poll.js:6-12`), which
  reads the Redis per-driver set via `OfferService.list_driver_offers`
  (`offer_service.py:393-412`). Items are booking refs; no attempt
  addressing exists. No Socket.IO/push offer channel exists.
- Driver response endpoints take `<booking_reference>` and call
  `OfferService.accept_offer/decline_offer(booking_ref, driver_id)`
  (`api/driver_routes.py:440-509`, wired `api/routes.py:115-120`).
  Routing an attempt through them would address the wrong entity and
  risk touching Booking state — explicitly forbidden.
- Per-driver notification MECHANISM exists and is reusable:
  `NotificationService.send_driver_notification(driver_id, …)`
  (used by `_notify_driver_new_offer`, `matching_service.py:543-578`;
  best-effort, never raises). Payloads today are Booking-bound; the
  new path SHALL send attempt payloads (`cycle_key`, attempt
  `public_id`, pickup text, `response_deadline`).
- **Decision:** OFFER-CREATE's handoff = persist the `offered` row +
  best-effort per-driver notify via the existing mechanism (no new
  infrastructure). Driver RESPONSE (view/accept/decline of a specific
  attempt) does not exist → split into bounded follow-up node
  `BOOKING-LIFECYCLE-OFFER-RESPONSE` (attempt-addressed endpoints +
  driver list view; must not accept booking refs). OFFER-PROGRESS
  (decline/timeout advancement, terminals, retry) follows RESPONSE.
  Nothing here is described as implemented.

### D3 — RESOLVED: direct-`offered` insert + constraint-backed concurrency
- **Transition chosen: direct `offered` INSERT (one flush).**
  The row is created with `status='offered'`, `offered_at=now`,
  `response_deadline=now+15s` in a single INSERT+commit. The commit IS
  the offer-activation event (D1). Rejected alternative: insert
  `queued` then update to `offered` at delivery — two flushes, wider
  crash window, no benefit since delivery is best-effort anyway.
- **Repeated delivery is idempotent:** delivery reads row state and
  resends only while `status='offered'` and now < `response_deadline`;
  each send appends a fact to `outcome_detail.delivery` (channel,
  timestamp) without changing lifecycle status. Resends never create
  rows and never mutate status.
- **Crash between persistence and delivery:** the row stands as
  `offered` with no delivery fact; recovery resends per the rule
  above. No duplicate row is possible: creation is guarded by the
  one-actionable partial index — a second concurrent INSERT with
  `offered`/`accepting` for the same cycle violates
  `uq_offer_attempt_actionable`; the catcher rolls back, re-reads the
  winner, and returns it (same resolve-to-winner pattern as
  request-create's `IntegrityError` path). `attempt_number` races hit
  `uq_offer_attempt_number` and resolve identically.
- **Late responses cannot double-advance:** driver responses apply via
  guarded single-row UPDATEs conditional on expected status
  (`WHERE status='offered'` for respond; `'accepting'` for conversion).
  A late accept on a `timed_out`/`declined` row matches zero rows →
  rejected as conflict; the cycle advances at most once because only
  one actionable row can exist and each terminal row is immutable.
- **No new schema prerequisite.** All fields/constraints exist
  (`offered_at`, `response_deadline`, `outcome_detail`,
  `uq_offer_attempt_actionable`, `uq_offer_attempt_number`).

## 7. Final scope

**OFFER-CREATE (this node):** snapshot pool → `cycle_metadata`;
INSERT attempt #1 `offered` + 15s deadline; idempotent duplicate-create
(resolves to existing); best-effort per-driver notify; zero Bookings.
**Follow-up OFFER-RESPONSE (bounded):** attempt-addressed driver
view/accept/decline endpoints + list surface; no booking refs.
**Then OFFER-PROGRESS:** timeout sweep, next-driver advancement,
`no_supply`/`all_rejected` terminals, explicit retry, crash-recovery
proofs. Conversion stays a separately gated node.

## Gate
Contract implementation-ready: delivery (persist + best-effort notify),
activation/deadline semantics (commit = activation, +15s persisted),
and concurrent creation (partial-index guards + resolve-to-winner) are
coherent. No application implementation in this task.

## Appendix — superseded §6
D1–D3 as originally framed are closed above; no open decisions remain.
