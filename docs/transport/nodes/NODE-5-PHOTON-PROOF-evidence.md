# NODE 5 — PHOTON PROVIDER PROOF (evidence)

Phase: PROOF. Lane: proof-only. Status: awaiting panel review.
Pass 1: 2026-10-05 UTC 20:03:58 · Pass 2 (evidence completion): 2026-10-05 UTC
20:19-20:23. Python 3.13.14, requests 2.33.1.
Adapter under test: `app/geo/providers/photon.py` (**unmodified in both passes** — see §11).

> **The adapter is NOT production-ready.** See §10 D1 (it cannot resolve anything against
> the only reachable real Photon endpoint as written), §8.2 P1 (no application surface
> reaches it), and §13.3 (what was not proven). This node proves behavior; it does not
> clear the adapter for use.

---

## §0 Status classification at a glance

Full detail: §14-§17 (pass 2). Nothing below is a claim about production readiness.

**PROVEN — live, against the real Photon 1.3.0 endpoint, through unmodified adapter code**

| Claim | Where |
|---|---|
| Forward geocoding resolves real locations; 200 + GeoJSON FeatureCollection; `resolved=True`, `provider="photon"` | §4 |
| Reverse geocoding resolves real points; first feature wins; nearest-feature snap measured | §5, §15.7 |
| GeoJSON `[lon,lat]` → latitude-first conversion is exact, no rounding, no silent swap | §6.1 |
| Round-trip forward→reverse reproduces point and name exactly | §5.4 |
| Coordinate-range/bool/NaN validation rejects before any I/O | §7.3 |
| Truthful miss on 9 distinct failure modes; no exception escapes; never fabricates coordinates | §7 |
| No retry: every call issued exactly 1 outbound HTTP request | §7.2 |
| Zero network at import, construction, and `load_geo_config()`; no startup dependency | §8.1 |
| Config is unconfigured: zero `GEO_*` keys anywhere; health reports `enabled=false, configured=false` | §8 |
| **Default timeout `10.0 s` is sufficient** on this network path; resolution succeeded | §14.1 A2 |
| **Default path as-written does NOT resolve** — HTTP 403, cause is D1 not the timeout | §14.1 A1 |
| Display-name degradation is real and reproducible for unnamed/address-only features | §15.1 |
| Three distinct villages named `Kampala` produce the **identical** label `Kampala, Uganda` | §15.3 |
| Reverse snaps to the nearest feature by up to ~457 m; adapter never substitutes it for the caller's point | §15.7 |
| OSM `osm_type`/`osm_id` + full result ordering stable across 4 repeats in one session | §16.1 |
| Forward and reverse agree on the same physical feature's OSM reference | §16.2, §16.3 |
| `osm_id` alone is ambiguous — the `osm_type`+`osm_id` pair is required | §16.4 |

**SOURCE / TEST-BACKED — from repository source and the existing suite, not from live traffic**

| Claim | Where |
|---|---|
| `build_geocoding_service()` has no production caller → provider unreachable from the app | §8.2 (grep + source) |
| `BaseProvider.health()` never fills `latency_ms` / `last_success` / `last_error` | §10 P3 (source) |
| `timeout_s` is never passed by `app/geo/config.py` → pinned to the 10.0 dataclass default | §8, §14.1 A0 |
| Localhost-fake contract suite (20 tests) green, unmodified | §12 |

**NOT PROVEN — explicitly out of reach of this node**

| Gap | Where |
|---|---|
| Behavior against a **self-hosted Uganda/Africa extract** — no such deployment exists | §10 P4 |
| Behavior of any AFCON360 environment: no endpoint is configured anywhere | §8 |
| OSM reference stability across a Photon data reimport, redeploy, or over days | §16.5 C5 |
| Rate-limit / throttling behavior under load | §2 (corrected wording) |
| `display_name` degenerating to `""` — plausible from `_display_name` source, **not observed** live | §15.2 |
| A `no_name` + `no_city` feature — plausible, **not observed** in 18 real reverse probes | §15.2 |
| Concurrency, bulk throughput, payload-size limits | §13, open |
| Non-Point geometries: code path skips them, but no live Photon response produced one | §13, open |

**DEFECTS** D1-D6 (§10) · **DEPENDENCIES** P1-P4 (§10) · **EXTENSION CANDIDATES** E1-E5 (§10)

**PANEL DECISIONS RECORDED** (§13) — D1 deferred and recorded only; D5/D6/P4 recorded now,
decision deferred; `place_ref` is display/audit only, never a primary key or cache key.

---

## 1. Scope actually executed

| Asked | Executed |
|---|---|
| Inspect adapter source | Yes — full file, 153 lines, read |
| Inspect geocoding service integration | Yes — `app/geo/services.py:150-173`, `:296-332` |
| Inspect provider configuration | Yes — `app/geo/config.py:43-84` |
| Inspect existing GEO geocoding tests | Yes — `tests/test_geo_geocoding.py` (334 lines), run: 20 passed |
| Inspect timeout/error behavior | Yes — live, 9 distinct failure probes (§7) |
| Live forward proof | Yes — 3 real queries, 15 normalized hits (§4) |
| Live reverse proof | Yes — 5 real points + 1 round-trip (§5) |
| Do not fabricate | Every value below came from the live endpoint or the adapter's own return |
| Do not redesign the adapter | No code change made. 4 defects recorded, none fixed (§10, §12) |

Exclusions honored: no caching, no failover, no provider redesign, no routing, no typed
search, no registry, no canonical-contract implementation, no migrations.

---

## 2. Endpoint under test + provider identity

Public Photon instance, confirmed live and reachable from this workstation. Probed 9
alternative public Photon hosts first (`photon.maptiler.com`, `photon.fossgis.de`,
`photon.geofabrik.de`, `photon.nchc.org.tw`, `photon.osm.ch`, `photon.entopia.eu`,
`photon.openstreetmap.fr`, `photon.geocoding.ai`, `search.photon-ondemand.com`) —
all unreachable or erroring from this network. `photon.komoot.io` is the only real
Photon endpoint reachable here.

Provider identity, live `GET /status`:

```json
{"status":"Ok","import_date":"2026-09-26T22:59:05Z","version":"1.3.0","git_commit":"4c28c7c1"}
```

| Property | Value |
|---|---|
| Endpoint | `https://photon.komoot.io` |
| Photon version | 1.3.0 |
| OSM data import date | 2026-09-26 |
| Server | `nginx` |
| No API key / no credentials | Confirmed — requests succeeded with none |
| Rate limiting | **No rate-limit headers were observed in the normal single-request responses tested. Rate-limit behavior under load was not tested against the public endpoint.** |

**Standing constraint honored:** `app/geo/providers/photon.py:5-6` states self-hosted
Photon is primary and public Nominatim must not become the production dependency.
This proof used the public instance **for verification only**. No repository config
file, `.env`, or application setting was changed (§6). Enabling a public instance in
any environment remains a human decision and is **not** recommended by this node.

---

## 3. Adapter source verified

`app/geo/providers/photon.py` — full source read; no defect in the coordinate path.

| Lines | Element | Verified behavior |
|---|---|---|
| 43-46 | `PhotonConfig` | `base_url=""`, `timeout_s=10.0`, `enabled=False` (disabled until operator configures) |
| 49-53 | `_display_name()` | Joins only `name`, `city`, `country`; skips falsy parts; never invents |
| 56-74 | `_feature_to_result()` | `lng, lat = coordinates[0], coordinates[1]` (GeoJSON `[lon,lat]` → lat-first); `validate_coordinates` gate; `raw=dict(properties)` verbatim; `resolved=True`; any `KeyError/TypeError/ValueError/IndexError` → `None` (skip, not fabricate) |
| 85-86 | `is_available()` | `enabled AND base_url` — pure config truth, zero I/O |
| 88-95 | `_validate_query()` | Rejects non-str / empty / whitespace **before** any request |
| 97-111 | `_validate_point()` | Rejects out-of-range / NaN / bool before any request |
| 113-131 | `geocode()` | `GET {base}/api` params `{q, limit}`; `raise_for_status()`; `.get("features") or []`; per-feature skip; blanket `except Exception` → `[]` |
| 133-153 | `reverse()` | `GET {base}/reverse` params `{lat, lon}`; empty collection → unresolved; **first feature wins**; blanket `except Exception` → unresolved |

Integration:

- `app/geo/services.py:319-332` `build_geocoding_service(config)` wires `PhotonGeocoder`
  only when `enabled and base_url`; otherwise returns a provider-less `GeocodingService`.
- `app/geo/services.py:150-173` `GeocodingService` delegates when a provider exists,
  otherwise returns truthful misses (`[]` / `resolved=False`, `provider="unresolved"`).
- `app/geo/routes.py:41-42` and `:555-556` expose only `enabled` + `configured` booleans.

Coordination helper proven in-range for real Photon values:
`app/utils/validators.py:619-657` `validate_coordinates` (bool rejection at :634,
`COORDINATE_REGEX = ^-?\d+(\.\d+)?$` at :44). All 20 live normalized hits passed this gate.

---

## 4. LIVE FORWARD PROOF

### 4.1 Request shape (verbatim, from the recorded outbound call)

```
GET https://photon.komoot.io/api
params = {'q': 'Nakasero Market, Kampala, Uganda', 'limit': 5}
timeout = 25 s
→ HTTP 200, Content-Type: application/json, 1906 bytes
```

Method `GET`, path `/api`, parameters `q` (free text) and `limit` (int) — exactly as
the adapter docstring (`:18-21`) and implementation (`:118-120`) specify. No other
parameters are sent by the adapter.

### 4.2 Response shape (verbatim live body, 5 features)

Top-level keys: `["features", "type"]`. Feature = `{"type":"Feature","properties":{...},"geometry":{"type":"Point","coordinates":[lon, lat]}}`.

First feature, verbatim:

```json
{
  "type": "Feature",
  "properties": {
    "osm_type": "N", "osm_id": 9626381835, "osm_key": "place", "osm_value": "village",
    "type": "district", "name": "Nakasero Market", "city": "Kampala",
    "state": "Central Region", "country": "Uganda", "countrycode": "UG"
  },
  "geometry": { "type": "Point", "coordinates": [32.580514, 0.3117701] }
}
```

Fifth feature (shows the optional `extent` bbox key appearing on a polygon-derived hit):

```json
{
  "type": "Feature",
  "properties": {
    "osm_type": "W", "osm_id": 329420618, "osm_key": "amenity", "osm_value": "marketplace",
    "type": "house", "name": "Nakasero Market Upper Section", "street": "Market Street",
    "locality": "Nakivubo", "district": "Central", "city": "Kampala",
    "state": "Central Region", "country": "Uganda", "countrycode": "UG",
    "extent": [32.5795183, 0.3120111, 32.5802706, 0.3115517]
  },
  "geometry": { "type": "Point", "coordinates": [32.5798945, 0.3117815] }
}
```

### 4.3 Adapter output (live, unmodified adapter code)

`geocode("Nakasero Market, Kampala, Uganda", limit=5)` → **5 hits, all `resolved=True`,
`provider="photon"`**:

| # | latitude | longitude | display_name |
|---|---|---|---|
| 0 | 0.3117701 | 32.580514 | `Nakasero Market, Kampala, Uganda` |
| 1 | 0.3125294 | 32.5794411 | `ABC Capital Bank Nakasero Market, Kampala, Uganda` |
| 2 | 0.3105867 | 32.5827579 | `Imprimerie Rosebury Lane, Nakasero Market, Kampala, Uganda` |
| 3 | 0.3117815 | 32.5798945 | `Nakasero Market Upper Section, Kampala, Uganda` |
| 4 | 0.3138618 | 32.5836655 | `African Art Crafts Market, Kampala, Uganda` |

Two more real queries, both 200 with 5 hits each:

- `geocode("Kampala", limit=5)` → 5 hits, `(0.3177137, 32.5813539)` first.
- `geocode("Entebbe", limit=5)` → 5 hits, `(0.0611715, 32.4698564)` first.

Observed latencies: 2.58 s, 2.64 s, 2.66 s (mean ≈ 2.6 s) — see §7.1, this matters.

---

## 5. LIVE REVERSE PROOF

### 5.1 Request shape (verbatim)

```
GET https://photon.komoot.io/reverse
params = {'lat': 0.3476, 'lon': 32.5825}
→ HTTP 200, application/json, 409 bytes, 1 feature
```

`lat` holds the latitude and `lon` the longitude — reversal-detecting and correct.

### 5.2 Response shape (verbatim live body)

```json
{
  "type": "FeatureCollection",
  "features": [
    {
      "type": "Feature",
      "properties": {
        "osm_type": "N", "osm_id": 8963738622, "osm_key": "amenity", "osm_value": "clinic",
        "type": "house", "name": "Cure Health Clinic", "street": "Northern Bypass",
        "locality": "Kyebando", "district": "Kawempe", "city": "Kampala",
        "state": "Central Region", "country": "Uganda", "countrycode": "UG"
      },
      "geometry": { "type": "Point", "coordinates": [32.5822782, 0.3475086] }
    }
  ]
}
```

### 5.3 Adapter output across 5 real points

| Input point | Label | Adapter result |
|---|---|---|
| `0.3476, 32.5825` | Kampala / Nakasero approx | `resolved=True`, `(0.3475086, 32.5822782)`, `Cure Health Clinic, Kampala, Uganda` |
| `0.3177137, 32.5813539` | Kampala city centre | `resolved=True`, identical point returned, `Kampala, Kampala, Uganda` |
| `0.0514, 32.4675` | Entebbe | `resolved=True`, `(0.0514656, 32.4671593)`, `Entebbe, Uganda` |
| `0.0, -30.0` | open ocean | `resolved=False`, coords `None` — live 200 with `features: []` |
| `0.0, 0.0` | Null Island | `resolved=False`, coords `None` — live 200 with `features: []` |

Note: reverse returns the **nearest OSM feature's** coordinate, not the input point
(0.3476, 32.5825 → 0.3475086, 32.5822782; a ~13 m snap). Consumers must not treat the
returned coordinate as the query coordinate.

### 5.4 Round-trip proof (forward output fed back into reverse)

```
forward("Kampala")            → (0.3177137, 32.5813539)  "Kampala, Kampala, Uganda"
reverse(same point)           → (0.3177137, 32.5813539)  "Kampala, Kampala, Uganda"
name match: True   |   point reproduced exactly: True
```

This single test proves end-to-end that the `[lon,lat] → (lat,lng)` conversion and the
reverse `lat`/`lon` parameter mapping are both correct against real Photon data. A
swapped coordinate order could not survive this round trip.

---

## 6. NORMALIZATION PERFORMED BY THE ADAPTER

### 6.1 Coordinate order — proven, not assumed

Live wire body compared element-by-element against adapter output for all 5 `Entebbe`
hits:

```
wire=[32.4698564, 0.0611715] -> adapter(lat=0.0611715, lng=32.4698564)   lon==coordinates[0]: True   lat==coordinates[1]: True
wire=[33.6490117, 2.700359 ] -> adapter(lat=2.700359,  lng=33.6490117)   lon==coordinates[0]: True   lat==coordinates[1]: True
wire=[32.8317423, 2.3957988] -> adapter(lat=2.3957988, lng=32.8317423)   lon==coordinates[0]: True   lat==coordinates[1]: True
wire=[30.85464,  2.488945 ] -> adapter(lat=2.488945,  lng=30.85464 )   lon==coordinates[0]: True   lat==coordinates[1]: True
wire=[34.1157801, 3.0033057] -> adapter(lat=3.0033057, lng=34.1157801)   lon==coordinates[0]: True   lat==coordinates[1]: True
```

**No silent swap. Conversion is exact, no rounding applied.**

### 6.2 `display_name` composition — live table

`_display_name()` joins `name`, `city`, `country` only. Real consequences:

| name | city | state | country | adapter `display_name` |
|---|---|---|---|---|
| `Nakasero Market` | `Kampala` | Central Region | Uganda | `Nakasero Market, Kampala, Uganda` |
| `Kampala` | `Kampala` | Central Region | Uganda | `Kampala, Kampala, Uganda` (name repeats city) |
| `Kampala` | *(absent)* | Sironko | Uganda | `Kampala, Uganda` (state dropped) |
| `Entebbe` | *(absent)* | Kotido | Uganda | `Entebbe, Uganda` |
| `Kampala` | *(absent)* | Sud-Kivu | `RΘpublique dΘmocratique du Congo` | `Kampala, RΘpublique dΘmocratique du Congo` |

The last row is the provider's own encoding artifact, reproduced verbatim (the endpoint
serves non-ASCII country names without a declared charset; `Θ` is U+0398). The adapter
performs **no** encoding repair, no normalization, no case folding, no dedupe of a
repeated name/city. Whatever Photon says is what surfaces.

Reverse consequence observed live: the Entebbe reverse hit has **no `name`** but does
carry `housenumber="1A"`, `street="Mugwanya Road"`, `district="Kakeeka"`,
`city="Entebbe"` → `display_name` collapses to `"Entebbe, Uganda"`. Street and house
number are present in the response and dropped by normalization.

### 6.3 `raw` passthrough

`raw=dict(properties)` — a verbatim, untyped shallow copy of Photon properties.
Observed key inventory across all 15 live forward hits (7 distinct key sets):

| Hits | Property keys observed live |
|---|---|
| 4 | `name, country, countrycode, state, osm_type, osm_id, osm_key, osm_value, type` |
| 3 | `county, name, country, countrycode, state, osm_*, type` |
| 3 | `name, street, locality, district, city, state, country, countrycode, osm_*, type` |
| 2 | `name, state, country, countrycode, extra, extent, osm_*, type` |
| 1 | `name, city, state, country, countrycode, osm_*, type` |
| 1 | `…, district, extent, …` |
| 1 | `name, city, state, country, countrycode, extra, extent, osm_*, type` |

Union of all keys ever returned: `name, street, housenumber, locality, district, city,
county, state, country, countrycode, osm_type, osm_id, osm_key, osm_value, type, extra,
extent`. **`accuracy` never appeared** — not on any of the 20 live calls.

`extent` is present on some features and is **not** in `[minLon, minLat, maxLon, maxLat]`
order. Live Kampala value `[32.5098753, 0.4057676, 32.6687413, 0.2143285]` only makes
geographic sense as `[west, north, east, south]` (a `[w,s,e,n]` reading would give
south > north). Verified against the Nakasero bbox too. The adapter does not touch
`extent`; whoever consumes it must not assume GeoJSON `[w,s,e,n]` ordering.

### 6.4 What the adapter does NOT normalize

No client-side clamp of returned hit count to the requested `limit`; no filtering by
country/bbox/language; no dedupe (the two distinct `Kampala` OSM relations R/10546821
and R/5457274 returned identical coordinates as separate hits); no confidence or
relevance score exposure; no caching; no retry.

---

## 7. FAILURE BEHAVIOR (live)

Every probe below used a real network call against the live endpoint or a real
resolution failure. Call counts are exact.

| # | Probe | Transport outcome | Adapter returned |
|---|---|---|---|
| 4a | `timeout_s=0.05` forward / reverse | `ConnectTimeout` (connect timeout=0.05) | `[]` / `resolved=False` |
| 4a | `timeout_s=0.5`, `1.0` forward / reverse | `ReadTimeout` (read timeout=0.5 / 1.0) | `[]` / `resolved=False` |
| 4a | `timeout_s=2.0`, `2.5`, `3.0` forward / reverse | HTTP 200 | 5 hits / `resolved=True` |
| 4b | `base_url=".../no-such-path"` forward / reverse | HTTP 404 | `[]` / `resolved=False` |
| 4c | `limit="abc"` forward | HTTP 400, body `{"limit":[{"message":"TYPE_CONVERSION_FAILED","args":{},"value":"abc"}]}` — valid JSON, **not** GeoJSON | `[]` |
| 4c | `limit=0` forward | HTTP 200 (server ignores the value) | 1 hit, `resolved=True` |
| 4d | `q="zzzqqxnothinghere9999"` | HTTP 200, `features: []` | `[]` (truthful empty) |
| 4e | unreachable host `photon.invalid-hostname-afcon360.example` | `ConnectionError` / `getaddrinfo failed` | `[]` / `resolved=False` |
| 4f | `geocode("")`, `("   ")`, `(None)`, `(123)` | transport poisoned with a raising stub — never reached | `ValidationError`, 0 calls |
| 4f | `reverse(91,0)`, `(0,181)`, `(nan,0)`, `(True,0)` | transport poisoned — never reached | `ValidationError`, 0 calls |

### 7.1 Timeout reality against the real provider

The single `PhotonConfig.timeout_s` is applied by `requests` to **both** connect and
read phases. Measured live latencies for the same three forward queries were
**1.37 s – 4.43 s** (pass 1; pass 2 with the real default timeout added 3.24 s – 4.09 s
forward and 3.24 s – 3.43 s reverse — see §14.1). Consequence: `timeout_s=1.0` times out
against a perfectly healthy endpoint, while `timeout_s=0.05` fails during TLS connect,
not read. The default `10.0 s` was sufficient on 3 of 3 pass-2 runs (§14.1).

### 7.2 Truthfulness

Across all 9 failure probes: no exception escaped to the caller, no fabricated
coordinate was produced, no partial/damaged result was returned, and **no probe issued
more than one outbound HTTP request** (no retry loop). `reverse` failures return
`provider="photon", resolved=False`; forward failures return `[]`.

### 7.3 Pre-I/O validation, live

With the transport replaced by a stub that raises on contact, every invalid-input case
still raised `ValidationError` and never reached the network. `reverse(GeoPoint(True, 0.0))`
was correctly rejected (bool guard at `app/utils/validators.py:634`).

### 7.4 The one live failure the adapter cannot avoid

Running the adapter **completely unmodified** against the live endpoint with its true
default User-Agent (`python-requests/2.33.1`) yields:

```
geocode(...)  -> []            1 call, HTTP 403, sent_UA=None
reverse(...)  -> resolved=False 1 call, HTTP 403, sent_UA=None
403 body: '<html>...<h1>403 Forbidden</h1>...<center>nginx</center>...' (not JSON)
```

The endpoint requires an identifying `User-Agent`; `python-requests/2.33.1` is refused
with 403, while any ordinary application UA returns 200. The adapter sends **no headers
at all** (`app/geo/providers/photon.py:119-120`, `:139-143`). The miss it returns is
truthful, but the success path is unreachable against this provider without a header.
See defect D1.

---

## 8. CONFIGURATION STATE (live, unchanged)

| Probe | Result |
|---|---|
| `os.environ` keys starting `GEO_` | **NONE** |
| `GEO_*` keys in `.env`, `.env.local`, `.env.docker`, `.env.prod`, `.env.test`, `.env.testing` | **NO GEO_* KEYS in any file** |
| `app.config["GEO"]` | absent → `load_geo_config()` falls through to pure env default |
| `load_geo_config().photon` | `PhotonConfig(base_url='', timeout_s=10.0, enabled=False)` |
| `routes._health_payload()["adapters"]["photon"]` | `{"enabled": false, "configured": false}` |
| `build_geocoding_service(config).provider_name` | `'unresolved'` |
| Disabled service `geocode("Kampala")` / `reverse(...)` | `[]` / `resolved=False` |
| `PhotonGeocoder().is_available()` | `False`; `health()` → `ProviderHealth(available=False, latency_ms=0.0, last_success='', last_error='')` |
| Network calls during all disabled/unconfigured probes | **0** |
| `timeout_s` operator override | **None exists** — `app/geo/config.py:73-76` never passes `timeout_s`, so it is always the 10.0 dataclass default |

### 8.1 Zero startup / zero import I/O

`load_geo_config()` → env reads only. `PhotonGeocoder.__init__` → no I/O.
`build_geocoding_service()` → no I/O (repo test `test_build_geocoding_service_enabled_wires_adapter_without_io`
asserts this; my live probes independently recorded 0 calls). Confirmed: **no startup
dependency on any geocoding provider.**

### 8.2 Integration reachability gap

`get_geocoding_service()` (`app/geo/services.py:296-300`) always returns a
provider-less `GeocodingService`. `build_geocoding_service(config)` is the only code
path that constructs a `PhotonGeocoder`, and a repository-wide search finds it called
**only from `tests/test_geo_geocoding.py`**. Therefore, even with `GEO_PHOTON_URL` and
`GEO_PHOTON_ENABLED` set, no running application surface can reach Photon today. See
dependency P1.

---

## 9. FIELDS AVAILABLE FOR FUTURE CANONICAL RESOLUTION (Node 1 §8.5)

Assessed against `docs/transport/nodes/NODE-1-canonical-location-contract.md` §1-§4.
This section reports availability only; **no adapter change was made.**

| Node 1 `ResolvedLocation` field | Supplied by live Photon via `GeocodeResult`? | Evidence |
|---|---|---|
| `latitude` | **Yes, typed** | 20/20 live hits populated, in-range, 7-decimal-safe |
| `longitude` | **Yes, typed** | same; order verified §6.1 |
| `source` | No — caller-set | Node 6 sets `search`; Node 7 enrichment does not change it |
| `resolved_at` | No — server time | not a provider concern |
| `label` | No — rider selection | not a provider concern |
| `display_name` | **Yes, typed** | present on every live hit, but lossy (§6.2) |
| `accuracy_m` | **No** | `accuracy` never appeared in any live property set → must stay `None`, exactly as contract §2 requires |
| `place_ref` (`osm_id`/`osm_type`) | **Present in provider data, NOT typed** | live in every feature (`osm_type` ∈ {N, W, R}, `osm_id` int) but reachable only via untyped `raw` |
| `label_status="enriched"` | Derivable by caller | reverse returned `resolved=True` + `raw`; Node 7 can set it |
| `area` (locality/admin) | **Present in provider data, NOT typed** | live keys `locality`, `district`, `city`, `county`, `state` |

Live locality hierarchy actually observed in Uganda (evidence for Node 1 §10.3, which
explicitly deferred this decision to a node holding real Photon responses):

| Feature class | Keys populated |
|---|---|
| City/place relation (Kampala R/10546821) | `state`, `country`, `countrycode`, `extra.admin_level`, `extent` |
| Village node (Kampala, Sironko) | `county`, `state`, `country`, `countrycode` |
| Named house (bank, clinic) | `street`, `locality`, `district`, `city`, `state`, `country`, `countrycode` |
| Unnamed house (Entebbe reverse hit) | `housenumber`, `street`, `district`, `city`, `state`, `country`, `countrycode` — **`name` and `locality` absent** |
| Polygon-derived place (marketplace) | named-house keys **plus** `extent` |

`countrycode` (`"UG"`, `"CD"`) is a reliable, always-present country discriminator
across all 20 live calls and is the cleanest available country filter if one is ever
needed.

---

## 10. GAPS / DEPENDENCIES / EXTENSION CANDIDATES

Recorded, **not implemented** (per the caveat: do not extend the adapter merely because
a future design might want more fields).

### Defects in the adapter as written

| ID | Severity | Finding | Evidence |
|---|---|---|---|
| **D1** | High | **No `User-Agent` is sent.** The only reachable real Photon endpoint answers `python-requests/2.33.1` with **HTTP 403**. Against that endpoint the adapter can never resolve a single location, forward or reverse. It degrades truthfully (`[]` / `resolved=False`), so this is silent non-function rather than corruption — the worst failure mode for an operator who believes geocoding is on. | §7.4 |
| **D2** | Medium | **`limit` is not validated.** `geocode(query, limit)` forwards whatever the caller passes. `limit="abc"` produced a live HTTP 400 with a non-GeoJSON body (`{"limit":[{"message":"TYPE_CONVERSION_FAILED",…}]}`); the caller's fault becomes a remote round trip and a `[]` that is indistinguishable from "no such place". `limit=0` / `-1` are silently accepted by the server. `query` and `point` are both strictly validated; `limit` is the odd one out. | §7 row 4c |
| **D3** | Medium | **`timeout_s` is not configurable.** `app/geo/config.py:73-76` constructs `PhotonConfig(base_url=…, enabled=…)` and never passes `timeout_s`, so the value is hard-pinned to the 10.0 s dataclass default with no env var, no `app.config["GEO"]` key, and no UI surface. Operators cannot tune it for a slow self-hosted Uganda extract. | §8 |
| **D4** | Low | **No client-side clamp on returned hits.** The adapter returns however many features Photon sent; `limit` is only a server hint. A server that ignores or over-honors `limit` silently changes the payload the domain receives. | §6.4 |
| **D5** | Medium | **`display_name` is not unique or address-adequate.** Proven live: three physically distinct villages named `Kampala` (Sironko, Kamwenge, and one in Sud-Kivu DRC) all yield the identical `display_name` `"Kampala, Uganda"` at coordinates over 3° apart. Four physically distinct segments of `Kintu Road` all yield `"Kintu Road, Kampala, Uganda"`. An unnamed house at `housenumber 1A, Mugwanya Road, Entebbe` collapses to `"Entebbe, Uganda"`. Node 1 §6 makes `display_name` the primary human identity for rider, driver and admin; today that identity can be ambiguous between unrelated places. | §14.2 |
| **D6** | Low | **No case normalization.** The same street is returned as both `Kololo Hill Drive` (W/45343641) and `KOLOLO HILL DRIVE` (N/8881587388) in one result set; both pass through verbatim. Deduping or grouping search candidates by label will not work on `display_name`. | §14.2 |

**Severity note on D5:** it is a data-composition limitation of `_display_name`
(`photon.py:49-53`), not a correctness failure — coordinates are correct in every case
probed. It is recorded as a defect because Node 1 depends on the label.

### Extension candidates required by Node 1 (not defects)

| ID | Candidate | Node 1 need | What live Photon already supplies |
|---|---|---|---|
| **E1** | Typed `place_ref` on `GeocodeResult` (or an explicit accessor) | §2 `place_ref` "from `osm_id/osm_type` when present" | `osm_type`, `osm_id` present on 20/20 live features; today only reachable through untyped `raw` |
| **E2** | Typed `area`/locality extraction from `raw` | §2 `area`, §10.3 open decision 3 | `locality`/`district`/`city`/`county`/`state` observed live; the `area` shape decision now has real data behind it |
| **E3** | Richer `display_name` composition for reverse enrichment | §6: `display_name` is the primary human identity for rider/driver/admin | `street`, `housenumber`, `district`, `locality` present live but dropped; the Entebbe reverse hit produced only `"Entebbe, Uganda"` for a specific house address |
| **E4** | Consumer-side `extent` handling with explicit `[west, north, east, south]` ordering | any future bbox use | `extent` observed live on 3 of 15 forward hits, in `[w, n, e, s]` order — not GeoJSON `[w, s, e, n]` |
| **E5** | Encoding normalization of provider text | §10.5 localization | live country name arrived as `RΘpublique dΘmocratique du Congo`; adapter passes through verbatim |

### Hard dependencies (no adapter change can satisfy these)

| ID | Dependency |
|---|---|
| **P1** | **No application surface reaches the provider.** `build_geocoding_service()` has no production caller; `get_geocoding_service()` always returns a provider-less service. Even a fully configured, fully working adapter is unreachable from the running app. |
| **P2** | **No authorized production Photon endpoint.** GEO-16 (`BACKLOG.md:2599-2609`) remains open: self-hosted is the locked stack, no endpoint exists in any environment. The public instance used here is verification-only and must not become the production dependency (`app/geo/providers/photon.py:5-6`). |
| **P3** | **No observable provider health.** `BaseProvider.health()` (`app/geo/providers/base.py:32-34`) is static: it echoes `is_available()` and never fills `latency_ms`, `last_success`, or `last_error`. After a live failure an operator has no signal distinguishing "not configured" from "configured but failing". Out of scope for this node; recorded. |
| **P4** | **No authorized self-hosted Photon, so no Uganda/Africa-extract evidence exists.** Every live observation in this document comes from a global-planet public instance (`import_date 2026-09-26`) reached over the public internet. Local coverage, address density, and latency for a self-hosted Uganda extract are unknown. Node 1 and Node 7 plans must not treat these numbers as target-environment numbers. |

---

## 11. FILES CHANGED

None in `app/`, `tests/`, `migrations/`, `templates/`, `static/`, or any `.env` file.
This evidence document is the only artifact created. Confirmed by `git status`: the
working tree already carried unrelated pre-existing modifications before this node
(`app/geo/validation.py`, `app/utils/validators.py`, several transport/auth files,
several templates) — none of them were touched by this node.

The live endpoint was reached from throwaway harnesses in `%TEMP%\opencode\`, outside the
repository, in two passes:

| Pass | Artifacts | Purpose |
|---|---|---|
| 1 | `node5_photon_proof.py`, `node5_photon_proof.json`, `node5_photon_proof.log`, plus three probe scripts | forward, reverse, round-trip, 9 failure modes, config/zero-I/O inspection |
| 2 | `node5_completion.py`, `node5_section_b.py`, `completion_run2.txt`, `section_b_run.txt`, `node5_section_b.json` | §14 default-timeout proof, §15 18-point reverse sweep + 4 forward queries, §16 4× repeat and cross-direction identity checks |

Both harnesses wrapped `requests.get` **in their own process only** to (a) record every
outbound call and (b) inject an identifying `User-Agent` for the success-path runs of §14.1 A2 / §15 / §16. No repository source was patched, no config file was written, no adapter behavior was monkeypatched, no adapter parameter was overridden. Pass 1's harness did override `timeout_s=25` for the success path; pass 2 removed that shortcut entirely and proved the shipped `10.0 s` default instead (§14.1).

One harness defect, recorded for honesty: `node5_completion.py` shadowed its logging
helper `h` with a loop variable named `h`, so its final artifact-write step raised a
`TypeError` **after** every probe had already completed and been printed. All pass-2
observations in §14-§16 come from the captured stdout (`completion_run2.txt`,
`section_b_run.txt`) and from `node5_section_b.json`, not from a partially written JSON
file. No repository file was affected.

---

## 12. VERIFICATION

| Command | Outcome |
|---|---|
| `pytest tests/test_geo_geocoding.py -q` (pass 1) | **20 passed**, 4 warnings (pre-existing deprecations), 24.70 s |
| `pytest tests/test_geo_geocoding.py -q` (pass 2, rerun, tests unaltered) | **20 passed**, 4 warnings (pre-existing deprecations), 32.88 s |
| `pytest tests/test_geo_integration.py -q` | **25 passed, 3 failed** — pre-existing and **unrelated to Photon**: all three assert GEO module-toggle state (`ModuleToggleService.is_enabled('geo')` returned `True` where the test expects `False`). No geocoding assertion involved. Recorded, not touched (out of scope, confirmed still outside this node in pass 2). |
| Live harness run, pass 1 (9 phases, 22 recorded outbound requests) | all assertions as reported in §4-§8 |
| Timeout sweep (`0.05 / 0.5 / 1.0 / 2.0 / 2.5 / 3.0`) | `ConnectTimeout` → `ReadTimeout` → success, both directions |
| Live harness run, pass 2 (Sections A/B/C: default-timeout proof, 18-point reverse sweep, 4 forward queries, 4× repeat, 2 cross-direction identity checks) | all assertions as reported in §14 |

Adapter source untouched, so the passing contract suite is a regression baseline, not a
new claim. Nothing in this node may be cited as evidence that the suite was extended.

---

## 13. Panel decisions requested

Three decisions were returned by the panel on 2026-10-05 and are recorded here as fact.
The rest remain open.

1. **D1 (missing `User-Agent`) — DEFERRED, RECORDED ONLY.** Panel decision: accept the
   defect as recorded and leave it unfixed. **Consequence accepted explicitly: live
   geocoding remains non-functional against every reachable Photon endpoint until a
   future node addresses it.** The adapter is not to be wired into any application
   surface, and no environment is to be configured, on the assumption that D1 is
   transient or minor. It is the reason the adapter cannot resolve anything (§14.1 A1).
   Revisit when a provider-hardening node is authorized; the change remains a one-line
   static header plus a config key, and it was deliberately not made in this
   proof-only lane.
2. **D5 / D6 / P4 — RECORDED NOW, DECISION DEFERRED.** Panel decision: keep all three
   recorded in this document and let Node 1 decide, when it defines the canonical
   location contract, whether richer identity (E2 typed `area`, E3 richer reverse
   `display_name`) is needed before any adapter normalization work is designed. D5 is
   the only defect that reaches the product layer (Node 1 §6 human identity). **No
   adapter-side fix is authorized by this decision, and none was made.**
3. **`place_ref` durability — DISPLAY / AUDIT ONLY.** Panel decision: record `place_ref`
   as a human-readable audit and display field, **explicitly never a primary key, never
   a cache key, and never a dedupe key**. Basis: OSM references were stable in every
   probe performed (§16.1-§16.4), but durability across a Photon data reimport, a
   redeploy, or the passage of days is unproven (§16.5 C5). Node 1 inherits this
   constraint and must carry it into the canonical location contract. Because it is not
   a cache key, the unproven reimport risk requires **no** revalidation policy — that
   cost was accepted in exchange for the guarantee that a stale reference can never
   silently merge two records.

Open, still requiring a decision:

4. **D2 / D3 / D4** — accept as recorded defects, or authorize a follow-up node?
5. **P1 (no production caller)** — is provider wiring part of Node 6/7, or its own node?
   Note: while D1 is deferred, wiring would be premature by decision 1.
6. **P2 (no authorized endpoint)** — self-host in an environment, or keep geocoding
   unconfigured and truthful? Confirm that the public instance stays verification-only
   and that no number in this document is treated as a target-environment number (P4).
7. **E1-E5** — which, if any, enter a future node as typed contract fields? Per the
   node's caveat, none were added here. E3 is strengthened by the §15 evidence. E1 is
   now bounded by decision 3 (`place_ref` is display/audit only, not a key).
8. **BACKLOG GEO-16** (`BACKLOG.md:2599-2609`) — this node produced the live evidence it
   asked for, but resolving it is the register/human step. `BACKLOG.md` was deliberately
   **not** edited by this node.
9. **Node 1 §10.3 (`area` shape)** — the live locality-hierarchy evidence in §9 and §15.6
   is now available; the decision remains open and is unowned by this node.

---

## 14. PASS 2 — DEFAULT-TIMEOUT PROOF

Requested because pass 1 used an explicit `timeout_s=25`, which is not the value an
operator actually gets. This section uses the **real default only**.

### 14.1 A0 — where the effective default comes from (source + live)

| Probe | Value |
|---|---|
| `PhotonConfig()` dataclass default (`photon.py:45`) | `10.0` |
| `load_geo_config().photon.timeout_s` (`config.py:73-76`) | `10.0` |
| Live `PhotonGeocoder(PhotonConfig(base_url=BASE, enabled=True)).config.timeout_s` | `10.0` |
| Value actually handed to `requests.get(timeout=...)` — recorded on the wire | `10.0` |

`app/geo/config.py:73-76` constructs `PhotonConfig(base_url=…, enabled=…)` and never
passes `timeout_s`, so 10.0 s is unavoidable through every configuration path. This is
defect **D3**, now confirmed against the running config loader, not just the dataclass.

### 14.1 A1 — PURE DEFAULT ADAPTER against the live endpoint (endpoint `https://photon.komoot.io`)

This is exactly what an operator would get today: default timeout, no header injection.

| | Forward | Reverse |
|---|---|---|
| Request | `GET https://photon.komoot.io/api` params `{'q': 'Nakasero Market, Kampala, Uganda', 'limit': 5}` | `GET https://photon.komoot.io/reverse` params `{'lat': 0.3476, 'lon': 32.5825}` |
| Timeout sent | `10.0` s | `10.0` s |
| Outcome | **HTTP 403 Forbidden** (adapter logged `Photon geocode request failed: 403 Client Error`) | **HTTP 403 Forbidden** (adapter logged `Photon reverse request failed: 403 Client Error`) |
| Latency | 1617.3 ms wire / 1619.8 ms adapter wall | 2231.6 ms wire / 2234.6 ms adapter wall |
| Resolution succeeded | **No** — `[]` | **No** — `resolved=False`, coords `None` |

**Stated explicitly, as required: the default path did not exercise successfully.** The
cause is **D1** (no `User-Agent`), not the timeout — the 403 arrived in 1.6-2.2 s, far
inside the 10.0 s budget. The failure was truthful: no exception escaped, no coordinate
was fabricated.

### 14.1 A2 — SAME ADAPTER, SAME `10.0 s` DEFAULT, header injected at the transport edge

Purpose: isolate the timeout variable from D1 without touching adapter source. 3
consecutive runs, forward and reverse each.

| Run | Direction | Request | HTTP | Wire latency | Adapter wall | Budget used | Resolution |
|---|---|---|---|---|---|---|---|
| 1 | forward | `/api?q=Nakasero Market, Kampala, Uganda&limit=5` | 200 | 4043.5 ms | 4046.6 ms | 40.4 % of 10.0 s | 5 hits, all `resolved=True` |
| 1 | reverse | `/reverse?lat=0.3476&lon=32.5825` | 200 | 3427.7 ms | 3430.6 ms | 34.3 % | `resolved=True`, `Cure Health Clinic, Kampala, Uganda` |
| 2 | forward | same | 200 | 3619.9 ms | 3621.2 ms | 36.2 % | 5 hits, all `resolved=True` |
| 2 | reverse | same | 200 | 3237.7 ms | 3240.4 ms | 32.4 % | `resolved=True`, same `display_name` |
| 3 | forward | same | 200 | 4092.6 ms | 4097.9 ms | 40.9 % | 5 hits, all `resolved=True` |
| 3 | reverse | same | 200 | 3376.5 ms | 3379.1 ms | 33.8 % | `resolved=True`, same `display_name` |

**Conclusion on the default timeout:** on this network path the default `10.0 s` was
sufficient on 6 of 6 requests, with ~2.4× headroom over the slowest observed forward
call. Adapter overhead over the wire call is 1.3-3.3 ms — negligible. The value is
nevertheless hard-pinned (**D3**) and must not be read as a validated choice: the
provider serving production would be a self-hosted Uganda extract (P4), whose latency is
unmeasured.

---

## 15. PASS 2 — DISPLAY-NAME DEGRADATION PROBES

No adapter modification. All results below come from the adapter's own
`display_name` on live responses.

Method: forward direction only indexes *named* OSM features, so the degradation cases
were driven by **reverse** — 18 real coordinates across Kampala, Nakasero, Kololo,
Entebbe, Jinja, Buikwe, Mityana, Masaka, Mbale, Gulu, Arua, and four rural points —
plus 4 forward queries chosen for street-level results.

### 15.1 Case: no `name`, but address fields present — CONFIRMED

Query point `(0.0514, 32.4675)` → HTTP 200, 1 feature, 2067.2 ms.

| | |
|---|---|
| Raw provider identity | `housenumber="1A"`, `street="Mugwanya Road"`, `district="Kakeeka"`, `city="Entebbe"`, `state="Central Region"`, `country="Uganda"`, `countrycode="UG"`, `type="house"`, `osm_key="place"`, `osm_value="house"`, `osm_type="N"`, `osm_id=3735926830` — **no `name`, no `locality`** |
| Adapter `display_name` | `'Entebbe, Uganda'` |
| Dropped | `name` (absent upstream), `housenumber` `1A`, `street` `Mugwanya Road`, `district` `Kakeeka`, `state`, `countrycode`, `osm_key`, `osm_value` |
| Coordinates | `(0.0514656, 32.4671593)` — snapped `+0.0000656 lat, -0.0003407 lon` from the query point |
| Usable? | **Coordinates: yes.** As a pickup identity: **no.** Two different addresses on Mugwanya Road would produce the identical label. This is the single most damaging case for Node 1 §6. |

### 15.2 Case: no `name` and no `city` — NOT OBSERVED

18 real reverse probes produced shapes: `name_and_city` ×10, `name_no_city` ×6,
`no_name_with_city` ×1, and 1 empty result. A `no_name` + `no_city` feature was **not**
observed, so the fully degenerate label was not demonstrated. Read from
`_display_name` source (`photon.py:49-53`), a feature lacking `name`, `city` *and*
`country` would yield `display_name = ""` — **plausible from source, not proven live.**
Recorded under §0 "Not proven"; not claimed as a finding.

### 15.3 Case: `name` present, `city` absent — CONFIRMED (6 live cases)

`_display_name` joins only what is truthy, so all six collapse to `'<name>, Uganda'`:

| Query point | Raw identity (abridged) | Adapter `display_name` | Dropped |
|---|---|---|---|
| Entebbe town centre `(0.0611715, 32.4698564)` | `name="Entebbe"`, `state="Central Region"`, `type="city"`, `R/14723820` | `'Entebbe, Uganda'` | `state`, `countrycode`, `osm_key`, `osm_value` |
| Buikwe `(0.0489, 33.0044)` | `name="Lukalu"`, `state="Buvuma"`, `type="city"`, `N/9394487663` | `'Lukalu, Uganda'` | same |
| Mityana `(0.1786, 32.0225)` | `name="Luwangal Jumbi"`, `state="Gomba"`, `N/9790517982` | `'Luwangal Jumbi, Uganda'` | same |
| rural Sironko `(1.2067001, 34.2040242)` | `name="Kampala"`, `county="Bugisa sub-region"`, `state="Sironko"`, `N/10202130958` | `'Kampala, Uganda'` | `county`, `state`, `countrycode`, `osm_key`, `osm_value` |
| rural Kamwenge `(0.3816006, 30.7795714)` | `name="Kampala"`, `state="Kamwenge"`, `N/11032086424` | `'Kampala, Uganda'` | `state`, … |
| Sud-Kivu DRC `(-2.6827567, 28.05007)` | `name="Kampala"`, `county="Shabunda"`, `state="Sud-Kivu"`, `country="RΘpublique dΘmocratique du Congo"`, `N/1160971626` | `'Kampala, RΘpublique dΘmocratique du Congo'` | `county`, `state`, `countrycode`, … |

**Concrete collision, three unrelated places:** the rows 4, 5 and 6 above are three
physically distinct villages all named `Kampala` — one near 1.21 °N, one near 30.78 °E,
one in the Democratic Republic of the Congo — and the adapter gives all three the label
`"Kampala, Uganda"`. Two of them differ only by the `state` field, which normalization
drops. This is defect **D5** and it is not hypothetical.

### 15.4 Case: address-like `name` — CONFIRMED

| Feature | Raw identity (abridged) | Adapter `display_name` |
|---|---|---|
| `W/1054062167` | `name="Kintu Road"`, `locality="Nakasero"`, `district="Central"`, `city="Kampala"`, `state`, `country`, `osm_key="highway"`, `osm_value="tertiary"` | `'Kintu Road, Kampala, Uganda'` |
| `W/43875006` | `name="Kintu Road"`, `locality="Simbwa (zone)"`, `district="Rubaga"`, `city="Kampala"`, `osm_value="residential"` | `'Kintu Road, Kampala, Uganda'` |
| `W/45425884` | `name="Sekabaka Kintu Road"`, `locality="Bulwa zone"`, `district="Rubaga"`, `city="Kampala"` | `'Sekabaka Kintu Road, Kampala, Uganda'` |
| `W/207715500` | `name="Sekabaka Kintu Road"`, `locality="Kitunzi"`, `district="Rubaga"`, `city="Kampala"` | `'Sekabaka Kintu Road, Kampala, Uganda'` |
| `N/4927141502` | `name="Boda stage - Sir Albert Cook Road / Sekabaka Kintu Road"`, `street="Sekabaka Kintu Road"`, `type="house"`, `osm_value="taxi"` | `'Boda stage - Sir Albert Cook Road / Sekabaka Kintu Road, Kampala, Uganda'` |
| `W/666656564` | `name="Nakasero Road"`, `locality="Nakasero"`, `district="Central"`, `city="Kampala"`, `osm_value="tertiary"` | `'Nakasero Road, Kampala, Uganda'` |
| `N/4123469779` | `name="NC Bank Nakasero Road Branch"`, `street="Nakasero Road Branch"`, `locality="Bat Valley"`, `type="house"`, `osm_value="bank"` | `'NC Bank Nakasero Road Branch, Kampala, Uganda'` |

Dropped from every row above: `locality`, `district`, `state`, `countrycode`
(and `county` where present).

Consequences: four physically distinct segments of `Kintu Road` share two distinct
labels, and `locality` — the one field that distinguishes them (`Nakasero`, `Simbwa
(zone)`, `Bulwa zone`, `Kitunzi`) — is dropped. A search UI cannot disambiguate these
candidates by label. Reverse at each of these exact coordinates returned the *same*
`osm_type`/`osm_id` with the *same* label, so the degradation is stable, not
run-dependent.

### 15.5 Case-insensitivity, observed live (defect D6)

One `Kololo Hill Drive, Kampala` query returned both `W/45343641` with
`name="Kololo Hill Drive"` and `N/8881587388` with `name="KOLOLO HILL DRIVE"`
(`osm_value="guidepost"`, `street="Kololo Hill Lane"`). Labels:
`'Kololo Hill Drive, Kampala, Uganda'` and `'KOLOLO HILL DRIVE, Kampala, Uganda'`. The
adapter applies no case folding, so label-based grouping or dedupe cannot rely on
`display_name`.

### 15.6 Baseline `name` + `city` — still lossy, recorded for contrast

| Query point | Raw identity (abridged) | Adapter `display_name` |
|---|---|---|
| Kampala city centre | `name="Kampala"`, `city="Kampala"`, `R/10546821` | `'Kampala, Kampala, Uganda'` — name repeated verbatim |
| Nakasero | `name="African Art Crafts Market"`, `street="Portal Avenue"`, `locality="Nakasero"`, `district="Central"`, `city="Kampala"`, `N/3942341740` | `'African Art Crafts Market, Kampala, Uganda'` |
| Jinja | `name="GADAFFI BARRACKS"`, `street="Kamuli Hill"`, `district="Special Area"`, `city="Jinja"`, `state="Eastern Region"`, `N/11056438784` | `'GADAFFI BARRACKS, Jinja, Uganda'` |
| Masaka probe `(0.3336, 33.7)` | `name="Nabyama Primary School"`, `city="Nabyama Central"`, `county="Bunya"`, `state="Bugiri"` | `'Nabyama Primary School, Nabyama Central, Uganda'` |
| Mbale probe `(1.0, 34.15)` | `name="Bukhumwa Primary School"`, `street="Butaleja Road"`, `city="Wabukhasa"`, `county="Bungokho"` | `'Bukhumwa Primary School, Wabukhasa, Uganda'` |
| Arua probe `(3.0, 30.9)` | `name="Giligili Bright Academy"`, `street="Opi lane"`, `locality="Yapi Sub urban village"`, `district="Pajulu"`, `city="Kasua"`, `county="Ayivu"` | `'Giligili Bright Academy, Kasua, Uganda'` — `city` is a sub-city, not Arua |
| rural Ssese `(0.05, 32.2)` | `name="Buvumbo Swamp"`, `city="Luubu"`, `state="Mpigi"`, `type="other"`, `R/12128253`, `osm_value="wetland"` | `'Buvumbo Swamp, Luubu, Uganda'` — a wetland, not a place a rider could be picked up |
| rural Karamoja `(2.0, 34.5)` | HTTP 200, `features: []` | `resolved=False` — truthful miss |

Note the Masaka/Mbale/Arua rows: the field named `city` in Photon properties is
sometimes a sub-city or parish, so treating it as Node 1 `area` without inspection would
be wrong. This is evidence for the §9 `area` open decision.

### 15.7 Reverse snap distance, measured live (new, relevant to Node 7)

| Query point | Returned coordinate | Offset |
|---|---|---|
| Kampala city centre | `(0.3177137, 32.5813539)` | `0.0000000, 0.0000000` (exact) |
| rural Sironko / Kamwenge / Sud-Kivu | feature centroid | `0.0000000, 0.0000000` (exact) |
| Kampala / Nakasero approx | `(0.3475086, 32.5822782)` | `-0.0000914 lat, -0.0002218 lon` (~29 m) |
| Entebbe town centre | exact | `0.0000000, 0.0000000` |
| Masaka probe | `(0.3343305, 33.6963117)` | `+0.0007305 lat, -0.0036883 lon` (~411 m) |
| Buikwe probe | `(0.0457222, 33.0076552)` | `-0.0031778 lat, +0.0032552 lon` (~457 m) |
| Jinja probe `(0.4478, 33.2025)` | `(0.449814, 33.2038062)` | `+0.0020140 lat, +0.0013062 lon` (~250 m) |

Reverse resolves to the **nearest indexed feature**, which can be hundreds of metres
away, and the feature may be a school, hospital, wetland or bank rather than the actual
drop-off point. This reinforces Node 1 §5: reverse geocoding may fill
`display_name`/`area`/`label_status` but must never replace coordinates. The adapter
itself never substitutes the returned coordinate for the caller's point — the caller
receives both and must keep its own.

---

## 16. PASS 2 — OSM REFERENCE STABILITY

### 16.1 C1 — same forward query repeated 4×

Query `geocode("Nakasero Market, Kampala, Uganda", limit=5)`. Runs 1-3 back to back,
run 4 ~60 s later in the session.

| Rank | Run 1 | Run 2 | Run 3 | Run 4 (later) | Stable |
|---|---|---|---|---|---|
| 0 | `N/9626381835` Nakasero Market | same | same | same | **yes** |
| 1 | `N/4116600468` ABC Capital Bank Nakasero Market | same | same | same | **yes** |
| 2 | `N/11400908835` Imprimerie Rosebury Lane, Nakasero Market | same | same | same | **yes** |
| 3 | `W/329420618` Nakasero Market Upper Section | same | same | same | **yes** |
| 4 | `N/14219273945` African Art Crafts Market | same | same | same | **yes** |

HTTP 200 on all four (3237.2 / 2640.7 / 2718.7 / ~3400 ms). Result: the **entire ordered
result list, including every `osm_type`/`osm_id` pair and the top-hit selection, was
byte-identical across all four runs**. The selected feature did not change.

### 16.2 C2 — forward feature vs reverse at that same coordinate

```
forward top feature  : osm=N/9626381835  name='Nakasero Market'  coord=(0.3117701, 32.580514)
reverse at that coord: osm=N/9626381835  name='Nakasero Market'  coord=(0.3117701, 32.580514)
same osm reference: True    same osm_id: True    same coordinate: True
```

Forward and reverse agree on the same physical feature, including its `osm_type`.

### 16.3 C3 — reverse-derived feature, then forward search by its name

```
reverse(0.3476, 32.5825) -> osm=N/8963738622  name='Cure Health Clinic'
                             street='Northern Bypass'  coord=(0.3475086, 32.5822782)
forward("Cure Health Clinic, Kampala, Uganda", limit=8) -> 1 hit
    osm=N/8963738622  name='Cure Health Clinic'  coord=(0.3475086, 32.5822782)
reappears in its own forward search: True, at rank 1 of 1
```

The reverse-derived reference is recoverable by forward search, at rank 1, with an
identical coordinate.

### 16.4 C4 — OSM reference keys observed across all live traffic

| `osm_type` | Meaning | Observed |
|---|---|---|
| `N` | node | majority — POIs, shops, clinics, schools, villages, streets-as-nodes |
| `W` | way | street segments (`W/1054062167`, `W/43875006`, `W/45425884`, `W/207715500`, `W/666656564`, `W/45343641`, `W/26801721`, `W/498307300`, `W/704996729`), marketplace polygon |
| `R` | relation | cities/places (`R/10546821`, `R/5457274`, `R/14723820`), wetland (`R/12128253`) |

**The pair is required.** `osm_id` alone is ambiguous across types. Two distinct Kampala
relations (`R/10546821`, `R/5457274`) share the name `Kampala` and even identical
coordinates but have different `osm_id`s — so a consumer must key on `osm_type` +
`osm_id`, never on `osm_id` alone.

### 16.5 C5 — what was NOT proven about stability

Recorded explicitly, per instruction not to assume persistence:

- Stability across a **Photon data reimport** — not tested. `/status` reports
  `import_date 2026-09-26`; the next reimport can change ranking, and OSM edits can
  change or delete ids.
- Stability across **days or weeks**, across **Photon version upgrades**, or across a
  **different deployment** (self-hosted extract, P4).
- Stability of `osm_id` for features that are **deleted or split** upstream.
- All stability evidence here is from a ~4-minute window on one network path with a
  single global-planet index. It is evidence of *determinism within a session*, not of
  *durability over time*.

Practical consequence for Node 1 — **decided (see §13, decision 3): `place_ref` is a
display and audit field only.** It is explicitly not a primary key, not a cache key, and
not a dedupe key, so the unproven reimport risk requires no revalidation policy, and a
reference that goes stale after a reimport can never silently merge two records.

---

## 17. FINAL STATUS

Nothing in this node authorizes production use of the adapter.

### 17.1 Three-state record: proposal, ratification, ratified state

This node distinguishes three separate facts. They are not interchangeable.

| State | What it means | Who established it |
|---|---|---|
| **1. Agent proposal** | The agent completed both proof passes, recorded all evidence, and proposed `STATUS: PASS` with `GATE: BLOCKED`. | Agent, 2026-10-05 |
| **2. Panel ratification** | The panel reviewed the proposal and supplied the missing ratification. An earlier agent edit that wrote a bare `GATE: PASS` was **procedurally premature** — it asserted the gate outcome before any panel member had ratified. That wording has been corrected here; the evidence it was attached to was not wrong, only unauthorized at the time. | Panel, 2026-10-05 |
| **3. Final ratified state** | `STATUS: PASS`, `GATE: PASS — PANEL RATIFIED`. Ratification covers the **proof**, not production use. | Panel, 2026-10-05 |

**Scope of what was ratified.** The panel ratified the *completeness and accuracy of the
proof record* — that the claims in §4-§16 are supported by the evidence cited, that the
gaps are honestly registered, and that nothing was overstated. Ratification does **not**
authorize production deployment of the adapter, does not authorize any provider
hardening, and does not clear D1. The adapter is still known-non-functional against the
only reachable endpoint. A PASS gate on a proof node means *the proof is complete and
truthful*, not *the software is fit to ship*.

### 17.2 Proof summary

- Forward and reverse geocoding, coordinate order, round-trip, normalization,
  validation, truthful failure on 9 live failure modes, no-retry behavior, zero startup
  I/O, and the unconfigured state are **proven** against a real Photon 1.3.0 instance.
- The **default path as written does not resolve** (HTTP 403, D1). The `10.0 s` default
  timeout itself was exercised and is sufficient on this network path.
- **Two new defects (D5, D6)** and **one new dependency (P4)** were discovered in pass 2
  and are recorded without fixes.
- Six defects (D1-D6), four dependencies (P1-P4) and five extension candidates (E1-E5)
  are recorded and unowned by implementation.
- **Panel decisions recorded 2026-10-05** (§13):
  - **D1 deferred, recorded only.** Accepted consequence: live geocoding stays
    non-functional until a future node fixes the missing `User-Agent`, and no application
    surface may be wired to this provider in the meantime.
  - **D5 / D6 / P4 recorded now, decision deferred to Node 1.** No adapter-side fix is
    authorized.
  - **`place_ref` is display/audit only** — never a primary key, cache key, or dedupe key.

---

## RATIFICATION RECORD

```text
AGENT PROPOSAL: 2026-10-05

PANEL RATIFICATION:
- DeepSeek: PASS — 2026-10-05
- ChatGPT: PASS — 2026-10-05
```

No times are recorded: none were supplied, and none are invented here. Dates only.

Note on attribution: the panel member is recorded as `ChatGPT` per the ratification
input. No panel member may self-modify an owner, impersonate, or amend another member's
vote; these two entries are taken as supplied by the panel and are not re-derived by the
agent.

---

STATUS: PASS
NODE: NODE-5-PHOTON-PROOF
SCOPE: Photon provider proof only — adapter source verification, live forward and
reverse proof, normalization proof, failure proof, configuration state, default-timeout
proof, display-name degradation probes, OSM reference stability, Node 1 field
availability, gap registration
PHASE: PROOF
COMMIT: none (no source change to commit)
REGISTER: unchanged — `BACKLOG.md` GEO-16 deliberately not edited; register update is
the human's step
FILES CHANGED:
  - docs/transport/nodes/NODE-5-PHOTON-PROOF-evidence.md  (+new, pass 1 + pass 2)
BEHAVIOR: none — the Photon adapter was proven against the live Photon 1.3.0 endpoint in
two passes and was not modified in either.
VERIFICATION (pass 1): live forward (3 queries / 15 hits, HTTP 200) and live reverse
(5 points + round-trip) through unmodified adapter code; 9 live failure probes
(ConnectTimeout, ReadTimeout, 404, 400 non-GeoJSON, DNS failure, empty collection,
unavailable provider, pre-I/O validation); 22 recorded outbound requests, per-call counts
all exactly 1. (pass 2): default `timeout_s=10.0` proven sufficient on 6/6 requests
(32-41 % of budget) and proven insufficient to resolve as written (403, D1); 18-point
reverse sweep + 4 forward queries classified into `name_and_city` ×10, `name_no_city` ×6,
`no_name_with_city` ×1; 4× repeat of one forward query with byte-identical ordered
results; forward↔reverse OSM identity agreement proven in both directions;
`pytest tests/test_geo_geocoding.py -q` → 20 passed (24.70 s pass 1, 32.88 s pass 2,
tests unaltered);
`pytest tests/test_geo_integration.py -q` → 25 passed / 3 pre-existing module-toggle
failures unrelated to geocoding, outside this node;
`git diff --stat` on `app/geo/providers/photon.py`, `tests/test_geo_geocoding.py`, all
`.env*` files and `migrations/` → empty.
RESIDUAL RISK: The success path was only ever exercised with a User-Agent injected at the
transport edge of the harness; the adapter as written cannot pass it against the only
reachable real Photon endpoint (D1), which the panel has deferred. Live geocoding is
therefore known-non-functional and must not be treated as available. No authorized
production Photon endpoint exists, so no live behavior in any AFCON360 environment is
proven and no number here is a target-environment number (P4). The `10.0 s` default was
sufficient against a public global instance at 1.4-4.4 s latency but is not
operator-tunable (D3) and is unvalidated against a self-hosted Uganda extract.
`display_name` is demonstrably ambiguous — three unrelated villages named `Kampala` share
one label, and an unnamed house collapses to `"Entebbe, Uganda"` (D5) — which directly
affects Node 1 §6 human identity; Node 1 owns whether E2/E3 resolve it. OSM references
were stable only within a ~4-minute session; durability across a reimport or deployment
change is unproven, which is why the panel bound `place_ref` to display/audit use only.
Three pre-existing GEO module-toggle test failures remain open and are outside this node.
FOLLOW-UPS (none started, none authorized): D1 User-Agent [DEFERRED BY PANEL]; D2 `limit`
validation; D3 configurable `timeout_s`; D4 client-side hit clamp; D5 non-unique
display_name [RECORDED, Node 1 decides]; D6 no case normalization [RECORDED, Node 1
decides]; E1 typed `place_ref` [bounded by the display/audit-only decision]; E2 typed
`area`; E3 richer reverse `display_name`; E4 `extent` ordering; E5 encoding normalization;
P1 no production caller; P2 no authorized endpoint; P3 static provider health; P4 no
Uganda-extract evidence [RECORDED].
GATE: PASS — PANEL RATIFIED
