# TH-3-D2 — Specification & Entry Gate: Atomic Dispatch Claim

**Status:** SPECIFICATION COMPLETE — CORRECTED AFTER ADVERSARIAL ENTRY REVIEW — FINAL ARTIFACT INTEGRITY PASS APPLIED — FINAL DOCUMENTATION PRECISION CLOSURE APPLIED (2026-09-11, §28.2) — **TH-3-D2 SPECIFICATION PASSES FINAL ARTIFACT INTEGRITY REVIEW — READY FOR MOE AUTHORIZATION.** — **Gate B REMAINS NOT AUTHORIZED** (**IMPLEMENTATION NOT AUTHORIZED**)
**Node:** TH-3-D2 (READ-ONLY; 0 production changes, 0 test changes, 0 migrations)
**Date created:** 2026-09-11
**Corrected:** 2026-09-11 (Gate-B-Closure specification correction pass — 14 corrections; history §28)
**Final artifact-integrity pass:** 2026-09-11 (4 corrections: canonical claim SQL single-source §5; `actor_is_admin` authorization contract §4/§14; lock-duration risk §24.1; honest Git attribution §27.1; history §28)
**Final documentation-precision closure:** 2026-09-11 (Item A: canonical-SQL occurrence reconciliation — Canonical claim SQL = §5, no competing definition exists; Item B: mandated verification tables in §28.2; artifact finished per mandate with NO IMPLEMENTATION PERFORMED)
**Prerequisite:** TH-3-D1 = PASS — COMPLETE (sealed). This specification extends the D1 graph fit; nothing in §10 of `docs/transport/geographic-graph-map.md` is changed.

**Scope guard:** Spec only. Implementation, tests, migrations, and D3 are NOT started. The P0 boundary is proven 0-migration (Decision A re-confirmed in §24).

---

## 1. D2 STATUS

**SPECIFICATION PHASE.** Gate A (this document) delivered. Final artifact-integrity pass applied (2026-09-11 — 4 corrections, §28.1). Final documentation-precision closure applied (2026-09-11 — Item A canonical-SQL reconciliation + Item B mandated verification tables, §28.2). Gate B (explicit authorization) NOT present — **Gate B REMAINS NOT AUTHORIZED.** No production code, test, or migration was written (NO IMPLEMENTATION PERFORMED).

## 2. D1 EVIDENCE INHERITANCE

Every load-bearing D1 fact was re-verified against live code this session (READ_COMMITTED; connect_args; status enum has no offered/accept state; claim availability reads only; `DriverLocationResource.post` unauthenticated; admin assign = plain RMW; status path = plain RMW with no release; `cancel_booking` plain RMW PENDING/CONFIRMED only; no release setter anywhere; ranker↔pool payload mismatch; `find_driver_for_booking` unwired/dead; `Vehicle.current_booking_id` non-authoritative; coordination `with_for_update`/advisory lock precedents; Redis degrade path; transport `NotificationService` is a log-only stub while `app/notifications/services.py` is the durable path).

## 3. EXISTING GRAPH MAP (summarized)

Booking (create → PENDING_PAYMENT) → CONFIRMED (no binding) → candidate discovery disconnected (pool + dead ranker, no caller) → NO offer/accept/claim/safe-release anywhere. Admin `BookingStatusResource` and `BookingAssignmentResource` are plain RMWs. Ownership authority = `Booking.assigned_driver_id`/`assigned_vehicle_id`.

## 4. CANONICAL CLAIM BOUNDARY

New single-owner service `app/transport/services/assignment_service.py`:

```
AssignmentService.claim(booking_ref, driver_id, vehicle_id, *, actor, force=False)
```

External inputs resolve to internal IDs only after authorized boundary resolution (driver accept: authenticated `current_user` → `get_driver_profile(current_user.id)`; admin assign: existing admin contract). Typed preconditions + failures: booking_unavailable / driver_unavailable / vehicle_unavailable / offer_expired / offer_not_found / unauthorized / invalid_state / service_error. Motivation is NOT a claim precondition (freshness is a ranker filter).

**`actor` parameter — authorization contract.** `actor` is the authenticated user object passed from the route layer into the claim primitive. The claim function derives `actor_is_admin` at the service boundary:

```python
actor_is_admin = has_global_role(actor, "admin", "super_admin", "owner")
```

using the existing `app.auth.helpers.has_global_role` function (helpers.py:143-192), which is the same check used by the `@admin_required` decorator (decorators.py:384-425). The two call paths:

- **Driver accept** (`@login_required` + `@role_required("driver")`): `actor = current_user` (the driver), `force=False` (force is not exposed to the driver accept route — the route handler never passes it). `actor_is_admin = False`.
- **Admin assign** (`@admin_required` on `BookingAssignmentResource.post`, booking_routes.py:327): `actor = current_user` (admin-authorized), `force` may be `True`. `actor_is_admin = True`.

**Defensive rule inside the claim primitive:** if `force=True` is passed and `actor_is_admin` is `False`, the claim MUST reject immediately with `unauthorized` — before any SQL execution. `force=True` is available only to an already-authorized administrative actor and never changes ownership/conflict/state protections (§14).

## 4.1 DOCUMENTED CONFIG DEFAULTS (NOT EMPIRICALLY OPTIMIZED)

Product/config evidence was checked this pass: neither `TRANSPORT_STALL_TIMEOUT_SECONDS` nor `TRANSPORT_OFFER_TTL_SECONDS` exists in `app/config.py` or in seeded transport settings; `TrackingService.LOCATION_TTL_SECONDS = 300` is the only adjacent constant. No evidence contradicts the following documented P0 defaults, so they are pinned (had evidence contradicted them, this pass would have STOPPED per protocol rather than silently renumbering):

- `TRANSPORT_STALL_TIMEOUT_SECONDS = 600` — documented P0 default (10 minutes: generous driver-approach window, short enough to revoke a stuck assignment within the same operating session). Configurable override at ship/runtime via the deterministic `get_setting(key, default)` pattern (`app/transport/models.py:1871-1908` + `TransportSetting`, models.py:1739). Expected to be product-tuned after MVP.
- `TRANSPORT_OFFER_TTL_SECONDS = 300` — documented P0 default, chosen to match the established `LOCATION_TTL_SECONDS = 300` freshness boundary (a consistent re-dispatch horizon). Configurable override; product-tunable after MVP.

These are sane defaults, NOT empirically optimized values. **Ship requirement:** explicit documented values must exist in configuration before the P0 sweep/offer code runs; the defaults above satisfy that without blocking implementation. An override changes only the constant, never the guard semantics (§5/§9). **Deeper-stage stall policy** (PICKUP_ARRIVED/IN_PROGRESS) remains a separate product decision — not invented here (§11).

## 5. ATOMICITY REQUIREMENT — CANONICAL CLAIM SQL (SINGLE SOURCE)

> **This section is the ONE authoritative, implementation-ready definition of the claim SQL.** Every other section (operating-race proofs §6, acquisition doctrine §8, force semantics §14, scope table §25) references THIS section; none reproduces the claim SQL. The claim primitive must be built exactly from the SQL below. The release SQL is a separate operation and lives in §9 (also single-source). If a conflict between sections ever appears, this section wins.

Writes in ONE transaction, exact ordering with rowcount gates. `r2` (driver) and `r3` (vehicle) carry the **reverse-ownership `NOT EXISTS` guard — the ONLY authoritative proof that a resource is free**. `is_available=true` is NOT by itself authoritative, because three live surfaces can toggle it directly without any ownership check (§8). The claim guard therefore re-derives freedom from `transport_bookings`, never from the availability flag alone.

```
BEGIN
r1 = UPDATE transport_bookings SET status='assigned',
       assigned_driver_id=:d, assigned_vehicle_id=:v, driver_assigned_at=now()
     WHERE id=:bk
       AND status='confirmed' AND assigned_driver_id IS NULL AND is_deleted=false
     -> assert r1.rowcount == 1 else ROLLBACK, booking_unavailable   # state+unassigned precondition (NOT force-relaxable, §14)
r2 = UPDATE driver_profiles SET is_available=false
     WHERE id=:d
       AND is_deleted=false AND compliance_status='approved'
       AND ( (is_online=true) OR (force AND actor_is_admin) )
       AND ( (is_available=true) OR (force AND actor_is_admin) )
       AND NOT EXISTS (
         SELECT 1 FROM transport_bookings b
         WHERE b.assigned_driver_id = :d
           AND b.status IN ('assigned','driver_en_route','pickup_arrived','in_progress','disputed')
           AND b.id <> :bk)
     -> assert r2.rowcount == 1 else ROLLBACK, driver_unavailable
r3 = UPDATE transport_vehicles SET is_available=false, current_booking_id=:bk
     WHERE id=:v
       AND is_deleted=false
       AND ( (is_available=true) OR (force AND actor_is_admin) )
       AND NOT EXISTS (
         SELECT 1 FROM transport_bookings b
         WHERE b.assigned_vehicle_id = :v
           AND b.status IN ('assigned','driver_en_route','pickup_arrived','in_progress','disputed')
           AND b.id <> :bk)
     -> assert r3.rowcount == 1 else ROLLBACK, vehicle_unavailable
audit append; COMMIT
```

Implementation requirements (no semantics left to the implementer):

- **Self-exclusion `b.id <> :bk` is REQUIRED — it prevents the claim from being its own false conflict.** `r1` already set booking `:bk` to `status='assigned' AND assigned_driver_id=:d` within this transaction; under READ_COMMITTED the later command snapshot includes the transaction's own write. Without the self-exclusion, `r2`'s subquery matches the very booking being claimed, `NOT EXISTS` becomes false, and every claim fails with `driver_unavailable`. `r3` mirrors this for the vehicle. (This is why the earlier abstract "add a reverse-lookup guard" statement was insufficient — it omitted the exclusion that makes the guard correct.)
- **Deleted booking rows are intentionally NOT excluded from the ownership subquery.** A soft-deleted row that still carries an active status and non-null `assigned_driver_id`/`assigned_vehicle_id` latches the resource and MUST block acquisition and release until remediated. The soft-delete disposition (§10.1) prevents NEW such rows; the guard defends against any that predate the fix.
- The subquery's status literals MUST come from the single canonical `ACTIVE_ASSIGNMENT_STATUSES` constant (§9), never hand-copied into multiple files.
- `force` semantics are defined exactly once in §14. `actor_is_admin` means the caller passed the authorized-admin boundary check (admin contract or core-admin role) — force is meaningless for a non-admin caller (`unauthorized`).
- Failed gate → ROLLBACK the ENTIRE transaction; no partial assignment survives. IntegrityError handled only if the partial-unique backstop is added (P1). OperationalError/lock-timeout → rollback + bounded retry (repo `@retry_on_deadlock` convention), typed service_error, never partial.

## 6. REQUIRED CLAIM RACES AND THE RELEASE↔CLAIM PROOF

### 6.1 Minimal race set

- A — 2 drivers → 1 booking: `r1` row-lock serializes on the booking row; loser rowcount 0 → `booking_unavailable`.
- B — 2 bookings → 1 driver: both `r1` succeed (different rows); `r2` row-lock serializes on the driver row; loser full-rollback, its booking returns to CONFIRMED/unassigned.
- C — 2 bookings → 1 vehicle: same shape via `r3`.
- D — offline during offer: pre/at accept blocked by the `is_online` pre-gate (and, for non-force, by `is_available=true`); offline AFTER a committed claim is NOT solved by the transaction — that is stall recovery (§11).

### 6.2 Interleaving proof — Release(A, D) ↔ Claim(B, D) using the corrected SQL

Notation: "row-lock" = PostgreSQL tuple lock acquired by an UPDATE on that row; EPQ = EvalPlanQual re-evaluation of the WHERE predicate against the latest committed version after waiting on a row-lock. **SQL fragments shown inline in this proof (e.g. `UPDATE driver_profiles SET is_available=false … AND NOT EXISTS(holder, id<>)`) are LABELED EXCERPTS quoted from §5 (claim) and §9 (release) purely to explain the concurrency mechanics. They are abbreviated (`…` elides the exact predicates) and are NOT a second, competing claim definition. §5 is the ONE authoritative, implementation-ready claim SQL; §9 is the ONE authoritative release SQL. Where an inline fragment differs from §5/§9 in spelling, §5/§9 win.** Steps: release = r1 clears A's pointers → r2/`r3` free D; claim = c_r1 flips B → c_r2/c_r3 acquire D.

**Scenario A — A.release commits FIRST, B.claim runs after.**

1. Booking rows acquired: A.release r1 (UPDATE bookings id=A) row-locks booking A; sets `assigned_driver_id=NULL`. B.claim c_r1 (UPDATE bookings id=B WHERE status='confirmed' AND unassigned) row-locks booking B; rowcount=1.
2. Driver row acquired: A.release r2 UPDATEs driver row D (is_available=false→true). Predicate snapshot: A's r1 already cleared A's pointer in-transaction, so within A's snapshot no row holds D → predicate true → A row-locks driver row D.
3. Conditional predicate (release r2): `WHERE id=D AND is_available=false AND NOT EXISTS(holder of D, id<>A)` → true (A un-assigned itself). rowcount=1 pending.
4. Blocking point: none for A at this stage; B's c_r2 (below) BLOCKS here on driver row D's lock (bounded by `lock_timeout`).
5. Committed state: A COMMITs → booking A terminal (`cancelled`), unassigned; driver D `is_available=true`.
6. Second writer: B.claim c_r2 (UPDATE driver_profiles SET is_available=false WHERE id=D AND … AND NOT EXISTS(holder, id<>B)) — fresh committed snapshot shows no holder → predicate true → EPQ confirms → rowcount=1.
7. Commit: B COMMITs → booking B `assigned` to D; D `is_available=false`.
8. Final resource state: D owned by B exactly once. No double-claim, no loss, no orphan.

**Scenario B — B.claim runs during A.release — reversed order.**

Setup: A owns D (assigned, active). A begins release; near-simultaneously B begins claim.

1. Booking rows acquired: A.release r1 row-locks booking A; clears its pointer (uncommitted). B.claim c_r1 row-locks booking B; rowcount=1 pending.
2. Driver row: B.claim c_r2 UPDATEs driver row D — predicate snapshot at command start: A STILL holds D in the committed state (A assigned, active) → `NOT EXISTS(holder of D, id<>B)` returns A's row → predicate FALSE → c_r2 acquires NO row lock and matches 0 rows.
3. Conditional predicate: c_r2 rowcount = 0 → claim ROLLs BACK entirely → booking B returns to CONFIRMED/unassigned (c_r1 ripple). Typed failure `driver_unavailable`.
4. Blocking point: none — PostgreSQL does NOT wait on rows that fail the predicate under the current snapshot; the reverse guard rejects without touching the lock. This is the fail-fast double-claim defense.
5. Committed state: A.release proceeds uninterrupted — r2 predicate true (A cleared its own pointer in-transaction) → rowcount=1; r1=1.
6. Rowcounts: A.release r1=1, r2=1.
7. A COMMITs → booking A terminal, D freed (`is_available=true`).
8. Final resource state: D free; B still CONFIRMED/unassigned — a later B retry/re-request acquires D cleanly. Single-owner invariant holds in both orders.

**Consequence:** whichever side commits the driver-row ownership change first wins the row; the loser's guard fails closed (rowcount 0) and its entire transaction rolls back. There is no interleaving in which two active bookings hold D.

## 7. RACE E — CANCEL VS CLAIM

Legal transitions allow cancel from DRAFT/PENDING_PAYMENT/CONFIRMED/ASSIGNED/DRIVER_EN_ROUTE, but `cancel_booking` service accepts only PENDING_PAYMENT/CONFIRMED and the only live binding is admin (`routes.py:1184-1214`). D2 canonical conditional cancel:

```
UPDATE transport_bookings SET status='cancelled', cancelled_at=now(), …
WHERE id=:bk AND status IN ('pending_payment','confirmed') AND is_deleted=false
```

- cancel-first → claim r1 rowcount 0 (booking_unavailable). Correct.
- claim-first → conditional cancel rowcount 0 → rejected per Policy A (§13).

## 8. DRIVER/VEHICLE AVAILABILITY ACQUISITION

Conditional acquisition is DB-enforced, not Python-only. Driver `r2` guards `is_available`, `is_online`, `compliance_status='approved'`, `is_deleted=false`, AND the reverse-ownership `NOT EXISTS` over `transport_bookings` (§5). Vehicle `r3` guards `is_available`, `is_deleted=false`, AND its own reverse-ownership `NOT EXISTS`. Admin assign re-uses the same canonical primitive (no parallel RMW path).

**`is_available=true` is NOT by itself authoritative proof that a resource is free.** Three current surfaces can toggle it directly with NO ownership check:

- admin driver availability PUT — `driver_routes.py:159-187` (`is_online`/`is_available` are updatable fields, plain RMW setattr+commit);
- provider driver self-toggle — `provider_service.py:1187-1199` (requires `is_online` when going available, but performs no active-booking check);
- admin vehicle availability PUT — `vehicle_routes.py:183-207` (`is_available`/`status`/`maintenance_status` updatable, no booking check).

A direct `SET is_available=true` while an active booking owns the resource is therefore NOT a legitimate hand-off. D2 does NOT re-engineer those surfaces (out of the authorized change map — only the surfaces in §23 change in P0). The corrected claim `r2`/`r3` reverse-ownership guard is the authoritative backstop and the ONLY proof of claimability. Doctrine: **availability flags advertise; the booking table owns.** The same doctrine also covers the legacy unguarded assign reader at `route_routes.py:293-323`, which is left unconverged in P0 and equally backstopped.

## 9. DRIVER/VEHICLE AVAILABILITY RELEASE

Single canonical definition (shared by claim/release, one source):

```python
ACTIVE_ASSIGNMENT_STATUSES = frozenset({"assigned", "driver_en_route",
                                        "pickup_arrived", "in_progress", "disputed"})
TERMINAL_STATUSES         = frozenset({"completed", "cancelled", "no_show"})
CLAIMABLE_STATUSES        = frozenset({"confirmed"})   # + unassigned
```

**Canonical single source (re-verified against the live enum this pass).** Every member exists in `BookingStatus` (models.py:78-90): ACTIVE = {assigned, driver_en_route, pickup_arrived, in_progress, disputed}; TERMINAL = {completed, cancelled, no_show}; CLAIMABLE = {confirmed} + unassigned (`assigned_driver_id IS NULL`). These three sets are distinct responsibilities:

- `ACTIVE_ASSIGNMENT_STATUSES` — booking currently OWNS resources; widest set used by the claim/release reverse-ownership guards (§5, §9).
- `TERMINAL_STATUSES` — booking releases its resources via the terminal transition (not an ownable-in-flight state).
- `CLAIMABLE_STATUSES` — booking MAY acquire resources (must also be unassigned).

Implementation MUST define the three frozensets in exactly ONE location (the `assignment_service` module, exported as constants) and MUST import them everywhere they are used (claim, release, stall sweep, status-transition guard, soft-delete reject). Hand-copying status literals into multiple files is prohibited (§5 subquery uses the same constant). Do NOT merge any of these with the events-coordination `coordination_contract.ASSIGNABLE_BOOKING_STATUSES = {"confirmed","assigned"}` (a different domain concept).

`AssignmentService.release(booking_id, terminal_status)` — SAME transaction as the terminal transition:

```
BEGIN
SELECT assigned_driver_id, assigned_vehicle_id INTO :d, :v FROM transport_bookings
WHERE id=:bk AND is_deleted=false            # none or d is NULL -> COMMIT, release_noop
r1 = UPDATE transport_bookings SET status=:terminal, (completed_at|cancelled_at|…)=now(),
       assigned_driver_id=NULL, assigned_vehicle_id=NULL, audit_log=audit_log||:entry
     WHERE id=:bk AND assigned_driver_id IS NOT NULL
     # r1.rowcount==0 -> COMMIT, release_noop
r2 = UPDATE driver_profiles SET is_available=true
     WHERE id=:d AND is_available=false AND NOT EXISTS (
       SELECT 1 FROM transport_bookings b
       WHERE b.assigned_driver_id=:d AND b.status IN (ACTIVE…) AND b.id <> :bk)
     # r2.rowcount==0 -> skip (driver already re-claimed by B; B undisturbed)
r3 = UPDATE transport_vehicles SET is_available=true,
       current_booking_id = CASE WHEN current_booking_id=:bk THEN NULL ELSE current_booking_id END
     WHERE id=:v AND is_available=false AND NOT EXISTS (
       SELECT 1 FROM transport_bookings b
       WHERE b.assigned_vehicle_id=:v AND b.status IN (ACTIVE…) AND b.id <> :bk)
     # r3.rowcount==0 -> skip
COMMIT
```

Ownership authority = reverse lookup through `Booking.assigned_driver_id`/`assigned_vehicle_id` (REQUIRED). `Vehicle.current_booking_id` (non-FK, non-unique, may be stale) is cleared only WHERE it equals the releasing booking; never trusted as authority. Late-release protection: Booking A completes late after D re-claimed by Booking B → NOT EXISTS excludes B → D's availability untouched. The driver-row lock serializes A.release vs B.claim, making the guard race-free at row level.

## 10. TERMINAL RELEASE MATRIX

| Trigger | State | Driver rel | Vehicle rel | Guard | Notify |
|---|---|---|---|---|---|
| COMPLETED (new driver-complete endpoint) | completed | yes | yes | reverse lookup | passenger + driver (durable) |
| COMPLETED (admin StatusResource) | completed | yes | yes | reverse lookup | passenger |
| CANCELLED (admin) | cancelled | yes | yes | reverse lookup | passenger |
| CANCELLED (passenger, PRE-assignment, new binding) | cancelled | n/a | n/a | status IN (pending_payment, confirmed) | passenger |
| NO_SHOW (admin) | no_show | yes | yes | reverse lookup | — |
| Failed/aborted assignment | rolled back | none acquired | none acquired | transaction rollback | — |
| Terminal admin closure (DISPUTED→…) | completed/cancelled | yes | yes | reverse lookup | passenger |

### 10.1 BOOKING SOFT-DELETE DISPOSITION (SELECTED: REJECT WHEN ACTIVE)

Endpoint: `BookingDetailResource.delete` (`booking_routes.py:240-254`), `@admin_required`, sets only `is_deleted=true` + `deleted_at`, docstring "Soft delete booking". It performs NO status transition, NO cancellation, NO release. Business meaning = **administrative record hiding**, NOT ride termination (termination semantics live exclusively in `BookingStatusResource` and `cancel_booking`).

**Decision: REJECT soft-delete while `status ∈ ACTIVE_ASSIGNMENT_STATUSES`.** A live assigned booking may not be hidden: hiding it latches the driver/vehicle (the row still carries `assigned_driver_id`/`assigned_vehicle_id` with an active status) while making the ride invisible, and there is no release anywhere in the path to free the resources.

Behavior (one disposition, no divergence):

- `status ∈ ACTIVE_ASSIGNMENT_STATUSES` → reject with 409, message "cannot delete an assigned booking"; `is_deleted`/`deleted_at` untouched, no status change.
- Non-active statuses (DRAFT/PENDING_PAYMENT/CONFIRMED or TERMINAL) → current soft-delete behavior preserved. Record hiding is legitimate there and CONFIRMED bookings deliberately hold no assignment to latch.

`release()` is NOT invoked from delete — the terminal transition + `release()` (§10 matrix) is the single ride-termination route.

Race note: delete vs claim — claim `r1` requires `is_deleted=false`, so a deleted booking can never be claimed; the reject makes simultaneous deletion of an active booking impossible; any pre-existing latched deleted-active row (should one exist from before this fix) is defended by the §5 guard, which intentionally does not exclude deleted rows from the ownership subquery.

Today every terminal path sets status/timestamps/audit only — D2 wires `release()` into each.

## 11. STALL RECOVERY — P0 DEFINITION (CONCRETE)

`ASSIGNED` → no en-route progress → terminal cancellation → canonical release → durable passenger notification → passenger re-request. No automatic replacement driver in P0.

Trigger predicate (durable DB columns are the source of truth; evaluated sweep-side by the beat task, not per-row):

```
status = 'assigned'
AND driver_en_route_at IS NULL
AND created_at + TRANSPORT_STALL_TIMEOUT_SECONDS < now()      -- age > timeout
```

- **Source of time:** database `now()` against `transport_bookings.created_at` (created_at is NOT NULL via `TimestampMixin`, models.py:178-189). Deterministic, restarts-safe.
- **Sweep trigger:** NEW beat task `transport-stall-recovery` (no transport beat task exists today — implementation requirement; precedent pattern `release-expired-ticket-holds` 60s sweep, `app/celery_app.py:91-168`).
- **Default timeout:** `TRANSPORT_STALL_TIMEOUT_SECONDS = 600` (§4.1). Read via the deterministic `get_setting(key, default)` plumbing so the live value is always explicit; a product override changes only the constant.
- **Target existing status:** `cancelled` (legal transition ASSIGNED→CANCELLED; per `STATUS_TRANSITIONS`, booking_routes.py:30-42).
- **Resource release:** same-transaction `release(booking_id, 'cancelled')` (§9) — guarded reverse-lookup release; a resource already re-claimed by Booking B before the sweep commits is left to B (NOT EXISTS self-exclusion), so the sweep never disturbs a live hand-off.
- **Notification:** durable passenger notification through `app/notifications/services.py` (the durable path), NOT the log-only transport stub — the passenger learns the ride was cancelled and re-requests.
- **No automatic replacement:** re-dispatch orchestration = P1 (§25).
- **Scope honesty — NOT extended:** `PICKUP_ARRIVED`/`IN_PROGRESS` → CANCELLED are NOT legal transitions (booking_routes.py:36-37). Deeper-stage stall (driver already at pickup or already en route) is OUT of P0 and requires a separate product decision — do not invent semantics. The metadata timestamps `driver_en_route_at`/`driver_arrived_at`/`pickup_actual_time` have zero writers today; D2 wires `driver_en_route_at` on the en-route transition, and the sweep's safety does not depend on the other two.

## 12. DRIVER POST-ACCEPTANCE CANCEL POLICY

No driver-initiated cancel in P0 (no binding exists; none added). Booking terminates only via admin/stall. Going offline does NOT free the driver. Vehicle frees only on terminal release. Durable notification on terminal. **Automatic re-dispatch = P1.** Decline-before-accept remains (RNA → next ranked).

## 13. PASSENGER POST-ASSIGNMENT CANCEL POLICY

**Policy A — passenger cannot cancel after assignment in P0.** UI hides/rejects cancel on ASSIGNED+ ("driver assigned — contact support"), consistent with the existing service guard. Policy B (fee-based post-assignment cancel) EXPRESSLY not adopted. This makes Race E a clean conditional UPDATE over pre-claim states only (§7).

## 14. ADMIN ASSIGNMENT — ONE PRIMITIVE (WRAPPED)

`BookingAssignmentResource.post` becomes a thin wrapper over `claim()` (actor=admin). The admin-authorized boundary is traced end-to-end inside the claim primitive: route layer uses the existing `@admin_required` contract (`BookingAssignmentResource.post`, booking_routes.py:324-374), which references the canonical `has_global_role(actor, "admin", "super_admin", "owner")` function (decorators.py:384-425); that authorization fact is passed into `claim()` as `actor_is_admin` (§4 authorization contract). The claim primitive itself derives `actor_is_admin` from the `actor` parameter via `has_global_role` — it does NOT rely on the route having already authenticated (defense in depth). **Defensive reject:** if `force=True` is received with `actor_is_admin=False`, the claim returns `unauthorized` before any SQL execution; the driver-accept path always passes `actor_is_admin=False` and never exposes `force` (§4).

**Single `force=True` semantic — exactly one definition, reconciling the former §5/§14 wording.** `force=True` MAY relax ONLY the non-conflict readiness/administrative pre-gates shown in the claim SQL (§5):

- driver `is_online=false`
- driver `is_available=false` (administrative availability flag)
- vehicle `is_available=false` (administrative availability flag)

`force=True` MUST NEVER permit or bypass:

- double assignment / acquisition of a resource already held by another active booking;
- the driver reverse-ownership `NOT EXISTS` (§5 `r2`);
- the vehicle reverse-ownership `NOT EXISTS` (§5 `r3`);
- the `r1` booking claim precondition (`status='confirmed' AND assigned_driver_id IS NULL AND is_deleted=false`) — no double-employment of a booking;
- driver `compliance_status='approved'` or `is_deleted=false`; vehicle `is_deleted=false`;
- the `rowcount == 1` gates (a force operation that loses a conflict fails, never clobbers);
- authorization / ownership resolution (non-admin caller ⇒ `unauthorized`; `force` is inert — `actor_is_admin=False` with `force=True` is rejected before SQL, §4);
- transaction integrity (still one atomic transaction; audit still appended) and canonical authority.

Equivalently: **force may relax readiness/administrative conditions; it may NEVER relax ownership/occupancy/state conditions.** A forced admin assignment still fails with `driver_unavailable`/`vehicle_unavailable` if the resource is genuinely owned by another active booking — the flag cannot claim an occupied resource. This resolves the former contradiction where `<force>` sat on the availability gate while §14 claimed force never bypassed conflict protections: the availability flag is an administrative gate (force-relaxable); the reverse-ownership guard is the conflict protection (never force-relaxable).

**Final rule: `force=True` is available only to an already-authorized administrative actor and never changes ownership/conflict/state protections.**

## 15. DRIVER OFFER REDIS MODEL (TRANSIENT — POSTGRES IS THE ONLY AUTHORITY)

No DB `DriverOffer` table (Decision A). Redis is a transient, driver-indexed **conveyance** of offers. **Redis is never the authoritative assignment store** — the `transport_bookings` row (`status`, `assigned_driver_id`, `assigned_vehicle_id`) is the sole authority for who owns what.

Keys:
```
transport:offer:{booking_ref}                HASH  (booking_ref, driver_id, vehicle_id,
                                                     offer_status=offered|accepted|declined|expired,
                                                     created_at, expires_at, sequence)
transport:driver:{driver_id}:offers          SET   (booking_refs with live offers to this driver)
transport:offer:index:booking:{booking_ref}  SET   (reverse index for expiry sweep)
```

Driver lookup is O(1): `SMEMBERS transport:driver:{id}:offers` → pipelined `HGETALL`.

Exact lifecycle (each step pinned):

- **Create** (on candidate selection, pool→ranker): write HASH + driver-index SET member + reverse-index SET member in one Lua block; set `expires_at = now() + TRANSPORT_OFFER_TTL_SECONDS`. TTL is a *max-lease*, not a heartbeat. Sequence number stored for dedup.
- **Accept** (driver): single Redis compare-and-swap (Lua: only transitions if `offer_status='offered'`) → set `offer_status='accepted'` + SREM both indices → then call `AssignmentService.claim()` (the real ownership transfer). Redis is a pace gate; claim is the authority. If claim fails (`driver_unavailable`/`vehicle_unavailable`/`vehicle_unavailable`), the offer record is cleaned (HASH removed + SREM) and the booking stays CONFIRMED/unassigned for rediscovery — no accepted-but-unassigned state survives.
- **Decline** (driver): atomic `SREM` from driver index + set `offer_status='declined'`; no claim. Booking continues rediscovery.
- **Expiry** (beat sweep): `expire_keys` sweep prunes HASH + both SET members where `expires_at < now()`. Expired offers return `offer_expired` on accept. Sweep cadence: ≤5 minutes (matches offer TTL budget).
- **Cleanup**: on any terminal booking state (cancelled/completed/no_show) AND on claim success, proactively prune offer keys for that booking_ref across all three keyspaces — never leave a live offer for a booked ride.
- **Duplicate accept**: redis CAS accepts exactly one winner; a second accept for the same booking sees `offer_status != 'offered'` → `offer_not_found`/`offer_expired`. A duplicated *claim* race is decided by booking row `r1` rowcount gate (§6).
- **Restart / Redis outage**: all offer keys are lost; the DB recovery sweep rebuilds offers only for `status='confirmed' AND assigned_driver_id IS NULL` bookings. Offer loss is harmless. Under sustained outage the dispatch layer degrades (app already degrades to `SimpleCache`/filesystem) — bookings stay CONFIRMED, nothing is assigned, no ride is double-booked. Full offer-hub availability under outage = P1.
- **Reconstruction from PostgreSQL**: always possible — `confirmed + unassigned` bookings with ranked candidates = the offer set. No reconciliation needed beyond the normal recovery sweep.

TTL default: `TRANSPORT_OFFER_TTL_SECONDS = 300` (§4.1), chosen to match `TrackingService.LOCATION_TTL_SECONDS = 300` freshness boundary — a consistent re-dispatch horizon; configurable override; product-tunable after MVP.

## 16. DRIVER ACCEPT — SECURITY / IDEMPOTENCY / RATE LIMIT

Auth chain mirrors driver dashboard: `@login_required` + driver capability/role + `@active_context_required(ContextType.DRIVER)` + `@role_required("driver")`. Ownership: profile resolved via `current_user.id`; offered driver_id must equal it, else `unauthorized`. Rate limit: Flask-Limiter (Redis-backed; `memory://` fallback). Idempotency: natural — retried accept for a booking already claimed by THIS driver returns idempotent success (check `assigned_driver_id==driver.id AND status='assigned'`); claimed by another → `booking_unavailable`; expired → `offer_expired`. First accept wins.

## 17. DRIVER LOCATION SECURITY (P0 D2-ENTRY DEPENDENCY)

`DriverLocationResource.post` is currently UNAUTHENTICATED (driver_routes.py:276). Intended gate: `@login_required` → driver role capability → DriverProfile ownership (`profile.user_id == current_user.id`, else 403) → canonical `update_location`. Route path for the POST resolves identity from the authenticated user, never a foreign driver_id for non-admin.

## 18. MATCHING HARMONISATION (MINIMAL)

Ranker reads `vehicle_classes`, `average_rating`, `acceptance_rate`, `service_types` (matching_service.py:179-196); pool payload (provider_service.py:1349-1366) supplies none → those score terms silently contribute zero. P0: extend the pool dict with the four fields already on `DriverProfile`. Do not touch ranker algorithm, pool "no ORDER BY / not cached" discipline.

## 19. FARE ESTIMATION — DECISION: P0

MVP is a price-committed dispatch loop; estimate already computed + persisted at creation (`base_price=estimated_price`, NOT NULL fare fields). P0 work = surface only (render on confirmation + booking detail). Zero schema/computation.

## 20. RESTART RECOVERY

- Trigger: beat tasks `transport-dispatch-recovery` + `transport-stall-recovery` (NO transport beat task exists — implementation requirement, pattern precedent `release-expired-ticket-holds` 60s sweep).
- Durable source of truth: `Booking` table. Redis not required for correctness.
- CONFIRMED+unassigned → rediscover (pool → ranker → offer). ASSIGNED+stalled → stall recovery.
- Duplicate prevention: sweep acts only on `status='confirmed' AND assigned_driver_id IS NULL`, and the claim itself is the unity guard.
- In-flight claim at process restart: Postgres rolls back on connection loss; booking stays CONFIRMED/unassigned → reconsidered. No action beyond default DB behavior.

## 21. DATABASE / LOCKING MODEL

PostgreSQL, READ_COMMITTED (config.py:128), connect_args timeouts (config.py:134-136). Guarded UPDATE + rowcount is safe via EvalPlanQual: a second writer waits on the row lock (bounded by lock_timeout) then re-evaluates WHERE against the latest committed row → 0 rows. Same mechanism already used repo-wide (wallet `on_conflict_do_nothing`, events tier capacity, `@retry_on_deadlock`). Explicit `SELECT FOR UPDATE` is NOT needed in claim/release (UPDATE self-locks target rows). `with_for_update`/advisory locks remain in their existing coordination paths and are NOT duplicated.

## 22. CONCURRENCY ENTRY TEST PLAN (defined, NOT written)

Repo harness pattern (threading.Thread ×N + Barrier + per-thread app context/session + `_isolate_db` cleanup). Written and run only AFTER Gate B. Expectations reflect the corrected claim SQL (§5), corrected release guard (§9), `force` conflict semantics (§14), soft-delete disposition (§10.1), and typed rowcount conflicts:

- T1 — two drivers → one booking: exactly one claim succeeds (`r1` rowcount 1); the loser returns `booking_unavailable` (booking returned to CONFIRMED/unassigned); booking `status='assigned'` exactly once with exactly one `assigned_driver_id` and `driver_assigned_at` set; winner's driver `is_available=false`.
- T2 — two bookings → one driver: one succeeds; loser returns `driver_unavailable` with its own booking fully rolled back at `CONFIRMED`/`assigned_driver_id IS NULL`; driver `is_available=false` exactly once.
- T3 — two bookings → one vehicle (mirror of T2 via `r3`; loser `vehicle_unavailable`; `Vehicle.current_booking_id` set exactly once to the winner).
- T4 — cancel ↔ claim, both orderings: cancel-first → claim `r1` rowcount 0 (`booking_unavailable`); claim-first → conditional cancel (`WHERE status IN ('pending_payment','confirmed')`) rowcount 0, rejected per Policy A; assert `cancelled_at` set exactly once in the cancel-first ordering.
- T5 — terminal release ↔ subsequent claim: (a) release-first → claim succeeds cleanly (D freed then acquired); (b) claim-first → release `r2`/`r3` `NOT EXISTS` excludes the new owner (`b.id <> :bk`) so the late release leaves the new owner's resources untouched (`is_available=false` preserved); (c) idempotent double-release on the same booking → `release_noop`, second call changes nothing. Assert no interleaving produces two bookings owning one driver/vehicle.
- Soft-delete guard assertion (§10.1): `BookingDetailResource.delete` on an assigned booking → 409, `is_deleted` unchanged, driver/vehicle still owned; delete on a non-active-status booking succeeds as today.
- Force conflict assertion (§14): `force=True` from an authorized admin succeeds when the ONLY obstacle is `is_online`/`is_available` flags; `force=True` STILL fails with `driver_unavailable`/`vehicle_unavailable` when the resource is actively owned by another booking (the reverse-ownership `NOT EXISTS` holds under force).
- Typed conflict assertion: claim rejection always carries a specific failure type (`booking_unavailable`/`driver_unavailable`/`vehicle_unavailable`/`offer_expired`) — never a generic "error".

## 23. EXACT FILE/SERVICE CHANGE MAP

| Component | Change | Why |
|---|---|---|
| `app/transport/services/assignment_service.py` | NEW canonical claim + release + status sets | single ownership authority |
| `app/transport/services/offer_service.py` | NEW Redis offer model | transient driver-indexed authority |
| `app/transport/services/matching_service.py` | supply 4 payload fields; wire discovery; remove dead assign → delegate to claim | harmonisation + kill legacy double-assignment |
| `app/transport/services/provider_service.py` | extend pool dict with 4 fields | only site feeding ranker reads |
| `app/transport/services/booking_service.py` | conditional cancel + rowcount; surface fare; stall timestamps | Race E; fare P0 |
| `app/transport/api/booking_routes.py` | terminal transitions call release; admin assign wraps claim | terminal matrix; one primitive |
| `app/transport/api/driver_routes.py` | offer/accept/en-route/arrival/start/complete; GATE DriverLocationResource.post | MVP loop; P0 security |
| `app/transport/routes.py` | passenger cancel binding (Policy A); dashboard offer surface | Race E / §13 |
| `app/transport/services/notification_service.py` | route through `app/notifications/services.py` (durable) + emit `transport_driver_assigned` signal | durable notification reuse |
| `app/celery_app.py` (beat) | NEW transport-dispatch-recovery + transport-stall-recovery | §11/§20 |
| `tests/test_transport_concurrent_claim.py` | NEW 5 entry tests (after Gate B) | prove atomicity |
| `docs/transport/geographic-graph-map.md` | D2 status note | closure record |

## 24. MIGRATION GATE — DECISION A INTACT (0 / 0 / 0 / 0 / 0)

**This correction pass re-confirmed: 0 P0 tables · 0 P0 columns · 0 P0 enum changes · 0 P0 constraints · 0 P0 migrations.** The corrected claim reverse-ownership guard (§5) and force semantics (§14) are pure WHERE predicates and a runtime parameter on existing columns; the documented defaults (§4.1) are config constants; no schema object changes. `BookingStatus` untouched → no enum CHECK sync (§20.2). Release guard (§9) unchanged and also 0-schema. No new index added (claim/release are PK-driven entry points; stall sweep reads `ix_booking_status`; the reverse-lookup scan is acceptable at current P0 volume — see §24.1).

### 24.1 REVERSE-LOOKUP PERFORMANCE RISK REGISTER

**This guard is now load-bearing (appears on every claim and release path):** the claim `r2`/`r3` `NOT EXISTS` subquery, and the release `r2`/`r3` `NOT EXISTS` subquery, scan `transport_bookings` filtering by `assigned_driver_id`/`assigned_vehicle_id` + status.

- **Current indexing evidence:** `transport_bookings` has NO index on `assigned_driver_id` or `assigned_vehicle_id` (`models.py __table_args__` 870-881: `ix_booking_user` / `ix_booking_provider` / `ix_booking_status` / `ix_booking_dates` / `ix_booking_reference` / `ix_booking_event` / `ix_booking_pickup` / `ix_booking_dropoff`; the columns themselves, lines 1020-1021, are plain non-indexed `BigInteger` FKs). The `ix_booking_status` index (status, created_at) partially covers the subquery's `status IN (…)` filter; the main scan is the FK column itself.
- **Expected P0 suitability:** acceptable at MVP scale. Claim/release are low-frequency, single-resource entry points; the subquery's cardinality is the set of active bookings referencing one `driver_id` or `vehicle_id` — bounded and small under MVP load; correctness of the guard is index-independent (the NOT EXISTS predicate is evaluated correctly under scan + EPQ, regardless of index).
- **Lock-duration / critical-section risk (NEW this integrity pass):** the reverse-lookup subquery executes INSIDE the claim/release transaction while the booking row (`r1`) and driver/vehicle rows (`r2`/`r3`) are already row-locked. A scan on the unindexed FK column inside that in-flight transaction lengthens the write critical section: the longer the subquery takes, the longer the booking/driver/vehicle rows stay locked, which raises contention probability for concurrent writers (other claims/releases/cancels touching the same rows block up to `lock_timeout`). This is a **correctness-neutral, scalability-only** risk at P0 — claim frequency is low relative to read traffic, and every failed locked writer rolls back cleanly (no correctness impact, only latency). The risk compounds only as write concurrency on the same resources grows, which is exactly the volume regime the §24.1 escalation metric and the named P1 partial index address.
- **P0 correctness vs P1 scalability — explicit distinction:** the guard's correctness is 100% index-independent (P0, already true); the lock-duration and scan cost are scalability concerns (P1, hardening). They are different kinds of risk and must not be conflated: P0 does not need the index; P1 ships it once the escalation metric triggers.
- **Risk escalation metric:** sustained per-call guard latency growth as bookings volume grows, or claim/release throughput that makes the scans material. **Alert when:** EXPLAIN ANALYZE on the guard subquery stops showing single-digit ms at normal load, or when the scan node in the subquery plan grows to full-table scans at sustained throughput.
- **P1 hardening (named, NOT created now, NOT migrated now):** **Partial index on active `assigned_driver_id` / `assigned_vehicle_id` lookup paths** — e.g.:
  ```
  CREATE INDEX ix_booking_active_driver ON transport_bookings (assigned_driver_id)
    WHERE status IN ('assigned','driver_en_route','pickup_arrived','in_progress','disputed');
  CREATE INDEX ix_booking_active_vehicle ON transport_bookings (assigned_vehicle_id)
    WHERE status IN ('assigned','driver_en_route','pickup_arrived','in_progress','disputed');
  ```
  This is a P1 performance hardening, explicitly NOT required for current P0 correctness; it will surface as a proposed migration under the §20 process once the risk metric above is triggered.
- **Absence of the index is a documented P1 cost, not a correctness gap:** correctness of the `NOT EXISTS` guard is completely index-independent.

## 25. P0 / P1 / P2 SCOPE TABLE (contradiction-free)

| Tier | Items | Notes |
|---|---|---|
| **P0** | atomic claim (single-owner primitive, reverse-ownership guard §5) | `force` semantics (§14) |
| | terminal release (all §10 triggers wired, guarded reverse-lookup) | every terminal path in §10 gets `release()` |
| | minimum stall recovery (ASSIGNED + no en-route, §11) | `TRANSPORT_STALL_TIMEOUT_SECONDS=600` default |
| | conditional passenger cancellation (Policy A, §13/§7) | Race E conditional UPDATE |
| | driver-location security gate (§17) | P0 entry dependency, fixed before ship |
| | driver acceptance (offer accept + claim, idempotency + rate limit §16) |  |
| | offer lifecycle (Redis transient model, accept/decline/expiry/cleanup/restart/outage §15) | Redis never authoritative |
| | driver lifecycle (online/available/compliance enforced at claim) |  |
| | restart safety (DB-truth recovery sweeps §20) |  |
| | resource conflict protection (reverse-guard backstop + force semantics) | availability-flip defense |
| | admin-assign convergence (one primitive §14) | legacy plain-RMW → claim wrapper |
| | fare estimation P0 surface-only (existing journey justification) | zero schema/computation |
| | matching harmonisation (pool supplies 4 ranker fields) |  |
| | booking soft-delete disposition: reject while active (§10.1) | NEW this correction pass |
| **P1** | full reassignment orchestration (auto-select replacement driver after stall/cancel) |  |
| | driver post-acceptance cancellation policy |  |
| | optional partial indexes/performance hardening (§24.1) | named P1 item |
| | payment execution |  |
| | offer-hub availability under Redis outage |  |
| | concurrency backend store |  |
| **P2** | realtime push |  |
| | advanced pooling / group rides |  |
| | other explicitly deferred features |  |

Nothing above adds a P0 migration (§24). The §24.1 partial index is the first P1 schema item admitted.

## 26. GATE CONDITIONS FOR IMPLEMENTATION

All defined and established: claim owner, release owner, acquisition guard, release guard, active/terminal statuses, terminal triggers, Race E policy (A), Race D P0 recovery, admin path convergence, Redis driver index, driver-location boundary, fare P0, restart recovery, concurrency test plan, file map, 0-migration boundary. **Gate B = explicit MOE authorization, absent.**

## 27. DURABLE RECORDS

`.opencode/thread_state.md` TH-3-D2 bullet · this file · `BACKLOG.md` TH-3-D2 entry · `docs/transport/geographic-graph-map.md` §10 D2 note. All four updated by the correction pass and the final artifact-integrity pass.

### 27.1 GIT SCOPE ATTRIBUTION (honest, verified this pass)

`git status --short` on the four record files yields: ` M BACKLOG.md`, `?? .opencode/thread_state.md`, `?? docs/transport/d2-atomic-dispatch-claim.md`, `?? docs/transport/geographic-graph-map.md`; `git diff --stat` on the same set reports only `BACKLOG.md | 637 ++++…--- (614 insertions, 23 deletions)`; `git log` and `git ls-files` on `docs/transport/geographic-graph-map.md` return nothing (never committed to the current branch).

**Those states prove only that `BACKLOG.md` has uncommitted modifications vs HEAD and that the other three files are untracked.** They do NOT independently partition each file's content into "pre-existing" vs "this worker's changes". Therefore, per the final-integrity-pass doctrine: **Git scope attribution is inconclusive from the available working-tree state.** The factual, non-over-claiming statement is: during TH-3-D2, this worker created `docs/transport/d2-atomic-dispatch-claim.md`, `.opencode/thread_state.md`, and `docs/transport/geographic-graph-map.md` (first two entirely in-session; the third received the D2 §10 note), and appended D2 entries to the pre-existing, already-modified `BACKLOG.md`. Those four are the ONLY files this worker edited in TH-3-D2. No D2 production code, test, or migration was created (Gate B absent).

## 28. CORRECTION HISTORY (GATE-B CLOSURE SPECIFICATION CORRECTION)

**Pre-correction state:** the artifact passed a READ-ONLY adversarial entry review (2026-09-11; 14/15 PASS with 1 PARTIAL) and was recorded as "PASSES ADVERSARIAL ENTRY REVIEW". That review identified material specification defects that were required to be corrected in the durable artifact before Gate B.

**This correction pass (2026-09-11)** applied 14 fixes and re-confirmed Decision A:

1. Exact claim SQL with reverse-ownership `NOT EXISTS` for driver and vehicle, including mandatory self-exclusion `b.id <> :bk` (§5). Deleted rows intentionally NOT excluded from the subquery.
2. Single `force=True` conflict semantic (§14): may relax only `is_online`/`is_available` (admin-only); never ownership/occupancy/state/authorization/integrity.
3. Booking soft-delete disposition: REJECT while `status ∈ ACTIVE_ASSIGNMENT_STATUSES` — one decision, evidence-based, no divergence (§10.1).
4. Documented defaults: `TRANSPORT_STALL_TIMEOUT_SECONDS = 600`, `TRANSPORT_OFFER_TTL_SECONDS = 300` (§4.1); each configurable, not empirically optimized, ship requirement explicit.
5. Reverse-lookup performance risk register with escalation metric and named P1 item (partial index on active `assigned_driver_id`/`assigned_vehicle_id`) (§24.1).
6. Canonical status sets kept single-source, re-verified against the live enum, NOT merged with events-coordination sets (§9).
7. Release↔claim interleaving proof rewritten on the corrected SQL — Scenario A (release-first) and Scenario B (claim-first), 8 steps each (§6.2).
8. Direct availability-flip surfaces documented (3 paths) and assigned to the claim guard as the authoritative backstop (§8).
9. Driver-location security retained as P0 D2-entry dependency, not fixed in this pass (§17).
10. Redis offer model semantics made exact with full lifecycle (create/accept/decline/expiry/cleanup/duplicate/restart/outage/reconstruction); "Redis never authoritative" (§15).
11. P0 stall recovery made concrete with trigger predicate, source of time, default 600, notification, no auto-replacement (§11).
12. Clean P0/P1/P2 scope table with no contradictions (§25).
13. Concurrency test expectations updated for corrected guards, force, and soft-delete (§22).
14. Artifact cleaned: stale "adversarial review passed" pre-correction wording removed; typos fixed; single consistent status line; "CORRECTED AND READY FOR EXPLICIT MOE AUTHORIZATION" / "IMPLEMENTATION NOT AUTHORIZED".

Decision A re-confirmed: 0 P0 tables / 0 P0 columns / 0 P0 enums / 0 P0 constraints / 0 P0 migrations.

## 28.1 FINAL ARTIFACT INTEGRITY PASS (2026-09-11 — 4 corrections, READ-ONLY)

Applied directly to the durable artifact (spec-only; no code, test, or migration touched):

1. **Canonical claim SQL made explicitly single-source (§5).** §5 is declared the ONE authoritative, implementation-ready definition of the claim SQL; §6, §8, §14, §22 reference it; no section reproduces it. Release SQL remains single-source in §9 (separate operation).
2. **`actor_is_admin` defined with an explicit authorization path (§4, §14).** Pinned binding: route layer `@admin_required`/`@role_required("driver")` (decorators.py:384-425 / 240-281) → existing admin boundary `has_global_role(actor, "admin", "super_admin", "owner")` (helpers.py:143-192) → explicit `actor_is_admin` boolean passed into `claim()`. Defensive reject: `force=True` with `actor_is_admin=False` → `unauthorized` before any SQL; driver-accept path always passes `actor_is_admin=False` and never exposes `force`. Final rule: **`force=True` is available only to an already-authorized administrative actor and never changes ownership/conflict/state protections.**
3. **Lock-duration / critical-section risk added to §24.1.** Reverse-lookup scan executes inside the claim transaction while booking/driver/vehicle rows are row-locked → longer write critical section → higher contention as write concurrency grows. P0-correct (correctness is index-independent) vs P1-scalability (named partial index on active `assigned_driver_id`/`assigned_vehicle_id`, NOT created) explicitly distinguished. Escalation metric unchanged (EXPLAIN ANALYZE not single-digit ms / full-table scans).
4. **Honest Git scope attribution (§27.1).** Verified `git status --short` / `git diff --stat` / `git log` / `git ls-files`: only `BACKLOG.md` is proven modified vs HEAD; the other three record files are untracked. **Conclusion stated plainly: "Git scope attribution is inconclusive from the available working-tree state."** No over-claiming.

## 28.2 FINAL DOCUMENTATION PRECISION CLOSURE PASS (2026-09-11 — Items A+B, READ-ONLY)

Distinct historical entry; prior correction history (§28) and integrity-pass history (§28.1) are preserved unchanged.

### Item A — Canonical SQL reconciliation (occurrence audit)

Every occurrence of `NOT EXISTS`, `b.id <> :bk`, `UPDATE driver_profiles SET is_available=false`, and `UPDATE transport_vehicles SET is_available=false` in this artifact was located and classified:

| Occurrence | Location | Classification | Action |
|---|---|---|---|
| Reverse-ownership `NOT EXISTS` guard declared "the ONLY authoritative proof" | §5 (intro prose) | Canonical SQL (authoritative) | retain |
| `r2 = UPDATE driver_profiles SET is_available=false` + `NOT EXISTS` + `b.id <> :bk`; `r3 = UPDATE transport_vehicles SET is_available=false` + `NOT EXISTS` + `b.id <> :bk` | §5 (canonical block) | Canonical claim SQL (SINGLE AUTHORITY) | retain |
| `b.id <> :bk` required self-exclusion rationale | §5 (implementation note) | Canonical-section rationale | retain |
| `UPDATE driver_profiles SET is_available=false WHERE id=D AND … AND NOT EXISTS(holder, id<>)` and shorthand `NOT EXISTS(holder of D, id<>)` | §6.2 (Scenarios A/B steps 3, 6, 2) | Concurrency-proof excerpt of §5/§9 | labeled excerpt — NOW EXPLICIT (§6.2 intro); not a competing definition |
| Claim/release guard descriptions; release `r2`/`r3` `NOT EXISTS` + `b.id <> :bk` | §9 (release SQL + prose) | Release SQL (DISTINCT operation, single authority) + rationale | retain distinct; NOT merged with claim SQL |
| "NOT EXISTS self-exclusion" (stall sweep) | §11 | Prose reference to §9 release guard | retain |
| "reverse-ownership `NOT EXISTS` (§5 `r2`/`r3`)", "NOT EXISTS holds under force" | §14, §22 | Prose reference to §5 | retain (already cites §5) |
| "claim `r2`/`r3` `NOT EXISTS`"; "release `r2`/`r3` `NOT EXISTS`"; index-independence statements | §24.1 | Prose reference, both guards | retain |
| "Exact claim SQL with reverse-ownership `NOT EXISTS` … `b.id <> :bk` (§5)" | §28 (historical) | Historical correction record | retain as history |

**Reconciliation result: Canonical claim SQL = §5. No competing claim definition exists.** No section reproduces the full claim SQL block; §6.2 now labels its inline fragments explicitly as excerpts of §5/§9; the release SQL in §9 remains the distinct single-source release primitive (claim and release are NOT collapsed into one block). No material divergence from §5 was found — no BLOCKED item.

### Item B — Mandated verification tables

**Mandated Verification Table 1 — Correction Verification**

| Correction | Result | Exact evidence |
|---|---|---|
| Single canonical claim SQL | PASS | `docs/transport/d2-atomic-dispatch-claim.md` §5 is the single authoritative claim-SQL definition. Driver and vehicle claim guards include reverse-ownership `NOT EXISTS` with self-exclusion `b.id <> :bk`. §6.2 contains only a clearly labeled explanatory excerpt referencing §5; it is not a competing definition. |
| `actor_is_admin` definition | PASS | §4 / §14 define the authorization path: `@admin_required` (`app/auth/decorators.py:384-425`) → `has_global_role(actor, "admin", "super_admin", "owner")` (`app/auth/helpers.py:143-192`) → explicit `actor_is_admin` passed to `claim()`. Defensive rule: `force=True` with `actor_is_admin=False` returns `unauthorized` before SQL. Driver acceptance never exposes `force`. |
| Lock-duration risk | PASS | §24.1 explicitly records that the reverse-ownership lookup executes inside the claim transaction while booking/driver/vehicle rows are write-locked, increasing critical-section duration and contention risk. P0 correctness is distinguished from P1 scalability hardening; the named P1 partial indexes are not created or migrated in P0. |
| Git verification | INCONCLUSIVE | `git status --short` shows `M BACKLOG.md` and the other durable records as untracked. The current working-tree state cannot independently attribute every record-file change to this correction pass. The report therefore does not overclaim Git authorship/scope. |

**Mandated Verification Table 2 — Specification Integrity**

| Specification integrity property | Result | Exact evidence |
|---|---|---|
| Decision A preserved | PASS | §24 confirms **0 P0 tables / 0 P0 columns / 0 P0 enum changes / 0 P0 constraints / 0 P0 migrations**. No P0 schema change is introduced. |
| Force contradiction resolved | PASS | §14 contains the single authoritative `force=True` rule: admin-only; may relax readiness/administrative `is_online` / `is_available` conditions only; never bypasses ownership, occupancy/conflict, booking-state, authorization, or transaction-integrity protections. Final rule: "force=True is available only to an already-authorized administrative actor and never changes ownership/conflict/state protections." |
| Reverse ownership guard preserved | PASS | §5 contains the canonical driver and vehicle claim guards using `NOT EXISTS` against active bookings with `b.id <> :bk`; rowcount remains the authoritative success gate. |
| Release guard preserved | PASS | §9 release specification uses `Booking.assigned_driver_id` / `assigned_vehicle_id` as ownership authority with active-booking `NOT EXISTS` protection (`b.id <> :bk`), preventing a late release from freeing a resource already re-claimed by another booking. |
| P0/P1 boundaries coherent | PASS | §25 P0 includes atomic claim, terminal release, minimum stall recovery, cancellation guard, location security, offer/accept flow, and resource-conflict protection. P1 includes full reassignment, driver post-acceptance cancel, payment execution, and scalability/index hardening. |
| Artifact clean | PASS | Final artifact sweep: no `Thought:` traces, no tool transcript fragments, no `IMPLEMENTATIONSHIP`, no duplicated live status statements; prior correction records retained and identifiable as historical (§28, §28.1, §28.2). The artifact's active status states specification readiness for MOE authorization with implementation still unauthorized. |
| No production/test implementation | PASS | This pass is documentation-only. No application implementation, concurrency tests, or migrations were authorized or performed. The record explicitly states **Gate B REMAINS NOT AUTHORIZED** and **NO IMPLEMENTATION PERFORMED**. |

**Final verification statement:** Both mandated verification tables are now part of the D2 record. No architectural decision is changed. No production/test code is implemented. Gate B remains pending explicit MOE authorization.

---

TH-3-D2 SPECIFICATION PASSES FINAL ARTIFACT INTEGRITY REVIEW — READY FOR MOE AUTHORIZATION.

Gate B REMAINS NOT AUTHORIZED.

NO IMPLEMENTATION PERFORMED.

D2 SPECIFICATION READY FOR MOE AUTHORIZATION — IMPLEMENTATION NOT AUTHORIZED. STOP.