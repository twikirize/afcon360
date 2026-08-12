# AFCON360 Seamless Booking — Product & Engineering Spec
**Status:** Ready for implementation
**Owner:** Obed (Product Owner / Lead Dev)
**Author of this spec:** Claude, acting as Chief Product Engineer for this workstream
**Scope:** `accommodation` module — checkout flow, guest identity, payment options
**Goal:** A guest in Nairobi, São Paulo, Toronto, Beijing, or Kampala should be able to book a stay on AFCON360 faster and with less friction than on Booking.com or Airbnb, without the platform ever asking them for information it doesn't need yet.

---

## 0. Design Philosophy — the one rule everything below follows

> **Ask only for what today's step needs. Never gate a reservation on information that belongs to a later step.**

Three steps only exist to *hold a room and take payment*: dates, party size, payment. Everything else — who exactly is staying, their ID, their phone in the right format, special requests — is a **check-in requirement**, not a **booking requirement**, and is collected after confirmation, on the guest's own terms, in their own language and script.

This single rule is why the flow below feels different from booking.com/Airbnb, not just visually but structurally: most competitor platforms still front-load guest data because their legacy schemas require it. AFCON360's schema, as built, was clearly designed to *not* require it (see §1) — the current checkout form just hasn't caught up to the schema yet. This spec closes that gap.

---

## 1. What the codebase already got right (evidence, not assumption)

Confirmed by direct inspection of the current codebase — this is not a redesign of the data model, it's finishing one that's ~80% built:

| Capability | Where it already lives |
|---|---|
| Booker ≠ Guest ≠ Owner separation | `AccommodationBooking.booked_by_user_id`, `.primary_guest_id/name/email/phone`, `.booking_owner_id/owner_email/claim_token_hash` |
| Self-serve claim-link for third-party bookings | `AccommodationBooking.claim_token_hash`, `owner_claimed_at` — built, unused |
| Per-booking guest roster, independent of the User table | `GuestRegistration` model (`accommodation_guest_registrations`) — `status: pending/in_progress/completed/skipped`, `registration_source: self/host/admin` |
| Soft registration deadline (never blocks a paying guest) | `AccommodationBooking.registration_deadline`, `BookingStateMachine._registration_satisfied()` — deadline lapsed + incomplete → **still allowed to check in**, host just sees a warning |
| Guest loyalty/preferences separate from per-booking identity | `GuestProfile` (`accommodation_guest_profiles`) — one-to-one with `User`, holds `preferred_currency`, `preferred_language`, loyalty points |
| Corporate/org payment-preference precedent | `EventPaymentPreference` (`app/wallet/models/payment_method.py`) — `accepted_methods`, `preferred_currency`, `auto_convert_wallet` |
| Group booking primitive | `AccommodationBooking.group_booking_id/group_size/room_number`, `booking_type` enum incl. `group` |

**Conclusion:** we are not designing new architecture. We are (a) removing one blocking `NOT NULL` constraint, (b) reordering a Jinja template and its route, and (c) adding two genuinely-missing fields to the payment method schema. Everything else is wiring.

---

## 2. Confirmed root causes (evidence trail)

1. **`AccommodationBooking.guest_name` / `.guest_email` are `nullable=False`** at the DB level (`app/accommodation/models/booking.py`), despite the newer `primary_guest_*` fields being nullable and clearly intended to supersede them.
2. **`BookingService.create_booking()`** declares `guest_name: str` and `guest_email: str` as *required positional parameters with no default* — the strictest point of enforcement in the whole chain, stricter than the DB even.
3. Internally, `create_booking()` treats the **legacy fields as primary** and `primary_guest_*` as the fallback (`primary_guest_name or guest_name`) — backwards from what the schema's own design intent (§1) implies. This inversion is *why* the checkout form is forced to collect name/email immediately: nothing downstream can treat them as optional yet.
4. `routes.py`'s checkout POST handler additionally requires `primary_guest_name`/`primary_guest_email` in `required_fields` for `booking_type == 'third_party'` — a second, route-level gate on top of the above.
5. **Payment timing is not a real field anywhere.** `PaymentMethodConfig` (single source of truth for payment methods, `app/wallet/models/payment_method.py`) has no timing/deposit-eligibility column at all. `PaymentPolicyService.get_allowed_options()` fabricates a timing map by hardcoded `method_type` bucket (`'pay_now': ['wallet','card','mobile_money']`), which cannot represent "this specific host-configured Visa integration is pay-now only."
6. **Per-method, per-property currency is not modeled.** `PaymentMethodConfig.supported_currencies` is a *global capability list* ("this method type can technically handle these currencies"), not "this host chose to charge in KES for this property." No field currently carries the host's actual selection.
7. **The booking form has no dedicated module.** `accommodation/forms.py` only contains `PropertyForm` (host listing creation). `forms/booking_forms.py` exists as a path but is empty. The checkout POST handler in `accommodation/routes.py` reads directly from `request.form` with manual `if not data.get(field)` checks — there is no WTForm validation layer between the guest and the database for the booking itself.
8. A second, independent call site — `events/routes/assignment.py::assign_accommodation()` — calls `create_booking()` with a parameter set (`check_in_date=`, `check_out_date=`, omits `guest_name`/`guest_email` entirely) that does not match the real signature. **This call currently raises `TypeError` on every invocation and has almost certainly never executed successfully.** Flagged for separate triage, out of scope for this spec but must not be copied as a pattern.

---

## 3. The checkout flow, redesigned

### 3.1 Three visible steps. Nothing else, ever, before confirmation.

```
STEP 1 — Stay & Party            STEP 2 — Payment            STEP 3 — Confirm & Hold
  • Who's this for?                • Method                    • Booking created
    (Myself / Someone else /       • Timing (filtered by         (status: HELD)
     Group)                          selected method)           • Reference issued
  • Party size / room count        • Amount shown in the        • Claim-link sent if
  • NO names, NO email,              method's currency,           booker ≠ guest
    NO ID, NO phone required        FX-converted note if
                                     ≠ guest's session currency
```

A guest with a wallet balance and a known stay length can complete Steps 1–3 in **under 20 seconds**, faster than Airbnb (which asks for full guest details before showing final price) and Booking.com (which asks for guest details before payment method selection).

### 3.2 Step 1 — Stay & Party detail

| Field | booking_type = self | third_party | group |
|---|---|---|---|
| Booking type selector | ✓ (3 options, radio/segmented control) | | |
| Check-in / check-out | ✓ (from prior search context — pre-filled, not re-asked) | ✓ | ✓ |
| Number of guests | ✓ | ✓ | ✓ total across group |
| Number of rooms | 1 (implicit) | 1 (implicit) | ✓ explicit, e.g. "4 rooms for 9 people" |
| Guest name / email / phone | **not asked** | **not asked** | **not asked** |

Rationale for dropping name/email even for `third_party` at this step: the booker frequently doesn't have the guest's exact legal name-as-ID or correctly-formatted phone on hand at the moment of booking (booking for a boss, an employee, a family member abroad). Forcing it here is the single biggest friction point identified in the current form. Defer to the claim-link flow (§3.5).

**Group room-to-guest mapping is explicitly NOT required here.** The organizer states room count and total guests; who's in which room is resolved in the post-booking Guest Roster step, once the group has actually decided — this matches how real group trips are organized in practice, and removes the current form's requirement to pre-declare `room_number`/`num_guests` per room before payment.

### 3.3 Step 2 — Payment

**Fetch order (server → client), replacing the current dual-service split:**

1. Client requests `GET /accommodation/api/checkout/payment-options?property_id=&amount=&currency_context=`
2. Server (see §4.2 for the consolidated service) returns, for *this specific property*, only the methods the host has actually enabled — no hardcoded allowlist, no client-side filtering.
3. Each method object carries its **own** `allowed_timings` and its **own** `currency` (§4.1 schema additions) — not inferred from `method_type`.
4. Client renders method selector first. **Timing options only appear, and only render the timings that method's `allowed_timings` contains, after a method is selected.** Selecting a different method re-renders the timing options from scratch — never a static global list, never a client-side `data-timing` string match.
5. Once method + timing are both chosen, the amount displays in the **method's currency**. If that differs from the guest's session/wallet currency, show the converted amount and the rate:
   `Total: KES 45,000  (≈ UGX 612,000 at today's rate — via AFCON360 FX)`
6. Cash / pay-on-arrival methods never show "deposit" or "pay now" as options — structurally absent from the DOM for that method, not merely disabled, so a bad state (cash + deposit) is impossible to submit.

### 3.4 Step 3 — Confirm & Hold

- Server creates the `AccommodationBooking` row in `HELD` (or `DRAFT`→`HELD` per the existing state machine — no change to `booking_states.py`, it already models this correctly).
- `guest_name`/`guest_email` are **not required inputs at this point** (see §4.1 — nullable, and no longer sourced from the checkout form for third_party/group when unknown).
- A `RoomHold` (unit-level — see the outstanding architectural note in §6) is created per room in the group.
- Guest sees: booking reference, dates, total, payment confirmation. That's it. No name field, no special-requests box, no ID upload.

### 3.5 Deferred — Guest Roster & Special Requests (post-booking, self-serve, before check-in)

Reachable any time from the booker's dashboard between confirmation and check-in. Not a wizard step — a standing page the booking links to.

- **For `self` bookings:** auto-populated from the booker's own account. Zero additional action required, ever — this path can be entirely skipped in the UI.
- **For `third_party` / `group` bookings:** the booker sees a roster with one row per guest/room, each either:
  - Filled in directly by the booker, or
  - Sent as a **self-serve claim link** (email or WhatsApp/SMS — WhatsApp preferred by default for phone-only guests, matching regional usage patterns across the guest base) using the existing but currently-unused `claim_token_hash` mechanism. The guest opens the link, fills their own name exactly as they'd write it (no forced first/last split — supports mononyms, patronymics, and non-Latin scripts), their own phone with a proper country-code selector, and their own ID document.
- Each `GuestRegistration` row transitions `pending → in_progress → completed` (or `skipped` via host override) exactly as the model already supports.
- Deadline messaging uses the existing soft-gate language: *"Guest details help your host prepare — please complete by [registration_deadline]. This will never block your check-in."* This mirrors `BookingStateMachine._registration_satisfied()`'s own comment almost verbatim — the UI copy should match the backend's actual guarantee so guests aren't warned about something that can't actually happen to them.
- **Special requests** move here too — out of the booking wizard entirely. It's check-in-experience data (late arrival, dietary notes, accessibility needs), not a payment-blocking field. Lives on the same page as the guest roster, one shared "finish your stay details" surface.

### 3.6 Localization checklist (applies across all steps)

| Concern | Rule |
|---|---|
| Name field | Single free-text field, no forced first/last split. Never require a family name. |
| Phone | Country-code dropdown + national number, always, everywhere a phone is collected (checkout and roster) |
| Currency | Session currency resolved from guest's wallet/locale; every price shown in that currency with FX note when it differs from the property/method currency; never mix currency symbols on one screen |
| Date format | Explicit format shown near the field (`DD Mon YYYY`), not raw ISO, not silently locale-dependent |
| Language | Step labels and confirmations pulled from the existing i18n layer if present; if not present yet, flag as a fast-follow, not a blocker for this spec |

---

## 4. Required engineering changes

### 4.1 Schema changes (Alembic migrations, in order)

**Migration A — relax legacy guest identity fields**
```python
# app/accommodation/models/booking.py
guest_name = Column(String(255), nullable=True)   # was nullable=False
guest_email = Column(String(255), nullable=True)  # was nullable=False
```
Verify via `pg_constraint` before/after per existing team practice. Check nothing outside `routes.py`/`booking_service.py` assumes non-null (search, admin exports, notification templates at lines ~1930/2154/2825 of `routes.py` already null-guard via `or` fallbacks — confirm the rest do too before deploying).

**Migration B — payment method timing capability**
```python
# app/wallet/models/payment_method.py — PaymentMethodConfig
allowed_timings = Column(JSON, default=list)  # e.g. ["pay_now", "deposit"]
```
Global default per method. Backfill existing rows: wallet/card/mobile_money → `["pay_now","deposit"]`; cash → `["pay_on_arrival"]`; invoice → `["invoice"]` — this replaces `PaymentPolicyService`'s hardcoded `method_timing_map` with real data.

**Migration C — per-property payment currency**
```python
# app/accommodation/models/property_payment_method.py — PropertyPaymentMethod
preferred_currency = Column(String(3), nullable=True)  # host's chosen currency for this method on this property
```
Mirrors `EventPaymentPreference.preferred_currency`, already a shipped pattern in `app/wallet`. Falls back to `Property.currency` when null so no existing row breaks.

**Note:** `property_payment_method.py`'s current full field list was not directly inspected in this workstream (only referenced from `payment_policy_service.py`) — confirm Migration C's exact table state before writing it; do not assume the field is absent without a final check.

### 4.2 Service layer — consolidate two competing services into one

Currently `payment_option_service.py` and `payment_policy_service.py` overlap and disagree on shape (one is currency-aware with no timing, the other has fabricated timing with no currency). Replace both call sites with a single `PaymentPolicyService.get_allowed_options()` that returns, per method:

```python
{
  "method_id": "momo",
  "display_name": "MTN MoMo",
  "currency": "UGX",                 # from Migration C, falls back to Property.currency
  "allowed_timings": ["pay_now"],    # from Migration B, filtered by policy toggles
  "transaction_fee": 0.01,
  "min_amount": 500.00,
  "max_amount": 5000000.00,
  "icon": "smartphone"
}
```
`payment_option_service.py` can be deprecated once its one unique capability (currency-filtered `get_available_methods`) is folded into the consolidated service — don't run both in production checkout simultaneously, that's the exact drift that caused the current bug.

### 4.3 `BookingService.create_booking()` signature change

```python
guest_name: str = None,       # was required, no default
guest_email: str = None,      # was required, no default
```
And flip the internal precedence (currently backwards) at the snapshot/fallback lines:
```python
# was: primary_guest_name or guest_name  (primary_guest_* as fallback)
# now: guest_name or primary_guest_name  →  but canonical source should be primary_guest_*
guest_name_to_store = primary_guest_name or guest_name
guest_email_to_store = primary_guest_email or guest_email
```
`primary_guest_*` becomes canonical; legacy fields become a mirror for backward-compatible reads only.

### 4.4 Route layer (`accommodation/routes.py`)

- Drop `primary_guest_name`/`primary_guest_email` from `required_fields` for `booking_type == 'third_party'` (currently ~line 1549).
- When guest identity is unknown at booking time: generate `claim_token_hash`, set `booking_owner_id`/`owner_email`, and rely on the notification path that already exists (lines ~1930, ~2154) rather than blocking submission.
- Stop passing `guest_name=primary_guest_name, guest_email=primary_guest_email` unconditionally (lines ~1845–1846) — pass `None` through when genuinely deferred.

### 4.5 New dedicated booking form module — separating checkout from the model

Currently there is no form module standing between the guest and the database for checkout. Create:

**`app/accommodation/forms/booking_forms.py`** *(new — the existing empty path should become this real module, distinct from `accommodation/forms.py` which stays scoped to host/listing forms)*

```python
class StayPartyForm(FlaskForm):
    """Step 1 — dates, party size, booking type. No identity fields."""
    booking_type = SelectField(choices=[('self','Myself'),('third_party','Someone else'),('group','Group')])
    check_in = DateField(...)
    check_out = DateField(...)
    num_guests = IntegerField(...)
    num_rooms = IntegerField(default=1)  # group only

class PaymentSelectionForm(FlaskForm):
    """Step 2 — method + timing, validated server-side against
    get_allowed_options() for the specific property, not a static choice list."""
    payment_method_id = StringField(...)
    payment_timing = SelectField(...)

class GuestRosterEntryForm(FlaskForm):
    """Deferred step — one guest at a time, self-serve or booker-filled.
    This is where name/email/phone/ID actually get validated."""
    guest_name = StringField(validators=[DataRequired(), Length(max=255)])
    guest_email = StringField(validators=[Optional(), Email()])
    guest_phone_country_code = StringField(...)
    guest_phone_national = StringField(...)
    id_document_type = SelectField(...)

class SpecialRequestsForm(FlaskForm):
    """Deferred step — lives alongside the guest roster, not the wizard."""
    special_requests = TextAreaField(...)
```

Route handlers import from this module instead of reading `request.form` directly with manual `if not data.get(...)` checks — this gives the checkout flow the same validation rigor `PropertyForm` already has for host listings, closing the gap flagged in §2.7.

---

## 5. File-by-file change list (for the implementing agent)

| File | Change |
|---|---|
| `app/accommodation/models/booking.py` | Migration A (nullable guest_name/email) |
| `app/wallet/models/payment_method.py` | Migration B (`allowed_timings`) |
| `app/accommodation/models/property_payment_method.py` | Migration C (`preferred_currency`) — confirm current schema first |
| `app/accommodation/services/payment_policy_service.py` | Consolidate; read real `allowed_timings`/`preferred_currency`; remove hardcoded `method_timing_map` |
| `app/accommodation/services/payment_option_service.py` | Deprecate after consolidation, or reduce to a thin currency-filter helper called by the consolidated service |
| `app/accommodation/services/booking_service.py` | `create_booking()` signature + precedence flip (§4.3) |
| `app/accommodation/routes.py` | Drop upfront identity requirement for third_party (§4.4); new checkout route(s) serving Steps 1–3; new `payment-options` JSON endpoint |
| `app/accommodation/forms/booking_forms.py` | **New file** — `StayPartyForm`, `PaymentSelectionForm`, `GuestRosterEntryForm`, `SpecialRequestsForm` |
| `templates/accommodation/checkout.html` | Rebuilt to 3 steps per §3.1–3.4; strip name/email/special-requests fields |
| `templates/accommodation/guest_roster.html` | **New template** — deferred step from §3.5, reachable from dashboard |
| `events/routes/assignment.py` | **Out of scope for this spec** — flagged in §2.8 as separately broken; do not model new call sites on its current pattern |

---

## 6. Explicitly out of scope for this spec (tracked separately)

- **`RoomHold` vs `BlockedDate`**: `create_hold()` currently writes to the property-wide `BlockedDate` table instead of instantiating the unit-aware `RoomHold` model that already exists. Multi-room group bookings and unit-level inventory depend on this being fixed, but it's an availability-engine change, not a checkout-flow change. Needed before group booking (§3.2) can fully guarantee specific-unit holds — flag as a hard dependency for group bookings specifically, non-blocking for self/third_party.
- **`events/routes/assignment.py::assign_accommodation()`**: confirmed broken call to `create_booking()` (§2.8). Needs its own triage pass to determine if it's live/reachable before fixing.
- **i18n/translation layer**: this spec assumes correct locale-driven copy is either already handled or a fast-follow; it does not design the translation system itself.
- **`PropertyPaymentMethod` full schema audit**: Migration C assumes the field is absent based on indirect evidence; needs direct confirmation.

---

## 7. Production-readiness checklist

- [ ] Migration A applied, verified via `pg_constraint`, no NOT NULL violations on existing rows
- [ ] Migration B applied, defaults backfilled for existing `PaymentMethodConfig` rows
- [ ] Migration C applied, `preferred_currency` falls back correctly where null
- [ ] `create_booking()` callable with `guest_name=None, guest_email=None` without error, for all three `booking_type` values
- [ ] `events/routes/assignment.py::assign_accommodation()` confirmed either fixed or confirmed unreachable/unused (not silently left broken in production)
- [ ] Checkout completes in ≤3 visible steps for a `self` booking with a funded wallet
- [ ] Timing options render only from the selected method's real `allowed_timings` — manually test cash method shows no deposit/pay-now option
- [ ] Amount displays in method currency with FX conversion note when applicable
- [ ] Claim-link flow sends and a guest can complete registration via the link without an AFCON360 account
- [ ] Guest Roster page reachable from booker dashboard, shows correct per-guest status (`pending/in_progress/completed/skipped`)
- [ ] Special requests field removed from checkout wizard, present on Guest Roster page
- [ ] Name field accepts non-Latin script and single-word/mononym input without validation error
- [ ] Phone field enforces country-code selection on both checkout (if collected) and roster
- [ ] `test_accommodation_booking.py` updated to cover nullable guest identity paths
