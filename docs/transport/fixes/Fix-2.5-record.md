# Fix 2.5 — Record (Booking Request Points Extraction, corrected)

Status:          PASS (subject to human confirmation)
Date:            2026-09-23
Owner:           [your name]

Files changed:
  - app/transport/services/booking_service.py   (+20 -13, booking_request_points body only)
  - tests/transport/test_booking_request_points.py   (new, 3 tests + helpers + legacy oracle)
  - docs/transport/fixes/Fix-2.5-contract.md   (human-authored; amended per direction: -> supersedes ->>)
  - docs/transport/fixes/Fix-2.5-evidence.md   (new, corrected final state)

Evidence:
  See docs/transport/fixes/Fix-2.5-evidence.md

Behavior summary:
  booking_request_points() returns identical (points, skipped) to the
  legacy implementation for the full edge matrix, selecting only the two
  native JSON scalars per row via `->` and streaming with
  execution-level yield_per=1000. JSON true/false yield 1.0/0.0 points;
  "true"/"false" strings skip; null/missing skip; boundaries inclusive,
  just-outside skipped; filters (DRAFT/CANCELLED/deleted/window)
  preserved. Signature, ValueErrors, tuple shape, skip counting, and
  unordered output all preserved.

Correction note:
  First implementation used `->>` and was rejected on semantic review
  (boolean erasure). Corrected to `->` so the JSON scalar type survives
  extraction and the existing Python float()/range/skip logic stays
  authoritative. No other logic changed between v1 and v2.

Scalar proof:
  Captured statement selects exactly two BinaryExpression columns;
  compiled PostgreSQL shows exactly two `->` uses, zero `->>`.

Streaming proof:
  yield_per=1000 in statement execution options, pre-execution.

Query count:
  Exactly 1 SELECT per call, listener installed/removed in try/finally.

Runtime verification:
  Focused file: 3 passed. Full tests/transport/: 74 passed (71 baseline
  + 3 new), 2 failed — the same pre-existing marketplace owner-review
  failures proven pre-existing on the clean tree.

Residual risk:
  None material to the guarantee. Fixture rows must satisfy the DB-level
  chk_pickup_time_future (pickup_time > created_at), which lives only in
  the database, not in models.py metadata — a model/DB drift footnote.

Follow-ups:
  - Model/DB drift: chk_pickup_time_future exists in PostgreSQL but not
    in app/transport/models.py metadata. Recorded, not fixed here.
  - The 2 pre-existing test_marketplace_ux_harmonisation failures remain
    out of scope.
  - Signature kept byte-identical (no return annotation added).

Gate reference:
  Edition 2.0, Part VII, Fix 2.5
