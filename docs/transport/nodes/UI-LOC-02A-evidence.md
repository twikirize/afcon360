
# UI-LOC-02A: SAFETY CLOSURE — EVIDENCE

## STATUS: IMPLEMENTATION PASS / EVIDENCE GATE HOLD

NODE: UI-LOC-02A
PARENT: UI-LOC-02
PHASE: VERIFY → GATE (panel review pending)
BRANCH: main
DATE: 2026-10-05

---

## SUMMARY

UI-LOC-02A makes coordinate safety a genuine server boundary on both paths
that can reach distance, fare, matching, or booking persistence:
`BookingService.create_booking()` and `POST /api/transport/ride-options`.
Unresolved, partial, non-numeric, bool, non-finite, and out-of-range
endpoints are refused before any downstream computation; the silent
booking-bound `planning_default` fallback is removed (explicit estimate mode
keeps its labelled default); the canonical validator rejects raw bool input
at the root so no `float()` pre-conversion can launder it. The panel
(ChatGPT + DeepSeek) owns the final gate decision.

---

## SCOPE — 02A-OWNED FILES

| File | Change |
|------|--------|
| `app/utils/validators.py` | Raw-bool guard in `TransportValidators.validate_coordinates` (canonical root) |
| `app/geo/validation.py` | Raw-bool guard in `normalize_coordinate` before `float()` |
| `app/transport/services/booking_service.py` | Raw validation before `float()` in `_resolve_canonical_location`; `_ensure_canonical_coords` guard; booking-bound `planning_default` replaced with refusal; pyright narrowing guards + `Dict[str, Any]` annotation |
| `app/transport/api/ride_options_routes.py` | Server quote boundary via canonical validator on raw values; planning-default fallback removed |
| `templates/transport/new_home.html` | Client `validateA()` coordinate gate + `loadOptions()` early return (prior work, untouched in closure) |
| `tests/test_transport_booking_geocoding.py` | Test-strength restoration (creation-rejection assert) |
| `tests/test_ui_loc_02a_closure.py` | New node-owned proof file (9 tests) |
| `docs/transport/nodes/UI-LOC-02A-evidence.md` | This file |

No changes to: fare logic/formulas, matching, tracking, search/Photon,
reverse geocoding, routing, GPS/map UX, chips, wallet, migrations.

---

## WORKTREE STATE (DOCUMENTATION EVIDENCE)

Captured 2026-10-05. The tree is intentionally dirty (multi-agent
workstreams active). A dirty tree is not a failure; no commit per node is
required. What is proven here is ownership and attribution, not
cleanliness. No `git stash / stash pop / reset --hard / clean` used.

`git status --short` (abbreviated to 02A-relevant entries; full output
retained in shell history):

```text
M app/geo/validation.py
M app/transport/api/ride_options_routes.py
M app/transport/services/booking_service.py
M app/utils/validators.py
M templates/transport/new_home.html
M tests/test_transport_booking_geocoding.py
M tests/test_transport_concurrent_claim.py
M tests/test_transport_ride_options.py
?? docs/transport/nodes/UI-LOC-02A-evidence.md
?? tests/test_ui_loc_02a_closure.py
```

Plus ~25 unrelated dirty files from other workstreams (auth, admin,
notifications, templates, BACKLOG.md, tree.md, celerybeat files, etc.).
None were touched by this node. In particular,
`tests/test_transport_concurrent_claim.py` and
`tests/test_transport_ride_options.py` show as modified from PRIOR work, not
from this closure execution — this execution made zero edits to either file
(verified: no edit call targets them; their 12 + 29 tests pass unmodified).

### Ride-options ownership diff

`git diff HEAD -- app/transport/api/ride_options_routes.py` (current):

```diff
-        # Distance basis (same rules as fare estimate): caller-supplied
-        # estimate wins, then straight-line from supplied pins, then the
-        # engine's planning default.
-        distance_km = data.get("estimated_distance_km")
-        distance_basis = "planning_default"
-        if distance_km is None:
-            sl = _straight_line_km(data)
-            if sl is not None:
-                distance_km = sl
-                distance_basis = "straight_line_planner"
+        # UI-LOC-02A: booking-bound quote inputs must carry resolved
+        # coordinates. Validate RAW values with the canonical validator
+        # (no float() pre-conversion — that launders bool/nan/inf).
+        # Only after validation converts to float for distance/fare.
+        from app.core.validators import validate_coordinates
+        pickup_lat = data.get("pickup_latitude")
+        pickup_lng = data.get("pickup_longitude")
+        dropoff_lat = data.get("dropoff_latitude")
+        dropoff_lng = data.get("dropoff_longitude")
+
+        # All four coordinate fields must be present and numeric
+        coord_fields = {
+            "pickup_latitude": pickup_lat,
+            "pickup_longitude": pickup_lng,
+            "dropoff_latitude": dropoff_lat,
+            "dropoff_longitude": dropoff_lng,
+        }
+        for name, value in coord_fields.items():
+            if value is None or (isinstance(value, str) and value == ""):
+                return {"success": False, "error": f"Missing coordinate: {name}"}, 400
+            # Canonical verdict on the RAW value, paired with a known-valid
+            # peer (0.0 is in range on both axes), so any rejection is
+            # attributable to `value` alone. No float() pre-conversion here.
+            try:
+                if name.endswith("latitude"):
+                    validate_coordinates(value, 0)
+                else:
+                    validate_coordinates(0, value)
+            except Exception:
+                # Message granularity only (not a second verdict) ...
+                if isinstance(value, bool):
+                    return {"success": False, "error": f"Invalid coordinate: {name}"}, 400
+                try:
+                    float(value)
+                except (TypeError, ValueError):
+                    return {"success": False, "error": f"Invalid coordinate: {name}"}, 400
+                if name.endswith("latitude"):
+                    return {"success": False, "error": f"Invalid latitude: {name}"}, 400
+                return {"success": False, "error": f"Invalid longitude: {name}"}, 400
+
+        # Distance must be derived from supplied coordinates (no planning default)
+        sl = _straight_line_km(data)
+        if sl is None:
+            return {"success": False, "error": "Invalid coordinates for distance calculation"}, 400
+        distance_km = sl
+        distance_basis = "straight_line_planner"
```

**Classification: 02A-owned.** The diff removes the planning-default
fallback and adds the coordinate boundary — exactly the 02A quote-boundary
requirement. It contains no rate-limit, availability, fare-formula, ETA, or
display-name changes, so there is no overlap with another workstream and no
mixed-file conflict.

---

## BOOKING SAFETY BOUNDARY

### Guard (preserved verbatim)

`app/transport/services/booking_service.py`:

```python
# Ensure both locations are resolved with canonical coordinates
def _ensure_canonical_coords(loc, field_name):
    if not isinstance(loc, dict) or loc.get("latitude") is None or loc.get("longitude") is None:
        raise ValidationError(
            message=f"{field_name} must be a resolved location with coordinates",
            field=field_name,
        )

_ensure_canonical_coords(pickup_location, "pickup_location")
_ensure_canonical_coords(dropoff_location, "dropoff_location")
```

Position: after `_resolve_canonical_location` calls, before distance/fare.

### Raw-before-float in `_resolve_canonical_location`

```python
# UI-LOC-02A: validate RAW values before float() launders
# bool/nan/inf into floats. Canonical validator owns the verdict.
try:
    validate_coordinates(lat_raw, lng_raw)
except Exception:
    raise ValidationError(
        message=f"{field_name} coordinates must be numeric",
    )

try:
    lat = float(lat_raw)
    lng = float(lng_raw)
except (TypeError, ValueError):
    raise ValidationError(
        message=f"{field_name} coordinates must be numeric",
    )

validate_coordinates(lat, lng)
```

Plus a pyright narrowing guard (`isinstance((str, int, float))`) that rejects
non-scalar input with the same message; bool passes the guard and is
rejected by the canonical validator. Same `ValidationError` contract.

### planning_default removal (booking-bound)

```python
# UI-LOC-02A: booking-bound pricing has no silent fallback. ...
measured_km = _measured_distance_km(pickup_location,
                                    dropoff_location)
if measured_km is None:
    raise ValidationError(
        message="Resolved coordinates required for fare calculation",
        field="pickup_location",
    )
distance_for_fare = measured_km
distance_basis = "straight_line_planner"
```

Fare formulas untouched. `fare_routes.FareEstimateResource` untouched —
explicit estimates keep labelled `planning_default`.

### Case proof (all via fresh tests)

| Case | Result |
|------|--------|
| Text-only both endpoints | REJECT `ValidationError` |
| Mixed resolved/unresolved | REJECT |
| Partial (lat only) | REJECT |
| Bool (`True`) either side | REJECT |
| NaN / ±Inf (float + string forms) | REJECT |
| Client `estimated_distance` without coords | REJECT |
| Valid coords both sides | ACCEPT, `straight_line_planner` |

---

## RIDE_OPTIONS SERVER BOUNDARY

Validation precedes `available_by_class()`,
`fare_service.calculate_estimate()`, and `nearest_eta_minutes_for_class()`.
17 direct-POST cases → all HTTP 400 (`test_ride_options_rejection_classes`):
missing pickup ×1, missing dropoff ×1, partial ×4, empty string ×1,
non-numeric ×1, bool ×2, NaN/Inf/−Inf ×3, out-of-range ×4.
Valid coordinates → 200, `distance_basis == "straight_line_planner"`.

### Peer-0 note

**Peer-0 pairing is a workaround for the current pair-oriented coordinate
validator. It is not a scalar validation API or a new coordinate contract.
It is technically valid under the current symmetric validator because 0 is
range-valid. A future scalar validator/API may replace this technique.**
The per-field `float()` in the message-mapping branch selects error text
only; the rejection verdict comes solely from the canonical validator.

---

## CANONICAL VALIDATOR MATRIX (EXPLICIT)

`test_canonical_validator_matrix` against `app.core.validators.validate_coordinates`:

| Input | Result |
|-------|--------|
| `True` / `False` (either axis) | RAISE (bool guard added at canonical root) |
| `NaN`, `±Inf` (float + `"nan"`/`"Infinity"` strings) | RAISE |
| `None`, `"abc"` | RAISE |
| lat `999.0`/`−91.0`, lng `181.0`/`−181.0` | RAISE |
| Valid Kampala pair, numeric strings | PASS (returns `None`) |
| `(0, 0)` | PASS — intentional 02A policy (no service-area/plausibility rule authorized; future policy item) |

Root cause found by read: `TransportValidators.validate_coordinates` did
`float(lat)` first, and `float(True) == 1.0` laundered bool into valid
coordinates. Fixed at the root with an `isinstance(bool)` guard; mirrored
in `app/geo/validation.py::normalize_coordinate`.

---

## TEST COVERAGE

### New/restored 02A coverage — 16 tests

`tests/test_ui_loc_02a_closure.py` (9 new):

| Test | Proves |
|------|--------|
| `test_canonical_validator_matrix` | Matrix above |
| `test_booking_rejects_bool_nan_inf` | Service rejects bool/NaN/Inf/text/estimate-only |
| `test_booking_valid_coordinates_still_books` | Valid books, `straight_line_planner` |
| `test_ride_options_rejection_classes` | 17 direct-POST 400s |
| `test_ride_options_rejected_quotes_never_reach_fare` | Fare/availability unreached (see mechanism below) |
| `test_ride_options_valid_still_works` | Valid quote 200 |
| `test_explicit_estimate_keeps_planning_default` | Estimate 200 `planning_default` |
| `test_booking_needs_coords_while_estimate_does_not` | Estimate without coords → 200 planning_default; booking without coords → ValidationError |
| `test_legacy_book_route_rejects_text_only_endpoints` | Legacy route honest refusal (see below) |

`tests/test_transport_booking_geocoding.py` (7, restored): text-only
rejected, partial rejected, out-of-range rejected, pin assembly, measured
pricing, client-distance rejected, matchability creation-rejection restored
(exact change: re-added `pytest.raises(ValidationError)` around text-only
`create_booking` before the `_coordinates_or_none` asserts; before =
helper-only asserts, after = creation rejection + helper asserts).

### Regression confirmation — 77 tests

| Suite | Count | Outcome |
|-------|-------|---------|
| `tests/test_transport_ride_options.py` | 12 | PASS (unmodified file) |
| `tests/test_transport_booking_show.py` | 3 | PASS |
| `tests/test_transport_concurrent_claim.py` | 29 | PASS (unmodified file) |
| `tests/test_transport_fare_engine.py` | 15 | PASS |
| `tests/test_transport_passengers.py` | 18 | PASS |

### Totals

```text
93 passing test cases represented in final evidence
16 new/restored 02A coverage
77 regression confirmation
0 failures
```

Where:
16 = 9 tests in `tests/test_ui_loc_02a_closure.py` + 7 tests in `tests/test_transport_booking_geocoding.py`
77 = 12 + 3 + 29 + 15 + 18 from the regression table.

---

## LEGACY ROUTE PROOF — POST /transport/book

`test_legacy_book_route_rejects_text_only_endpoints` (1 passed, 13.69s):

- Setup: `test_user` promoted to KYC tier ≥ 2 (phone verified + verified
  `IndividualVerification` with national_id/biometric scope; tier asserted
  via `calculate_kyc_tier`), so KYC/profile gates cannot explain the result.
- Request: `POST /transport/book` with text-only `pickup_location` /
  `dropoff_location` and NO lat/lng keys — exactly what `book.html` sends
  (verified: no `latitude|longitude` fields in `templates/transport/book.html`).
- Result: HTTP 302, `Location` contains `/transport/book`, does NOT contain
  `/transport/rides/` (no booking page) or `/kyc/upgrade` (not a gate
  redirect), and the rider's booking count is unchanged.
- Mechanism (verified by read, not inferred): `app/schemas/transport.py`
  does not exist, so the route uses raw form data → `create_booking` raises
  `ValidationError` → the route's generic `except Exception` handler flashes
  "Booking error: …" and redirects to `book_transport`. Honest refusal, no
  silent pricing, no row written. Intended BLOCK semantics; rider UX repair
  belongs to 0B.

---

## MONKEYPATCH PROOF — PRECISE MECHANISM

`test_ride_options_rejected_quotes_never_reach_fare`:

- Monkeypatched targets (module `app.transport.api.ride_options_routes`):
  1. `ro.fare_service.calculate_estimate` → replaced with `_boom`, which
     records the call in `calls` and raises `AssertionError`.
  2. `ro.available_by_class` → replaced with a lambda raising
     `AssertionError` ("availability must not be reached").
- Rejected POST cases sent (5): `{}` (empty), `{"pickup_latitude": LAT_A}`
  (partial), bool `True` pickup, `NaN` pickup, `999.0` pickup.
- Outcome: all 5 returned HTTP 400; `calls == []` asserted — zero
  monkeypatched downstream calls recorded. This proves validation precedes
  both availability and fare computation on the quote path. No further
  claims are made (e.g. ETA internals are not instrumented).

---

## VALIDATOR SCOPE AUDIT

| File | Function | Mechanism | Raw-validated? | Changed? |
|------|----------|-----------|----------------|----------|
| `app/utils/validators.py` | `TransportValidators.validate_coordinates` | float+range+regex → bool | YES (bool guard added) | YES |
| `app/core/validators.py` | `validate_coordinates` | wraps above, raises | inherits | NO |
| `app/geo/validation.py` | `normalize_coordinate` / `normalize_point` | float then canonical | YES (bool guard added) | YES |
| `booking_service.py` | `_validate_booking_location_coordinates` | canonical on dict values | YES (inherits fix) | NO |
| `booking_service.py` | `_resolve_canonical_location` | canonical on RAW then float | YES (added) | YES |
| `booking_service.py` | `_ensure_canonical_coords` | shape only (dict/non-None) | n/a | NO |
| `booking_service.py` | `_measured_distance_km._coords` | narrowing + fail-closed None | YES | YES |
| `ride_options_routes.py` | `post()` boundary | canonical on RAW + peer 0 | YES | YES |
| `fare_routes.py` | `_straight_line_km` | float then canonical → None | estimate-only path | NO |
| `matching_service.py` | `_coordinates_or_none` | float+range → `(None,None)` | fail-closed helper, not on 0A path | NO (record only) |
| `tracking_service.py` | `_coordinates_or_none` + `update_location` | same helper; ingest via canonical | ingest covered post-fix | NO (record only) |
| `transport/models.py` | `DriverProfile.update_location` | canonical | inherits fix | NO |

Matching/tracking bool-laundering residual is unreachable from validated
inputs (all ingest boundaries reject bool); consolidation is a forbidden
broad refactor — recorded, not fixed.

---

## CSP WORDING

Relevant scripts and inline-handler source checks are satisfied for
`new_home.html` (Leaflet CDN + `geo-map.js` + inline booking block carry the
per-request nonce; no inline event-handler attributes found); this is not a
page-wide runtime CSP verification.

---

## MIGRATION STATUS

**NO MIGRATION RUN.** No `flask db migrate`, `flask db upgrade`,
`flask db downgrade`, or `flask db merge` executed. No schema change. No
migration file created, edited, or repaired.

---

## RESIDUAL RISKS

| Risk | Note |
|------|------|
| Browser proof outstanding | Infrastructure absent; contract-declared separate from the server gate |
| `(0,0)` accepted as valid | Intentional 02A policy; future service-area rule item |
| Legacy `/book` text-only now flashes an error | Intended BLOCK semantics; 0B owns UX repair |
| Matching/tracking helper bool nuance | Unreachable post-fix; consolidation deferred (forbidden broad refactor) |
| Pre-existing pyright diagnostics elsewhere in touched files (SQLAlchemy `Column[bool]`, `__table__`, `rowcount` idioms) | Untouched by this node; typing-hygiene follow-up, not a 02A gate item |
| GPS accuracy not surfaced | Node 2/3 scope |

---

## IMPLEMENTATION RESULT: SERVER SAFETY BOUNDARY PROVEN

## PANEL GATE: HOLD — awaiting ChatGPT + DeepSeek final evidence review

The panel makes the gate decision. This agent does not set it.

---

## NEXT (GATED ON PANEL)

Only after panel PASS: 0B rider location UX. No 0B/0C/Node-1+ code touched
in this node.
