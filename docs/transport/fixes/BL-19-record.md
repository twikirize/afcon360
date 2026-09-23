# BL-19 — Record (moderator rejection reason accepted but not persisted)

Status:          PASS (subject to human confirmation)
Date:            2026-09-23
Owner:           [your name]

Files changed:
  - templates/transport/moderate_vehicle.html   (-4: reason form-group
    removed from reject form; flag form untouched)
  - templates/transport/moderate_driver.html    (-4: same)
  - app/transport/routes.py   (+5 -1: reject reason-required gate scoped
    to booking + BL-19 comment; hasattr/flag/booking/approve untouched)
  - tests/transport/test_moderator_actions.py   (+4 BL-19 tests)
  - docs/transport/fixes/BL-19-evidence.md   (new)

Evidence:
  See docs/transport/fixes/BL-19-evidence.md

Behavior summary:
  Vehicle/driver reject no longer asks for a reason it cannot store;
  both reject with a single confirm and persist status directly
  (vehicle.status='rejected'; driver compliance REVOKED via the existing
  service shorthand). Booking reject still requires a reason and still
  persists cancellation_reason. Flag flows unchanged (reason persisted
  via create_flag). No schema change, no migration, no authorization
  change.

Runtime verification:
  Focused file: 7 passed (3 pre-existing T-10 + 4 new BL-19).
  Regression: tests/test_transport_service_integrity.py 49 passed.
  Startup: create_app() green; all five moderate endpoints registered;
  reject pages GET 200 with no reason field (asserted in-test).

Residual risk:
  Moderators who previously typed vehicle/driver rejection rationales
  into the form now have nowhere to put them — intended per backlog
  option (b); if rationales are later wanted persisted, that is backlog
  option (a) and needs the migration pass. The admin moderator twin
  (BL-17, deferred) still renders its own forms and still silently
  discards transport reasons behind identical hasattr guards —
  deliberately untouched.

Follow-ups:
  - BL-17/BL-18 (twin-surface duplication, missing nav) unchanged.
  - Option (a) (persist reason to a real column) remains unimplemented
    by design; needs schema authorization if ever wanted.

Gate reference:
  BL-19: PASS
