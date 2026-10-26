# CANCEL-FEE-SCHEDULED-P1 — Record

Status:          PASS (node scope; see deviations)
Commit:          this node commit (sha reported in the final report)
Date:            2026-10-26
Owner:           Agent (implementation, evidence, record) / human register

Files changed:
  - app/transport/services/booking_service.py               (+478 -59)
  - app/transport/api/driver_routes.py                      (+31 -1)
  - app/transport/routes.py                                 (+37 -2)
  - templates/transport/driver/driver_dashboard.html        (+15 -3)
  - templates/transport/rides/show.html                     (+41 -26)
  - tests/transport/test_cancel_fee_scheduled_p1.py         (new, 470 lines)
  - docs/transport/nodes/CANCEL-FEE-SCHEDULED-P1-contract.md (new, 264 lines)
  - docs/transport/nodes/CANCEL-FEE-SCHEDULED-P1-evidence.md (new, 371 lines)
  - docs/transport/nodes/CANCEL-FEE-SCHEDULED-P1-record.md   (new, this file)
  - BACKLOG.md                                              (+55 -0)

Behavior:
  Scheduled rider cancellations now use the server-owned tier policy
  (>1h 0%; 15m–1h 20% capped at 10,000; <15m 40% capped at 20,000;
  safety/instant/mode-less/non-rider 0%), record the fee as uncollected
  with audit metadata, and append an 80% driver credit without touching
  the wallet. The assigned driver can record a no-show only after
  pickup_arrived and the 15-minute grace; the no-show fee is 40% (cap
  20,000), the driver credit is 100%, the transition uses
  transition_status(NO_SHOW), and a second call is idempotent. Rider
  copy uses the server preview; the driver dashboard gates the action
  server-side.

Evidence:
  See docs/transport/nodes/CANCEL-FEE-SCHEDULED-P1-evidence.md

Runtime verification:
  pytest tests/transport/test_cancel_fee_scheduled_p1.py -q
    → 16 passed, 2 warnings in 58.73s
  P1 gate (pickup authority, mode probe, scheduled release, route capacity)
    → 46 passed, 42 warnings in 101.07s
  match01 retry + UI14F1 + UI14 D5 wording
    → 22 passed, 2 warnings in 48.30s
  tests/test_transport_concurrent_claim.py
    → 29 passed, 22 warnings in 56.71s
  tests/test_transport_d5_execution_lifecycle.py
    → 6 failed, 22 passed, 95.71s (pre-existing SUPPLY-00a stale assertions;
      not caused by this node; see evidence §7.2)
  app factory
    → DB_VERIFY_OK
  flask db heads / current
    → 1793013676 (head)

Browser verification (Playwright MCP, isolated test DB, port 5611):
  - Rider previews: +2h → no fee; +45m → USD 20.00; +10m → USD 40.00.
  - Driver: no “Rider no-show” before grace; button appears after grace.
  - End-to-end driver click: confirmation shown; booking persisted as
    no_show, fee 40.00, stage pickup_arrived, initiated_by driver;
    no_show metadata (D3DRV001, USD, uncollected, grace 15) and
    driver_cancellation_credits (reason no_show, 40.00, uncollected)
    recorded.
  - Screenshots: .playwright-mcp/driver-no-show-before-grace.png and
    .playwright-mcp/driver-no-show-after-grace.png.

Deviations / disclosures:
  - Contract header records previous node b5b5a7a and baseline
    1793011323. Actual parent is b9dabb8 (concurrent M3 correction);
    actual heads/current is 1793013676. This node adds no migration.
  - Contract §6 item 9 (“existing D5 remain green”) cannot be met at
    baseline: six D5 tests assert is_available changes that SUPPLY-00a
    already removed. They are recorded as TRANSPORT-D5-SUPPLY00A-STALE-01
    in BACKLOG.md and were not modified.
  - Production was not touched by this node. The concurrent M3 commit
    recorded production at 1793013676.

Residual risk:
  Fees and driver credits remain metadata facts. There is no collection,
  refund execution, reconciliation, FX policy, or driver earnings ledger.
  The rider preview can become stale if the pickup crosses a tier
  boundary before confirmation; the server recalculates and its returned
  fee is authoritative. No-show idempotency is proven sequentially;
  concurrent no-show calls are not serialized by an explicit row lock.
  The no-show action is driver-only. D5 remains red at baseline.

Follow-ups:
  - CANCEL-FEE-COLLECT-P1 (OPEN): collect/refund/reconcile scheduled fees.
  - DRIVER-EARNINGS-LEDGER-P1 (OPEN): settle driver metadata credits.
  - ADMIN-NO-SHOW-FEE-P1 (OPEN): authorized admin/moderator no-show path.
  - CANCEL-FEE-FX-P1 (OPEN): base-currency caps and FX policy.
  - TRANSPORT-D5-SUPPLY00A-STALE-01 (OPEN): reconcile six stale D5 tests.

Gate reference:
  Owner directive “Plan is final. Execute.”; contract
  CANCEL-FEE-SCHEDULED-P1. Human review of the contract, evidence, and
  record occurs in the same node commit. Human owns the register update.

Gate: PASS (node scope) — with the baseline/contract deviations above
recorded for human review.
