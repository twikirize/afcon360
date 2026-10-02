# AFCON360 Fine-Grade — Working Master Register

**File:** `C:\Users\OBED\Desktop\afcon360_app\fine tuning transport.md`

**Purpose:** Agent-facing working register and evidence record.

**Rule:** Read this file before starting work. Work only on the assigned register ID. Bring current source evidence into every implementation report. Update the assigned row after implementation and verification.

**Control authority:** The human/control session authorizes product decisions, scope changes, ownership changes, implementation, and closure.

**Repository:** Source code remains the technical source of truth. This register is the control/evidence index.

## Agent Working Protocol

Before work:
1. Read this register.
2. Locate the assigned ID.
3. Read its current state and evidence.
4. Confirm ownership and file/function scope.
5. Check for conflicting active workstreams.

Before implementation:
1. Bring the current relevant source code into the report.
2. State the invariant/problem.
3. Give exact evidence.
4. Give the exact Find/Replace or diff.
5. State the tests.
6. STOP for approval when the node is plan-gated.

After implementation:
1. Report files changed.
2. Report the actual correction.
3. Report exact tests and results.
4. Inspect the final diff.
5. Update the assigned register row.
6. Gate the node.

Never silently change another register item.
Never infer a product decision.
Never mark an item CLOSED without verification.

---

# TABLE 1 — A–L FINE-GRADE REGISTER

| # | Problem | Workstream / Owner | File / Function | Problem Definition + Code Evidence | Correction | Verification / Remarks / State |
|---|---------|-------------------|-----------------|-----------------------------------|------------|-------------------------------|
| **A — Rider Journey** | | | | | | |
| A1 | Journey-state presentation missing | Transport / Rider Journey | UNASSIGNED / DECISION REQUIRED | Not started. No implementation evidence. | PROPOSED: Implement journey-state presentation UI/UX | OPEN |
| A2 | Ride-selection card lifecycle incomplete | Transport / Rider Journey | UNASSIGNED / DECISION REQUIRED | Not started. No implementation evidence. | PROPOSED: Define and implement ride-selection card lifecycle | OPEN |
| A3 | Progress indicator missing | Transport / Rider Journey | UNASSIGNED / DECISION REQUIRED | Overlaps MATCH-01 — coordinate with matching panel. | PROPOSED: Implement progress indicator coordinated with MATCH-01 | OPEN |
| A4 | Matching-panel cleanup needed | Transport / Rider Journey | UNASSIGNED / DECISION REQUIRED | Overlaps MATCH-01 relabel. | PROPOSED: Clean up matching panel per MATCH-01 relabel | OPEN |
| A5 | Chronological timeline gap | Transport / Rider Journey | UNASSIGNED / DECISION REQUIRED | Trip Started timestamp gap on quick IN_PROGRESS→COMPLETE (Node 7). | PROPOSED: Fix timestamp gap in timeline | OPEN |
| A6 | Conflicting wording in rider journey | Transport / Rider Journey | UNASSIGNED / DECISION REQUIRED | Overlaps MATCH-01b. | PROPOSED: Resolve wording conflicts with MATCH-01b | OPEN |
| A7 | Assignment moment | Transport / Rider Journey | Live-proven | Live-proven. Works correctly. | ACTUAL: No correction needed | **CLOSED — Live-proven** |
| A8 | Live tracking after assignment — marker displacement unproven | Transport / Rider Journey | Node 7: marker + SSE proven live | Marker + SSE proven live. Marker displacement unproven (stationary driver) — needs L-A8-move. | PROPOSED: Verify marker displacement with moving driver | **PARTIAL** — Source + Node 7 proven; displacement needs L-A8-move |
| A9 | No-reload completion | Transport / Rider Journey | Source + tests | Source + tests exist. Live confirmation pending. | PROPOSED: Live verification of no-reload completion | **VALIDATION** — Source + tests; live confirmation pending |
| A10 | Live transition latency | Transport / Rider Journey | UNASSIGNED / DECISION REQUIRED | Live measurement pending. | PROPOSED: Measure and optimize live transition latency | **VALIDATION** — Live measurement pending |
| A11 | Driver-card single-source strategy deferred | Transport / Rider Journey | UNASSIGNED / DECISION REQUIRED | Deferred. | FUTURE / NOT IMPLEMENTED | OPEN — Deferred |
| A12 | Rider cancellation capability | Transport / Rider Journey | Migration 0050d44787c5 applied; 81 tests pass | CORE CLOSED / BACKLOG. Migration applied, 81 tests pass. Subitems remain. | ACTUAL: Migration 0050d44787c5 applied | **CORE CLOSED / BACKLOG** — 81 tests pass; subitems open |
| A12-P0 | Cancel modal typo (getElementElementById) | Transport / Rider Journey | Agent 2 confirmed getElementElementById absent — paste artifact | Confirmed paste artifact. Not a real code issue. | ACTUAL: Confirmed paste artifact; no code change needed | **CLOSED** — Confirmed paste artifact |
| A12a | Backend stage gate + reason + safety flag + release | Transport / Rider Journey | Test-proven | Test-proven. Backend stage gate with reason, safety flag, and release works. | ACTUAL: Implemented and test-proven | **CLOSED** — Test-proven |
| A12b | Fee sensitivity by stage/driver effort | Transport / Rider Journey | UNASSIGNED / DECISION REQUIRED | PARTIAL — decision needed (age-based vs stage multipliers). | DECISION REQUIRED | **PARTIAL** — Decision needed (age-based vs stage multipliers) |
| A12c | Admin/privileged cancellation semantics | Transport / Rider Journey | UNASSIGNED / DECISION REQUIRED | Needs audit proof. | PROPOSED: Implement audit proof for admin cancellation | **PARTIAL** — Needs audit proof |
| A12d | Pre-assignment safety audit coverage | Transport / Rider Journey | UNASSIGNED / DECISION REQUIRED | Needs proof. | PROPOSED: Implement pre-assignment safety audit coverage | **PARTIAL** — Needs proof |
| A12e | Driver notification on cancel | Transport / Rider Journey | Source-proven only | Source-proven only. Not live-proven. | PROPOSED: Live verification of driver notification | **PARTIAL** — Source-proven only |
| A12f | Live rider cancel journey | Transport / Rider Journey | UNASSIGNED / DECISION REQUIRED | Not live-proven. | PROPOSED: Live verification of rider cancel journey | **PARTIAL** — Not live-proven |
| A12g | Anti-abuse enforcement | Transport / Rider Journey | Evidence foundation only | Evidence foundation only. No implementation yet. | PROPOSED: Implement anti-abuse enforcement | **PARTIAL** — Evidence foundation only |
| A12h | Migration execution | Transport / Rider Journey | Migration 0050d44787c5 applied | Migration executed successfully. | ACTUAL: Migration 0050d44787c5 applied | **CLOSED** — Migration executed |

| **B — Contact / Privacy** | | | | | | |
| B1 | Public driver-data contract — verify PII exposure | Transport / Contact & Privacy | UNASSIGNED / DECISION REQUIRED | OPEN — verify PII exposure. | PROPOSED: Audit and fix PII exposure in driver data contract | **OPEN** — Verify PII exposure |
| B2 | Phone/contact lifecycle decision | Transport / Contact & Privacy | POLICY / CONTROL SESSION | OPEN — decision required. | DECISION REQUIRED | **OPEN** — Decision required |
| B3 | Call action | Transport / Contact & Privacy | UNASSIGNED / DECISION REQUIRED | OPEN. | PROPOSED: Implement call action | OPEN |
| B4 | Chat | Transport / Contact & Privacy | UNASSIGNED / DECISION REQUIRED | OPEN. | PROPOSED: Implement chat functionality | OPEN |
| B5 | Post-trip contact expiry | Transport / Contact & Privacy | POLICY / CONTROL SESSION | DECISION (Tier 1 privacy). | DECISION REQUIRED | **DECISION** — Tier 1 privacy; control session required |

| **C — Matching / Availability** | | | | | | |
| C1 | Matching/no-supply bound | Transport / Matching | Implemented in-tree | CLOSED. Implemented in MATCH-01 backend state. | ACTUAL: Implemented in MATCH-01 | **CLOSED** — Implemented in-tree |
| C2 | Empty-state CTA | Transport / Matching | Implemented in MATCH-01 | CLOSED / VALIDATION. Implemented in MATCH-01 rider projection. | ACTUAL: Implemented in MATCH-01 | **CLOSED / VALIDATION** — Implemented in MATCH-01 |
| C3 | VIP empty wording | Transport / Matching | UNASSIGNED / DECISION REQUIRED | OPEN. | PROPOSED: Implement VIP empty wording | OPEN |
| C4 | VIP controlled proof | Transport / Matching | UNASSIGNED / DECISION REQUIRED | OPEN. | PROPOSED: Implement VIP controlled proof | OPEN |
| C5 | Service-switch refresh | Transport / Matching | UNASSIGNED / DECISION REQUIRED | OPEN. | PROPOSED: Implement service-switch refresh | OPEN |
| C6 | Online vs matchable | Transport / Matching | Supply Eligibility Contract defines; admin gate bypass | OPEN — Supply Eligibility Contract defines; admin gate bypass. | PROPOSED: Enforce matchability per Supply Eligibility Contract | **OPEN** — Supply Eligibility Contract defines; admin gate bypass |
| C7 | Stale-online hygiene | Transport / Matching | Must be read-only projection | OPEN — must be read-only projection. Linked to D8. | PROPOSED: Implement read-only projection for stale-online | **OPEN** — Must be read-only projection; linked to D8 |
| C8 | Release → matchability semantics | Transport / Matching | POLICY / CONTROL SESSION | DECISION required. | DECISION REQUIRED | **DECISION** — Control session required |
| C9 | Multi-candidate redispatch | Transport / Matching | UNASSIGNED / DECISION REQUIRED | FUTURE. Not implemented. | FUTURE / NOT IMPLEMENTED | FUTURE |
| C10 | Matching observability | Transport / Matching | UNASSIGNED / DECISION REQUIRED | FUTURE. Not implemented. | FUTURE / NOT IMPLEMENTED | FUTURE |

| **D — Driver Location** | | | | | | |
| D1 | Immediate first GPS | Transport / Driver Location | UNASSIGNED / DECISION REQUIRED | PARTIAL / DEFERRED. | PROPOSED: Implement immediate first GPS | **PARTIAL / DEFERRED** |
| D2 | Heartbeat reliability | Transport / Driver Location | Evidence + Node 8 trace | CLOSED. Heartbeat reliability proven. | ACTUAL: Verified via D2 evidence + Node 8 trace | **CLOSED** — Evidence + Node 8 trace |
| D3 | Background driver behaviour | Transport / Driver Location | pagehide/pageshow gap candidate; L8 pending | PARTIAL — pagehide/pageshow gap candidate; L8 pending. | PROPOSED: Fix pagehide/pageshow gap; complete L8 | **PARTIAL** — pagehide/pageshow gap candidate; L8 pending |
| D4 | Permission recovery | Transport / Driver Location | Verified | CLOSED. Works. | ACTUAL: Verified working | **CLOSED** |
| D5 | 300s freshness gate | Transport / Driver Location | Verified | CLOSED. Enforced. | ACTUAL: Verified working | **CLOSED** |
| D6 | Stale-location UI | Transport / Driver Location | Verified | CLOSED. Works. | ACTUAL: Verified working | **CLOSED** |
| D7 | Location recovery | Transport / Driver Location | Verified | CLOSED. Works. | ACTUAL: Verified working | **CLOSED** |
| D8 | Stale-online auto-offline | Transport / Driver Location | POLICY / CONTROL SESSION | DECISION — linked to C7. | DECISION REQUIRED | **DECISION** — Linked to C7; control session required |
| D9 | Location latency observability | Transport / Driver Location | UNASSIGNED / DECISION REQUIRED | PARTIAL. | PROPOSED: Implement location latency observability | **PARTIAL** |
| D10 | Active-trip cadence | Transport / Driver Location | UNASSIGNED / DECISION REQUIRED | FUTURE. Not implemented. | FUTURE / NOT IMPLEMENTED | FUTURE |
| D11 | Movement-triggered updates | Transport / Driver Location | UNASSIGNED / DECISION REQUIRED | FUTURE. Not implemented. | FUTURE / NOT IMPLEMENTED | FUTURE |
| D12 | Truthful location age | Transport / Driver Location | Verified | CLOSED. Implemented. | ACTUAL: Verified working | **CLOSED** |

| **D3-adjacent backlog (proposed)** | | | | | | |
| D3-b1 | pagehide/pageshow restart gap | Transport / Driver Location | L8 confirmation required | Proposed backlog item. L8 confirmation required. | PROPOSED: Fix pagehide/pageshow restart gap | PROPOSED — L8 confirmation required |
| D3-b2 | admin is_online without location age | Transport / Driver Location | Linked to D8/C7 | Proposed backlog item. Linked to D8/C7. | PROPOSED: Address admin is_online without location age | PROPOSED — Linked to D8/C7 |
| D3-b3 | Driver product documentation — "no background publishing" | Transport / Driver Location | POLICY / CONTROL SESSION | Proposed backlog item. Documentation needed. | PROPOSED: Document "no background publishing" behavior | PROPOSED — Documentation needed |
| D3-b4 | driverConsole test/template mismatch | Transport / Driver Location | UNASSIGNED / DECISION REQUIRED | Proposed backlog item. Test/template mismatch. | PROPOSED: Fix driverConsole test/template mismatch | PROPOSED — Test/template mismatch |

| **E — Maps / Tracking** | | | | | | |
| E1 | Tracking-card injection | Transport / Maps & Tracking | Correction 4 landed; Node 6 verified post-fix; 33 geo/rider tests + 2 JS harnesses pass | CLOSED — source + test proven. Correction 4 landed; Node 6 verified post-fix; 33 geo/rider tests + 2 JS harnesses pass. | ACTUAL: Correction 4 landed | **CLOSED** — Source + test proven; 33 geo/rider tests + 2 JS harnesses pass |
| E2 | Map injection | Transport / Maps & Tracking | Pipeline proven; visual tile render unproven — needs L-E2-tiles | PARTIAL. Pipeline proven; visual tile render unproven — needs L-E2-tiles. | PROPOSED: Verify visual tile render on network with OSM tiles | **PARTIAL** — Pipeline proven; visual tile render unproven (needs L-E2-tiles) |
| E3 | Track Driver | Transport / Maps & Tracking | Node 7 live | CLOSED — Node 7 live. Full tracking works. | ACTUAL: Verified live in Node 7 | **CLOSED** — Node 7 live |
| E4 | Tracking lifecycle | Transport / Maps & Tracking | Node 7 live | CLOSED — Node 7 live. Full lifecycle verified. | ACTUAL: Verified live in Node 7 | **CLOSED** — Node 7 live; full lifecycle verified |
| E5 | Fresh/stale indicator | Transport / Maps & Tracking | Verified | CLOSED. Works. | ACTUAL: Verified working | **CLOSED** |
| E6 | Degraded map | Transport / Maps & Tracking | UNASSIGNED / DECISION REQUIRED | OPEN — Small-02 candidate. | PROPOSED: Implement degraded map handling | **OPEN** — Small-02 candidate |
| E7 | Tile provider | Transport / Maps & Tracking | POLICY / CONTROL SESSION | VALIDATION / DECISION. | DECISION REQUIRED | **VALIDATION / DECISION** — Control session required |
| E8 | Navigation | Transport / Maps & Tracking | POLICY / CONTROL SESSION | DECISION. | DECISION REQUIRED | **DECISION** — Control session required |

| **F — Network / Failure** | | | | | | |
| F1 | Timeout handling | Transport / Network & Failure | Verified | CLOSED. Works. | ACTUAL: Verified working | **CLOSED** |
| F2 | Timeout-path test | Transport / Network & Failure | UNASSIGNED / DECISION REQUIRED | OPEN. No test implemented. | PROPOSED: Implement timeout-path test | OPEN |
| F3 | No infinite spinner | Transport / Network & Failure | UNASSIGNED / DECISION REQUIRED | VALIDATION (Tier 1). Critical blocker. Live verification pending. | PROPOSED: Verify no infinite spinner in low connectivity | **VALIDATION** — Tier 1 blocker; live verification pending |
| F4 | Network failure ≠ no supply | Transport / Network & Failure | Verified | CLOSED. Correctly distinguished. | ACTUAL: Verified working | **CLOSED** |
| F5 | Retry safety | Transport / Network & Failure | Verified | CLOSED. Implemented. | ACTUAL: Verified working | **CLOSED** |
| F6 | Backoff refinement | Transport / Network & Failure | UNASSIGNED / DECISION REQUIRED | OPEN. | PROPOSED: Refine backoff strategy | OPEN |
| F7 | Gevent/server-stall investigation | Transport / Network & Failure | UNASSIGNED / DECISION REQUIRED | PARKED. Investigation pending. | PARKED | PARKED |
| F8 | Low-connectivity behaviour | Transport / Network & Failure | UNASSIGNED / DECISION REQUIRED | OPEN (Tier 1). Critical blocker. | PROPOSED: Implement low-connectivity handling | **OPEN** — Tier 1 blocker |

| **G — Driver Experience** | | | | | | |
| G1 | Offer clarity | Transport / Driver Experience | UNASSIGNED / DECISION REQUIRED | OPEN (Tier 1). Critical blocker. | PROPOSED: Improve offer clarity for drivers | **OPEN** — Tier 1 blocker |
| G2 | Driver next action | Transport / Driver Experience | Verified | CLOSED. Clear. | ACTUAL: Verified working | **CLOSED** |
| G3 | Navigation | Transport / Driver Experience | UNASSIGNED / DECISION REQUIRED | OPEN. | PROPOSED: Implement driver navigation | OPEN |
| G4 | Driver location health | Transport / Driver Experience | Overlaps D8 | OPEN — overlaps D8. | PROPOSED: Implement driver location health monitoring | **OPEN** — Overlaps D8 |
| G5 | Timeout/error UX | Transport / Driver Experience | UNASSIGNED / DECISION REQUIRED | OPEN. | PROPOSED: Improve timeout/error UX for drivers | OPEN |
| G6 | Driver completion | Transport / Driver Experience | Verified | CLOSED. Works. | ACTUAL: Verified working | **CLOSED** |
| G7 | Driver history | Transport / Driver Experience | UNASSIGNED / DECISION REQUIRED | PARTIAL. | PROPOSED: Implement driver history | **PARTIAL** |
| G8 | Earnings | Transport / Driver Experience | Money workstream | OPEN — Money workstream. Parked. | PARKED — Money workstream | PARKED |
| G9 | Cash state | Transport / Driver Experience | Money workstream | DECISION — Money workstream. | DECISION REQUIRED | **DECISION** — Money workstream |

| **H — Money** | | | | | | |
| H1 | Cash semantics | Money | POLICY / CONTROL SESSION | DECISION (Tier 1). Critical blocker. | DECISION REQUIRED | **DECISION** — Tier 1 blocker; control session required |
| H2 | Cash receipt | Money | UNASSIGNED / DECISION REQUIRED | OPEN. | PROPOSED: Implement cash receipt | OPEN |
| H3 | Driver collection confirmation | Money | UNASSIGNED / DECISION REQUIRED | OPEN. | PROPOSED: Implement driver collection confirmation | OPEN |
| H4 | Payment state after completion | Money | UNASSIGNED / DECISION REQUIRED | OPEN (Tier 1). Critical blocker. | PROPOSED: Implement payment state after completion | **OPEN** — Tier 1 blocker |
| H5 | Rider receipt | Money | UNASSIGNED / DECISION REQUIRED | INDICATED. | PROPOSED: Implement rider receipt | **INDICATED** |
| H6 | Driver trip history | Money | UNASSIGNED / DECISION REQUIRED | PARTIAL. | PROPOSED: Implement driver trip history | **PARTIAL** |
| H7 | Settlement summary | Money | UNASSIGNED / DECISION REQUIRED | OPEN. | PROPOSED: Implement settlement summary | OPEN |
| H8 | Dispute evidence | Money | UNASSIGNED / DECISION REQUIRED | OPEN. | PROPOSED: Implement dispute evidence | OPEN |

| **I — Completion / Post-trip** | | | | | | |
| I1 | Completed-page refinement | Transport / Completion | UNASSIGNED / DECISION REQUIRED | OPEN. | PROPOSED: Refine completed page | OPEN |
| I2 | Trip summary | Transport / Completion | UNASSIGNED / DECISION REQUIRED | OPEN. | PROPOSED: Implement trip summary | OPEN |
| I3 | Receipt | Transport / Completion | Money-adjacent | INDICATED — Money-adjacent. | PROPOSED: Implement receipt | **INDICATED** — Money-adjacent |
| I4 | My Trips | Transport / Completion | Verified | CLOSED. Works. | ACTUAL: Verified working | **CLOSED** |
| I5 | Contact expiry | Transport / Completion | POLICY / CONTROL SESSION | DECISION (Tier 1). | DECISION REQUIRED | **DECISION** — Tier 1; control session required |

| **J — Visual Polish** | | | | | | |
| J1 | Human-readable timestamps | Transport / Visual Polish | Small-01 addendum: input matrix, TZ hazard caught + fixed. Citations pending (provisional). Live visual pending | CLOSED. Small-01: input matrix, TZ hazard caught + fixed. Citations pending (provisional). Live visual pending. | ACTUAL: Small-01 implemented | **CLOSED** — Small-01 addendum; TZ hazard fixed; citations pending; live visual pending |
| J2 | Currency consistency | Transport / Visual Polish | Small-01: toFixed(0) removed; fmtCur canonical | CLOSED. Small-01: toFixed(0) removed; fmtCur canonical. | ACTUAL: Small-01 implemented | **CLOSED** — Small-01; toFixed(0) removed; fmtCur canonical |
| J3 | Mobile density | Transport / Visual Polish | UNASSIGNED / DECISION REQUIRED | OPEN. | PROPOSED: Improve mobile density | OPEN |
| J4 | Primary action hierarchy | Transport / Visual Polish | UNASSIGNED / DECISION REQUIRED | OPEN. | PROPOSED: Fix primary action hierarchy | OPEN |
| J5 | Generic marketing blocks | Transport / Visual Polish | UNASSIGNED / DECISION REQUIRED | OPEN. | PROPOSED: Remove/replace generic marketing blocks | OPEN |
| J6 | Terminology | Transport / Visual Polish | UNASSIGNED / DECISION REQUIRED | OPEN — Small-02 candidate. | PROPOSED: Standardize terminology | **OPEN** — Small-02 candidate |
| J7 | Accessibility | Transport / Visual Polish | UNASSIGNED / DECISION REQUIRED | OPEN — Small-02 candidate. | PROPOSED: Implement accessibility improvements | **OPEN** — Small-02 candidate |
| J8 | Contrast/focus | Transport / Visual Polish | UNASSIGNED / DECISION REQUIRED | OPEN — Small-02 candidate. | PROPOSED: Fix contrast/focus issues | **OPEN** — Small-02 candidate |
| J9 | PWA manifest/icons + physical install | Transport / Visual Polish | Install ✅ + launch ✅ proven; tile-icon unconfirmed | DISPUTED. Install + launch proven; tile-icon unconfirmed → split J9-install (✅) / J9-icon (🔴). | PROPOSED: Split into J9-install (CLOSED) and J9-icon (OPEN) | **DISPUTED** — Split: J9-install CLOSED; J9-icon OPEN |
| J10 | Notification-history links | Transport / Visual Polish | UNASSIGNED / DECISION REQUIRED | OPEN — Small-02 candidate. | PROPOSED: Implement notification-history links | **OPEN** — Small-02 candidate |
| J11 | Degraded-map UX | Transport / Visual Polish | Overlaps E6 | OPEN — overlaps E6. | PROPOSED: Implement degraded-map UX | **OPEN** — Overlaps E6 |

| **Small-01 closed (outside A–L count)** | | | | | | |
| P3 | Driver assigned + waiting contradiction | Transport / Visual Polish (Small-01) | Verified | CLOSED (outside A–L count). Small-01 item. | ACTUAL: Fixed in Small-01 | **CLOSED** — Small-01 |
| P4 | Notification bell dead # link | Transport / Visual Polish (Small-01) | Verified | CLOSED (outside A–L count). Small-01 item. | ACTUAL: Fixed in Small-01 | **CLOSED** — Small-01 |
| P6 | Trips panel raw fare | Transport / Visual Polish (Small-01) | Verified | CLOSED (outside A–L count). Small-01 item. | ACTUAL: Fixed in Small-01 | **CLOSED** — Small-01 |

| **K — Architecture** | | | | | | |
| K1 | Rider data contract | Architecture | UNASSIGNED / DECISION REQUIRED | OPEN. | PROPOSED: Define rider data contract | OPEN |
| K2 | Duplicate driver-card rendering | Architecture | UNASSIGNED / DECISION REQUIRED | OPEN. | PROPOSED: Fix duplicate driver-card rendering | OPEN |
| K3 | Public/internal IDs | Architecture | Verified | CLOSED. Correctly separated. | ACTUAL: Verified working | **CLOSED** |
| K4 | Canonical services | Architecture | Verified | CLOSED. Established. | ACTUAL: Verified working | **CLOSED** |
| K5 | Cache invalidation | Architecture | Verified | CLOSED. Works. | ACTUAL: Verified working | **CLOSED** |
| K6 | Observability | Architecture | UNASSIGNED / DECISION REQUIRED | OPEN. | PROPOSED: Implement observability | OPEN |
| K7 | Shared-edit discipline | Architecture | Function-level ownership accepted (D3 acknowledgment + MATCH-01/Small-01 coexistence confirmed) | CLOSED. Function-level ownership accepted. D3 acknowledgment + MATCH-01/Small-01 coexistence confirmed. | ACTUAL: Function-level ownership discipline established | **CLOSED** — Function-level ownership accepted |
| K8 | Physical networking | Architecture | UNASSIGNED / DECISION REQUIRED | VALIDATION. | PROPOSED: Validate physical networking | **VALIDATION** |

| **L — Evidence Maturity** | | | | | | |
| L1 | Full no-reload journey | Evidence / L-series | Node 7 proved method (two journeys) | OPEN. Node 7 proved method with two journeys. | PROPOSED: Complete full no-reload journey verification | **OPEN** — Node 7 proved method (two journeys) |
| L2 | Reload detection | Evidence / L-series | UNASSIGNED / DECISION REQUIRED | OPEN. | PROPOSED: Implement reload detection | OPEN |
| L3 | Latency measurement | Evidence / L-series | UNASSIGNED / DECISION REQUIRED | OPEN. | PROPOSED: Implement latency measurement | OPEN |
| L4 | Timeout failure proof | Evidence / L-series | UNASSIGNED / DECISION REQUIRED | OPEN. | PROPOSED: Implement timeout failure proof | OPEN |
| L5 | Driver UI evidence | Evidence / L-series | UNASSIGNED / DECISION REQUIRED | OPEN. | PROPOSED: Collect driver UI evidence | OPEN |
| L6 | VIP proof | Evidence / L-series | UNASSIGNED / DECISION REQUIRED | OPEN. | PROPOSED: Collect VIP proof | OPEN |
| L7 | Heartbeat trace | Evidence / L-series | D2 evidence + Node 8 trace | OPEN. D2 evidence + Node 8 trace exist. | PROPOSED: Complete heartbeat trace verification | **PARTIAL** — D2 evidence + Node 8 trace |
| L8 | Background-driver proof | Evidence / L-series | Runbook written; human physical run pending | OPEN. Runbook written; human physical run pending. | PROPOSED: Execute human physical run for background-driver proof | **OPEN** — Runbook written; human physical run pending |
| L9 | Permanent dev CA / SAN | Evidence / L-series | Verified | CLOSED. Established. | ACTUAL: Verified working | **CLOSED** |
| L10 | Repeatable E2E | Evidence / L-series | Node 7 demonstrated pattern | OPEN. Node 7 demonstrated pattern. | PROPOSED: Establish repeatable E2E pattern | **PARTIAL** — Node 7 demonstrated pattern |

| **L-series additions** | | | | | | |
| L-A8-move | Driver delivers ≥2 positions; marker visibly displaces | Evidence / L-series | UNASSIGNED / DECISION REQUIRED | L-series addition. Requires moving driver to verify marker displacement. | PROPOSED: Execute with moving driver to verify marker displacement | **OPEN** — Needs moving driver verification |
| L-E2-tiles | Run on network where OSM tiles render | Evidence / L-series | UNASSIGNED / DECISION REQUIRED | L-series addition. Requires network with OSM tile rendering. | PROPOSED: Test map injection on network with OSM tiles | **OPEN** — Needs OSM tile rendering network |

---

# TABLE 2 — SUPPLY TRUTH PLANE

| # | Problem | Workstream / Owner | File / Function | Problem Definition + Code Evidence | Correction | Verification / Remarks / State |
|---|---------|-------------------|-----------------|-----------------------------------|------------|-------------------------------|
| SUPPLY-01 | release() restores is_available=True while is_online=False | Organisation / Fleet | AssignmentService.release() | **P1 invariant defect.** CURRENT CODE: release() can restore is_available=True while is_online=False. EVIDENCE: Invariant violation confirmed. Patch plan returned; needs A–F review under new protocol. | ACTUAL: Added DriverProfile.__table__.c.is_online.is_(True) to the driver availability-restore predicate in app/transport/services/assignment_service.py AssignmentService.release() Frontend: FRONTEND CHANGE NOT REQUIRED — EXISTING UI REMAINS TRUTHFUL. Regression: tests/test_transport_concurrent_claim.py 29 passed, 24 warnings. Verified scenarios: - offline driver release remains unavailable - online driver release restores availability - offline post-assignment cancellation remains unavailable - reverse active-booking protection preserved Scope: No frontend changes, vehicle-release changes, fleet, marketplace, admin-override, migration, wallet/payment, or unrelated changes. Gate: PASS — SUPPLY-01 VERIFIED | **CLOSED — VERIFIED** — All 4 regression scenarios proven; gate PASS |
| SUPPLY-02 | Fleet participation not enforced at pool/availability/claim | Organisation / Fleet | Pool/availability/claim logic | **P0 if fleet pilot.** Design ready; conditional predicate shape pending. | PROPOSED: Enforce fleet participation at pool/availability/claim | **DESIGN READY** — Conditional predicate shape pending |
| SUPPLY-03 | Marketplace contract dates not enforced | Marketplace | Contract date validation | **P0 if marketplace pilot.** Design ready; conditional predicate shape pending. | PROPOSED: Enforce marketplace contract dates | **DESIGN READY** — Conditional predicate shape pending |
| SUPPLY-04 | _activate_contract swallows DriverVehicleHistory failure | Organisation / Fleet | _activate_contract() | **P1.** Design ready; caller map required. | PROPOSED: Fix _activate_contract to propagate DriverVehicleHistory failure | **DESIGN READY** — Caller map required |
| SUPPLY-ADMIN | Admin update_driver_status sets is_online=True without checks | Auth / KYC | update_driver_status() | **POLICY.** 5-axis capability contract required. Authorized operational override is product direction, but detailed capability semantics still require control-session decisions. | DECISION REQUIRED — 5-axis capability contract | **POLICY** — 5-axis capability contract required; control session needed |
| SUPPLY-Q3 | Scheduled-driver-without-vehicle ambiguity | Organisation / Fleet | Universal vehicle rule | **RESOLVED.** Universal vehicle-before-Online rule decides. | ACTUAL: Universal vehicle rule decided | **DECIDED** — Universal vehicle rule decides |
| SUPPLY-00 | Driver is_available/is_online semantic inversion + admin override + audit fixes + idempotency key selection | Supply Truth | assignment_service.py claim()/release(); provider_service.py writers + register_driver + set_admin_online_override; go_live_service.py; driver_routes.py; api/routes.py; routes.py; driver_dashboard.html; utils/idempotency.py; admin templates | **Evidence trail (preserved): prior session BLOCKED on (1) TypeError 'str' object is not callable at idempotency.py:104, (2) 7 audit call sites passing entity_type/entity_id/request_id kwargs, (3) D4 audit placed after commit, (4) D4 disable-path flush/check before metadata assignment, (5) register_driver sanitize-dict / validation-tuple / with_cache_lock-CM defects. Corrected invariant: is_online => is_available; trip lifecycle never touches driver.is_available; override in driver_metadata JSONB with absolute blocked states.** | ACTUAL: A1/A2 claim-release writes removed; B1/B2 guards + B3 override endpoint; C1/C2 registration; D1-D7 writers + override method + register init (F,F)/(T,F); E1 go_live short-circuit; F1 detail route + admin templates; I1-I3 labels/payload; idempotency 3-way selection; audit kwargs + db_session with pre-commit ordering; _redis_lock helper. Transport-only; no migrations; no schema changes. | **GREEN — semantic correction + admin override + audit fixes + T1–T15 (16 exec) + idempotency contract (6)** — supply00 16/16; invariant 3/3; idempotency contract 6/6. SUPPLY-IDEMPOTENCY CLOSED / folded into SUPPLY-00. Residual OPEN: SUPPLY-LOCK-SITE-1048 (P1); test_one_driver_two_bookings (P3); SUPPLY-AUDIT-PERSIST; AuditLog collision; ActivityLog signature. NOTE: _redis_lock is module-private and single-use. When SUPPLY-LOCK-SITE-1048 lands, decide whether to promote it to app.utils.caching alongside a fix to with_cache_lock, or inline the correction. |

---

# TABLE 3 — MATCH-01 WORKSTREAM

| # | Problem | Workstream / Owner | File / Function | Problem Definition + Code Evidence | Correction | Verification / Remarks / State |
|---|---------|-------------------|-----------------|-----------------------------------|------------|-------------------------------|
| MATCH-01-A | Backend state (no_match enum, no_match_reason, CHECK, STATUS_TRANSITIONS) | MATCH-01 (Agent 1) | Backend models/migrations | Implemented in-tree. No_match enum, no_match_reason, CHECK constraints, STATUS_TRANSITIONS all implemented. | ACTUAL: Implemented in-tree | **IMPLEMENTED AND VERIFIED** — In-tree |
| MATCH-01-B | Silent re-offer on rejection | MATCH-01 (Agent 1) | Re-offer logic | Test-verified. Silent re-offer on rejection works correctly. | ACTUAL: Implemented and test-verified | **TEST-VERIFIED** — 48 tests |
| MATCH-01-C | Terminals: no_supply / all_rejected | MATCH-01 (Agent 1) | Terminal state logic | Test-verified. Terminal states no_supply and all_rejected work correctly. | ACTUAL: Implemented and test-verified | **TEST-VERIFIED** — 48 tests |
| MATCH-01-D | Rider projection (badge relabel, terminal copy, CTAs) | MATCH-01 (Agent 1) | Frontend rider projection | Implemented. Badge relabel, terminal copy, CTAs all implemented. | ACTUAL: Implemented | **IMPLEMENTED** |
| MATCH-01-E | Retry endpoint | MATCH-01 (Agent 1) | Retry API endpoint | Implemented. Retry endpoint works. | ACTUAL: Implemented | **IMPLEMENTED** |
| MATCH-01-F | Test suite (8 files, 48 tests) | MATCH-01 (Agent 1) | Test suite | 47 PASS, 1 FAIL. One test failing. | PROPOSED: Fix failing test | **47/48 PASS** — 1 FAIL |
| MATCH-01-G | _current_user_is_admin() misclassifies owner | MATCH-01 (Agent 1) | _current_user_is_admin() | **P1 DEFECT — Test/fixture isolation defect (NOT production authorization defect).** Over-strips admin payloads (safe direction). Current evidence establishes this as test/fixture isolation defect. Production code unchanged. Test fixture/session isolation corrected in `tests/transport/test_match01_payload_stripping.py`. Rider request now uses separate Flask test client from admin client. | ACTUAL: Fixed test fixture isolation in `tests/transport/test_match01_payload_stripping.py` — rider request uses separate Flask test client from admin client | **CLOSED — TEST/INTEGRATION FIXTURE DEFECT CORRECTED AND VERIFIED** — Focused payload-stripping test: PASS; Full MATCH-01 suite: 48/48 PASS; `tests/test_rider_sync_driver_card.cjs`: 17/17 PASS; `tests/test_rider_matching_search.cjs`: 18/18 PASS; Agent 1 gate: PASS — MATCH-01-G TEST DEFECT CORRECTED AND VERIFIED |
| MATCH-01-H | JS harnesses | MATCH-01 (Agent 1) | JS test harnesses | 17/17, 18/18 PASS. All JS harnesses pass. | ACTUAL: All JS harnesses pass | **PASS** — 17/17, 18/18 |
| MATCH-01-I | Live runs | MATCH-01 (Agent 1) | Live environment | NOT STARTED. Rider path safe from admin defect. | FUTURE / NOT IMPLEMENTED | **NOT STARTED** — Rider path safe |
| MATCH-01-J | Product C (booking_no_match inbox notification) | MATCH-01 (Agent 1) | POLICY / CONTROL SESSION | Separate node — pending decision. | DECISION REQUIRED | **PENDING DECISION** — Separate node |
| MATCH-01-K | Migration 20260930_1335 | MATCH-01 (Agent 1) | Migration 20260930_1335 | Applied. Migration executed. | ACTUAL: Migration applied | **APPLIED** |

---

# TABLE 4 — OTHER / PARALLEL WORKSTREAMS

| # | Problem | Workstream / Owner | File / Function | Problem Definition + Code Evidence | Correction | Verification / Remarks / State |
|---|---------|-------------------|-----------------|-----------------------------------|------------|-------------------------------|
| MIGRATION-01 | Generation experiment | Migration (Agent 3) | Migration tooling | CLOSED / SUPERSEDED — premise was invalid. | ACTUAL: Superseded | **CLOSED / SUPERSEDED** |
| MIGRATION-02 | Migration execution | Migration (Agent 3) | e8bf41930fb2 → 20260930_1335 | DONE — e8bf41930fb2 → 20260930_1335 logged. | ACTUAL: Executed and logged | **DONE / PROVEN** |
| MIGRATION-03 | Migration technical review | Migration (Agent 3) | Migration review | REVIEWED — deliberate design, CHECK-sync blind spot handled. | ACTUAL: Reviewed | **REVIEWED** |
| MIGRATION-04 | Migration authorization disposition | Migration (Agent 3) | POLICY / CONTROL SESSION | Control session decision if required. | DECISION REQUIRED | **CONTROL SESSION DECISION REQUIRED** |
| MIGRATION-05 | Migration chain vs DB state reconciliation | Migration (Agent 3) | Dev VARCHAR(15) vs Test VARCHAR(30) | Still unresolved — dev is VARCHAR(15), test is VARCHAR(30). | PROPOSED: Reconcile migration chain with DB state | **BLOCKED** — Dev VARCHAR(15) vs Test VARCHAR(30) |
| DRIVER-SOUND-01 | Custom song persistence for driver alerts | Future | UNASSIGNED / DECISION REQUIRED | NOT FILED — needs register entry. | FUTURE / NOT IMPLEMENTED | **NOT FILED** — Needs register entry |
| N7-EnRoute-CardVanish | Live-only defect from Node 7 | Transport / Rider Journey | UNASSIGNED / DECISION REQUIRED | NEEDS register entry + regression test. Live-only defect observed in Node 7. | PROPOSED: File register entry + create regression test | **NEEDS REGISTER ENTRY + REGRESSION TEST** |
| FUTURE-MAP-01 | Driver-side rider/pickup live location | Future | UNASSIGNED / DECISION REQUIRED | FUTURE ONLY — not implemented. Privacy review required. | FUTURE / NOT IMPLEMENTED | **FUTURE ONLY** — Privacy review required |
| PWA/APP-TELEMETRY-01 | Installation and active-device registry | Future | UNASSIGNED / DECISION REQUIRED | FUTURE ONLY — privacy review required. | FUTURE / NOT IMPLEMENTED | **FUTURE ONLY** — Privacy review required |
| L-A8-move | Driver delivers ≥2 positions; marker visibly displaces | Evidence / L-series | UNASSIGNED / DECISION REQUIRED | L-series addition. Requires moving driver to verify marker displacement. | PROPOSED: Execute with moving driver | **OPEN** — Needs moving driver verification |
| L-E2-tiles | Run on network where OSM tiles render | Evidence / L-series | UNASSIGNED / DECISION REQUIRED | L-series addition. Requires network with OSM tile rendering. | PROPOSED: Test on network with OSM tiles | **OPEN** — Needs OSM tile rendering network |

---

## Current Active Implementation Queue

| Priority | Register ID | Workstream | Current State | Next Action |
|---|---|---|---|---|
| 1 | MATCH-01-G | MATCH-01 | TEST/FIXTURE DEFECT | Correct test isolation → verify 48/48 |
| 2 | SUPPLY-01 | Supply Truth | DESIGN READY | Exact patch → approval → implement |

---

## Unresolved Control-Session Decisions

| # | Decision | Blocks |
|---|----------|--------|
| 1 | Admin Online authority — 5-axis capability contract | SUPPLY-ADMIN |
| 2 | Pilot scope — driver-owned / + fleet / + marketplace / all | SUPPLY-02/03 priority |
| 3 | Product C: booking_no_match inbox notification — approve or decline | MATCH-01 close |
| 4 | Migration 20260930_1335 disposition | Formal closure |
| 5 | Migration chain reconciliation — which DB is canonical | Production apply |
| 6 | A12b fee policy — age-based or stage multipliers | A12 close |
| 7 | J9 split — accept J9-install / J9-icon split | J9 close |
| 8 | Redis fix in app/__init__.py or abandon | Migration env (now superseded) |

---

## File Ownership / Cross-Workstream Boundaries

| Agent | Workstream | Key File/Function Boundaries |
|-------|------------|------------------------------|
| Agent 1 | MATCH-01 | Backend state (no_match enum, no_match_reason, CHECK, STATUS_TRANSITIONS), Silent re-offer, Terminals, Rider projection, Retry endpoint, Test suite, _current_user_is_admin(), JS harnesses, Migration 20260930_1335 |
| Agent 2 | Supply Truth | AssignmentService.release(), Pool/availability/claim logic, Contract date validation, _activate_contract(), update_driver_status() |
| Agent 3 | Migration | Migration tooling, e8bf41930fb2 → 20260930_1335, Migration review, Authorization disposition, Dev/Test DB schema reconciliation |

---

## SUPPLY-00 Follow-up Register

Recorded at SUPPLY-00 closure. SUPPLY-00 is GREEN (see TABLE 2). SUPPLY-IDEMPOTENCY is CLOSED / folded into SUPPLY-00. The following remain OPEN.

```text
SUPPLY-LOCK-SITE-1048
Priority: P1
Status: OPEN / FOLLOW-UP
Area: provider registration
File: app/transport/services/provider_service.py

Finding:
register_organisation_transport contains the same
with_cache_lock(..., timeout=10) context-manager misuse that was
corrected at the driver-registration site (site 667).

Evidence:
site 1048 still uses:
with with_cache_lock(f"lock:org_transport:{organisation_id}", timeout=10):
with_cache_lock is a decorator factory, not a context manager.

Required closure:
Add or identify a focused organisation-registration regression test,
then apply the minimal equivalent correction and verify best-effort
Redis-lock semantics.

Boundary:
Do not fix as part of SUPPLY-00.
```

```text
test_one_driver_two_bookings
Priority: P3
Status: OPEN / FOLLOW-UP
Area: concurrent claim

Finding:
Passes in isolation but can fail in the broader suite due to
barrier/thread timing.

Evidence:
Full-run result: 1 failure.
Isolated run: PASS.

Required closure:
Obtain a CI/repeated-run datapoint before deciding whether this is
a real synchronization defect or a test timing flake.

Boundary:
Do not modify this test as part of SUPPLY-00.
```

```text
SUPPLY-AUDIT-PERSIST
Status: OPEN / FOLLOW-UP
Area: audit durability (transport + non-transport)

Finding:
Audit calls with correct kwargs but no db_session persist only to the
console log, never to the database audit table, because the utility
only adds the DB row and the caller never commits it into a persisted
transaction.

Evidence:
Transport console-only sites: routes.py booking/driver/vehicle actions,
booking_service.py, coordination_contract.py (3 sites),
passenger_service.py (3 sites), payment_service.py.
Non-transport db_session gaps across auth, admin, wallet, compliance,
events, accommodation (same defect class, not enumerated here).

Required closure:
Dedicated node to add db_session=db.session (with a committing
transaction) where the record must persist, or explicitly mark
console-only intent per call site.
```

```text
AuditLog collision
Status: OPEN / FOLLOW-UP
Area: audit architecture

Finding:
Two classes named AuditLog with incompatible log() signatures:
app.utils.audit.AuditLog.log(action, user_id, details, resource_type,
resource_id, ...) vs app.audit.models.AuditLog.log(user_id, action,
resource_type, resource_id, meta, ...). The utility translates
details to meta only when db_session is provided.

Evidence:
Established during SUPPLY-00 audit investigation; utility proven
correct, call-site kwargs were the defect class.

Required closure:
Dedicated rename/disambiguation node. Out of scope for SUPPLY-00.
```

```text
ActivityLog signature
Status: OPEN / FOLLOW-UP
Area: audit architecture

Finding:
A third audit mechanism exists: app/models/audit.py
ActivityLog.log(action, target, actor, changes, request) — yet another
signature alongside the two AuditLog classes.

Evidence:
Discovered during SUPPLY-00 audit investigation.

Required closure:
Cover in the same audit-architecture follow-up as the AuditLog
collision. Out of scope for SUPPLY-00.
```

*End of register. All content preserved from original master register. Restructured into four tables with seven standardized columns. Visual grouping added for readability. MATCH-01-G updated to CLOSED with full verification evidence.*