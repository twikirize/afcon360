# DIAGNOSE-FRESH-LOCATION-GAP — Record (evidence only, no production change)

Status:          COMPLETE (diagnostic; nothing implemented)
Date:            2026-09-23

## ROOT CAUSE

The driver location publication endpoint has no operational caller.

POST /api/transport/drivers/<driver_id>/location exists and routes to
TrackingService.update_location(), but no driver client, browser
publisher, or background task in this repository publishes driver
presence/location.

Stale location data is the symptom.
Missing operational publisher/client is the cause.

## Publication path (all current code, verified by reading)

Publisher: `POST /api/transport/drivers/<driver_id>/location`
(DriverLocationResource, driver_routes.py:255-328) — login_required,
owner-or-admin gate (403 otherwise), requires latitude+longitude.
Service: `TrackingService.update_location('driver', id, {...})`
(tracking_service.py:30-115) — validates ranges, Redis setex 300s,
DB `last_location` + `location_updated_at` (+ current-vehicle mirror
+ GEO LocationObservation history), one commit. No other production
caller exists (single call site: driver_routes.py:307). No web
client in templates/static publishes (no watchPosition, no POST);
no beat/background publisher in app/tasks. Expected publishers are
the external driver mobile clients; none are connected in dev.

## Persistence

`DriverProfile.last_location` (JSONB) + `location_updated_at`
(timestamptz). Ranker additionally requires canonical lat/lon pair.

## Driver pool state, complete set (read-only probe, corrected 2026-09-23)

MATCHABLE_POOL_COUNT = 6 (approved + online + available). The prior
"4 with vehicles" was overstated; the complete evidenced set is:

| profile | approved | online | avail | vehicle | loc | updated_at | age_s |
|---------|----------|--------|-------|---------|-----|------------|-------|
| 171 | approved | T | T | 2 | yes | 2026-09-20T22:19 | 299247 (~3.5d) |
| 172 | approved | T | T | 3 | yes | 2026-09-21T00:04 | 292947 (~3.4d) |
| 174 | approved | T | T | none | NO | never | — |
| 175 | approved | T | T | none | NO | never | — |
| 176 | approved | T | T | none | NO | never | — |
| 178 | approved | T | T | 9 | yes | 2026-09-23T10:25 | 82886 (~23h) |

So: 3 with vehicles (initialized but stale, all >> 300s) + 3 without
vehicles (location never initialized). No row implied without
evidence. Nothing mutated; identities summarized.

## Freshness contract (intentional, unchanged)

TTL = 300s defined tracking_service.py:26 (mirrored geo/services,
availability_service, matching_service, provider docstring; TTL
parity asserted in test_transport_tracking_distance.py:84-87).
Age = now − location_updated_at; NULL/missing/stale/malformed →
excluded by ranker (matching_service.py:229-238, documented
geographic contract). Do NOT change TTL to manufacture options.

## Ping cadence

No in-repo heartbeat/client/beat publisher; no invented cadence.
Staying matchable requires a publish within every 300s window —
an operational concern for driver clients, not a code gap.

## Location → matching chain (why options == [])

Online+approved+available pool (6) → ranker drops all without a
fresh canonical location → pool empty → discover_and_offer returns
no_suitable_drivers → ride-options options:[]. Distinguished from
no-drivers/offline/unavailable: drivers exist and are eligible
except for location freshness. Correct rejection, not a defect.

## Map tiles

Requested https://b.tile.openstreetmap.org/... → connection
timeout: development environment has no external network. Config is
standard public OSM default, env-switchable (config.py:433-440) —
no application defect. Map JS runs from app data (pins UI present,
"Map is ready"); only raster tiles missing.

## D2 test diff audit

tests/test_transport_d2_evidence.py: 'Estimated Fare' →
'Base fare' + comment. Supported: committed f1a3a82 replaced that
exact show.html line during the Fix-2.3 payment-block restructure
(Base fare + discount + Total); value still booking.base_price.
Assertion not weakened (label + value binding both asserted). KEEP.

## Changes made

None to production code (evidence-only node).

## Tests

- tracking_live/tracking_distance/geographic_contract/
  matching_distance/ride_options/booking_geocoding: 82 passed,
  3 errors (TestLocationEndpointAuthorization app-context fixture
  errors — pre-existing, files untouched by this node).
- booking_route_path (transaction retention): 2 passed.
- Full suite NOT run.

## Startup

STARTUP_OK; endpoints registered (verified in prior node run).

## Gate effect

REAL-RIDE evidence corrected to SELECT→BOOK PASS, BOOK→OFFER PASS,
OFFER→ASSIGNMENT BLOCKED → NODE BLOCKED (legitimate supply, no
fresh locations; nothing fabricated).

## Next (one controlled node)

DRIVER-PRESENCE-HEARTBEAT DECISION: product/ops call on how driver
clients publish locations (mobile ping cadence/contract), then a
minimal implementation node — do not start building yet.
