# Supply Eligibility Contract v1

**Node:** SUPPLY-ELIGIBILITY-V1
**Status:** DRAFT — awaiting human review. Policy sections (§8) are open.
**Scope of this file:** specification only. No code was changed to produce it.
**Evidence basis:** repository source at commit-time of writing. Every claim in §1–§7, §9–§12 carries a `file:line` citation in §12.

---

## 0. Purpose and scope

### 0.1 Purpose

This contract defines **who can be ONLINE** and **who can be MATCHABLE**, uniformly, across the three vehicle-sourcing paths of AFCON360 Transport:

1. **Driver-owned** — vehicle registered with `owner_type='driver'` (`app/transport/models.py:667`, `:755-761`)
2. **Fleet / organisation** — vehicle registered with `owner_type='organisation'` (`app/transport/models.py:667`, `:762-770`)
3. **Marketplace** — vehicle listed on `VehicleMarketplaceListing` and driven under a `VehicleContract` (`app/transport/models.py:2956`, `:3100`)

It exists because those three paths were built independently and today reach supply eligibility by **different predicates**. This contract states the single canonical predicate, separates what is **already true in code** from what is **not yet implemented**, and names the decisions only the control session can make.

### 0.2 In scope

- Driver online/available/qualification state and its writers
- The dispatch supply pool predicate (rider-facing)
- The marketplace supply pool predicate (owner-facing) — design only
- Vehicle-sourcing convergence onto `DriverVehicleHistory`
- The admin online override capability contract
- The test contract protecting these invariants

### 0.3 Out of scope (non-goals — see §11)

Trip status machine, fare, wallet, payment, notifications, rider UI copy, admin UI styling, and every unrelated register item.

### 0.4 Vocabulary — the two flags that were historically inverted

The single most important fact in this contract:

| Flag | Type | Meaning under this contract | Column |
|------|------|----------------------------|--------|
| `DriverProfile.is_online` | driver state | **Intent**: the driver has switched themselves to working. | `app/transport/models.py:333` |
| `DriverProfile.is_available` | driver state | **Qualification**: the driver currently satisfies the requirements to take a trip. | `app/transport/models.py:334` |
| `Vehicle.is_available` | vehicle state | **Busy flag**: `False` while assigned to an active booking. Not a qualification. | `app/transport/models.py:739` |

Before SUPPLY-00 these were conflated: `is_available` was used as a busy flag, which made "online but not available" reachable and made trip lifecycle mutate qualification. That is now closed at `app/transport/services/assignment_service.py:193-195` and `:377-382`.

---

## 1. Stable invariants

These are **STABLE**. They are already true in code, they are load-bearing, and no node may weaken them without a control-session decision recorded here.

### I-1 — `is_online ⇒ is_available`

An online driver is always qualified.

Enforced at four independent write sites, all projecting the **end state** before writing either field (so a partial payload cannot smuggle the forbidden combination):

| Site | Guard |
|------|-------|
| Driver self-service status endpoint | `app/transport/api/driver_routes.py:710-720` |
| `ProviderService.set_driver_operational_status` | `app/transport/services/provider_service.py:1400-1408` |
| Admin PUT `DriverDetailResource.put` | `app/transport/api/driver_routes.py:176-184` |
| `ProviderService.update_driver_status` | `app/transport/services/provider_service.py:1283-1289` |

Enforced by construction at registration: a driver is always created `is_online=False`, `is_available=auto_approve` — i.e. `(F,F)` or `(F,T)`, never `(T,F)` (`app/transport/services/provider_service.py:757-764`).

Enforced by construction when the override is enabled: the override forces `is_available=True` because "override vouches for qualification" (`app/transport/services/provider_service.py:1495-1497`).

**Known enforcement hole (GAP-01, §7.6):** the moderator "suspend" action writes `entity.is_available = False` on a `DriverProfile` **without** writing `is_online = False` (`app/admin/moderator/routes.py:3601-3602`). If the driver was online, the persisted row violates I-1. The dispatch pool masks this (it filters both flags), so the violation is invisible in supply terms but is a real I-1 breach in storage.

### I-2 — Trip lifecycle NEVER touches `DriverProfile.is_available`

`AssignmentService.claim` no longer writes driver availability (`app/transport/services/assignment_service.py:193-195`; the `r2` statement at `:196-207` is a read-only `SELECT ... FOR UPDATE`, not an `UPDATE`). `AssignmentService.release` likewise writes only the **vehicle** busy flag (`app/transport/services/assignment_service.py:384-405`, `:403`). The rider trip transition delegates to `release` and never touches the driver flags (`app/transport/services/booking_service.py:708-730`).

### I-3 — 300 s freshness authority

`TrackingService.LOCATION_TTL_SECONDS = 300` is the single freshness constant (`app/transport/services/tracking_service.py:26`). Every consumer derives its cutoff from it:

- `availability_service._freshness_cutoff()` — `app/transport/services/availability_service.py:70-73`
- `MatchingService._rank_drivers_for_booking` — `app/transport/services/matching_service.py:349`
- `TrackingService.get_nearby_drivers` — `app/transport/services/tracking_service.py:445`

Freshness is written only on a real observation (`app/transport/services/tracking_service.py:95`). **No code anywhere flips `is_online` off because location went stale** — see GAP-04 (§7.6) and policy §8.3.

### I-4 — Busy state is derived from `ACTIVE_ASSIGNMENT_STATUSES`, not from `is_available`

`ACTIVE_ASSIGNMENT_STATUSES = {assigned, driver_en_route, pickup_arrived, in_progress, disputed}` (`app/transport/services/assignment_service.py:36-42`) is the single source of truth for "engaged".

Engagement is evaluated as a correlated `NOT EXISTS` subquery:

- driver: `app/transport/services/assignment_service.py:183-192` (inside claim, `SELECT ... FOR UPDATE` at `:206`)
- vehicle: `app/transport/services/assignment_service.py:221-230` (inside claim)
- driver, read paths: `app/transport/services/availability_service.py:46-55`
- vehicle, read paths: `app/transport/services/availability_service.py:58-66`
- reverse late-release protection: `app/transport/services/assignment_service.py:391-401`

**Consequence:** a driver on a live trip is still `is_online=True, is_available=True` in storage and is excluded from supply only by the booking-status predicate.

### I-5 — Blocked states are absolute

`_BLOCKED_DRIVER_STATES = {"suspended", "revoked", "blacklisted"}` (`app/auth/context.py:104`).

- Go-live gate: `app/transport/services/go_live_service.py:132-135`
- Override cannot be enabled on a blocked driver: `app/transport/services/provider_service.py:1477-1483`
- Dispatch pool requires `compliance_status == APPROVED`, which excludes every blocked state by construction: `app/transport/services/provider_service.py:1786`, `app/transport/services/availability_service.py:101`, `:147`, `:218`
- Claim requires `compliance_status == APPROVED` **even when `force=True`** (`app/transport/services/assignment_service.py:201-202`; `force` relaxes only the `is_online` clause at `:203` and the vehicle readiness clause at `:237`)

**Consequence:** a blocked driver is excluded from supply even though `is_online` may remain `True` in storage (GAP-04, §7.6).

### I-6 — Admin override bypasses requirement gates but not blocked states

`can_go_live` short-circuits when `driver_metadata["admin_online_override"]["enabled"]` is true (`app/transport/services/go_live_service.py:115-117`). Under override, only two checks remain **required**: `profile` and `blocked` (`app/transport/services/go_live_service.py:138-169`). KYC, compliance approval, licence and vehicle are bypassed — but they are also **not rendered at all** in the override branch, so a caller cannot see what was skipped beyond the explanatory `admin_override` hint item (`app/transport/services/go_live_service.py:155-166`).

Override does **not** bypass:

- profile existence / soft-delete (`app/transport/services/go_live_service.py:120-122`)
- blocked states (`app/transport/services/go_live_service.py:133-135`)
- the `is_online ⇒ is_available` invariant (`app/transport/services/provider_service.py:1495-1497`)
- dispatch pool `compliance_status == APPROVED` (`app/transport/services/provider_service.py:1786`) ← **see GAP-02 (§7.6)**

### I-7 — Vehicles are sourced only through an active `DriverVehicleHistory` row

`DriverProfile.current_vehicle` reads the history table, not `Vehicle.owner_id` (`app/transport/models.py:500-516`). It returns the first row where `ended_at IS NULL AND NOT is_deleted AND vehicle NOT NULL AND NOT vehicle.is_deleted`. The availability queries join the same table on `ended_at IS NULL AND is_deleted IS FALSE` (`app/transport/services/availability_service.py:86-93`, `:132-139`, `:202-209`).

**Consequence:** owning a vehicle is **not** being sourced with it. `register_vehicle_internal` accepts `driver_id` / `organisation_id` parameters and **never uses them** — it creates a `Vehicle` row and no history row (`app/transport/services/provider_service.py:860-936`, unused params at `:861-862`).

---

## 2. Vehicle sourcing model

### 2.1 The canonical convergence point

All three paths are required to converge into **exactly one** active `DriverVehicleHistory` row per driver.

| Path | Owner field | How the active history row is created | Citation |
|------|-------------|------------------------------------------|----------|
| Driver-owned | `Vehicle.owner_type='driver'`, `owner_id=DriverProfile.id` | **Not** at vehicle registration. Only via `assign_driver_to_vehicle`, called from the admin vehicle-assign endpoint, the driver vehicle-switch endpoint, CLI, or seed. | `app/transport/models.py:755-761`; `app/transport/api/vehicle_routes.py:427-460`; `app/transport/api/driver_routes.py:871-887` |
| Fleet | `Vehicle.owner_type='organisation'`, `owner_id=OrganisationTransportProfile.organisation_id` | Same canonical function; fleet participation itself is recorded in the `organisation_drivers` table, which is a **separate** concern. | `app/transport/models.py:762-770`; `app/transport/models.py:2015-2029` |
| Marketplace | `Vehicle` owned by a `User`; listing at `VehicleMarketplaceListing` | `MarketplaceService._activate_contract` → `assign_driver_to_vehicle(reason='marketplace_contract')` on driver acceptance of contract terms. | `app/transport/services/marketplace_service.py:703-737`, call at `:721-727` |

### 2.2 The canonical function

`assign_driver_to_vehicle(driver, vehicle, reason, authorized_by, notes)` — `app/transport/models.py:2584`.

It ends any prior active row for that driver (`:2597-2607`), ends any prior active row for that vehicle (`:2610-2620`), inserts one new active row (`:2623-2631`), and **commits internally** (`:2635`).

### 2.3 What the database actually guarantees

| Constraint | Present? | Citation |
|-----------|----------|----------|
| At most one active row per **vehicle** | **YES** — partial unique index `ix_unique_active_vehicle` on `vehicle_id WHERE ended_at IS NULL` | `app/transport/models.py:924-929` |
| At most one active row per **driver** | **NO** — `ix_driver_vehicle_history_driver (driver_id, started_at)` is non-unique | `app/transport/models.py:921` |

### 2.4 The gap (GAP-03, §7.6)

**Convergence is procedural, not guaranteed.**

1. **No per-driver uniqueness.** Nothing at the database level prevents a driver from holding two active `DriverVehicleHistory` rows. `assign_driver_to_vehicle` prevents it *when it is the writer*, but the admin assign endpoint (`app/transport/api/vehicle_routes.py:427-460`) and the breakdown handler (`app/transport/models.py:2640-2698`) both insert directly. `current_vehicle` would then return an arbitrary row (`app/transport/models.py:506-516`), and `availability_service` would produce duplicate vehicle rows.
2. **Vehicle registration creates no supply.** A driver can register three vehicles and hold zero of them (`app/transport/services/provider_service.py:860-936`). Ownership is recorded; supply is not.
3. **The marketplace path can silently lose supply.** `_activate_contract` sets the contract `ACTIVE` and then wraps the `assign_driver_to_vehicle` call in `try/except` that logs and continues (`app/transport/services/marketplace_service.py:713-734`), committing the `ACTIVE` contract regardless (`:736`). A driver can therefore hold an ACTIVE contract and no vehicle — permanently, because `accept_contract_terms` requires `PENDING_SIGNATURE` (`:697-698`) and would refuse a second attempt on the now-ACTIVE contract. This is register row SUPPLY-04.
4. **Fleet participation is recorded but not enforced in supply.** `organisation_drivers.is_active` exists (`app/transport/models.py:2025`) and is read in exactly one place — the org dashboard counter (`app/transport/services/provider_service.py:444-456`). No pool, claim, or availability predicate reads it. This is register row SUPPLY-02.

---

## 3. Driver state model

### 3.1 The four states

```
                 register (auto_approve)
   DRIVER EXISTS ─────────────────────────────► QUALIFIED  (is_available=True, is_online=False)
        │                                              ▲
        │ auto_approve off                             │ approve / override enable
        ▼                                              │
   NOT QUALIFIED (F,F) ────────────────────────────────┘
        │  can_go_live.ready                           │ can_go_live.ready == False
        ▼                                              ▼
  ONLINE ELIGIBLE ──────go-live toggle──► ONLINE ──────► (blocked / eligibility lost → forced offline)
                                                    │        │
                                                    │        └── driver_metadata flag cleared / block applied
                                                    ▼
                                              MATCHABLE  = ONLINE ∩ FRESH ∩ UNENGAGED
                                                          ∩ APPROVED ∩ VALID VEHICLE ∩ SCORE ≥ 40
```

### 3.2 State table

| # | State | Entry condition | Exit condition | Authority |
|---|-------|-----------------|----------------|-----------|
| **S0** | DRIVER EXISTS | `register_driver` commits a `DriverProfile` | soft delete, or blocked | `app/transport/services/provider_service.py:740-778`; delete at `app/transport/api/driver_routes.py:201-217` |
| **S1** | NOT QUALIFIED | default (`auto_approve` off) → `(F,F)` | admin approve, or override enable | `app/transport/services/provider_service.py:757-764` |
| **S2** | QUALIFIED (offline) | `is_available=True` **and** `is_online=False` — i.e. `compliance_status == APPROVED`, or override enabled | go-live toggle | `app/transport/services/provider_service.py:1244-1267` (approve), `:1497` (override) |
| **S3** | ONLINE ELIGIBLE | `can_go_live(driver).ready is True` | any required gate turns false | `app/transport/services/go_live_service.py:257-258` |
| **S4** | ONLINE | a writer sets `is_online=True` after the I-1 projection passes, and (self-service path) after the S3 check | explicit offline toggle; override disable with no longer-eligible (§6.4); soft delete; **NOT** location staleness | `app/transport/api/driver_routes.py:722-740`; `app/transport/services/provider_service.py:1410-1420`; `app/transport/services/provider_service.py:1511-1515` |
| **S5** | MATCHABLE | ONLINE **and** `location_updated_at ≥ now-300s` **and** valid canonical coords **and** no active booking **and** `compliance_status == APPROVED` **and** a current vehicle **and** `match_score ≥ 40` | any conjunct false | see §3.3 |

### 3.3 The `can_go_live` gate composition (S3 detail)

`can_go_live(driver) -> GoLiveChecklist(ready, checks)` — `app/transport/services/go_live_service.py:98-258`. `ready` is `not any(c.required and not c.ok)` (`:257-258`).

| Gate | key | required | Source | Citation |
|------|-----|----------|--------|----------|
| Active driver profile | `profile` | yes, never bypassed | `id` truthy and not `is_deleted` | `:120-122`, `:196-202` |
| Identity verification (KYC) | `kyc` | yes, bypassable | `driver_go_live_kyc_qualified(user_id)`, fail-closed on evaluation error | `:125-130`; `app/auth/kyc_compliance.py:860-879` |
| Not suspended or blocked | `blocked` | yes, **never** bypassed | `compliance_status ∉ {suspended, revoked, blacklisted}` | `:132-135`, `:215-221`; set at `app/auth/context.py:104` |
| Compliance approval | `approval` | yes, bypassable | `compliance_status == "approved"` — deliberately the same gate claim enforces | `:171-172`, `:222-232` |
| Valid driver licence | `licence` | yes, bypassable | number present **and** expiry ≥ now (naive expiries coerced to UTC) | `:174-187`, `:233-243` |
| Assigned vehicle | `vehicle` | **conditional** | only when `service_types` contains `on_demand` | `:189-193`, `:244-254`; `service_requires_own_vehicle` at `:76-95` |
| Admin online override | `admin_override` | no | informational, shown only in the override branch | `:155-166` |

`can_go_live` is the single decision authority; the writers are the execution. It is consumed by the self-service endpoint (`app/transport/api/driver_routes.py:725`), the service method (`app/transport/services/provider_service.py:1386`), the vehicle-switch endpoint (`app/transport/api/driver_routes.py:829`), and the override-disable re-check (`app/transport/services/provider_service.py:1514`).

### 3.4 The `match_score` composition (S5 detail)

`_rank_drivers_for_booking` — `app/transport/services/matching_service.py:344-424`.

**Hard geographic pre-filter** (applied before scoring, `:357-372`): a driver is only matchable when `location_updated_at ≥ now-300s` **and** both canonical `latitude`/`longitude` parse and are in range. A driver whose location is legacy `lat`/`lng`, partial, or malformed is excluded even if the timestamp is fresh, so non-geographic score terms cannot promote them.

**Score terms** (`:374-409`):

| Term | Points | Citation |
|------|--------|----------|
| Distance < 5 km | +30 | `:384-385` |
| Distance < 10 km | +20 | `:386-387` |
| Distance < 15 km | +10 | `:388-389` |
| Vehicle class exact match | +25 | `:393-394` |
| Class list contains `premium`/`luxury` (non-exact) | +15 | `:395-396` |
| Class contains `van` and `passenger_count > 4` | +25 | `:397-398` |
| `average_rating × 4` (floor) | +0..+20 | `:401` |
| `acceptance_rate/100 × 15` (floor) | +0..+15 | `:404` |
| Booking service type in `service_types` | +10 | `:407-409` |

**Threshold:** `score ≥ 40` — `app/transport/services/matching_service.py:418`. Below threshold the driver is silently dropped (no reason recorded). Results sorted descending by score (`:423`).

Distance uses canonical GEO haversine, converted to km to preserve Transport's kilometre contract (`app/transport/services/matching_service.py:443-460`). ETA is a heuristic, not routing: `distance × 2 + 5` minutes, else 15 (`:411-415`); the availability-side ETA uses a 25 km/h straight-line planning speed (`app/transport/services/availability_service.py:174`, `:244-246`).

---

## 4. Rider dispatch pool predicate

### 4.1 The predicate as implemented

| File | Function | Predicate |
|------|----------|-----------|
| `app/transport/services/provider_service.py:1743` | `get_available_drivers` | `is_deleted == False AND is_online == True AND is_available == True AND compliance_status == APPROVED` (`:1782-1787`), optional `operational_zones.contains([zone])` (`:1789-1792`), optional `vehicle_classes.contains([vehicle_class])` (`:1794-1797`), `LIMIT 50` default (`:1745`, `:1799`) |
| `app/transport/services/matching_service.py:344` | `_rank_drivers_for_booking` | + fresh canonical location (`:357-372`) + `score ≥ 40` (`:418`) |
| `app/transport/services/availability_service.py:76` | `_available_vehicle_ids` | + active `DriverVehicleHistory` (`:86-93`) + driver approved (`:101`) + fresh (`:102-103`) + `NOT` driver engaged (`:104`) + `NOT` vehicle engaged (`:105`) — **no caller; dead code** |
| `app/transport/services/availability_service.py:115` | `available_by_class` | same as above, grouped by `vehicle_class` (`:141-153`) |
| `app/transport/services/availability_service.py:177` | `nearest_eta_minutes_for_class` | same, plus `vehicle_class` equality and non-null `last_location` (`:211-224`) |

### 4.2 What the contract requires vs. where each conjunct actually lives

Required: `is_online AND is_available AND NOT engaged`.

| Conjunct | In the pool selector? | Where it is actually enforced |
|-----------|------------------------|------------------------------|
| `is_online` | **Yes** — `provider_service.py:1784` | — |
| `is_available` | **Yes** — `provider_service.py:1785` | — |
| `NOT engaged` | **No** | Split across two later stages: **claim** re-reads engagement under `SELECT ... FOR UPDATE` for the driver (`assignment_service.py:183-208`) and the vehicle (`:221-242`); the **availability** read paths apply it as `NOT EXISTS` (`availability_service.py:104-105`, `:150-151`, `:222-223`) |

The ranking pool is deliberately a **superset**: `get_available_drivers`'s own docstring says "THIS METHOD IS A POOL SELECTOR, NOT A RANKER" and requires `limit` to be large enough that truncation is unlikely to bias the ranker (`app/transport/services/provider_service.py:1746-1761`). It explicitly forbids `ORDER BY` (`:1762-1765`) and caching (`:1767-1777`).

### 4.3 Consequences of the split (all current, all real)

1. **Engaged drivers are offered work.** A driver on an active trip passes the pool selector and can be ranked and sent an offer. Refusal happens only at accept-time claim (`:459-465`). Register row C6 / MATCH-01 unaffected but operationally noisy.
2. **Vehicle-less drivers receive un-acceptable offers.** The pool applies no vehicle predicate, so it can return drivers with `vehicle_id: None` (`app/transport/services/provider_service.py:1813`). `DriverOfferAcceptResource` refuses such an accept with HTTP 400 (`app/transport/api/driver_routes.py:433-438`). A non-`on_demand` driver can reach ONLINE with no vehicle — `service_requires_own_vehicle` returns `False` for them (`app/transport/services/go_live_service.py:76-95`, `:189-193`) — and then be ranked into **on-demand** offers, because the ranker scores `booking.service_type` against `driver.service_types` but does not require it (`app/transport/services/matching_service.py:407-409`).
3. **Four divergent supply predicates exist.** `get_available_drivers`, `availability_service` (three near-identical copies), and `tracking_service.get_nearby_drivers` each encode a different subset. `get_nearby_drivers` filters only `is_online + is_available + fresh` — **no** `is_deleted`, **no** `compliance_status`, **no** engagement, **no** vehicle (`app/transport/services/tracking_service.py:448-456`), and hard-caps at 50 (`:451`).
4. **Dashboard counters are a fifth definition.** `count_active_drivers` = `is_online AND is_available AND not deleted` (`app/transport/services/provider_service.py:357-367`); `count_available_vehicles` = `Vehicle.is_available AND not deleted` (`:369-378`); `count_org_active_drivers` adds the `organisation_drivers.is_active` participation filter (`:444-456`). The transport dashboard uses its own filters again (`app/transport/api/dashboard_routes.py:52`, `:56`, `:70`), and analytics likewise (`app/transport/api/analytic_routes.py:101`, `:111`). Admin driver listing can filter on `is_online` alone (`app/transport/api/organisation_routes.py:278`).
5. **Scheduled-route assignment ignores online state entirely.** `ScheduledRouteAssignmentResource.post` selects a driver with `is_deleted=False, is_available=True` only — no `is_online`, no compliance (`app/transport/api/route_routes.py:293-302`).

### 4.4 Guarantee

A rider-facing supply answer may only come from the availability predicate in `app/transport/services/availability_service.py`. Any surface needing a supply count must read that predicate or a named projection of it — never re-derive it.

---

## 5. Marketplace pool predicate

### 5.1 Status: **NOT IMPLEMENTED — design item**

There is no marketplace supply pool in the codebase. Confirmed by exhaustive read of `VehicleMarketplaceService` (`app/transport/services/marketplace_service.py:36-957`): every method is either listing management (`create_listing` `:43`, `update_listing` `:116`, `pause_listing` `:151`, `reactivate_listing` `:164`, `close_listing` `:177`), driver-side **discovery** (`search_listings` `:743`, `get_recommended_listings` `:789`, `get_listing_details` `:836`), or contract lifecycle (`submit_application` `:234`, `approve_application` `:460`, `accept_contract_terms` `:669`, `terminate_contract` `:584`).

None of them read `Vehicle.is_available` or `DriverProfile.is_online`. The direction is listing → driver, never vehicle → rider supply.

### 5.2 Intended predicate (design only — NOT a specification of current behaviour)

A vehicle is in the **marketplace pool** for a rider when:

```
Vehicle.is_available                       -- not busy on an active booking
AND Vehicle.is_deleted IS FALSE
AND Vehicle.status = 'active'
AND NOT DriverProfile.is_online            -- not already serving the rider dispatch pool
AND (no active DriverVehicleHistory row)   -- un-converged supply, offered to drivers first
AND (a VehicleMarketplaceListing exists with an acceptable listing_status)
AND NOT (a VehicleContract exists that has not reached ACTIVE for this vehicle)
```

This is a **two-pool dispatch model**: marketplace supply is routed to *drivers* who need a vehicle, while rider supply comes only from §4. The same vehicle must never appear in both pools — hence `NOT DriverProfile.is_online` as the mutual-exclusion term, and `Vehicle.is_available` as the busy flag that the rider pool already respects.

### 5.3 What must be decided before this can be built

- Which `MarketplaceListingStatus` values expose a vehicle to supply (`app/transport/models.py:2976-2981`)
- Whether an un-converged vehicle may be shown to riders at all, or only to drivers
- Precedence when a vehicle has both an ACTIVE contract and an open listing (`app/transport/models.py:2940-2946`)
- Interaction with `VehicleContract` date windows — see §7.2 (SUPPLY-03)

**Nothing in §5 is implemented. It must not be read as current behaviour.**

---

## 6. Admin override capability contract

Implemented by SUPPLY-00. Five axes.

### 6.1 Axis 1 — WHO (permission)

Two independent checks, both must pass:

| Layer | Check | Citation |
|-------|-------|----------|
| Decorator | `@transport_admin_required` | `app/transport/api/driver_routes.py:923` |
| In-body | `has_global_role(current_user, "owner", "super_admin", "admin", "transport_admin")` → else 403 | `app/transport/api/driver_routes.py:932-933` |

**Gap:** the service method `set_admin_online_override` itself carries **no** authorization check — only `@monitor_endpoint` and `@rate_limit("driver_status_update", limit=60, period=60)` (`app/transport/services/provider_service.py:1434-1442`). The boundary is the route, not the service. Any future internal caller bypasses the WHO axis entirely.

Route: `POST /api/transport/drivers/<int:driver_id>/admin-online-override` (`app/transport/api/routes.py:132-133`).

### 6.2 Axis 2 — WHAT (which gates are overridable)

Bypassed when the override is active (`app/transport/services/go_live_service.py:138-169`):

- KYC capability (`:125-130`)
- Compliance approval (`:171-172`)
- Valid licence (`:174-187`)
- Assigned vehicle, including the `on_demand` requirement (`:189-193`)

**Not bypassed:**

- Active driver profile (`:120-122`, `:140-146`)
- Not blocked (`:133-135`, `:147-154`)

Enabling the override also **forces `is_available = True`** to preserve I-1 (`:1495-1497`).

**GAP-02 (§7.6):** the override does **not** reach the dispatch pool or the claim. `get_available_drivers` requires `compliance_status == APPROVED` unconditionally (`app/transport/services/provider_service.py:1786`) and `claim` requires it too (`app/transport/services/assignment_service.py:201-202`). An override-enabled driver who is not `APPROVED` passes `can_go_live`, goes ONLINE, is written as ONLINE in storage — and is **still absent from the rider supply pool**. This is the single most consequential open item in this contract.

### 6.3 Axis 3 — WHAT IS ABSOLUTE (blocked states)

Two independent enforcements:

1. Grant refused when `compliance_status ∈ {suspended, revoked, blacklisted}` → HTTP 422 (`app/transport/services/provider_service.py:1477-1483`; mapped at `app/transport/api/driver_routes.py:952-953`).
2. `can_go_live` keeps `blocked` as a required check in the override branch (`app/transport/services/go_live_service.py:147-154`).

Neither is bypassable by any role.

### 6.4 Axis 4 — AUDIT (by / at / reason)

Persisted in `driver_metadata["admin_online_override"]` (JSONB column `metadata`, `app/transport/models.py:358`):

| Field | Value | Citation |
|-------|-------|----------|
| `enabled` | bool | `app/transport/services/provider_service.py:1490`, `:1500` |
| `by` | actor user id | `:1491`, `:1501` |
| `at` | UTC ISO-8601 | `:1492`, `:1502` |
| `reason` | trimmed, truncated to 200 chars | `:1493`, `:1503` |

Additionally an `audit_log` row `action="driver_admin_online_override_set"` carrying `resource_type="driver"`, `resource_id=str(driver_id)`, `user_id=actor_user_id`, `details={enabled, reason, is_available, is_online}`, with `db_session=db.session` and **before** the commit so it persists in the same transaction (`:1517-1533`). This was one of the explicit SUPPLY-00 corrections.

The admin UI renders `by`, `at`, `reason` read-only (`app/transport/routes.py:2867-2876`, `templates/transport/admin/driver_detail.html:78-85`) and requires a reason client-side before enabling (`:142-145`), with a confirm dialog (`:146`).

**Known durability caveat (register row SUPPLY-AUDIT-PERSIST):** persistence depends on this call site passing `db_session` with a committing transaction. Other transport call sites without it persist to console only.

### 6.5 Axis 5 — RETURN PATH

**Disable behaviour, current** (`app/transport/services/provider_service.py:1498-1515`):

1. `enabled = False` written with `by`/`at`/`reason`.
2. `is_available` reverted to `(compliance_status == "approved")` — `:1506`.
3. `db.session.flush()` so `can_go_live` observes the cleared flag — `:1513`.
4. If `is_online` and `can_go_live(driver).ready` is now `False` → `is_online = False` — `:1514-1515`.
5. Audit + commit — `:1519-1533`.

So the return path **does** force offline, but only when the driver no longer passes the gates. A driver who is still `APPROVED` stays online after the override is removed.

**NOT implemented — see §8.2:** no auto-expire, no TTL, no expiry field in the metadata (the shape is fixed four keys, `:1489-1494`).

### 6.6 Summary of the override capability today

| Axis | Status |
|------|--------|
| WHO | Implemented at route; **not** at service (GAP-05, §7.6) |
| WHAT | Implemented for `can_go_live`; **does not reach pool/claim** (GAP-02) |
| WHAT IS ABSOLUTE | Implemented, doubly enforced |
| AUDIT | Implemented (metadata + audit row) |
| RETURN PATH | Implemented on disable; **no auto-expire** (§8.2) |

---

## 7. Known gaps (implementation level)

Every gap below is a **current-state defect or omission** in code, with evidence. None is fixed by this document.

### 7.1 SUPPLY-02 — Fleet participation not enforced at pool/claim — P0 if fleet pilot

`OrganisationTransportProfile.can_provide_on_demand` (`app/transport/models.py:581`) and `organisation_drivers.is_active` (`app/transport/models.py:2025`) exist and are schema-constrained (`app/transport/models.py:538`, `:542`).

**Neither is read by any supply predicate.** Exhaustive read confirms `can_provide_on_demand` appears only in registration defaults (`app/transport/services/provider_service.py:1124`) and org API serialization (`app/transport/api/organisation_routes.py:65`, `:121`, `:208`). `organisation_drivers.is_active` is read only by the dashboard counter (`app/transport/services/provider_service.py:444-456`).

Consequence: a driver whose fleet membership is inactive, or whose organisation cannot provide on-demand, is fully dispatchable.

Also: `register_organisation_transport` creates the org profile with `can_provide_on_demand=False` unconditionally (`app/transport/services/provider_service.py:1124`).

### 7.2 SUPPLY-03 — Marketplace contract dates not enforced — P0 if marketplace pilot

`VehicleContract` carries `start_date` / `end_date` / `actual_end_date` / `notice_given_at` (`app/transport/models.py:3155-3161`) and a `ContractStatus` with `ACTIVE / SUSPENDED / TERMINATED / EXPIRED / PENDING_SIGNATURE` (`app/transport/models.py:2940-2946`).

**No date arithmetic anywhere.** `terminate_contract` checks only `contract.status != ACTIVE` (`app/transport/services/marketplace_service.py:616`); `_activate_contract` checks only `PENDING_SIGNATURE` (`:705`); `get_driver_contracts` / `get_owner_contracts` order by `start_date` but never filter on it (`:639`, `:652`). `DriverVehicleApplication` also carries `contract_start_date` / `contract_end_date` (`app/transport/models.py:3083-3084`) that nothing reads.

Consequence: an expired or terminated contract leaves the `DriverVehicleHistory` row active, so the vehicle stays in rider supply with no valid commercial basis. Expiry is never detected, so no code path ever sets a contract to `EXPIRED`.

### 7.3 SUPPLY-04 — `_activate_contract` swallows `DriverVehicleHistory` failure — P1

`app/transport/services/marketplace_service.py:703-737`. The `assign_driver_to_vehicle` call is wrapped in `try/except Exception` that logs and continues (`:731-734`); the contract is committed `ACTIVE` regardless (`:736`). See §2.4 item 3 for the permanent-loss consequence.

### 7.4 SUPPLY-ADMIN — Admin Online policy — POLICY

Axis-by-axis state is in §6.6. The open policy decisions are in §8.

### 7.5 Unchecked: `max_concurrent_bookings`

`DriverProfile.max_concurrent_bookings` exists with `default=1` (`app/transport/models.py:340`) and is **read by no code anywhere** (verified by exhaustive grep across the repository — the only occurrence is the column definition).

The effective limit today is the hardcoded reverse-booking check in `claim`: a driver with **any** other booking in `ACTIVE_ASSIGNMENT_STATUSES` is unclaimable (`app/transport/services/assignment_service.py:183-192`, enforced at `:204` under `SELECT ... FOR UPDATE` at `:206`).

So the implemented behaviour is `max_concurrent_bookings == 1` for every driver regardless of the stored value. This is a divergence between a stored setting and the enforced rule — a stale-configuration hazard (OS §6 "Sage" class), not merely an unimplemented feature. A driver set to `3` would silently be limited to `1`.

### 7.6 Additional gaps found while writing this contract

These are **new findings**, not present in the register. Recorded, not fixed (OS §12).

| ID | Gap | Evidence | Severity |
|----|-----|----------|----------|
| **GAP-01** | Moderator suspend breaks I-1 in storage: writes `is_available = False` on a driver without clearing `is_online` | `app/admin/moderator/routes.py:3601-3602` (compare the correct pattern at `app/transport/api/driver_routes.py:207-208`) | P1 |
| **GAP-02** | Admin override does not reach the dispatch pool or claim: override-enabled non-`APPROVED` driver goes ONLINE but is absent from supply | `app/transport/services/provider_service.py:1495-1497` vs `:1786`; `app/transport/services/assignment_service.py:201-202` | **P1 — most consequential** |
| **GAP-03** | No per-driver uniqueness on active `DriverVehicleHistory`; `current_vehicle` returns an arbitrary row when duplicates exist | `app/transport/models.py:921` vs `:924-929`; property at `:500-516` | P1 |
| **GAP-04** | No code path clears `is_online` when compliance changes to a blocked state. `update_driver_status` string shorthand writes `compliance_status` only (`app/transport/services/provider_service.py:1244-1267`); `DriverVerificationResource` `update_compliance` likewise (`:246-247`); the admin web approve/reject routes add nothing (`app/transport/routes.py:2804`, `:2833`). `is_online = False` is written only at `app/transport/api/driver_routes.py:207`, `app/transport/services/provider_service.py:1515`, and `app/transport/cli_driver.py:330` | see citations | P1 — feeds register C7 / D8 |
| **GAP-05** | `set_admin_online_override` carries no authorization check at the service layer | `app/transport/services/provider_service.py:1434-1442` | P2 |
| **GAP-06** | `_available_vehicle_ids` is the only function documented as the shared canonical predicate ("no drift between what we count and what we use") and has **zero callers** | `app/transport/services/availability_service.py:76-108` | P2 |
| **GAP-07** | Vehicle registration creates no `DriverVehicleHistory`; `driver_id` / `organisation_id` parameters accepted and never used | `app/transport/services/provider_service.py:860-862` | P2 |
| **GAP-08** | Vehicle-less drivers can be ranked into on-demand offers; accept then 400s. Pool has no vehicle predicate; ranker scores service type but does not require it | `app/transport/services/provider_service.py:1782-1787`; `app/transport/services/matching_service.py:407-409`; `app/transport/api/driver_routes.py:433-438` | P2 |
| **GAP-09** | Admin `VehicleAssignmentResource.assign` applies **no** compliance or blocked-state check — a suspended driver can be assigned a vehicle, and thereby reach `current_vehicle` | `app/transport/api/vehicle_routes.py:427-460` | P2 |
| **GAP-10** | `ScheduledRouteAssignmentResource` selects drivers on `is_available` alone — no `is_online`, no compliance | `app/transport/api/route_routes.py:293-302` | P2 |
| **GAP-11** | `TrackingService.get_nearby_drivers` omits `is_deleted`, `compliance_status`, engagement and vehicle predicates, and hard-caps at 50 | `app/transport/services/tracking_service.py:448-456` | P2 |
| **GAP-12** | No approval-rejection reason recorded on the `DriverVehicleApplication`↔`VehicleContract` chain at supply level; `marketplace_service._check_driver_eligibility` (`:322`) is evaluated at application time only | `app/transport/services/marketplace_service.py:322-380` | P3 |

---

## 8. Policy decisions still required

**The control session owns these. The agent does not.**

### 8.1 Pilot scope — driver-owned / + fleet / + marketplace / all

Blocks the priority order of SUPPLY-02 and SUPPLY-03 (register "Unresolved Control-Session Decisions" row 2).

The scope choice determines:

- whether `can_provide_on_demand` and `organisation_drivers.is_active` must enter the dispatch predicate (SUPPLY-02)
- whether `VehicleContract` date windows must enter it (SUPPLY-03)
- whether §5's two-pool marketplace model is built at all

Dependency note: §5.2 as designed requires marketplace to be **out** of the rider dispatch pool by construction (`NOT is_online`). If marketplace is in scope, that design must be settled before any predicate work, not after.

### 8.2 Auto-expire for the admin override

Currently the override is indefinite — the metadata shape has no TTL (`app/transport/services/provider_service.py:1489-1494`), and nothing re-evaluates it. Decisions required:

- Does an override expire automatically after a fixed period?
- Does expiry require a human to clear it (safer) or self-clear (prevents forgotten live bypasses)?
- On expiry, does the driver follow the §6.5 return path (forced offline if no longer eligible)?
- Is a per-driver max duration required before enabling?

Interaction to decide: GAP-02. If the override does not reach the pool, auto-expiry changes nothing about supply; the gate stays shut either way.

### 8.3 Stale-online auto-offline policy (D8)

Register C7 requires stale-online to be a **read-only projection**; D8 defers the write policy.

Current state: `is_online` is never cleared by staleness (GAP-04). Freshness is enforced only at the read boundary (`app/transport/services/availability_service.py:102-103`; `app/transport/services/matching_service.py:349`, `:362-372`) and never at the write boundary (`app/transport/services/provider_service.py:1350-1420`).

Decisions required:

- Does staleness clear `is_online`, or does it only remove the driver from supply?
- If it clears it, is the write synchronous (on read) or a Celery sweep (`app/tasks/` already holds transport recovery jobs, `app/tasks/transport_recovery.py`)?
- What happens to an in-progress trip when the driver's location goes stale — must the trip be protected from any auto-offline?
- Does the 300 s TTL apply to `last_seen_at` as well as `location_updated_at`?

Consequence of not deciding: a driver whose phone dies stays `is_online=True` in storage and in every dashboard counter (`app/transport/services/provider_service.py:357-367`), while correctly absent from real supply. Admin views and reality diverge.

### 8.4 Additional decisions this contract surfaces

| # | Decision | Blocks |
|---|----------|--------|
| 4 | GAP-02 disposition: should the admin override reach the dispatch pool and the claim? | override usefulness; §6.2 |
| 5 | §4.3 item 1: should the pool exclude engaged drivers, or is accept-time refusal acceptable operationally? | register C6 |
| 6 | §5.2: is the two-pool marketplace model accepted, and which `listing_status` values expose supply? | §5 |
| 7 | `max_concurrent_bookings`: honoured, or removed as a stale setting (GAP in §7.5)? | §7.5 |
| 8 | `score ≥ 40` threshold ownership: product rule or engineering constant? | `app/transport/services/matching_service.py:418` |
| 9 | Whether the five divergent supply predicates (§4.3 item 4) consolidate onto `availability_service`, and in which node | §4.4 |

---

## 9. Ownership map

Constitutional boundary (AGENTS.md §17): a module MUST NOT become owner of another module's state.

| Domain | Owns | Fields / functions named in this contract |
|--------|------|------------------------------------------|
| **Transport** | Driver eligibility state, the dispatch pool, claim/release, freshness constant, matching | `DriverProfile.is_online` / `.is_available` / `.location_updated_at` / `.last_seen_at` / `.driver_metadata` (`app/transport/models.py:333-337`, `:358`); `Vehicle.is_available` / `.status` / `.owner_type` / `.owner_id` (`:667-668`, `:738-739`); `DriverVehicleHistory` (`:917-959`); `can_go_live` (`app/transport/services/go_live_service.py:98`); `AssignmentService.claim` / `.release` (`app/transport/services/assignment_service.py:107`, `:313`); `ACTIVE_ASSIGNMENT_STATUSES` (`:36-42`); `get_available_drivers` (`app/transport/services/provider_service.py:1743`); `set_driver_operational_status` (`:1350`); `set_admin_online_override` (`:1436`); `_rank_drivers_for_booking` (`app/transport/services/matching_service.py:344`); `LOCATION_TTL_SECONDS` (`app/transport/services/tracking_service.py:26`); `available_by_class` (`app/transport/services/availability_service.py:115`) |
| **Auth / KYC** | KYC tier authority; blocked-state vocabulary; global roles | `driver_go_live_kyc_qualified` (`app/auth/kyc_compliance.py:860-879`); `DRIVER_GO_LIVE_MIN_KYC_TIER` (referenced `:871`); `_BLOCKED_DRIVER_STATES` (`app/auth/context.py:104`); `has_global_role` (used `app/transport/api/driver_routes.py:932`) |
| **Organisation** | Fleet eligibility; driver↔organisation membership | `OrganisationTransportProfile.can_provide_on_demand` (`app/transport/models.py:581`); `organisation_drivers` table incl. `is_active` (`app/transport/models.py:2015-2029`); `register_organisation_transport` (`app/transport/services/provider_service.py:1052`) |
| **Marketplace** | Listings, applications, contracts | `VehicleMarketplaceListing` (`app/transport/models.py:2956`); `DriverVehicleApplication` (`app/transport/models.py:3037`); `VehicleContract` (`app/transport/models.py:3100`); `ContractStatus` (`:2940`); `VehicleMarketplaceService` (`app/transport/services/marketplace_service.py:36`) |
| **Audit** | Forensic record of state-changing transport operations | `audit_log` (`app/utils/audit.py`, called from `app/transport/services/assignment_service.py:253`, `:420` and `app/transport/services/provider_service.py:1519`); `driver_admin_online_override_set` action (`app/transport/services/provider_service.py:1520`) |

### 9.1 Boundary violations visible today

- **Admin writes Transport state without a Transport-side gate.** Moderator suspend (GAP-01) writes `DriverProfile.is_available` from the admin module (`app/admin/moderator/routes.py:3602`), duplicating — and getting wrong — a rule Transport already owns. Transport's soft-delete path shows the correct shape: clear both flags (`app/transport/api/driver_routes.py:207-208`).
- **Transport reads Auth's blocked vocabulary correctly** (`app/transport/services/go_live_service.py:105`, `:135`) — this boundary is respected.
- **Auth does not write Transport state.** No KYC-revocation path flips `is_online` (GAP-04). Whether one *should* exist is part of §8.3.

---

## 10. Test contract

### 10.1 What exists today

| File | Tests | Protects |
|------|-------|----------|
| `tests/transport/test_supply00_override.py` | T1 `:88`, T2 `:134`, T3 `:162`, T4 `:211`, T5 `:252`, T6 `:280`, T7 `:305`, T8 `:356`, T9 `:402`, T10 `:442`, T11 `:481`, T12 `:516`, T13 `:545`, T14 `:581`, T15 `:614` | I-1 (T5, T6), I-2 (T1, T2), §3.3 gates (T3, T4), registration init (T7, T8), all five override axes (T9–T15) |
| `tests/transport/test_assignment_release_supply_invariant.py` | `:65`, `:94` | I-2 on `release`; `Vehicle.is_available` busy flag toggled by claim |
| `tests/test_transport_concurrent_claim.py` | `:253`, `:297`, `:339`, `:382`, `:400`, `:438`, `:488`, `:502`, `:522`, `:539`, `:869`, `:891`, `:909`, `:930` | I-4 under concurrency; late-release protection; `force` authorization; soft-delete |

### 10.2 Tests that MUST exist to protect the invariants

Each row is a named requirement, not an example. A node may not close a listed invariant without its case.

**I-1 — `is_online ⇒ is_available`**
1. Every writer refuses the projected state `online ∧ ¬available` — self-service endpoint, `set_driver_operational_status`, `update_driver_status`, admin `PUT`. *(T5/T6 cover admin PUT only.)*
2. A partial payload that omits `is_available` is still validated against the resulting state.
3. Registration never yields `(True, False)` under either `auto_approve` setting. *(T7/T8 cover this.)*
4. Override-enable produces `(?, True)`. *(T9/T10 cover the metadata and the go-live result.)*
5. **GAP-01 regression:** moderator suspend on an online driver must not leave `is_online=True, is_available=False`. **MISSING.**

**I-2 — trip lifecycle never touches driver `is_available`**
1. `claim` leaves `DriverProfile.is_available` unchanged. *(T1.)*
2. `release` leaves `DriverProfile.is_available` unchanged for both online and offline drivers. *(T2; `tests/test_transport_concurrent_claim.py:869`–`:930` assert pre-SUPPLY-00 semantics and are register row SUPPLY-00-TEST-UPDATE.)*
3. Full trip lifecycle `confirmed → assigned → driver_en_route → pickup_arrived → in_progress → completed` leaves driver flags unchanged at every step.

**I-3 — 300 s freshness**
1. A driver with `location_updated_at` older than 300 s is excluded from `available_by_class`, `nearest_eta_minutes_for_class` and the ranker.
2. A driver exactly at the boundary is included; one second past is excluded.
3. A fresh timestamp with legacy `lat`/`lng` or out-of-range coordinates is still excluded. *(`app/transport/services/matching_service.py:357-372`; partially covered by `tests/test_transport_geographic_contract.py`.)*
4. `get_nearby_drivers` applies the same cutoff. *(`app/transport/services/tracking_service.py:456`.)*

**I-4 — busy derived from booking status**
1. Two concurrent claims for one booking → exactly one wins. *(`:253`.)*
2. Two concurrent claims by one driver for two bookings → exactly one wins. *(`:297`; register row `test_one_driver_two_bookings` is OPEN P3 as a possible timing flake.)*
3. Same for the vehicle. *(`:339`.)*
4. Late release does not free a re-claimed driver or vehicle. *(`:438`.)*
5. A driver mid-trip is excluded from supply by the booking-status predicate **while remaining `is_online=True, is_available=True` in storage**.

**I-5 / I-6 — blocked absolute; override boundaries**
1. Override cannot be enabled on suspended / revoked / blacklisted. *(T12 covers suspended.)* **Revoked and blacklisted MISSING.**
2. `can_go_live` reports `blocked` as required and failing under override. *(`app/transport/services/go_live_service.py:147-154`.)*
3. **GAP-02:** an override-enabled, non-`APPROVED` driver — assert the actual current outcome (absent from pool, per `:1786`) so the behaviour is pinned before the §8.4 decision changes it. **MISSING.**
4. `force=True` does not relax the `APPROVED` requirement. *(`app/transport/services/assignment_service.py:201-202`; `:522` covers non-admin rejection.)*
5. `force=True` by a non-admin actor is refused. *(`:522`.)*

**§2 — sourcing convergence**
1. Assigning a second vehicle to a driver ends the first active row. *(`app/transport/models.py:2597-2607`.)*
2. Assigning a second driver to a vehicle ends the first active row; the unique index is the DB backstop. *(`app/transport/models.py:2610-2620`; `:924-929`.)*
3. **GAP-03:** a driver cannot hold two active rows; `current_vehicle` is unambiguous. **MISSING — no DB constraint exists to make it pass.**
4. **SUPPLY-04:** `assign_driver_to_vehicle` failure inside `_activate_contract` must not leave the contract `ACTIVE`. **MISSING** (`tests/transport/test_marketplace_operational_flow.py:328-330` mocks the failure but the assertion direction needs confirming against `:731-736`).
5. Vehicle registration alone does not create supply. *(`app/transport/services/provider_service.py:860-936`.)*

**§6.5 — return path**
1. Disable override forces offline when the driver no longer passes `can_go_live`. *(T11.)*
2. Disable override leaves online when the driver still passes. *(T11 covers the negative direction only.)*
3. `is_available` reverts to `(compliance_status == "approved")` on disable. *(T11.)*
4. Audit row persists with actor, timestamp, reason. *(T13.)*
5. Authorization: non-admin refused. *(T14, T15.)*

### 10.3 Test rules

- No test may be weakened to accommodate a behaviour change; behaviour changes come with their own node.
- Every gap in §7.6 needs either a pinning test (characterising current behaviour) or a fix test, **decided explicitly** — silence is not acceptable.
- `tests/conftest.py` and shared fixtures are out of scope for all of the above (OS §12).

---

## 11. Non-goals

This contract does **not** cover, and must not be read as covering:

1. **Booking status machine** — `BookingStatus`, `STATUS_TRANSITIONS`, the `no_match` CHECK (`app/transport/models.py:1016-1021`). Register MATCH-01 owns it.
2. **Matching quality** — the score weights, the 40-point threshold, the proximity bands. §3.4 records them; it does not govern them.
3. **Fare, wallet, payment, settlement** — register workstream H. Out of bounds per AGENTS.md §18.1.
4. **No-supply UX and empty states** — register C1–C3, MATCH-01-D.
5. **Location publishing reliability** — register D1–D3, D9–D11. §1 I-3 fixes only the TTL authority, not the heartbeat.
6. **Trip lifecycle timestamps and timeline** — register A5, A12.
7. **Route/scheduled assignment semantics** — noted as GAP-10 only; the route model is not a supply-predicate concern until a decision says it is.
8. **Notifications, dashboards, analytics presentation** — noted in §4.3 item 4 as divergence evidence; redesigning them is a separate node.
9. **Marketplace earnings and settlement** — `calculate_driver_earnings` (`app/transport/services/marketplace_service.py:871`), `process_settlement` (`:894`).
10. **Any code change.** This document changes nothing.

---

## 12. Citation index

### 12.1 Models — `app/transport/models.py`

| Symbol | Line |
|--------|------|
| `DriverProfile` class | 242 |
| `ix_driver_online` composite index | 249 |
| `compliance_status` column | 284 |
| `is_online` column | 333 |
| `is_available` column | 334 |
| `last_seen_at` | 335 |
| `last_location` | 336 |
| `location_updated_at` | 337 |
| `auto_accept_bookings` | 339 |
| `max_concurrent_bookings` | 340 |
| `driver_metadata` (column `metadata`) | 358 |
| `DriverProfile.current_vehicle` property | 500–516 |
| `OrganisationTransportProfile` class | 522 |
| `chk_hotel_no_on_demand` | 538 |
| `chk_tour_operator` constraint | 542 |
| `can_provide_on_demand` | 581 |
| `Vehicle` class | 644 |
| `Vehicle.owner_type` | 667 |
| `Vehicle.owner_id` | 668 |
| `Vehicle.status` | 738 |
| `Vehicle.is_available` | 739 |
| `Vehicle.is_reserved` | 740 |
| `Vehicle.owner_driver` relationship | 755–761 |
| `Vehicle.organisation_owner` relationship | 762–770 |
| `Booking.status` CHECK | 1016–1021 |
| `DriverVehicleHistory` class | 917 |
| `ix_driver_vehicle_history_driver` (non-unique) | 921 |
| `ix_driver_vehicle_history_active` (non-unique) | 923 |
| `ix_unique_active_vehicle` (partial unique) | 924–929 |
| `DriverVehicleHistory.driver_id` / `.vehicle_id` | 932 / 933 |
| `ended_at` | 938 |
| `assignment_reason` | 941 |
| `ContractStatus` enum | 2940–2946 |
| `VehicleMarketplaceListing` class | 2956 |
| `listing_status` | 2976–2981 |
| `DriverVehicleApplication` class | 3037 |
| `contract_start_date` / `contract_end_date` | 3083 / 3084 |
| `VehicleContract` class | 3100 |
| `VehicleContract.status` | 3146–3151 |
| `start_date` / `end_date` / `actual_end_date` | 3155 / 3156 / 3157 |
| `assign_driver_to_vehicle()` | 2584 |
| — ends prior driver assignment | 2597–2607 |
| — ends prior vehicle assignment | 2610–2620 |
| — inserts new row | 2623–2631 |
| — internal commit | 2635 |
| `handle_vehicle_breakdown()` | 2640–2698 |
| `organisation_drivers` table | 2015–2029 |
| `organisation_drivers.is_active` | 2025 |

### 12.2 Go-live — `app/transport/services/go_live_service.py`

| Symbol | Line |
|--------|------|
| `service_requires_own_vehicle()` | 76–95 |
| `can_go_live()` | 98 |
| override read from metadata | 115–117 |
| profile gate | 120–122 |
| KYC gate | 125–130 |
| blocked gate | 133–135 |
| override short-circuit branch | 138–169 |
| — `profile` check (override branch) | 140–146 |
| — `blocked` check (override branch) | 147–154 |
| — `admin_override` info item | 155–166 |
| approval gate | 171–172 |
| licence gate | 174–187 |
| vehicle gate | 189–193 |
| full check list | 195–255 |
| `ready` computation | 257–258 |

### 12.3 Assignment — `app/transport/services/assignment_service.py`

| Symbol | Line |
|--------|------|
| `ACTIVE_ASSIGNMENT_STATUSES` | 36–42 |
| `TERMINAL_RELEASE_STATUSES` | 44–48 |
| `CLAIMABLE_STATUSES` | 50 |
| `_actor_is_admin()` | 85–97 |
| `claim()` | 107 |
| force/admin authorization | 128–132 |
| r1 booking-state gate | 154–178 |
| `driver_engaged_other` subquery | 183–192 |
| SUPPLY-00a comment (no driver `is_available` write) | 193–195 |
| r2 driver gate (`SELECT ... FOR UPDATE`) | 196–208 |
| — `APPROVED` requirement (never relaxed by force) | 201–202 |
| — `is_online OR forced` | 203 |
| — `~driver_engaged_other` | 204 |
| — `with_for_update()` | 206 |
| `vehicle_engaged_other` subquery | 221–230 |
| r3 vehicle gate | 231–242 |
| — `Vehicle.is_available = False` | 240 |
| — `Vehicle.is_available OR forced` | 237 |
| audit + commit | 253–268 |
| `release()` | 313 |
| terminal-status check | 335–338 |
| booking row read | 340–352 |
| transition | 355–375 |
| SUPPLY-00a comment | 377–382 |
| vehicle restore (busy flag only) | 384–405 |
| — reverse `NOT EXISTS` guard | 391–401 |
| — `Vehicle.is_available = True` | 403 |
| audit + commit | 420–436 |

### 12.4 Provider — `app/transport/services/provider_service.py`

| Symbol | Line |
|--------|------|
| `count_active_drivers()` | 357–367 |
| `count_available_vehicles()` | 369–378 |
| `count_org_active_drivers()` (reads `organisation_drivers.is_active`) | 444–456 |
| `get_driver_online_status()` / `get_driver_availability()` | 524 / 533 |
| `register_driver()` | 664 |
| `_redis_lock` usage | 696 |
| `_assert_no_open_flags` | 712 |
| registration init `(F,F)` / `(F,T)` | 757–764 |
| `register_vehicle_internal()` | 860 |
| — unused `driver_id` / `organisation_id` params | 861–862 |
| — vehicle created with `is_available=True`, no history row | 904–926 |
| `register_vehicle()` ownership verification | 955–982 |
| `register_organisation_transport()` | 1052 |
| `can_provide_on_demand=False` | 1124 |
| `update_driver_status()` | 1206 |
| — string shorthand (compliance only, no `is_online` clear) | 1244–1267 |
| — I-1 projected guard | 1283–1289 |
| — field writes | 1291–1298 |
| `set_driver_operational_status()` | 1350 |
| — ownership check | 1378–1381 |
| — `can_go_live` gate | 1385–1392 |
| — I-1 projected guard | 1400–1408 |
| — writes | 1410–1420 |
| `set_admin_online_override()` | 1436 |
| — decorators (no authorization decorator) | 1434–1442 |
| — blocked-state refusal | 1477–1483 |
| — metadata written (enable) | 1489–1494 |
| — forces `is_available=True` | 1495–1497 |
| — metadata written (disable) | 1499–1504 |
| — `is_available` revert | 1506 |
| — `flag_modified` | 1508–1509 |
| — flush + `can_go_live` re-check → forced offline | 1511–1515 |
| — audit row | 1517–1531 |
| — commit | 1533 |
| `get_available_drivers()` | 1743 |
| — "POOL SELECTOR, NOT A RANKER" | 1746–1761 |
| — "DO NOT add ORDER BY" | 1762–1765 |
| — "DO NOT cache this method" | 1767–1777 |
| — pool filters | 1782–1787 |
| — zone filter | 1789–1792 |
| — vehicle-class filter | 1794–1797 |
| — `LIMIT` | 1799 |
| — projection incl. nullable `vehicle_id` | 1813 |

### 12.5 Availability — `app/transport/services/availability_service.py`

| Symbol | Line |
|--------|------|
| Availability definition (docstring) | 5–14 |
| `_driver_engaged_elsewhere()` | 46–55 |
| `_vehicle_engaged_elsewhere()` | 58–66 |
| `_freshness_cutoff()` | 70–73 |
| `_available_vehicle_ids()` (**no caller**) | 76–108 |
| `available_by_class()` | 115 |
| — predicate | 141–152 |
| `_PLANNING_SPEED_KMH` | 174 |
| `nearest_eta_minutes_for_class()` | 177 |
| — predicate | 211–224 |
| — ETA computation | 244–246 |

### 12.6 Matching — `app/transport/services/matching_service.py`

| Symbol | Line |
|--------|------|
| `_rank_drivers_for_booking()` | 344 |
| freshness cutoff | 349 |
| geographic matchability contract | 357–372 |
| distance bands | 376–389 |
| vehicle-class scoring | 391–398 |
| rating term | 401 |
| acceptance-rate term | 404 |
| service-type term | 406–409 |
| ETA heuristic | 411–415 |
| **`score >= 40` threshold** | 418 |
| sort descending | 423 |
| `_coordinates_or_none()` | 427–440 |
| `_calculate_distance()` | 443–460 |

### 12.7 Tracking — `app/transport/services/tracking_service.py`

| Symbol | Line |
|--------|------|
| **`LOCATION_TTL_SECONDS = 300`** | 26 |
| `update_location()` | 30 |
| `location_updated_at` write | 95 |
| `get_nearby_drivers()` | 434 |
| — cutoff | 445 |
| — filters (`is_online`, `is_available` only) | 448–451 |
| — staleness skip | 454–456 |
| — hard cap of 50 | 451 |

### 12.8 API — `app/transport/api/`

| Symbol | File:Line |
|--------|-----------|
| `DriverDetailResource` | `driver_routes.py:122` |
| — admin `PUT` updatable fields (incl. both flags) | `driver_routes.py:170–175` |
| — I-1 projected guard | `driver_routes.py:176–184` |
| — field application loop | `driver_routes.py:185–187` |
| — `DELETE` clears both flags (correct I-1 pattern) | `driver_routes.py:201–217`, esp. `:207–208` |
| `DriverVerificationResource.update_compliance` (no `is_online` clear) | `driver_routes.py:220`, `:246–247` |
| `DriverOfferAcceptResource` | `driver_routes.py:415` |
| — vehicle gate before accept | `driver_routes.py:433–438` |
| — offer CAS | `driver_routes.py:442` |
| — canonical claim | `driver_routes.py:452–458` |
| — claim failure path | `driver_routes.py:459–465` |
| `DriverStatusResource` | `driver_routes.py:653` |
| — ownership / admin check | `driver_routes.py:691–696` |
| — I-1 projected guard | `driver_routes.py:710–720` |
| — `can_go_live` gate → 403 + checklist | `driver_routes.py:722–731` |
| — service delegation | `driver_routes.py:733–740` |
| `DriverVehicleSwitchResource` | `driver_routes.py:763` |
| — `can_go_live` use | `driver_routes.py:829` |
| — canonical vehicle switch write | `driver_routes.py:871–887` |
| `DriverAdminOnlineOverrideResource` | `driver_routes.py:913` |
| — `@transport_admin_required` | `driver_routes.py:923` |
| — `has_global_role` check | `driver_routes.py:932–933` |
| — `enabled` required | `driver_routes.py:936–938` |
| — reason truncation | `driver_routes.py:940` |
| — service call | `driver_routes.py:943–948` |
| — error mapping (404 / 422 / 500) | `driver_routes.py:950–960` |
| route registration: go-live status | `routes.py:121–123` |
| route registration: admin online override | `routes.py:132–133` |
| `VehicleAssignmentResource.post` | `vehicle_routes.py:411` |
| — driver lookup (no compliance check) | `vehicle_routes.py:432–436` |
| — canonical assign | `vehicle_routes.py:438–445` |
| — unassign | `vehicle_routes.py:462–468` |
| `ScheduledRouteAssignmentResource.post` | `route_routes.py:273` |
| — driver lookup on `is_available` only | `route_routes.py:293–302` |
| — vehicle lookup | `route_routes.py:304–323` |
| dashboard counters | `dashboard_routes.py:52`, `:56`, `:70` |
| analytics counters | `analytic_routes.py:101`, `:111` |
| org driver listing `is_online` filter | `organisation_routes.py:65`, `:121`, `:208`, `:278` |

### 12.9 Web routes and templates

| Symbol | File:Line |
|--------|-----------|
| `api_availability` (uses `available_by_class`) | `app/transport/routes.py:310–317` |
| `approve_driver` | `app/transport/routes.py:2797–2823`, esp. `:2804` |
| `reject_driver` | `app/transport/routes.py:2826–2852`, esp. `:2833` |
| `admin_driver_detail` (override read) | `app/transport/routes.py:2855–2876`, esp. `:2867–2869` |
| admin override control card | `templates/transport/admin/driver_detail.html:66–127` |
| — override detail display | `templates/transport/admin/driver_detail.html:78–85` |
| — documented bypass / absolute / audit statement | `templates/transport/admin/driver_detail.html:94–106` |
| — reason field + client-side requirement | `templates/transport/admin/driver_detail.html:109–114`, `:142–145` |
| — confirm dialog | `templates/transport/admin/driver_detail.html:146` |
| — POST with CSRF token | `templates/transport/admin/driver_detail.html:154–161` |
| moderator suspend writes `is_available=False` only | `app/admin/moderator/routes.py:3594–3609`, esp. `:3601–3602` |

### 12.10 Auth / KYC

| Symbol | File:Line |
|--------|-----------|
| `_BLOCKED_DRIVER_STATES` | `app/auth/context.py:104` |
| workspace gate use | `app/auth/context.py:502` |
| `driver_go_live_kyc_qualified()` (fail-closed) | `app/auth/kyc_compliance.py:860–879` |
| `DRIVER_GO_LIVE_MIN_KYC_TIER` reference | `app/auth/kyc_compliance.py:871` |

### 12.11 Marketplace — `app/transport/services/marketplace_service.py`

| Symbol | Line |
|--------|------|
| `VehicleMarketplaceService` class | 36 |
| `_check_driver_eligibility()` | 322–380 |
| `approve_application()` | 460 |
| `terminate_contract()` | 584 |
| — `ACTIVE` check | 616 |
| `get_driver_contracts()` (orders, never filters, by `start_date`) | 628, `:639` |
| `get_owner_contracts()` (same) | 641, `:652` |
| `accept_contract_terms()` | 669–701 |
| — `PENDING_SIGNATURE` requirement | 697–698 |
| `_activate_contract()` | 703–737 |
| — sets `ACTIVE` + `start_date` | 709–710 |
| — `assign_driver_to_vehicle` in `try` | 713–727 |
| — `except` swallows failure | 731–734 |
| — commits `ACTIVE` regardless | 736 |
| `search_listings()` (driver-side discovery) | 743 |
| `get_recommended_listings()` | 789 |
| `calculate_driver_earnings()` | 871 |

### 12.12 Tasks and CLI (non-authoritative writers)

| Symbol | File:Line |
|--------|-----------|
| `CLAIMABLE_STATUSES` consumed by recovery | `app/tasks/transport_recovery.py:97–101`, `:309`, `:365` |
| trip transition delegates to `release` | `app/transport/services/booking_service.py:708–730` |
| CLI writes `is_online=False` / `is_available=False` | `app/transport/cli_driver.py:330–331` |
| CLI inserts `DriverVehicleHistory` directly | `app/transport/cli_driver.py:405` |
| seed writes both flags true | `scripts/seed_transport_driver.py:42–43`, `:56–57` |

### 12.13 Tests

| File | Lines |
|------|-------|
| `tests/transport/test_supply00_override.py` | T1 `:88`, T2 `:134`, T3 `:162`, T4 `:211`, T5 `:252`, T6 `:280`, T7 `:305`, T8 `:356`, T9 `:402`, T10 `:442`, T11 `:481`, T12 `:516`, T13 `:545`, T14 `:581`, T15 `:614` |
| `tests/transport/test_assignment_release_supply_invariant.py` | `:65`, `:94` |
| `tests/test_transport_concurrent_claim.py` | `:253`, `:297`, `:339`, `:382`, `:400`, `:438`, `:488`, `:502`, `:522`, `:539`, `:869`, `:891`, `:909`, `:930` |
| `tests/transport/test_marketplace_operational_flow.py` | `:280–281`, `:328–330` |
| `tests/test_transport_geographic_contract.py` | `:274` (fixture) |
| `tests/test_transport_ride_options.py` | `:86` (fixture) |

---

## 13. Register cross-reference

| Register row | This contract | State |
|--------------|---------------|-------|
| SUPPLY-00 | §1 I-1, I-2, I-6; §3.2; §6 | GREEN — semantics recorded here |
| SUPPLY-01 | §1 I-2 | CLOSED / superseded — driver-restore predicate removed |
| SUPPLY-02 | §2.4 item 4; §7.1 | DESIGN READY |
| SUPPLY-03 | §7.2 | DESIGN READY |
| SUPPLY-04 | §2.4 item 3; §7.3 | DESIGN READY |
| SUPPLY-05 | §1 I-1 (admin PUT guard) | CLOSED |
| SUPPLY-IDEMPOTENCY | — (out of scope) | CLOSED |
| SUPPLY-Q3 | §3.3 vehicle gate (conditional on service type) | DECIDED |
| C6 | §4.2, §4.3 item 1 | OPEN |
| C7 | §8.3 | OPEN |
| C8 | §6.5 | OPEN |
| D5 | §1 I-3 | CLOSED |
| D8 | §8.3 | DECISION |
| D3-b2 | §8.3; GAP-04 | PROPOSED |

New rows this contract proposes for the human's consideration: **GAP-01 … GAP-12** (§7.5, §7.6). The agent does not write them to the register.

---

## 14. Assumptions flagged by the author

1. **File name deviates from the OS convention.** OS §3 specifies `docs/transport/nodes/<node-id>-contract.md`. The instructed path is `docs/transport/nodes/SUPPLY-ELIGIBILITY-v1.md` with no `-contract` suffix. Followed the instruction; created no second file. The human may rename at will.
2. **The agent wrote a contract-shaped document.** OS §18 states the contract is the human's. This document was produced by the agent under direct instruction as an *architectural control specification*, not as an acceptance-criteria contract. It therefore grades nothing and approves nothing. §8 is deliberately left as open questions rather than proposed answers.
3. **`_BLOCKED_DRIVER_STATES` is treated as the canonical blocked vocabulary** because `go_live_service` imports it from `app.auth.context` (`app/transport/services/go_live_service.py:105`). `provider_service.py:1478` re-hardcodes the same three strings rather than importing the constant — consistent today, a divergence risk if the set ever grows.
4. **`score ≥ 40` is treated as part of MATCHABLE** per the task statement. In code it is a ranker threshold (`app/transport/services/matching_service.py:418`), not a pool predicate; the two are distinguished throughout.
5. **`VehicleContract` expiry is assumed never to run.** No date comparison exists in code; the conclusion rests on exhaustive read of `marketplace_service.py`, not on a scheduler search — a Celery task could in principle exist elsewhere. Recorded as a gap, not a proven absence of a sweeper.
6. **Register contents are quoted from `fine tuning transport.md`** as of its current state. The agent did not modify it.