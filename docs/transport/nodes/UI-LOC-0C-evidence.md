# UI-LOC-0C — Map Operational Hardening — Evidence (final closure)

## STATUS
IMPLEMENTATION VERIFIED / EVIDENCE GATE HOLD (panel review pending)

## NODE
UI-LOC-0C (upstreams 01C/02A/0B/UI-20 CLOSED/PASS)

## SCOPE
Leaflet load/init failure, tile-layer failure, map availability messaging,
local retry where supported. No search/autocomplete, provider/Photon,
registry, reverse geocoding, Node 1/2/3, routing, PostGIS/H3, fare/matching/
tracking, wallet, migrations, broad refactors.

## BASELINE (current authoritative implementation, verified from source)
`static/js/geo/geo-map.js` (v2, `VERSION = 2`) is the final baseline and was
NOT modified in this closure pass:
- Lifecycle: `removeCurrentMap()` destroys any previous instance before
  re-init; `destroy()` removes tile layer + map and clears the handle.
- Unavailable: `renderUnavailable()` sets `data-geo-map-status=unavailable`,
  renders truthful fallback + `Try again` retry button (re-invokes `init`).
- Tile degradation: `tileerror` listener attached to the TileLayer BEFORE
  `addTo(map)`; `renderTileDegraded()` sets `data-geo-map-tiles=degraded` +
  single notice with retry; clean `load` cycle clears it via
  `renderTileRecovered()` (never clears a cycle that had an error).
- Coordinate validation: `finiteNumber`/`validLatitude`/`validLongitude`
  reject null/bool/empty/non-numeric/non-finite/out-of-range; markers
  validated per-marker (malformed skipped, never fatal).
- `new_home.html` surfaces `__boltMapAvailable=false` through the existing
  map-target indicator; 0B GPS/targeting/Continue/`loadOptions` logic intact.

## FILES CHANGED (this closure pass only)
- `tests/test_ui_loc_0c.py` (restored strict locality in
  `test_0c_tile_failure_degraded_not_unavailable`: asserts
  `data-geo-map-tiles` + `degraded` + notice text inside the
  `renderTileDegraded()` function body, and no `unavailable` there)
- `docs/transport/nodes/UI-LOC-0C-evidence.md` (this file)
- No product-code edits. No `geo-map.js` edits. No migrations.

## TESTS
- `tests/test_ui_loc_0c.py` — 5 passed.
- `tests/test_ui_loc_0b.py` — 8 passed.
- `tests/test_transport_booking_geocoding.py` + `tests/test_transport_ride_options.py` — 19 passed.
- Session total: 32 passed, 0 failed. No counts inflated; no reruns double-counted.

## BROWSER (executed 2026-10-05, https://localhost:5443/transport/new-home, headed Chromium via Playwright)
- B1 normal render: map `rendered`, zoom + OSM attribution, target `Select pickup on the map`, Continue disabled with reason. BROWSER-PROVEN. Console 0 errors (pre-existing style-src report-only infos only).
- B2 real tile failure: tile CDN requests aborted (12 `ERR_FAILED`) → live TileLayer-level listener observed the degradation → `data-geo-map-tiles=degraded`, exactly one `Map tiles are failing to load…` notice with retry, map stayed `rendered`, target unchanged, Continue disabled, no coords. BROWSER-PROVEN.
- B3 multiple failures: exactly one notice across 12 failed tiles. BROWSER-PROVEN.
- B4 recovery: degraded-notice retry re-initialized map → `rendered`, degraded marker + notice cleared, target intact, no coords. BROWSER-PROVEN.
- B5 Leaflet unavailable: Leaflet CDN aborted → `data-geo-map-status=unavailable` + fallback + retry + unavailable target message + Continue disabled + no coords. BROWSER-PROVEN.
- No `ride-options` request while unresolved (network log). BROWSER-PROVEN.

## FAILURE MATRIX
| Scenario | Source | Test | Browser | Final evidence |
|---|---|---|---|---|
| Normal render | ✅ | ✅ | ✅ | Proven |
| Leaflet missing | ✅ | ✅ | ✅ | Proven |
| Tile degradation handler | ✅ | ✅ | ✅ via real failure | Proven |
| Real tile failure → degraded state | ✅ | ✅ | ✅ | **Proven** |
| Single-notice guard | ✅ | ✅ | ✅ | Proven |
| Retry/recovery | ✅ | ✅ | ✅ | Proven |
| Invalid center | ✅ | ✅ | — | Source/test-backed residual, PM accepted |
| Missing tile URL | ✅ | ✅ | — | Source/test-backed residual, PM accepted |
| Constructor exception | ✅ | ✅ | — | Source/test-backed residual, PM accepted |

## PROVEN
Normal render, Leaflet-missing fallback + retry, real tile-failure degraded state, single-notice guard, retry recovery, 0B/02A preservation, CSP nonce integrity.

## SOURCE/TEST BACKED
B6/B7/B8 paths share the single truthful `renderUnavailable()` implementation covered by init-failure tests; coordinate validation and marker isolation covered by renderer unit tests.

## ACCEPTED RESIDUAL
PM accepts B6/B7/B8 as source/test-backed residual evidence for this node; no additional browser fault-injection run is required for 0C closure. Applies to this evidence gate only.

## OUT OF SCOPE
Search, Photon/provider, registry, reverse geocoding, Node 1/2/3, routing, PostGIS/H3, fare/matching/tracking, wallet, migrations, offline maps, caching, rate limiting.

## 0B PRESERVATION
GPS sequence/token, failure preservation, resolved-state targeting, indicator writers, Continue gate, `loadOptions` guard — source-verified intact (0B tests 8/8 pass).

## 02A SAFETY
INTACT — no validator/BookingService/ride-options/fare/matching/tracking/migration edits in this node.

## CSP
`nonce="{{ csp_nonce }}"` script tags untouched; retry buttons use `document.createElement` + `addEventListener` (no inline handlers); no policy change. Style `style-src` report-only infos are pre-existing and out of scope.

## WORKTREE / OWNERSHIP
Repo intentionally dirty (multi-agent). This closure pass owns only the two files above. No stash/reset/clean. No migrations run.

## MIGRATION STATUS
NO MIGRATION RUN. No schema change.

## GATE RECOMMENDATION
PROPOSE UI-LOC-0C = PASS / CLOSED (panel to confirm)

## NEXT
STOP. Do not begin Node 1/2/3/4/5/6/7.
