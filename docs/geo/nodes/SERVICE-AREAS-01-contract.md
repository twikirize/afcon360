# SERVICE-AREAS-01 — Owner-managed service-area geofencing

**Status:** Implementation proposal on `feat/geo-service-area-management-20261128`
**Owner:** GEO
**Configuration:** `SystemConfig` JSON key `GEO_SERVICE_AREAS`
**Schema impact:** None. Uses the existing system configuration store.

## 1. Guarantee

Pamoja can operate location-dependent services only in the city/service polygons activated by an owner or super-admin. The service-area policy is centralized in GEO and is checked by server-side domain operations. Browser checks improve feedback but are never an authorization boundary.

An area has a stable slug ID, display name, optional ISO alpha-2 country code, active state, enabled service list and GeoJSON Polygon or MultiPolygon boundary. Supported service keys are transport, accommodation, events and tourism.

Geofence enforcement has its own global enable/disable setting. This switch does not disable GEO, routing, geocoding, maps or the Transport module.

## 2. Geometry and semantics

- GeoJSON uses RFC 7946 position order: [longitude, latitude].
- A point on an outer polygon boundary is included.
- Interior rings are holes and are excluded.
- MultiPolygon supports separated service pockets.
- Coordinates must be finite and within WGS84 numeric ranges.
- Rings must be closed. Configuration is bounded to 100 service areas and 5,000 points per area.
- Invalid polygons are rejected on save; invalid stored geometry never grants support.
- Routes are not required to keep every road segment inside the polygon. The polygon controls service eligibility endpoints; routing may need a small data buffer around it.

## 3. Transport behavior in this implementation

When enforcement is enabled:
1. The rider's pickup and destination must each belong to an active area that includes transport.
2. Both endpoints must resolve to the same area by default.
3. An owner can explicitly allow cross-area journeys.
4. Ride-options rejects unsupported journeys before issuing fare quotes.
5. Booking and ride-request creation re-check the policy server-side.
6. Route-preview checks the same policy.
7. Driver matching only ranks fresh-location drivers that are inside the same active Transport service area as the pickup. The shared ranker is used by both booking matching and request-first dispatch.

When enforcement is disabled, these area checks are bypassed. Coordinate validation, authentication, driver eligibility, quote validation and all other domain controls still apply.

This implementation does not yet change the fare distance basis; existing straight-line fare pricing remains until the separate road-distance pricing node is approved and implemented.

## 4. Owner and super-admin controls

The page is `/admin/owner/geofencing` and is guarded by the existing `owner_or_superadmin_required` decorator. It supports:
- enabling/disabling geofence enforcement;
- configuring whether cross-area ride journeys are allowed;
- creating, editing and disabling service areas;
- drawing Polygon/MultiPolygon outlines on the map or pasting GeoJSON;
- assigning one or more supported services to each area.

Settings are written through `SystemConfig.set(..., value_type='json', category='geo', updated_by=...)`. No Alembic migration is needed.

Enforcement defaults to disabled to avoid unexpectedly rejecting existing journeys before an operator has configured and validated areas. The global switch cannot be enabled unless at least one active area exists. If no Transport area is active, the manager warns that ride quotes and bookings will be rejected while enforcement is on.

## 5. Place search and client behavior

`GET /geo/api/geocode?service=transport&q=...` annotates each candidate with a fresh `service_area` verdict after the provider response/cache lookup. The geocoding provider result may be cached; the service-area verdict is recalculated so a changed boundary takes effect immediately.

The rider pickup/dropoff pickers:
- mark unsupported results as unavailable;
- exclude them from mouse and keyboard selection;
- re-request service eligibility rather than keeping stale browser-cached verdicts.

`POST /geo/api/service-area/check` is available for point or trip eligibility checks for any of the four service keys.

The quote and booking APIs remain authoritative for GPS and map-pin journeys; clients cannot bypass the policy by skipping place search.

## 6. Operational limitations and follow-up

- Transport quote, booking, request, route-preview and driver matching paths are wired in this change.
- The management schema and GEO check endpoint support Accommodation, Events and Tourism, but those domains' booking/search operations are not yet wired to enforce this policy. Each domain needs its own integration node.
- The owner map editor uses the existing browser map renderer and can fall back to direct GeoJSON entry if tiles are not configured.
- Production city polygons must be drawn, reviewed and activated by an authorized operator after deployment. None are pre-seeded by this code change.
- Valhalla routing data coverage and the road-distance fare integration are separate concerns and are not activated by enabling geofencing.
