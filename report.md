# AFCON360 Accommodation Booking System - Engineering Audit

**Target:** `Implement/booking_flow.md`  
**Auditor Role:** Independent Engineering Auditor  
**Date:** 2026-07-31  
**Codebase Root:** `/workspace/afcon360`  
**Result:** PARTIAL IMPLEMENTATION. The accommodation booking flow contains several required pieces, but the state machine is incomplete/unsafe, room holds are not a separate entity, checkout is not the specified 4-step wizard, pricing omits taxes/discounts, and direct status mutations still bypass audit/history.

---

## 1. Verified Evidence

### Requirement: Stored booking states include the specified lifecycle states except READY_FOR_CHECKIN
**Classification:** ✅ VERIFIED IMPLEMENTED for stored enum values; ⚠️ PARTIAL against the full state model because `READY_FOR_CHECKIN` is computed and not an enum value.

**Evidence:** `AccommodationBookingStatus` defines `DRAFT`, `HELD`, `PENDING_PAYMENT`, `PENDING_APPROVAL`, `CONFIRMED`, `CHECKED_IN`, `CHECKED_OUT`, `CLOSED`, `CANCELLED`, `NO_SHOW`, `EXPIRED`, and `REFUNDED` as string-backed Python enum values. It also carries legacy `PENDING` and `PAYMENT_PARTIAL` values.

**Evidence Location:** `app/accommodation/models/booking.py`, lines 26-44.

**Code Snippet:**
```python
class AccommodationBookingStatus(enum.Enum):
    DRAFT = "draft"
    HELD = "held"
    PENDING_PAYMENT = "pending_payment"
    PENDING_APPROVAL = "pending_approval"
    CONFIRMED = "confirmed"
    CHECKED_IN = "checked_in"
    CHECKED_OUT = "checked_out"
    CLOSED = "closed"
    CANCELLED = "cancelled"
    NO_SHOW = "no_show"
    EXPIRED = "expired"
    REFUNDED = "refunded"
```

**Proves:** The booking table can store 12 of the 13 named lifecycle states from the specification; `READY_FOR_CHECKIN` is intentionally not stored.

**Does NOT prove:** The state machine can transition through all of those states. It cannot: `CHECKED_IN`, `CHECKED_OUT`, `CLOSED`, `CANCELLED`, `REFUNDED`, `EXPIRED`, and `NO_SHOW` are not all represented as keys in `VALID_TRANSITIONS`.

---

### Requirement: `READY_FOR_CHECKIN` is computed, not stored
**Classification:** ✅ VERIFIED IMPLEMENTED.

**Evidence:** `AccommodationBooking.is_ready_for_checkin` is a property, not a column. It derives readiness from confirmed status, paid/partial payment, check-in date, and required guest registration.

**Evidence Location:** `app/accommodation/models/booking.py`, lines 305-319.

**Code Snippet:**
```python
@property
def is_ready_for_checkin(self) -> bool:
    return (
        self.status == AccommodationBookingStatus.CONFIRMED.value
        and self.payment_status_enum in [
            AccommodationPaymentStatus.PAID,
            AccommodationPaymentStatus.PARTIALLY_PAID,
        ]
        and self.check_in <= date.today()
        and self.all_required_guests_registered
    )
```

**Proves:** The computed property exists and evaluates status, payment, date, and guest-registration prerequisites.

**Does NOT prove:** Routes/services consistently use this property before check-in. `BookingService.check_in()` directly changes `booking.status` to checked-in before calling the state machine.

---

### Requirement: Booking default status is DRAFT
**Classification:** ✅ VERIFIED IMPLEMENTED.

**Evidence:** The `AccommodationBooking.status` column has default `AccommodationBookingStatus.DRAFT.value`.

**Evidence Location:** `app/accommodation/models/booking.py`, lines 161-163.

**Code Snippet:**
```python
status = Column(String(50), default=AccommodationBookingStatus.DRAFT.value, nullable=False, index=True)
```

**Proves:** ORM-created bookings with no explicit status default to `draft`.

**Does NOT prove:** Runtime booking creation uses DRAFT. `BookingService.create_booking()` supplies an explicit `initial_status` instead of relying on the default.

---

### Requirement: Payment states include unpaid/pending/processing/partial/paid/refund/failure values
**Classification:** ✅ VERIFIED IMPLEMENTED.

**Evidence:** `AccommodationPaymentStatus` defines `UNPAID`, `PENDING`, `PROCESSING`, `PAID`, `PARTIALLY_PAID`, `FAILED`, `REFUNDED`, and `PARTIAL_REFUND`.

**Evidence Location:** `app/accommodation/models/booking.py`, lines 47-56.

**Code Snippet:**
```python
class AccommodationPaymentStatus(enum.Enum):
    UNPAID = "unpaid"
    PENDING = "pending"
    PROCESSING = "processing"
    PAID = "paid"
    PARTIALLY_PAID = "partially_paid"
    FAILED = "failed"
    REFUNDED = "refunded"
    PARTIAL_REFUND = "partial_refund"
```

**Proves:** Required payment status names can be stored.

**Does NOT prove:** Payment callbacks are idempotent or that payment status guards state transitions.

---

### Requirement: Status history model has trigger and metadata context
**Classification:** ✅ VERIFIED IMPLEMENTED for columns; ❌ BROKEN in state-machine usage.

**Evidence:** `BookingStatusHistory` has `trigger` and `change_metadata` columns.

**Evidence Location:** `app/accommodation/models/booking.py`, lines 400-410.

**Code Snippet:**
```python
class BookingStatusHistory(BaseModel):
    __tablename__ = 'accommodation_booking_status_history'
    booking_id = Column(BigInteger, ForeignKey('accommodation_bookings.id'), nullable=False)
    from_status = Column(String(50), nullable=True)
    to_status = Column(String(50), nullable=False)
    changed_at = Column(DateTime, default=func.now(), nullable=False)
    changed_by = Column(BigInteger, nullable=True)
    trigger = Column(String(100), nullable=True)
    change_metadata = Column(JSON, nullable=True)
```

**Proves:** The history table can store trigger and structured transition context.

**Does NOT prove:** `BookingStateMachine.transition()` correctly writes those fields. It passes invalid constructor keyword arguments (`changed_by_user_id`, `reason`, `ip_address`, `user_agent`, and `metadata`) that are not mapped on `BookingStatusHistory`; it should pass `changed_by` and `change_metadata` and either add missing columns or stop passing non-existent fields.

---

### Requirement: A state-machine transition method exists and validates at least some transitions
**Classification:** ⚠️ PARTIAL.

**Evidence:** `BookingStateMachine.can_transition()` special-cases check-in readiness and otherwise checks `VALID_TRANSITIONS`; `transition()` calls `can_transition()`, creates a history object, and applies the new status.

**Evidence Location:** `app/accommodation/state_machine/booking_states.py`, lines 64-84 and 129-188.

**Code Snippet:**
```python
if new_status == AccommodationBookingStatus.CHECKED_IN:
    current_enum = AccommodationBookingStatus(booking.status)
    return (
        current_enum == AccommodationBookingStatus.CONFIRMED
        and cls._can_check_in(booking)
    )
...
history = BookingStatusHistory(...)
db.session.add(history)
booking.status = new_status_string
```

**Proves:** A centralized state-machine API exists and includes a check-in guard.

**Does NOT prove:** All required transitions are present or correct. `VALID_TRANSITIONS` omits `CHECKED_IN -> CHECKED_OUT`, `CHECKED_OUT -> CLOSED`, `CANCELLED -> REFUNDED`, and terminal keys for `CLOSED`, `REFUNDED`, `EXPIRED`, and `NO_SHOW`. The `transition()` method also appears runtime-broken because it constructs `BookingStatusHistory` with unmapped keyword arguments.

---

### Requirement: Host approval workflow fields and service path exist
**Classification:** ⚠️ PARTIAL.

**Evidence:** Booking rows include host approval/rejection fields, and `BookingService.approve_booking()` transitions `PENDING_APPROVAL` to `CONFIRMED` after setting approval metadata.

**Evidence Location:** `app/accommodation/models/booking.py`, lines 168-176; `app/accommodation/services/booking_service.py`, lines 712-727.

**Code Snippet:**
```python
booking.approved_by_user_id = approved_by_user_id
booking.approval_reason = reason
booking.host_approved_at = datetime.now(timezone.utc)
BookingStateMachine.transition(
    booking,
    AccommodationBookingStatus.CONFIRMED,
    changed_by_user_id=approved_by_user_id,
    reason=reason or "Approved by host",
)
```

**Proves:** There is a host approval service path.

**Does NOT prove:** The route layer always uses it. Checkout sets `booking.status = PENDING_APPROVAL` directly for pay-on-arrival/invoice bookings, bypassing the state machine/history.

---

### Requirement: Availability supports temporary hold reason and release
**Classification:** ⚠️ PARTIAL; not the specified RoomHold entity.

**Evidence:** `AccommodationBlockedReason` includes `TEMPORARY_HOLD`; `AvailabilityService.create_hold()` calculates a 15-minute `expires_at` and blocks dates with `temporary_hold`; `release_hold()` delegates to `unblock_dates()` filtered by that reason.

**Evidence Location:** `app/accommodation/models/availability.py`, lines 24-32; `app/accommodation/services/availability_service.py`, lines 388-429 and 437-536.

**Code Snippet:**
```python
expires_at = datetime.now(timezone.utc) + timedelta(minutes=hold_minutes)
blocked_count = AvailabilityService.block_dates(
    property_id=property_id,
    check_in=check_in,
    check_out=check_out,
    reason=AccommodationBlockedReason.TEMPORARY_HOLD,
    created_by=created_by,
    expires_at=expires_at
)
```

**Proves:** There is an attempt to model holds through `BlockedDate` records.

**Does NOT prove:** The specification's separate `RoomHold` entity exists. `BlockedDate` has no `expires_at` column, and `block_dates()` accepts but does not persist `expires_at`, so automatic hold expiration cannot be driven from these records.

---

### Requirement: Pricing engine calculates a breakdown
**Classification:** ⚠️ PARTIAL.

**Evidence:** `PricingService.calculate_total()` calculates nights, nightly rate, subtotal, cleaning fee, service fee, and total.

**Evidence Location:** `app/accommodation/services/pricing_service.py`, lines 22-77.

**Code Snippet:**
```python
subtotal = nightly_rate * nights
service_fee = subtotal * (service_fee_pct / Decimal('100'))
total = subtotal + cleaning_fee + service_fee
return {
    'nightly_rate': nightly_rate,
    'nights': nights,
    'subtotal': subtotal,
    'cleaning_fee': cleaning_fee,
    'service_fee': service_fee,
    'total': total
}
```

**Proves:** Base price, cleaning fee, service fee, and total are calculated.

**Does NOT prove:** Taxes, promo discounts, loyalty points, wallet credits, multi-room quantity, or line-item tax breakdowns are implemented in this pricing service.

---

### Requirement: Cancellation refund calculation exists
**Classification:** ⚠️ PARTIAL.

**Evidence:** `PricingService.calculate_refund()` calculates flexible/moderate/strict/super-strict refund amounts based on days before check-in.

**Evidence Location:** `app/accommodation/services/pricing_service.py`, lines 80-154.

**Code Snippet:**
```python
days_until_checkin = (booking.check_in - cancellation_date).days
policy = booking.accommodation_property.cancellation_policy
if policy == "moderate":
    if days_until_checkin >= 5:
        return {'refund_amount': booking.total_amount, ...}
    elif days_until_checkin >= 1:
        refund = booking.total_amount * Decimal('0.5')
```

**Proves:** Policy-based refund math exists.

**Does NOT prove:** All cancellation paths call it. The host cancellation route directly mutates `booking.status` and does not compute refund.

---

### Requirement: Checkout route has property_id guard and payment idempotency key generation
**Classification:** ✅ VERIFIED IMPLEMENTED for those two claims.

**Evidence:** `guest_checkout()` normalizes and validates `property_id` before availability checks. It also computes a deterministic SHA-256 `idempotency_key` for booking creation and payment processor calls.

**Evidence Location:** `app/accommodation/routes.py`, lines 1301-1367 and 1737-1805.

**Code Snippet:**
```python
property_id = booking_data.get('property_id')
if not isinstance(property_id, int) or property_id <= 0:
    flash('Invalid booking data. Please start again.', 'danger')
    session.pop('pending_booking', None)
    return redirect(url_for('accommodation.guest_search'))
...
idempotency_key = hashlib.sha256(
    json.dumps(idempotency_data, sort_keys=True).encode()
).hexdigest()
```

**Proves:** The checkout regression guard and booking/payment idempotency-key generation exist.

**Does NOT prove:** Payment callbacks deduplicate by idempotency key. No `idempotency_key` column exists on `AccommodationBookingPayment`.

---

## 2. Errors Found

| Severity | File / Lines | Error | Impact | Suggested Fix |
|---|---|---|---|---|
| P0 | `app/accommodation/state_machine/booking_states.py`, 174-184 vs `app/accommodation/models/booking.py`, 400-410 | `BookingStateMachine.transition()` constructs `BookingStatusHistory` with unmapped fields: `changed_by_user_id`, `reason`, `ip_address`, `user_agent`, and `metadata`. The model has `changed_by`, `trigger`, and `change_metadata` only. | Any call to `transition()` can fail at runtime with invalid keyword errors, preventing state changes and history creation. | Align constructor args with model columns (`changed_by`, `change_metadata`) and add missing audit columns if required by spec. |
| P0 | `app/accommodation/state_machine/booking_states.py`, 32-62 | `VALID_TRANSITIONS` lacks `CHECKED_IN -> CHECKED_OUT`, `CHECKED_OUT -> CLOSED`, `CANCELLED -> REFUNDED`, and terminal keys for `CLOSED`, `REFUNDED`, `EXPIRED`, `NO_SHOW`. | Checkout/closure/refund transitions cannot be validated by the state machine. Service code that calls `transition(CHECKED_OUT)` after direct mutation is especially unsafe. | Complete the transition matrix from the specification and add tests for every allowed and disallowed transition. |
| P0 | `app/accommodation/services/booking_service.py`, 497-508 and 536-557 | `check_in()` and `check_out()` directly set `booking.status` before calling `BookingStateMachine.transition()`. | The direct mutation bypasses the intended guard and changes the current state, so `transition()` validates from the wrong state and may reject or create incorrect history. | Call `BookingStateMachine.transition()` before mutating status; remove direct assignments. |
| P0 | `app/accommodation/routes.py`, 1910-1911 and 3412-3417 | Routes directly set statuses to `PENDING_APPROVAL` and `CANCELLED`. | Route-level status changes bypass transition validation and status history. | Replace direct mutations with `BookingStateMachine.transition()` or service methods. |
| P0 | `app/accommodation/services/availability_service.py`, 343-419 vs `app/accommodation/models/availability.py`, 38-78 | `create_hold()` computes `expires_at`, but `BlockedDate` has no `expires_at` field and `block_dates()` does not persist it. | Temporary holds cannot expire automatically through `BlockedDate`; overbooking prevention is incomplete. | Implement the separate `RoomHold` model/service from the spec or add persisted expiration metadata and cleanup. |
| P1 | `app/accommodation/services/pricing_service.py`, 61-77 | Pricing total excludes taxes and discounts even though the booking model has a `taxes` column and the spec requires city tax/VAT and discounts. | Displayed/charged totals may not match required price breakdown. | Add tax and discount calculation inputs/outputs and persist snapshots. |
| P1 | `templates/accommodation/guest/checkout.html`, 30-293 | The checkout UI is a single long form with numbered sections 1-7, not the specified 4-step wizard. It also includes inline layout styles at lines 23, 60, and 85. | UX does not match the specification and violates frontend standards forbidding inline styles on layout containers. | Redesign as a persisted 4-step wizard and move inline display/background styles to CSS. |
| P1 | `app/accommodation/models/booking_payment.py`, 40-70 | Payment event table has no `idempotency_key` column. | Payment callback deduplication cannot be verified at the accommodation payment-event layer. | Add idempotency-key handling in the canonical payment/wallet callback path and expose accommodation-level evidence. |
| P2 | `app/accommodation/services/booking_service.py`, 921-924 | Host policy violation check runs after the booking has already transitioned to cancelled, but then tests whether status is confirmed/checked-in. | The violation branch is effectively unreachable for confirmed bookings after transition. | Capture `old_status` before transition and evaluate policy violation against that value. |
| P2 | `app/accommodation/services/booking_service.py`, 995 | `filter_by(status=AccommodationBookingStatus(status))` passes an enum object for a string column. | Status filtering may return no rows or produce inconsistent behavior. | Use `.filter_by(status=AccommodationBookingStatus(status).value)`. |

---

## 3. Not Implemented

| Specification Reference | Requirement | Status | Impact |
|---|---|---|---|
| Business Rule BR-002; Section 6 RoomHold | Separate `RoomHold` entity with `booking_id`, `property_id`, room/room-type, `expires_at`, and lifecycle cleanup. | ❌ MISSING | Holds are represented as `BlockedDate` rows without persisted expiration, so 15-minute release is not reliable. |
| State model / Critical Checks | Complete transition matrix for DRAFT, HELD, PENDING_PAYMENT, PENDING_APPROVAL, CONFIRMED, READY_FOR_CHECKIN, CHECKED_IN, CHECKED_OUT, CLOSED, CANCELLED, NO_SHOW, EXPIRED, REFUNDED. | ⚠️ PARTIAL | Several required transitions and terminal states are absent from `VALID_TRANSITIONS`. |
| State model / Guards | Guards for payment confirmation, host approval, cancellation policy, hold expiry, no-show, checkout, closure, and refund. | ⚠️ PARTIAL | Only check-in readiness is guarded centrally; other transitions rely on scattered service logic or no guard. |
| Audit Trail | Every state change creates `BookingStatusHistory` with `trigger` and `change_metadata`. | ❌ MISSING/BROKEN | Direct mutations bypass history; transition history constructor is misaligned with the model. |
| Phase 6 Pricing | Taxes, city tax/VAT, service fee, cleaning fee, discounts, promo, loyalty, wallet credit. | ⚠️ PARTIAL | Current pricing omits taxes and discounts. |
| Phase 7 Checkout | Wizard with exactly 4 steps: Guest Details → Special Requests → Payment → Review & Confirm; data persists between steps; validation each step. | ❌ MISSING | Current checkout is a single form with 7 displayed sections and no wizard persistence. |
| BR-004 Payment Timing | Pay now, deposit, and pay on arrival workflows integrated with booking states and confirmation rules. | ⚠️ PARTIAL | UI/service paths exist, but pay-on-arrival is direct `PENDING_APPROVAL`; payment guard for confirmation is absent from state machine. |
| BR-005 Cancellation | Cancellation policy determines refund amount on every cancellation path. | ⚠️ PARTIAL | Refund calculator exists, but direct host route cancellation does not use it. |
| Idempotency | Payment callbacks deduplicate with an `idempotency_key`. | ⚠️ PARTIAL | Booking/processor key generation exists, but accommodation payment events lack `idempotency_key` and callback dedupe evidence was not found. |
| Tests | Automated tests for booking state machine, hold expiry, pricing, checkout, and idempotency. | ❌ MISSING | No direct accommodation booking-flow tests were located during this audit. |

---

## 4. Recommendations

### P0 - Must fix before release
1. **Repair `BookingStateMachine.transition()` history creation** so it uses real `BookingStatusHistory` fields and can execute successfully.
2. **Complete `VALID_TRANSITIONS`** exactly per `Implement/booking_flow.md`, including `CHECKED_IN -> CHECKED_OUT`, `CHECKED_OUT -> CLOSED`, `CANCELLED -> REFUNDED`, and terminal states.
3. **Remove all direct `booking.status = ...` mutations outside the state machine**, especially in `BookingService.check_in()`, `BookingService.check_out()`, checkout route, and host cancellation route.
4. **Implement a real hold-expiration model/process**: preferably the specified `RoomHold` entity plus a scheduled cleanup/release job.

### P1 - High priority
1. Add guards for `PENDING_PAYMENT -> CONFIRMED`, `PENDING_APPROVAL -> CONFIRMED`, cancellation, refund, no-show, checkout, and closure.
2. Extend pricing to include taxes and discount line items and ensure booking snapshots persist the same breakdown shown to guests.
3. Replace the current single-page checkout form with the specified 4-step wizard and step-level validation.
4. Add accommodation booking-flow tests covering every valid/invalid transition and audit-history side effect.

### P2 - Medium priority
1. Fix host policy-violation detection by capturing pre-cancellation status before transition.
2. Fix status filtering to compare string status values, not enum objects.
3. Move inline checkout template styles into `static/css/modules/accommodation/checkout.css` and update `static/MOBILE_OPTIMIZATION.md` if frontend files are changed.

### P3 - Lower priority
1. Add explicit evidence/logging around notification delivery, analytics updates, and guest registration reminders.
2. Document the rollback plan for any schema changes needed to support status-history audit columns and RoomHold.

---

## 5. Updated Verification Matrix

| Critical Check | Final Status | Evidence Summary |
|---|---:|---|
| All 13 states exist in `AccommodationBookingStatus` enum | ⚠️ PARTIAL | 12 stored enum states exist; `READY_FOR_CHECKIN` is computed, not stored. |
| All transitions from `booking_flow.md` exist in `VALID_TRANSITIONS` | ❌ MISSING | Transition matrix omits several required transitions and terminal keys. |
| READY_FOR_CHECKIN is computed, not stored | ✅ IMPLEMENTED | `is_ready_for_checkin` property derives readiness. |
| `transition()` method creates history records | ❌ BROKEN | Method attempts history creation but uses unmapped constructor fields. |
| `trigger` field exists in `BookingStatusHistory` | ✅ IMPLEMENTED | `trigger = Column(String(100))`. |
| `change_metadata` field exists | ✅ IMPLEMENTED | `change_metadata = Column(JSON)`. |
| Every state change creates a history record | ❌ MISSING | Direct route/service mutations bypass history. |
| Direct `booking.status =` assignments eliminated | ❌ MISSING | Multiple direct assignments remain. |
| RoomHold model exists as separate entity | ❌ MISSING | No `RoomHold` class found; temporary holds use `BlockedDate`. |
| 15-minute expiration is implemented | ⚠️ PARTIAL | 15-minute value is calculated but not persisted on `BlockedDate`. |
| Expired holds release inventory | ❌ MISSING | No reliable persisted hold expiry release path verified. |
| Pricing calculates base price | ✅ IMPLEMENTED | Subtotal = nightly rate × nights. |
| Pricing calculates taxes | ❌ MISSING | No tax calculation in `PricingService.calculate_total()`. |
| Pricing calculates service fee | ✅ IMPLEMENTED | Service fee percentage applied to subtotal. |
| Pricing calculates cleaning fee | ✅ IMPLEMENTED | Cleaning fee included. |
| Pricing applies promo/loyalty/wallet discounts | ❌ MISSING | No discount inputs/outputs in pricing service. |
| Checkout has 4 wizard steps | ❌ MISSING | Template is a single form with seven numbered sections. |
| Checkout data persists between steps | ❌ MISSING | No multi-step persistence verified. |
| Checkout validates each step | ❌ MISSING | No step-specific validation verified. |
| Cancellation calculates refund based on days before check-in | ⚠️ PARTIAL | Refund calculator exists but not used by all cancellation paths. |
| `idempotency_key` on payment transactions/callbacks | ⚠️ PARTIAL | Booking key and processor key exist; accommodation payment event has no key and callback dedupe was not verified. |

---

## 6. Commands Run

```bash
find .. -name AGENTS.md -print
sed -n '1,520p' Implement/booking_flow.md
sed -n '1,520p' report.md
find app/accommodation -path '*/__pycache__' -prune -o -type f | sort
rg -n "booking\.status\s*=|RoomHold|temporary_hold|expires_at|idempotency_key|checkout|guest_checkout|BookingStateMachine|calculate_total|calculate_refund|tax|discount|promo|wizard|step" app/accommodation tests report.md Implement/booking_flow.md
nl -ba app/accommodation/models/booking.py | sed -n '1,460p'
nl -ba app/accommodation/state_machine/booking_states.py | sed -n '26,205p'
nl -ba app/accommodation/services/booking_service.py | sed -n '30,120p;130,180p;220,245p;300,335p;470,560p;580,610p;650,675p;710,730p;790,815p;900,945p;990,1020p'
nl -ba app/accommodation/routes.py | sed -n '1283,1410p;1728,1812p;1888,1920p;3398,3420p'
nl -ba app/accommodation/services/availability_service.py | sed -n '330,440p;500,555p'
nl -ba app/accommodation/models/availability.py | sed -n '1,148p'
nl -ba app/accommodation/services/pricing_service.py | sed -n '1,154p'
nl -ba app/accommodation/models/booking_payment.py | sed -n '1,220p'
nl -ba templates/accommodation/guest/checkout.html | sed -n '1,360p'
python -m py_compile app/accommodation/models/booking.py app/accommodation/state_machine/booking_states.py app/accommodation/services/booking_service.py app/accommodation/routes.py app/accommodation/services/availability_service.py app/accommodation/services/pricing_service.py app/accommodation/models/availability.py
```

**Note:** A deeper runtime import check could not be completed because the environment lacks Flask (`ModuleNotFoundError: No module named 'flask'`). `py_compile` completed before that attempted import failed.

---

## 7. Production Hardening Update - 2026-07-31

The follow-up implementation addressed the highest-risk audit findings while preserving the repository rule that migration files are generated by the user, not by the agent.

### Implemented Hardening

| Area | Status | Evidence |
|---|---:|---|
| State transition matrix | ✅ HARDENED | `BookingStateMachine.VALID_TRANSITIONS` now includes stored lifecycle paths for `DRAFT`, `HELD`, `PENDING_PAYMENT`, `PENDING_APPROVAL`, `CONFIRMED`, `CHECKED_IN`, `CHECKED_OUT`, `CANCELLED`, and terminal `CLOSED`, `REFUNDED`, `EXPIRED`, `NO_SHOW`. |
| State guards | ✅ HARDENED | `can_transition()` now validates allowed transitions first, keeps `CHECKED_IN` behind readiness checks, requires payment satisfaction for payment confirmation, requires host approval markers for approval confirmation, and requires refund data before `REFUNDED`. |
| Audit history constructor | ✅ HARDENED | `transition()` now writes to actual mapped fields: `changed_by`, `trigger`, and `change_metadata`. |
| Direct booking status mutation | ✅ HARDENED | Booking service check-in/check-out, checkout pending approval, model confirm/cancel helpers, and host cancellation now route through `BookingStateMachine.transition()`. |
| Host cancellation | ✅ HARDENED | Host route delegates to `BookingService.cancel_booking()` so cancellation policy/refund logic and audit history are applied. |
| RoomHold | ✅ ADDED | Added `RoomHold` model with 15-minute default hold metadata, active/released/expired/converted statuses, and expiry indexes/checks. |
| Hold expiration | ✅ ADDED | `AvailabilityService.expire_room_holds()` expires active holds and releases temporary blocked inventory. |
| Pricing breakdown | ✅ HARDENED | `PricingService.calculate_total()` now includes room quantity, taxes, gross total, promo discount, loyalty discount, wallet credit, discount total, and final total. |
| Booking pricing snapshot | ✅ HARDENED | Booking creation now persists calculated `taxes` alongside nightly rate, cleaning fee, service fee, and total. |
| Status filtering bug | ✅ FIXED | Property booking status filters now compare string column values instead of enum objects. |
| Host policy violation bug | ✅ FIXED | Cancellation captures the pre-transition status before deciding whether a host cancellation should record a policy violation. |

### Migration Needed

Yes. The hardening adds the new `accommodation_room_holds` model/table. Per repository policy, no migration file was generated or edited automatically. The user should generate and review the migration manually:

```bash
flask db migrate -m "add accommodation room holds"
flask db upgrade
```

### Remaining Work

| Priority | Remaining Item | Notes |
|---|---|---|
| P0 | Automated tests | Add state-machine, RoomHold expiry, cancellation/refund, and pricing tests. |
| P1 | Checkout wizard | The checkout UI still needs the exact 4-step wizard: Guest Details → Special Requests → Payment → Review & Confirm. |
| P1 | Payment callback idempotency proof | Booking and processor idempotency exist, but payment callback deduplication should be tested and documented end-to-end. |
| P2 | Operational scheduler | Wire `AvailabilityService.expire_room_holds()` into Celery/beat or the project's scheduled task runner. |
