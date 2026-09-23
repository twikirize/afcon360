# BL-19 — Evidence (moderator rejection reason accepted but not persisted)

Status:          PASS (subject to human confirmation)
Date:            2026-09-23
Scope:           transport moderate vehicle/driver reject path only
Option taken:    backlog option (b) — remove the reason field from the
                 vehicle/driver forms. Option (a) (persist via new column)
                 requires a schema change / migration pass and is NOT
                 authorized in this node (AGENTS.md red lines).

## 1. UNDERSTAND (source of truth)

- BACKLOG.md §BL-19 (Not started, raised 2026-09-22, T-10 side finding,
  DEFERRED / TRANSPORT, owner Transport/Moderation, record-only
  authorization, implemented under this EGGE cleanup node).
- Referenced docs read: docs/transport/fixes/T-10-evidence.md,
  docs/transport/fixes/T-10-record.md.
- Category: misleading-UI cleanup (mandatory-but-discarded form input),
  not dead code.
- BL-19 text: "either add an optional reason parameter that writes to a
  real column (requires schema change — batch with the migration pass),
  or remove the reason field from the vehicle/driver forms so moderators
  aren't misled."

## 2. MAP (classification)

| Reference | Classification |
|-----------|----------------|
| templates/transport/moderate_vehicle.html reject `reason` textarea (required) | LIVE CONSUMER of misleading field → removed |
| templates/transport/moderate_driver.html reject `reason` textarea (required) | LIVE CONSUMER of misleading field → removed |
| templates/transport/moderate_booking.html cancel `reason` | LIVE CONSUMER of persisting path (cancellation_reason) → kept |
| all three flag-form `reason` fields | LIVE CONSUMER of persisting path (create_flag) → kept |
| app/transport/routes.py moderate_action reject branch | LIVE — reason gate scoped to booking |
| tests/transport/test_moderator_actions.py vehicle reject WITH reason | TEST CONSUMER → still passes (extra field tolerated) |
| app/admin/moderator/routes.py twin (BL-17) | separate deferred surface → untouched |

Templates moderate_vehicle/driver/booking.html are rendered ONLY by
transport.moderate_vehicle/driver/booking (no other render callers).

## 3. TRACE (ownership chain)

- Vehicle: form reason → route `hasattr(item,'rejection_reason')` guard →
  False (no such column anywhere in app/transport/models.py; repo-wide
  `rejection_reason` hits are events/KYC/wallet/etc.) → discarded.
- Driver: form reason → `update_driver_status(id,'rejected')`, signature
  (driver_id, status_data, user_id=None), no reason parameter →
  discarded ('rejected' → ComplianceStatus.REVOKED).
- Booking: form reason → `item.cancellation_reason = reason` → persisted.
- Flag: form reason → `create_flag(...)` → persisted.

## 4. PROVE (before fix)

- Baseline: tests/transport/test_moderator_actions.py 3 passed.
- New BL-19 tests run pre-fix: 3 failed, 1 passed —
  vehicle/driver reject WITHOUT reason bounced with a warning redirect
  and no status change (mandatory-but-discarded proven); booking
  without-reason bounce / with-reason persist passed pre-fix
  (preservation baseline).

## 5. MINIMAL CHANGE

- templates/transport/moderate_vehicle.html: removed the 4-line
  reason form-group from the reject form only (confirm/cancel kept).
- templates/transport/moderate_driver.html: same.
- app/transport/routes.py moderate_action reject: `if not reason` →
  `if entity_type == 'booking' and not reason` (+ BL-19 comment).
  hasattr guard, flag branch, booking branch, approve branch untouched.
- tests/transport/test_moderator_actions.py: +4 BL-19 tests.
- NOT touched: decorators.py (security), provider_service.py,
  models/schema (no migration), admin twin, KYC/wallet/GEO/matching.

## 6. VERIFY (after fix)

- tests/transport/test_moderator_actions.py: 7 passed (3 T-10 + 4 BL-19).
- tests/test_transport_service_integrity.py: 49 passed.
- Post-fix template grep: vehicle/driver pages contain no
  "Rejection Reason"; flag forms + booking form intact.
- Full suite NOT run (out of scope; exact totals above).

## 7. STARTUP

- create_app() completes; transport.moderate, .moderate_action,
  .moderate_vehicle, .moderate_driver, .moderate_booking all registered.
- Reject pages GET 200 with no reason field (asserted in-test).

## 8. GATE

BL-19: PASS — scope confirmed; misleading input removed; vehicle/driver
reject works without a reason; booking/flag reason paths preserved;
focused + regression tests pass; startup clean.
