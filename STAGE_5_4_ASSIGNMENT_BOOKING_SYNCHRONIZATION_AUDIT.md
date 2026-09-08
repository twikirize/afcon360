# STAGE 5-4 — Assignment ↔ Accommodation Booking Synchronization (Discovery & Verification Audit)

**Node:** Stage 5-4 (DISCOVERY / VERIFICATION — read-only; no application code changed)
**Frozen boundaries honored:** `EventAssignment.accommodation_booking_id` is a bare `BigInteger`
(`info={"id_kind": IDKind.CROSS_MODULE_REF}`) with **no FK and MUST NOT be converted**. No
`EventAccommodationBooking` entity created. No schema, migration, or routing change.
**Date:** 2026-09-07

---

## 1. Scope

Discovery and verification of the synchronization contract between Event assignments
(`EventAssignment`) and Accommodation bookings (`AccommodationBooking`) plus the per-booking
guest-slot records (`GuestRegistration`), answering Q1–Q8, proving the ownership boundary, and
classifying gaps A/B/C/D. Focused proof tests were added ONLY where evidence was missing.

**Files inspected (evidence):**
- `app/events/guest_coordination_service.py` — `assign_accommodation` (:571), `cancel` (:668),
  `_assignment` (:303), `_resolve_accommodation_booking` (:408), `_commit_assignment` (:520),
  `dashboard` (:174).
- `app/events/accommodation_bridge.py` — `issue_accommodation_for_assignment` (:45), dead
  `_token_for_booking` (:32).
- `app/accommodation/services/coordination_contract.py` — `ensure_event_guest_slot` (:31),
  `release_event_guest_slot` (:125).
- `app/events/accommodation_booking_service.py` — attendee self-service `create_booking` (:220),
  `cancel_attendee_booking` (:469).
- `app/events/models.py` — `EventAssignment` (:1113), `accommodation_booking_id` (:1135).
- `app/accommodation/models/guest_registration.py` — `event_assignment_id` FK (:81), `remove` (:143).
- `app/accommodation/models/booking.py` — `cancel` (:485-508).
- `app/accommodation/services/booking_service.py` — `cancel_booking` (:1589-1770).
- `app/accommodation/state_machine/booking_states.py` — no emit hooks; `READY_FOR_CHECKIN` computed.
- `app/events/services.py` — `_cancel_event_accommodation_bookings` (:566).
- `app/accommodation/routes.py` — `assignment_completion` (:2767), `remove_registration` (:2914),
  `guest_cancel_booking` (:3673).
- `app/events/routes_accommodation.py` — inventory read path (:71-86); `app/events/assignment.py` — stats (:308-314).
- `app/notifications/events/registry.py` (:114-118, :336-344) and `app/notifications/events/policy.py` (:416-440).
- Tests listed in Section 11 plus the new `tests/test_stage5b4_sync_synchronization.py`.

**Out of scope / deliberately not implemented:** Stage 5-5, Transport, Stage 6, Payment, Wallet,
escrow. Any finding touching those is recorded here and in `BACKLOG.md` only.

---

## 2. Runtime Trace

Two Event-initiated flows both terminate, atomically, in the same Accommodation state:

**Flow 1 — Coordinator assignment** (`GuestCoordinationService.assign_accommodation`):
actor permission → module toggle → `_registration` → `_resolve_accommodation_booking`
(`select_for_update` on the booking row; validates status ∈ {held, confirmed, pending,
pending_approval}, dates presence, room active, room capacity, event-link or owner-link) →
`_assignment` (lock/create the `EventAssignment`, flush) → `_provider_allows_assignment` veto
→ `assignment.accommodation_booking_id = booking.id` → (reassign only) contract
`release_event_guest_slot(old)` → bridge `issue_accommodation_for_assignment` (sets
`acc_link_token_hash`/`acc_link_expires_at` and contract `ensure_event_guest_slot(...,
event_assignment_id=assignment.id)`) → `_commit_assignment` (flush, domain-event emit, forensic
audit) → **single `db.session.commit()`** (line 567). Any failure rolls back the whole chain.

**Flow 2 — Attendee self-service booking** (`AttendeeAccommodationBookingService.create_booking`):
creates the booking via `BookingService.create_booking` (accommodation-owned), links
`assignment.accommodation_booking_id = booking.id` (:288), calls
`AccommodationCoordinationContract.ensure_event_guest_slot` (:292), issues the completion link via
the bridge (:312), then a single commit (:314).

Both flows converge on the same three-way linkage in one transaction:
`EventAssignment.id ↔ GuestRegistration.event_assignment_id` (real FK) and
`EventAssignment.accommodation_booking_id → AccommodationBooking.id` (cross-module ref).

---

## 3. Assignment → Booking (Event writes the reference)

**Q1 answer — a durable, single-transaction relationship exists.**
- `assign_accommodation` sets `assignment.accommodation_booking_id = booking.id` and neither the
  bridge nor the contract commits early; `_commit_assignment` performs the only commit
  (guest_coordination_service.py:567, :624-626).
- The bridge persists the per-assignment link token (SHA-256 hash, `acc_link_token_hash`) and
  ensures the guest slot in the same unit of work (accommodation_bridge.py:45).
- The slot creation is idempotent: `ensure_event_guest_slot` twice for the same
  (booking, assignment) returns the same `slot_id` (proven in `test_ensure_event_guest_slot_idempotent`).
- No FK on `accommodation_booking_id` is intentional; it is a cross-module reference guarded by the
  Event resolver (`_resolve_accommodation_booking`), never used as a join key.

---

## 4. Booking → Assignment (reverse pointer)

**Q2 answer — the chain is fully reconstructible in both directions.**
- `GuestRegistration.event_assignment_id` is a **real FK → `event_assignments.id`
  (ondelete SET NULL)** (guest_registration.py:81). It is the reverse pointer created by the contract.
- Reconstruction proof: `assignment_completion` (`/assignment/<token>`, routes.py:2767) resolves
  `sha256(token)` → `EventAssignment` → `db.session.get(AccommodationBooking, assignment.accommodation_booking_id)`
  → slot by `(booking_id, event_assignment_id, is_active=True)`.
- Forward reads exercise the same path in `GuestCoordinationService.dashboard` / `guest_journey`.

---

## 5. Cancellation — three paths, three synchronization levels

| Trigger | Who acts | Slot released? | Assignment ref cleared? | Token cleared? | Notified? |
|---|---|---|---|---|---|
| Coordinator cancel (`GuestCoordinationService.cancel`, :668) | Events | **Yes** via `release_event_guest_slot` | **Yes** (:706) | **Yes** (:704-705) | Yes (:722) |
| Attendee self-service cancel (`cancel_attendee_booking`, accommodation_booking_service.py:469) | Events | **No** | **Yes** (:502) | **No** | No |
| Accommodation cancel (`BookingService.cancel_booking`, booking_service.py:1589) / `_cancel_event_accommodation_bookings` (events/services.py:566) | Accommodation | **No** | **No** | **No** | No |

**Q3 answer:** cancellation of a booking AFTER it was assigned does **not** propagate back to the
Event module. `BookingService.cancel_booking` releases BlockedDate/InventoryBlock, transitions the
booking to CANCELLED (or REFUNDED for paid refundable `pay_now`), records the policy snapshot, and
commits — it never touches `EventAssignment` or `GuestRegistration`, and emits no event. The
Event-side coordinator cancel is fully synchronized, but it is the only fully synchronized path.

---

## 6. Reassignment

**Q5 answer — reassignment is a single atomic unit with NO committed intermediate window (proved).**
Ordering inside `assign_accommodation` (:588-626): set new `accommodation_booking_id` →
`release_event_guest_slot(old_ref, event_assignment_id=assignment.id, reason="reassigned")` →
`issue_accommodation_for_assignment` (new slot + token) → single commit. A same-booking
re-assignment short-circuits at the `previous == booking.id` guard.

New focused proof `test_reassignment_is_atomic_no_partial_committed_window`: when the bridge fails
after the old slot was released, the raise triggers rollback (:613/:621) so the assignment still
points at the OLD booking, the OLD slot is still `is_active`, and the NEW booking has zero slots.
There is no state in which the attendee is visible as unassigned.

---

## 7. Registration Completion

**Q6 answer — completion exists and resolves the SAME slot created by the bridge, but does NOT
revalidate booking status.**
`assignment_completion` (routes.py:2767) resolves token → assignment → booking → slot and, on POST,
finalizes the slot. It checks the booking only for existence / not-deleted — **not** for a still
assignable status. A cancelled/refunded booking can therefore still be used to "complete" a guest’s
registration. This is part of the Q3 gap (see Section 12, C2). The slot-resolution identity is
proven by `test_completion_resolves_same_slot_and_reference`.

---

## 8. Shared Capacity

**Q7 answer — capacity is derived and Accommodation-owned, with no Event-side counter.**
The pool is consumed by repeated `ensure_event_guest_slot` calls; the derived-capacity model is
`max_registrants = reserved_quantity` (capacity formula on the registration link), consumed by
active slots (`is_active=True`), enforced in Accommodation via row-locked insert + `active_count`
vs allowed. The Event side keeps a dependency-free count only (dashboard/inventory queries);
`BookingRegistrationLinkService.spots_remaining` is the authoritative counter and it is decremented
only when the slot is created by Accommodation. `test_normal_shared_booking_capacity` and
`test_no_stock_request_rejected_by_accommodation_capability` prove rejection by the capability
itself, not by Event. Event-initiated reassign/cancel release capacity back (no leak proofs in
Stage 5-3/5-4 files).

---

## 9. Ownership Boundary

**Q9 answer — the boundary holds: no synchronization violation was found.**
- Accommodation owns the booking lifecycle (`BookingService`, `BookingStateMachine`) and the
  guest-slot records (`GuestRegistration.remove`, `RegistrationService`).
- `AccommodationCoordinationContract` is the **only** write surface Events uses into Accommodation
  guest state; `test_events_side_never_writes_accommodation_directly` verifies the Events-side
  modules never construct `GuestRegistration` / `BookingRegistrationLink` and import no
  accommodation-model write APIs.
- `GuestRegistration.event_assignment_id` is a coordination *reference* (SET NULL on deletion), not
  Event ownership of Accommodation state.
- Domain-event flow is one-directional: Events emits `EVENT_ACCOMMODATION_ASSIGNED` /
  `EVENT_ACCOMMODATION_CHANGED` / `EVENT_COORDINATION_CANCELLED` (registry.py:114-118; policy
  hooks policy.py:416-440). **Accommodation emits nothing** (no `emit_event` in `app/accommodation`).
- `event_id` on bookings and `context_type="event"` are read-side linkage metadata, not write ownership.

---

## 10. State Machine Interaction

`BookingStateMachine.transition` has **no event-emit hook** (booking_states.py); it is a pure state
guard. `PaymentStateMachine` is separate. `READY_FOR_CHECKIN` is a computed property, not stored.
Cancellation from `confirmed` routes to CANCELLED, or to REFUNDED when a refund is processed —
both OUTSIDE the assignable set `{held, confirmed, pending, pending_approval}` enforced by
`_resolve_accommodation_booking` (:437-440). There is no signal, listener, or reconciler that reacts
to these transitions; the BookingPolicyEvaluator is the only cross-cutting hook and it is read-side.

---

## 11. Existing Tests

Suites run this session (smallest relevant set; new file added):

| File | Result |
|---|---|
| `test_event_accommodation_assignment_flow.py` | 10 passed |
| `test_guest_coordination_accommodation.py` | passed |
| `test_guest_coordination_contract.py` | 6 passed |
| `test_assignment_ownership_boundary.py` | 10 passed |
| `test_stage5b2_assignment_lifecycle.py` | 9 passed |
| `test_stage5b3_handoff_architecture.py` | 8 passed |
| `test_stage5b4_sync_synchronization.py` (NEW) | 2 passed |
| `test_accommodation_lifecycle_verification.py` | passed |
| `test_guest_assignment_account_optional.py` | passed |

**Combined:** `93 passed, 0 failed, 0 errors, 0 skipped`.

Coverage map: Event→Accommodation direction is well covered (assign, reassign slot release,
cancellation frees capacity, token isolation, shared capacity, completion identity, idempotency,
ownership isolation). The **uncovered** horizontal slice is exactly the gap in Section 12: booking
cancelled/changed on the Accommodation side after assignment. The 2 new tests close that evidence
gap (one proves atomic reassignment, one proves the missing propagation). The pre-existing 6 failing
tests in `tests/test_attendee_accommodation_booking.py` remain unchanged and are not part of the
chosen suite (documented baseline, fbc7491).

---

## 12. Gaps

- **Gap A (synchronization nonexistent):** Not applicable — a real, tested Event→Accommodation
  synchronization exists.
- **Gap B (exists, not fully implemented):** YES — accommodation-initiated booking cancellation is
  not surfaced to the Event module at all: no callback, no listener, no reconciler
  (`BookingStateMachine` has no emit hook; `app/accommodation` emits no domain events).
- **Gap C (implemented but genuine defect):** YES —
  - **C1 (stale assignment):** after `BookingService.cancel_booking`, `EventAssignment`
    `accommodation_booking_id` still points to the cancelled/refunded booking, `acc_link_token_hash`
    stays set, and the `GuestRegistration` slot stays `is_active=True` (proved by new test
    `test_booking_cancel_after_assignment_is_not_propagated_to_event`).
  - **C2 (unguarded completion):** `assignment_completion` does not revalidate booking status, so an
    attendee can complete registration against a cancelled/refunded booking.
  - **C3 (read staleness, informational):** `dashboard` / `assignment.py` stats count any assignment
    with `accommodation_booking_id IS NOT NULL` as "assigned" regardless of booking status; the
    inventory read path filters status but does not remediate the reference.
  - **C4 (secondary leak):** attendee self-service `cancel_attendee_booking` clears the assignment
    pointer but never releases the slot via the contract.
- **Gap D (architecture genuinely missing):** A dedicated Accommodation→Event notification bus is
  NOT required to satisfy the requirement — see Section 13.

**Corrections to prior findings:**
- `release_unmatched_guest` does **not exist** in the codebase. Actual roster removal is
  `RegistrationService.remove(row, ...)` → `GuestRegistration.remove()` (routes.py:2914;
  guest_registration.py:143 sets `is_active=False`). Stage 5-3 report item 4 referenced a
  nonexistent symbol — corrected here.
- `_token_for_booking` in `accommodation_bridge.py:32` is dead code (defined, never called); the link
  token is generated inline in `issue_accommodation_for_assignment`.
- The creation-path discovery test revealed `BookingService.cancel_booking` routes a refundable,
  guaranteed `pay_now` booking to **REFUNDED**, not CANCELLED.

---

## 13. Minimal Recommendation (NOT implemented — requires authorization)

The smallest correction preserves the frozen architecture (Accommodation never depends on Event;
Event remains the coordinator/consumer; the contract remains the only write surface):

1. **Read-side revalidation (C1/C3):** Event read paths (dashboard, stats, guest journey) that
   expose an assignment treat a booking outside {held, confirmed, pending, pending_approval} as
   "not assigned". Informational staleness disappears without new writes.
2. **Fail-closed completion (C2):** `assignment_completion` revalidates the booking status before
   completing the slot and fails with a clear message otherwise.
3. **Contract-based cleanup on detection (C1):** when an invalid reference is detected (completion
   attempt or coordinator view), invoke `AccommodationCoordinationContract.release_event_guest_slot`
   and clear `assignment.accommodation_booking_id` / token hash — Event-side caller of the existing
   contract, no new architecture.
4. **Attendee path parity (C4):** `cancel_attendee_booking` releases the slot through the contract
   (it already clears the pointer).
5. **Documentation:** correct the Stage 5-3 report symbol and note the dead `_token_for_booking`.

No schema change, no migration, no accommodation→event dependency, no `EventAccommodationBooking`.

---

## 14. Migration Status

**No migration created. No migration applied.** Dev and test databases share a single Alembic head
(`flask db heads --directory migrations` → `1788729103`); the test bootstrap (`db.create_all()` +
stamp) is unchanged. Neither of the new tests touches schema.

---

## 15. Verdict

**DEFECT FOUND — implementation authorization required.**

Synchronization exists and is correct for every Event-initiated operation (Q1–Q8 satisfied; the
ownership boundary §9 holds; Event→Accommodation direction is atomic, contract-driven, idempotent,
and well tested). However, the accommodation-initiated booking-cancellation path is not synchronized
back to the Event module and leaves a stale assignment, an active guest slot, a live completion
token, and an unguarded completion route (Section 12, Gap B/C1/C2/C3/C4) — a genuine asymmetric
defect under classification C. The minimal correction in Section 13 is application-layer and does
not require new architecture (Gap D not needed).

**Counts:** `PASS = 93 / FAIL = 0 / ERROR = 0 / SKIPPED = 0` (9 suites, incl. new `test_stage5b4_sync_synchronization.py`).
**Startup:** `STARTUP_OK` (fresh `create_app()`). Pre-existing external baseline: 6 failing tests in
`test_attendee_accommodation_booking.py` (unchanged, not in the chosen suite).

---

## 16. Section 13 Correction — IMPLEMENTED (follow-up node, authorized 2026-09-07)

The minimal correction (Section 13, C1–C4) is implemented and verified. Application-layer only:
no schema, no migration, no new architecture, no accommodation→event dependency, no
`EventAccommodationBooking`, no `SystemConfig.MODULE_FLAGS` writes.

**Changes per file:**

- `app/events/guest_coordination_service.py`
  - New single source of truth `ACCOMMODATION_ASSIGNABLE_STATUSES = frozenset(("held", "confirmed",
    "pending", "pending_approval"))` (module constant, before the class).
  - New helpers `_accommodation_booking_assignable(booking)`,
    `_assignable_accommodation_booking_ids(bookings)`, `_accommodation_assignment_status(assignment)`.
  - `_resolve_accommodation_booking` now honours assignability; dashboard rows set
    `accommodation_assigned=False` + `accommodation=None` for non-assignable bookings; dashboard
    aggregate revalidated and deduped (`unique_assignments = {a.id: a for a in assignments.values()
    if a.id is not None}` — one assignment can appear under both a registration and a user key);
    guest_journey status via `_accommodation_assignment_status`.
  - New idempotent `retire_invalid_accommodation_assignment(assignment, *, removed_by_user_id=None,
    reason=None)`: releases the slot via `AccommodationCoordinationContract.release_event_guest_slot`
    (skips only on `BOOKING_NOT_FOUND` / deleted / missing booking), clears `accommodation_booking_id`
    + `acc_link_token_hash` + `acc_link_expires_at`, sets `status = "active" if
    transport_booking_id else "cancelled"`, sets `assigned_at`, single commit, returns False when
    there is nothing to do.
- `app/events/assignment.py`
  - The `accommodation_assigned` stat now JOINs `AccommodationBooking` filtered `is_deleted=False`
    and `status IN (assignable set)`; `list_attendees` builds `valid_accommodation_booking_ids`
    (one query) and skips stale accommodation-only assignments before building `assignment_map`.
- `app/accommodation/routes.py` (`assignment_completion`, ~:2784)
  - Lazy-imports `GuestCoordinationService`; revalidates `not booking or booking.is_deleted or not
    GuestCoordinationService._accommodation_booking_assignable(booking)`; on invalid reference calls
    `retire_invalid_accommodation_assignment(assignment, removed_by_user_id=None, reason="booking no
    longer assignable during assignment completion")` (rollback + log on exception) and fails closed
    with the 404 expired template. No slot finalization is performed for a retired assignment.
- `app/events/accommodation_booking_service.py` (`cancel_attendee_booking`)
  - After `booking.cancel()` reports success: releases the slot via
    `release_event_guest_slot` (skip only on `BOOKING_NOT_FOUND`), clears the pointer and token
    hash/expiry, single commit; rollback on exception.

**Regression tests** — `tests/test_stage5b4_sync_synchronization.py` grew 2 → **6 passed / 0 failed**:

| Test | Proves |
|---|---|
| `test_reassignment_is_atomic_no_partial_committed_window` (kept) | No intermediate unassigned window |
| `test_booking_cancel_after_assignment_is_not_propagated_to_event` (kept) | Gap B documented; no auto-propagation added |
| `test_c1_cancelled_booking_is_not_presented_as_active_assignment` | C1: event dashboard row unassigns, stats count excludes the booking |
| `test_c2_completion_route_fails_closed_for_cancelled_booking` | C2+C3: HTTP GET `/accommodation/assignment/<token>` → 404; pointer/token cleared; slot released |
| `test_c3_retire_invalid_assignment_is_idempotent` | C3: second retire is a no-op returning False |
| `test_c4_attendee_cancel_releases_slot_and_clears_pointer` | C4: self-service cancel releases the slot and clears the pointer/token |

**Verification (after implementation):** 9-file focused suite → **97 passed / 0 failed / 0 errors /
0 skipped**; startup `python -c "from app import create_app"` → `STARTUP_OK`; migration head single
`1788729103` (dev + test) unchanged. Note: the HTTP test (`test_c2`) captures primitive ids before
the test-client request and re-fetches rows afterwards because the client request tears the session
down (detached `DetachedInstanceError` on the original instances).

**Scope protections honoured:** no fix to the 6 pre-existing `test_attendee_accommodation_booking.py`
defects (unchanged); no migration created/applied; no `_token_for_booking` removal (dead code,
documented deferred item 5); no unrelated refactor of Transport / Stage 5-5 / Stage 6.

---

## 17. Stage 5-5 — Cancellation / Reassignment Lifecycle (VERIFIED + 2 DEFECTS FIXED, 2026-09-07)

Stage 5-5 verified the full cancellation/reassignment lifecycle matrix against the code and added
focused lifecycle + regression tests. All lifecycle invariants held; two genuine failure-path
defects were found and fixed (minimal, application-layer only).

### Lifecycle matrix — verified against code

| Id | Scenario | Result |
|---|---|---|
| A | Coordinator cancels accommodation (`GuestCoordinationService.cancel`) | Slot released via contract, pointer + token + expiry cleared, `status="cancelled"`, single commit (guest_coordination_service.py:766-896) |
| B | Attendee self-service cancel (`cancel_attendee_booking`) | Booking cancelled, slot released + pointer/token cleared in one transaction (Stage 5-4 C4) |
| C | Accommodation-side cancel (`BookingService.cancel_booking`) | Not propagated to Events; read revalidation presents attendee as unassigned (Stage 5-4 C1/C3) |
| D | Repeated cancel | Idempotent — slot released exactly once, second call raises `ASSIGNMENT_NOT_FOUND`, no double release |
| E | Reassignment | Atomic — old slot released + new slot ensured in ONE transaction (Stage 5-4 proof); pointer moved; token rotated |
| F | Cancel → reassign | Works from the cleared state |
| G | Reassign → cancel | Clears the NEW booking's slot |
| H | Cross-context cancellation | Rejected (an attendee of one event cannot cancel another event's assignment) |

### Defects found and fixed (both in `app/events/guest_coordination_service.py`, pure Python)

- **D1 — coordinator `cancel()` (accommodation branch, ~:795):** the old-booking slot release raised an
  unguarded `CoordinationContractError("BOOKING_NOT_FOUND")` whenever the booking had been soft-deleted
  on the Accommodation side, surfacing as an HTTP 500. Fixed by wrapping the release: skip only
  `BOOKING_NOT_FOUND` (log + continue), re-raise others — matching the established skip pattern used by
  `cancel_attendee_booking` and `retire_invalid_accommodation_assignment`.
- **D2 — reassignment path (~:698):** the old-booking slot release similarly raised `BOOKING_NOT_FOUND`
  after soft-delete, aborting an otherwise valid reassignment to a NEW booking with `COORDINATION_FAILED`
  (500). Fixed identically: skip only `BOOKING_NOT_FOUND` (log + continue) so the reassignment completes.

Note: `current_app.logger` was already imported and used elsewhere in the module (e.g.
`retire_invalid_accommodation_assignment`, ~:656), so no import change was required.

### Tests — `tests/test_stage5b5_cancellation_reassignment_lifecycle.py` → **10 passed / 0 failed**

| Test | Proves |
|---|---|
| `test_a_coordinator_cancel_releases_slot_and_clears_pointer` | A: coordinator cancel releases slot + clears pointer/token/expiry, status cancelled |
| `test_b_attendee_cancel_releases_slot_and_clears_pointer` | B: attendee cancel releases slot + clears pointer/token |
| `test_c_accommodation_side_cancel_not_propagated_but_read_unassigned` | C: no propagation; read revalidates away |
| `test_d_repeated_coordinator_cancel_is_idempotent` | D: second cancel → `ASSIGNMENT_NOT_FOUND`, no double release |
| `test_e_reassignment_moves_pointer_and_rotates_token` | E: pointer moved, old slot released, new slot ensured, token rotated |
| `test_f_cancel_then_reassign_from_clear_state` | F: reassignment works after cancel |
| `test_g_reassign_then_cancel_from_new_state` | G: cancel clears the new slot |
| `test_h_cross_context_cancellation_rejected` | H: cross-event cancel rejected; other event's assignment untouched |
| `test_d1_coordinator_cancel_survives_deleted_old_booking` | D1 regression: cancel no longer 500s on deleted booking |
| `test_d2_reassignment_survives_deleted_old_booking` | D2 regression: reassign completes even when the old booking is deleted |

### Verification (after implementation)

- 10-file Stage 5 focus suite → **107 passed / 0 failed / 0 errors / 0 skipped** (Stage 5-4, 97 in 9 files; +10 from this file).
- Startup `python -c "from app import create_app"` → exit 0, `STARTUP_OK`.
- Migration head single **`1788729103`** (dev + test) unchanged; `flask db current` = `1788729103 (head)`.
- No migration created/applied; no `SystemConfig.MODULE_FLAGS` writes; no schema change; no wallet/payment/escrow/transport work.

### Architecture check (unchanged)

Event → GuestCoordinationService → AccommodationCoordinationContract → Accommodation remained the sole
write surface. `EventAssignment.accommodation_booking_id` stays a cross-module reference (not a FK); no
new `EventAccommodationBooking`; no accommodation→event sync added. Both fixes preserved the asymmetric,
event-side revalidation architecture introduced in Stage 5-4.