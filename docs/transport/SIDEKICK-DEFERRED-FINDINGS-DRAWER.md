# Sidekick — Deferred Findings Drawer (DFD)

**Status:** STANDALONE CAPTURE REGISTER — out-of-scope findings observed during Sidekick work.
**Scope:** Sidekick / Location Resolution Foundation / Location Lifecycle workstreams only.

## Rules (binding)

1. This drawer is a **capture mechanism, not authorization** to implement any finding recorded here.
2. A finding recorded here is **deferred unless its owning workstream explicitly authorizes it**. Recording ≠ approval.
3. A finding that prevents an *active* Sidekick requirement from working is **not** deferred to protect the schedule — it is resolved within the active item or the item is gated BLOCKED.
4. Potentially launch-critical safety, integrity, security, or data-loss concerns are **escalated for an explicit human decision**; they are never silently shelved here.
5. This drawer is kept **strictly separate** from: the Sidekick ten-item tracker, the A–L Master Roadmap, the Fine-Grade Attention Register, the UI/UX-HARDENING register, `BACKLOG.md`, and `GEO_DEFERRED_WORK_REGISTER.md`. Do not merge, renumber, replace, or claim progress in one register based on another.
6. The drawer is **never used to claim that an active Sidekick item is complete**.
7. Each finding carries a stable ID (`DFD-NN`), evidence, status/uncertainty, deferral reason, recommended next step, scope owner, and a launch-safety note.

---

## DFD-01 — Geocoding and search responsiveness

- **Evidence/source:** Prior live measurements recorded roughly 1.2–3.1 s per Geoapify forward/reverse request (browser + service-level evidence, October 2026). Current code: 300 ms client debounce (`static/js/modules/transport/dropoff-search.js`, pickup counterpart), `AbortController` + sequence guards, server 60/min budgets, per-adapter 10 s timeouts (`app/geo/providers/geoapify.py`, `app/geo/routes.py`). No result caching exists by explicit deferral.
- **Status:** Open, non-blocking. Uncertainty: none about the measurements; open about which optimization pays off.
- **Why deferred:** Deliberately deferred to keep the Sidekick ten-item sequence focused on correctness/integrity before performance.
- **Recommended investigation order (do not implement without authorization):**
  1. Evaluate smart geocoding caching and common-place handling.
  2. Evaluate faster autocomplete approaches and appropriate Geoapify autocomplete options.
  3. Reassess provider latency and relevance using measured evidence.
- **Scope owner:** GEO provider layer (`app/geo/`).
- **Launch safety:** Not launch-blocking at the ~100 riders/day operating target; revisit if latency degrades conversion or quota headroom.

## DFD-02 — Transient PostgreSQL connection termination

- **Evidence/source:** One ORM query encountered `server closed the connection unexpectedly` (October 2026 session); subsequent direct SQL checks, including `SELECT 1`, succeeded. No recurrence observed across the Item 2 proof runs (`tests/transport/test_location_lifecycle_booking_set.py`, 5 passed) or the regression suites run alongside them.
- **Status:** Open, cause **unknown**. Uncertainty: single incident; insufficient evidence for any infrastructure conclusion.
- **Why deferred:** Single transient with no recurrence and no affected test outcome; investigating a non-reproducible single blip would interrupt active items.
- **Recommended next step:** If it recurs or affects a focused suite, preserve the full failure evidence (query, backend logs, connection-pool state) and investigate; do not restart services or alter connection configuration without authorization.
- **Scope owner:** platform/database operations.
- **Launch safety:** Not declared an infrastructure defect. Escalate for explicit decision only on recurrence with impact.

## DFD-03 — ACTUAL_START bypass via admin/CLI status transitions

- **Evidence/source:** `BookingService.transition_status` (`app/transport/services/booking_service.py:891-1009`) commits `PICKUP_ARRIVED → IN_PROGRESS` (legal edge, `STATUS_TRANSITIONS` `:182`) with no `LocationLifecycleEvent` write. Reachable via `@admin_required POST /api/transport/bookings/<id>/status` (`app/transport/api/booking_routes.py:397-449`) and dev-only `driver trip <id> start` (`app/transport/cli_driver.py:163-195`, `_ensure_dev` guard). Pinned behaviorally: `tests/transport/test_location_lifecycle_actual_start.py::test_admin_transition_bypasses_actual_start` (admin drives the edge → 200, status changes, zero events). The driver trip flow (`_execute_driver_trip_action`) always records the event.
- **Status:** Open, behavior intentional-or-oversight undecided. Uncertainty: whether operator overrides should emit lifecycle events (and with what actor semantics) is a product decision, not a code accident.
- **Why deferred:** Correcting it means touching shared admin/moderator/CLI transition paths and deciding actor semantics — broader than the Item 3 driver-flow scope; explicitly not rearchitected in Item 3.
- **Recommended next step:** Explicit product decision: (a) emit ACTUAL_START from `transition_status` for this edge, (b) refuse the edge outside the driver flow, or (c) accept the bypass with audit-log accountability as sufficient.
- **Scope owner:** transport booking-state ownership (admin/moderator flows).
- **Launch safety:** Operator-only path with audit-log entries; not a rider/driver-flow integrity issue. Decide before relying on lifecycle completeness for reporting/reconciliation.

**Owner decision (Oct 2026):** Admin Booking Management should ultimately control authorized overrides. Super Admin and Transport Admin share this capability. Any override must emit a `LocationLifecycleEvent` with `actor_user_id` = the acting admin's user id, `event_metadata.reason = "admin_override"`, and full audit provenance (correlation-id, IP, UA, session). Implementation deferred to a future admin-override node; current bypass remains as-is (DFD-03 recorded, not resolved).

## DFD-04 — Hardcoded 120 s lifecycle freshness threshold

- **Evidence/source:** `app/transport/api/driver_routes.py:548` and `app/transport/services/assignment_service.py:353` hardcode `threshold = 120` (comment claims "configurable" but no config/env read exists). The approved location freshness boundary is `TrackingService.LOCATION_TTL_SECONDS = 300` (`app/transport/services/tracking_service.py:26`), used by availability/matching/GEO.
- **Current implementation behavior (verified by Item 5 tests):** a ~115 s observation classifies `fresh`, a ~125 s observation classifies `stale` (`stale_beyond_threshold`), linkage stays honest, stale freshness never blocks `IN_PROGRESS`/`COMPLETED`. Age tolerance ±10 s by design; exact 120 s boundary NOT tested. Tests must not be read as approval of the 120 s threshold.
- **Owner decision (Oct 2026):** Initial freshness threshold = 60 seconds (not 120). Support a 30‑second minimum for high‑precision modes. Value configurable system‑wide via Transport Settings. System Health must alert when observed freshness exceeds **twice** the configured threshold for any active trip.
- **Status:** `OWNER DIRECTION RECORDED / IMPLEMENTATION DEFERRED`.
- **Scope owner:** transport location policy (future freshness node).
- **Launch safety:** Metadata‑only; no correctness impact on transitions, linkage, or atomicity.

## DFD-05 — Stale supply-model assertions vs SUPPLY-00a availability invariant

- **Evidence/source (refreshed Oct 2026, actual runs):** WITH the uncommitted Item 4 diff (`assignment_service.py`: actor fix + capture reorder): 6 failed, 22 passed, exit 1 — `TestBookingCancellation::test_dispute_latches_then_cancel_releases`, `TestBookingCancellation::test_illegal_in_progress_to_cancelled_refused`, `TestExecutionConcurrency::test_start_before_no_show_blocks_no_show`, `TestRecoveryVsProgress::test_progress_before_recovery_keeps_trip`, `TestModeratorBookingActions::test_moderator_reject_in_progress_blocked`, `TestModeratorBookingActions::test_moderator_reject_requires_reason`. WITHOUT that diff (file stashed, HEAD code): 10 failed, 18 passed, exit 1 — the same 6 plus `TestDriverTripEndpoint::test_full_trip_happy_path_and_canonical_completion`, `TestDriverTripEndpoint::test_reference_keyed_full_lifecycle`, `TestResourceSafetyAfterTerminal::test_driver_vehicle_reusable_after_completion`, `TestModeratorBookingActions::test_moderator_reject_completed_blocked` (all four break on the pre-fix capture path Item 4 repairs, so the diff strictly improves 10→6 and the 6 are identical in both runs). Representative assertion shape (`tests/test_transport_d5_execution_lifecycle.py:922`): `assert _drv_field(app, drv, "is_available") is False` observes `True` (profile 330). Meanwhile `assignment_service.py:210-212,454-463` (SUPPLY-00a) states `is_available` means "qualified", is NOT affected by trip lifecycle, and busy protection comes from booking status — yet the claim path still writes `is_available=False` (`assignment_service.py:256`) and these tests still assert the old predicate. Three mutually inconsistent positions (comments vs write path vs tests); lifecycle event rows have no readers in `app/` (verified Oct 2026: 11 grep matches, all model definition, relationship join, or the three write sites — zero SELECT consumers), so the lifecycle work neither causes nor can resolve this. Causality is not inferred from failure order: the 6 fail identically on HEAD code without the Item 4 diff.
- **Status:** Open, pre-existing. Uncertainty: whether the intended invariant is flag-based (fix code to match tests), status-based (fix tests to match SUPPLY-00a), or a session-staleness artifact in `_drv_field` reads (Core updates use `synchronize_session=False`; reads do not expire/refresh).
- **Why deferred:** Deciding the availability-model truth belongs to the supply/assignment owners; changing either code or tests here would prejudge that decision and exceed lifecycle scope.
- **Recommended next step:** Owner decision on the invariant, then align exactly one of: the claim/release writes, or the six assertions (plus a staleness audit of `_drv_field`-style reads).
- **Scope owner:** transport supply/assignment ownership.
- **Launch safety:** Test-suite signal only; no production behavior changed by this finding. Escalate if fleet-availability reads are suspected wrong at runtime.

## DFD-06 — Offer-holder timing failure in the Playwright browser harness

- **Evidence/source:** `test-results/zz_e2e_run2b-item4-run2b-T-958f2-rch-full-cycle-to-COMPLETED/error-context.md` — `expect(holder).not.toBeNull()` after a 100 s concurrent poll of three driver dashboards for `.ck-focus--offer` carrying the run's own booking ref; artifacts retained: 4 PNG screenshots + 46 MB `trace.zip`. The run's rider journey (map pickup + `Acacia Mall` search destination, comfort class, cash confirm) reached the rides page, so the booking existed; no driver dashboard rendered the offer card within the poll window.
- **Status:** Open, harness-level. Uncertainty: the short Redis offer TTL (25 s) plus multi-context dashboard rendering makes a harness timing race plausible, but equivalent behavior under slow real-client conditions remains unverified. This is NOT classified as an app defect and NOT cleared as harness-only; either claim needs slow-client evidence.
- **Why deferred:** Dispatch, accept, and trip actions are each proven repeatedly through the same harness and endpoints (CF7MAD 17 s full cycle with fresh/fresh GPS events; VKMXKI 4-event chain; staged Q9YHLP/FTGUJB ends); one missed-holder run does not block Items 3/4, and changing TTL/dispatch policy to chase it would exceed scope.
- **Orphaned-booking disclosure:** the failed run's booking reference was not captured (reporter filter hid the booking log); its row remains confirmed/unassigned in `afcon360_test` — fleet-harmless (no driver/vehicle held) but unaccounted. Rebuild the test DB (`python scripts/setup_test_db_schema.py`) before the next browser campaign.
- **Recommended next step:** No TTL, dispatch, or application change without explicit contract approval. If re-attempted: log the booking ref first, then compare dispatch timestamp vs first-render timestamp to separate TTL-expiry from render-miss.
- **Scope owner:** browser-harness/test infrastructure (temp specs `tests/browser/zz_e2e_run*.spec.js`).
- **Launch safety:** Test-harness signal only; no production behavior implicated. Escalate only with slow-real-client evidence.

**Owner decision (Oct 2026):** The 25 s offer TTL is too short for the intended driver experience (network variance, device wake, app-switch latency). On expiry the offer must automatically re-dispatch to the next eligible driver (same booking, new TTL). The overall search must be bounded (max N re-dispatches or max total search time). Benchmark 60 s vs 90 s TTL under load before selecting the final timer. No timer or dispatch changes in this workstream; the 25 s TTL and single-dispatch behavior stay as-is (DFD-06 recorded, not resolved).

## DFD-07 — Database & location-ingestion capacity monitoring

- **Evidence/source:** Projected scale target of **100,000 concurrent online drivers** requires measured evidence of database pressure and location-write throughput. Current stack: PostgreSQL + Redis + Celery; location writes via `TrackingService.update_location` → `LocationObservation` table; matching reads via `availability_service.py` freshness window (300 s TTL). No production‑grade capacity metrics or alerting have been captured in this work.
- **Status:** Open, future work. Uncertainty: write latency under load, replication lag (if replication is used), queue backlog growth, connection‑pool saturation — none measured.
- **Why deferred:** Not in current Sidekick scope (Items 1–10). Freshness alerting (DFD-04) is not a substitute for database-capacity monitoring.
- **Recommended signals for future capacity node:** location-write p95 latency, rows/sec sustained, Redis memory pressure, Celery queue depth, DB CPU/IOPS, replication lag (conditional on replication being used). Alerting thresholds for Owner / Super Admin / Transport Admin via System Health.
- **Scope owner:** platform/database operations + transport matching/availability.
- **Launch safety:** No production behavior change. Escalate when scale testing begins.

## DFD-08 — Booking/offer inconsistency: transient offer for a booking with no persisted row (TR261010GVHZV0)

- **Evidence/source (2026-10-10, HTTPS 5443 Playwright run):** `server.log.err` recorded `Offer created for booking TR261010GVHZV0 -> driver 1 (ttl=25s)` and `-> driver 164` at 14:32:28, immediately followed at 14:32:30/30/35 by three `offer enrichment: no booking row for TR261010GVHZV0 (stale index); serving thin offer` lines. Direct SQL against `afcon360_test` found **zero** `transport_bookings` rows for that reference *including soft-deleted rows*; the read-only probe returned `found:false`. The run's driver journey timed out (`page.waitForResponse` on a `POST /trips/`) and never completed; no accept/claim/trip transition lines for the reference appear in the server log.
- **Status:** Open. Reason the booking row was absent: **UNKNOWN**. Uncertainty: the booking row was never observed persisted — whether the booking-creation transaction was rolled back after transient-offer dispatch, a commit/connection failure occurred, or another removal path acted is not reconstructable from retained artifacts (the run's trace/`https5443-results.json` were not preserved).
- **Why deferred:** Further reproduction and root-cause investigation deferred by the current owner direction. This is **not labelled a confirmed production defect**; the identical accept→transition→release path completed the same day for `TR2610100YIAOF` on the same server.
- **Distinct from DFD-06:** DFD-06 is an offer-holder timing miss on a run whose booking **did** exist. DFD-08 is the inverse — offers were dispatched for a booking that no persisted row backed.
- **Recommended next step:** If re-attempted: retain the full Playwright trace plus request/response bodies for the ride-options, booking-create, and driver `POST /trips/` endpoints, and server SQL logs; compare the offer dispatch timestamp against the enrichment timestamp. Do not change booking, dispatch, or TTL code without a separate authorized contract.
- **Scope owner:** browser-harness/test infrastructure + transport booking/dispatch verification.
- **Launch safety:** The booking row never persisted → fleet-harmless (no driver/vehicle assignment, no payment). A transient offer for a non-existent booking can surface a stale driver card; escalate for explicit decision if a re-run shows real booking-create persistence failures.

## UI-16-A note -- test_beat_closes_expired_window_as_no_supply single grouped-run failure (test reliability, NOT a product defect)

- **History:** 2026-10-10/11 -- failed once inside a 4-file grouped pytest run (test_match01_no_match_terminals + retry + recovery_beat + silent_rejection: 24 passed, 1 failed). Passed alone immediately after (1 passed). Passed in a focused-group re-run (25 passed). Passed again in a fresh UI-16-A bounded reproduction (25 passed, exit 0).
- **Reproduced:** NO -- three consecutive passes after the single failure.
- **Likely cause:** timing-sensitive beat test under grouped-run load (wall-clock window expiry racing parallel test setup), not MATCH-01 behavior. No source or test change made; behavior and test intentionally untouched.
- **Scope owner:** transport matching verification (UI-16-A workstream note only).
- **Launch safety:** none -- test-harness signal only.

## Pre-existing test failures in tests/transport/ (baseline, not regressions)

- **Status:** Known; not a regression; out of scope for Phase A.
- **Count:** 10
- **Files / tests:**
  - `tests/transport/test_booking_request_points.py::test_same_output_as_legacy_for_controlled_fixture`
  - `tests/transport/test_driver_console.py` (4 tests)
  - `tests/transport/test_marketplace_ux_harmonisation.py` (2 tests)
  - `tests/transport/test_public_endpoint_rate_limits.py` (3 tests)
- **Proof of pre-existing status:** stashing only the Phase A-changed paths and re-running produces the identical 6 non-console failures. The 4 `test_driver_console` failures target `/transport/driver-console`, a route not defined anywhere in the codebase.
- **Action:** None in this node. Separate investigation if desired.
- **Reference:** `docs/transport/SCHEMA-ADOPTION-PLAN.md` §12 (Note A).
