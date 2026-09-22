# AFCON360 — Transport Dashboard Preservation & Capability Inventory

**Status:** DURABLE PROJECT STATE — Phase A (read-only inventory) + Phase C
(Driver Workspace Home consolidation, implemented 2026-09-18) of the EGGE Master
Node ("Transport Dashboard Preservation + Full Driver/Admin Consolidation").
**Type:** Phases A/B are READ-ONLY. Phase C is a presentation/routing
implementation (no new backend, no schema, no migrations) — see §11.
**Last Updated:** 2026-09-18
**Governing node:** root `AGENTS.md` §5 (scope), §17 (ownership), §6 (spec law),
§34 (prohibited actions), §12.1 (dual ID), §28 (module toggles).

> **Contract note.** The named durable record
> `AFCON360_Transport_Dashboard_Preservation_and_Architecture_Contract.md`
> **now exists at the repository root** (311 lines, dated 2026-09-18). It was
> absent during Phase A (recorded as BACKLOG `EGGE-PRES-1`), so Phase A used
> this document as the interim preservation record. Both documents are now
> authoritative for transport dashboard work; they remain supplementary to the
> root constitution, never a replacement.

---

## 0. Non-Destructive Preservation Rule

Nothing existing may be lost. Do not delete routes, templates, services, APIs,
models, JS, CSS, tests, or working functionality. A component may be retired
ONLY after: (1) ownership proven, (2) consumers identified, (3) behavior
captured, (4) equivalent functionality proven to survive, (5) explicit
authorization. Duplication is preferable to accidental loss until consolidation
is proven safe. This node is **not** a cleanup node.

---

## 1. Three Surfaces + Universal Dashboard

| Surface | Shell (base template) | Entry | Actor | Auth boundary |
|---|---|---|---|---|
| **A. Driver Workspace** | `templates/transport/driver/base.html` (exists, 174 lines) | `transport.driver_dashboard` (`/transport/driver-dashboard`), `driver_dashboard_slash` (`/transport/driver/dashboard`) | authenticated user with **active DRIVER context** (and not blocked/suspended/revoked) | `@login_required` + `@active_context_required(ContextType.DRIVER)` (`app/auth/context.py:754`); backend `get_driver_profile()` resolves by `current_user.id` |
| **B. Transport Admin / Operations** | `templates/transport/base.html` (exists) + `templates/transport/admin/dashboard.html` | `transport_admin.dashboard` (`/transport/admin/dashboard`), `transport.dashboard_overview` (`/transport/dashboard`, `/transport/dashboard/overview`) | authorized transport administrator/operator | manual `has_global_role('admin') or is_super_admin()` in body of `transport_admin.dashboard`; `@admin_required` on the locked `/transport/drivers*` surfaces; `@require_role("transport_admin")` on `app/admin/route_modules/transport_admin.py` family |
| **C. Organisation / Fleet** | `templates/org/transport.html` | `org.transport` (`/org/<org_id>/transport`, `app/identity/routes.py:847`) | organisation member with `org.transport.manage` | `_require_org_permission` (identity routes:136) + organisation context |
| **Universal dashboard** | user's general AFCON360 home | links to Role Workspaces | any authoritative user | delegates by context/role. Transport Admin MUST NOT become the universal personal dashboard (§15). |

---

## 2. Shell contents (Phase B confirmation)

### A. Driver shell — `templates/transport/driver/base.html`
> This section records the Phase B (pre-Phase-C) state. See **§11** for the
> Phase C consolidated Driver Workspace Home and the updated nav labels
> (TODAY / MY TRANSPORT; "My Vehicles" → `transport.vehicle_dashboard`).
- Nav items (only 3): **Overview** → `transport.driver_dashboard`;
  **My Vehicle** → `transport.vehicle_dashboard`;
  **Register Vehicle** → `transport.register_vehicle`.
- Loads `css/modules/transport/base.css` (exists), `js/modules/transport/base.js`
  (exists), `js/global/theme-manager.js` (exists), and
  **`static/transport/js/utils.js` (MISSING → browser 404, non-fatal)**.
- Renders no admin/operations nav (intended separation). Shares pane-mode (`?_pane=1`).
- Current nav does NOT surface: online/offline & Go Live, trips/assignments,
  offers, schedule/availability, earnings, history, settings, inbox/support/safety.

### B. Operations shell — `templates/transport/base.html`
- Contains the platform transport operations nav. (See route inventory §3.)

### Legacy role-aware shell — `templates/transport/dashboard/base_dashboard.html`
- Complete legacy shell with a Driver branch and a Platform-Admin branch. Orphan
  in part (`dashboard/index.html`, `dashboard/keep.html` also orphaned).
- References missing assets. **Preserve; reuse selectively. Do not delete. Do not
  promote to canonical without authorization.**

---

## 3. Route inventory (condensed; full tables held in the node's agent evidence)

Six HTML blueprints + one REST blueprint.

| Blueprint | File | Prefix | Registered |
|---|---|---|---|
| `transport_bp` (~66 routes) | `app/transport/__init__.py:13-19` | `/transport` | `app/__init__.py:1135-1138` |
| `transport_admin_bp` (14) | `app/transport/__init__.py:21-26` | `/transport/admin` | same block |
| `admin_bp` transport module (14) | `app/admin/route_modules/transport_admin.py` | `/admin/transport-admin` | `app/admin/__init__.py:103` |
| `admin_bp` settings (2) | `app/admin/routes.py:1233,1271` | `/admin/...` | via `admin_bp` |
| `moderator_bp` transport (9) | `app/admin/moderator/routes.py:3139-3551` | `/admin/moderator/transport*` | via `admin_bp` |
| `org_bp` fleet (1) | `app/identity/routes.py:847` | `/org/<org_id>/transport` | `app/__init__.py:1077-1086` |
| `transport_api` (40 REST resources, 67 methods) | `app/transport/api/__init__.py:24` | `/api/transport` | inside `create_app` → `init_transport_module` |

### Auth posture (HTML)
- `@module_enabled_required("transport")` on most `transport_bp` routes (73 guard sites total).
- **`moderate*` routes (`/transport/moderate*`) have NO module guard** (reachable when transport disabled).
- `org.transport` has no module guard (relies on org permission).

### Auth posture (REST)
- 53 methods `@admin_required`, 13 `@login_required`, 1 **no decorator**
  (`POST /api/transport/incidents`, `incident_routes.py:102`).
- **REST API is NOT module-gated** (path check keys on first segment `api`).

---

## 4. Broken authorization guard — `transport.role_required`

`app/transport/decorator.py:52-65` compares `role_name not in getattr(current_user, 'roles', [])`,
but `User.roles` (`app/identity/models/user.py:163`) is a relationship of `UserRole`
ORM objects → the string can never match → **deny-by-design**. Affected routes
(all `@role_required(...)` in `app/transport/routes.py`):
`incidents_investigate`, `organisations_new`, `routes_new`, `settings_index`,
`organisation_dashboard`, and all 14 `transport_admin_bp` routes except the
unguarded `transport_admin.dashboard`. Repair is a BEHAVIORAL change and needs its
own authorized node. `app/transport/decorator.py:70-81 rate_limit` is a **no-op**
(real limiter: `app/auth/decorators.py:575`).

---

## 5. Capability reuse map (Driver)

| Capability | Existing implementation | Class | Reuse target |
|---|---|---|---|
| Home / online-offline state | `driver_dashboard` (`routes.py:1098`) + `DriverProfile.is_online/is_available` | EXISTS — adapt presentation | Driver shell nav |
| Go Live readiness | `go_live_service.can_go_live` (`go_live_service.py:98`) composing KYC + blocked-state + compliance + licence (+own vehicle for ON_DEMAND) | EXISTS — reuse directly | Driver Home |
| Go Live toggle | REST `DriverStatusResource` (`/api/transport/drivers/<id>/status`, `driver_routes.py:601`) + `set_driver_operational_status` | EXISTS — reuse directly | Driver Home |
| Current/upcoming assignments | `DriverProfile.current_assignment` (`models.py:406`); `driver_bookings` via `booking_service`; `DriverTripResource` (`/me/trips/<id>/status`) | EXISTS — reuse directly | Trips |
| Assigned vehicle | `provider_service.get_driver_vehicle` (`:478`, via `DriverProfile.current_vehicle`) | EXISTS — reuse directly | Trips |
| My (owned) vehicles | `provider_service.get_user_vehicles` (`:521`, `Vehicle.owner_type='driver'`, `owner_id=DriverProfile.id`) | EXISTS — reuse directly | My Vehicle (owner semantics preserved) |
| Register vehicle | web `register_vehicle` (`routes.py:1168`), REST `register_vehicle_internal`/`register_vehicle` | EXISTS — reuse directly | My Vehicle |
| Vehicle dashboard | web `vehicle_dashboard` (`routes.py:1277`, KYC≥3) | EXISTS — adapt presentation | My Vehicle |
| Trip offers | `offer_service`, `matching_service`, `DriverOfferListResource` (`/me/offers`), accept/decline, `tasks/transport_recovery.py` | EXISTS — reuse directly | Trips / Offers |
| Schedule / availability | No dedicated model surfaced; availability = `is_online`/`is_available` flags; reservations exist separately | **PARTIAL — gap** | Record; do not invent |
| Earnings | `dashboard_service.get_driver_earnings` (tested in `test_transport_service_integrity.py` `TestDashboardDriverMethods`) | EXISTS (backend) — needs UI | Driver Home |
| Trip history | `DriverHistoryResource` (`/drivers/<id>/history`) is **admin-only**; `transport.drivers_history` endpoint **does not exist** | **PARTIAL — gap + defect** | Record (D-WORKSPACE-2) |
| Recipient history | `app/identity/routes.py:379`, `org.py:331` read `LedgerRepository().get_balance(...)` (wallet-owned; transport pays via booking_service) | EXISTS (read-only) | Earnings |
| Documents / compliance | `DriverProfile.compliance_status`, verification tier, `DriverVerificationResource` (admin) | EXISTS — reuse | Requirements |
| Profile | `DriverProfile` (`models.py:239`), web `drivers_show` (now admin-locked) | EXISTS — reuse; driver self-view gap | Profile |
| Inbox / support / safety | `Rating` (`models.py:1360`, safety review `:1419`), `TransportIncident`, notification service (`notification_service.py`), shared `components/notification_bell.html` | EXISTS — reuse shared infra | Home / Support |
| Driver settings | none transport-specific surfaced | **MISSING — record only** | Settings |

## 6. Capability reuse map (Admin / Operations)

| Capability | Existing implementation | Class | Reuse target |
|---|---|---|---|
| Operations overview | REST `/api/transport/dashboard/overview` (`dashboard_routes.py:41`, `@admin_required`), `dashboard_service`, `view_models.AdminDashboardViewModel` | EXISTS — reuse directly | Admin Home |
| Dashboard (HTML) | `transport_admin.dashboard` (`routes.py:1850`, works; has debug `print()`s) + `templates/transport/admin/dashboard.html` | EXISTS — reuse; remove debug prints in a later authorized change | Admin Home |
| Bookings | web `bookings_index/show/new/edit/timeline/payments`, REST `BookingList/Detail/Status/Assignment/Payment/Route`, `booking_service` | EXISTS (many web pages context-broken) | Bookings |
| Drivers roster + verify/approve | `/transport/admin/drivers*` (locked), `transport_admin.drivers_filter` (full ctx), REST `DriverList/Detail/Verification` | EXISTS — reuse; **keep `/transport/drivers*` admin lock** | Drivers |
| Vehicles registry | REST `VehicleList/Detail/Maintenance/Assignment`, web `vehicles_*` (ctx-broken) | EXISTS | Vehicles |
| Dispatch / assignment | `AssignmentService.claim/release`, `BookingAssignmentResource`, `DriverVehicleHistory`, `Booking.assigned_driver_id/assigned_vehicle_id` | EXISTS — reuse; do NOT build a second dispatch layer | Dispatch |
| Routes / scheduling | REST `ScheduledRoute*`, web `routes_*` (ctx-broken), `ScheduledRoute` model | EXISTS | Routes |
| Reservations | REST `Reservation*`, `reservation_service` (full state machine), `TransportReservation` | EXISTS | Bookings/Reservations |
| Organisations / fleets | REST `Organisation*` (admin-only), org fleet page `org.transport` | EXISTS — keep org workspace distinct | Organisations |
| Incidents | web `incidents_*`, REST `Incident*` (create is public) | EXISTS | Incidents |
| Analytics / reporting | REST `AnalyticsSummary/Revenue/Performance`, web `analytics_*` (some ctx-broken), `analytic_routes` direct SQL | EXISTS (web partly broken) | Analytics |
| Settings / config | REST `Settings*`, `settings_service`, `TransportSetting`, web `settings_index`/`admin_settings` (ctx-broken + broken gate) | EXISTS | Settings |
| Moderation | `moderate*` (no module guard) + `moderator_bp.transport_*` (healthy) | EXISTS — two independent systems | Moderation |

## 7. Broken capabilities — classified (do NOT silently fix in this node)

| Defect | Surface | Class |
|---|---|---|
| `transport.drivers_history` endpoint missing (driver "Trip History" dead link, `driver_dashboard.html:192`) | Driver | Driver — Phase C removed the dead link from Driver Home; endpoint/presentation gap remains (PHASE-C-2) |
| `drivers_verification` / `drivers_location` pass only `id=` → context mismatch (`routes.py:1077/1087`) | Admin | Admin |
| Assigned driver cannot open booking detail via booker-ownership path | Driver | Driver — Phase C removed the dead per-assignment detail link; access-rule fix deferred (PHASE-C-2) |
| `vehicle_dashboard` / `register_vehicle` lack DRIVER active-context gate | Driver | Driver — Phase C deliberate non-change (cross-context consumers); needs decision (PHASE-C-1) |
| Organisation vehicle ownership authorization needs separate review | Org/Fleet | Organisation/Fleet |
| Missing `datetimeformat`/`dateformat` filters (shared) | Shared | Shared infrastructure |
| Missing transport static assets (`static/transport/**`, incl. `js/utils.js`) | Shared | Shared infrastructure |
| `transport.role_required` deny-by-design (§4) | Admin | Admin (authz) |
| `transport.rate_limit` no-op | Shared | Shared infrastructure |
| `service_detail` renders missing template → 500 | Public | Admin/Public |
| `transport_admin_bp` 4 missing templates; `admin/transport_admin/*` 9 missing templates | Admin | Admin |
| `transport.organisation_dashboard` missing singular template (`routes.py:1500`) | Admin | Admin |
| ctx-broken render pages (bookings/vehicles/incidents/routes/analytics/settings + `*_edit/location/verification`) | Admin | Admin |
| Missing endpoints referenced by templates: `transport.booking_assign`, `transport.api_*`, `transport.restart`, `transport.audit_log`, `transport.drivers_create`, `transport.driver_update` | Admin | Admin |
| Missing API endpoints: `/analytics/export`, `/bookings/export`, `/drivers/<id>/toggle-online`, `/drivers/<id>/compliance` | Admin | Admin |
| `GET /transport/drivers/new` 500 for admin (BACKLOG D-ADMIN-1) | Admin | Admin |
| Flask-RESTful anonymous 401→500 (Defect B; two `test_transport_restful_auth.py` failures) | Shared | Shared infrastructure |
| `provider_service.py:853` sets `vehicle.current_driver_id` (no such column) — latent AttributeError | Shared | Separate future node |
| `TransportPermission` extends plain `db.Model`, not `BaseModel` (§13 candidate) | Org/Fleet | Organisation/Fleet |
| `booking_service.get_user_bookings` serializes internal `b.id` (§12.1) | Shared | Separate future node |
| `app/tasks/transport_permission_purge.py` has no Celery decorators | Org/Fleet | Separate future node |

## 8. Proof matrix (anti-loss)

| Capability | Existing implementation | Driver | Admin | Org/Fleet | Reused | Status |
|---|---|---|---|---|---|---|
| Driver home / status | `driver_dashboard` + `DriverProfile` | ✓ | — | — | ✓ | EXISTS — adapt |
| Go Live readiness/toggle | `go_live_service.can_go_live`, REST status | ✓ | ✓ | — | ✓ | EXISTS — reuse |
| Current/upcoming trips | `current_assignment`, `booking_service` | ✓ | ✓ | — | ✓ | EXISTS — reuse |
| Owned vehicles | `get_user_vehicles` | ✓ | ✓ | — | ✓ | EXISTS — reuse |
| Assigned vehicle | `get_driver_vehicle`/`current_vehicle` | ✓ | ✓ | — | ✓ | EXISTS — reuse |
| Register vehicle | web + REST | ✓ | ✓ | — | ✓ | EXISTS — reuse |
| Trip offers | `offer_service`/`matching_service`/REST | ✓ | — | — | ✓ | EXISTS — reuse |
| Availability / schedule | flags + reservations | ✓ | ✓ | ✓ | partial | PARTIAL — gap |
| Earnings | `dashboard_service.get_driver_earnings` | ✓ | ✓ | ✓ | ✓ | EXISTS — needs UI |
| Trip history | admin REST + missing endpoint | — | ✓ | — | partial | PARTIAL + defect |
| Documents/compliance | `DriverProfile`, verification | ✓ | ✓ | — | ✓ | EXISTS — reuse |
| Inbox/support/safety | notifications, `Rating`, incidents | ✓ | ✓ | ✓ | ✓ | EXISTS — reuse |
| Driver settings | — | — | — | — | — | MISSING — record |
| Operations overview | REST dashboard + HTMl dashboard | — | ✓ | — | ✓ | EXISTS — reuse |
| Bookings | web + REST + service | — | ✓ | ✓(reservations) | ✓ | EXISTS |
| Drivers roster | locked `/transport/drivers*` + REST | — | ✓ | — | ✓ | EXISTS |
| Vehicles registry | REST + web | — | ✓ | ✓(org) | ✓ | EXISTS |
| Dispatch/assignment | `AssignmentService` | ✓(accept) | ✓ | — | ✓ | EXISTS — reuse |
| Routes/schedules | REST + web | — | ✓ | — | ✓ | EXISTS |
| Reservations | REST + `reservation_service` | — | ✓ | ✓ | ✓ | EXISTS |
| Organisations/fleets | REST admin + `org.transport` | — | ✓ | ✓ | ✓ | EXISTS |
| Incidents | web + REST | ✓(report) | ✓ | — | ✓ | EXISTS |
| Analytics/reporting | REST + web | — | ✓ | ✓ | ✓ | EXISTS (web partial) |
| Settings/config | REST + `settings_service` | — | ✓ | — | ✓ | EXISTS (web partial) |
| Moderation | `moderate*` + `moderator_bp` | — | ✓ | — | ✓ | EXISTS |

## 9. Implementation order (contract)

- **Phase A** — this inventory. READ-ONLY. **DONE.**
- **Phase B** — confirm shells/relationships (§1–2). **DONE (analysis).**
- **Phase C** — consolidate existing driver-facing capability into the Driver shell (presentation/routing only; no new backend). **DONE — Driver Home consolidation (see §11).** Trips/Offers/history/settings UI remain recorded gaps.
- **Phase D** — consolidate existing admin/operations capability into the Admin dashboard (presentation/routing only).
- **Phase E** — cross-surface links point to the correct workspace.
- **Phase F** — verification (driver separation, admin, org scope, preservation).

Phases C–F require a separate authorized implementation node. This document must
be updated (not replaced) as each phase lands.

## 10. Out of scope (unchanged)

wallet · KYC · canonical identity · Go Live rules · vehicle verification
architecture · DB schema · migrations · RBAC seed architecture · event
architecture · accommodation architecture · transport ownership model · dispatch
domain model · payment architecture.

---

## 11. Phase C — Driver Workspace Home consolidation (IMPLEMENTED 2026-09-18)

**Node:** Phase C of the EGGE Master Node. **Mode:** IMPLEMENTATION.
**Classification:** BEHAVIORAL-adjacent presentation change with HIGH_RISK
preservation constraints. **Governing contract:** root
`AFCON360_Transport_Dashboard_Preservation_and_Architecture_Contract.md` +
this document.

### What changed (presentation-only; no new backend, no schema, no migrations)

| File | Change |
|---|---|
| `app/transport/routes.py` (`driver_dashboard`, ~:1094) | Enriched the view context **only** with reused services: `upcoming` (`get_driver_upcoming_bookings`), `recent` (`get_driver_recent_bookings`), `earnings` (`get_driver_earnings`), `owned_vehicles` (`get_user_vehicles`), `assigned_vehicle` (`DriverProfile.current_vehicle`). Existing `driver_profile` / `bookings` / `go_live` keys and the `@active_context_required(ContextType.DRIVER)` guard are unchanged. |
| `templates/transport/driver/driver_dashboard.html` | Consolidated Driver Home: hero + online toggle + stats + Go-Live checklist retained; added Current Assigned Vehicle, My (owned) Vehicles, Earnings, Upcoming Assignments, Recent Trips. Removed admin/dead links (`transport.drivers_verification`, `transport.drivers_location`, `transport.drivers_history`, booker-owned `transport.bookings_show`). My Vehicles now points to `transport.vehicle_dashboard` (NOT the global `transport.vehicles_index`). |
| `templates/transport/driver/base.html` | Nav section labels moved to **Today** / **My Transport**; same three real driver routes (`driver_dashboard`, `vehicle_dashboard`, `register_vehicle`). No new/fake nav items. |
| `tests/test_driver_workspace_consolidation.py` | New focused suite (12 tests): render, driver shell, no admin navigation, context gate (403 personal / allowed pending / denied blocked), no-toggle before go-live, owned-vs-assigned vehicle semantics, driver-surface links, go-live rule-set preservation. |

### Presentation adapter note

`Booking.to_dict()` serializes datetimes as ISO-8601 **strings** and omits the
internal `id` (dual-ID law). The template therefore formats trip time by
slicing the ISO string and does not call `.strftime()` or link by internal id.
This also fixes a latent render bug in the previous template.

### Deliberate non-change (recorded decision)

`vehicle_dashboard` / `register_vehicle` were **not** given
`@active_context_required(ContextType.DRIVER)` in Phase C. Contract §11 lists
the missing gate as a known finding to preserve, but evidence shows these routes
are NOT exclusively Driver surfaces:
`templates/events/service_provider/service_provider_dashboard.html:38` links
`transport.vehicle_dashboard`; `register_vehicle` is referenced from
`templates/transport/home.html`, `homes.html`, `vehicles/index.html`,
`vehicles/_form.html`, `dashboard/base_dashboard.html`, `dashboard/keep.html`.
Adding the gate now would 403 existing consumers → preservation violation.
Both routes already require a real driver flow (DriverProfile + KYC tier 3) via
their existing decorators. Recorded as **needs-decision** in BACKLOG.

### Preserved gaps (not fixed here)

Driver trip-history presentation, assigned-driver booking detail, offers/trips
web UI, availability/settings UI, and notifications remain recorded gaps —
see BACKLOG `D-WORKSPACE-2`, `D-WORKSPACE-3`, `EGGE-PRES-1` and the new Phase C
entries.

### Phase C verification (all green)

- `tests/test_driver_workspace_consolidation.py` — 12 passed
- `tests/test_driver_workspace_activation.py tests/test_canonical_identity_center.py` — 32 passed
- `tests/test_onboarding.py tests/test_auth_context.py` — 45 passed
- `create_app()` → `STARTUP_OK`; endpoint validator passed

---

## 12. Phase D0 — Transport Admin Authority Resolution

**Node:** Phase D0. **Mode:** IMPLEMENTATION (Gate 3) after a Gate 1 Discovery
report (`DISCOVERY GATE: PASS`) and a Gate 2 human authorization.
**Classification:** BEHAVIORAL / HIGH_RISK (identity + authorization surface),
scoped to the minimal change set. **No schema change, no migration.**

### 12.1 The contradiction resolved

Gate 1 proved that `transport_admin` — the canonical Transport-domain
global role — carried **zero** Transport permissions. The `/admin/transport-admin`
family was guarded by `require_role("transport_admin")`, whose only non-broken
path was the dynamic `TransportPermission` fallback, while all other Transport
admin surfaces keyed off `admin_required` (platform admin). Result: the role
that *should* own Transport admin authority was effectively powerless.

### 12.2 Gate 2 Decision (binding, user-issued)

1. Canonical Transport Admin role = `transport_admin` (Transport-domain
   authority only — NOT `admin`/`super_admin`/`owner`).
2. Canonical mechanism = the existing global permission system
   (`Permission` → `RolePermission` → `Role`, resolved by `can()` /
   `require_permission`). **Rejected:** `app/transport/decorator.py::role_required`
   and the dynamic `TransportPermission` fallback as canonical paths.
3. Map `transport_admin` → `transport.view` + `transport.manage`.
   `transport.settings` is intentionally **not** granted (owner/super_admin only).
   No new permission identifiers invented.
4. `owner`/`super_admin`/`admin` retain their existing Transport powers.
5. Route rule: read/dashboard → `transport.view`; mutate → `transport.manage`;
   settings → `transport.settings`.
6. Canonical entry point = `/admin/transport-admin` family; guard refactored
   from `require_role("transport_admin")` to permission-based authority.
7. Driver, Organisation (`org.transport.*`), and Moderator paths preserved
   unchanged; drivers must not gain Transport Admin authority.
8. Dynamic `TransportPermission` preserved-but-not-canonical; broken
   `transport.role_required` consumers preserved and deferred (no global repair).
9. Durable record: this section + BACKLOG. STOP-condition: if `transport.view` /
   `transport.manage` could not express the required authority without schema or
   a new architecture → `GATE=BLOCKED`. **Condition not hit.**

### 12.3 Implementation (minimal change)

| File | Change |
|---|---|
| `app/auth/seed_roles.py` | Added `transport_admin` to the role lists for `transport.view` and `transport.manage` only. `transport.settings` unchanged (owner/super_admin). Single source of truth for role→permission seeding. |
| `app/admin/route_modules/transport_admin.py` | Replaced all 14 `@require_role("transport_admin")` guards with `@require_permission(...)`: `transport.view` (dashboard, vehicles, drivers, bookings, organizations, analytics); `transport.manage` (create/edit/delete vehicle, verify/reject driver, approve/reject booking); `transport.settings` (settings). Removed the now-unused `require_role` import. `@active_context_or_platform_required(ContextType.PLATFORM)` on dashboard/vehicles preserved. |
| `tests/test_transport_admin_permission_authority.py` | New focused suite (11 tests) exercising the real seeded DB + HTTP path + `can()` resolver. |

### 12.4 Authority resolution (answers to the Gate 2 Required Test Contract)

| Question | Evidence |
|---|---|
| Does `transport_admin` obtain authority through the canonical permission system? | `Role.permission_names` contains `transport.view`/`transport.manage`; `can(user,"transport.view")` and `can(user,"transport.manage")` are `True`; HTTP reaches `/admin/transport-admin` and `/admin/transport-admin/drivers`. |
| Does `admin`/`super_admin`/`owner` retain access? | `test_platform_admin_retains_transport_access`, `test_owner_retains_transport_access` pass (owner bypass + unchanged role perms). |
| Ordinary user denied? | Yes — `/admin/transport-admin` denied (admin-blueprint 403 handler → redirect `/`). |
| Driver separation preserved? | Driver reaches `/transport/driver-dashboard` (200) and is denied `/admin/transport-admin`; drivers receive only `transport.driver`. |
| View vs manage distinction? | A view-only role can read but is denied mutation; `transport_admin` passes the mutation guard. |
| Role name alone confers authority? | No — a `transport_admin`-shaped role with no permission is denied; granting `transport.view` confers authority. |

### 12.5 Denial transport note (pre-existing behaviour)

Routes mounted on `admin_bp` convert `abort(403)` into a safe redirect to `/`
via `admin_bp.errorhandler(403)` (`app/admin/routes.py:2172`). Denial on the
`/admin/transport-admin` family is therefore observable as a 302 to `/` (never a
login bounce), not a raw 403. The D0 tests assert this explicitly. This handler
was **not** changed (out of scope).

### 12.6 Deferred (recorded, NOT implemented in D0)

- Broken `app/transport/decorator.py::role_required` consumers, including 13 of
  14 `/transport/admin/*` routes.
- Dynamic `TransportPermission` schema/design (duplicate `__table_args__`,
  not a `BaseModel`).
- Ungated login-only `/transport/*` web ops; REST `/api/transport` auth mix.
- Missing `templates/admin/transport_admin/` sub-templates; duplicate/legacy
  Transport admin shells.
- Fine-grained `transport.drivers.*` / `transport.vehicles.*` permissions.
- `/transport/drivers*` `@admin_required` (excludes `transport_admin`).

### 12.7 Phase D0 verification (all green)

- `tests/test_transport_admin_permission_authority.py` — 11 passed
- `tests/test_transport_drivers_admin_lock.py tests/test_transport_dashboard_overview.py tests/test_driver_workspace_consolidation.py tests/test_driver_workspace_activation.py` — 47 passed
- `create_app()` → `STARTUP_OK`; endpoint validator passed
- `GATE 4 (VERIFY): PASS` — no schema/migration required.

---

## 13. Phase C-1 — Vehicle Ownership & Management independence (IMPLEMENTED 2026-09-18)

**Node:** Phase C-1. **Mode:** IMPLEMENTATION. **Classification:** BEHAVIORAL /
HIGH_RISK (authorization surface) with preservation constraints.
**Governing contract:** root
`AFCON360_Transport_Dashboard_Preservation_and_Architecture_Contract.md` +
this document. **No schema change, no migration, no new model.**

### 13.1 The invariant established

Ownership, driver participation, assignment, dispatch, and organisation fleet
authority are **independent**. One human may simultaneously be a non-driver
personal owner, an approved driver, and an organisation member, and may own
vehicles in more than one of those capacities. Vehicle **assignment** never
creates **ownership** (assignment is open `DriverVehicleHistory` rows; ownership
is the polymorphic `Vehicle.owner_type` / `owner_id` pair).

Three ownership vocabularies are supported through the **existing** polymorphic
columns (no new columns, no new model, no migration):

| `owner_type` | `owner_id` resolves to | Meaning |
|---|---|---|
| `driver` | `DriverProfile.id` | owned through an approved driver profile |
| `user` | `User.id` | personal / non-driver owner |
| `organisation` | `Organisation.id` | organisation fleet |

`Vehicle.current_driver` and `DriverProfile.current_vehicle` remain **derived
`@property`** values (from open `DriverVehicleHistory` rows) — not persisted
columns.

### 13.2 Files changed

| File | Change |
|---|---|
| `app/transport/models.py` | Removed phantom writes to non-existent attributes (`driver.current_vehicle_id`, `vehicle.current_driver_id`) in `assign_driver_to_vehicle` and `handle_vehicle_breakdown`. Assignment now persists only through `DriverVehicleHistory`. |
| `app/transport/services/provider_service.py` | `get_user_vehicles` resolves **both** driver-owned (`owner_type='driver'` via the user's driver profiles) **and** personal (`owner_type='user'`, `owner_id=user.id`); removed the early `if not drivers: return []` that hid personal ownership. `register_vehicle_internal` no longer writes `vehicle.current_driver_id`. `register_vehicle` gained an `owner_type='user'` branch (validates the owning `User` exists, not soft-deleted). Removed the unseeded `@require_permission('vehicle:register')` decorator (dead RBAC). |
| `app/transport/routes.py` | `register_vehicle` route is now dual-track: an approved driver registers as `('driver', driver.id)`, otherwise the logged-in user registers as `('user', current_user.id)` (instead of rejecting non-drivers). `_require_vehicle_ownership` extended: `owner_type='user'` branch (owner is `current_user`) and `owner_type='organisation'` branch using the **canonical** `org.transport.manage` permission. `vehicles_edit` now enforces ownership (JSON 404 / non-JSON re-raise). |
| `app/utils/monitoring.py` | `MonitorContext` (returned by `start_span()`) gained an additive span-compatible API: `set_status`, `set_attribute`, `end`. |
| `tests/test_phase_c1_vehicle_ownership.py` | New focused suite (30 tests across ownership multiplicity, assignment semantics, organisation fleet authority, cross-owner route access, registration route, vehicle dashboard surface). |
| `tests/test_stage4b5_transport.py` | Reconciled the two superseded `get_user_vehicles` tests + module docstring to the expanded driver-or-user ownership vocabulary. |

### 13.3 Dead-permission and root-cause defects fixed

1. **Dead RBAC permission.** `@require_permission('vehicle:register')` on
   `ProviderService.register_vehicle` was unseeded — no role holds it, so the
   path was unreachable. Removed; `@monitor_endpoint` + `@rate_limit` retained.
2. **Wrong organisation permission.** The canonical org transport permission is
   **`org.transport.manage`**. `OrganizationPermissionService.can_manage_transport`
   checks the dead `org.manage_transport`, which no seeded org role holds.
   `_require_vehicle_ownership` now resolves via
   `OrganizationPermissionService.has_permission(current_user, org,
   'org.transport.manage')` — mirroring `identity/routes.py` `_require_org_permission`.
3. **`validate_vehicle_registration` return contract.** The validator returns a
   `(is_valid, errors)` **tuple**; `register_vehicle_internal` indexed it as a
   dict (`validation_result['valid']`), raising `TypeError: tuple indices must
   be integers or slices, not str` (swallowed into `{'success': False}`). Fixed
   to tuple unpacking.
4. **`sanitize_input` expects a string.** `register_vehicle_internal` passed the
   whole `vehicle_data` **dict** to the string-only `sanitize_input`
   (`security.py:205`), masking registration with `AttributeError`. Now each
   string value is sanitized individually (non-strings preserved).
5. **`MonitorContext` span API.** `start_span()` returns `MonitorContext`, but
   transport services also call `span.set_status()` / `span.set_attribute()` /
   `span.end()`, raising `AttributeError`. Additive methods added — this repairs
   all transport `start_span` callers, not only vehicle registration.
6. **`vehicles_edit` HTML-render 500 (found by browser proof, affects ALL users
   including org managers).** The route rendered
   `transport/vehicles/edit.html` with only `id`, but the template requires
   `vehicle` (accesses `vehicle.license_plate` etc.) → Jinja `UndefinedError`
   → `500 INTERNAL SERVER ERROR`. Tests stayed green because they only exercised
   JSON (where the old context `{"status":"ok","id":id}` serialized fine) and
   403 paths. Fixed: after `_require_vehicle_ownership`, fetch
   `vehicle = get_provider_service().get_vehicle(id)` and pass `vehicle=vehicle`
   to the template (mirrors `vehicles_show`).
7. **`vehicles_edit` JSON must not serialize the ORM `Vehicle`.** Passing the
   model through `_json_or_template` put a non-serializable ORM object into
   `jsonify(...)` → 500 on `Accept: application/json` GET (the C-1 route tests
   assert exactly this). Fixed: the route now branches explicitly — JSON
   returns `{"status": "ok", "id": id}` (byte-for-byte the pre-fix payload),
   HTML renders the edit template with `vehicle`.

### 13.4 Deferred (recorded, NOT implemented in C-1)

- `provider_service.py:648` (`register_driver`) and ~`:1002`
  (`register_organisation_transport`) carry the **same two defect classes**
  already fixed for vehicle registration: dict passed to `sanitize_input` and
  tuple-vs-dict misuse of the validator result. See BACKLOG.
- `vehicles_show` swallows its own `abort(403)` (inside its `try`) → HTML
  redirects to `vehicles_index` (302) / JSON returns 404; cross-owner show is
  therefore not a hard 403. C-1 asserts `status != 200` for show and uses
  `vehicles_edit` for the hard-403 assertion. Recorded, not changed.
- `_json_or_template` on `vehicle_dashboard` / `vehicles_show` serializes ORM
  `Vehicle` objects when `Accept: application/json` → 500. Positive tests use
  HTML Accept. Recorded, not changed. (`vehicles_edit` was in this class too;
  it is now FIXED — see §13.3 item 7.)
- `TransportValidators.validate_vehicle_registration` accepts uppercase
  `vehicle_class` via `.upper()`, but `VehicleClass` enum **values are
  lowercase** and the real template emits lowercase. Latent case inconsistency
  (tests use lowercase per the UI contract). Recorded, not changed.

### 13.5 Phase C-1 verification (all green)

- `tests/test_phase_c1_vehicle_ownership.py tests/test_stage4b5_transport.py` — **30 passed**
- `tests/test_driver_workspace_consolidation.py tests/test_provider_participation.py` — **36 passed**
- `create_app()` → `STARTUP_OK`; endpoint validator passed
- **No schema change / no migration** (Decision A preserved)

### 13.6 Browser proof (2026-09-18, green)

Live proof server on `127.0.0.1:5055`, seeded test DB only
(`tests/conftest.py` bootstrap: `.env.testing`, `FLASK_ENV=testing`,
`DISABLE_REDIS=1`, `create_app(TestingConfig)`, `WTF_CSRF_ENABLED=False`).
Driver-less personal owner, approved driver, and org fleet are THREE separated
ownership surfaces.

| Actor (seeded) | Flow | Result |
|---|---|---|
| `pc1owner` (personal, non-driver) | `/transport/register-vehicle` real UI form → `PC1O-001` → dashboard | success toast "Vehicle registration submitted!", 1 vehicle, state Active/Available |
| `pc1owner` | `GET /transport/vehicles/148` (own show) + `/transport/vehicles/148/edit` | 200; `PC1O-001 — AFCON360`; edit form rendered with vehicle data |
| `pc1owner` | `GET /transport/vehicles/147/edit` (org vehicle) and `/149/edit` (driver vehicle) | **403 Forbidden** (ownership boundary) |
| `pc1owner` | `/transport/vehicle-dashboard` | **isolated**: shows ONLY `PC1O-001` (vehicle 148), never org 147 or driver 149 |
| `pc1driver` (approved driver) | register `PC1D-001` via same UI form | success, 1 vehicle (id 149) — driver-track `('driver', id)` |
| `pc1orgmgr` (org `transport_manager`) | `GET /transport/vehicles/147/edit` (org vehicle, canonical `org.transport.manage`) | **200**, edit form pre-filled with `ORGVF3F0` / Toyota Hiace / Van / 14 pax |

Screenshots (project root):
`proof_pc1_personal_owner_dashboard.png`,
`proof_pc1_driver_dashboard.png`,
`proof_pc1_org_manager_edit_org_vehicle.png`,
`proof_pc1_personal_owner_edit_own_vehicle.png`,
`proof_pc1_org_edit_final.png`.

Re-verified after the `vehicles_edit` fix: `tests/test_phase_c1_vehicle_ownership.py
tests/test_stage4b5_transport.py` → **30 passed**;
`tests/test_driver_workspace_consolidation.py
tests/test_provider_participation.py` → **36 passed**;
`create_app()` → STARTUP_OK. Launcher note: detached server children inherit
`CWD=C:\Windows\System32`, so the proof launcher `os.chdir(PROJECT_ROOT)` so
`.env` discovery and the DB URL load correctly (otherwise the fallback DB URL
produces `password authentication failed for user "israeli"`).

---

## 14. Phase D1 — Transport Admin / Operations capability discovery (DISCOVERY ONLY)

**Node:** Phase D1, GATE 1 DISCOVERY. **Mode:** EXPLORER / AUDIT (read-only).
**Classification:** BEHAVIORAL / ARCHITECTURAL discovery. **No application
code, template, CSS, JS, model, migration, or test was modified.**
**Application files changed: NONE** (this document + `BACKLOG.md` only).

### 14.1 Method + evidence standard

Evidence hierarchy used: runtime HTTP probe (`d1_probe*.py`, real seeded test
DB) > authoritative URL map (`app.url_map` dump) > live source
(route/decorator/service/model) > existing tests > docs. Confidence labels:
`PROVEN` (runtime or authoritative source), `SUPPORTED` (source with strong
context), `INDICATED` (partial/template-level), `UNKNOWN`.

### 14.2 Canonical route inventory (PROVEN — `app.url_map`)

- `transport.*` (web, blueprint `/transport`): ~70 rules — dashboard,
  bookings, passengers, drivers, vehicles, routes, incidents, organisations,
  analytics, moderate, register-vehicle, health, api/status, become-driver,
  driver/vehicle dashboards, `transport.static`.
- `transport_admin.*` (web, blueprint `/transport/admin`): 14 rules
  (`dashboard`, `list_bookings`, `cancel_booking`, `list_drivers`,
  `approve_driver`, `reject_driver`, `drivers_filter`, `admin_incidents`,
  `bookings_report`, `admin_routes`, `admin_settings`, `list_vehicles`,
  `approve_vehicle`, `reject_vehicle`).
- `admin.transport_admin_*` (web, blueprint `/admin/transport-admin`): 14
  rules — the D0 canonical family (`require_permission`).
- `admin.moderator.transport_*`: 9 rules under `/admin/moderator/transport`
  (guarded `@require_role(*_MOD)`; `app/admin/moderator/routes.py:3136-3414`).
- `transport_api.*` (REST, blueprint `/api/transport`): 40 endpoints
  (`app/transport/api/routes.py` logs "resources registered (40 endpoints)").
- Duplicate same-endpoint rules: `transport.dashboard_overview` is mapped to
  **both** `/transport/dashboard` and `/transport/dashboard/overview`.

### 14.3 Authorization map (PROVEN via runtime probes)

| Actor | `/transport/dashboard` | `/transport/bookings` | `/transport/analytics` | `/transport/incidents` | `/transport/organisations` | `/transport/routes` | `/transport/settings` |
|---|---|---|---|---|---|---|---|
| anonymous | 302 `/login` | — | — | — | 302 `/login` | — | — |
| ordinary (`user`) | **200** | **500** | 200 | **500** | 200 | 200 | 302 `/transport/` |
| `admin` | — | — | — | 500 | 200 | 200 | 302 `/transport/` |

| Actor | `/transport/drivers` | `/transport/admin/dashboard` | `/transport/admin/bookings` | `/admin/transport-admin` | `/admin/transport-admin/vehicles` |
|---|---|---|---|---|---|
| ordinary | 403 | 302 (self) | 302 `/transport/` | 302 `/` | 302 `/` |
| `transport_admin` | **403** | 302 (self) | 302 `/transport/` | 302 `/admin/dashboard`* | 302 `/admin/transport-admin` |
| `admin` | **200** | 302 (self) | 302 `/transport/` | 200† | 200 / redirect |

`*` Test-DB-only: `TransportPermission.get_active_by_user()` raises
`UndefinedTable: relation "transport_permissions" does not exist` because the
`TransportPermission(db.Model)` module is imported lazily and is therefore not
in `db.metadata` at `db.create_all()` bootstrap. A migrated DB has the table
via `migrations/versions/b73d33d073e1_add_transport_permissions_table.py`
(INDICATED, not runtime-verified here).
`†` D0 test-verified.

REST parity (ordinary vs `admin`): dashboard/overview 403/200, bookings 403/—,
analytics/summary 403/200. **`GET /api/transport/settings` → ordinary `200`
(`@login_required` only)** and **`POST /api/transport/incidents` has no
decorator** (anonymous POST reached the handler → 400 validation, no auth
gate). Anonymous access to REST routes bearing Flask-RESTful `@login_required`
returns **500** (known `BACKLOG.md:1584`).

### 14.4 Runtime-proven broken surfaces (GATE 1 findings)

1. **`datetimeformat` Jinja filter is never registered.** Zero `.py` matches
   repo-wide (only `format_number` is registered, `app/__init__.py:1685`),
   yet four transport templates use it: `templates/transport/bookings/index.html:110`,
   `bookings/show.html:60,122,126,187,216-237`, `incidents/index.html:12,147`,
   `routes/index.html:54`. Runtime: `GET /transport/bookings` → **500**
   `TemplateAssertionError: No filter named 'datetimeformat'`; `GET
   /transport/incidents` → **500** (same).
2. **`/transport/admin/dashboard` is a self-redirect loop.** `dashboard()`
   (`app/transport/routes.py:1915-2008`) debug-prints an emoji (`:1924`);
   on Windows cp1252 stdout `print` raises `UnicodeEncodeError`, caught by the
   broad `except` (`:2004`) → `redirect(url_for("transport_admin.dashboard"))`
   (`:2008`) = redirect to itself. Runtime: 302 `Location:
   /transport/admin/dashboard` for ordinary, `transport_admin`, and `admin`.
3. **13 of 14 `/transport/admin/*` routes deny everyone** (broken
   `transport.role_required`), including `admin` and `transport_admin`; all
   302 → `/transport/`. Reinforces `PHASE-D0-2`.
4. **Dangling endpoint** `transport_admin.admin_dashboard` referenced at
   `app/transport/routes.py:1903` and `:1909` (only `transport_admin.dashboard`
   exists) → `BuildError` if those except-paths execute.
5. **Dangling template endpoint refs** in `templates/transport/dashboard/keep.html`:
   `transport_admin.incidents` (real: `admin_incidents`),
   `transport_admin.routes` (real: `admin_routes`), `transport_admin.settings`
   (real: `admin_settings`).
6. **Missing route for existing templates:** `/transport/analytics/drivers`,
   `/transport/analytics/vehicles`, `/transport/analytics/history` → **404**
   although `templates/transport/analytics/{drivers,vehicles,history}.html`
   exist; `/transport/analytics/performance` and `/analytics/revenue` are 200.
7. **Missing template endpoints** (NOT FOUND IN URL MAP): `transport.driver_update`,
   `transport.drivers_create`, `transport.driver_history`,
   `transport.drivers_history`, `transport.booking_assign`.
8. **Broken static asset paths:** `templates/transport/dashboard/base_dashboard.html`
   and `keep.html` load `static/transport/css/*` + `static/transport/js/*`
   (do not exist — assets live under `static/css/modules/transport/` and
   `static/js/modules/transport/`); `transport/base.html:183` and
   `driver/base.html:156` load `transport/js/utils.js` (missing).
9. **`templates/admin/transport_admin/` sub-directory does not exist** (only
   `templates/admin/transport_admin_dashboard.html`); every D0 sub-route
   (`vehicles`, `analytics`, `settings`, …) therefore renders a missing
   template and redirects. `transport_admin_analytics` also calls a nonexistent
   `DashboardService.get_analytics_data()` (`app/admin/route_modules/transport_admin.py:451`).
   Reinforces `PHASE-D0-5`.

### 14.5 Correction to a prior assumption

Transport's **own** `NotificationService`
(`app/transport/services/notification_service.py`) is **not** call-free: it is
imported and invoked by `app/wallet/services/wallet_notifications.py:52-53`
and `:69-70` (`send_email`). No transport-module code calls it. The durable
notification path is `app/notifications/services.py`.

### 14.6 Duplicate / parallel surfaces (candidate consolidation scope — NOT authorized)

- Admin dashboards: `transport_admin.dashboard` (`/transport/admin/dashboard`,
  broken) vs `transport.dashboard_overview` (`/transport/dashboard`, 200,
  login-only) vs `transport.dashboard_performance`.
- Admin management: `/admin/transport-admin/*` (D0 canonical, permission-based)
  vs `/transport/admin/*` (broken) vs `/admin/moderator/transport/*` (moderator).
- Shells: `templates/transport/base.html` (ops shell) vs
  `templates/transport/dashboard/base_dashboard.html` + `keep.html` (legacy
  role-aware, broken asset paths) vs `templates/transport/driver/base.html`
  (driver) vs `templates/admin/transport_admin_dashboard.html` (platform).
- Driver entry: `transport.driver_dashboard` + `transport.driver_dashboard_slash`.

### 14.7 Service reuse map (available, do not duplicate)

22 modules under `app/transport/services/` (dashboard, booking, reservation,
matching, assignment, provider, settings, tracking, notification,
availability, …) + 40 REST endpoints + repositories under
`app/transport/repositories/`. Candidate consolidation must route through
these; no second transport engine.

### 14.8 GATE 1 verdict

**GATE 1 (DISCOVERY): PASS.** The Transport Admin / Operations capability
surface is mapped with runtime + authoritative-source evidence sufficient to
authorize a decision node. **IMPLEMENTATION AUTHORIZATION REQUIRED** — no
implementation was performed. Open items are classified in `BACKLOG.md`
(`PHASE-D1-*`).

---

## 15. Phase D2 — Transport Admin / Operations Decision Gate (DECISION ONLY)

**Node:** Phase D2, GATE 2. **Mode:** DECISION. **Classification:**
BEHAVIORAL / ARCHITECTURAL decision. **No application code, template, CSS/JS,
model, test, or migration was modified. Application files changed: NONE.**

This section records **DECISIONS**. It does not implement. Labels: `DISCOVERED`
(from D1), `DECIDED` (this gate), `AUTHORIZED FOR D3`, `DEFERRED`.

### 15.1 D1 evidence accepted — DECIDED

All D1 facts in §14 are accepted as the decision basis.

### 15.2 Canonical Transport Admin entry — DECIDED

- **CANONICAL:** `/admin/transport-admin` (`admin.transport_admin_*`, D0
  permission-gated family). It is the single Platform Transport Admin entry.
- `/transport/admin/*` (`transport_admin_bp`) — **legacy**, preserve
  temporarily, candidate future retirement (13/14 routes broken).
- `/transport/dashboard` and `/transport/dashboard/overview` —
  **preserve temporarily** (legacy operations dashboard, login-only); mark
  candidate for later redirect to the canonical entry.
- `/transport/admin/dashboard` — **legacy/broken** (self-redirect loop);
  preserve, defer repair to an optional node; not canonical.
- **No route may be deleted in D2.**

### 15.3 Canonical authority — DECIDED

Confirm D0: `transport_admin` + `transport.view` + `transport.manage`;
`transport.settings` retained for `owner` / `super_admin`. `owner`,
`super_admin`, `admin` retain existing broader platform authority. **No
authorization redesign. No new permissions.**

### 15.4 Workspace boundaries — DECIDED

| Workspace | Entry | Context | Authority |
|---|---|---|---|
| Platform Transport Admin | `/admin/transport-admin` | PLATFORM | `transport.view` / `transport.manage` |
| Organisation Transport | `/org/<org_id>/transport` | ORGANISATION | `org.transport.manage` |
| Driver Workspace | `/transport/driver-dashboard` | DRIVER | `transport.driver` |
| Moderator | `/admin/moderator/transport/*` | PLATFORM | `require_role(*_MOD)` |

Invariant preserved: **ownership ≠ driver participation ≠ vehicle assignment
≠ dispatch ≠ organisation fleet authority.**

### 15.5 Canonical information architecture — DECIDED

OVERVIEW · OPERATIONS (Bookings, Reservations, Dispatch, Scheduled Routes) ·
FLEET (Vehicles, Drivers, Assignments, Driver Compliance) · NETWORK
(Organisations, Fleet Operations) · SAFETY (Incidents) · INSIGHTS (Analytics,
Reports) · CONFIGURATION (Settings) · OVERSIGHT (Audit/Alerts + read-only
Moderation link). Grouping matches existing D1 capabilities; **Dispatch**,
**Analytics drivers/vehicles/history**, and **Settings** are not yet ready and
are gated below. Organisation, Driver, and Moderator surfaces remain
**separate**.

### 15.6 Shell decision — DECIDED

- Canonical Transport Admin shell: `templates/admin/transport_admin_dashboard.html`
  (+ future `templates/admin/transport_admin/` sub-templates).
- Canonical Driver shell: `templates/transport/driver/base.html`.
- Organisation shell: `templates/base.html` (org transport page).
- Moderator shell: existing moderator templates.
- Legacy shells: `templates/transport/base.html`,
  `templates/transport/dashboard/base_dashboard.html`, `keep.html` —
  preserve, candidate future retirement; broken asset paths recorded.

### 15.7 Capability batch order — AUTHORIZED FOR D3

- **D3-A** Canonical Admin shell + Overview (prereq: `datetimeformat` filter).
- **D3-B** Bookings + Reservations.
- **D3-C** Drivers + Vehicles + Assignments + Driver Compliance.
- **D3-D** Scheduled Routes (Dispatch UI **deferred/blocked** — TH-3-D2
  implementation not authorized).
- **D3-E** Incidents.
- **D3-F** Analytics + Reports.
- **D3-G** Settings + Oversight.

### 15.8 Service reuse decision — DECIDED / AUTHORIZED FOR D3

| Capability | Canonical service | Existing method | D3? | Deferred? |
|---|---|---|---|---|
| Overview | `app/transport/services/dashboard_service.py` | `get_admin_dashboard_context()` | Yes | — |
| Bookings | `booking_service.py` | `count_bookings`, `get_recent_bookings`, `count_bookings_by_status` | Yes | — |
| Reservations | `reservation_service.py` | reservation methods | Yes | — |
| Drivers | `provider_service.py` | `count_pending_drivers`, `count_active_drivers`, driver CRUD | Yes | — |
| Vehicles | `provider_service.py` | `count_pending_vehicles`, `count_available_vehicles`, vehicle CRUD | Yes | — |
| Assignments | `assignment_service.py` | assignment primitives | Yes | — |
| Scheduled Routes | `app/transport/api/route_routes.py` / route service | route CRUD | Yes | Dispatch part |
| Incidents | incident service/API | `IncidentListResource` et al. | Yes | — |
| Analytics | `dashboard_service.py` | `get_analytics_data()` **does not exist** | Yes (must add method to existing service) | — |
| Reports | `booking_service.py` | `generate_booking_report()` | Yes | — |
| Settings | `settings_service.py` | settings methods | Yes | — |

**No new service is authorized merely because a page is missing.**

### 15.9 Authorization decisions — DECIDED

- Transport Admin + PLATFORM + `transport.view` → read Operations/Fleet/Network/Safety/Insights/Overview.
- Transport Admin + `transport.manage` → authorized Transport mutations.
- Transport Admin + `transport.settings` → settings (owner/super_admin only).
- Organisation + `org.transport.manage` → organisation fleet scope (unchanged).
- Driver + `transport.driver` → Driver Workspace (unchanged).
- Moderator + `require_role(*_MOD)` → moderation (unchanged).

### 15.10 Moderation decision — DECIDED

`/admin/moderator/transport/*` remains a **separate** moderation authority
surface. The future Admin UI may add a **link / read-only status /
operational indicator** only. **No authorization merge.**

### 15.11 REST decision — DECIDED

`GET /api/transport/settings` (login-only) and `POST /api/transport/incidents`
(no decorator) are **NOT** D3 scope. They are deferred to a separate
**PHASE-D-AUTH-REST** node. **No API changes in D2.** (Revisit only if a
direct dependency blocks the canonical Admin UI.)

### 15.12 Broken surface classification — DECIDED

| Finding | Classification |
|---|---|
| `datetimeformat` unregistered filter | **D3-A implementation dependency** (prereq) |
| Missing `templates/admin/transport_admin/` sub-templates | **D3 implementation dependency** (A–G) |
| `get_analytics_data()` missing | **D3 implementation dependency** (F) |
| Missing analytics `drivers/vehicles/history` routes | **D3 optional repair** (F) |
| Broken static asset paths in legacy shells | **D3 optional repair** (A) |
| Dangling endpoints (`transport_admin.admin_dashboard`, `keep.html`) | **D3 optional repair** |
| `/transport/admin/dashboard` self-redirect loop | **Legacy/deferred** (optional repair) |
| `/transport/admin/*` broken `role_required` | **Legacy/deferred** (PHASE-D0-2) |
| `transport_permissions` test-bootstrap gap + malformed model | **Separate node** (PHASE-D0-3 / future architecture) |
| REST auth exposure | **Separate authorization node** (PHASE-D-AUTH-REST) |

### 15.13 Legacy preservation — DECIDED

No deletion of legacy dashboards, shells, routes, moderator surfaces,
templates, or authorization mechanisms. All marked **candidate for future
retirement**; retirement requires a later explicit cleanup gate.

### 15.14 No new permissions / no migration — DECIDED

Continue `transport.view` / `transport.manage` / `transport.settings`.
**NO DATABASE MIGRATION.** Any schema/new-table/new-column/enum/constraint
requirement is `BLOCKED / FUTURE ARCHITECTURE NODE`.

### 15.15 D3 implementation boundary — AUTHORIZED

- **D3 MAY IMPLEMENT:** register/fix `datetimeformat`; build canonical
  `templates/admin/transport_admin/` sub-templates; repair canonical admin
  static asset references; fix dangling references; surface existing services
  in the canonical Admin family; add `get_analytics_data()` to the existing
  dashboard service; add missing analytics routes for existing templates;
  correct broken analytics endpoints.
- **D3 MUST NOT IMPLEMENT:** REST authorization remediation; new permissions;
  schema/migration; route deletion; moderator merge; Driver/Organisation
  workspace changes; dynamic `TransportPermission` redesign; dispatch engine;
  legacy retirement.
- **D3 MUST PRESERVE:** all legacy routes/shells; D0 authority; Org/Driver/
  Moderator scoping; the ownership/participation/assignment/dispatch/fleet
  invariant.
- **D3 ACCEPTANCE CRITERIA:** `/admin/transport-admin` canonical entry renders
  200 for `transport_admin`; ordinary user denied; Driver Workspace unchanged
  (200); Organisation transport unchanged; Overview uses existing
  `DashboardService` (no business logic in routes); every batch leaves
  legacy surfaces intact.

### 15.16 D2 verdict

**GATE 2: PASS.**
**IMPLEMENTATION AUTHORIZATION FOR D3 IS NOW SEPARATELY DEFINED.**
No D3 implementation performed in this gate. Deferred/blocked items are
recorded in `BACKLOG.md` (`PHASE-D2-*`).


### 15.17 Phase D3-A � Canonical Foundation (implemented, Gate 3)

- **Canonical entry:** `/admin/transport-admin` (`admin.transport_admin_dashboard`), guard = `login_required` + `require_permission("transport.view")` + `active_context_or_platform_required(PLATFORM)`.
- **Canonical shell:** `templates/admin/transport_admin_dashboard.html` (extends `base.html`; Overview nav active; Operations/Fleet/Network/Safety/Insights/Configuration/Oversight rendered as aria-disabled `Soon` chips � no dead links).
- **Overview data:** exclusively `DashboardService.get_admin_dashboard_context()`; route performs no business calculations; deterministic `abort(500)` on service failure (no self-redirect).
- **Template-helper collision resolved:** the service context's `module_enabled` boolean is popped before render so `base.html` `{% if module_enabled('wallet') %}` stays callable.
- **Prerequisite filter:** `datetimeformat` registered centrally in `create_app`.
- **Scope discipline:** D3-B..G, REST auth remediation, legacy retirement, dynamic `TransportPermission` redesign, Dispatch changes NOT implemented.

### 15.18 Phase D4-A � Verification (Gate 4, 2026-09-18)

- **Tests (focused + regression): 93 passed, 0 failed.**
  - `test_transport_admin_canonical_overview.py` � 11 passed.
  - `test_transport_admin_permission_authority.py` + `test_transport_drivers_admin_lock.py` + `test_transport_dashboard_overview.py` � 31 passed.
  - `test_driver_workspace_consolidation.py` + `test_driver_workspace_activation.py` + `test_provider_participation.py` � 51 passed.
- **Startup:** `create_app()` ? `STARTUP_OK`; endpoint validator: all known endpoint references validated successfully.
- **Browser proof (live server, test DB, throwaway users, since removed):**
  - `transport_admin` ? `/admin/transport-admin` 200; canonical shell + Overview KPIs (Total Bookings, Active Drivers, Available Vehicles, Today's Completed Revenue) + status breakdowns + Recent Activity empty-state + "data via DashboardService" footer render; 7 disabled nav chips present; **zero console errors/warnings** (no missing filter/asset/template error). Screenshot: `proof_g4_transport_admin_canonical.png`.
  - ordinary `user` ? denied (redirect to `/`, no admin content, no login bounce).
  - Driver ? `/admin/transport-admin` denied (redirect to `/`); Driver Workspace `/transport/driver-dashboard` 200.
  - `super_admin` ? 200; `admin` and `owner` ? 200 (pytest).
- **Acceptance criteria:** all 14 D3-A criteria satisfied (entry/canonical, authority matrix, Driver/Org/Platform boundaries, DashboardService-only Overview, no duplicated business logic, `datetimeformat`, valid template context, assets resolve, legacy surfaces preserved, no migration/schema change, no D3-B..G implemented).
- **Deferred findings (pre-existing, NOT fixed in Gate 4):** Driver Workspace template references missing `static/transport/js/utils.js` (404); `test_transport_restful_auth.py` 2 fails (RESTful `@login_required`?500, deferred PHASE-D-AUTH-REST).
- **GATE 4: PASS.**
