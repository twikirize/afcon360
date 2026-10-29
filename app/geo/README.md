# AFCON360 GEO — Independent Platform Module

> GEO is a first-class platform capability, NOT a Transport/Accommodation/
> Events/Tourism subsystem. Dependency direction: domains ──→ GEO.

## What GEO owns

Coordinate validation/normalization, current state + freshness, history
infrastructure, distance / road distance / routing / duration / ETA / geometry,
map matching, matrices, geocoding / reverse / place search, POI integration,
nearby + spatial queries, geofencing primitives, tile/map adapters, realtime
delivery, provider health + fallback, geo configuration + observability.

## What GEO does NOT own

Business records: drivers, vehicles, requests, bookings, trips (Transport);
properties, rooms, availability, pricing (Accommodation); events, venues,
attendance (Events); attractions, products (Tourism); ledger (Wallet).
GEO operates on geographic representations via interfaces; domains resolve.

## Consuming GEO (stable contracts)

```python
from app.geo import get_location_service, get_routing_service, get_geocoding_service
from app.geo.services import NearbyService, bounding_box, straight_line_distance_m
from app.geo.validation import normalize_point

point = normalize_point(lat, lng)                      # raises ValidationError
dist_m = straight_line_distance_m(origin, dest)        # meters, radians-correct
hits = NearbyService.order_by_distance(center, points, radius_m=5_000.0, limit=5)
closest = NearbyService.nearest(center, points, limit=1)
box = bounding_box(center, radius_m=5_000.0)            # SQL BETWEEN pre-filter
routing = get_routing_service()
result = routing.route(origin, destination)            # RouteResult; check .resolved
geocoding = get_geocoding_service()
hits = geocoding.geocode("Nambole, Kampala")           # [] when unavailable
```

Rules: straight-line helpers are named `straight_line_*` (never road
distance); unresolved results are truthful (`resolved=False`, never fake
coordinates); no provider SDK objects cross into domains.

## Canonical contracts (Node 4)

### Coordinates

- Order is always **latitude-first**: `GeoPoint(latitude, longitude)`,
  `normalize_point(latitude, longitude)`, `(lat, lng)` tuples.
- Valid ranges: latitude `[-90, 90]`, longitude `[-180, 180]`.
- Numeric strings coerce (`"0.3476"` → `0.3476`); non-numeric, null, NaN,
  and out-of-range inputs raise `ValidationError` — never silently clamped
  (clamping invents a location the user never reported).
- Coordinates round to 7 decimals (~1 cm); extra precision is noise.
- Missing `latitude`/`longitude` keys in a payload raise `ValidationError`.

### Distance

- `straight_line_distance_m(origin, destination)` returns **meters**
  (haversine great-circle, radians applied to all angular inputs).
- Deterministic: same inputs → same output; identical points → `0.0`.
- This is explicitly NOT road distance — the name says so, and
  `RoutingService` labels its straight-line fallback
  `provider="haversine-fallback"` with `resolved=False`.

### Nearby / radius / nearest

- `NearbyService.order_by_distance(center, candidates, radius_m, limit=None)`:
  radius in meters, guarded `(0, 100_000]`; boundary **inclusive**
  (`dist <= radius`); empty candidates → `[]`; duplicates kept (identity
  belongs to the owning domain); ascending `distance_m`, ties keep input
  order; optional positive-integer `limit` truncates after sorting.
- `NearbyService.nearest(center, candidates, limit=1)`: closest N with
  **no radius gate** — use `order_by_distance` when a radius applies.
- `bounding_box(center, radius_m)` returns
  `{min_latitude, max_latitude, min_longitude, max_longitude}` in degrees,
  clamped to `[-90, 90]` / `[-180, 180]`. It is a **pre-filter** for
  caller-side queries (`WHERE lat BETWEEN ... AND lng BETWEEN ...`);
  exact membership still requires `straight_line_distance_m` because box
  corners lie outside the circle.
- GEO never filters by business rules and never returns domain records —
  hits carry `public_id` (candidate index) + `distance_m`; the owning
  domain resolves eligibility, ranking, and record lookup.
- Database-side filtering: `app/geo/sql.py::straight_line_distance_km_expr`
  owns the canonical SQL form of the great-circle contract (kilometres,
  same semantics as the Python canonical). Use it for `WHERE` radius
  filters instead of hand-rolling trigonometric SQL; never replace a
  database query with per-row Python calls for scalability.

### Freshness

- `LOCATION_TTL_SECONDS = 300` (shared with Transport tracking).
- `is_fresh(point, max_age_seconds, now=None)`: naive timestamps are read
  as UTC; missing timestamp → not fresh; boundary inclusive
  (`age <= max_age`).
- Freshness is domain-neutral recency only — Transport-specific tracking
  policy (availability flips, dispatch eligibility) stays in Transport.

### Providers and fallback truthfulness

| Capability | Status | Behavior when unconfigured |
|---|---|---|
| Routing | CONFIG-DEPENDENT | configured chain when a provider is selected; otherwise `RouteResult(resolved=False, provider="haversine-fallback")` with straight-line distance and `duration_s=0.0` |
| Geocoding (Photon) | STUB | `geocode()` → `[]`; `reverse()` → unresolved `GeocodeResult` |
| Tiles | CONFIG SEAM | `tile_url()` → `""` when unavailable; OSM attribution never stripped |
| ETA | READY | `eta_from_duration(duration_s)` — duration must come from a routing engine or labelled estimate, never distance×k |

Paid/external providers stay disabled by default with server-side
credentials only. A truthful unresolved result is always preferable to
fake success: never return fabricated coordinates, routes, or ETAs.

### Errors

GEO raises `app.utils.exceptions.ValidationError` (with `field`) for
`INVALID INPUT` (bad coordinates/radius/limit/duration). Provider outage
is `UNAVAILABLE`/`UNRESOLVED` via `resolved=False`, never an exception
masquerading as success. GEO never swallows failures into fake results
and never exposes internal database IDs.

## Provider adapters (`app/geo/providers/`)

| Capability | Primary | Later | Status |
|---|---|---|---|
| Routing | Valhalla / OSRM / Geoapify / GraphHopper / ORS / Google Maps | — | adapters live only when the provider is selected and configured; each returns a truthful unresolved miss when unavailable |
| Geocoding | Geoapify | Photon (best-effort fallback) | chain: Geoapify when operator configures `GEOAPIFY_API_KEY` + enables it; Photon when it answers after a Geoapify miss (`GEO_PHOTON_URL` + enabled); honest `unresolved` on double failure; `[lon,lat]` converted at the boundary |
| Tiles | PMTiles → Martin | external | config seam + shared Leaflet renderer (`map_renderer.py`, `static/js/geo/geo-map.js`, proven on `/geo/`) |

Paid/external providers: disabled by default, server-side credentials only,
quota + fallback explicit. OSM attribution is never stripped.

### Routing provider chain

`RoutingService` resolves through an ordered chain:

* `ROUTING_PROVIDER` — primary engine (`valhalla`, `osrm`, `geoapify`,
  `graphhopper`, `ors`, `google`); absent/`unresolved` means no road
  provider.
* `ROUTING_FALLBACKS` — comma-separated engines tried in order after the
  primary fails or is unconfigured.
* `ROUTING_PROFILE` — `auto` (default), `motorcycle`, `pedestrian`,
  `bicycle`, `scooter`, or `truck`; adapters map only profiles they
  genuinely support. An unmapped profile is a truthful miss, never a
  silent fallback profile.
* `ROUTING_TIMEOUT_S` — per-request timeout (default 10 s).

Each adapter requires its own URL and enable flag; Geoapify, GraphHopper,
ORS, and Google Maps additionally require a server-side key. The chain
returns the first `resolved=True` result. If every provider fails, the
service returns
`resolved=False, provider="haversine-fallback"` with straight-line
distance and `duration_s=0.0`; Transport must keep that result labelled as
an estimate, not a road route.

| Engine | Transport | Profiles | Notes |
|---|---|---|---|
| Valhalla | `GEO_VALHALLA_URL` | `auto`, `motorcycle`, upstream costing names | public demo available; no SLA |
| OSRM | `GEO_OSRM_URL` | `auto`/`driving` | public demo is driving-only; motorcycle/foot need a self-hosted profile |
| Geoapify | `GEOAPIFY_*` | `auto`, `motorcycle`, `pedestrian`, `bicycle`, `scooter`, `truck` | hosted; API key server-side only |
| GraphHopper | `GEO_GRAPHHOPPER_*` | `auto`, `motorcycle`, `pedestrian`, `bicycle` | hosted key or self-hosted; no key configured by default |
| ORS | `GEO_ORS_*` | `auto`, `pedestrian`, `bicycle` | hosted key or self-hosted; no public motorcycle profile |
| Google Maps | `GEO_GOOGLE_MAPS_*` | `auto`/`driving`, `pedestrian`, `bicycle` | Directions API; no motorcycle mode; key server-side only; disabled by default |

`get_routing_service()` builds the configured chain lazily (inside a Flask
app context when one exists). `reload_routing_service()` rebuilds the
singleton after a configuration change in development. Route calls accept
an optional `provider=` override; this is intended for benchmarks and
does not trigger the configured fallback chain.

### Owner routing selection

Owner / Super Admin users can override the environment chain at
`/admin/owner/transport-routing`. The non-secret selection is stored in
`SystemConfig` under category `transport_routing`:

* `TRANSPORT_ROUTING_PROVIDER`
* `TRANSPORT_ROUTING_FALLBACKS`
* `TRANSPORT_ROUTING_PROFILE`

The page stores no credentials, reads no key values, and renders only
`enabled` / `configured` booleans. Keys remain in `.env`/process
environment. A database selection disables the legacy Valhalla/OSRM
auto-fallback, so selecting `unresolved` really means straight-line
fallback until a road provider is selected again.

Saving rebuilds the routing singleton in the current worker only; other
Gunicorn workers may retain the previous chain until restart.

### Hosted routing lab (benchmark)

`scripts/routing_benchmark.py` measures one or more engines on an
operator-supplied OD list:

```powershell
& .venv\Scripts\python.exe scripts/routing_benchmark.py `
  --providers valhalla,osrm,geoapify,google `
  --valhalla-url https://valhalla1.openstreetmap.de `
  --osrm-url https://router.project-osrm.org
```

Results are written to `var/routing-lab/routing-benchmark-<stamp>.json`
and `.csv` (gitignored). The script suppresses `urllib3` logging so a
provider URL containing a key cannot leak into debug logs.

The 29 October 2026 Uganda/East Africa sample (14 OD pairs) produced:

| Engine | Resolved | Median detour ratio | p50 latency |
|---|---|---|---|
| Valhalla demo | 14/14 | 1.266 | 1460 ms |
| OSRM demo | 10/14 | 1.164 | 1384 ms |
| Geoapify | 14/14 | 1.199 | 1564 ms |

The OSRM demo failed every motorcycle pair because it is driving-only.
Valhalla's public `auto` durations were materially slower than OSRM and
Geoapify on Ugandan roads (e.g. Kampala CBD→Namboole 33.1 min versus 11.8
and 14.0 min), so its ETA calibration is not yet trusted. Public demo
endpoints have no SLA and are not a production deployment.

### Geocoding provider order + secrets

`GET /geo/api/geocode` resolves through `GeocodingService` under a locked
policy (`geoapify_needs_secondary()` + chain in `services.py`):

* A. operational failure (timeout, network, 429/5xx/any HTTP error,
  unusable shape, unavailable) -> next provider (Photon ROLE A fallback);
* B. valid success with useful candidates -> returned verbatim (no ranking
  fusion, no merged lists, no double query);
* C. valid success with zero useful candidates -> honest no-result, NO
  automatic Photon call (explicit Map / known-place recovery instead);
* D. valid but weak single candidate (non-`full_match` or confidence < 0.5,
  v1 pending bake-off calibration) -> conditional Photon supplement
  appended AFTER the Geoapify hits, each provider-labelled (ROLE B).

The response `provider` names who ANSWERED (`geoapify` / `photon` /
`unresolved`), and `attribution` carries the display credit for that
provider (`Powered by Geoapify | © OpenStreetMap contributors` for
Geoapify; `© OpenStreetMap contributors` for Photon) — consuming UIs must
render it wherever provider labels are shown.

Quota protection: 60 req/min shared endpoint budget (house `rate_limit`
helper; blueprint-scoped 429 `RATE_LIMITED` JSON), client-side debounce
retained, single-character queries answered without provider calls,
per-adapter timeouts. No search-result cache is built: no compatible
bounded store exists without shared-fixture or ToS risk (see BACKLOG
follow-up); the canonical booking snapshot stays the only authority.

`GEOAPIFY_API_KEY` is server-side only: read by `load_geo_config()`, sent as
a request parameter over HTTPS, never logged (provider exception text may
embed the URL), never rendered, never returned in any payload. Health and
config surfaces report only `enabled` / `configured` booleans. Env:
`GEOAPIFY_BASE_URL` (default `https://api.geoapify.com`), `GEOAPIFY_API_KEY`,
`GEOAPIFY_ENABLED` (default false), `GEOAPIFY_TIMEOUT_S` (default 10.0),
`GEOAPIFY_LANG` (default `en`), `GEOAPIFY_BIAS` / `GEOAPIFY_FILTER`
(optional operator passthrough, unset by default).

### Reverse lookup (`GET /geo/api/reverse`)

Provider-neutral enrichment bridge for accepted GPS/map coordinates:
`?lat=&lon=` (validated finite in-range numbers, else 400) resolves
through `GeocodingService.reverse()` (Geoapify, then Photon where
configured) and returns `{provider, latitude, longitude, display_name,
presentable, attribution}`. `display_name` is set ONLY when
`reverse_identity_presentable()` holds (non-empty identity, no
`unknown` result type, no water-body feature — provider-supplied
semantics, never a distance threshold); otherwise `display_name` is
null and callers keep their generic method label. Anonymous-allowed
(Discovery) under the shared 60/min budget. Enrichment never changes
coordinates, source, method, or canonical state.

## Shared map renderer (map renderer node)

`app/geo/map_renderer.py::build_public_map_config()` derives the
browser-safe map configuration from `GeoConfig` (tile URL template +
attribution + source label + default center/zoom). It emits only
allowlisted keys — never secrets, never internal IDs — and performs no
I/O, so application startup never depends on map infrastructure.

`static/js/geo/geo-map.js` (`window.GeoMap.init`) is the shared Leaflet
initializer: latitude-first coordinates (same order as `GeoPoint`, no
reversal), explicit truthful states instead of blank areas or fabricated
maps, no domain concepts. Leaflet assets load from `cdn.jsdelivr.net`
(the CSP-allowlisted CDN; existing pages still use `unpkg.com`, which the
enforced CSP `script-src` does not allow — see BACKLOG migration item).
The `/geo/` overview page is the first consumer (default center marker is
labelled "not a tracked location"). MapLibre remains a deferred future
option, not introduced here.

## Realtime location delivery (GEO-14)

`app/geo/realtime.py` owns the delivery mechanism, never the business
meaning: the event envelope (`version`, `location.updated`,
`entity_type`, `public_ref`, latitude-first coordinates, `observed_at`,
`age_s`, `fresh`, `source`), best-effort publication onto scoped Redis
channels (`geo:location:<type>:<public-ref>` — one channel per entity,
never a global feed), safe parsing (malformed → `None`, never raise),
and the SSE byte/iteration contract (snapshot first, then live updates;
latest-state semantics, no replay — history is GEO-15).

Producer: Transport `TrackingService.update_location()` publishes after
a successful write (driver → `driver_code`, vehicle → `license_plate`);
publication can never break the write path. Consumer: `GET
/geo/stream/location/<type>/<public-ref>` (SSE; login + admin +
transport-module guard, mirroring the existing location read surfaces)
opens with the current canonical snapshot (or truthful `missing`) and
degrades to snapshot-only with an explicit `degraded` state when the
channel is unavailable. `static/js/geo/geo-realtime.js`
(`window.GeoRealtime.connect`) is the shared browser client (fresh /
stale / missing / disconnected / degraded states, bounded reconnect);
the Transport driver location page consumes it to move its own marker.
Freshness here is geographic recency only (300 s); online/available/
dispatchable stay in Transport.

## Location observation history (GEO-15)

`app/geo/models.py::LocationObservation` is the durable, domain-neutral
observation record (one row = one WHERE + WHEN); `app/geo/history.py`
(`get_observations`) is the chronological retrieval boundary (oldest
first, public references only, internal IDs never emitted).

Writer: Transport `TrackingService.update_location()` appends the
observation in the SAME transaction as the current-state write, so
history and current state can never diverge. Every authoritative
observation is persisted — no sampling (no product requirement
justifies one; each call is already one commit, so one extra INSERT is
proportional). SSE/browser frames are derived and never persisted.

Timestamps: `observed_at` is the source observation time, which the
current producer stamps as server-receive time (no trusted device
timestamp is forwarded); `recorded_at` marks the row write. Reads never
refresh either. Consumer: `GET /geo/history/location/<type>/<public-ref>`
(JSON; login + admin + transport-module guard, same as the SSE view);
unknown references 404, empty history returns `[]`.

RETENTION_POLICY = PENDING PRODUCT/COMPLIANCE DECISION. No
location-observation retention period exists in the project, so rows
are never auto-purged; future cleanup must use soft-delete, never raw
DELETE.

## Demand / activity layers (GEO-17)

`app/geo/activity.py` answers geographic questions only: fixed decimal
grid cells (`CELL_DECIMALS = 2`, ~1.1 km) bin point streams into
concentration counts. No H3, no PostGIS, no ML — unevidenced at this
scale. Zero new writes: everything derives from authoritative records.

- **Activity** (`get_activity`, `GET /geo/activity/cells`): observation
  concentration from GEO-15 history — `observation_count` plus distinct
  observed entities per cell. Entity count is observed presence, NOT
  availability (online/available/dispatchable stay in Transport).
- **Demand** (`GET /geo/demand/cells`): booking-request concentration.
  The demand signal is Transport-owned
  (`booking_request_points`: submitted requests except drafts and
  cancellations); GEO only bins the points. No fares, no surge, no
  dispatch meaning — `request_count` per cell only.

Time windows (`since`/`until`) are REQUIRED — no implicit default
window; responses echo the resolved window plus `computed_at` so
historical aggregates are never mistaken for live state. Both views
are admin-guarded (login + admin + transport module), per-entity-type
scoped, and emit counts/centers only: no raw movements, no internal
IDs. SUPPLY vs ACTIVITY vs DEMAND stay separate by construction.

## Rider booking-scoped live tracking (GEO rider node)

`GET /geo/stream/booking/<booking_reference>` (SSE; login +
transport-module guard) streams the assigned driver's location to the
booking owner. Authorization is booking ownership — never admin role,
never driver-reference knowledge: the Transport-owned
`TrackingService.get_rider_tracking_subject` decides (owner or global
admin; active assignment states per canonical
`ACTIVE_ASSIGNMENT_STATUSES`, disputed latched; terminal states,
released assignment, and missing driver deny).

Booking state and assignment are RE-VALIDATED on every stream tick
(message or heartbeat): terminal/release/driver-change closes the
stream with an explicit `closed` frame (the shared client stops
retrying and reports `closed`; reconnect re-authorizes from scratch).
Frames carry only the assigned driver's public reference (per-tick
match guard). Snapshot-first reconnect recovery, truthful
fresh/missing/degraded states, no internal IDs. The booking show page
consumes it through the shared `GeoMap` renderer + `GeoRealtime`
client only when the server-computed `tracking_allowed` flag is set —
the page never decides authorization.

## Configuration

`app/geo/config.py::load_geo_config()` reads Flask `GEO` config with env
fallback:

* routing chain: `ROUTING_PROVIDER`, `ROUTING_FALLBACKS`,
  `ROUTING_PROFILE`, `ROUTING_SHADOW`, `ROUTING_TIMEOUT_S`;
* engines: `GEO_VALHALLA_URL/_ENABLED`, `GEO_OSRM_URL/_ENABLED`,
  `GEOAPIFY_BASE_URL/_API_KEY/_ENABLED`, `GEO_GRAPHHOPPER_URL/_KEY/_ENABLED`,
  `GEO_ORS_URL/_KEY/_ENABLED`, `GEO_GOOGLE_MAPS_URL/_KEY/_ENABLED`;
* geocoding/tiles/location: `GEO_PHOTON_URL/_ENABLED`,
  `GEO_TILES_KIND/_URL/_STYLE_URL`, `GEO_LOCATION_TTL_SECONDS`.

No new settings model — reuse SystemConfig/TransportSetting KV. Provider
keys are server-side only; health and config surfaces report only
`enabled` / `configured` booleans.

## Freshness

`LOCATION_TTL_SECONDS = 300`, shared with Transport `TrackingService`.
Current state: Redis. History: Postgres `geo_location_observations` (GEO-15; plain table, not PostGIS).

## Roadmap (mandate §8 order)

1. boundary ✅ (this slice) → 2. contracts ✅ → 3. validation ✅ →
4. PostGIS → 5. current-location → 6. history → 7. routing adapter →
8. distance/ETA → 9. geocoding → 10. nearby → 11. realtime → 12. map
abstraction → 13. MapLibre component → 14. demand → 15/16. domain
integration → 17. legacy migration (incl. matching radians fix) →
18. observability/scale → 19. docs.
