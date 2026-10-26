# CANCEL-FEE-SCHEDULED-P1 — Contract

**Previous node:** `PICKUP-TIME-AUTHORITY-P1` — committed `b5b5a7a`
**Baseline:** `1793011323` (single migration head, production + test)
**Phase:** CONTRACT (draft authored under the owner's "Plan is final.
Execute." directive; human review in the same node commit)
**Scope owner:** Transport / cancellation policy + driver trip actions

## 1. Objective

Make scheduled-ride cancellation fees truthful and mode-aware, record
driver compensation without touching the wallet, and give the assigned
driver a server-authoritative no-show path after the pickup grace window.
Instant rides, mode-less legacy rides, and safety/mismatch cancellations
remain fee-free.

## 2. Source-evidence map (current HEAD `b5b5a7a`)

- `Booking` (`app/transport/models.py:910`) carries `pickup_time`
  (`:1037`), `pickup_mode` (`:1035`), `request_received_at` (`:1036`),
  `final_price` (`:1080`), `currency` (`:1083`), `booking_metadata`
  JSONB (`:1160`), `cancellation_fee` (`:1116`),
  `cancellation_initiated_by` (`:1115`), `cancelled_stage` (`:1114`),
  `assigned_driver_id` (`:1120`).
- `BookingStatus` includes `PICKUP_ARRIVED`, `NO_SHOW`
  (`app/utils/enums.py:55`, `:59`); `STATUS_TRANSITIONS` permits
  `PICKUP_ARRIVED -> NO_SHOW`
  (`app/transport/services/booking_service.py:185`).
- Current cancellation fee tiers are the old 24h/4h/2h policy
  (`booking_service.py:1886-1918`); the grace window is 0 minutes and a
  past pickup is always free (`:1910`). This is the behavior to replace
  for scheduled rides only.
- `cancel_booking` (`booking_service.py:867`) currently charges every
  stage, uses `user_id == booking.user_id` nowhere for fee authority,
  does not persist `cancellation_initiated_by` pre-assignment (`:949-
  957`), and post-assignment calls `AssignmentService.release`
  (`:971`) before a second UPDATE (`:985-1000`). The node must preserve
  safety waiver (`:900-906`, `:927-935`) and canonical release.
- `AssignmentService.release` (`app/transport/services/
  assignment_service.py:406`) is the only canonical terminal release;
  it clears `assigned_driver_id`/`assigned_vehicle_id`, frees
  resources, writes audit, and commits (`:535-536`). It must not be
  modified.
- Driver trip actions are the shared table
  `_DRIVER_TRIP_ACTIONS` (`app/transport/api/driver_routes.py:513`) and
  `_execute_driver_trip_action` (`:521`); the reference-keyed resource
  is `DriverTripReferenceResource` (`:707`). The table currently has
  `en_route|arrive|start|complete`.
- Driver rows are serialized by `_driver_trip_row`
  (`booking_service.py:1622`) and active-trip state by
  `_driver_active_trip` (`app/transport/routes.py:2115`); the dashboard
  card renders `.trip-action` (`templates/transport/driver/
  driver_dashboard.html:213-251`) and the JS dispatcher (`:1536-1558`).
- Rider page is `rides_show` (`app/transport/routes.py:1206`); cancel
  is `rides_cancel` (`:1315`). The modal copy currently promises "no
  fee" for `pending_payment`/`confirmed`
  (`templates/transport/rides/show.html:501-522`) and
  `confirmCancel` ignores the response (`:563-605`).
- `get_driver_earnings` (`booking_service.py:1733`) only sums
  `COMPLETED` + captured payment; metadata credits are deliberately not
  added to it in this node.

## 3. Contract decisions

### 3.1 Mode gate and authority
- Scheduled status is `booking_metadata["booking_mode"] == "scheduled"`
  (trimmed, case-insensitive). This is the P1 canonical metadata gate;
  a missing/`instant` mode is a fail-safe zero fee.
- `pickup_mode` remains the persisted column from P1 but does not
  replace the metadata gate for fee authority.
- The server is the fee authority. Client previews are advisory only;
  the server recalculates at cancellation time.

### 3.2 Scheduled cancellation tiers
Let `delta = pickup_time - now` (timezone-aware; naive pickup treated as
UTC) and `fare = final_price`.
- `delta > 1 hour` → **0%**, fee `0`.
- `15 minutes <= delta <= 1 hour` → **20% of fare**, capped at
  **10,000** in the booking currency.
- `delta < 15 minutes` (including a past pickup) → **40% of fare**,
  capped at **20,000** in the booking currency.
- Exact 1 hour is 20%; exact 15 minutes is 20%; exactly at pickup is 40%.
- Fees round to 2 decimal places and never exceed the cap or the fare.
- Caps are face value in the booking's currency; no FX conversion.
- Scheduled with no released `pickup_time` → 0 (cannot price an
  unreleased slot).
- Safety/mismatch categories (`driver_vehicle_mismatch`,
  `driver_identity_mismatch`, `safety_concern`,
  `driver_requested_cancel`, `unexpected_driver_behaviour`) → 0.
- Non-rider actors (admin/provider) → 0 and `cancellation_initiated_by`
  is not `rider`; the rider is the only fee-bearing cancel actor.
- Instant or mode-less → 0.

### 3.3 Fee recording
- The existing `cancellation_fee` column is written for scheduled rider
  cancellations.
- `booking_metadata["cancellation"]` records:
  `fee`, `currency`, `tier`, `policy: "scheduled_v1"`,
  `recorded_uncollected: true`, `initiated_by`, `at`.
- A `booking_cancellation_fee_recorded` audit row is added in the same
  transaction with public identifiers only.
- No wallet, payment, or reconciliation mutation.

### 3.4 Driver credits (non-wallet)
- On a fee-bearing rider cancellation **with an assigned driver**,
  append to `booking_metadata["driver_cancellation_credits"]`:
  `driver_code`, `driver_user_public_id`, `amount`, `currency`,
  `reason: "late_cancellation"`, `recorded_uncollected: true`,
  `booking_reference`, `at`.
- Amount = **80% of the cancellation fee**; 0 when fee is 0.
- No `DriverProfile.total_earnings` write. Credits are metadata facts
  only until a future ledger node.

### 3.5 Rider cancellation flow
- Keep `STATUS_TRANSITIONS`, `AssignmentService`, and the existing
  cancellable status set unchanged.
- Pre-assignment: one guarded UPDATE (status, timestamps, reason,
  safety, stage, fee, initiated_by, metadata) and commit.
- Post-assignment: capture driver code + user public id and compose
  metadata/credit/fee **before** release; flush; then call
  `AssignmentService.release` so fee, credit, audit, status, and
  resource clearing commit atomically. Do not mutate the assignment
  afterwards.
- Return `booking_reference`, `cancellation_fee`, `refund_amount`,
  `stage_at_cancellation`, `safety_cancellation`, and `release`.
  `refund_amount = max(0, final_price - fee)`.
- `cancellation_initiated_by` is `rider` only when
  `user_id == booking.user_id`; otherwise `admin` (the established
  non-rider authority; no new role inference).

### 3.6 Driver no-show
- New service method `BookingService.mark_no_show(booking_id,
  driver_user_id)`.
- Require: scheduled mode; `PICKUP_ARRIVED`; booking assigned to the
  caller's `DriverProfile`; `pickup_time` present; now >= pickup_time +
  **15 minutes**.
- Fee = **40% of fare**, cap **20,000**, recorded as uncollected in
  `booking_metadata["no_show"]` and in `cancellation_fee` (no-show is a
  terminal fee-bearing outcome; `cancelled_stage = pickup_arrived`,
  `cancellation_initiated_by = driver`).
- Driver credit = **100% of the no-show fee**, same metadata list,
  `reason: "no_show"`.
- Use `transition_status(NO_SHOW)` for the state transition; no direct
  status write and no `no_show_at` attribute.
- Idempotent: a booking already `NO_SHOW` returns the existing result
  without duplicating fee or credit.
- Audit `booking_no_show_recorded` in the same transaction with public
  identifiers and amounts.
- Any wrong status, wrong driver, instant/mode-less, missing pickup, or
  early call is a typed 409/403, never a silent success.

### 3.7 Driver API
- Add `no_show` to `_DRIVER_TRIP_ACTIONS` (PICKUP_ARRIVED -> NO_SHOW)
  and dispatch it to `mark_no_show` before the generic transition path.
- Both the legacy internal-id and reference-keyed resources share the
  same behavior; the dashboard uses only the reference-keyed URL.
- Action validation text includes `no_show`.
- Do not change `STATUS_TRANSITIONS` or `AssignmentService`.

### 3.8 Driver row and dashboard
- `_driver_trip_row` adds `booking_mode` (derived from metadata) and
  `can_mark_no_show` = scheduled + `pickup_arrived` + assigned driver +
  pickup + 15 minutes elapsed.
- The Active Trip card renders a secondary "Rider no-show" button when
  `can_mark_no_show`, using the existing `.trip-action` POST, CSRF
  helper, confirm, and reload behavior. The no-show action is not
  offered before the grace window.

### 3.9 Rider copy
- `rides_show` passes the scheduled flag, currency, pickup ISO, and a
  server-computed fee preview.
- The modal replaces false "no fee" stage promises with:
  - safety: fee waived;
  - instant/mode-less: scheduled fee does not apply;
  - scheduled preview 0: no fee now;
  - scheduled preview > 0: exact fee in the booking currency, recorded
    as uncollected.
- On success, show the server-returned fee/refund before reload; never
  claim a fee that the server did not return.

## 4. Scope

**In scope**
- `app/transport/services/booking_service.py`
- `app/transport/api/driver_routes.py`
- `app/transport/routes.py`
- `templates/transport/rides/show.html`
- `templates/transport/driver/driver_dashboard.html`
- `tests/transport/test_cancel_fee_scheduled_p1.py` (new)
- this contract, its evidence, its record, and `BACKLOG.md`

**Out of scope**
- Wallet, payments, `PaymentMethodConfig`, cash rejection, card/mobile
  money, `DriverProfile.total_earnings`, ledger collection.
- `STATUS_TRANSITIONS`, `AssignmentService`, `Booking` model,
  migrations, `no_show_at`, pickup-time authority, idempotency,
  `_split_rides`, `is_upcoming`, `current_booking`, instant-ride fee
  policy.
- Existing tests and shared fixtures.
- Production migration/cutover.

## 5. Interface contract

- `BookingService._calculate_cancellation_fee(booking, now=None)`:
  Decimal; scheduled-only policy above; no side effects.
- `BookingService._cancellation_policy(booking, now=None)`: internal
  dict with `scheduled`, `fee`, `currency`, `tier`, `percentage`,
  `cap`, `pickup_time`.
- `BookingService.mark_no_show(booking_id, driver_user_id)`: dict;
  raises `NotFoundError`, `PermissionError`, `ValidationError`.
- `BookingService.cancel_booking(...)` keeps its signature and adds fee
  metadata plus `booking_reference` to the result.
- `POST /api/transport/drivers/me/trips/<booking_reference>/status`
  accepts `{"action": "no_show"}`; 200 on success, 403 wrong driver,
  409 invalid state/timing, 404 unknown booking.
- Rider cancel JSON returns `body.data.cancellation_fee` and
  `body.data.refund_amount`.

## 6. Proof of done (test matrix)

`tests/transport/test_cancel_fee_scheduled_p1.py`:
1. Scheduled >1h, exactly 1h, 15m-1h, exactly 15m, <15m, past pickup.
2. Caps at 10,000 / 20,000; fare below caps; currency unchanged.
3. Safety categories, instant, missing mode, non-rider → 0.
4. Pre-assignment fee recorded, no driver credit, rider initiated.
5. Post-assignment fee + 80% credit, assignment released, metadata
   public-only, `cancellation_initiated_by="rider"`.
6. No-show: wrong driver 403; early 409; instant 409; success after
   grace; 40% fee/100% credit; status NO_SHOW; assignment released;
   idempotent second call adds nothing.
7. `_driver_trip_row` `booking_mode` + `can_mark_no_show` before/after
   grace; driver dashboard template source contains the no-show action.
8. Rider page preview uses scheduled fee and no false "no fee" for
   pending/confirmed; cancel JSON carries fee/refund.
9. Existing P1, D5, match01-retry, and UI14F1 suites remain green.

**Verification commands**
- `python -c "from app import create_app; create_app(); print('DB_VERIFY_OK')"`
- `flask db heads` → `1793011323` (single)
- targeted pytest for the new file
- P1 files, `test_ui14_d5_confirm_wording.py`,
  `test_match01_retry.py`, `test_ui14f1_schedule_consistency.py`
- Playwright MCP on the isolated test DB: rider copy at >1h, 15m-1h,
  <15m; driver button before/after grace.

## 7. Rollback and risk

- Code-only; no migration. Rollback is revert of the node commit.
- Main risks: boundary drift (use timedeltas, not float hours), stale
  rider preview (server recalculates), release ordering (metadata flush
  before `AssignmentService.release`), and double-crediting (idempotent
  no-show; cancel is terminal).
- Production schema is already at `1793011323`; this node adds no
  schema change and does not authorize production operations.

## 8. Acceptance criteria

- Every fee decision is explainable by the policy above and server
  evidence.
- Riders never see a false fee promise; drivers never see a no-show
  action before grace.
- Driver compensation is recorded, not silently paid or dropped.
- No wallet, assignment, status-map, migration, or shared-fixture change.
- Full targeted verification green.
