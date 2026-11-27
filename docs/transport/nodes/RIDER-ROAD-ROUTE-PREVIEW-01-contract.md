# RIDER-ROAD-ROUTE-PREVIEW-01 — Contract

**Owning domain:** Transport  
**Dependency:** GEO / ROUTING-01 (merged in PR #155)  
**Status:** OWNER-APPROVED SCOPE — 27 November 2026  
**Branch:** `feat/transport-rider-road-route-preview-20261127`

This file records the repository owner's approval on 27 November 2026 of the scope and behavior described below. It is limited to a non-persistent planned-road-route preview for the existing web rider journey. The React Native client is a later consumer and is not part of this node.

---

## 1. Guarantee

When a rider has selected valid pickup and destination coordinates on the existing Transport web booking page, AFCON360 can request a driving route through the canonical GEO routing service and display the returned road geometry, road distance and provider duration on the existing map.

A route preview is informational only. It does not create a ride, start matching, issue or change a fare quote, or commit a booking.

If road routing is unavailable or unresolved, the UI reports that honestly. It never draws a straight line and labels it a road route, and it never fabricates road distance, duration or geometry.

## 2. Current behavior

- The existing rider page is `templates/transport/new_home.html`.
- Browser GPS, selected forward-geocode candidates and map pins already populate resolved pickup and destination coordinates.
- `static/js/geo/geo-map.js` provides the shared Leaflet map renderer.
- The Transport rider page currently draws a dashed straight connector between the pickup and destination pins; this is not a road route.
- `POST /api/transport/ride-options` validates resolved coordinates and calculates signed fare quotes using `straight_line_planner`.
- GEO ROUTING-01 is merged. `get_routing_service()` activates the configured Valhalla provider and returns `RouteResult` with metre/second measurements and latitude-first geometry when resolved.

## 3. Scope-In

1. Add a Transport-owned, non-persistent route-preview API under the existing `/api/transport` REST blueprint.
2. Accept pickup and destination latitude/longitude only; validate raw inputs using the canonical coordinate validator before constructing GEO points.
3. Call `app.geo.services.get_routing_service()` and request the `auto` (driving) profile. Do not call Valhalla directly from Transport.
4. Return a stable JSON contract:
   - resolved route: `resolved=true`, `distance_m`, `duration_s`, `geometry=[{latitude, longitude}, ...]`, and `provider`;
   - unresolved route: `resolved=false`, null distance/duration, empty geometry and truthful provider provenance;
   - invalid coordinates: HTTP 400 with a field-specific error.
5. Rate-limit this anonymous-allowed, pre-commitment preview consistently with existing public rider estimate endpoints. Preserve the application's normal CSRF boundary for same-origin browser POSTs.
6. Integrate the API into the existing rider website only:
   - request a road preview only when both endpoints have valid resolved coordinates;
   - discard stale responses when endpoints change and clear stale route geometry;
   - render Valhalla's actual latitude-first geometry on the existing Leaflet map;
   - show resolved road distance and duration, labelled as a planned driving route;
   - display a truthful unavailable/loading state without blocking the existing quote journey;
   - remove the misleading dashed straight-line connector from the rider map.
7. Add focused backend and frontend contract tests owned by this node.

## 4. Scope-Out

- React Native / Expo / APK changes. The API is designed for a future mobile consumer, but mobile integration is a separate node.
- Any change to fare formulas, fare basis, `ride-options`, signed fare quote contents, quote validation, quote expiry, currency/FX, displayed fare amounts or fare acceptance.
- Passing Valhalla road distance into the existing fare engine. Existing `straight_line_planner` fare behavior remains unchanged.
- Booking creation, request lifecycle, dispatch, matching, driver availability, pickup/drop-off ETA, driver or rider tracking, or driver earnings.
- Actual travelled distance, GPS trace verification, map matching or trip telemetry.
- New tables, columns, persistence, migrations, Redis keys, Celery tasks or background jobs.
- A new geocoder, map tile provider, map framework or browser-to-Valhalla direct request.
- Production provider configuration, production deployment or production routing activation.

## 5. Interface Contract

### Endpoint

`POST /api/transport/route-preview`

Request JSON:

```json
{
  "pickup_latitude": 0.3476,
  "pickup_longitude": 32.5825,
  "dropoff_latitude": 0.0515,
  "dropoff_longitude": 32.4467
}
```

The endpoint is anonymous-allowed for the discovery/pre-commitment rider flow, rate-limited, and protected by the application's standard CSRF handling for browser POSTs. It accepts no provider URL, costing override, fare, currency, booking ID or internal database identifier.

Resolved response (shape):

```json
{
  "success": true,
  "data": {
    "resolved": true,
    "distance_m": 45352.0,
    "duration_s": 2734.163,
    "provider": "valhalla",
    "profile": "auto",
    "geometry": [
      {"latitude": 0.3476, "longitude": 32.5825},
      {"latitude": 0.0515, "longitude": 32.4467}
    ]
  }
}
```

The example geometry is illustrative; the implementation returns the provider's decoded route points, not a two-point straight connector.

Unresolved response (HTTP 200; no road measurements):

```json
{
  "success": true,
  "data": {
    "resolved": false,
    "distance_m": null,
    "duration_s": null,
    "provider": "unresolved",
    "profile": "auto",
    "geometry": []
  }
}
```

The client must not treat an unresolved response as a road route. Provider exceptions must not expose request URLs, secrets or raw upstream exception messages.

## 6. Proof of Done

- Valid resolved coordinates call the canonical GEO service exactly once with profile `auto`.
- The API returns metre/second units and latitude-first geometry without leaking internal IDs or provider configuration.
- Missing, partial, boolean, non-finite, non-numeric and out-of-range coordinates return HTTP 400 before provider I/O.
- Unresolved provider results remain unresolved with null measurements and empty geometry; no straight-line substitution is made.
- Provider errors do not create booking, request, search-cycle, offer, fare-quote or wallet records.
- Existing `ride-options` tests still prove `distance_basis=straight_line_planner`; fare behavior is unchanged.
- The website requests only when both endpoint coordinates are resolved, clears obsolete routes after edits/swaps, discards stale asynchronous responses, and renders the returned geometry.
- Loading, unresolved and resolved route states render correctly on the existing mobile-responsive page.
- Targeted Python tests, JavaScript syntax/source-contract checks, relevant rider-page tests, and the repository's applicable CI checks pass.
- Manual local verification on a mobile browser demonstrates GPS/search → route preview → map geometry and route summary. This is development verification only, not production activation.

## 7. Rollback

Revert the node's API resource/registration, rider-page route-preview integration, JS/CSS and node-owned tests together. The pre-existing GPS, geocoding, pin placement, map, ride-options and booking flows must remain usable. No data rollback is required because this node creates no persistent state.

## 8. Constraints

- Follow `docs/engineering/02-OPERATING-SYSTEM.md` and EGGE.
- GEO remains the sole owner of geographic routing and provider adapters; Transport consumes only the public GEO service interface.
- Transport remains the owner of the rider journey and route-preview HTTP surface.
- Preserve existing latitude-first coordinate semantics and canonical validation.
- Preserve the pre-commitment flow and existing authentication, CSRF, CSP and rate-limit conventions.
- Keep the route preview informational and non-persistent. It must not be treated as a booking-bound route snapshot.
- The map may display only provider-returned route geometry. A straight connector between endpoint pins must not be presented as the road route.
- Fare calculations remain unchanged and explicitly use their current straight-line planning basis.
- No shared test fixture changes; tests use `afcon360_test` only.
- No migrations, production writes, production configuration changes, direct commits to `main` or force pushes.

## 9. Acceptance Criteria

The node is acceptable when all Proof of Done checks pass, the existing website rider journey remains functional, the route overlay is demonstrably based on the Valhalla response, existing fare/booking semantics remain unchanged, and the PR review confirms that no scope-out behavior was modified.

Passing automated tests alone does not authorize production routing activation. Production remains outside this node and requires its own operational approval and staging verification.
