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
| `templates/transport/driver_dashboard.html` | Consolidated Driver Home: hero + online toggle + stats + Go-Live checklist retained; added Current Assigned Vehicle, My (owned) Vehicles, Earnings, Upcoming Assignments, Recent Trips. Removed admin/dead links (`transport.drivers_verification`, `transport.drivers_location`, `transport.drivers_history`, booker-owned `transport.bookings_show`). My Vehicles now points to `transport.vehicle_dashboard` (NOT the global `transport.vehicles_index`). |
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

