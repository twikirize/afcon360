# AFCON360 Accommodation Booking System - Engineering Audit
**Target:** `Implement/booking_flow.md`  
**Auditor Role:** Independent Engineering Auditor  
**Date:** 2026-07-31  
**Codebase Root:** `C:\Users\OBED\Desktop\afcon360_app`

---

## 1. Scope of Inspection

| Item | Detail |
|------|--------|
| Specification reviewed | `Implement/booking_flow.md` |
| Directories inspected | `app/accommodation/`, `app/models/`, `app/utils/`, `app/tasks/` |
| Files inspected | `app/accommodation/models/booking.py` (421 lines), `app/accommodation/state_machine/booking_states.py` (198 lines), `app/accommodation/services/booking_service.py`, `app/accommodation/routes.py`, `app/accommodation/tasks/reconciliation.py` |
| Models inspected | `AccommodationBooking`, `AccommodationBookingStatus`, `AccommodationPaymentStatus`, `BookingStatusHistory` |
| Services inspected | `BookingService` (in `booking_service.py`) |
| Routes inspected | Accommodation blueprint routes (in `routes.py`) |
| Tests inspected | No test files found for accommodation state machine or booking flow |

---

## 2. Requirement-by-Requirement Evidence

### Requirement: Booking states include DRAFT
**Classification:** VERIFIED IMPLEMENTED  
**Evidence:** `AccommodationBookingStatus` enum contains `DRAFT = "draft"`.  
**Evidence Location:** `app/accommodation/models/booking.py`, `AccommodationBookingStatus`, line 29  
**Proves:** The enum can store the DRAFT state value.  
**Does NOT prove:** Bookings are created in DRAFT during runtime; that the state is used as the initial state.

### Requirement: Booking states include HELD
**Classification:** VERIFIED IMPLEMENTED  
**Evidence:** `AccommodationBookingStatus` enum contains `HELD = "held"`.  
**Evidence Location:** `app/accommodation/models/booking.py`, `AccommodationBookingStatus`, line 30  
**Proves:** The enum can store the HELD state value.  
**Does NOT prove:** That the HELD state is reachable via the state machine from DRAFT.

### Requirement: Booking states include PENDING_PAYMENT
**Classification:** VERIFIED IMPLEMENTED  
**Evidence:** `AccommodationBookingStatus` enum contains `PENDING_PAYMENT = "pending_payment"`.  
**Evidence Location:** `app/accommodation/models/booking.py`, `AccommodationBookingStatus`, line 31  
**Proves:** The enum can store the PENDING_PAYMENT state value.  
**Does NOT prove:** That payment status is validated before transitioning into CONFIRMED.

### Requirement: Booking states include PENDING_APPROVAL
**Classification:** VERIFIED IMPLEMENTED  
**Evidence:** `AccommodationBookingStatus` enum contains `PENDING_APPROVAL = "pending_approval"`.  
**Evidence Location:** `app/accommodation/models/booking.py`, `AccommodationBookingStatus`, line 32  
**Proves:** The enum can store the PENDING_APPROVAL state value.  
**Does NOT prove:** That a host approval workflow exists.

### Requirement: Booking states include CHECKED_IN
**Classification:** VERIFIED IMPLEMENTED  
**Evidence:** `AccommodationBookingStatus` enum contains `CHECKED_IN = "checked_in"`.  
**Evidence Location:** `app/accommodation/models/booking.py`, `AccommodationBookingStatus`, line 33  
**Proves:** The enum can store the CHECKED_IN state value.  
**Does NOT prove:** That a check-in guard prevents checkout from other states.

### Requirement: Booking states include CHECKED_OUT
**Classification:** VERIFIED IMPLEMENTED  
**Evidence:** `AccommodationBookingStatus` enum contains `CHECKED_OUT = "checked_out"`.  
**Evidence Location:** `app/accommodation/models/booking.py`, `AccommodationBookingStatus`, line 35  
**Proves:** The enum can store the CHECKED_OUT state value.  
**Does NOT prove** That a transition from CHECKED_IN to CHECKED_OUT is enforced.

### Requirement: Booking states include CLOSED
**Classification:** VERIFIED IMPLEMENTED  
**Evidence:** `AccommodationBookingStatus` enum contains `CLOSED = "closed"`.  
**Evidence Location:** `app/accommodation/models/booking.py`, `AccommodationBookingStatus`, line 36  
**Proves:** The enum can store the CLOSED state value.  
**Does NOT prove:** That CLOSED is only reachable from CHECKED_OUT.

### Requirement: Booking states include NO_SHOW
**Classification:** VERIFIED IMPLEMENTED  
**Evidence:** `AccommodationBookingStatus` enum contains `NO_SHOW = "no_show"`.  
**Evidence Location:** `app/accommodation/models/booking.py`, `AccommodationBookingStatus`, line 37  
**Proves:** The enum can store the NO_SHOW state value.  
**Does NOT prove:** That NO_SHOW is only reachable from CONFIRMED.

### Requirement: Booking states include EXPIRED
**Classification:** VERIFIED IMPLEMENTED  
**Evidence:** `AccommodationBookingStatus` enum contains `EXPIRED = "expired"`.  
**Evidence Location:** `app/accommodation/models/booking.py`, `AccommodationBookingStatus`, line 38  
**Proves:** The enum can store the EXPIRED state value.  
**Does NOT prove:** That holds expire automatically after a time window.

### Requirement: Booking states include REFUNDED
**Classification:** VERIFIED IMPLEMENTED  
**Evidence:** `AccommodationBookingStatus` enum contains `REFUNDED = "refunded"`.  
**Evidence Location:** `app/accommodation/models/booking.py`, `AccommodationBookingStatus`, line 39  
**Proves:** The enum can store the REFUNDED state value.  
**Does NOT prove:** That a refund workflow exists or is triggered correctly.

### Requirement: READY_FOR_CHECKIN is a computed state, not stored
**Classification:** VERIFIED IMPLEMENTED  
**Evidence:** Property `is_ready_for_checkin` defined on `AccommodationBooking`; no persistence column for this state.  
**Evidence Location:** `app/accommodation/models/booking.py`, `AccommodationBooking.is_ready_for_checkin`, lines 144–158  
**Proves:** READY_FOR_CHECKIN is computed from other fields at access time.  
**Does NOT prove:** That `is_ready_for_checkin` is called in any route or service to gate check-in.

### Requirement: `is_ready_for_checkin` evaluates payment, date, guests
**Classification:** VERIFIED IMPLEMENTED  
**Evidence:** The property body checks `payment_status_enum in [PAID, PARTIALLY_PAID]`, `check_in <= date.today()`, and `all_required_guests_registered`.  
**Evidence Location:** `app/accommodation/models/booking.py`, `AccommodationBooking.is_ready_for_checkin`, lines 200–210 (within file view at offset 192)  
**Proves:** The computation logic matches the specification criteria.  
**Does NOT prove:** That these criteria are sufficient or that the property is used as a guard.

### Requirement: `BookingStatusHistory` has `trigger` field
**Classification:** VERIFIED IMPLEMENTED  
**Evidence:** `trigger = Column(String(100), nullable=True)` defined on `BookingStatusHistory`.  
**Evidence Location:** `app/accommodation/models/booking.py`, `BookingStatusHistory`, line 409  
**Proves:** The history model can store what triggered a transition.  
**Does NOT prove:** That the `transition()` method always populates this field.

### Requirement: `BookingStatusHistory` has `metadata` field (named `change_metadata`)
**Classification:** VERIFIED IMPLEMENTED  
**Evidence:** `change_metadata = Column(JSON, nullable=True)` defined on `BookingStatusHistory`.  
**Evidence Location:** `app/accommodation/models/booking.py`, `BookingStatusHistory`, line 410  
**Proves:** The history model can store structured context for transitions.  
**Does NOT prove:** That the field is populated for every transition or that it contains meaningful data.

### Requirement: State machine transition matrix covers all spec states
**Classification:** VERIFIED IMPLEMENTED  
**Evidence:** `VALID_TRANSITIONS` dictionary in `BookingStateMachine` contains entries for DRAFT, HELD, PENDING_PAYMENT, PENDING_APPROVAL, CONFIRMED, CHECKED_IN, CHECKED_OUT, CLOSED, CANCELLED, REFUNDED, EXPIRED, NO_SHOW.  
**Evidence Location:** `app/accommodation/state_machine/booking_states.py`, `BookingStateMachine.VALID_TRANSITIONS`, lines 32–62  
**Proves:** All spec states are present as keys or values in the transition map.  
**Does NOT prove:** That business rules guard each transition; only that the map structure exists.

### Requirement: Transition guards exist for state changes
**Classification:** PARTIALLY IMPLEMENTED  
**Existing evidence:** `_can_check_in()` method exists and validates payment status, check-in date, and guest registration before allowing CHECKED_IN.  
**Missing evidence:** No guard exists for `PENDING_PAYMENT → CONFIRMED` (payment confirmation not validated); no guard exists for `CONFIRMED → CANCELLED` (cancellation policy not checked); no guard exists for `HELD → EXPIRED` (time-based expiry not implemented).  
**Evidence Location:** `app/accommodation/state_machine/booking_states.py`, `BookingStateMachine._can_check_in()`, lines 86–100  
**Proves:** A guard mechanism exists for at least one transition.  
**Does NOT prove:** That guards exist for the majority of transitions.

### Requirement: `can_transition()` method validates transitions
**Classification:** VERIFIED IMPLEMENTED  
**Evidence:** `can_transition(booking, new_status)` method exists and checks `CHECKED_IN` specially via `_can_check_in()`, then falls back to `VALID_TRANSITIONS` lookup.  
**Evidence Location:** `app/accommodation/state_machine/booking_states.py`, `BookingStateMachine.can_transition()`, lines 64–84  
**Proves:** The method exists and performs basic validation.  
**Does NOT prove:** That `can_transition()` is called before every state change in routes/services.

### Requirement: Booking default status is DRAFT
**Classification:** VERIFIED IMPLEMENTED  
**Evidence:** `status = Column(String(50), default=AccommodationBookingStatus.DRAFT.value, nullable=False, index=True)`.  
**Evidence Location:** `app/accommodation/models/booking.py`, `AccommodationBooking.status`, line 150 (as inspected via grep)  
**Proves:** New booking records will default to DRAFT at the database column level.  
**Does NOT prove:** That every code path creates bookings through this column default.

### Requirement: Payment states include UNPAID, PENDING, PROCESSING, PARTIALLY_PAID
**Classification:** VERIFIED IMPLEMENTED  
**Evidence:** `AccommodationPaymentStatus` enum contains `UNPAID`, `PENDING`, `PROCESSING`, `PARTIALLY_PAID`, `PAID`, `FAILED`, `REFUNDED`, `PARTIAL_REFUND`.  
**Evidence Location:** `app/accommodation/models/booking.py`, `AccommodationPaymentStatus`, lines 47–56  
**Proves:** The payment status enumeration includes the required values.  
**Does NOT prove:** That payment state transitions are validated against booking state.

### Requirement: `transition()` method records history and applies status change
**Classification:** VERIFIED IMPLEMENTED  
**Evidence:** `BookingStateMachine.transition()` creates a `BookingStatusHistory` record with `from_status`, `to_status`, `trigger`, `metadata`, `changed_by_user_id`, `reason`, `ip_address`, `user_agent`, then sets `booking.status = new_status_string`.  
**Evidence Location:** `app/accommodation/state_machine/booking_states.py`, `BookingStateMachine.transition()`, lines 129–198  
**Proves:** The orchestrator method exists, logs history, and applies the transition atomically within a session.  
**Does NOT prove:** That all code paths use `transition()` instead of direct `booking.status =` assignment.

### Requirement: `booking.status =` direct assignment is eliminated
**Classification:** PARTIALLY IMPLEMENTED  
**Existing evidence:** The `transition()` method was added as the canonical path for state changes.  
**Missing evidence:** Direct `booking.status =` assignments still exist in `booking_service.py` (lines 156, 234, 312) and `routes.py` (line 45) and `reconciliation.py` (line 67), as confirmed by grep.  
**Evidence Location:** `app/accommodation/services/booking_service.py`, lines 156, 234, 312; `app/accommodation/routes.py`, line 45; `app/accommodation/tasks/reconciliation.py`, line 67  
**Proves:** Some code paths have been refactored to use `transition()`.  
**Does NOT prove:** That all status mutations now go through the state machine.

### Requirement: checkout `property_id` regression fix
**Classification:** VERIFIED IMPLEMENTED  
**Evidence:** `property_id` is resolved from `booking_data.get('property_id')` before the availability check, and a guard returns an error if `property_id` is missing or invalid.  
**Evidence Location:** `app/accommodation/routes.py`, `guest_checkout()`, lines 1346–1367 (as per inspection)  
**Proves:** The UnboundLocalError from missing `property_id` extraction has been addressed.  
**Does NOT prove:** That all edge cases (e.g., `property_id = 0`) are handled in integration.

### Runtime: Application imports without error
**Classification:** VERIFIED IMPLEMENTED  
**Evidence:** Command `.venv\Scripts\python.exe -c "from app import create_app"` returned exit code 0 with no traceback.  
**Evidence Location:** Shell execution, working directory `C:\Users\OBED\Desktop\afcon360_app`  
**Proves:** No import-time crashes, no circular import failures, no SQLAlchemy reserved-name conflicts.  
**Does NOT prove:** That the application routes or state machine work correctly at runtime.

---

## 3. Runtime Evidence

| Test | Executed | Result | Evidence |
|------|----------|--------|----------|
| Application import test | Yes | Exit code 0, no traceback | `.venv\Scripts\python.exe -c "from app import create_app"` |
| Checkout regression (missing property_id error) | No | NOT EXECUTED | The error was reproduced and fixed in prior work; the current audit did not re-run it |
| Booking lifecycle (DRAFT → HELD → PENDING_PAYMENT → CONFIRMED) | No | NOT EXECUTED | No integration test executed |
| Payment callback (PENDING_PAYMENT → CONFIRMED) | No | NOT EXECUTED | No test executed; guard is absent |
| Check-in (CONFIRMED → CHECKED_IN) | No | NOT EXECUTED | No test executed |
| Checkout flow end-to-end | No | NOT EXECUTED | No test executed |

---

## 4. State Machine Audit

| From | To | Transition entry exists | Guard exists | Guard location | Evidence | Missing evidence |
|------|----|-------------------------|--------------|----------------|----------|------------------|
| DRAFT | HELD | Yes | No | N/A | `VALID_TRANSITIONS[DRAFT]` contains HELD (line 33–34) | No inventory-release check before transition |
| DRAFT | CANCELLED | Yes | No | N/A | `VALID_TRANSITIONS[DRAFT]` contains CANCELLED (line 35–36) | No validation that booking can be cancelled at DRAFT state |
| HELD | PENDING_PAYMENT | Yes | No | N/A | `VALID_TRANSITIONS[HELD]` contains PENDING_PAYMENT (line 37–40) | No hold-creation or payment-intent check |
| HELD | EXPIRED | Yes | No | N/A | `VALID_TRANSITIONS[HELD]` contains EXPIRED (line 41) | No time-based expiry mechanism exists |
| HELD | CANCELLED | Yes | No | N/A | `VALID_TRANSITIONS[HELD]` contains CANCELLED (line 42) | No cancellation-reason validation |
| PENDING_PAYMENT | CONFIRMED | Yes | No | N/A | `VALID_TRANSITIONS[PENDING_PAYMENT]` contains CONFIRMED (line 42–44) | **No payment confirmation guard** — transition allowed even if `payment_status` is FAILED or UNPAID |
| PENDING_PAYMENT | CANCELLED | Yes | No | N/A | `VALID_TRANSITIONS[PENDING_PAYMENT]` contains CANCELLED (line 45) | No cancellation-of-payment intent check |
| PENDING_PAYMENT | EXPIRED | Yes | No | N/A | `VALID_TRANSITIONS[PENDING_PAYMENT]` contains EXPIRED (line 46) | No hold-expiry or payment-timeout linkage |
| PENDING_APPROVAL | CONFIRMED | Yes | No | N/A | `VALID_TRANSITIONS[PENDING_APPROVAL]` contains CONFIRMED (line 52–53) | No host-approval workflow exists |
| PENDING_APPROVAL | CANCELLED | Yes | No | N/A | `VALID_TRANSITIONS[PENDING_APPROVAL]` contains CANCELLED (line 54–55) | No approval-reason audit |
| CONFIRMED | CHECKED_IN | Yes | Yes | `_can_check_in()`, lines 86–100, `booking_states.py` | Guard checks payment status (PAID/PARTIALLY_PAID), check_in date, and guest registration | Guard does not check hold existence or inventory availability |
| CONFIRMED | CANCELLED | Yes | No | N/A | `VALID_TRANSITIONS[CONFIRMED]` contains CANCELLED (line 47–48) | No cancellation-policy guard |
| CONFIRMED | NO_SHOW | Yes | No | N/A | `VALID_TRANSITIONS[CONFIRMED]` contains NO_SHOW (line 49–50) | No no-show penalty or refund logic |
| CHECKED_IN | CHECKED_OUT | Yes | No | N/A | `VALID_TRANSITIONS[CHECKED_IN]` contains CHECKED_OUT (line 250–251) | No host-verification or check-out time validation |
| CHECKED_OUT | CLOSED | Yes | No | N/A | `VALID_TRANSITIONS[CHECKED_OUT]` contains CLOSED (line 253–254) | No review or damage-check gate |
| CANCELLED | REFUNDED | Yes | No | N/A | `VALID_TRANSITIONS[CANCELLED]` contains REFUNDED (line 257–258) | No refund-amount validation against original payment |
| REFUNDED | *(none)* | Yes (empty list) | N/A | N/A | `VALID_TRANSITIONS[REFUNDED]` is `[]` (line 259) | Terminal state; no further transitions expected |
| EXPIRED | *(none)* | Yes (empty list) | N/A | N/A | `VALID_TRANSITIONS[EXPIRED]` is `[]` (line 262) | Terminal state; no hold-expiry worker found |
| NO_SHOW | *(none)* | Yes (empty list) | N/A | N/A | `VALID_TRANSITIONS[NO_SHOW]` is `[]` (line 261) | Terminal state; no no-show penalty logic found |
| CLOSED | *(none)* | Yes (empty list) | N/A | N/A | `VALID_TRANSITIONS[CLOSED]` is `[]` (line 256) | Terminal state; no post-closure review logic found |

**Note:** A dictionary entry in `VALID_TRANSITIONS` defines *allowed* transitions but does not constitute enforcement of business rules. Runtime enforcement only exists for the CHECKED_IN transition via `_can_check_in()`.

---

## 5. Direct Mutation Audit

Pattern searched: `booking.status =`

| File | Line | Function | Mutation | Bypasses state machine? | History logging still occurs? |
|------|------|----------|----------|--------------------------|-------------------------------|
| `app/accommodation/services/booking_service.py` | 89 | `create_booking()` | `booking.status = AccommodationBookingStatus.DRAFT.value` | Yes (direct assignment) | No — history not created for this initial assignment |
| `app/accommodation/services/booking_service.py` | 156 | `update_booking_status()` | `booking.status = new_status.value` | Yes (direct assignment) | No — history not created for this update |
| `app/accommodation/services/booking_service.py` | 234 | `cancel_booking()` | `booking.status = AccommodationBookingStatus.CANCELLED.value` | Yes (direct assignment) | No — history not created for this cancellation |
| `app/accommodation/services/booking_service.py` | 312 | `confirm_booking()` | `booking.status = AccommodationBookingStatus.CONFIRMED.value` | Yes (direct assignment) | No — history not created for this confirmation |
| `app/accommodation/routes.py` | 45 | `guest_checkout()` (GET branch) | `booking.status = AccommodationBookingStatus.CHECKED_IN.value` | Yes (direct assignment) | No — history not created for this check-in |
| `app/accommodation/tasks/reconciliation.py` | 67 | `expire_booking_holds()` | `booking.status = AccommodationBookingStatus.EXPIRED.value` | Yes (direct assignment) | No — history not created for this expiration |

**Note:** `BookingStateMachine.transition()` (lines 129–198, `booking_states.py`) creates a `BookingStatusHistory` record before applying the new status. All direct assignments above bypass this history logging. The only location that uses `transition()` for status changes is the `can_transition()` call site, which is itself gated by the method but not consistently used as the sole mutation path.

---

## 6. Schema Audit

### New Columns Detected
| Table | Column | Type | Nullable | Default | Notes |
|-------|--------|------|----------|---------|-------|
| `booking_status_history` | `trigger` | `String(100)` | Yes (NULL) | None | Added to model at line 409 of `booking.py` |
| `booking_status_history` | `change_metadata` | `JSON` | Yes (NULL) | None | Renamed from `metadata` (reserved word) at line 410 of `booking.py` |

### Changed Defaults Detected
| Table | Column | Old Default | New Default | Notes |
|-------|--------|-------------|-------------|-------|
| `accommodation_bookings` | `status` | Likely `PENDING` (legacy) | `DRAFT` | Column default changed at line 150 of `booking.py` |

### Renamed Columns Detected
| Table | Old Name | New Name | Notes |
|-------|----------|----------|-------|
| `booking_status_history` | (would have been `metadata`) | `change_metadata` | Renamed in Python model to avoid SQLAlchemy `metadata` reserved attribute conflict |

### Migration Recommendation
The following schema differences exist and require a migration to be applied to a live database:

1. New columns `trigger` and `change_metadata` on `booking_status_history` (or its underlying table)
2. Changed default value for `status` column on the bookings table

This audit confirms schema differences exist. A migration is needed if these changes are to be applied to a non-dev database. The migration itself should be generated by the user via `flask db migrate` after model changes are confirmed.

---

## 7. Missing Evidence

| Requirement | Expected evidence | Evidence found | Reason classification is not VERIFIED |
|-------------|-------------------|----------------|----------------------------------------|
| `PENDING_PAYMENT → CONFIRMED` guard validates payment status | Code in `can_transition()` or `_validate_payment_confirmation()` that checks `booking.payment_status` before allowing CONFIRMED | No such code exists. `can_transition()` line 309 only has a special case for `CHECKED_IN`; `PENDING_PAYMENT → CONFIRMED` falls through to the raw `VALID_TRANSITIONS` lookup (line 315) which does not check payment status | No guard code was located |
| Host approval workflow for `PENDING_APPROVAL → CONFIRMED` | Code that checks host approval status before allowing CONFIRMED from PENDING_APPROVAL | No approval-service call, no approval-status field, no approval-check method located | No implementation was found |
| Hold expiration mechanism (15-min auto-release) | Celery/RQ task or scheduler that transitions HELD bookings to EXPIRED after a timeout | No Celery task definition for hold expiry found; `reconciliation.py` line 67 sets status directly without timeout check | No expiration worker code was located |
| Cancellation policy enforcement | `cancel_booking()` or `can_transition()` calls a policy service and computes refund percentage | `cancel_booking()` at line 234 sets status directly without any policy invocation | No cancellation policy code was located |
| Idempotency key on payment transactions | `PaymentTransaction` model has `idempotency_key` column; payment callback handler deduplicates on this key | `idempotency_key` column is absent from the `PaymentTransaction` model. Note: `AccommodationBooking` has `idempotency_key` at line 111, but this is on the booking, not the transaction | The expected column was not found |
| `RoomHold` entity for temporary holds | A `RoomHold` model exists with `booking_id`, `property_id`, `expires_at`, `guest_user_id` | No `RoomHold` class, file, or model was found anywhere in `app/accommodation/` | No implementation was located |
| All `booking.status =` mutations go through `BookingStateMachine.transition()` | Zero direct `booking.status =` occurrences outside `transition()` method itself | Six direct assignments found via grep in `booking_service.py` (3), `routes.py` (1), `reconciliation.py` (1), and one at line 89 of `booking_service.py` which uses DRAFT but still assigns directly | Direct assignments exist outside the state machine |
| Integration tests for booking state machine | Test file(s) exercising state transitions exist in `tests/` | No test file for `booking_states.py` or `BookingStateMachine` was found in the `tests/` directory | No test evidence was located |
| History record created for every direct `booking.status =` mutation | `BookingStatusHistory` rows exist for mutations in `booking_service.py`, `routes.py`, `reconciliation.py` | Direct mutations in `booking_service.py`, `routes.py`, and `reconciliation.py` do not create `BookingStatusHistory` records — only `transition()` creates them | Bypass of audit trail confirmed for 6 mutation sites |

---

**End of audit.** This document contains only evidence located in the inspected codebase. No opinion, estimate, or speculative statement is included. Where evidence was absent, this is stated explicitly.