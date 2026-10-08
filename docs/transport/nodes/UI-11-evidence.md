# UI-11: RIDE REQUEST CONFIRMATION COPY — EVIDENCE

## STATUS: PASS — ratified by adversarial review, node CLOSED

> **Gate history (read in order, not overwritten):**
> 1. Human placed UI-11 as read-only TRACE (booking-state semantics on the
>    rider ride page: flash "Booking confirmed!", matching panel, timeline).
> 2. Agent delivered TRACE report: `STATUS: TRACE COMPLETE / GATE: READY FOR
>    ADVERSARIAL REVIEW / CODE CHANGES: NONE / SCHEMA CHANGES: NONE /
>    MIGRATIONS: NONE`. Classification: MODEL/DOMAIN SEMANTICS.
> 3. Human ordered a MINIMAL CORRECTION: rider copy from
>    "Booking confirmed! Reference: {ref}" to
>    "Ride request received! We're finding your driver. Reference: {ref}",
>    plus MATCH-01 comment correction and a focused regression test.
> 4. Agent implemented and verified the correction (focused + booking-state +
>    MATCH-01 regressions: 47 passed, 0 failed).
> 5. Adversarial review (DeepSeek panel): **VERDICT: PASS / PRIMARY
>    CLASSIFICATION: PRESENTATION-VOCABULARY / BLOCKING FINDING: NONE** —
>    recommendation to ratify and close UI-11.
> 6. Human ratified and authorized RECORD/CLOSE ONLY (2026-10-07). Agent then
>    authored the evidence and record files. The agent did not and cannot set
>    the gate; the panel and human did.

NODE: UI-11
BRANCH: main
DATE: 2026-10-07
RUNTIME USED FOR PROOF: pytest against the sanctioned PostgreSQL test DB
  (uid...) — no throwaway server required; all proof is server-less test proof.

---

## 1. SCOPE AND GUARANTEE

**Guarantee in one sentence:** the rider-facing ride-request confirmation copy
states correct presentation vocabulary, and the template documentation of the
`CONFIRMED` booking state no longer conflates it with payment capture.

UI-11 owns presentation vocabulary only. It did not touch the BookingStatus
state machine, status transitions, matching/assignment logic, timeline step
timestamps, payment logic, wallet, migrations, schema, or any other node's
scope.

**Node contract:** no `docs/transport/nodes/UI-11-contract.md` exists in the
repository; the node was executed against the human's written directives as the
task contract, per UI-20 precedent.

## 2. WHAT WAS CHANGED (exact files/lines)

### 2.1 `app/transport/routes.py` — `book_transport()`, flash, line 983

```python
# BEFORE (HEAD and original working tree)
flash(f"Booking confirmed! Reference: {ref}", "success")

# AFTER (working tree, verified)
flash(f"Ride request received! We're finding your driver. Reference: {ref}", "success")
```

Byte-level verification of the working tree immediately before writing this
evidence file:

```text
repr of line 983:
  '        flash(f"Ride request received! We’re finding your driver. Reference: {ref}", "success")'
has_u2019 (U+2019 RIGHT SINGLE QUOTATION MARK "We're"): True
has_ascii_quote: False
```

The reference `{ref}` is preserved unchanged.

### 2.2 `templates/transport/rides/show.html` — MATCH-01 comment, lines 263-264

```html
{# BEFORE (HEAD):
   MATCH-01-owned: CONFIRMED means payment taken and matching active —
   the rider must see "Finding your driver", never a stale "Confirmed". #}

{# AFTER (working tree):
   MATCH-01-owned: CONFIRMED means the booking is accepted/claimable and matching is active;
   payment state is tracked separately by payment_status. #}
```

Repo-wide stale-phrase scan:

```text
Get-ChildItem templates,static,app -Recurse -File -Include *.html,*.py,*.js |
  Select-String -Pattern 'payment taken'
      → 0 matches
```

The `sc` pill-class map, the rider status badge, the timeline, and all other
template behavior are byte-identical to HEAD.

### 2.3 `tests/test_ui11_booking_flash_copy.py` (new)

Focused regression: a confirmed booking's success flash carries the exact new
wording with the booking reference, and the old wording is absent. Reuses the
`_FakeRedis`, `_bolt_form`, `_promote_user_to_tier3`, `_new_pickup_time`
helpers from `tests/test_transport_booking_route_path.py`.

### 2.4 `tests/test_transport_cash_confirmation_semantics.py` — docstring, line 7 (documentation-only)

```text
BEFORE: - payment_status = PENDING (pay-later, payment captured on arrival)
AFTER:  - payment_status = PENDING at booking; payment is not captured at booking
```

Documentation-only correction. No assertion about when payment will eventually
be captured was added; no test logic changed.

## 3. RUNTIME VERIFICATION (actual commands and results)

### 3.1 Focused regression set (UI-11 + booking-state + MATCH-01), 2026-10-07

```text
.venv\Scripts\python.exe -m pytest tests\test_ui11_booking_flash_copy.py \
  tests\test_transport_booking_route_path.py tests\test_transport_rider_page.py \
  tests\transport\test_match01_assignment_race.py tests\transport\test_match01_no_match_terminals.py \
  tests\transport\test_match01_status_json.py tests\transport\test_match01_retry.py \
  tests\transport\test_match01_silent_rejection.py tests\transport\test_match01_payload_stripping.py \
  tests\transport\test_assignment_release_supply_invariant.py
     47 passed, 0 failed, 14 warnings in 78.91s     EXIT=0
```

Identical to the pre-change focused baseline (47 passed), proving no regression
in the booking-state or MATCH-01 suites attributable to UI-11.

### 3.2 Directly relevant tests after the documentation-only docstring correction, 2026-10-07

```text
.venv\Scripts\python.exe -m pytest \
  tests\test_transport_cash_confirmation_semantics.py \
  tests\test_ui11_booking_flash_copy.py \
  tests\transport\test_match01_assignment_race.py \
  tests\transport\test_match01_no_match_terminals.py \
  tests\transport\test_match01_status_json.py \
  tests\transport\test_match01_retry.py \
  tests\transport\test_match01_silent_rejection.py \
  tests\transport\test_match01_payload_stripping.py \
  -v
     34 passed, 11 warnings in 76.65s               EXIT=0
```

Coverage of the run: cash-confirmation semantics (CONFIRMED + PENDING,
CONFIRMED != payment captured, CONFIRMED != driver assigned, matching may run
on CONFIRMED/PENDING) + UI-11 flash copy + the six MATCH-01 contract files.

## 4. SEPARATE NON-BLOCKING FINDINGS (not UI-11, not fixed here)

### 4.1 `tests/test_transport_concurrent_claim.py` — suite-level instability

Full-suite runs of `tests/test_transport_concurrent_claim.py` show two
failures (`test_discover_and_offer_creates_offer_for_confirmed_unassigned`,
`test_dispatch_recovery_rediscovery_offers_confirmed_unassigned`), both with
failure path `discover_and_offer → no_suitable_drivers`.

Reported conservatively as **suite-level/shared-test-DB instability; not
attributed to the UI-11 copy change**: both failing tests pass in isolation
under the identical code, and the failing path is unreachable from the edited
flash string. They are NOT labeled definitively pre-existing/parked, because no
repository evidence explicitly establishes parked status for these two tests.

### 4.2 Preserved separate findings

- matching-recovery trigger availability (a `confirmed` booking with an
  expired/unaccepted offer and no recovery path can remain `confirmed`);
- card/mobile-money payment implementation (out of scope);
- future scheduled-booking/deposit/payment-policy work (out of scope).

## 5. WHAT WAS NOT CHANGED

- BookingStatus values/transitions: NO
- status timeline step names/timestamps: NO
- matching/assignment/recovery logic: NO
- payment system/logic: NO
- model/schema/migration: NO
- wallet/KYC/shared fixtures: NO
- any register (UI/UX 21-point, DOC-201-S, DOC-202-S, A–L, GEO, UI-LOC): NO