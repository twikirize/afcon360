# CANCEL-FEE-SCHEDULED-P1 — Evidence

## Node ID

CANCEL-FEE-SCHEDULED-P1

## Status

PASS for the authorized node scope. Two acceptance-record deviations are
disclosed in §7: the contract's baseline revision is stale after a
concurrent M3 commit, and the contract's D5-green criterion cannot be met
at the parent baseline because six D5 assertions are already red. Neither
deviation was caused by this node.

## Date

2026-10-26

## Baseline and actual parent

- Contract header: previous node `PICKUP-TIME-AUTHORITY-P1`, committed
  `b5b5a7a`; baseline `1793011323`.
- Actual parent at closeout: `b9dabb8` — `transport: apply corrected
  pickup-time constraint M3 and record prod revision` (concurrent commit,
  not authored by this node).
- Actual `flask db heads` / `flask db current`: `1793013676 (head)`.
- This node adds no migration and does not modify schema. The stale
  contract baseline is recorded, not rewritten.

## Objective

Scheduled cancellation fees must be truthful and mode-aware; driver
compensation must be recorded without touching the wallet; the assigned
driver must have a server-authoritative no-show action only after the
15-minute grace window. Instant, mode-less, safety/mismatch, and
non-rider cancellations remain fee-free.

## Source evidence

### Policy constants and time helpers

`app/transport/services/booking_service.py:48-87`

- `SCHEDULED_BOOKING_MODE = "scheduled"`.
- `CANCEL_FEE_STANDARD_CAP = Decimal("10000.00")`.
- `CANCEL_FEE_LATE_CAP = Decimal("20000.00")`.
- `NO_SHOW_FEE_RATE = Decimal("0.40")`; `NO_SHOW_FEE_CAP = Decimal("20000.00")`.
- `NO_SHOW_GRACE = timedelta(minutes=15)`.
- `DRIVER_LATE_CANCEL_CREDIT_RATE = Decimal("0.80")`.
- `_booking_mode()` reads only `booking_metadata["booking_mode"]`,
  trims/lowercases, and returns `""` for a missing/non-string value.
- `_booking_currency_code()` and `_money()` centralize currency/Decimal
  handling; `_as_utc()` normalizes naive values to UTC.

### Fee policy

`app/transport/services/booking_service.py:2215-2310`

- `get_cancellation_policy()` is the read-only preview API.
- `_cancellation_policy()` returns `scheduled`, `fee`, `currency`, `tier`,
  `percentage`, `cap`, and `pickup_time`.
- `delta > 1h` → tier `more_than_1h`, 0%.
- `15m <= delta <= 1h` → 20%, cap `10,000`; exact 1h and exact 15m are 20%.
- `delta < 15m` including a past pickup → 40%, cap `20,000`; exact pickup
  is 40%.
- No scheduled mode or no released pickup → zero, fail-safe.
- Fee is rounded to 2 decimals and clamped to the cap and the fare.
- Caps are face value in the booking currency; no FX conversion.
- `_calculate_no_show_fee()`: 40% of fare, cap `20,000`, never above fare.

### Rider cancellation

`app/transport/services/booking_service.py:912-1175`

- Fee authority is `booking.user_id == user_id`; only the rider can be
  fee-bearing. Otherwise `cancellation_initiated_by = "admin"` and the fee
  is zero.
- Safety/mismatch categories set fee zero and tier `safety`.
- `booking_metadata["cancellation"]` records `fee`, `currency`, `tier`,
  `policy: "scheduled_v1"`, `recorded_uncollected: true`, `initiated_by`,
  `scheduled`, `percentage`, and `at`.
- Audit action `booking_cancellation_fee_recorded` is added in the same
  transaction with public booking reference and no internal IDs.
- Pre-assignment: one guarded `UPDATE` (id, current status, not deleted)
  writes status/timestamps/reason/stage/fee/initiator/metadata; rowcount
  must be 1.
- Post-assignment: fee, metadata, driver credit, and audit are flushed
  before `AssignmentService.release`; release commits them atomically with
  status `cancelled` and resource clearing. The assignment is not mutated
  afterwards.
- Response carries `booking_reference`, `cancellation_fee`,
  `refund_amount = max(0, final_price - fee)`, `currency`, `fee_tier`,
  `recorded_uncollected`, `driver_credit`, `stage_at_cancellation`,
  `safety_cancellation`, and `release`.

### Driver credits (metadata only)

`app/transport/services/booking_service.py:1013-1034, 2312-2337`

- A fee-bearing rider cancellation with an assigned driver appends to
  `booking_metadata["driver_cancellation_credits"]` with `driver_code`,
  `driver_user_public_id`, `amount`, `currency`,
  `reason: "late_cancellation"`, `recorded_uncollected: true`,
  `booking_reference`, and `at`.
- Amount is 80% of the cancellation fee.
- No `DriverProfile.total_earnings`, wallet, payment, or ledger write.
- `driver_user_public_id` is the public UUID; no internal user id.

### Driver no-show

`app/transport/services/booking_service.py:1178-1356`

- `mark_no_show(booking_id, driver_user_id)` resolves the caller's
  `DriverProfile` by `user_id`.
- Requires scheduled metadata mode, `pickup_arrived`, live assignment to
  that profile, released `pickup_time`, and `now >= pickup + 15 minutes`.
- Records `cancellation_fee`, `cancelled_stage = pickup_arrived`,
  `cancellation_initiated_by = "driver"`, and
  `booking_metadata["no_show"]` (`fee`, `currency`,
  `recorded_uncollected`, `grace_minutes`, `marked_at`, `marked_by`,
  `driver_code`, `driver_user_public_id`, `driver_credit`).
- Appends a 100%-of-fee driver credit with `reason: "no_show"`.
- Audit action `booking_no_show_recorded` is added before the transition.
- `transition_status(NO_SHOW)` owns the status transition; no direct status
  write and no `no_show_at`.
- Sequential idempotency: an already-`NO_SHOW` booking returns the
  recorded result and adds no fee/credit. Authorization for that path uses
  the recorded `driver_code` because release clears `assigned_driver_id`.
- Errors: unknown booking 404; wrong driver/no profile 403; wrong state,
  instant/mode-less, missing pickup, or early call 409.

### Driver API and dashboard

`app/transport/api/driver_routes.py:513-571`

- `no_show` is in `_DRIVER_TRIP_ACTIONS` as `pickup_arrived -> no_show`.
- `_execute_driver_trip_action()` special-cases `no_show` to
  `BookingService.mark_no_show` before the generic transition path.
- Action validation text advertises `no_show`.
- Internal-id and reference-keyed resources share the dispatcher; the
  dashboard uses the reference-keyed URL.

`app/transport/services/booking_service.py:1932-1963`

- `_driver_trip_row()` adds `booking_mode` and `can_mark_no_show`:
  scheduled + `pickup_arrived` + assigned driver + pickup present + grace
  elapsed.

`templates/transport/driver/driver_dashboard.html:242-262, 1545-1555`

- Active-trip actions render only when `next_action` or
  `can_mark_no_show`.
- The secondary “Rider no-show” button is rendered only when
  `can_mark_no_show`; it uses the existing `.trip-action` POST, CSRF
  helper, confirmation, and reload.
- The confirmation text explicitly names the 15-minute grace and the
  no-show fee.

### Rider preview and copy

`app/transport/routes.py:1265-1344`

- `rides_show()` computes `cancellation_policy_preview` server-side and
  passes `booking_mode`, `booking_currency`, `pickup_time_iso`, and the
  preview to the template.
- Preview failure falls back to a non-scheduled zero-fee shape; it does not
  invent a fee.

`templates/transport/rides/show.html:492-530, 590-607`

- `cancellationMessage()` uses the server preview:
  - safety → fee waived;
  - non-scheduled/mode-less → scheduled fee does not apply;
  - scheduled fee 0 → no fee now;
  - scheduled fee > 0 → exact fee in the booking currency, recorded as
    uncollected.
- On success, the server-returned fee/refund are shown before reload.
- No client-side re-derivation of the tier or cap.

### Unchanged contracts

- `STATUS_TRANSITIONS` (`booking_service.py:222-235`) unchanged.
- `AssignmentService` unchanged.
- `Booking` model unchanged; no migration.
- No wallet, payment, `DriverProfile.total_earnings`, or ledger change.
- No shared fixture or existing test changed.

## Test evidence

All pytest runs used the PostgreSQL-backed test database.

### New node suite

```text
& .venv/Scripts/python.exe -m pytest tests/transport/test_cancel_fee_scheduled_p1.py -q --tb=short
16 passed, 2 warnings in 58.73s
```

Coverage:

- Tier boundaries: `>1h`, exact `1h`, `15m-1h`, exact `15m`, `<15m`, past
  pickup.
- Caps `10,000`/`20,000`, low fare, currency face value.
- Instant and mode-less fail-safe zero.
- Pre-assignment fee/refund, no driver credit, rider initiator.
- Post-assignment fee + 80% credit, release, public-only metadata.
- Safety waiver and non-rider zero.
- No-show after grace: 40% fee, 100% credit, `NO_SHOW`, release,
  idempotent second call.
- No-show before grace, wrong driver, instant mode.
- Reference-keyed driver API.
- `_driver_trip_row` gating, dashboard action source, rider server preview,
  cancel JSON fee/refund.

### P1 regression gate

```text
& .venv/Scripts/python.exe -m pytest \
  tests/transport/test_pickup_time_authority_p1.py \
  tests/transport/test_booking_mode_probe.py \
  tests/transport/test_scheduled_release_p1.py \
  tests/transport/test_scheduled_route_capacity_p1.py -q --tb=short
46 passed, 42 warnings in 101.07s
```

### UI/retry regression

```text
& .venv/Scripts/python.exe -m pytest \
  tests/transport/test_match01_retry.py \
  tests/transport/test_ui14f1_schedule_consistency.py \
  tests/transport/test_ui14_d5_confirm_wording.py -q --tb=short
22 passed, 2 warnings in 48.30s
```

### Concurrent-claim regression

```text
& .venv/Scripts/python.exe -m pytest tests/test_transport_concurrent_claim.py -q --tb=short
29 passed, 22 warnings in 56.71s
```

### D5 suite — pre-existing failures, not caused by this node

```text
& .venv/Scripts/python.exe -m pytest tests/test_transport_d5_execution_lifecycle.py -q --tb=line
6 failed, 22 passed, 37 warnings in 95.71s
```

Failing tests:

- `TestBookingCancellation::test_dispute_latches_then_cancel_releases`
- `TestBookingCancellation::test_illegal_in_progress_to_cancelled_refused`
- `TestExecutionConcurrency::test_start_before_no_show_blocks_no_show`
- `TestRecoveryVsProgress::test_progress_before_recovery_keeps_trip`
- `TestModeratorBookingActions::test_moderator_reject_in_progress_blocked`
- `TestModeratorBookingActions::test_moderator_reject_requires_reason`

Every failure is an `is_available is False` assertion after claim/release.
At `b5b5a7a`, `app/transport/services/assignment_service.py` already carries
the `SUPPLY-00a` comments “claim no longer writes is_available” and
“release no longer writes is_available”; the D5 tests still assert the
retired write. This is a baseline test/contract mismatch, out of scope and
not modified.

### Database and HEAD checks

```text
python -c "from app import create_app; create_app(); print('DB_VERIFY_OK')"
DB_VERIFY_OK

flask db heads   → 1793013676 (head)
flask db current → 1793013676 (head)
```

No migration was authored or applied by this node.

## Browser evidence (Playwright MCP, isolated test DB)

Server: `http://127.0.0.1:5611` (`tests/browser/start_test_server.py`,
`TestingConfig`, isolated `*_test` database). Server was stopped after
evidence collection.

Seed rows (rider `d3_rider`):

- `CF-BR-OVER-255C35` — scheduled pickup +2h.
- `CF-BR-MID-540648` — scheduled pickup +45m.
- `CF-BR-LATE-EF3FCB` — scheduled pickup +10m.
- `CF-BR-DRV-E7A08C` — scheduled pickup -20m, `pickup_arrived`, assigned
  driver `D3DRV001`.

### Rider preview messages

- `CF-BR-OVER-255C35`:
  `No cancellation fee applies right now.`
- `CF-BR-MID-540648`:
  `A cancellation fee of USD 20.00 applies based on the scheduled pickup time. It will be recorded as uncollected.`
- `CF-BR-LATE-EF3FCB`:
  `A cancellation fee of USD 40.00 applies based on the scheduled pickup time. It will be recorded as uncollected.`

### Driver gating and end-to-end no-show

- Before grace (pickup +10m): no `Rider no-show` button; `Start trip` still
  rendered.
- After grace (pickup -20m): `Rider no-show` button rendered.
- Clicking it showed:
  `Confirm the rider did not show up after the 15-minute grace period? A no-show fee will be recorded.`
- After accepting, the booking persisted as:

```text
status no_show
fee 40.00
stage pickup_arrived
initiated_by driver
no_show: driver_code D3DRV001, fee 40.00, currency USD,
         recorded_uncollected true, grace_minutes 15
driver_cancellation_credits: reason no_show, amount 40.00, currency USD,
         recorded_uncollected true
```

Evidence files:

- `.playwright-mcp/driver-no-show-after-grace.png`
- `.playwright-mcp/driver-no-show-before-grace.png`

No application console errors were observed on the ride pages or driver
dashboard. Login-page CSP report-only messages are pre-existing.

## 7. Disclosed deviations

### 7.1 Contract baseline is stale after concurrent M3 commit

The contract header records `b5b5a7a` and baseline `1793011323`. Between
implementation and closeout, commit `b9dabb8` (not authored by this node)
applied the corrected M3 pickup-time constraint and updated the repository
record. Actual parent/head is `b9dabb8` / `1793013676`. The node itself is
code-only and adds no migration; this is a record correction, not a schema
change by this node. The contract's `flask db heads → 1793011323`
verification line therefore cannot be reproduced; the observed value is
`1793013676`.

### 7.2 Contract D5-green criterion cannot be met at baseline

Contract §6 item 9 requires existing D5 tests to remain green. They are not
green at the parent baseline: six assertions are stale after `SUPPLY-00a`
removed `is_available` writes from claim/release. This node does not touch
D5 behavior, `AssignmentService`, or those tests. The six failures are
recorded in `BACKLOG.md` as a separate deferred item.

## 8. Residual risks

- Fees and driver credits are metadata facts only. Collection, refunds,
  reconciliation, and driver earnings are not implemented; those are
  separate wallet/ledger nodes.
- Caps are face value in the booking currency. No FX policy exists.
- The rider preview is computed at page load. If the pickup time crosses a
  tier boundary before the rider confirms, the server recalculates and the
  returned fee is authoritative; the displayed preview may be stale.
- No-show idempotency is proven sequentially. Concurrent no-show requests
  are not serialized with an explicit row lock; the guarded status
  transition remains the final state authority, but a concurrency-specific
  no-show test is not part of this node.
- The no-show action is driver-only; no admin/moderator no-show path exists.
- D5 baseline failures remain open and are not a pass claim for that suite.

## 9. Gate

Node-scope behavior, targeted regression, browser gating, and end-to-end
no-show evidence are PASS. The two disclosed deviations above are recorded
for human review in the node commit. No wallet, migration, assignment,
status-map, model, or shared-fixture change was made.
