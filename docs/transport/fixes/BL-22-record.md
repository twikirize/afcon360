# BL-22 — Record (driver never notified on assignment)

Status:          PASS (subject to human confirmation)
Date:            2026-09-23
Owner:           [your name]

Files changed:
  - app/notifications/services.py   (+7 -1, isolated hunk
    @@ -1976,7 +1976,14: transport driver branch resolves
    Booking.driver → user_id; non-transport branch unchanged)
  - tests/test_notify_driver_assigned_bl22.py   (new, 1 behavioral test)
  - docs/transport/fixes/BL-22-evidence.md   (new)

Evidence:
  See docs/transport/fixes/BL-22-evidence.md

Behavior summary:
  notify_driver_assigned on a transport booking now addresses the
  "New Trip Assigned" notification to the assigned driver's User
  (via the canonical Booking.driver relationship), with the booking
  reference in data. Rider SMS, admin broadcast, and non-transport
  behavior unchanged.

Runtime verification:
  New test: FAILED pre-fix (calls went to rider twice, driver never),
  1 passed post-fix. Existing notification file: 4 passed.
  Transport integrity: 49 passed. Startup: factory + imports green.

Residual risk:
  The naive backlog shorthand (assigned_driver_id as recipient) would
  have misaddressed to a profile id; the fix resolves to the profile's
  user instead. If a future caller passes a detached Booking whose
  relationship cannot lazy-load, the driver branch yields no
  notification rather than raising (listener contains exceptions) —
  same failure mode as before the fix, not a regression.

Follow-ups (recorded, NOT started — out of scope):
  - No producer of the transport_driver_assigned signal exists in
    app/ today; live dispatch_claim notifies the passenger directly.
    Wiring production emission is a product/dispatch decision, not
    taken in this node.

Gate reference:
  BL-22: PASS (last item of the current cleanup batch)
