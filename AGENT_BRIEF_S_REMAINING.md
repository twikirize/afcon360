# AGENT BRIEF — Transport module, remaining S-items

## Your role

You are fixing a bounded list of service-layer bugs in the AFCON360
transport module. Each item below has: the file, the verified problem,
the exact change, and the test that proves it.

## Ground rules (read before starting)

1. **Work one item at a time.** After each, run its test. If the test
   fails, STOP and report — do not move to the next item.
2. **Do not create files.** Every fix is an in-place edit.
3. **Do not touch the database schema.** No migrations. No new columns.
   No dropped constraints. (Constitution §20.)
4. **Do not touch the accommodation, event, or wallet modules.**
   Transport only. Cross-module state needs an explicit contract (§17).
5. **Do not touch `app/transport/models.py`.** M-items are out of scope.
6. **Do not change function signatures** unless the item explicitly says to.
7. **Do not expose internal `id` in APIs/URLs** (§12.1). Prefer `public_id`
   / `booking_reference` in user-facing payloads.
8. **One commit per item**, message format: `S-XX: <short description>`.
   Let the user verify before moving on.
9. **If you cannot find the exact code described** — stop and report.
   Do not guess (§47).
10. **If a "Decision required" flag is present**, do not implement.
    Report and skip.

## Environment

- Windows / PowerShell
- Virtualenv at `.venv`
- Test style: `.venv\Scripts\python.exe -m pytest <path> -x -q --tb=short`
- Startup sanity: `.venv\Scripts\python.exe -c "from app import create_app"`

---

## S-04 — Driver earnings ignore commission

**File:** `app/transport/services/booking_service.py`
**Function:** `get_driver_earnings` (line ~803)
**Severity:** High (compliance exposure)

**Verified problem:** Returns `sum(Booking.final_price)` — the gross fare
the rider paid. Never subtracts the platform's `commission_rate`
(`DriverProfile.commission_rate`, `Numeric(5,2)`, default 15.00 —
confirmed at `app/transport/models.py:342`). Driver dashboards overstate
payout by the platform cut.

**Change:** Replace the function body. Keep the
`@monitor_endpoint("get_driver_earnings")` decorator.

```python
@monitor_endpoint("get_driver_earnings")
def get_driver_earnings(self, driver_user_id: int) -> float:
    """Total driver earnings across completed + captured bookings.

    Applies the driver's commission_rate (percentage the PLATFORM keeps)
    so the returned number is the driver's payout, not the gross fare.

    Note: commission_rate lives on DriverProfile, not per-booking. If the
    rate changes over time, historical bookings recompute at the current
    rate. Snapshotting the rate per booking is deferred (see S-18).
    """
    try:
        from app.transport.models import DriverProfile
        profile = DriverProfile.query.filter_by(
            user_id=driver_user_id, is_deleted=False
        ).first()
        if not profile:
            return 0.0

        gross = (
            db.session.query(func.sum(Booking.final_price))
            .filter(
                Booking.assigned_driver_id == profile.id,
                Booking.status == BookingStatus.COMPLETED,
                Booking.payment_status == PaymentStatus.CAPTURED,
                Booking.is_deleted == False,  # noqa: E712
            )
            .scalar()
            or 0
        )
        gross = float(gross)
        if gross <= 0:
            return 0.0

        rate = profile.commission_rate
        if rate is None:
            rate_pct = 15.0
        else:
            try:
                rate_pct = float(rate)
            except (TypeError, ValueError):
                rate_pct = 15.0

        if rate_pct < 0:
            rate_pct = 0.0
        elif rate_pct > 100:
            rate_pct = 100.0

        return round(gross * (1.0 - rate_pct / 100.0), 2)

    except Exception as e:
        logger.error(f"Error getting driver earnings: {e}", exc_info=True)
        return 0.0
```

**Test:**

```powershell
.venv\Scripts\python.exe -m pytest tests/test_transport_service_integrity.py -x -q --tb=short
```

Plus manual earnings check against a driver with completed+captured
bookings: `actual == round(gross * (1 - rate/100), 2)`.

---

## S-05 — On-demand cancellation fee bug

**File:** `app/transport/services/booking_service.py`
**Function:** `_calculate_cancellation_fee` (line ~921)
**Severity:** High (over-charge)

**Verified problem:** Current body is:

```python
hours = (booking.pickup_time - datetime.now(timezone.utc)).total_seconds() / 3600
if hours > 24:
    return Decimal("0.0")
elif hours > 2:
    return booking.final_price * Decimal("0.1")
else:
    return booking.final_price * Decimal("0.5")
```

For an on-demand booking created "now", `pickup_time` is at or before
now → `hours <= 0` → falls to `else` → 50% fee. Immediate cancel
charges half the fare. Also crashes on naive `pickup_time`
(`can't subtract offset-naive and offset-aware`) and on `None`.

**Change:** Replace with:

```python
def _calculate_cancellation_fee(self, booking: Booking) -> Decimal:
    """Cancellation fee tiers.

    On-demand / immediate-cancel window: a booking whose pickup_time is
    at or before now is "just booked, cancel immediately" — nominal fee
    (0). The 50% tier applies only when pickup is within 2h AND in the
    future.
    """
    now = datetime.now(timezone.utc)
    pickup = booking.pickup_time
    if pickup is None:
        return Decimal("0.00")
    if pickup.tzinfo is None:
        pickup = pickup.replace(tzinfo=timezone.utc)

    hours_before = (pickup - now).total_seconds() / 3600.0
    final_price = booking.final_price or Decimal("0.00")

    if hours_before <= 0:
        return Decimal("0.00")
    if hours_before > 24:
        return Decimal("0.00")
    if hours_before > 4:
        return final_price * Decimal("0.10")
    if hours_before > 2:
        return final_price * Decimal("0.25")
    return final_price * Decimal("0.50")
```

**Test:**

```powershell
.venv\Scripts\python.exe -c "
from app import create_app; create_app()
from app.transport.services import get_booking_service
from datetime import datetime, timezone, timedelta
from decimal import Decimal
svc = get_booking_service()
class FakeBooking:
    final_price = Decimal('100.00')
def fee(td):
    b = FakeBooking(); b.pickup_time = datetime.now(timezone.utc) + td
    return svc._calculate_cancellation_fee(b)
assert fee(timedelta(minutes=-5)) == Decimal('0.00')
assert fee(timedelta(minutes=10)) == Decimal('0.00')
assert fee(timedelta(hours=3)) == Decimal('25.00')
assert fee(timedelta(hours=10)) == Decimal('10.00')
assert fee(timedelta(hours=30)) == Decimal('0.00')
print('CANCEL_FEE_VERIFIED')
"
```

---

## S-06 — Duplicate canonical-location resolution in create_booking

**File:** `app/transport/services/booking_service.py`
**Function:** `create_booking` (lines ~185-254)
**Severity:** Low (cleanup)

**Verified problem:** The `_resolve_canonical_location` pickup/dropoff
block plus the `_measured_distance_km` / `distance_for_fare` block
appears TWICE (lines 185-204 and again 236-254). The second overwrites
the first. Harmless but wastes work and invites divergence.

**Change:** Delete the SECOND occurrence only (the one after
`special_req` handling, ~lines 236-254). Keep the first. Variables are
already in scope for the fare-engine call below.

**Test:**

```powershell
.venv\Scripts\python.exe -m pytest tests/test_transport_service_integrity.py -x -q --tb=short
```

Expect: all green, no change in pass count.

---

## S-07 — pickup_time parsed naive from form

**File:** `app/transport/services/booking_service.py`
**Function:** `create_booking` (lines ~227-230)
**Severity:** Medium (TZ ambiguity in prod)

**Verified problem:**

```python
pickup_time = datetime.fromisoformat(str(sanitized_data["pickup_time"]))
```

Form input `"2026-09-22T17:27"` (no offset) → naive datetime → stored
into TIMESTAMPTZ, where Postgres coerces using the DB session TZ
(dev local vs prod UTC → different instant for the same string).

**Change:** Replace the try/except block with:

```python
try:
    raw = sanitized_data["pickup_time"]
    pickup_time = datetime.fromisoformat(str(raw))
    if pickup_time.tzinfo is None:
        # Assume deployment-local TZ; Postgres TIMESTAMPTZ would
        # otherwise coerce via the DB session TZ, which differs by env.
        local_tz = datetime.now().astimezone().tzinfo
        pickup_time = pickup_time.replace(tzinfo=local_tz)
except (ValueError, TypeError, KeyError):
    pickup_time = datetime.now(timezone.utc)
```

**Test:** Baseline check + one manual booking via UI, confirm stored
`pickup_time` reads back with a tz offset.

---

## S-08 — idempotency_key column verification → CLOSED (false alarm)

**File:** `app/transport/models.py` — read only, do not edit.
**Status:** CLOSED. No action.

**Evidence:** `Booking.idempotency_key = db.Column(db.String(128),
nullable=True)` exists (`models.py:1078`) with partial unique index
`ix_booking_idem` (`models.py:977-978`). The `filter_by(idempotency_key=
...)` query in `create_booking` is valid. Close S-08, do not add any
column.

---

## S-10 — Promo validation references non-existent fields

**File:** `app/transport/services/promotion_service.py`
**Function:** `validate_promo_code` (lines ~100-105)
**Severity:** High (crash)

**Verified problem:**

```python
has_previous_rides = Booking.query.filter_by(
    customer_id=customer_id,        # no such column; it is user_id
    status__in=['completed', 'paid']  # invalid SQLAlchemy; needs .in_()
).count() > 0
```

Any first-ride promo call crashes. Also `Booking` import exists but
`BookingStatus` is NOT imported (line 15 imports only `Booking`).

**Change:**

1. Add `BookingStatus` to the models import:

```python
from app.transport.models import Booking, BookingStatus
```

2. Replace the first-ride block with:

```python
if promo_details.get('first_ride_only') and customer_id:
    has_previous_rides = Booking.query.filter(
        Booking.user_id == customer_id,
        Booking.status.in_([
            BookingStatus.COMPLETED,
            BookingStatus.CONFIRMED,
            BookingStatus.IN_PROGRESS,
        ]),
        Booking.is_deleted == False,  # noqa: E712
    ).count() > 0

    if has_previous_rides:
        return {
            'success': False,
            'valid': False,
            'message': 'Promo code only valid for first ride',
            'code': 'NOT_FIRST_RIDE'
        }
```

**Test:** Request a first-ride promo for a user with a completed booking
→ expect `NOT_FIRST_RIDE`, not a 500.

---

## S-11 — Promo discount double-applied

**File:** `app/transport/services/promotion_service.py`
**Function:** `apply_promo_code` (lines ~258-268)
**Severity:** High (wrong price)

**Verified problem:**

```python
booking.promotion_discount = (booking.promotion_discount or Decimal('0.00')) + discount_amount
...
# Recalculate final price if already set
if booking.final_price:
    booking.final_price = booking.final_price - discount_amount
elif booking.base_price:
    booking.final_price = booking.base_price - discount_amount
```

`final_price` is derived from components by the fare engine
(`fare_service.py` subtracts `promotion_discount`). Decrementing
`final_price` directly here means the next recompute subtracts the
discount a second time.

**Change:** Delete the "Recalculate final price" block entirely. Keep
only the `promotion_discount` accumulation + `booking_metadata` update.
The fare engine recomputes `final_price` from components on next call.

**Test:** After applying a promo: `promotion_discount` increased by the
discount; `final_price` NOT directly modified by `apply_promo_code`.
Manual: booking detail page shows the discount exactly once.

---

## S-12 — Promo codes hardcoded, all expired 2024 → DECISION REQUIRED

**File:** `app/transport/services/promotion_service.py`
**Status:** REPORT ONLY. Do not implement.

Verified: `WELCOME10` / `AFCON25` / `FIRSTRIDE` all have
`valid_until` in 2024. Today every code returns `EXPIRED_CODE`.
Options: (a) real `PromoCode` model + table (schema change — needs
authorization), (b) fresh test codes dated 2026-12-31, (c) delete the
mock dict and return `INVALID_CODE`. Ask the user which. Do not pick
for them.

---

## S-13 — _ranked_candidates crashes on string pickup_location

**File:** `app/transport/services/matching_service.py`
**Function:** `_ranked_candidates` (line ~44-48)
**Severity:** High (dispatch crash)

**Verified problem:**

```python
zone=booking.pickup_location.get('zone'),
```

`pickup_location` is JSONB and the current writer can produce a plain
string (`"Nakawa"`) or `None` → `.get` raises `AttributeError`.
Check `matching_service.py` imports: add `Optional` if missing.

**Change:** Add module-level helper, then use it:

```python
def _pickup_zone(booking) -> Optional[str]:
    """Extract pickup zone from a JSONB pickup_location that may be
    a dict, a string, or None."""
    loc = getattr(booking, "pickup_location", None)
    if isinstance(loc, dict):
        return loc.get("zone")
    return None
```

Replace `zone=booking.pickup_location.get('zone'),` with
`zone=_pickup_zone(booking),`.

**Test:**

```powershell
.venv\Scripts\python.exe -c "
from app import create_app; create_app()
from types import SimpleNamespace
from app.transport.services.matching_service import _pickup_zone
assert _pickup_zone(SimpleNamespace(pickup_location='Nakawa')) is None
assert _pickup_zone(SimpleNamespace(pickup_location={'zone':'cbd'})) == 'cbd'
assert _pickup_zone(SimpleNamespace(pickup_location=None)) is None
print('PICKUP_ZONE_VERIFIED')
"
```

---

## S-14 — Driver-assigned notification payload → INVESTIGATE, then fix

**File:** `app/transport/services/assignment_service.py`
**Function:** `_notify_assigned` (lines ~270-289)
**Severity:** Medium (wrong payload, not a missing method)

**Correction to earlier description:** `NotificationService.
send_transport_notification` DOES exist on the central service
(`app/notifications/services.py:562`) with signature
`(user_id, booking, notification_type, channel)`, and the current call
matches that signature. It does not raise `AttributeError`.

The real defects are in the callee's payload for transport bookings:

- `data['booking_id'] = booking.id` — exposes internal `id` (§12.1);
  should be `public_id` / `booking_reference`.
- `link = f"/transport/bookings/{booking.id}"` — same exposure.
- `message` interpolates `booking.pickup_location` raw (may be a dict).
- `data` reads `booking.booking_code` / `booking.scheduled_time`,
  which do not exist on transport `Booking` (guarded by `hasattr`,
  so they silently yield `''` — dead fields).

**Change (authorized, no signature change):** Keep calling the central
`send_transport_notification`. Do NOT switch to the transport-module
`send_booking_notification` (different signature, different service).
Instead fix the payload at the call site by passing a transport-shaped
booking — OR, minimal safe fix: leave the call, and file the callee
payload defects (`booking.id` exposure, dead `booking_code` /
`scheduled_time` fields, raw-dict message) as a follow-up node for the
notifications owner. Do not rewrite `app/notifications/services.py`
from this brief (cross-module, §17).

**Test:** Complete a driver assignment via admin UI; verify the rider
receives an in-app `driver_assigned` notification. Report the payload
defects observed.

---

## S-15 — Booking-created fan-out → INVESTIGATE, then fix

**Files:** `app/notifications/listeners.py:256-260`,
`app/notifications/services.py:1490-1533`
**Severity:** High (spam + missing rider notification)
**Status:** INVESTIGATE FIRST. Do not edit until you report.

**Verified structure:**

- `_on_transport_booking` calls `notify_booking_confirmed(booking)`.
- That method resolves `guest_id = booking.guest_user_id or
  booking.customer_id` — transport `Booking` has NEITHER (it uses
  `user_id`). Result: `guest_id` is `None` → **the rider is never
  notified**.
- `host_id = booking.host_user_id` — also absent on transport →
  `None` → skipped.
- `_notify_admins(...)` then broadcasts to owner/super_admin/admin
  (+ domain roles) via `notify_roles`. THIS is the fan-out: N admins
  × 1 booking = N notifications per booking (matches the "12"
  log evidence if 12 admin accounts exist).

**Task:** Read `notify_booking_confirmed` + `_notify_admins` +
`notify_roles` and report:

1. Recipient list actually resolved for a transport booking
   (confirm rider skipped, count of admin recipients).
2. Proposed minimal fix: resolve the transport rider via
   `booking.user_id` when `module == 'transport'` (mirror the
   `module_for_booking` branch already used for the send call),
   without changing accommodation/tourism paths.
3. Whether the admin broadcast for transport bookings is intended.
   If yes, leave it; if no, propose scoping (e.g. domain='transport'
   only, or in_app only).

Do not change anything until you report findings 1-3.

---

## S-16 — Dashboard cache key has no scope

**File:** `app/transport/services/dashboard_service.py`
**Function:** `get_cached_admin_dashboard` (lines ~21, 65-73)
**Severity:** Medium (cache bleed)

**Verified problem:** `CACHE_KEY = "transport:admin:dashboard"` with no
user/org scope. Org-scoped admins (`organisation_admin` role exists)
can receive the platform-wide dashboard from cache.

**Change:** Add an optional scope param; default preserves call sites:

```python
CACHE_KEY = "transport:admin:dashboard"

def get_cached_admin_dashboard(self, scope: str = "global") -> Dict[str, Any]:
    """Get dashboard data from cache or generate fresh.

    scope separates caches per actor class. Callers with org-scoped
    admin rights should pass scope=f"org:{org_id}".
    """
    key = f"{self.CACHE_KEY}:{scope}"
    cached = cache.get(key)
    if cached:
        logger.debug("Returning cached admin dashboard (%s)", scope)
        return cached
    context = self.get_admin_dashboard_context()
    cache.set(key, context, timeout=self.CACHE_TTL)
    logger.debug("Admin dashboard cached for 5 minutes (%s)", scope)
    return context
```

Do not change callers.

**Test:** Default call still returns a dict; two calls with different
scopes do not share cache entries.

---

## S-17 — calculate_driver_earnings returns placeholder zeros → DECISION REQUIRED

**File:** `app/transport/services/marketplace_service.py`
**Function:** `calculate_driver_earnings` (line ~848)
**Status:** REPORT ONLY. Do not implement.

Verified stub returning zeroed dict ("would integrate with
booking/payment services"). Needs product decisions: how contract
revenue splits with booking earnings; whether to reuse
`BookingService.get_driver_earnings` or a new query; what period to
aggregate. Report and skip.

---

## S-18 — Snapshot commission rate per booking → DEFERRED (schema change)

**Status:** SKIP. Tracked for a future sprint. Requires
`Booking.driver_commission_rate_applied` column + write at completion
time. Out of scope for this brief (§20).

---

## S-09 — Non-cash payment methods 500 → DEFERRED (feature work)

**Status:** SKIP in this brief. Real payment-gateway integration work;
needs a product/engineering decision, not a mechanical fix.

---

## Order of execution

1. S-04 — driver earnings (verification gate)
2. S-05 — cancellation fee (verification gate)
3. S-06 — duplicate location resolution (regression suite)
4. S-07 — naive pickup_time
5. S-08 — CLOSED, no action (record in report)
6. S-10 — promo validation fix
7. S-11 — promo double-discount
8. S-12 — REPORT ONLY, skip after reporting
9. S-13 — dispatch crash on string JSONB
10. S-14 — verify notification received; report payload defects
11. S-15 — REPORT findings 1-3, await decision
12. S-16 — dashboard cache scope
13. S-17 / S-18 / S-09 — SKIP (report as deferred)

## Final report format (after EACH item)

```text
ITEM: S-XX
STATUS: PASS | FAIL | REPORT_ONLY | SKIPPED_DEFERRED | CLOSED_FALSE_ALARM
FILES: <path list>
TESTS_RUN: <command>
TESTS_RESULT: <summary line>
NOTES: <anything unexpected>
```

If any item FAILs, do not proceed. Report and wait.
