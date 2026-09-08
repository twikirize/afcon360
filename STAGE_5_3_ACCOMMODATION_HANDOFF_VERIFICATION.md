# STAGE 5-3 — Accommodation Service Handoff & Existing Reservation Architecture Verification

**Status:** INVESTIGATION COMPLETE (report per §19 of the Stage 5-3 task)
**Date:** 2026-09-07
**Scope:** Discovery-first verification of the existing reserve → hold/block → registration-link → consume → complete booking flow, and whether Event is a thin consumer via an Accommodation-owned capability.

---

## 1. Executive verdict

The reserve → hold/block → registration-link → guest-consume → complete flow **already exists** and is
**already wired end-to-end through an Accommodation-owned capability** consumed by Events through a
thin contract. **No new booking entity, no new service, and no architectural change is required.**

The only genuine shortfall found is **not architectural** — it is a set of **pre-existing test defects** in
`tests/test_attendee_accommodation_booking.py` (6 failing tests) that were committed simultaneously with
the attendee booking service in `fbc7491` and have never passed. They do not reflect a regression from
Stage 5-1/5-2 work. They are documented (item 8/9 below) and proposed for backlog, not silently fixed
(§9, §34).

---

## 2. Evidence inspected

### Files / modules inspected
- `app/accommodation/services/coordination_contract.py` (`AccommodationCoordinationContract`)
- `app/events/accommodation_bridge.py` (`issue_accommodation_for_assignment`, `_link_expiry`, `_token_for_booking`)
- `app/events/accommodation_booking_service.py` (`AttendeeAccommodationBookingService`)
- `app/events/guest_coordination_service.py` (`GuestCoordinationService.assign_accommodation`)
- `app/events/routes.py` (attendee accommodation API routes ~2991–3280)
- `app/events/assignment.py` (assign route ~502+)
- `app/accommodation/routes.py` (`/r/<token>` shared_registration :2632, `/assignment/<token>` assignment_completion :2766, group booking :1721–2096, holds :1999–2008)
- `app/accommodation/models/booking_registration_link.py` (`BookingRegistrationLink`)
- `app/accommodation/services/booking_registration_link_service.py`
- `app/accommodation/services/booking_service.py` (`BookingService.create_booking` :233–271)
- `app/accommodation/services/availability_service.py` (:450–468 :711)
- `app/accommodation/services/host_service.py` (:1586–1629)
- `app/accommodation/state_machine/booking_states.py`, `payment_states.py`, `policy_evaluator.py`
- `tests/test_attendee_accommodation_booking.py` (all 21 methods + fixtures)
- `tests/test_event_accommodation_assignment_flow.py` (:194, :836, :902)
- `tests/test_accommodation_lifecycle_verification.py` (:372, :580, :612, :617)
- `tests/test_fix_accommodation_unit_availability.py` (:99, :180)
- `tests/test_accommodation_capacity_rules.py` (:48)
- `tests/test_stage5b2_assignment_lifecycle.py` (Stage 5-2 new file)

### Commands executed
- `git log --oneline -- app/events/accommodation_booking_service.py tests/test_attendee_accommodation_booking.py` → both last touched solely by `fbc7491`
- Baseline combined run (8 files): 6 failed / 97 passed
- Isolated run `tests/test_attendee_accommodation_booking.py`: 6 failed / 10 passed

---

## 3. §19 item-by-item findings

### 3.1 (Item 1) Existing normal accommodation booking flow
YES. Public web flow: search/explore → availability → guest checkout hold → `BookingService.create_booking` → confirm. Routes in `app/accommodation/routes.py` (all web routes, 6214 lines); templates at `templates/accommodation/guest/**`. `BookingService.create_booking` signature (booking_service.py:233–271) **matches** all callers; the spec note claiming a "mismatched signature TypeError at events/routes/assignment.py" is **stale/disproven** — `app/events/assignment.py:502+` now delegates to `GuestCoordinationService.assign_accommodation`, and no mismatched call exists.

### 3.2 (Item 2) Reservation / hold architecture
Derived availability + explicit holds. `HostService.available_units` = `total_units − Σ rooms_requested(active) − Σ units_blocked(non-booked)` (host_service.py:1586–1629, availability_service.py:711). `InventoryBlock` / `RoomHold` used for **temporary** holds during checkout (routes.py:1999–2008, availability_service.py:450–468). There is **no atomic decrement counter**; capacity accounting is **derived** (verified by `test_fix_accommodation_unit_availability.py:99,180` and `test_accommodation_capacity_rules.py:48`).

### 3.3 (Item 3) Bulk / group / block reservation
PARTIAL-exists. Group bookings use `rooms_requested=N` + `group_booking_id` (routes.py:1721–1743, :2078–2096; booking.py:160–161). Capacity is enforced through the derived-availability accounting above; **there is no separate "block reservation" entity** with reservation quantity 100→99→98 semantics. The closest equivalent is the capped multi-use `BookingRegistrationLink` (see 3.4), which enforces pool consumption via `max_registrants` / `registrants_count` with row locks.

### 3.4 (Item 4) Guest registration link / token mechanism
YES. `BookingRegistrationLink` (model `accommodation_booking_registration_links`): `booking_id` FK, `token_hash`, `max_registrants`, `is_active`, `expires_at`, capped multi-use. Routes:
- `/r/<token>` → `accommodation.shared_registration` (routes.py:2632): validates link, is_expired, `is_full` → 409; locks the row `with_for_update()`; creates `GuestRegistration` via `RegistrationService.create(... status="completed")`; honors "event_coordination" placeholder slots (idempotent, no double-slot).
- `/assignment/<token>` → `accommodation.assignment_completion` (routes.py:2766): validates assignment by `acc_link_token_hash`, expiry, booking exists, resolves the event-assignment guest slot by `(booking_id, event_assignment_id, is_active)`, renders `GuestRosterEntryForm` + `SpecialRequestsForm`, completes `GuestRegistration`. Owner-claim token path (`claim_token_hash`) exists.

### 3.5 (Item 5) How reserved inventory is consumed
Consumption is **derived + capped-link**, not a decrement. `BookingRegistrationLink.registrants_count` increments via active `GuestRegistration` rows; `is_full = registrants_count >= max_registrants`. Concurrent consumption is protected by `find_by_token(token, lock=True)` (`with_for_update()`) before each insert. Evidence tests: `test_event_accommodation_assignment_flow.py:194` (2 spots → 0/1/2 → 3rd rejected 409) and `:836` (unknown third party rejected at capacity).

### 3.6 (Item 6) Accommodation-owned services/contracts
- `AccommodationCoordinationContract` — the **sole write boundary**: `ensure_event_guest_slot` (idempotent by `(booking_id, guest_email)`), `release_event_guest_slot`, `ensure_registration_link`.
- Backing services: `BookingService`, `RegistrationService`, `BookingRegistrationLinkService`, `AvailabilityService`, `PaymentPolicyService`, `PricingService`, `SpecialRequestService`.
- Business-rule gates in `app/accommodation/state_machine/` (`BookingStateMachine`, `PaymentStateMachine`, `BookingPolicyEvaluator`, `PaymentPolicyEvaluator`) — not modified in this stage.

### 3.7 (Item 7) Existing Event→Accommodation boundary
Already a thin consumer:
- Events never imports accommodation write models; it uses `AccommodationCoordinationContract` only (events/accommodation_bridge.py header states this invariant explicitly).
- `app/events/accommodation_bridge.py`: per-assignment token persisted on `EventAssignment` (`schedule_json["acc_link_token"]`, `acc_link_token_hash`, `acc_link_expires_at` = max(event.end, booking.check_out) + 7d); pre-fills guest slot via `ensure_event_guest_slot`; emails account-free `/assignment/<token>` link (best-effort, non-fatal).
- `GuestCoordinationService.assign_accommodation` (Stage 5-1/5-2) orchestrates booking + bridge atomically; `EventAssignment.accommodation_booking_id` is a **bare cross-module reference** (no ownership FK) — per Stage 5-1 decision.

### 3.8 (Item 8) Exact missing capability
**None architectural.** The full flow exists. Findings to surface (pre-existing, not introduced by this stage):
- (a) `tests/test_attendee_accommodation_booking.py` has **6 failing tests** (see §4). All are test-defect/pre-existing, not app regressions.
- (b) Spec claim of a "mismatched create_booking signature" is stale (see 3.1).
- (c) The `AttendeeAccommodationBookingService.get_booking_requirements` service-vs-test shape mismatch (`has_booking` key) is a **test-contract drift** candidate — the service returns `BookingPolicyEvaluator.get_booking_requirements(booking)` directly (never had `has_booking`); the test asserts a wrapped shape. Either the test or the contract is stale; needs a decision, not a silent fix (§9).

### 3.9 (Item 9) Minimal implementation required
- **None for architecture/app code.** Event already invokes an Accommodation-owned capability through `AccommodationCoordinationContract`; no `EventAccommodationBooking`, no direct accommodation writes, no new service.
- **Focused tests only** (per §16): add a new Stage 5-3 file proving the mandated behaviors that the existing suites do NOT already isolate (see §5).

### 3.10 (Item 10) What will NOT be changed
- No migrations created/applied. Pending (pre-existing, environment-side) migration family `f1fe91ef0ebf_add_listing_type_column_to_.py`, `1788711780_sync_check_constraints.py`, `1788729103_sync_check_constraints.py` are **untouched**; head remains `1788729103`.
- No changes to `BookingStateMachine` / `PaymentStateMachine` / `BookingPolicyEvaluator` (no compatibility issue proven).
- No `EventAccommodationBooking` entity.
- No payment/wallet/escrow work (Stage 5-4/5-5 out of scope).
- No Transport changes (out of scope).
- No redesign of `scripts/setup_test_db_schema.py` (documented hang on this machine).
- No silent fixing of the 6 pre-existing failing tests.

---

## 4. Classification of the 6 failing tests

All are in `tests/test_attendee_accommodation_booking.py`, shipped together with the service in
`fbc7491` (2026-08-30) and never passing for these cases. Neither Stage 5-1 nor Stage 5-2 touched this
file or the service.

| Test | Failure | Classification |
|---|---|---|
| `test_list_available_properties` | `assert 0 >= 1` (isolated) — fixture creates **no RoomType**, so the property is filtered by `has_capacity` | Pre-existing **test-fixture defect** (ordering-dependent: passes when another suite leaves a RoomType row behind) |
| `test_get_booking_requirements` | `KeyError: 'has_booking'` | Pre-existing **test-contract drift**: service returns `BookingPolicyEvaluator.get_booking_requirements(...)` which never had a `has_booking` key; test asserts a wrapped shape |
| `test_cancel_attendee_booking` | `AttributeError: 'FixtureFunctionDefinition' object has no attribute 'id'` — signature (line 423) is `(app, test_property, test_event, attendee_registration)` but body (line 446) uses `test_organizer_user.id` without requesting the fixture | Pre-existing **test defect** (missing fixture parameter) |
| `test_available_properties_api` | 401 Unauthorized | Pre-existing **test defect**: test sets `sess['user_id']` but routes use Flask-Login `@login_required` which reads `session['_user_id']` |
| `test_book_accommodation_api` | 401 Unauthorized | Same as above |
| `test_book_accommodation_pay_on_arrival_api` | 401 Unauthorized | Same as above |

No app-code regression is implicated.

---

## 5. Focused Stage 5-3 test plan (§16)

New file `tests/test_stage5b3_handoff_architecture.py` proving behaviors the existing suites do not
isolate directly (fixture pattern copied from `tests/test_stage5b2_assignment_lifecycle.py`):

1. Existing accommodation path produces a booking + guest slot **independently** of any Event wiring.
2. Event handoff: registering a guest through the contract keeps the booking intact and creates a GuestRegistration slot with `registration_source="event_coordination"`.
3. Reserved-quantity consumption: `BookingRegistrationLink` pool 100→99→98 consumption semantics for a multi-registrant booking (matches the architectural model).
4. No-stock: an Event requesting when capacity is consumed is rejected **by the Accommodation capability** (Event does not manipulate stock).
5. Ownership isolation: writing an accommodation GuestRegistration row from Event code is not a used path (contract is the only write boundary); absent authorization, direct mutations are not performed by Event.
6. Abandonment: an assigned-but-incomplete slot leaks **no** capacity (no false assignment / fake booking).
7. Completion: booking reference exists on the assignment and Event can complete the assignment against it.
8. Idempotency: `ensure_event_guest_slot` twice for the same `(booking, guest)` does not double-create a slot.

---

## 6. Operating constraints honored
- No migrations created/applied (§20). Pending migration family untouched.
- No direct Event writes to accommodation tables (§8 of task).
- No `EventAccommodationBooking` (§11 of task).
- No state-machine / policy-evaluator edits (§21 of task).
- No test-DB pollution or module-flag manipulation (§18 of task).
- 6 pre-existing failing tests documented, not silently fixed (§9, §34).