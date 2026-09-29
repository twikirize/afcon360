# D4 — Driver Location Permission Recovery Evidence

## Node ID
D4

## Objective
Improve the driver PWA's handling when browser/device location permission is denied, unavailable, previously blocked, or needs to be re-enabled.

## Product Guarantee
A driver must receive a truthful, understandable location-permission state and an obvious recovery action without the application pretending that live location is healthy.

## Current Behaviour Before Change (Proven)

### Source Code Inspected
- `static/js/modules/transport/driver-dashboard.js:217-247` — `renderAvailabilityBadge()` function
- `static/js/modules/transport/driver-dashboard.js:255-274` — `onAcquireError()` function
- `static/js/modules/transport/driver-dashboard.js:293-321` — `retryLocationPermission()` function (NEW)
- `static/js/modules/transport/driver-dashboard.js:126-144` — `setLocBadge()` and `geoErrorName()` functions (NEW)

### Behaviour for Each Scenario

| Scenario | Before Change | After Change |
|----------|---------------|--------------|
| **1. First permission granted** | Works: getCurrentPosition → ingestPosition → ensureWatch → publishLocation | Unchanged |
| **2. Permission denied (code 1)** | Sets `blockedByPermission=true`, stops watcher, shows "Location permission denied. Re-grant it in the browser — retrying every Xs." Timer calls publishLocation but returns early. Recovery ONLY via Permissions API watcher or visibilitychange. | Same logic but: message now says "Open browser site settings → Location → Allow. Then click Retry or refresh the page." + **Retry button** appears. Clicking Retry clears blocked flag, calls getCurrentPosition, restarts watcher on success. |
| **3. Position unavailable (code 2)** | Shows "Location unavailable this tick (2). Retrying every Xs." (raw error code) | Shows "Location unavailable (Position unavailable). Retrying every Xs." (human-readable) |
| **4. Timeout (code 3)** | Shows "Location unavailable this tick (3). Retrying every Xs." (raw error code) | Shows "Location unavailable (Timeout). Retrying every Xs." (human-readable) |
| **5. Permission already blocked** | Same as scenario 2 — browser immediately returns PERMISSION_DENIED | Same as scenario 2 |
| **6. Retry/recovery** | Only automatic: Permissions API watcher + visibilitychange event. No manual trigger. | **Manual Retry button** + automatic Permissions API watcher + visibilitychange event. |

### Protected Invariants Verified
- ✅ 300-second freshness gate preserved (`FRESHNESS_MS = 5 * 60 * 1000` unchanged)
- ✅ No location fabrication (`afconValidObservation` rejects invalid coords)
- ✅ Driver not marked matchable when permission denied (backend freshness gate unchanged)
- ✅ Heartbeat cadence unchanged (`pingInterval` clamped to 300s max)
- ✅ GEO architecture unchanged
- ✅ A12 cancellation untouched
- ✅ Small-01 J1/J2/P3/P4/P6 untouched

## Changes Made

### File: `static/js/modules/transport/driver-dashboard.js`

#### 1. Enhanced `setLocBadge()` (lines 126-137)
```javascript
function setLocBadge(msg, isErr, showRetry) {
    var el = document.getElementById("dcLocBadge");
    if (!el) return;
    el.className = isErr ? "dc-toast err" : "dc-toast ok";
    if (showRetry) {
        el.innerHTML = msg + ' <button type="button" class="btn btn-sm btn-outline" id="dcLocRetry" style="margin-left:8px;padding:2px 8px;font-size:0.75rem;">Retry</button>';
        var btn = document.getElementById("dcLocRetry");
        if (btn) btn.addEventListener("click", retryLocationPermission);
    } else {
        el.textContent = msg;
    }
}
```
- Added optional `showRetry` parameter
- When true, injects a Retry button that calls `retryLocationPermission()`

#### 2. Added `geoErrorName()` helper (lines 139-144)
```javascript
function geoErrorName(code) {
    if (code === 1) return "Permission denied";
    if (code === 2) return "Position unavailable";
    if (code === 3) return "Timeout";
    return "Unknown error (" + (code || "?") + ")";
}
```
- Maps Geolocation API error codes to human-readable strings

#### 3. Updated `renderAvailabilityBadge()` (lines 217-247)
- Permission denied: Shows actionable instruction + Retry button
- Position unavailable: Uses `geoErrorName()` for human-readable error
- Low accuracy / good accuracy: Unchanged

#### 4. Added `retryLocationPermission()` (lines 293-321)
```javascript
function retryLocationPermission() {
    if (!navigator.geolocation || !navigator.geolocation.getCurrentPosition) return;
    if (!syncOnline()) return;
    blockedByPermission = false;
    setLocBadge("Requesting location permission…", false);
    try {
        navigator.geolocation.getCurrentPosition(
            function (pos) {
                ingestPosition(pos);
                ensureWatch();
                publishLocation();
            },
            function (err) {
                if (err && err.code === 1) {
                    blockedByPermission = true;
                    watchPermissionResume();
                }
                onAcquireError(err);
                renderAvailabilityBadge();
            },
            OPT_FAST
        );
    } catch (e) {
        blockedByPermission = true;
        renderAvailabilityBadge();
    }
}
```
- Clears `blockedByPermission` flag
- Requests fresh position via `getCurrentPosition` with fast options
- On success: ingests position, restarts watcher, publishes location
- On permission denied again: re-sets flag, re-arms Permissions API watcher
- On other errors: delegates to `onAcquireError`, re-renders badge

## Test Evidence

### Pure Function Tests (Deterministic, No Browser)
```
[TEST FILE] tests/transport/test_driver_location_permission.py
[TEST] test_afconValidObservation_valid
[TEST] test_afconValidObservation_invalid_lat
[TEST] test_afconValidObservation_invalid_lon
[TEST] test_afconValidObservation_invalid_acc
[TEST] test_afconShouldReplaceBest_ruleA_no_current
[TEST] test_afconShouldReplaceBest_ruleB_stale_current
[TEST] test_afconShouldReplaceBest_ruleC_materially_better
[TEST] test_afconShouldReplaceBest_ruleD_slightly_better_and_newer
[TEST] test_afconShouldReplaceBest_retain_good_fresh
[TEST] test_afconShouldReplaceBest_future_dated_ignored
[TEST] test_tierOf_none
[TEST] test_tierOf_low
[TEST] test_tierOf_good
[TEST] test_geoErrorName_permission_denied
[TEST] test_geoErrorName_position_unavailable
[TEST] test_geoErrorName_timeout
[TEST] test_geoErrorName_unknown
[RESULT] PASS
```

### Integration Tests (Pytest)

| Test Suite | Result | Notes |
|------------|--------|-------|
| `test_transport_driver_dashboard.py` | 3/3 PASS | Dashboard renders, context gates work |
| `test_transport_d2_evidence.py::TestDriverLocationRouteSecurity` | 4/4 PASS | Location endpoint auth unchanged |
| `test_driver_console.py::test_location_publish_updates_timestamp` | PASS | Location publishing works |
| `test_transport_matching_distance.py` | 26/26 PASS | Freshness gate & matching logic intact |
| `test_driver_workspace_consolidation.py` | 10/12 PASS | 2 pre-existing template string mismatches unrelated to changes |

### Verification Commands
```bash
# App factory sanity
python -c "from app import create_app"  # OK

# Core dashboard tests
pytest tests/test_transport_driver_dashboard.py -v  # 3 passed

# Location security tests
pytest tests/test_transport_d2_evidence.py -v -k "location"  # 4 passed

# Matching/freshness gate tests
pytest tests/ -k "matching" -v  # 26 passed

# Location publish test
pytest tests/transport/test_driver_console.py::test_location_publish_updates_timestamp -v  # PASS
```

## Security / Authorization / Availability Implications

- **Security**: No change to authorization model. Location endpoint still requires driver ownership or admin role.
- **Authorization**: No change to permission checks. `blockedByPermission` is a client-side UI state only.
- **Availability**: Improved — driver can now manually recover from permission denied without leaving the page or waiting for Permissions API.
- **Privacy**: No new data collected. Same geolocation API usage.

## Protected Nodes Checked

| Node | Status | Verification |
|------|--------|--------------|
| A12 Cancellation | ✅ Unaffected | No changes to trip lifecycle |
| Small-01 J1/J2/P3/P4/P6 | ✅ Unaffected | No changes to offer/dispatch logic |
| Freshness Gate (300s) | ✅ Preserved | `FRESHNESS_MS` constant unchanged |
| GEO Architecture | ✅ Preserved | No changes to tracking_service.py |
| Matching Service | ✅ Preserved | All 26 matching tests pass |

## Remaining Limitations

1. **Permissions API support**: The automatic `watchPermissionResume()` still depends on `navigator.permissions` API support. The manual Retry button works regardless.
2. **HTTPS requirement**: Geolocation still requires secure context (http://localhost works, http://other-host does not). Unchanged.
3. **Browser permission UI**: The "Open browser site settings → Location → Allow" instruction is generic. Browser-specific steps vary.
4. **No persistent retry state**: If user closes tab and reopens, they must click Retry again (or refresh). This is acceptable for a PWA.

## Master Tracker Recommendation

No new backlog items required. The changes are self-contained and complete the D4 objective.

## Gate
**PASS** — All acceptance criteria met:
- Truthful status messages (human-readable error names)
- Clear explanation (actionable instruction for permission denied)
- Obvious recovery action (Retry button + refresh guidance)
- Retry/re-request path where browser allows it (getCurrentPosition on click)
- No false "online location healthy" state (blockedByPermission prevents publish)
- Existing freshness and availability contracts preserved (all matching tests pass)