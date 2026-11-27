# ROUTING-01 — GEO Road Routing Service Activation

**Contract status:** APPROVED — adopted by repository owner on 27 November 2026
**Owning domain:** GEO
**Contract path:** `docs/geo/nodes/ROUTING-01-contract.md`
**Baseline reviewed:** `main` at `c471f89d21fb285745e510dfd86cdd8c8b70e92b`
**Date prepared and approved:** 27 November 2026
**Contract authorship:** Draft prepared by the assistant under the repository owner's explicit, one-node drafting override, then adopted by the repository owner on 27 November 2026.

---

## 1. Guarantee

GEO provides one trustworthy, provider-backed road-routing boundary for the platform.

When Valhalla is enabled and correctly configured, GEO returns validated road distance in **metres**, estimated road duration in **seconds**, and latitude-first route geometry. Its matrix operation returns correctly ordered road distances and durations for every requested origin/destination pair.

When routing is disabled, unconfigured, unreachable, malformed, or unable to find a route, GEO reports an unresolved result. It must never present a straight-line measurement or a fabricated zero as a successful road distance or duration.

Straight-line measurement remains a distinct GEO capability for proximity and geographic screening. It is not a substitute for road distance.

This node activates and proves the GEO routing capability. It does not yet make Transport fares, bookings, driver matching, or trip mileage depend on it.

## 2. Current Behavior — Findings on the reviewed `main`

1. `app/geo/services.py::build_routing_service(config)` already knows how to create a Valhalla-backed service when the operator has both enabled and configured it.

2. `app/geo/services.py::get_routing_service()` does not use that factory or load GEO configuration. It creates a process-level `RoutingService()` without a provider. Consequently, the normal public getter does not activate the configured Valhalla adapter.

3. `app/geo/providers/valhalla.py::ValhallaRouter.route()` already calls Valhalla's `/route` endpoint, sends latitude-first `lat`/`lon` coordinates, reads the trip summary and decodes precision-6 geometry. It currently assumes the returned route length is kilometres without explicitly requesting the units.

4. Unresolved point-to-point results currently contain numeric zero duration. The no-provider facade also places a Haversine distance in a result marked `resolved=False`. Although the flag and provider label communicate the fallback, numeric fields make accidental misuse easier.

5. `ValhallaRouter.matrix()` is currently an unresolved stub. It returns zero-valued measurements for every pair and does not call Valhalla's `sources_to_targets` service.

6. `app/geo/routes.py::_health_payload()` calls `load_geo_config()` without the active Flask application. It can therefore report environment configuration rather than the effective app-specific `GEO` configuration.

7. Existing tests exercise the adapter through a controlled fake HTTP server and exercise the configuration factory. They do not prove that the public service getter activates the effective Flask configuration, and they currently expect the matrix capability to remain deferred.

8. A repository search on the reviewed `main` did not identify a live Transport consumer of `get_routing_service()`. The Transport pricing, booking, matching and tracking paths therefore remain separate work and must be re-traced before their own contracts are written.

The existing GEO documentation already distinguishes straight-line distance from road distance and says that callers must check `RouteResult.resolved`. This node strengthens that boundary rather than changing the meaning of existing proximity helpers.

## 3. Scope-In

Only the following work is authorized by this node:

1. **Activate the canonical service getter.** Connect `get_routing_service()` to the existing `load_geo_config()` and `build_routing_service()` path. Resolve the active Flask app's `GEO` configuration when an app context exists; use the existing environment fallback outside an app context. Cache the service per Flask application so one application's configuration cannot leak into another. Service construction and health inspection must not make network requests.

2. **Make unresolved route measurements unambiguous.** Update the GEO route result contract so unavailable distance and duration are represented as `None`, not fabricated zero values. A successful provider result may legitimately have a zero value for a same-point route; `resolved` and the presence of valid measurements distinguish that case from an unresolved result. Do not put Haversine distance into the road-route result.

3. **Harden point-to-point Valhalla parsing.** Explicitly request kilometre units, convert route distance to metres at the provider boundary, retain duration in seconds, preserve latitude-first `GeoPoint` geometry, and reject malformed/non-finite/negative values or invalid decoded coordinates. Invalid input coordinates must be rejected before network I/O. Provider failures must remain unresolved and must not trigger an automatic straight-line substitute.

4. **Complete the existing matrix provider contract.** Implement the Valhalla `sources_to_targets` request for the existing `RoutingProvider.matrix()` interface. Preserve the caller's origin row order and destination column order. Normalize distance to metres and duration to seconds. Preserve the requested matrix dimensions. A null or otherwise unreachable pair must be represented as unresolved, not as a valid zero-distance pair. A malformed overall response must not be returned as a successful partial or misaligned matrix.

5. **Preserve bounded, truthful provider behavior.** Honour the configured request timeout; do not introduce unbounded retries. Keep provider construction, availability inspection and health reporting free of network I/O. Do not expose credentials or sensitive configuration in API responses or logs.

6. **Make GEO health reporting configuration-correct.** Use the effective app configuration for the health response. Report enabled/configured state without performing a live route request or disclosing secrets. Do not label configuration presence as proof that the remote service is reachable.

7. **Update GEO's routing documentation.** Correct the routing status and document the resolved/unresolved value semantics, units, matrix ordering, and operator-controlled enablement.

8. **Add focused regression tests** in the existing GEO routing test area. Use the existing fake Valhalla HTTP-server pattern; do not depend on a public routing server for deterministic unit tests.

## 4. Scope-Out

This contract explicitly does **not** authorize:

- Changing Transport fare formulas, fare calculation ownership, fare estimates, ride-options, signed fare quotes, quote validation, booking creation, booking metadata, or rider/driver displayed prices.
- Changing driver candidate selection, driver-to-pickup ranking, dispatch, matching, assignment, availability, nearby-driver filtering, pickup ETA, or drop-off ETA.
- Changing rider or driver mobile/web screens, navigation UX, route presentation, or location-picker behavior.
- Calculating actual travelled trip distance, writing `Booking.actual_distance_km`, updating driver mileage totals, GPS trace validation, map matching, telematics, or trip lifecycle transitions.
- Replacing straight-line GEO helpers used for proximity, radii, bounding boxes, and spatial pre-filtering.
- Adding database tables, columns, indexes, Alembic migrations, Redis keys, Celery tasks, public API endpoints, paid routing providers, or a new routing engine.
- Changing Wallet, KYC, Identity, or unrelated modules.
- Enabling Valhalla in production, changing production environment variables, deploying or reconfiguring a routing server, or performing production data writes.

Those behaviors require their own traced Transport or operations contracts and must consume the proven GEO interface rather than reimplement provider logic.

## 5. Interface Contract

### 5.1 Point-to-point route

Input:

- `origin` and `destination` are validated `GeoPoint` objects.
- Coordinates remain latitude-first in GEO: `GeoPoint(latitude, longitude)`.
- `profile` is forwarded as the selected supported Valhalla costing model; the existing default remains `auto`.

Resolved result:

- `resolved=True` only when Valhalla has returned a structurally valid route with finite, non-negative distance and duration.
- `provider` identifies the answering provider (`valhalla`).
- `distance_m` is metres.
- `duration_s` is seconds.
- Geometry is returned as latitude-first `GeoPoint` values. Any returned geometry must be decoded and range-validated.

Unresolved result:

- `resolved=False`.
- `distance_m=None` and `duration_s=None`.
- No fabricated geometry.
- Provider provenance identifies the configured provider when it was attempted, or `unresolved` when no provider was available.
- The caller must not convert an unresolved result to zero, Haversine distance, or a made-up ETA.

Invalid coordinates remain input-validation errors and must not cause a provider request.

### 5.2 Matrix

Input:

- Ordered, non-empty origin and destination lists of validated `GeoPoint` values.
- Each origin maps to one output row.
- Each destination maps to one output column.
- The provider request uses Valhalla's `sources_to_targets` service with latitude-first `lat`/`lon` locations, explicit kilometre units, and the existing `auto` costing default.

Output:

- Exactly `len(origins)` rows and `len(destinations)` columns.
- `matrix[i][j]` always represents `origins[i]` to `destinations[j]`.
- Resolved cells contain road distance in metres and duration in seconds.
- Unreachable/null cells are unresolved with unavailable measurements (`None`), never fabricated zero values.
- A malformed response that cannot preserve the expected dimensions and ordering must not be presented as a valid matrix.
- Matrix cells do not contain route geometry unless a later, separately approved contract adds that capability.

### 5.3 Configuration and lifecycle

- The existing `GEO` Flask configuration and `GEO_VALHALLA_URL` / `GEO_VALHALLA_ENABLED` environment variables remain the configuration sources.
- Valhalla remains disabled by default.
- App-specific configuration must not leak between Flask applications or test app instances.
- Getter construction, provider construction, `is_available()` and health reporting perform no network I/O.
- Real network requests occur only when `route()` or `matrix()` is called.
- The health response distinguishes `enabled` and `configured`; it does not claim that the remote service is reachable merely because both are true.

## 6. Proof of Done

The implementation must prove all of the following with targeted tests:

1. The public `get_routing_service()` uses the configured provider when the active Flask app has Valhalla enabled and configured.
2. Disabled or unconfigured Valhalla produces truthful unresolved results.
3. Separate Flask application configurations do not contaminate each other.
4. Getting or constructing a routing service and reading GEO health causes no outbound provider request.
5. The point-to-point request uses latitude-first coordinates, the requested costing profile and explicit kilometre units.
6. A valid route is normalized to metres and seconds and its precision-6 geometry is decoded correctly.
7. Invalid input is rejected before network I/O.
8. Timeout, HTTP error, disabled provider, unreachable route and malformed response do not produce a successful route or fabricated metrics.
9. A successful same-point result can retain a legitimate zero measurement without being confused with an unresolved result.
10. Matrix tests prove request coordinates, source/target order, row/column cardinality, unit conversion and per-pair mapping.
11. Matrix tests prove that unreachable/null pairs remain unresolved and that malformed matrix dimensions are not accepted as successful output.
12. GEO health reflects the effective app configuration and does not expose secret values or claim live reachability.
13. Straight-line helper tests and behavior remain unchanged.

Targeted verification commands:

```text
pytest tests/test_geo_routing.py tests/test_geo_foundation.py tests/test_geo_contract.py -q
python -m py_compile app/geo/services.py app/geo/interfaces.py app/geo/providers/valhalla.py app/geo/routes.py
git diff --check
```

No test may depend on a public Valhalla service or a production database. Do not edit shared test fixtures to obtain a passing result.

**Operational gate:** Unit tests against the fake provider prove adapter behavior, not real map coverage. Before production routing is enabled in a later operational change, an operator must verify a controlled staging Valhalla instance with representative local routes, confirm that route geometry and returned measurements are sensible, and record endpoint/map-data coverage and service health. Until that separate verification is complete, production routing remains disabled.

## 7. Rollback

- Revert only the implementation commit(s) belonging to ROUTING-01.
- Keep Valhalla disabled by default. If a staging configuration causes problems, set `GEO_VALHALLA_ENABLED=false` or remove the staging endpoint configuration.
- With Valhalla disabled, GEO must return an unresolved route result with unavailable road measurements; it must not quietly revert to Haversine as road distance.
- This node creates no schema or persisted data, so no database rollback or migration is required.
- Do not change production configuration as a rollback or verification shortcut.

## 8. Constraints

- Follow EGGE in order: UNDERSTAND → MAP → TRACE → PROVE → MINIMAL CHANGE → VERIFY → GATE → RECORD → NEXT.
- Implement only this approved node. Stop at a scope boundary and record discoveries as follow-ups.
- Use the current `main` baseline and a dedicated work branch. Do not commit directly to `main`, force-push, or create unrelated branches.
- No manual or generated migrations; no DB schema changes.
- No production commands, production writes, or production configuration changes.
- Do not modify Wallet, KYC, `app/models/base.py`, `tests/conftest.py`, or shared test setup.
- Do not duplicate fare, distance, ETA, or provider logic in Transport.
- Keep straight-line distance semantics and all existing coordinate validation contracts intact.
- Do not claim live-service verification from a fake-server test.
- The human owner remains responsible for the project's register update.

## 9. Acceptance Criteria

ROUTING-01 is accepted only when:

- The public GEO routing getter activates the correct configured Valhalla provider without network I/O during construction.
- Route and matrix outputs have explicit, tested units and correct ordering.
- Unresolved measurements are represented as unavailable, not as fabricated zeros or Haversine road measurements.
- Provider failures and unreachable pairs fail truthfully and predictably.
- The focused GEO test set and syntax/diff checks pass.
- GEO documentation and health reporting agree with the implemented behavior.
- No Transport consumer, fare, booking, dispatch, actual-distance, schema, Wallet, KYC, or production behavior has been changed.
- The operator-facing staging verification requirement is recorded as a separate gate; production remains disabled until that gate is satisfied.

**Owner adoption:**

- [x] I approve this ROUTING-01 guarantee, scope, interface contract, proof requirements, rollback and constraints.
- [x] I approve `GEO` as the primary owning domain for this behavior.
- [x] I approve `docs/geo/nodes/` as the canonical location for GEO node contracts, evidence and records.
- [x] I approve the narrowly scoped exception that allowed this draft to be prepared on my behalf; this document is adopted as the human-owned contract.

**Repository-owner approval:** Approved — 27 November 2026  
**Implementation authorization:** Approved for ROUTING-01 only, subject to the stated scope, EGGE process and constraints. Production routing enablement remains explicitly excluded.
