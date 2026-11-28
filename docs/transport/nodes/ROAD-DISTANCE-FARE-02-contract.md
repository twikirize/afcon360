# Transport Road-Distance Fare Contract (ROAD-DISTANCE-FARE-02)

**Status:** implementation candidate  
**Scope:** web and native Transport fare quotes, quote acceptance, booking/request persistence, and driver offer presentation.

## 1. Goal

A fare must be calculated from the same resolved driving route the rider reviews. A straight-line measurement is not a substitute for a road route, and a client-supplied distance, duration, geometry, or provider name is never authoritative.

GEO owns the route provider and returns provider-independent \`RouteResult\` values. Transport consumes them through \`app.transport.services.road_distance_service.measure_road_route\`.

## 2. Quote flow

1. The rider enters or selects pickup and destination places. The existing geocoding/place-selection flow resolves both to validated coordinates.
2. \`POST /api/transport/ride-options\` requests one driving route from GEO (\`profile="auto"\`).
3. The response returns \`distance_km\`, \`duration_s\`, \`duration_minutes\`, \`route_provider\`, \`route_geometry\`, and \`distance_basis="road_network"\`.
4. Each vehicle-class fare is calculated from that road distance. Each signed fare quote v2 binds:
   - pickup and destination coordinates;
   - service type and vehicle class;
   - currency, amount and fare-table version;
   - \`distance_basis="road_network"\`;
   - road distance, route duration and provider identity;
   - quote issue time.
5. The rider UI displays the road distance and estimated driving duration and dispatches the exact response route to the map preview. This replaces the earlier provisional preview route, so map, distance, duration and displayed fare refer to the same provider result.
6. On confirmation, both request-first \`RideRequestService\` and legacy/scheduled \`BookingService\` validate and consume the signed route measurements. Neither asks the provider for a second route nor accepts measurements supplied by the browser.
7. The request/booking stores road distance and duration. When a request becomes a Booking on driver acceptance, those values are copied to the Booking and driver offer presentation.

## 3. Routing failure policy

There is no Haversine/straight-line fallback for booking-bound fares.

If GEO returns an unresolved route, malformed/non-finite measurements, missing geometry, or no provider identity, the quote endpoint returns \`503 ROUTING_UNAVAILABLE\`. No signed fare quote is issued, no request/booking is created, and no driver search begins. The rider is told the driving route is unavailable and can retry.

This is deliberately fail-closed. Operations must enable and health-check the configured GEO routing provider before enabling production booking flows. For the current Valhalla adapter, deployment configuration must provide an enabled provider and a reachable routing base URL. A route provider outage therefore makes new fare quotes unavailable rather than silently underpricing trips.

## 4. Other estimate endpoint

\`POST /api/transport/fare/estimate\` is a planning endpoint:
- when pickup and destination coordinates are supplied and no explicit distance is supplied, it uses GEO road distance and labels the result \`road_network\`;
- when a caller supplies an explicit distance-only planning value, the response labels it \`explicit_planning_input\`;
- when no distance or route coordinates are supplied, the response labels the default \`planning_default\`.

These planning-only modes do not authorize booking creation. Booking commitment still requires a valid, unexpired signed road quote v2.

## 5. Compatibility and rollout

Quote v1 used the \`transport-fare-quote-v1\` salt and straight-line distance. Quote v2 uses a different salt and requires road distance, duration, provider and route identity. Old v1 tokens are intentionally rejected. A rider must refresh fare options before confirming a ride after deployment.

Web and native booking endpoints share the same quote/commitment authority. Native clients obtain a quote from \`/api/mobile/v1/transport/ride-options\` and submit the resulting token and accepted amount to the existing Booking-first or request-first endpoint.

No database migration is required: existing Booking distance/duration columns and JSON request/booking metadata hold the road measurements.

## 6. Verification required before production

- GEO routing is enabled and reachable from every web/worker runtime that serves Transport.
- \`ride-options\` returns road distance/duration and signs matching route facts.
- unresolved/malformed provider result returns 503 without a fare quote;
- quote tampering, expired tokens, changed endpoints, amount, fare version or route claims are rejected;
- request-first and Booking-first confirmation consume the exact signed facts;
- driver acceptance preserves road distance/duration on the resulting Booking;
- rider map, distance/duration summary and fare options use the same route response;
- PostgreSQL 15/18 targeted CI suites and browser script/template validation pass.
