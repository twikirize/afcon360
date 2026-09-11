# AFCON360 Transport — Geographic Graph Map (frozen contract)

**Status:** AUTHORITATIVE (TH-3-Contract durable artifact)
**Scope:** Transport geographic producer/consumer graph, coordinate contract, freshness contract
**Companion node:** TH-3-Contract — Transport Geographic Contract Freeze & Repair
**Next consumer:** TH-3 Dispatch & Assignment Harmonisation (must read this file as its geographic pre-flight contract; do not rediscover or redesign)
**Last verified against tree:** 2026-09-11 (HEAD `ed153d7`, branch `main`)

---

## 1. Purpose

This document freezes the geographic producer/consumer graph and the canonical
coordinate contract established by TH-3-Contract. A future agent entering
TH-3-Dispatch MUST rely on the rules below and MUST NOT re-derive, rename, or
redesign the coordinate keys, the freshness boundary, the ingestion path, or
the exclusion rules.

Per TH-3-Contract:

- Canonical coordinate keys are `latitude` / `longitude`.
- Legacy keys `lat` / `lng` are NOT canonical and are rejected at the booking
  boundary (no alias translation, no silent conversion).
- Malformed, partial, legacy, non-dict, and out-of-range coordinates resolve to
  `None` (or are rejected) — never to `(0, 0)` and never to a zero-distance result.
- The single freshness source is `TrackingService.LOCATION_TTL_SECONDS = 300`.

---

## 2. Canonical geographic contract

```text
latitude:  float ∈ [-90, 90]
longitude: float ∈ [-180, 180]
```

- Both keys must be present, parseable as floats, and in range.
- Legacy `lat` / `lng` is rejected (booking boundary) or excluded (matching).
- A dict containing `lat`/`lng` alongside canonical keys is REJECTED at the
  booking boundary (`_validate_booking_location_coordinates` raises
  `ValidationError`).
- Non-dict payloads (plain address strings / `None`) pass through the booking
  boundary unchanged — address-only bookings remain supported.
- Invalid coordinates are never converted to a zero-distance result; distance
  helpers return `None`.

Range enforcement points:

| Point | File:line | Behavior |
|---|---|---|
| Ingestion | `app/transport/services/tracking_service.py:50` (`validate_coordinates`) | Rejects out-of-range at REST → HTTP 400 |
| Booking boundary | `app/transport/services/booking_service.py:57` | Rejects out-of-range via `ValidationError` |
| Matching extraction | `app/transport/services/matching_service.py:223` | Out-of-range → `(None, None)` → excluded |
| Tracking extraction | `app/transport/services/tracking_service.py:256` | Out-of-range → `(None, None)` → excluded |
| Vehicle model | `app/transport/models.py:759-769` (`@validates('current_location')`) | Range guard on Vehicle JSONB write |

---

## 3. Freshness contract

```text
LOCATION_TTL_SECONDS = 300   # 5 minutes — the single source of truth
```

- Defined once: `app/transport/services/tracking_service.py:24`.
- **Produced:** `TrackingService.update_location` writes `location_updated_at
  = now(utc)` (`tracking_service.py:78`) and the same dict into Redis with
  `setex(..., LOCATION_TTL_SECONDS, ...)` (`tracking_service.py:65-68`).
- **Enforced (matching):** `MatchingService._rank_drivers_for_booking`
  computes `freshness_cutoff = now - timedelta(seconds=LOCATION_TTL_SECONDS)`
  (`matching_service.py:136`) and a driver is matchable only if
  `location_updated_at` parses (`datetime.fromisoformat`) and is `>= cutoff`
  (`matching_service.py:150-157`).
- **Enforced (nearby):** `TrackingService.get_nearby_drivers` uses the same
  cutoff (`tracking_service.py:314-326`) and skips drivers missing
  `last_location` / `location_updated_at`, or stale.
- Missing, stale, malformed, or non-dict `location_updated_at` ⇒ excluded.

---

## 4. Producer table

Every producer of geographic state. `REST` = HTTP entry-point.

| # | Component | File : function / route | Producer | Input field | Output field | Canonical shape | Validation point | Freshness rule | Storage destination | Downstream consumer | Test evidence | Classification |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| P1 | Driver GPS / mobile REST | `app/transport/api/driver_routes.py:276` `DriverLocationResource.post` — `POST /api/transport/drivers/<driver_id>/location` | REST | body `latitude`, `longitude` (both required → 400 if missing) | passes through to P2 | dict → `{'latitude','longitude',accuracy,speed,heading}` | `ValidationError` from P2 → 400 (`:305-307`) | Redis TTL 300 via P2 | `TrackingService.update_location` | `current_app` logging, `driver.last_seen_at` (`:298`) | `TC-07` ingestion; suite blocked at bootstrap (`pytest` → 1 collection error, 0 collected) | TH-3-owned |
| P2 | Ingestion service | `app/transport/services/tracking_service.py:28` `TrackingService.update_location(entity_type, entity_id, location_data)` | service | `location_data` dict | canonical dict `{'latitude','longitude','accuracy','speed','heading','timestamp'}` | dict (`:53-60`) | `required_fields` check (`:43-47`), `validate_coordinates` (`:50`) | TTL 300 `setex` (`:65-68`) | Redis `transport:tracking:driver:<id>` AND `DriverProfile.last_location`/`location_updated_at` (+ vehicle cascade) | P3, P4, matching, nearby, UI | `TC-07`, `TC-05` (via suite), prior direct proofs GREEN (2026-09-10) | TH-3-owned |
| P3 | Driver DB persistence | `tracking_service.py:74-85` (`driver.last_location`, `driver.location_updated_at`, `current_vehicle.current_location`, `current_vehicle.last_location_update`) | DB write | canonical dict | persisted JSONB + timestamps | dict | via P2 | 300 via P2 | `driver_profiles.last_location` (`models.py:333`), `location_updated_at` (`:334`); `vehicles.current_location` (`:679`), `last_location_update` (`:680`) | `ProviderService.get_available_drivers`, `get_nearby_drivers`, `get_location`, templates | `TC-07` persists/cascade/`location_updated_at` | TH-3-owned |
| P4 | Provider pool payload | `app/transport/services/provider_service.py:1291-1366` `ProviderService.get_available_drivers(zone, vehicle_class, limit)` | service | `DriverProfile.last_location`, `location_updated_at` | pool dict with `current_location` (`:1362`), `location_updated_at` ISO (`:1363`), `user.name` via `User.display_name` (`:1354`), `current_vehicle` (`:1358-1359`) | canonical (only `last_location` if it is a dic) | eligibility: not-deleted, online, available, APPROVED (`:1330-1335`) | none at pool level (deliberate — documented `:1310-1325`); consumer filters | read-only | `MatchingService._rank_drivers_for_booking` | `TC-06`, prior direct proofs GREEN | TH-3-owned |
| P5 | Booking REST | `app/transport/api/booking_routes.py:140` `BookingListResource.post` — `POST /api/transport/bookings` | REST | body `pickup_location`, `dropoff_location` | stored booking locations | canonical or address/None | `_validate_booking_location_coordinates` (`:158-159`) → `ValidationError` → 400 (`:167-169`) | n/a | `Booking.pickup_location` (`models.py:936`) / `dropoff_location` (`:944`) | `track_booking`, matching, notification, list UI | `TC-04` boundary; suite blocked at bootstrap | TH-3-owned |
| P6 | Booking service create | `app/transport/services/booking_service.py:98-108` `BookingService.create_booking` | service | `booking_data['pickup_location']`, `['dropoff_location']` | `Booking(pickup_location=…, dropoff_location=…)` | canonical or address/None | `_validate_booking_location_coordinates` (`:35-58`) | n/a | booking table | P5 consumers | `TC-04` | TH-3-owned |
| P7 | Geocoding (dormant) | `app/transport/services/external_platforms.py:210-249` `ExternalPlatformsService.geocode_address(address, provider='google')` | service (provider-gated) | address string | canonical `{'success','latitude','longitude','formatted_address','provider'}` — Google `lat`/`lng` converted to canonical (`:235-236`) | dict | provider must be `google` else `ValidationError` (`:242-245`) | n/a | none (returns to caller) | callers that build booking coords (none live) | prior direct proofs GREEN | Producer of canonical coords; real provider path dormant (no API key → mock) |
| P8 | Mock geocoding (fallback) | `external_platforms.py:251-282` `_mock_geocode` | service | address string | canonical `{'latitude','longitude',...}` | dict | keyword match else random Nairobi | n/a | none | P7 | — | canonical output |

---

## 5. Consumer table

Every consumer of geographic state.

| # | Component | File : function | Consumer | Input field(s) | Contract behaviour | Freshness rule | Validation point | Test evidence | Classification |
|---|---|---|---|---|---|---|---|---|---|
| C1 | Matching ranker | `app/transport/services/matching_service.py:131-211` `_rank_drivers_for_booking(drivers, booking)` | `current_location`, `location_updated_at` (from P4 payload), `booking.pickup_location` | Excludes drivers without fresh CANONICAL location; computes distance + score + ETA; only `score >= 40` ranked | `freshness_cutoff` 300s (`:136`); parse + `>= cutoff` (`:150-157`) | `_coordinates_or_none` (`:214-227`) | `TC-05`, `TC-08`; prior direct proofs GREEN | TH-3-owned |
| C2 | Matching distance | `matching_service.py:230-242` `_calculate_distance(location1, location2)` | canonical lat/lon pairs | Haversine km; `None` if either location invalid; never `0` for invalid input | n/a | `_coordinates_or_none` | `TC-02`, `TC-03`, `TC-05`; prior direct proofs GREEN | TH-3-owned |
| C3 | Book tracking | `app/transport/services/tracking_service.py:178-244` `track_booking(booking_id)` | `Booking.pickup_location`/`dropoff_location` (`:192-193`), live driver location (`:202-204`), vehicle (`:208-210`) | ETA = distance×2 min/km (`:219`), route polyline (`:225-229`) | n/a (reads whatever persisted) | `_calculate_distance` | — | Tracking consumers (address/None safe) |
| C4 | Nearby drivers | `tracking_service.py:303-349` `get_nearby_drivers(location, radius_km=5, limit=10)` | `DriverProfile.last_location`, `location_updated_at` | skips missing/stale, distance `None` or `> radius` skipped, returns distance-sorted | cutoff 300s (`:314-326`) | `_calculate_distance` | `TC-05` equivalent; no dedicated REST binding (gap, see §9) | pre-existing service |
| C5 | Provider routing | `app/transport/services/provider_service.py:1349-1366` pool payload consumer → ranker | `current_location` / `location_updated_at` | exposed as canonical or None | consumer enforces | n/a | `TC-06` | TH-3-owned |
| C6 | Nearby search | `tracking_service.py:119-174` `get_location(entity_type, entity_id)` | Redis first, DB fallback (`:124-143`) | returns canonical stored dict + source | n/a | stored shape | — | pre-existing |
| C7 | Driver location UI | `templates/transport/drivers/location.html:45-57,97-102` | `driver.last_location.get('latitude'/'longitude')`, Leaflet `L.map`/`L.marker` (`:97-102`) | renders canonical keys; `—` fallback when absent | n/a | template `.get` | — | UI consumer (canonical keys) |
| C8 | Vehicle location UI | `templates/transport/vehicles/location.html:37-42` | `vehicle.current_location.get('latitude'/'longitude')`, Leaflet | renders canonical keys | n/a | template `.get` | — | UI consumer (canonical keys) |
| C9 | Driver list UI | `templates/transport/drivers/index.html:272` | `driver.last_location` (JS) | presence-checked display | n/a | shape guard | — | UI consumer |
| C10 | Vehicle telemetry event | `app/transport/event_listeners.py:60` | `vehicle.current_location` | emitted in vehicle event payload | n/a | stored shape | — | event consumer |
| C11 | Booking list/notification | `app/transport/services/booking_service.py:315-326`, `app/transport/services/notification_service.py:249-251` | `booking.pickup_location`/`dropoff_location` | `.get('address'|'name'|'label')` on dicts; address-safe | n/a | `isinstance(dict)` | — | address/None-safe |

---

## 6. End-to-end live geographic paths

### 6.1 Driver GPS → ranking/matching

```text
POST /api/transport/drivers/<id>/location
  → DriverLocationResource.post (driver_routes.py:276)
  → TrackingService.update_location('driver', id, {lat, lon, ...}) (tracking_service.py:28)
      → validate: required keys (:43-47), validate_coordinates (:50)
      → Redis setex transport:tracking:driver:<id> TTL 300 (:63-69)  [Redis failure tolerated]
      → DB: DriverProfile.last_location + location_updated_at (:77-78)
      → vehicle cascade: current_vehicle.current_location + last_location_update (:81-83)
  → ProviderService.get_available_drivers(...) (provider_service.py:1291) → pool payload
      → current_location = last_location if dict, location_updated_at ISO (:1362-1363)
  → MatchingService._rank_drivers_for_booking (matching_service.py:131)
      → freshness gate 300s (canonical + fresh required) (:149-158)
      → distance Haversine (_calculate_distance) (:166-169) → score + ETA (:198-202)
  → ranked/sorted by match_score (:210)
```

### 6.2 Booking → storage → tracking consumers

```text
POST /api/transport/bookings
  → BookingListResource.post (booking_routes.py:140)
  → _validate_booking_location_coordinates on pickup/dropoff (:158-159)  [ValidationError → 400]
  → Booking(pickup_location, dropoff_location) (:160)  [also create_booking service path :98-108]
  → Booking.pickup_location / dropoff_location (models.py:936 / :944)
  → track_booking (tracking_service.py:178), matching (matching_service.py:61,:165-169),
    notification (notification_service.py:249-251), list UI (booking_service.py:315-326)
```

### 6.3 Geographic calculations

```text
coordinate extraction (_coordinates_or_none)
  → range/type validation ([-90,90] / [-180,180], float-cast)
  → freshness gate when location_updated_at present (300s)
  → Haversine distance (km) or None
  → ranking score / ETA / polyline
```

### 6.4 UI

`templates/transport/drivers/location.html` and
`templates/transport/vehicles/location.html` consume the canonical keys via
Leaflet (see C7/C8); `templates/transport/drivers/index.html` presence-checks
`last_location` (C9); `templates/transport/dashboard/base_dashboard.html:17`
includes Leaflet mapping assets.

---

## 7. Database geographic fields

| Table / model | Field | Type | Writer | Reader(s) | Notes |
|---|---|---|---|---|---|
| `driver_profiles` | `last_location` | JSONB | `TrackingService.update_location` (`tracking_service.py:77`); legacy `DriverProfile.update_location` (`models.py:456-468`, canonical shape) | provider pool, nearby, GET location, driver UI, events | contains accuracy/speed/heading/timestamp |
| `driver_profiles` | `location_updated_at` | DateTime(tz) | `update_location` (`:78`) | provider payload (`:1363`), matching freshness (`:152`), nearby (`:325`) | freshness authority |
| `vehicles` | `current_location` | JSONB | `update_location` via `current_vehicle` (`:82`) | vehicle UI, event listeners (`event_listeners.py:60`) | `@validates` range guard (`models.py:759-769`) |
| `vehicles` | `last_location_update` | DateTime(tz) | `update_location` (`:83`) | (no active reader found) | **gap**: written but unused |
| `bookings` | `pickup_location` | JSONB NOT NULL | `BookingService.create_booking` (`:107`), `BookingListResource.post` (`:160`) | `track_booking`, matching, notification, list UI | canonical-or-address |
| `bookings` | `dropoff_location` | JSONB NOT NULL | same | same | canonical-or-address |
| `bookings` | `pickup_point` | JSONB | (none) | (none) | **gap**: dead column (`models.py:937`, indexed `:880`) |
| `bookings` | `dropoff_point` | JSONB | (none) | (none) | **gap**: dead column (`models.py:945`, indexed `:881`) |
| `transport_incidents` | `location` | JSONB | `incident_routes.py:140` | (views) | **gap**: unvalidated shape/ranges |
| `scheduled_routes` | `stops`, `path_coordinates` | JSONB | `route_routes.py:121,:126,:206-207` | (views) | **gap**: unvalidated shape/ranges |

---

## 8. Test coverage

### 8.1 Geographic contract suite `tests/test_transport_geographic_contract.py`

Focused suite proving TC-01..TC-08 (docstring at top of file):

- `TestCoordinateContract` (6 tests) — canonical accepted, legacy rejected,
  partial rejected, out-of-range rejected, non-dict rejected.
- `TestDistanceNeverFalseZero` (5 tests) — canonical positive distance; legacy /
  partial / malformed ⇒ `None`, never `0`.
- `TestBookingLocationBoundary` (8 tests) — canonical passes; legacy rejected;
  both-key-sets rejected; partial rejected; out-of-range rejected; string
  address and `None` pass through; error message names canonical keys.
- `TestDriverRankingFreshness` (8 tests) — fresh canonical ranked; legacy /
  stale / missing-timestamp / missing-location / garbage-timestamp excluded;
  empty list; ETA grows from proximity.
- `TestTrackingServiceIngestion` (7 tests) — persists canonical pair; Redis TTL
  300; Redis failure tolerated; missing keys rejected; out-of-range rejected;
  vehicle cascade preserved; `location_updated_at` set.
- `TestProviderAvailabilityPayload` (1 test) — payload carries
  `current_location` + `location_updated_at`.

**Current result (2026-09-11):** `pytest tests/test_transport_geographic_contract.py -q --tb=short`
→ **35 passed, 2 warnings** (0 failed, 0 errors) on the canonical clean test DB
(built via `python scripts/setup_test_db_schema.py`). Matches the pre-gate run.
Earlier in the same day the module was uncollectable due to the §9 BLOCKER
(now RESOLVED). The contract itself was additionally proven correct on a sparse
DB by a direct app-context harness (`PROBE_CONTRACT_OK`): a fresh
APPROVED/online/available driver with canonical `latitude`/`longitude` appears
in the pool payload carrying `current_location` (canonical dict) +
`location_updated_at` (ISO).

**Isolation fragility (E/B) — RESOLVED (TI test-isolation repair, 2026-09-11):**
the single TH-3 payload test
(`TestProviderAvailabilityPayload::test_payload_carries_location_fields`)
asserts the freshly-created fixture driver appears within
`get_available_drivers(limit=100)`. The pool selector applies `LIMIT 100` with
NO `ORDER BY`; when the shared, session-scoped `afcon360_test` DB accumulates
≥100 committed APPROVED/online/available drivers from other suites run earlier
in the same pytest session, the fixture driver is truncated from the unordered
top-100 and `len(match) == 0` → **1 failed / 34 passed**. Reproduced and
root-caused via a throwaway probe (pool size 100, fresh driver absent); same
flow GREEN on a sparse DB. Classification: **E (test infrastructure/isolation
defect — shared test DB pollution across suites)** with a secondary B-type test
fragility (the `limit=100` un-ordered-pool assumption). NOT a TH-3 production
defect (contract proven correct).

**Repair (TI, this worker):** an arbitrary `limit=100000` request (TI-1's first
attempt) masked but did not repair the defect and is forbidden by the isolation
mandate. The test now performs a **transactional eligibility isolation** within
its own test transaction: it marks every *other* driver non-eligible
(`is_online`/`is_available` = False) before calling the pool at the bounded
`limit=100`, so the fixture driver is deterministically the only eligible row
regardless of how polluted the shared DB is. The update is never committed and
the `db_session` teardown rolls it back, so other suites' committed data is
untouched. No production code, query ordering, or schema changed.
**Determinism evidence:** RED at `limit=100` with 263 eligible drivers (fixture
truncated → 1 failed); GREEN with isolation at the same 263-eligible state;
GREEN under a 29-eligible count; full file 35 passed under heavy pollution and
again under low count; combined 9-suite transport+auth run **170 passed**
(forward and reverse file orders); collect-only 1286 / 0 errors.

### 8.2 Related transport regression (current, 2026-09-11, post-BLOCKER-resolution, clean test DB)

- `python -m py_compile app/transport/services/provider_service.py` → **PASS** (§9 BLOCKER resolved).
- `create_app()` → **STARTUP_OK**; boot log: `Transport API resources registered (32 endpoints)`,
  `Transport module registered`, `Wallet module registered`.
- `pytest tests/test_transport_front_page.py tests/test_transport_stage5t3.py tests/test_transport_stage5t4.py -q --tb=short`
  → **17 passed, 9 warnings**.
- `pytest tests/test_transport_service_integrity.py -q --tb=short` → **47 passed, 2 warnings**.
- `pytest tests/test_transport_coordination_contract.py tests/test_transport_passengers.py -q --tb=short`
  → **33 passed, 57 warnings**.
- `pytest tests/test_stage62a1_transport_serialization.py tests/test_stage62a_transport_auth_public_id.py -q --tb=short`
  → **38 passed, 2 warnings** (Defect-2 E-class session-cookie leak RESOLVED by
  the canonical fix — conftest `client` fixture is now `scope='function'`, so
  every test starts with an empty session cookie jar; re-verified 2026-09-11 in
  forward and reverse order, plus 26/26 standalone).
- `pytest --collect-only -q` → **1286 tests collected, 0 errors**.

### 8.3 Pre-recorded direct proof (2026-09-10, unchanged code)

Coordinate extraction, distance-never-zero, booking boundary, matching
freshness, Redis TTL 300, and Redis-failure resilience were proven GREEN by the
TH-3-Contract implementation node via `python -c` harnesses. Source of those
proofs is unchanged in the current tree (`py_compile` + code inspection
re-verified 2026-09-11).

---

## 9. Known gaps / deferred items

Do NOT turn any of these into implementation work inside this contract artifact.

- **BLOCKER — RESOLVED (2026-09-11):** `app/transport/services/provider_service.py:1282`
  previously contained an unterminated `raise ServiceUnavailableError(` inside the
  concurrently-authored `update_vehicle_status` method (whole method was
  additions-only vs HEAD `ed153d7`; not TH-3 content). This made
  `app.transport.services` unimportable, so the transport module failed to
  register at boot and every transport test module was uncollectable. Classified
  `C — pre-existing Transport defect (concurrent uncommitted work)`. **Resolved by
  an approved narrow manual transport correction** (closed the parenthesis —
  appended `)` after `retry_after=60,`); the change is confined to the already-added
  line (net-zero diff-stat effect) and re-verified: `python -m py_compile` PASS,
  `create_app()` STARTUP_OK with `Transport API resources registered (32 endpoints)`
  and `Transport module registered`, migration head unchanged (`f1658aba3410`).
- Dead `pickup_point` / `dropoff_point` booking columns (`models.py:937,945`, indexes `:880-881`).
- Unused `Vehicle.last_location_update` (written at `tracking_service.py:83`, no active reader).
- Unvalidated `TransportIncident.location` (`models.py:1660`; written `incident_routes.py:140`).
- Unvalidated `ScheduledRoute.stops` / `path_coordinates` (`models.py:1419-1420`).
- Geographic helper duplication: `_coordinates_or_none` / `_calculate_distance`
  exist in both `tracking_service.py` and `matching_service.py` (consolidation
  deliberately deferred).
- Dead `MatchingService.find_driver_for_booking` (no app-code callers; tests only).
- `TrackingService.get_nearby_drivers` has no REST/API binding (service-level only).
- Realtime push (WebSocket/SSE) of driver location to customers is missing.
- Real mapping provider + real geocoding path is dormant/config-gated
  (`ExternalPlatformsService.geocode_address` falls back to mock without an API key).
- TH-3-Security: driver-location POST (`DriverLocationResource.post`) has no
  login/ownership/permission gate (deferred, separate node).
- Future work (NOT authorized here): dispatch & assignment harmonisation,
  scheduled rides, availability/conflict protection, fare/payment redesign,
  Redis GEO / PostGIS spatial redesign.
- Wallet: no interaction; geographic operations imply no wallet mutation.

---

## 10. TH-3-Dispatch pre-flight

TH-3 Dispatch & Assignment Harmonisation MAY assume the following without
re-verifying:

- **Canonical coordinates = `latitude` / `longitude`** (float; lat ∈ [-90, 90], lon ∈ [-180, 180]).
- **Freshness threshold = 300 seconds** (`TrackingService.LOCATION_TTL_SECONDS`, single source).
- **Invalid / malformed / legacy coordinates are excluded** from geographic matching
  (never zero-distance, never silently promoted).
- **Stale / missing locations are excluded** from geographic matching.
- **`TrackingService.update_location` is the ingestion path** for driver/vehicle
  location (REST → update_location → Redis + DB) with Redis-failure resilience
  and ValidationError → HTTP 400.
- **Transport owns geographic operational state** (driver/vehicle/booking
  location fields are Transport-owned per AGENTS.md §17).
- **No Wallet mutation is implied by geographic operations.**

Dispatch SHALL start from the live state proven by the final gate (2026-09-11):
the §9 BLOCKER is closed, `pytest --collect-only` reports **1286 tests collected /
0 errors**, `test_transport_geographic_contract.py` = **35 passed**, and the
relevant transport regressions (front_page + stage5t3/5t4 = 17 passed,
service_integrity = 47 passed, coordination + passengers = 33 passed) are green.
Dispatch MUST still treat the deferred E/B isolation items (see §8.1 and §9) as
out of scope unless separately authorized, and MUST NOT re-open the geographic
contract decision.

### D1 correction addendum (2026-09-11)

TH-3-D1 (Dispatch & Assignment Existing-Graph Fit Review, READ-ONLY) has completed
its correction pass and its final two closure corrections; the final gate **PASS —
TH-3-D1 COMPLETE** is recorded in `.opencode/thread_state.md` and `BACKLOG.md`
(both the earlier "PASS — READY FOR D2 REVIEW" and "PASS WITH OPEN D2-ENTRY
EVIDENCE" verdicts were superseded after adversarial review; the race/edge tables,
the still-open cancellation race, the absent transport concurrent-claim test, and
the two closure corrections below are documented in the D1 final report). Nothing in
§10 above is changed. D1 re-verified against live code and confirmed: the missing
layer is thin dispatch/claim wiring over these pre-flight facts (no
`DispatchAttempt`/`DriverOffer`/`AvailabilityLock` tables for P0); the canonical
claim will use guarded conditional UPDATEs under READ_COMMITTED (safe — race losers
see 0 rows); `DriverLocationResource.post` (driver_routes.py:276) has no auth
decorator and its freshness feeds the ranker — a P0 security dependency for the
MVP; driver-availability toggle and watch passenger-visible fare estimation are P0
wiring gaps (fare estimation already computed/stored at booking creation,
`booking_service.py:700-714`); payment execution remains out of scope (P1). Race E
(cancellation vs claim) is explicitly NOT safe today — `cancel_booking`
(booking_service.py:205-246) is a plain read-modify-write with an unconditional
PK update, so a concurrent claim-then-cancel can overwrite; the D2 target is a
conditional cancellation `WHERE status IN ('pending_payment','confirmed')` +
rowcount. **Final closure corrections (2026-09-11):** (1) Race D / P0-P1 — minimum
post-acceptance stall recovery (release on terminal booking state + stall timeout)
is **P0**; full reassignment orchestration stays **P1**. (2) Availability release —
**no safe driver/vehicle release path is proven today**: terminal status transitions
(`BookingStatusResource.post`, booking_routes.py:261-317) set status/timestamps/
audit_log but never clear `assigned_driver_id`/`assigned_vehicle_id` (models.py:
1020-1021) nor flip `is_available` True; the only recovery is admin manual PUT
(driver_routes.py:171, vehicle_routes.py:193). D2 must add a canonical release
primitive (same transaction as the terminal status update, ownership-guarded with
conditional UPDATEs, rowcount-checked) wired into BookingStatusResource.post,
cancel_booking, and the driver completion path. D2 implementation awaits explicit
authorization, including its recommended entry concurrency test; no dispatch design
is specified here.

### D2 specification note (2026-09-11)

TH-3-D2 (Specification & Entry Gate — Atomic Dispatch Claim, READ-ONLY) has completed
Gate A and has been **corrected after an adversarial entry review** (14 material spec
defects fixed — gate-closure pass 2026-09-11) and then **passed a final artifact-integrity
pass** (4 further corrections, 2026-09-11). The corrected, implementation-ready
specification is recorded in `docs/transport/d2-atomic-dispatch-claim.md` and summarized
in `.opencode/thread_state.md` and `BACKLOG.md`. D1 = PASS — TH-3-D1 COMPLETE (sealed)
is unchanged. **The specification PASSES FINAL ARTIFACT INTEGRITY REVIEW and is READY
FOR MOE AUTHORIZATION; Gate B (implementation authorization) is NOT granted.** Nothing
in §10 above is changed; P0 D2 remains 0-migration (Decision A re-confirmed:
0 tables/columns/enums/constraints). Key corrections: exact claim SQL with reverse-ownership
`NOT EXISTS` for driver and vehicle (incl. mandatory self-exclusion `b.id <> :bk`,
§5 is the single canonical source); single `force=True` semantic (admin-only, authorised
via `@admin_required`→`has_global_role`→`actor_is_admin`, relaxes ONLY
`is_online`/`is_available`, never ownership/state/authorization; non-admin `force=True`
rejected `unauthorized` before SQL); booking soft-delete rejected while ACTIVE; documented
P0 defaults `TRANSPORT_STALL_TIMEOUT_SECONDS=600` / `TRANSPORT_OFFER_TTL_SECONDS=300`
(configurable); reverse-lookup performance risk register (P1 partial index named;
lock-duration/critical-section risk documented, P0-correct vs P1-scalability explicit);
canonical status sets single-source; release↔claim interleaving proof on corrected SQL;
availability-flip surfaces documented (3 paths), claim guard is authoritative backstop;
Redis offer lifecycle exact (never authoritative); P0 stall recovery concrete; P0/P1/P2
scope table. Git scope attribution: **inconclusive from the available working-tree state**
(see the artifact §27.1 for the honest statement of what git can and cannot prove).
Driver location POST (driver_routes.py:276) remains the P0 D2-entry security dependency.
**Final documentation-precision closure (2026-09-11, §28.2):** Item A canonical-SQL reconciliation closed (all `NOT EXISTS` / `b.id <> :bk` / `UPDATE driver_profiles/vehicles SET is_available=false` occurrences classified; §6.2 excerpts labeled explicitly; claim SQL single-source §5, release single-source §9, NOT collapsed; **Canonical claim SQL = §5. No competing claim definition exists.**); Item B mandated verification tables added (Table 1: canonical claim SQL PASS / actor_is_admin PASS / lock-duration PASS / Git INCONCLUSIVE; Table 2: Decision A PASS, force PASS, reverse-owner PASS, release PASS, P0/P1 PASS, artifact clean PASS, no-implementation PASS). Gate B remains absent.
D2 finishing line: D2 SPECIFICATION READY FOR MOE AUTHORIZATION — IMPLEMENTATION NOT AUTHORIZED. STOP.