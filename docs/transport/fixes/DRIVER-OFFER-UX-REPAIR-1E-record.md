# DRIVER-OFFER-UX-REPAIR-1E — Record (Passenger First Name on Driver Offer Surface)

Status:          PASS (human-confirmed 2026-09-26)
Date:            2026-09-26
Owner:           [your name]

Files changed:
  - app/transport/services/offer_service.py   (+93 -4: passenger field in
    enrich_offer, docstring contract update, _passenger_first_name_or_none,
    _first_name_token)
  - templates/transport/driver/driver_dashboard.html   (4 passenger-only
    insertions in offer focus card + list card; file also carries a
    concurrent actor's workspace hunks — NOT this node)
  - tests/transport/test_driver_offer_passenger_first_name.py   (new, 8 tests)
  - docs/transport/fixes/DRIVER-OFFER-UX-REPAIR-1E-evidence.md   (new)
  - docs/transport/fixes/DRIVER-OFFER-UX-REPAIR-1E-record.md   (new)

Evidence:
  See docs/transport/fixes/DRIVER-OFFER-UX-REPAIR-1E-evidence.md

Behavior summary:
  Driver pre-accept offers now carry passenger {first_name}: canonical
  transport passenger row first (name → linked user display), else the
  booking creator's display_name for self-bookings (which write no
  passenger row). First whitespace token only; @-shaped values rejected;
  any derivation failure omits the key with a warning — offers never fail.
  API and both dashboard offer cards render "Passenger: <first>" ahead of
  pickup/destination/fare. Absent key renders the pre-1E layout unchanged.

Verification:
  Focused suite 8 passed (first run 6 failed — root-caused to the test
  helper not committing after add_passenger's flush; fixed in test only).
  Regression: 70 passed / 12 failed — all 12 proven concurrent-actor
  (4 x driver-console 404s from removed route; 8 x workspace sections from
  in-flight consolidation). Offer contract suite (other actor's file)
  green including its forbidden-fields PII list. APP_IMPORT_OK.

Residual risk:
  driver_dashboard.html is edited by two actors at once — this node's 4
  hunks can be clobbered by the other actor's next write; re-verify
  `Passenger:` lines after that work lands. Passenger visibility depends
  on callers committing after add_passenger (existing behavior, unchanged).

Follow-ups:
  - 12 concurrent-actor test failures (test_driver_console x4 stale for
    removed route; test_driver_workspace_sections x8) belong to that
    actor's node; recorded, not fixed.
  - Split-node leftovers: BACKLOG entries (rider chat, orphan extra_js in
    org/* templates), HTTPS server restart + live verify of rider/admin
    page split.
  - Booking 15 (TR260925V8YVPW) still ASSIGNED to driver 179 — open
    disposition decision.
  - NOTIF-BELL-SYSTEM-SOUND-1 recorded separately (same day).

Gate reference:
  DRIVER-OFFER-UX-REPAIR-1E node spec (user-provided, this session).
