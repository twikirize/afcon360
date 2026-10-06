# NODE 1 — Canonical Resolved-Location Contract (design, no implementation)

**Status:** PASS — no production code, migration, provider, UI, or search changed. `app/geo/interfaces.py` is frozen for this node. `ResolvedLocation` is a proposed, additive product-layer value object; it does not exist in code yet.

**Gate:** PASS — PANEL RATIFIED

## Ratification record — 2026-10-06

**Agent proposal:** PASS — 2026-10-06

**Panel ratification:**

* DeepSeek: PASS — 2026-10-06
* ChatGPT: PASS — 2026-10-06

No times are recorded because none were supplied.

This ratification closes the **Node 1 contract/design gate only**. It does not authorize implementation of `ResolvedLocation`, modification of `app/geo/interfaces.py`, database persistence, migrations, Photon hardening, production provider wiring, or automatic advancement of downstream nodes.

---

## Correction history — 2026-10-06

Following adversarial panel review and re-review:

* `identity_status` vocabulary is `none | unverified | enriched | verified`.
* The earlier orphaned `synthetic` state was removed.
* The earlier top-level `place_ref` concept was folded into `provenance.reference`, leaving one field for the provider/registry reference datum.
* `provenance.reference` remains display/audit information only and is never a primary key, cache key, or dedupe key.
* `display_name` is `Optional[str]`.
* Empty-string `display_name` is normalized to `None` before construction.
* `format_endpoint_display()` is non-normative Transport implementation evidence only; it is not canonical GEO authority.
* `app/geo/interfaces.py` remains unchanged.

---

## 1. Canonical contract

```python
@dataclass(frozen=True)
class ResolvedLocation:
    # --- geographic truth ---
    latitude: float
    longitude: float

    # --- originating input path ---
    source: str                # gps | map | search | curated
    resolution_method: str     # browser_geolocation | map_pin |
                               # forward_geocode | registry_lookup

    # --- provenance ---
    provenance: Optional[ProvenanceRecord]

    # --- human identity ---
    label: str
    display_name: Optional[str]
    identity_status: str       # none | unverified | enriched | verified
    area: Optional[str]

    # --- quality ---
    accuracy_m: Optional[float]
    confidence: Optional[float]

    # --- time ---
    observed_at: Optional[datetime]
    resolved_at: datetime
```

Coordinate resolution requires no separate field.

The existence of a valid `ResolvedLocation` instance is the coordinate-resolution invariant. Construction is valid only when latitude and longitude satisfy the existing coordinate validation rules.

There is no:

```text
coordinates_resolved
identity_resolved
```

boolean.

Identity quality is represented only by `identity_status`.

---

## 2. ProvenanceRecord

`ProvenanceRecord` is a **contract-level semantic definition**, not a Python implementation added by this node.

```text
ProvenanceRecord
    authority: str
    reference: Optional[str]
```

### Semantics

`authority` identifies the information authority that supplied the resolved identity or provenance.

Examples:

```text
photon
curated-registry
```

`reference` carries the reference actually observed from that authority when one exists.

Examples:

```text
N/9626381835
W/45343641
registry-place-123
```

The reference is provenance/audit data only.

Neither `authority` nor `reference` is business identity.

Provider-specific payloads remain in `GeocodeResult.raw` and are not copied wholesale into `ResolvedLocation`.

---

## 3. Types and nullability

All coordinate and quality numeric values are Python `float`.

The fields are:

```text
latitude               float
longitude              float

source                 str
resolution_method      str

provenance             Optional[ProvenanceRecord]

label                  str
display_name           Optional[str]
identity_status        str
area                   Optional[str]

accuracy_m             Optional[float]
confidence             Optional[float]

observed_at            Optional[datetime]
resolved_at            datetime
```

All timestamps are timezone-aware `datetime`.

### Required and non-null

```text
latitude
longitude
source
resolution_method
label
identity_status
resolved_at
```

### Required but nullable

```text
display_name
provenance
```

The fields exist in the record, but their values may be `None`.

### Optional and nullable

```text
area
accuracy_m
confidence
observed_at
```

An empty-string `display_name` is not a valid canonical value. It is normalized to `None` before construction.

---

## 4. Authoritative, advisory, and quality semantics

### Authoritative

The following are authoritative contract facts:

```text
latitude
longitude
source
resolution_method
resolved_at
```

`provenance`, when present, is authoritative as an audit record of where the information came from.

### Advisory

The following are human identity/presentation information:

```text
label
display_name
identity_status
area
```

They must never be treated as authoritative geographic position, pricing input, matching input, or database identity.

### Quality

The following are nullable factual metadata:

```text
accuracy_m
confidence
observed_at
```

Missing values mean unknown.

Unknown must never be represented by fabricated zero values.

---

## 5. Source model

`source` answers:

> How did this location enter AFCON360?

The closed set is:

```text
gps
map
search
curated
```

### `gps`

The rider's device supplied a browser geolocation position.

### `map`

The rider placed or dragged a pin on the map.

A tap and a drag are the same canonical source class.

### `search`

The rider typed a query and explicitly selected a forward-geocoded candidate.

A typed query that has not been explicitly selected is not a resolved location.

### `curated`

The location came from an authoritative curated registry entry.

A client may select a curated identifier, but must not supply arbitrary coordinates while claiming that they represent the curated entry.

### No `manual` source

Typed text that never resolves is not a `ResolvedLocation`.

Therefore the contract does not introduce a separate `manual` source.

---

## 6. Resolution-method model

`resolution_method` answers:

> How did AFCON360 resolve or establish this location?

The closed set is:

```text
browser_geolocation
map_pin
forward_geocode
registry_lookup
```

Required source/method relationships are:

```text
gps      → browser_geolocation
map      → map_pin
search   → forward_geocode
curated  → registry_lookup
```

### Reverse geocoding

Reverse geocoding is **enrichment**, not coordinate resolution.

It may:

* add `display_name`;
* add `area`;
* improve `identity_status` to `enriched`.

It must never:

* replace latitude/longitude;
* become a separate `resolution_method`;
* convert a nearby indexed feature centroid into the user's actual position.

---

## 7. Provenance model

`provenance` answers:

> Where did the resolved identity information come from?

### GPS / map

Normally:

```text
provenance = None
```

when there is no external provider or registry identity.

### Search

When provider identity is actually observed:

```text
authority = "photon"
reference = observed provider reference or None
```

### Curated

When a registry identity is actually observed:

```text
authority = "curated-registry"
reference = observed registry reference or None
```

No provenance may be fabricated.

Provenance is distinct from:

* `source` — originating input path;
* `resolution_method` — resolving mechanism;
* `label` — user/system-facing label;
* `display_name` — advisory human identity.

---

## 8. `provenance.reference` — display/audit only

The earlier top-level `place_ref` concept has been folded into:

```text
provenance.reference
```

This is a deliberate one-field-per-datum rule.

The Node 5 panel decision remains binding:

`provenance.reference` is **DISPLAY/AUDIT ONLY**.

It is:

* never a primary key;
* never a cache key;
* never a dedupe key;
* never assumed durable across provider reimport;
* never assumed durable across redeploy;
* never assumed durable across upstream edit, deletion, or split.

Node 5 showed same-session OSM reference stability, but not long-term durability.

No revalidation mechanism is created by Node 1.

When the authority supplies no reference:

```text
reference = None
```

When the entire provenance is unknown:

```text
provenance = None
```

---

## 9. Human identity and D5/D6

Node 5 evidence establishes that provider-generated `display_name` is not guaranteed to uniquely identify a physical location.

Observed examples include:

* unrelated places named `Kampala` producing the same `Kampala, Uganda`;
* distinct Kintu Road segments losing locality information;
* an unnamed Entebbe house with street/housenumber information collapsing to `Entebbe, Uganda`;
* case variants passing through differently;
* Photon `city` sometimes representing a sub-city/parish rather than the expected city.

Therefore:

`display_name` is **not unique identity**.

It does not guarantee:

* uniqueness;
* address adequacy;
* casing normalization;
* locality preservation.

The canonical object provides:

```text
display_name
identity_status
optional area
```

as the best identity information available at that point in processing.

These remain advisory.

### Identity status vocabulary

```text
none
unverified
enriched
verified
```

#### `none`

No human identity is available.

Normally:

```text
display_name = None
```

Typical for GPS/map points without an attached identity.

#### `unverified`

A human identity exists but has not been curated or independently verified.

Examples include provider/search-derived identity.

#### `enriched`

Identity was added through reverse geocoding or equivalent enrichment to an already-resolved point.

Coordinates remain unchanged.

#### `verified`

Identity originated from the authoritative verified curated registry.

The model does not claim that a provider name is correct merely because a provider returned it.

---

## 10. Area semantics

Node 5 established that provider fields such as:

```text
city
locality
district
county
state
```

do not map cleanly to one universal AFCON360 geographic hierarchy.

For example, a provider `city` value can represent something closer to a sub-city, parish, or locality.

Therefore:

```text
area: Optional[str]
```

means:

> the best available sub-national locality label supplied by the source, with no hierarchy guaranteed.

### Rules

The value is retained as source-supplied text.

There is no required:

* parsing;
* ordering;
* normalization;
* synthetic hierarchy construction.

When provider geography is absent or semantically unclear:

```text
area = None
```

The system must not synthesize a geographic hierarchy merely to populate this field.

A future structured locality hierarchy is explicitly outside this contract.

---

## 11. Accuracy and confidence

### `accuracy_m`

```text
Optional[float]
```

`None` means unknown.

Normally:

* GPS may supply accuracy;
* map may not;
* search may not;
* curated may not.

Do not write:

```text
0.0
```

to mean unknown.

### Legacy GeoPoint limitation

The existing:

```text
GeoPoint.accuracy = 0.0
```

cannot distinguish:

```text
unknown
```

from:

```text
known zero-metre accuracy
```

Therefore `ResolvedLocation.accuracy_m` deliberately has independent nullable semantics.

Any conversion into `GeoPoint` must preserve the call-site's explicit convention and must not silently manufacture factual accuracy.

### `confidence`

```text
Optional[float]
```

with range:

```text
0..1
```

Only populate it when a genuine resolver/provider supplies a confidence or relevance value.

Photon currently supplies no such confidence for this contract.

Therefore `None` is correct.

---

## 12. Time semantics

### `observed_at`

Represents when the underlying observation occurred.

Examples:

* GPS fix time;
* pin event time;
* other genuine source observation time.

If the source does not provide a trustworthy observation time:

```text
observed_at = None
```

It must never be backfilled from `resolved_at`.

### `resolved_at`

Represents:

> when AFCON360 accepted the location into the canonical resolved-location contract.

It is required and timezone-aware.

### Freshness

There is no freshness field in `ResolvedLocation`.

Freshness remains a derived/domain concern.

For example, driver location freshness may continue to compare `location_updated_at` to an established TTL.

Trusted device timestamp policy remains an operational decision.

The existing tracking convention remains relevant: server receive time is authoritative, while client timestamps may be observability information.

---

## 13. Label vs display_name

### `label`

`label` is the rider-facing/input-associated label.

Examples:

```text
Current location
Pinned · …
chip text
selected search text
```

It is required but advisory.

### `display_name`

`display_name` is the best human-readable identity currently associated with the resolved location.

It is:

```text
Optional[str]
```

It is:

* advisory;
* non-unique;
* non-authoritative.

When available, it may come from the best currently available identity source, such as explicit address information, provider/search identity, or curated identity.

When unavailable:

```text
display_name = None
```

An empty string is normalized to `None`.

### Transport presentation

`app/transport/services/offer_service.py::format_endpoint_display()` may be cited as evidence of how the current Transport implementation formats endpoint identity.

It is **not** the canonical semantic authority.

Presentation-specific fallback strings such as:

```text
to be confirmed
Pinned · …
coordinate-derived text
```

belong to the downstream presentation layer and are not mandated by this GEO contract.

Neither `label` nor `display_name` is:

* a primary key;
* a uniqueness guarantee;
* a cache key;
* a dedupe key.

---

## 14. Compatibility with existing GEO interfaces

### `GeoPoint`

The coordinate mapping is:

```text
GeoPoint.latitude  ↔ ResolvedLocation.latitude
GeoPoint.longitude ↔ ResolvedLocation.longitude
```

Latitude/longitude values map directly and losslessly.

Accuracy metadata is **not** fully lossless because the current `GeoPoint.accuracy=0.0` representation is ambiguous.

`GeoPoint.timestamp` may represent `observed_at` when the call site is specifically representing an observation event.

It must not be assumed that `resolved_at` and `observed_at` mean the same thing.

Any call-site mapping must preserve the intended semantics explicitly.

### `GeocodeResult`

Only:

```text
resolved=True
```

results may feed a `ResolvedLocation`.

Coordinates map directly.

`provider` and selected values from `raw` can supply provenance candidates.

`display_name` can seed human identity.

Provider-specific OSM metadata remains provider-specific information.

The canonical contract does not promote provider-specific raw structures into the existing GEO interfaces.

The mapping as a whole is **not lossless**.

### `RouteResult`

Unaffected.

### `NearbyItem`

Unaffected.

### Provider ABCs

Unaffected.

---

## 15. Explicit invariants

The following are contract invariants.

1. A `ResolvedLocation` always contains valid latitude/longitude values according to the existing coordinate validation rules.

2. The existence of `ResolvedLocation` is sufficient to establish coordinate resolution; no `coordinates_resolved` field exists.

3. Coordinates remain authoritative. A human label can never become geographic position.

4. A `GeocodeResult` with `resolved=False` cannot become a canonical `ResolvedLocation`.

5. Human labels are not unique identifiers.

6. `provenance.reference` is not business identity and may not be used as a PK, cache key, or dedupe key.

7. Reverse enrichment cannot overwrite source coordinates.

8. A reverse-geocoder feature coordinate can differ substantially from the requested point; Node 5 observed offsets up to approximately 457 m.

9. Unknown accuracy/confidence remain `None`, never fabricated zero values.

10. `source` and `resolution_method` must form one of the explicitly permitted semantic pairs.

11. `identity_status` may not claim evidence stronger than its source:

    * `none` when identity is absent;
    * `unverified` for unverified provider/search identity;
    * `enriched` when identity was added by reverse enrichment;
    * `verified` only for verified curated identity.

12. An empty-string `display_name` must normalize to `None` before construction.

13. `observed_at` and `resolved_at` retain distinct meanings.

14. The contract must never fabricate:

    * coordinates;
    * labels;
    * references;
    * area;
    * accuracy;
    * confidence;
    * timestamps.

---

## 16. Future extensions — not part of this contract

The following remain explicit extension candidates.

### Typed provenance reference

A future consumer may want a structured accessor for an OSM reference such as:

```text
osm_type + osm_id
```

without changing the semantic rule that the reference is audit/display only.

### Structured area

A future typed locality hierarchy may be introduced only when a real consumer proves the need and appropriate data evidence exists.

### Richer provider-derived identity

Node 5 E3 remains available for a future richer identity composition using information such as:

```text
street
housenumber
district
locality
```

### Extent semantics

Provider extent data can be typed/documented later, including explicit coordinate ordering.

### Encoding/normalization policy

Provider text normalization can be addressed later when a real consumer requires it.

None of these extension candidates authorize modifying `app/geo/interfaces.py` in this node.

---

## 17. Node 4 / Node 5 implications

### Node 4

The place-registry reconnaissance established that verified, public, published properties with valid coordinates are currently the strongest existing curated-place candidates.

Airport, stadium, and venue information is not currently an equivalent authoritative registry.

Event/route JSONB and booking contextual location data are contextual records, not canonical registry sources.

These findings do not authorize changes to Node 4 in this node.

### Node 5

Node 5 is panel-ratified PASS.

Its recorded implications are:

* forward and reverse provider behavior was proven against a real Photon instance;
* GeoJSON coordinate order was verified;
* truthful failures were verified;
* default timeout behavior was exercised;
* display-name degradation was demonstrated;
* same-session OSM reference stability was demonstrated;
* D1 remains explicitly deferred;
* D5/D6/P4 remain recorded;
* the provider/registry reference is display/audit only;
* the public Photon instance remains verification-only;
* no production endpoint is authorized.

Node 5 is not reopened.

---

## 18. Migration and storage boundary

This node authorizes:

* no schema changes;
* no migrations;
* no persistence implementation.

A future persistence design must preserve the semantics of the entire canonical object.

Future storage must be able to represent:

* nullable provenance;
* nullable provenance reference;
* nullable area;
* nullable accuracy;
* nullable confidence;
* nullable observed timestamp;
* timezone-aware resolved timestamp;
* `display_name=None`;
* legacy string-only location records that have not yet been resolved.

Existing stored location records must not be reinterpreted merely because this contract exists.

---

## 19. Downstream mapping

### Node 2 — snapshot/presentation

Later Node 2 may consume the complete canonical object.

Presentation should:

* show `display_name` when available;
* otherwise let the presentation layer render a truthful fallback based on `identity_status`;
* expose coordinates/quality only where appropriate.

The canonical contract does not prescribe UI copy.

### Node 3 — rider endpoint state

Later Node 3 may expose:

```text
ResolvedLocation | None
```

for each endpoint.

`None` means no canonical resolved location currently exists.

### Node 6 — typed search

Later Node 6 may:

* accept typed rider input;
* return normalized candidates;
* require explicit rider selection;
* construct `source=search`;
* use `resolution_method=forward_geocode`.

No search candidate may be auto-selected merely because it is ranked first.

### Node 7 — human identity / reverse enrichment

Later Node 7 may enrich a resolved point with:

* `display_name`;
* `area`;
* `identity_status=enriched`.

Coordinates remain immutable.

Nodes 4 and 5 are evidence inputs and do not require modification here.

---

## 20. Open decisions

The following remain genuinely open:

1. Trusted device/source timestamps for `observed_at`.

2. Whether and when to introduce a structured locality hierarchy for `area`.

3. Retention/privacy boundaries for provenance references and provider raw metadata.

4. Localization of display-name presentation.

5. Whether an actual downstream consumer eventually proves a need for typed access to `provenance.reference`.

These open decisions do not invalidate the current core contract.

---

## Sources inspected

The contract was checked against:

* `app/geo/interfaces.py`

  * `GeoPoint`
  * `GeocodeResult`
  * `RouteResult`
  * `NearbyItem`
  * provider interfaces

* `app/geo/providers/photon.py`

  * configuration;
  * forward/reverse request shapes;
  * feature conversion;
  * display-name behavior

* `app/geo/config.py`

  * Photon configuration surface;
  * timeout default behavior

* `app/geo/services.py`

  * provider facades;
  * geocoding service construction;
  * truthful-miss behavior

* `app/transport/services/booking_service.py`

  * canonical location validation/resolution behavior

* `app/transport/models.py`

  * existing contextual pickup/dropoff storage

* `app/transport/services/offer_service.py`

  * current endpoint-display implementation, treated as non-normative evidence only

* `app/transport/services/tracking_service.py`

  * timestamp authority conventions

* `docs/transport/nodes/NODE-5-PHOTON-PROOF-evidence.md`

  * ratified Photon findings, D1/D5/D6/P4, identity degradation, OSM-reference evidence

* Node 4 place-registry reconnaissance

  * curated-place source evidence

---

## Verification — Node 1

Confirmed for this documentation node:

* `app/geo/interfaces.py` remains unchanged.
* No production source was modified.
* No tests were modified.
* No configuration was modified.
* No migration was created or modified.
* No UI/search implementation was created.
* `coordinates_resolved` does not exist in the contract.
* `identity_resolved` does not exist in the contract.
* `identity_status` is exactly:

```text
none | unverified | enriched | verified
```

* `display_name` is `Optional[str]`.
* Empty-string `display_name` normalizes to `None`.
* `format_endpoint_display()` is non-normative evidence only.
* `provenance.reference` is the single reference location.
* `provenance.reference` is never PK/cache/dedupe/durable identity.
* D5/D6/P4 are incorporated as contract constraints rather than converted into adapter work.
* Existing GEO interfaces remain frozen.

---

## Final gate

This contract is panel-ratified PASS.

```text
STATUS: PASS
GATE: PASS — PANEL RATIFIED
```

The ratification closes the Node 1 **contract/design** gate only.

It does not by itself authorize:

* implementation of `ResolvedLocation`;
* modification of `app/geo/interfaces.py`;
* database persistence;
* migrations;
* Photon hardening;
* production provider wiring;
* Node 2;
* Node 3;
* Node 6;
* Node 7.

Those remain separately authorized work.
