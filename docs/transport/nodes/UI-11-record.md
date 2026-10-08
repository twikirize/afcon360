# UI-11 — Record

STATUS:          CLOSED / PASSED
CLASSIFICATION:  PRESENTATION-VOCABULARY
BLOCKING FINDING: NONE

Commit:          none — UI-11 changes remain together in the working tree for a
                 separately-authorized commit
Date:            2026-10-07
Owner:           agent (implementation + verification + evidence + record);
                 human (gate + register)
Gate:            human placed read-only TRACE → TRACE complete (READY FOR
                 ADVERSARIAL REVIEW) → human ordered MINIMAL CORRECTION →
                 correction verified (47 passed) → adversarial review returned
                 VERDICT: PASS / PRESENTATION-VOCABULARY / BLOCKING FINDING:
                 NONE → human ratified and ordered RECORD/CLOSE only

---

## Guarantee delivered

The rider-facing ride-request confirmation copy states correct presentation
vocabulary, and the template documentation of the `CONFIRMED` booking state no
longer conflates it with payment capture.

## Core conclusion

- `Booking.status=CONFIRMED` = accepted/claimable booking with matching active
- `payment_status` is a separate payment lifecycle
- `CONFIRMED` does not mean payment captured
- `CONFIRMED` does not mean driver assigned
- rider copy was corrected from "Booking confirmed!" to
  "Ride request received! We're finding your driver..."
- MATCH-01 semantic comment was corrected
- no BookingStatus/state-machine redesign
- no migration/schema change
- no payment implementation
- no matching/recovery implementation

## What changed

| File | Change |
|------|--------|
| `app/transport/routes.py` (:983) | `book_transport()` success flash: `Booking confirmed! Reference: {ref}` → `Ride request received! We're finding your driver. Reference: {ref}` (reference preserved; U+2019 apostrophe byte-verified) |
| `templates/transport/rides/show.html` (:263-264) | MATCH-01 comment: `CONFIRMED` = accepted/claimable + matching active; payment state tracked separately by `payment_status` (stale "payment taken" phrasing gone repo-wide: 0 matches) |
| `tests/test_ui11_booking_flash_copy.py` (new) | focused regression: new flash wording + reference present, old wording absent |
| `tests/test_transport_cash_confirmation_semantics.py` (:7) | documentation-only docstring correction: `payment captured on arrival` → `payment_status=PENDING at booking; payment is not captured at booking` (no assertion added) |

No BookingStatus value/transition, status timeline step, matching/assignment
logic, payment logic, wallet, model, schema, migration, or shared fixture was
modified.

## Evidence

See `docs/transport/nodes/UI-11-evidence.md` — contains the actual verification
commands/results and the exact files/lines involved. Summary:

```text
Focused regression set (2026-10-07):
  UI-11 copy + booking-route-path + rider-page + MATCH-01 (6 files)
  + assignment-release
      -> 47 passed, 0 failed            EXIT=0

Directly relevant tests after docstring correction (2026-10-07):
  tests/test_transport_cash_confirmation_semantics.py
  tests/test_ui11_booking_flash_copy.py
  tests/transport/test_match01_{assignment_race,no_match_terminals,status_json,
                                retry,silent_rejection,payload_stripping}.py
      -> 34 passed, 0 failed            EXIT=0
```

## Residual risk

The headline "Finding your driver" badge and the `pay-pill-pending` /
`pending_payment` pill mapping are unchanged; a cash booking can therefore show
"Ride request received" while `payment_status` is `PENDING`. Consistent with
the corrected semantics, but a future payment-messaging decision may want to
surface `payment_status` to the rider explicitly. Untouched here.

## Separate findings (preserved, non-blocking)

1. **`tests/test_transport_concurrent_claim.py` suite-level/shared-test-DB
   instability; not attributed to UI-11** — two full-suite failures
   (`test_discover_and_offer_creates_offer_for_confirmed_unassigned`,
   `test_dispatch_recovery_rediscovery_offers_confirmed_unassigned`; path
   `discover_and_offer → no_suitable_drivers`) both pass in isolation under
   identical code. Not labeled definitively pre-existing/parked — no
   repository evidence establishes parked status for these two tests.
2. **Matching-recovery trigger availability** — a `confirmed` booking whose
   offer expires (or is never accepted) with no recovery path can remain
   `confirmed`. Separate investigation; kept out of UI-11.
3. **Card/mobile-money payment implementation** — none performed; separate work.
4. **Future scheduled-booking/deposit/payment-policy work** — none performed;
   separate work.

## Register

The UI/UX 21-point register, DOC-201-S, DOC-202-S, A–L, GEO, and UI-LOC
registers were NOT touched, created, renamed, renumbered, or merged. Register
transcription remains the human's step (Operating System §18; §18.1 applies,
not invoked here). No register file was invented.