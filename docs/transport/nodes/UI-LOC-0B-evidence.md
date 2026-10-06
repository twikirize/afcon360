# UI-LOC-0B — Interim Rider Location UX Repair — Evidence

## STATUS
IMPLEMENTATION PASS / EVIDENCE GATE HOLD (panel review pending)

## NODE
UI-LOC-0B (parent UI-LOC-02, upstream 02A CLOSED/PASS, UI-20 CLOSED/PASS)

## SCOPE
UI-04 current-location clarity; UI-05 map-selected pickup; UI-06 map-selected
destination; UI-12 disabled-control explanations; minimum rider location
clarity. No search/autocomplete, no provider/Photon, no registry, no reverse
geocoding, no Node 1/2/3, no routing/map-matching/PostGIS/H3, no fare/
matching/tracking changes, no migrations.

## BASELINE (pre-edit, verified from source)
- `validateA()` required text + 4 hidden coords but wrote no reason text.
- `btnLocate` had no token; failure unconditionally cleared pickup text and
  pickup side even when a valid resolved pickup existed.
- Map click used `!!pins.pickup || !!inputPickup.value.trim()` as occupancy,
  so unresolved text blocked pickup targeting.
- Chips set `inputDest.value` only + cleared dest side; no coords invented.
- `#gpsStatus`, `#mapTargetIndicator`, `#continueDisabledReason` existed as
  empty `aria-live="polite"` placeholders with no writers.

## THE FOUR BLOCKERS (all implemented)

### A — GPS race + destructive failure
- `var gpsSeq = 0; bumpGpsSeq()` added; bumped on: `btnLocate` click (before
  request), pickup `input` event, `btnSwap` (pickup changes), map click that
  places pickup, pickup `dragend`. Never bumped for destination input, chip
  click, destination clear, or swap-clears-destination.
- Each geolocation request captures `mySeq`; both success and failure
  callbacks return early when `mySeq !== gpsSeq`.
- Failure captures `hadResolved/prevText/prevLat/prevLng` before request.
  No previous resolved pickup → clear to unresolved + actionable error.
  Previous resolved pickup → restore text + lat/lng, `validateA()`, status
  `Location attempt failed – previous pickup kept`.
- Success (non-stale) writes `Current location` + real `pos.coords` to
  existing hidden fields, then existing validate/sync flow + `__mapPinPickup`.

### B — Resolved-state map targeting
- Click handler now reads `pickup_latitude/longitude`, `dropoff_latitude/
  longitude` hidden fields (same truth as `validateA()`), not input text.
- Rule: none resolved → pickup; pickup resolved + dropoff unresolved →
  destination; pickup unresolved + dropoff resolved → pickup; both resolved
  → preserved deterministic nearest-pin replacement.
- Pickup-placing click branches and pickup `dragend` call `bumpGpsSeq()`;
  destination-only branches do not.
- `placePin()` contract untouched (still calls `writeFields()` +
  `validateA()`); `setFieldSync`/`__mapSyncing` preserved.

### C — UI indicators (presentation only, no state writes)
- `updateGpsStatus(state,msg)` writes only `#gpsStatus` text + data attr.
- `updateMapTarget()` derives from `isPickupResolved()/isDropoffResolved()`
  (hidden coords): pickup/destination prompts or ready message.
- `updateContinueReason()` reuses existing `btnContinue.disabled` gate;
  writes specific reason (missing pickup/destination, unresolved pickup/
  dropoff with chip note). `validateA()` is the single sync point and calls
  both at its end.
- Minimal CSS added for `.gps-status`, `.map-target-indicator`,
  `.bolt-cta-reason`; `#continueDisabledReason` changed from `sr-only` to
  visible `bolt-cta-reason`.

### D — Chip safety + visible explanation
- Chips unchanged in safety behavior: text-only `data-dest`, no `data-lat/
  lng`, no fetch, no `placePin()`, clear dest side + `validateA()`.
- Added `title` attributes stating text-only + map needed; the visible
  `updateContinueReason()` message (`chips set text only`) provides the
  actionable instruction. No coordinates invented, no registry/search.

## STATE RELATIONSHIP
Single source of truth remains valid hidden coordinate fields. Text, pins,
indicators, Continue state/reason, GPS status all derive from it.

## FILES CHANGED (0B-owned)
- `templates/transport/new_home.html` (IIFE rider script + 3 indicator
  placeholders already present + minimal CSS; CSP `nonce="{{ csp_nonce }}"`
  script tags untouched)
- `tests/test_ui_loc_0b.py` (new, 8 source tests)
- `docs/transport/nodes/UI-LOC-0B-evidence.md` (this file)

## SAFETY (02A invariant preserved)
- `validateA()` gate `!state.dest || !state.pickup || !coordsPresent`
  unchanged. `loadOptions()` coordinate guard untouched. No validator,
  BookingService, ride-options, fare, matching, tracking, migration changes.

## TESTS
- New: `tests/test_ui_loc_0b.py` — 8 passed.
- Regression: `tests/test_transport_booking_geocoding.py` +
  `tests/test_transport_ride_options.py` — 19 passed.
- Total executed this session: 27 passed, 0 failed.
- No unrelated tests rewritten; no counts inflated.

## STALE-GPS UI RESET (final correction)
- Before: stale callbacks ignored but spinner + `Getting your location…` could remain stuck after pickup invalidation.
- After: `invalidateGpsRequest()` bumps the sequence AND restores the locate button to crosshair AND clears GPS status immediately. Used by pickup input, swap, pickup-placing map clicks, and pickup dragend. Destination-only paths do not call it. `btnLocate` new-request path still sets locating UI normally.
- Stale callbacks remain ignored via `mySeq !== gpsSeq` on both success and failure.

## BROWSER (executed 2026-10-05, https://localhost:5443/transport/new-home, headed Chromium via Playwright)
- B1 initial: map target `Select pickup on the map`, Continue disabled + `Select a pickup and destination to continue.` BROWSER-PROVEN.
- B2 typed `Mutundwe` pickup: unresolved, map still targets pickup, Continue disabled. BROWSER-PROVEN.
- B5 chip `Namboole Stadium`: destination text set, no coords, Continue disabled (`Select pickup and destination on the map to continue.`). BROWSER-PROVEN.
- B6 locating: click Locate shows `Locating…` + `Getting your location…` + spinner. BROWSER-PROVEN.
- B8 failure (no prior pickup): input cleared, status `Unable to get location – choose pickup on the map.`, button restored, Continue disabled. BROWSER-PROVEN.
- B9 invalidation: Locate then immediate pickup typing restored crosshair, cleared status and coords synchronously. BROWSER-PROVEN.
- GPS success / prior-pickup-preserved failure / map-pin flows: NOT VERIFIED (headless geolocation unavailable; map clicks not exercised). Source+test proven only.
- Console: 0 errors, 0 warnings; 9 style-src report-only infos (pre-existing, out of scope). No `ride-options` network request while unresolved. BROWSER-PROVEN.

## CSP
- `nonce="{{ csp_nonce }}"` on main inline script + Leaflet + geo-map
  external tags preserved. No inline event attributes added (all
  `addEventListener`). No policy change.

## WORKTREE / OWNERSHIP
- Repo intentionally dirty (multi-agent). 0B owns only the three files
  above. UI-20 nonce changes in same file preserved (script tags untouched).
- Untracked `update_gps.py` at repo root is not 0B-owned; left untouched.
- No stash/reset/clean used. No migrations run.

## RESIDUAL RISKS
- Browser proof partial: initial/typed/chip/locating/failure/invalidation verified; GPS success, prior-pickup-preserved failure, and map-pin flows not verified in this run.
- `(0,0)` accepted as range-valid per 02A policy (unchanged).
- Chip UX still requires manual map step until Node 4 registry + Node 6
  search (both on hold).

## OUT OF SCOPE (explicitly not done)
Typed search, autocomplete, Photon/provider, registry, reverse geocoding,
Node 1/2/3, routing, PostGIS/H3, fare/matching/tracking changes, migrations.

## MIGRATION STATUS
NO MIGRATION RUN. No schema change.

## GATE RECOMMENDATION
PASS (implementation) / EVIDENCE GATE HOLD (panel review pending)

## NEXT
STOP — await panel review. Do not begin 0C/Node 1+.
